"""仓库管理服务 — 扫描/添加/删除"""

import asyncio
import logging
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from app.biz.credentials.service import CredentialService
from app.biz.threads.service import ThreadService
from app.config import Settings

logger = logging.getLogger(__name__)


class RepoService:
    """项目仓库管理：扫描项目目录下的 git 仓库，添加/删除仓库"""

    def __init__(
        self, settings: Settings, credential_service: CredentialService, thread_service: ThreadService
    ) -> None:
        self._settings = settings
        self._credential_service = credential_service
        self._thread_service = thread_service

    def _repo_root(self, project_id: str) -> Path:
        return self._settings.project_dir(project_id) / "repo"

    def scan_repos(self, project_id: str) -> list[dict[str, str]]:
        """扫描项目目录下的 git 仓库"""
        repo_root = self._repo_root(project_id)
        if not repo_root.exists():
            return []
        repos = []
        for entry in sorted(repo_root.iterdir()):
            if entry.is_dir() and (entry / ".git").is_dir():
                repos.append({"name": entry.name})
        return repos

    async def add_repo(
        self,
        project_id: str,
        *,
        url: str | None = None,
        name: str | None = None,
        user_id: str | None = None,
        thread_id: str | None = None,
    ) -> dict[str, str]:
        """添加仓库：URL 则 git clone，目录名则 git init。失败时返回包含 error 键的字典"""
        repo_name = name
        if url and not name:
            repo_name = url.rstrip("/").split("/")[-1]
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]

        if not repo_name:
            return {"error": "需要提供 url 或 name"}

        if os.sep in repo_name or "/" in repo_name or "\\" in repo_name or ".." in repo_name:
            return {"error": f"无效的仓库名: {repo_name}"}

        repo_root = self._repo_root(project_id)
        target = repo_root / repo_name

        if target.exists():
            return {"error": f"目录已存在: {repo_name}"}

        if url:
            # SSH URL 不支持自动凭据注入，需要 SSH 密钥
            if url.startswith("git@") or url.startswith("ssh://"):
                return {"error": "不支持 SSH URL，请使用 HTTPS 地址"}
            # 克隆前通知
            if thread_id:
                await self._thread_service.send_system_message(project_id, thread_id, f"正在克隆仓库 {url}...")
            try:
                credential_helper = self._build_credential_helper(user_id, url)
                env = os.environ.copy()
                git_cmd = ["git", "clone", url, str(target)]
                if credential_helper:
                    git_cmd = ["git", "-c", f"credential.helper={credential_helper}", "clone", url, str(target)]

                await asyncio.to_thread(subprocess.run, git_cmd, check=True, capture_output=True, text=True, env=env)

                # clone 后配置 repo 级 credential helper，后续 pull/push 也自动认证
                if credential_helper:
                    await asyncio.to_thread(self._configure_repo_credential_helper, target, credential_helper)

                if thread_id:
                    await self._thread_service.send_system_message(project_id, thread_id, f"仓库 {repo_name} 已克隆")
                return {"name": repo_name}
            except subprocess.CalledProcessError as e:
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                logger.warning("git clone failed for %s: %s", url, e.stderr.strip())
                if thread_id:
                    await self._thread_service.send_system_message(project_id, thread_id, f"仓库克隆失败：{url}")
                return {"error": "clone 失败，请检查 URL 和凭据"}
            except Exception as e:
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                logger.warning("git clone failed for %s: %s", url, e)
                if thread_id:
                    await self._thread_service.send_system_message(project_id, thread_id, f"仓库克隆失败：{url}")
                return {"error": "clone 失败，请检查 URL 和凭据"}
        else:
            # 初始化前通知
            if thread_id:
                await self._thread_service.send_system_message(project_id, thread_id, f"正在初始化仓库 {repo_name}...")
            try:
                target.mkdir(parents=True, exist_ok=True)
                await asyncio.to_thread(
                    subprocess.run, ["git", "init", str(target)], check=True, capture_output=True, text=True
                )
                if thread_id:
                    await self._thread_service.send_system_message(project_id, thread_id, f"仓库 {repo_name} 已初始化")
                return {"name": repo_name}
            except subprocess.CalledProcessError as e:
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                logger.warning("git init failed: %s", e.stderr.strip())
                if thread_id:
                    await self._thread_service.send_system_message(
                        project_id, thread_id, f"仓库初始化失败：{repo_name}"
                    )
                return {"error": "init 失败，请检查目录名"}
            except Exception as e:
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                logger.warning("git init failed: %s", e)
                if thread_id:
                    await self._thread_service.send_system_message(
                        project_id, thread_id, f"仓库初始化失败：{repo_name}"
                    )
                return {"error": "init 失败，请检查目录名"}

    def delete_repo(self, project_id: str, repo_name: str) -> bool:
        """删除仓库（删除物理目录），目录不存在返回 False"""
        if os.sep in repo_name or "/" in repo_name or "\\" in repo_name or ".." in repo_name:
            raise ValueError(f"无效的仓库名: {repo_name}")
        repo_root = self._repo_root(project_id)
        target = repo_root / repo_name
        if not target.exists():
            return False
        shutil.rmtree(target, ignore_errors=True)
        return True

    def _build_credential_helper(self, user_id: str | None, url: str) -> str | None:
        """构建 git credential helper 命令字符串，无匹配凭据时返回 None"""
        if not user_id:
            return None

        # UUID 验证防止注入
        uid = str(uuid.UUID(user_id))

        credential = self._credential_service.match_credential(uid, url)
        if not credential:
            return None

        # 写临时 helper 脚本：接收 git 传入的 protocol+host，输出 username+password
        helper_script = self._write_helper_script(uid, credential.id)
        return f'!"{sys.executable}" "{helper_script}"'

    def _write_helper_script(self, user_id: str, credential_id: str) -> str:
        """写入临时 credential helper 脚本，返回脚本路径"""
        # UUID 验证 + 标准化，确保嵌入脚本内容安全
        uid = str(uuid.UUID(user_id))
        cid = str(uuid.UUID(credential_id))

        helpers_dir = Path(self._settings.root_dir) / "temp" / "credential-helpers"
        helpers_dir.mkdir(parents=True, exist_ok=True)
        helpers_dir.chmod(0o700)
        self._cleanup_old_helpers(helpers_dir)

        script_path = helpers_dir / f"helper-{uid}-{cid}.py"

        # 从当前运行环境获取 app 包路径
        import app as _app_mod

        app_path = repr(str(Path(_app_mod.__file__).parent.parent))

        # UUID 已标准化为 hex+hyphen，安全嵌入 f-string
        script_content = f'''import sys
sys.path.insert(0, {app_path})
from app.config import get_settings as _get_settings
from app.biz.credentials.service import CredentialService as _Svc

_settings = _get_settings()
_service = _Svc(_settings)

def main():
    lines = sys.stdin.read().strip().split("\\n")
    protocol = host = None
    for line in lines:
        if "=" in line:
            k, v = line.split("=", 1)
            if k == "protocol": protocol = v
            elif k == "host": host = v

    if not protocol or not host:
        return

    # 验证 git 请求的 host 与凭据匹配
    credential = _service.match_credential("{uid}", f"{{protocol}}://{{host}}")
    if not credential or credential.id != "{cid}":
        return

    token = _service.get_token("{uid}", "{cid}")
    if token:
        print("username=x-access-token")
        print(f"password={{token}}")

if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "get":
        main()
'''
        script_path.write_text(script_content)
        script_path.chmod(0o700)
        return str(script_path)

    def _cleanup_old_helpers(self, helpers_dir: Path, max_age_hours: int = 24) -> None:
        """清理过期的 credential helper 脚本"""
        now = time.time()
        for f in helpers_dir.iterdir():
            if f.is_file() and f.suffix == ".py":
                if now - f.stat().st_mtime > max_age_hours * 3600:
                    f.unlink(missing_ok=True)

    def _configure_repo_credential_helper(self, repo_path: Path, helper: str) -> None:
        """在 repo 级别配置 credential.helper"""
        subprocess.run(
            ["git", "config", "credential.helper", helper],
            check=True,
            capture_output=True,
            cwd=str(repo_path),
        )
