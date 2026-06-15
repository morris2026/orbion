"""Source Control 服务测试 — MVP-RE-3.1, 3.2"""

from pathlib import Path

from app.biz.git.service import GitService
from app.config import Settings

JWT_SECRET_TEST = "test-secret-for-git-sc"


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(jwt_secret=JWT_SECRET_TEST, root_dir=str(tmp_path))


def _init_repo_with_changes(repo_path: Path) -> None:
    """创建仓库并产生已修改+已staged文件"""
    import git

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

        service = GitService.__new__(GitService)
        service._settings = settings
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
        import git

        settings = _make_settings(tmp_path)
        repo_path = settings.project_repo_path("p1", "myrepo")
        repo_path.mkdir(parents=True, exist_ok=True)
        repo = git.Repo.init(str(repo_path))
        (repo_path / "README.md").write_text("# init\n")
        repo.index.add(["README.md"])
        repo.index.commit("init")

        service = GitService.__new__(GitService)
        service._settings = settings
        result = service.status("p1", "myrepo")

        assert result["staged"] == []
        assert result["changes"] == []
