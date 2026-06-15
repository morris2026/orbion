"""仓库管理服务 — 扫描/添加/删除"""

import logging
import os
import shutil
from pathlib import Path

from app.config import Settings

logger = logging.getLogger(__name__)


class RepoService:
    """项目仓库管理：扫描项目目录下的 git 仓库，添加/删除仓库"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

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

    def add_repo(self, project_id: str, *, url: str | None = None, name: str | None = None) -> dict[str, str] | None:
        """添加仓库：URL 则 git clone，目录名则 git init。同名目录已存在返回 None 或错误字典"""
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
            try:
                import git

                git.Repo.clone_from(url, str(target))
                return {"name": repo_name}
            except Exception as e:
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                return {"error": f"clone 失败: {e}"}
        else:
            try:
                import git

                target.mkdir(parents=True, exist_ok=True)
                git.Repo.init(str(target))
                return {"name": repo_name}
            except Exception as e:
                if target.exists():
                    shutil.rmtree(target, ignore_errors=True)
                return {"error": f"init 失败: {e}"}

    def delete_repo(self, project_id: str, repo_name: str) -> bool:
        """删除仓库（删除物理目录），目录不存在返回 False"""
        repo_root = self._repo_root(project_id)
        target = repo_root / repo_name
        if not target.exists():
            return False
        shutil.rmtree(target, ignore_errors=True)
        return True
