"""GitCommandService — git 命令封装（worktree / branch / merge / fetch）

纯命令封装层，不引入业务逻辑。所有 git 操作通过 subprocess 调用 git 二进制，
返回结构化结果（WorktreeResult / MergeResult）。全局 git 锁由上层 WorktreeService
负责（见 §5.4），本模块只做单次命令的封装。

Why 单独类：app/biz/git/service.py 已有 GitService（GitPython 封装，管 file-level
status/stage/commit + 事件驱动 commit-on-approve）。本类是 worktree 生命周期层，
用 subprocess（设计文档 §6.4 要求）。两者职责不同，未来步骤可考虑合并。

设计文档：docs/specs/1.10-mvp-git-worktree-model.md §5、§6.4
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WorktreeResult:
    """git worktree / branch / fetch 命令的统一返回结构"""

    success: bool
    message: str = ""
    error: str = ""


@dataclass
class MergeResult:
    """git merge 命令的返回结构

    success=False 且 has_conflicts=True 时，conflict_files 列出冲突文件路径；
    merge 已自动 abort，目标 worktree 回到合并前状态。
    """

    success: bool
    has_conflicts: bool = False
    conflict_files: list[str] = field(default_factory=list)
    error: str = ""


@dataclass
class MergeFileResult:
    """git merge-file 命令的返回结构（单文件三方合并）

    success=True 时 merged_content 为合并结果；
    success=False 时 merged_content 含冲突标记（<<<<<<< / ||||||| / ======= / >>>>>>>），
    conflict_markers 列出每个冲突块（含完整标记的字符串）。
    """

    success: bool
    merged_content: str = ""
    conflict_markers: list[str] = field(default_factory=list)
    error: str = ""


class GitCommandService:
    """git 二进制命令封装

    所有方法均为同步阻塞调用——git 操作通常毫秒级。调用方（WorktreeService）
    通过 asyncio.to_thread 调度并在全局 _global_git_lock 内串行化（§5.4），
    避免 subprocess 阻塞 event loop。
    """

    # git 命令超时（秒）。Why：防止 ssh 挂起、gc 慢等导致全局锁被无限期持有
    _CMD_TIMEOUT = 30

    def _run(self, args: list[str], cwd: str) -> subprocess.CompletedProcess[str]:
        """执行 git 命令，返回 CompletedProcess（不抛异常，由调用方判断 returncode）

        Why 不抛：本层是命令封装，错误语义由调用方解释（冲突 vs 真错误）。
        超时返回 returncode=124 + error 信息，由调用方作为失败处理。
        """
        try:
            return subprocess.run(
                ["git", *args],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self._CMD_TIMEOUT,
            )
        except subprocess.TimeoutExpired as e:
            # 构造一个失败的 CompletedProcess 返回，保持调用方处理路径统一
            return subprocess.CompletedProcess(
                args=["git", *args],
                returncode=124,
                stdout="",
                stderr=f"git 命令超时（{self._CMD_TIMEOUT}s）: {e}",
            )

    def worktree_add(self, repo_path: str, worktree_path: str, branch_name: str, base_ref: str) -> WorktreeResult:
        """git worktree add <worktree_path> -b <branch_name> <base_ref>

        在 repo_path（通常是 bare 仓库）下创建新 worktree，基于 base_ref 创建 branch_name 分支。
        worktree_path 会被归一化为绝对路径，避免 .git 文件登记相对路径导致后续操作定位失败。
        """
        worktree_path = os.path.abspath(worktree_path)
        proc = self._run(
            ["worktree", "add", "-b", branch_name, worktree_path, base_ref],
            cwd=repo_path,
        )
        if proc.returncode != 0:
            return WorktreeResult(success=False, error=proc.stderr.strip())
        return WorktreeResult(success=True, message=proc.stdout.strip())

    def worktree_remove(self, repo_path: str, worktree_path: str, force: bool = True) -> WorktreeResult:
        """git worktree remove <worktree_path>

        在 repo_path（bare 仓库）下执行，避免 worktree_path 目录已不存在时 cwd 失效。
        Why force=True 默认：Orbion 中 task worktree 通常含未提交产出，归档场景需强制清理；
        调用方需在归档前确保产出已合并或显式丢弃。
        """
        worktree_path = os.path.abspath(worktree_path)
        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(worktree_path)
        proc = self._run(args, cwd=repo_path)
        if proc.returncode != 0:
            return WorktreeResult(success=False, error=proc.stderr.strip())
        return WorktreeResult(success=True, message=proc.stdout.strip())

    def branch_create(self, repo_path: str, branch_name: str, base_ref: str) -> WorktreeResult:
        """git branch <branch_name> <base_ref>"""
        proc = self._run(["branch", branch_name, base_ref], cwd=repo_path)
        if proc.returncode != 0:
            return WorktreeResult(success=False, error=proc.stderr.strip())
        return WorktreeResult(success=True, message=proc.stdout.strip())

    def branch_delete(self, repo_path: str, branch_name: str, force: bool = False) -> WorktreeResult:
        """git branch -d <branch_name>

        Why force=False 默认：安全默认，未合并分支会被 git 拒绝删除（避免误丢产出）。
        archive 流程需显式传 force=True（产出已合并或显式丢弃）。
        """
        args = ["branch", "-D" if force else "-d", branch_name]
        proc = self._run(args, cwd=repo_path)
        if proc.returncode != 0:
            return WorktreeResult(success=False, error=proc.stderr.strip())
        return WorktreeResult(success=True, message=proc.stdout.strip())

    def fetch(self, repo_path: str, remote: str = "origin", refspec: str | None = None) -> WorktreeResult:
        """git fetch <remote> [refspec]

        MVP 阶段通常无远端，本方法为步骤 2 create_or_reuse 预留薄封装（设计 §15 远端同步暂缓）。
        """
        args = ["fetch", remote]
        if refspec:
            args.append(refspec)
        proc = self._run(args, cwd=repo_path)
        if proc.returncode != 0:
            return WorktreeResult(success=False, error=proc.stderr.strip())
        return WorktreeResult(success=True, message=proc.stdout.strip())

    def merge_file(self, mine: str, original: str, theirs: str) -> MergeFileResult:
        """git merge-file --diff3 <mine> <original> <theirs>

        单文件三方合并（设计 §5.2.1）。把三个字符串写入临时文件，调 git merge-file：
        - 返回 0：无冲突，mine 文件变为合并结果
        - 返回非 0：有冲突，mine 文件含冲突标记（<<<<<<< / ||||||| / ======= / >>>>>>>）

        临时文件用完即删。冲突时 merged_content 含完整标记，conflict_markers 列出每个冲突块。
        """
        import re
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            mine_path = Path(tmpdir) / "mine"
            orig_path = Path(tmpdir) / "orig"
            theirs_path = Path(tmpdir) / "theirs"
            mine_path.write_text(mine, encoding="utf-8")
            orig_path.write_text(original, encoding="utf-8")
            theirs_path.write_text(theirs, encoding="utf-8")

            # git merge-file 不需要仓库上下文，cwd 用 tmpdir
            proc = self._run(
                ["merge-file", "--diff3", str(mine_path), str(orig_path), str(theirs_path)],
                cwd=tmpdir,
            )
            # git merge-file 返回冲突数（0=无冲突，>0=冲突数，<0=错误）
            merged = mine_path.read_text(encoding="utf-8")

            if proc.returncode == 0:
                return MergeFileResult(success=True, merged_content=merged)

            if proc.returncode > 0:
                # 冲突：提取每个冲突块。git merge-file --diff3 的标记格式：
                # `<<<<<<< <label>` / `||||||| <label>` / `=======` / `>>>>>>> <label>`
                # 用 `<<<<<<< ` (带空格) 收紧匹配，避免用户原文含 `<<<<<<<` 字面量误匹配
                conflict_blocks = re.findall(
                    r"<<<<<<< .*?>>>>>>> .*?(?:\n|$)",
                    merged,
                    flags=re.DOTALL,
                )
                return MergeFileResult(
                    success=False,
                    merged_content=merged,
                    conflict_markers=conflict_blocks,
                )

            # returncode < 0：真错误（如临时文件 IO 失败）
            return MergeFileResult(
                success=False,
                merged_content=merged,
                error=proc.stderr.strip() or proc.stdout.strip(),
            )

    def merge(self, target_worktree: str, branch: str) -> MergeResult:
        """git merge --no-edit <branch> 到 target_worktree 当前分支

        merge commit message 用 git 默认模板（--no-edit 跳过编辑器交互）；
        上层 WorktreeService 在步骤 4 注入 §9 的 commit author 格式。

        冲突时自动 git merge --abort，target_worktree 回到合并前状态。
        返回 MergeResult(success=False, has_conflicts=True, conflict_files=[...])。
        """
        proc = self._run(["merge", "--no-edit", branch], cwd=target_worktree)
        if proc.returncode == 0:
            return MergeResult(success=True, has_conflicts=False)

        # 非 0 退出：用 status -z 判断是否冲突（NUL 分隔，路径不引号转义）
        status_proc = self._run(["status", "--porcelain", "-z"], cwd=target_worktree)
        conflict_files: list[str] = []
        has_conflicts = False
        for entry in status_proc.stdout.split("\0"):
            if not entry:
                continue
            # porcelain v1：XY <path>，X/Y ∈ {空格, M, T, A, D, R, C, U, ?}
            # 冲突标记：X 或 Y 为 U，或 AA/DD/AU/UA/DU/UD
            if len(entry) >= 2:
                x, y = entry[0], entry[1]
                if x == "U" or y == "U" or (x in {"A", "D"} and y in {"A", "D"}):
                    has_conflicts = True
                    conflict_files.append(entry[3:].strip())

        if has_conflicts:
            self._run(["merge", "--abort"], cwd=target_worktree)
            return MergeResult(
                success=False,
                has_conflicts=True,
                conflict_files=conflict_files,
                error=proc.stderr.strip(),
            )

        # 非 0 退出且无冲突标记：其他错误（如分支不存在）；尝试 abort 兜底
        self._run(["merge", "--abort"], cwd=target_worktree)
        return MergeResult(success=False, has_conflicts=False, error=proc.stderr.strip() or proc.stdout.strip())
