"""E2E测试服务器启动脚本 — 注入TestModelAdapter到生产lifespan，不修改生产代码"""

import asyncio
import json
import os
import uuid

# E2E独立于pytest进程运行，不依赖tests/conftest，自行定义测试密钥。
# Why: pytest的JWT_SECRET_TEST与e2e的JWT_SECRET_E2E是不同值——
# 避免跨进程耦合；e2e有自己的用户注册流程，无需共享pytest的token。
# 两者均>=32 bytes以满足PyJWT HS256最低密钥长度要求。
JWT_SECRET_E2E = "orbion-e2e-secret-key-at-least-32-by"

os.environ.setdefault("ORBION_JWT_SECRET", JWT_SECRET_E2E)
os.environ.setdefault("ORBION_POSTGRES__DB", "orbion_test")

import asyncpg

from app.biz.agents.adapters.base import ModelOutput, PromptInput


class TestModelAdapter:
    """E2E测试适配器：返回确定性结构化JSON响应

    从PromptInput.metadata提取真实ID（thread_id/plan_id等），
    无对应ID时生成随机UUID作为占位。
    """

    def _detect_agent_type(self, task: str) -> str:
        if "总结" in task or "摘要" in task:
            return "summary"
        if "分解" in task:
            return "decompose"
        if "执行" in task or "代码" in task or "重新生成" in task:
            return "execute"
        return "unknown"

    async def complete(self, prompt: PromptInput) -> ModelOutput:
        agent_type = self._detect_agent_type(prompt.task)

        if agent_type == "summary":
            return self._summary_response(prompt.metadata)
        if agent_type == "decompose":
            return self._decompose_response(prompt.metadata)
        if agent_type == "execute":
            return self._execute_response(prompt.metadata)

        return ModelOutput(content=prompt.task)

    def _summary_response(self, metadata: dict) -> ModelOutput:
        thread_id = metadata.get("thread_id", str(uuid.uuid4()))
        content = json.dumps({
            "summary_id": str(uuid.uuid4()),
            "thread_id": thread_id,
            "consensus_points": ["共识点1：项目目标明确", "共识点2：技术栈选择合理"],
            "divergence_points": ["分歧点1：部署策略"],
            "action_items": ["行动项1：实现核心API", "行动项2：配置CI流水线"],
            "knowledge_references": [],
        })
        return ModelOutput(content=content)

    def _decompose_response(self, metadata: dict) -> ModelOutput:
        plan_id = str(uuid.uuid4())
        task1_id = str(uuid.uuid4())
        task2_id = str(uuid.uuid4())
        thread_id = metadata.get("thread_id", str(uuid.uuid4()))
        content = json.dumps({
            "plan_id": plan_id,
            "thread_id": thread_id,
            "tasks": [
                {
                    "task_id": task1_id,
                    "type": "code",
                    "description": "实现API端点",
                    "dependencies": [],
                    "priority": "high",
                },
                {
                    "task_id": task2_id,
                    "type": "document",
                    "description": "编写部署文档",
                    "dependencies": [task1_id],
                    "priority": "medium",
                },
            ],
        })
        return ModelOutput(content=content)

    def _execute_response(self, metadata: dict) -> ModelOutput:
        diff_content = (
            "--- a/main.py\n+++ b/main.py\n"
            "@@ -1,3 +1,4 @@\n-import old\n"
            "+def hello():\n+    return 'world'"
        )
        plan_id = metadata.get("plan_id", str(uuid.uuid4()))
        task_id = metadata.get("task_id", str(uuid.uuid4()))
        content = json.dumps({
            "output_id": str(uuid.uuid4()),
            "task_id": task_id,
            "plan_id": plan_id,
            "output_type": "code",
            "content": "def hello():\n    return 'world'",
            "diff": diff_content,
            "file_paths": ["main.py"],
        })
        return ModelOutput(content=content)


# 注入TestModelAdapter：替换app.main中的StubModelAdapter
import app.main

app.main.StubModelAdapter = TestModelAdapter

# 清空所有业务表，确保E2E测试数据隔离
async def _clean_db() -> None:
    """动态发现所有业务表并TRUNCATE CASCADE，确保每次E2E运行从空库开始"""
    from app.config import get_settings

    settings = get_settings()
    conn = await asyncpg.connect(settings.postgres.url)
    rows = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    tables = ", ".join(r["tablename"] for r in rows)
    if tables:
        await conn.execute(f"TRUNCATE {tables} CASCADE")
    await conn.close()

asyncio.run(_clean_db())

# E2E 测试专用端点：seed worktree 记录（worktree 无创建 API，系统在 dispatch 时自动创建）
from fastapi import APIRouter as _AR
_test_router = _AR()


@_test_router.post("/test/seed-worktree")
async def _seed_worktree(body: dict) -> dict:
    """E2E 测试专用：直接插入 worktree 记录到 DB（复用 app.state 的连接池）"""
    from fastapi import Request as _Req
    # 用 app.state.worktree_service.pool 复用连接池，避免每次新建连接导致 ECONNRESET
    pool = app.main.app.state.worktree_service.pool
    async with pool.acquire() as conn:
        wt_id = uuid.uuid4()
        await conn.execute(
            "INSERT INTO worktrees (id, project_id, repo_name, worktree_type, branch_name, path, status, "
            "created_by, task_id) VALUES ($1, $2, $3, $4, $5, $6, 'active', $7, $8)",
            wt_id,
            uuid.UUID(body["project_id"]),
            body.get("repo_name", "orbion"),
            body.get("worktree_type", "task"),
            body.get("branch_name", f"task/{uuid.uuid4()}"),
            body.get("path", f"/tmp/wt_{wt_id}"),
            uuid.UUID(body["created_by"]),
            uuid.UUID(body["task_id"]) if body.get("task_id") else None,
        )
    return {"id": str(wt_id)}


app.main.app.include_router(_test_router, tags=["test"])

# 启动服务器
import uvicorn

uvicorn.run(app.main.app, host="0.0.0.0", port=8002)