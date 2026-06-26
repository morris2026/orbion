"""AgentModelMappingService — 四级解析（AR-2.4, AR-2.5, AR-2.6）

解析顺序（从高到低）：
1. 项目级覆盖（agent_model_override.json）
2. 用户级通用（agent_models.enc）
3. 智能默认（用户只有 1 个 UserModel 时自动套用）
4. 都没有 → 抛 ModelNotConfiguredError

同时提供 find_referrers 供 UserModelService.delete_model 校验引用。
"""

import json
from pathlib import Path

from app.biz.agent_models.store import AgentModelStore
from app.biz.user_models.service import UserModelService


class ModelNotConfiguredError(Exception):
    """未配置 UserModel 或解析失败，引导到 /users/me/agent-models 配置"""

    def __init__(self, agent_type: str) -> None:
        self.agent_type = agent_type
        super().__init__(f"No model configured for agent '{agent_type}'.")


class AgentModelMappingService:
    def __init__(
        self,
        store: AgentModelStore,
        user_model_service: UserModelService,
        projects_dir: Path,
    ) -> None:
        self._store = store
        self._user_model_service = user_model_service
        self._projects_dir = projects_dir

    async def resolve_model_id(
        self,
        user_id: str,
        agent_type: str,
        project_id: str | None = None,
    ) -> str:
        """四级解析：项目级覆盖 > 用户级 > 智能默认 > 引导

        返回 model_id（UserModel.model_id）。未配置抛 ModelNotConfiguredError。
        """
        # 1. 项目级覆盖
        if project_id is not None:
            override = self._read_project_override(project_id)
            if agent_type in override:
                return override[agent_type]

        # 2. 用户级通用
        user_mapping = self._store.read(user_id)
        if agent_type in user_mapping:
            return user_mapping[agent_type]

        # 3. 智能默认：用户只有 1 个 UserModel 时自动套用
        model_ids = await self._user_model_service.list_model_ids(user_id)
        if len(model_ids) == 1:
            return model_ids[0]

        # 4. 都没有 → 引导
        raise ModelNotConfiguredError(agent_type)

    async def get_user_mapping(self, user_id: str) -> dict[str, str]:
        """读用户级 agent_models.enc"""
        return self._store.read(user_id)

    async def set_user_mapping(self, user_id: str, mapping: dict[str, str]) -> dict[str, str]:
        """写用户级 agent_models.enc（整体替换）"""
        self._store.write(user_id, mapping)
        return self._store.read(user_id)

    def get_project_override(self, project_id: str) -> dict[str, str]:
        """读项目级覆盖"""
        return self._read_project_override(project_id)

    def set_project_override(self, project_id: str, mapping: dict[str, str]) -> dict[str, str]:
        """写项目级覆盖（整体替换）"""
        path = self._override_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2))
        return self._read_project_override(project_id)

    def delete_project_override(self, project_id: str, agent_type: str) -> dict[str, str]:
        """删除单个 agent 的项目级覆盖（回退到用户级）"""
        mapping = self._read_project_override(project_id)
        mapping.pop(agent_type, None)
        path = self._override_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2))
        return self._read_project_override(project_id)

    async def find_referrers(self, user_id: str, model_id: str) -> list[str]:
        """查找引用了该 model_id 的 agent_type（用户级 + 项目级）

        当前仅查用户级 agent_models.enc；项目级 agent_model_override.json 的引用
        在步骤 9（变更传播）补全——届时需要遍历用户的所有项目 + project_member 关系。
        """
        referrers: list[str] = []

        # 用户级
        user_mapping = self._store.read(user_id)
        for agent_type, mid in user_mapping.items():
            if mid == model_id:
                referrers.append(agent_type)

        # 项目级（遍历用户的所有项目）— MVP 简化：只查用户级
        # 项目级覆盖查询需要 project_member 关系，步骤 9 变更传播时再细化
        return referrers

    def _override_path(self, project_id: str) -> Path:
        return self._projects_dir / project_id / "config" / "agent_model_override.json"

    def _read_project_override(self, project_id: str) -> dict[str, str]:
        path = self._override_path(project_id)
        if not path.exists():
            return {}
        data: dict[str, str] = json.loads(path.read_text())
        return data
