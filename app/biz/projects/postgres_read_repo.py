"""PostgresProjectRead — PostgreSQL投影表读端实现"""

import uuid
from typing import Any

import asyncpg

from app.biz.projects.read_repo import ProjectReadProtocol
from app.config import get_settings
from app.hub.permissions.roles import derive_role_name

_MSG_NOT_CONNECTED = "PostgresProjectRead未连接，请先调用connect()"


class PostgresProjectRead(ProjectReadProtocol):
    """PostgreSQL投影表读端实现"""

    def __init__(self) -> None:
        settings = get_settings()
        self._url = settings.postgres.url
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        self._pool = await asyncpg.create_pool(self._url, min_size=2, max_size=10)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    def _require_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError(_MSG_NOT_CONNECTED)
        return self._pool

    async def list_projects(self, user_id: str) -> list[dict[str, Any]]:
        pool = self._require_pool()
        rows = await pool.fetch(
            """SELECT p.id, p.name, p.description, p.created_at, pm.roles
               FROM projects p
               JOIN project_members pm ON pm.project_id = p.id
               WHERE pm.participant_id = $1 AND pm.type = 'human'
               ORDER BY p.created_at DESC, p.id""",
            user_id,
        )
        results = [_row_to_dict(r) for r in rows]
        for r in results:
            r["role"] = derive_role_name(int(r["roles"]))
        return results

    async def get_project(self, project_id: str, user_id: str) -> dict[str, Any] | None:
        pool = self._require_pool()
        row = await pool.fetchrow(
            """SELECT p.id, p.name, p.description, p.tenant_id, p.created_at, pm.roles
               FROM projects p
               JOIN project_members pm ON pm.project_id = p.id
               WHERE p.id = $1 AND pm.participant_id = $2 AND pm.type = 'human'""",
            uuid.UUID(project_id),
            user_id,
        )
        if row is None:
            return None
        result = _row_to_dict(row)
        result["role"] = derive_role_name(int(result["roles"]))
        return result

    async def get_member_roles(self, project_id: str, user_id: str) -> int | None:
        pool = self._require_pool()
        row = await pool.fetchrow(
            "SELECT roles FROM project_members WHERE participant_id = $1 AND project_id = $2 AND type = 'human'",
            user_id,
            uuid.UUID(project_id),
        )
        return int(row["roles"]) if row else None

    async def check_member_exists(self, project_id: str, user_id: str, member_type: str | None = None) -> bool:
        pool = self._require_pool()
        if member_type is not None:
            row = await pool.fetchrow(
                "SELECT 1 FROM project_members WHERE participant_id = $1 AND project_id = $2 AND type = $3",
                user_id,
                uuid.UUID(project_id),
                member_type,
            )
        else:
            row = await pool.fetchrow(
                "SELECT 1 FROM project_members WHERE participant_id = $1 AND project_id = $2",
                user_id,
                uuid.UUID(project_id),
            )
        return row is not None

    async def list_agents(self, project_id: str) -> list[dict[str, Any]]:
        """列出项目的所有Agent成员"""
        pool = self._require_pool()
        rows = await pool.fetch(
            "SELECT participant_id, project_id, type, display_name, roles, "
            "agent_type, model_id, status, created_at "
            "FROM project_members WHERE project_id = $1 AND type = 'agent' "
            "ORDER BY created_at ASC",
            uuid.UUID(project_id),
        )
        return [_row_to_dict(r) for r in rows]

    async def get_agent(self, project_id: str, agent_id: str) -> dict[str, Any] | None:
        """获取项目单个Agent成员"""
        pool = self._require_pool()
        row = await pool.fetchrow(
            "SELECT participant_id, project_id, type, display_name, roles, "
            "agent_type, model_id, status, created_at "
            "FROM project_members WHERE participant_id = $1 AND project_id = $2 AND type = 'agent'",
            agent_id,
            uuid.UUID(project_id),
        )
        return _row_to_dict(row) if row else None

    async def list_members(self, project_id: str) -> list[dict[str, Any]]:
        """列出项目所有成员（人类+Agent）"""
        pool = self._require_pool()
        rows = await pool.fetch(
            "SELECT participant_id, project_id, type, display_name, roles, "
            "agent_type, model_id, status, created_at "
            "FROM project_members WHERE project_id = $1 ORDER BY created_at ASC",
            uuid.UUID(project_id),
        )
        results = [_row_to_dict(r) for r in rows]
        for r in results:
            r["role"] = derive_role_name(int(r["roles"]))
        return results


def _row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    """asyncpg Record → dict，UUID列自动转为str"""
    result: dict[str, Any] = dict(row)
    for key, value in result.items():
        if isinstance(value, uuid.UUID):
            result[key] = str(value)
    return result
