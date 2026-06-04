"""E2E测试服务器启动脚本 — 注入TestModelAdapter到生产lifespan，不修改生产代码"""

import json
import uuid

from app.biz.agents.adapters.base import ModelOutput, PromptInput


class TestModelAdapter:
    """E2E测试适配器：返回确定性结构化JSON响应

    从PromptInput.metadata提取真实ID（thread_id/plan_id等），
    无对应ID时生成随机UUID作为占位。
    """

    def _detect_agent_type(self, task: str) -> str:
        if "总结" in task or "摘要" in task:
            return "summary"
        if "分解" in task or "任务" in task:
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

# 启动服务器
import uvicorn

uvicorn.run(app.main.app, host="0.0.0.0", port=8000)