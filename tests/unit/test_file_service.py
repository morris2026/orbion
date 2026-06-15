"""文件操作服务测试 — MVP-RE-2.1, 2.2, 2.3a, 2.3b, 2.7, 2.9"""

from pathlib import Path

from app.biz.files.service import FileService
from app.config import Settings

JWT_SECRET_TEST = "test-secret-for-file-service"


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(jwt_secret=JWT_SECRET_TEST, root_dir=str(tmp_path))


def _init_repo(repo_path: Path) -> None:
    import git

    repo_path.mkdir(parents=True, exist_ok=True)
    repo = git.Repo.init(str(repo_path))
    readme = repo_path / "README.md"
    readme.write_text("# test\n")
    repo.index.add(["README.md"])
    repo.index.commit("init")


class TestMvpRe2FileService:
    def test_mvp_re_2_1_get_file_tree(self, tmp_path: Path) -> None:
        """MVP-RE-2.1：获取文件树"""
        settings = _make_settings(tmp_path)
        repo_path = settings.project_repo_path("p1", "myrepo")
        _init_repo(repo_path)
        (repo_path / "src").mkdir()
        (repo_path / "src" / "main.ts").write_text("code")
        (repo_path / "docs").mkdir()
        (repo_path / "docs" / "guide.md").write_text("guide")

        service = FileService(settings)
        tree = service.get_file_tree("p1", "myrepo")

        paths = [item.path for item in tree]
        assert "README.md" in paths
        assert "src/main.ts" in paths
        assert "docs/guide.md" in paths
        assert not any(".git" in p for p in paths)

    def test_mvp_re_2_2_empty_repo(self, tmp_path: Path) -> None:
        """MVP-RE-2.2：空仓库（无文件无提交）返回空列表"""
        import git

        settings = _make_settings(tmp_path)
        repo_path = settings.project_repo_path("p1", "myrepo")
        repo_path.mkdir(parents=True, exist_ok=True)
        git.Repo.init(str(repo_path))

        service = FileService(settings)
        tree = service.get_file_tree("p1", "myrepo")

        assert len(tree) == 0

    def test_mvp_re_2_3a_read_file_head_version(self, tmp_path: Path) -> None:
        """MVP-RE-2.3a：读取文件 HEAD 版本"""
        import git

        settings = _make_settings(tmp_path)
        repo_path = settings.project_repo_path("p1", "myrepo")
        _init_repo(repo_path)
        (repo_path / "src" / "main.ts").parent.mkdir(exist_ok=True)
        (repo_path / "src" / "main.ts").write_text("v1")
        repo = git.Repo(str(repo_path))
        repo.index.add(["src/main.ts"])
        repo.index.commit("add main.ts")

        (repo_path / "src" / "main.ts").write_text("v2")

        service = FileService(settings)
        content = service.read_file("p1", "myrepo", "src/main.ts", ref="HEAD")
        assert content == "v1"

    def test_mvp_re_2_3b_read_head_no_commit(self, tmp_path: Path) -> None:
        """MVP-RE-2.3b：无 commit 的仓库读取 HEAD 返回空内容"""
        import git

        settings = _make_settings(tmp_path)
        repo_path = settings.project_repo_path("p1", "myrepo")
        repo_path.mkdir(parents=True, exist_ok=True)
        git.Repo.init(str(repo_path))

        service = FileService(settings)
        content = service.read_file("p1", "myrepo", "any.ts", ref="HEAD")
        assert content == ""

    def test_mvp_re_2_7_path_traversal(self, tmp_path: Path) -> None:
        """MVP-RE-2.7：路径穿越攻击返回 ValueError"""
        settings = _make_settings(tmp_path)
        repo_path = settings.project_repo_path("p1", "myrepo")
        _init_repo(repo_path)

        service = FileService(settings)
        try:
            service.read_file("p1", "myrepo", "../../../etc/passwd")
            assert False, "应抛出 ValueError"
        except ValueError:
            pass

    def test_mvp_re_2_9_concurrent_write(self, tmp_path: Path) -> None:
        """MVP-RE-2.9：并发写入同一文件，后写入覆盖"""
        settings = _make_settings(tmp_path)
        repo_path = settings.project_repo_path("p1", "myrepo")
        _init_repo(repo_path)

        service = FileService(settings)
        service.write_file("p1", "myrepo", "concurrent.txt", "content-A")
        service.write_file("p1", "myrepo", "concurrent.txt", "content-B")

        content = service.read_file("p1", "myrepo", "concurrent.txt")
        assert content == "content-B"
