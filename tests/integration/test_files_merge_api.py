"""文件保存三方合并 API 集成测试 — GW-3.1 ~ GW-3.3

验证文件保存 API 的 mtime 检测 + 自动三方合并 + 409 冲突响应。
"""

import os
import time

import pytest
from httpx import AsyncClient

from app.config import get_settings
from app.hub.auth.repository import UserRepositoryProvider
from app.hub.auth.service import create_access_token, hash_password
from app.hub.events.bus import InProcessEventBus

pytestmark = pytest.mark.asyncio


async def _create_user(provider: UserRepositoryProvider, username: str) -> dict[str, str]:
    async with provider.scoped() as repo:
        user = await repo.create_user(username, hash_password("testpass123"), username.capitalize(), "active", False)
    token = create_access_token(
        user_id=user.id, username=user.username, display_name=user.display_name, is_admin=False, settings=get_settings()
    )
    return {"id": user.id, "token": token}


async def _create_project(
    client: AsyncClient, token: str, event_bus: InProcessEventBus, name: str = "MergeTestProject"
) -> str:
    resp = await client.post("/projects", json={"name": name}, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    await event_bus.wait_for_pending()
    return str(resp.json()["id"])


async def _add_repo(client: AsyncClient, token: str, project_id: str, name: str = "mergerepo") -> None:
    resp = await client.post(
        f"/projects/{project_id}/repos", json={"name": name}, headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 201


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _file_mtime(project_id: str, repo_name: str, path: str) -> float:
    """读取文件 mtime（Unix 秒，浮点）"""
    from app.config import get_settings

    settings = get_settings()
    full = settings.project_repo_path(project_id, repo_name) / path
    return os.path.getmtime(str(full))


class TestMvpRe3FilesMergeApi:
    async def test_gw_3_1_mtime_same_direct_save(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """GW-3.1：expected_mtime 与当前 mtime 一致，直接保存，不触发三方合并"""
        user = await _create_user(user_repo_provider, "mergeuser1")
        project_id = await _create_project(client, user["token"], event_bus)
        await _add_repo(client, user["token"], project_id)
        # 初始写入文件
        await client.put(
            f"/projects/{project_id}/repos/mergerepo/files",
            params={"path": "notes.md"},
            json={"content": "# v1\n"},
            headers=_auth(user["token"]),
        )
        # 模拟用户 A 打开时记录的 mtime
        expected_mtime = _file_mtime(project_id, "mergerepo", "notes.md")

        # A 保存（无修改并发，mtime 未变）
        resp = await client.put(
            f"/projects/{project_id}/repos/mergerepo/files",
            params={"path": "notes.md"},
            json={"content": "# v2\n", "expected_mtime": expected_mtime, "original_content": "# v1\n"},
            headers=_auth(user["token"]),
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["content"] == "# v2\n"
        # 验证文件已写入
        from app.config import get_settings

        settings = get_settings()
        assert (settings.project_repo_path(project_id, "mergerepo") / "notes.md").read_text() == "# v2\n"

    async def test_gw_3_2_mtime_diff_auto_merge_success(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """GW-3.2：mtime 变化，不同位置修改，git merge-file 成功，返回 200 + 合并内容

        A 的编辑（mine）只含 A 的修改，不含 B 的修改——迫使后端真正执行三方合并，
        否则 B 的修改会丢失。合并结果应同时含 A 和 B 的修改。
        """
        user = await _create_user(user_repo_provider, "mergeuser2")
        project_id = await _create_project(client, user["token"], event_bus)
        await _add_repo(client, user["token"], project_id)
        # 初始文件
        original = "line1\nline2\nline3\n"
        await client.put(
            f"/projects/{project_id}/repos/mergerepo/files",
            params={"path": "feature.md"},
            json={"content": original},
            headers=_auth(user["token"]),
        )
        # A 打开时记录 mtime + original_content
        expected_mtime = _file_mtime(project_id, "mergerepo", "feature.md")

        # B 保存：在文件开头加一行（不同位置）
        time.sleep(0.01)  # 确保 mtime 不同
        theirs = "B_ADDED\nline1\nline2\nline3\n"
        await client.put(
            f"/projects/{project_id}/repos/mergerepo/files",
            params={"path": "feature.md"},
            json={"content": theirs},
            headers=_auth(user["token"]),
        )

        # A 保存：A 在文件末尾加一行（不同位置），A 的 mine 不含 B 的修改
        mine = "line1\nline2\nline3\nA_ADDED\n"
        resp = await client.put(
            f"/projects/{project_id}/repos/mergerepo/files",
            params={"path": "feature.md"},
            json={
                "content": mine,
                "expected_mtime": expected_mtime,
                "original_content": original,
            },
            headers=_auth(user["token"]),
        )

        assert resp.status_code == 200
        merged = resp.json()["content"]
        # 合并结果应同时含 A 和 B 的修改（证明三方合并发生）
        assert "A_ADDED" in merged, "A 的修改丢失"
        assert "B_ADDED" in merged, "B 的修改丢失（未执行三方合并）"
        # 无冲突标记
        assert "<<<<<<<" not in merged

    async def test_gw_3_3_same_position_conflict_returns_409(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """GW-3.3：同位置修改，git merge-file 冲突，返回 409 + merged_content + conflict_markers"""
        user = await _create_user(user_repo_provider, "mergeuser3")
        project_id = await _create_project(client, user["token"], event_bus)
        await _add_repo(client, user["token"], project_id)
        original = "line1\nline2\nline3\n"
        await client.put(
            f"/projects/{project_id}/repos/mergerepo/files",
            params={"path": "conflict.md"},
            json={"content": original},
            headers=_auth(user["token"]),
        )
        expected_mtime = _file_mtime(project_id, "mergerepo", "conflict.md")

        # B 改 line2 位置
        time.sleep(0.01)
        await client.put(
            f"/projects/{project_id}/repos/mergerepo/files",
            params={"path": "conflict.md"},
            json={"content": "line1\nB_VERSION\nline3\n"},
            headers=_auth(user["token"]),
        )

        # A 也改 line2 同位置
        mine = "line1\nA_VERSION\nline3\n"
        resp = await client.put(
            f"/projects/{project_id}/repos/mergerepo/files",
            params={"path": "conflict.md"},
            json={
                "content": mine,
                "expected_mtime": expected_mtime,
                "original_content": original,
            },
            headers=_auth(user["token"]),
        )

        assert resp.status_code == 409
        body = resp.json()
        assert "merged_content" in body
        assert "conflict_markers" in body
        assert "<<<<<<<" in body["merged_content"]
        assert "A_VERSION" in body["merged_content"]
        assert "B_VERSION" in body["merged_content"]
        assert len(body["conflict_markers"]) >= 1

    async def test_gw_3_1a_consecutive_save_no_merge(
        self, client: AsyncClient, user_repo_provider: UserRepositoryProvider, event_bus: InProcessEventBus
    ) -> None:
        """C1 回归：连续两次保存（无并发修改），第二次 mtime 应更新、不触发合并"""
        user = await _create_user(user_repo_provider, "mergeuser4")
        project_id = await _create_project(client, user["token"], event_bus, "ConsecutiveSave")
        await _add_repo(client, user["token"], project_id)
        await client.put(
            f"/projects/{project_id}/repos/mergerepo/files",
            params={"path": "seq.md"},
            json={"content": "# v1\n"},
            headers=_auth(user["token"]),
        )
        # 第一次保存
        mtime1 = _file_mtime(project_id, "mergerepo", "seq.md")
        resp1 = await client.put(
            f"/projects/{project_id}/repos/mergerepo/files",
            params={"path": "seq.md"},
            json={"content": "# v2\n", "expected_mtime": mtime1, "original_content": "# v1\n"},
            headers=_auth(user["token"]),
        )
        assert resp1.status_code == 200
        body1 = resp1.json()
        assert body1["content"] == "# v2\n"
        # 响应应返回 new_mtime（C1 修复核心）
        assert body1["mtime"] is not None, "响应未返回 mtime（C1 bug）"
        mtime2 = body1["mtime"]

        # 第二次保存：用第一次返回的 mtime2 作为 expected_mtime
        resp2 = await client.put(
            f"/projects/{project_id}/repos/mergerepo/files",
            params={"path": "seq.md"},
            json={"content": "# v3\n", "expected_mtime": mtime2, "original_content": "# v2\n"},
            headers=_auth(user["token"]),
        )
        # 第二次应直接保存（200），不触发合并/冲突
        assert resp2.status_code == 200, f"连续保存不应触发合并，但返回 {resp2.status_code}"
        assert resp2.json()["content"] == "# v3\n"
