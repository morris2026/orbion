"""Source Control 服务测试 — MVP-RE-3.1, 3.2, 3.4"""

from pathlib import Path
from unittest.mock import MagicMock

import git

from app.biz.git.service import GitService
from app.config import Settings

JWT_SECRET_TEST = "test-secret-for-git-sc"


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(jwt_secret=JWT_SECRET_TEST, root_dir=str(tmp_path))


def _make_git_service(settings: Settings) -> GitService:
    """创建测试用 GitService，用 mock 替代 EventBus 和 Projections"""
    mock_bus = MagicMock()
    mock_projections = MagicMock()
    return GitService(settings, mock_bus, mock_projections)


def _init_repo_with_changes(repo_path: Path) -> None:
    """创建仓库并产生已修改+已staged文件"""
    repo_path.mkdir(parents=True, exist_ok=True)
    repo = git.Repo.init(str(repo_path))
    (repo_path / "README.md").write_text("# init\n")
    (repo_path / "modified.txt").write_text("v1")
    repo.index.add(["README.md", "modified.txt"])
    repo.index.commit("init")

    (repo_path / "modified.txt").write_text("changed")
    (repo_path / "staged.txt").write_text("new file")
    repo.index.add(["staged.txt"])


class TestMvpRe3GitScService:
    def test_mvp_re_3_1_status_with_changes(self, tmp_path: Path) -> None:
        """MVP-RE-3.1：status 返回 staged 和 changes 分组"""
        settings = _make_settings(tmp_path)
        repo_path = settings.project_repo_path("p1", "myrepo")
        _init_repo_with_changes(repo_path)

        service = _make_git_service(settings)
        result = service.status("p1", "myrepo")

        assert "staged" in result
        assert "changes" in result
        staged_paths = [f["path"] for f in result["staged"]]
        changes_paths = [f["path"] for f in result["changes"]]
        assert "staged.txt" in staged_paths
        assert "modified.txt" in changes_paths
        staged_entry = next(f for f in result["staged"] if f["path"] == "staged.txt")
        changes_entry = next(f for f in result["changes"] if f["path"] == "modified.txt")
        assert staged_entry["status"] == "A"
        assert changes_entry["status"] == "M"

    def test_mvp_re_3_2_status_no_changes(self, tmp_path: Path) -> None:
        """MVP-RE-3.2：无变更时 staged 和 changes 均为空"""
        settings = _make_settings(tmp_path)
        repo_path = settings.project_repo_path("p1", "myrepo")
        repo_path.mkdir(parents=True, exist_ok=True)
        repo = git.Repo.init(str(repo_path))
        (repo_path / "README.md").write_text("# init\n")
        repo.index.add(["README.md"])
        repo.index.commit("init")

        service = _make_git_service(settings)
        result = service.status("p1", "myrepo")

        assert result["staged"] == []
        assert result["changes"] == []

    def test_unstage_new_file_with_commit(self, tmp_path: Path) -> None:
        """有 commit 的仓库 unstage 新增文件(A)：文件从 staged 移到 changes"""
        settings = _make_settings(tmp_path)
        repo_path = settings.project_repo_path("p1", "myrepo")
        _init_repo_with_changes(repo_path)

        service = _make_git_service(settings)
        staged_before = [f["path"] for f in service.status("p1", "myrepo")["staged"]]
        assert "staged.txt" in staged_before

        service.unstage("p1", "myrepo", ["staged.txt"])

        result = service.status("p1", "myrepo")
        staged_paths = [f["path"] for f in result["staged"]]
        changes_paths = [f["path"] for f in result["changes"]]
        assert "staged.txt" not in staged_paths
        assert "staged.txt" in changes_paths
        # 工作区文件仍在
        assert (repo_path / "staged.txt").exists()

    def test_unstage_modified_file_with_commit(self, tmp_path: Path) -> None:
        """有 commit 的仓库 unstage 修改文件(M)：staged 清空，工作区内容不变"""
        settings = _make_settings(tmp_path)
        repo_path = settings.project_repo_path("p1", "myrepo")
        repo_path.mkdir(parents=True, exist_ok=True)
        repo = git.Repo.init(str(repo_path))
        (repo_path / "README.md").write_text("init")
        repo.index.add(["README.md"])
        repo.index.commit("init")
        (repo_path / "README.md").write_text("modified")
        repo.index.add(["README.md"])

        service = _make_git_service(settings)
        staged_before = [f["path"] for f in service.status("p1", "myrepo")["staged"]]
        assert "README.md" in staged_before

        service.unstage("p1", "myrepo", ["README.md"])

        result = service.status("p1", "myrepo")
        staged_paths = [f["path"] for f in result["staged"]]
        changes_paths = [f["path"] for f in result["changes"]]
        assert "README.md" not in staged_paths
        assert "README.md" in changes_paths
        # 工作区内容保持修改后状态
        assert (repo_path / "README.md").read_text() == "modified"

    def test_unstage_file_no_commit(self, tmp_path: Path) -> None:
        """无 commit 的仓库 unstage 文件：从 index 移除，文件变为 untracked"""
        settings = _make_settings(tmp_path)
        repo_path = settings.project_repo_path("p1", "myrepo")
        repo_path.mkdir(parents=True, exist_ok=True)
        repo = git.Repo.init(str(repo_path))
        (repo_path / "new.txt").write_text("hello")
        repo.index.add(["new.txt"])

        service = _make_git_service(settings)
        staged_before = [f["path"] for f in service.status("p1", "myrepo")["staged"]]
        assert "new.txt" in staged_before

        service.unstage("p1", "myrepo", ["new.txt"])

        result = service.status("p1", "myrepo")
        staged_paths = [f["path"] for f in result["staged"]]
        changes_paths = [f["path"] for f in result["changes"]]
        assert "new.txt" not in staged_paths
        assert "new.txt" in changes_paths
