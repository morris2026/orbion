"""仓库管理服务测试 — MVP-RE-1.1, 1.2, 1.5a, 1.5b"""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.biz.credentials.service import CredentialService
from app.biz.repos.service import RepoService
from app.biz.threads.service import ThreadService
from app.config import Settings

JWT_SECRET_TEST = "test-secret-for-repo-service"


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(jwt_secret=JWT_SECRET_TEST, root_dir=str(tmp_path))


def _make_repo_service(tmp_path: Path) -> RepoService:
    settings = _make_settings(tmp_path)
    credential_service = CredentialService(settings)
    thread_service = ThreadService(AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock())
    return RepoService(settings, credential_service, thread_service)


class TestMvpRe1RepoScan:
    def test_mvp_re_1_1_scan_git_repos(self, tmp_path: Path) -> None:
        """MVP-RE-1.1：扫描项目目录下的git仓库"""
        import git

        settings = _make_settings(tmp_path)
        project_id = "p1"
        repo_root = settings.project_dir(project_id) / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)

        (repo_root / "repo_a").mkdir()
        git.Repo.init(str(repo_root / "repo_a"))
        (repo_root / "repo_b").mkdir()
        git.Repo.init(str(repo_root / "repo_b"))

        service = _make_repo_service(tmp_path)
        repos = service.scan_repos(project_id)

        repo_names = [r["name"] for r in repos]
        assert "repo_a" in repo_names
        assert "repo_b" in repo_names

    def test_mvp_re_1_2_scan_excludes_non_git(self, tmp_path: Path) -> None:
        """MVP-RE-1.2：扫描排除非git目录"""
        import git

        settings = _make_settings(tmp_path)
        project_id = "p1"
        repo_root = settings.project_dir(project_id) / "repo"
        repo_root.mkdir(parents=True, exist_ok=True)

        (repo_root / "no_git").mkdir()
        (repo_root / "has_git").mkdir()
        git.Repo.init(str(repo_root / "has_git"))

        service = _make_repo_service(tmp_path)
        repos = service.scan_repos(project_id)

        repo_names = [r["name"] for r in repos]
        assert "has_git" in repo_names
        assert "no_git" not in repo_names

    @pytest.mark.asyncio
    async def test_mvp_re_1_5b_invalid_repo_name_rejected(self, tmp_path: Path) -> None:
        """MVP-RE-1.5b：含路径分隔符的目录名被拒绝"""
        service = _make_repo_service(tmp_path)

        result = await service.add_repo("p1", name="../evil")
        assert result is None or "error" in result

    @pytest.mark.asyncio
    async def test_mvp_re_1_5a_clone_failure(self, tmp_path: Path) -> None:
        """MVP-RE-1.5a：clone 无效 URL 失败返回错误"""
        service = _make_repo_service(tmp_path)

        result = await service.add_repo("p1", url="https://nonexistent.invalid/repo.git")
        assert result is not None and "error" in result
