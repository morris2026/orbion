"""文件/Git 模型字段约束测试 — FileNode.type 和 GitFileStatus.status 应拒绝非法值"""

import pytest
from pydantic import ValidationError

from app.biz.files.models import FileNode
from app.biz.git.models import GitFileStatus


class TestFileNodeConstraints:
    def test_file_node_accepts_file_type(self) -> None:
        node = FileNode(path="a.ts", type="file", name="a.ts")
        assert node.type == "file"

    def test_file_node_accepts_dir_type(self) -> None:
        node = FileNode(path="src", type="dir", name="src")
        assert node.type == "dir"

    def test_file_node_rejects_invalid_type(self) -> None:
        with pytest.raises(ValidationError):
            FileNode(path="x", type="symlink", name="x")  # type: ignore[arg-type]


class TestGitFileStatusConstraints:
    def test_git_status_accepts_known_codes(self) -> None:
        for code in ("A", "M", "D", "R", "U"):
            s = GitFileStatus(path="a.ts", status=code)
            assert s.status == code

    def test_git_status_rejects_invalid_code(self) -> None:
        with pytest.raises(ValidationError):
            GitFileStatus(path="a.ts", status="UNKNOWN")  # type: ignore[arg-type]
