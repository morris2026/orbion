"""UserModelService — UserModel CRUD + api_key_hash 变更检测

api_key 用 AES-256-GCM 加密存 user_models.api_key_enc；
api_key_hash 存 SHA-256 hex，用于编辑表单"是否修改了 key"判断，
避免每次保存都重新加密，同时为 AgentModelMapping 引用校验提供依据。
api_key_masked 在 create/update 时一次性计算写入，list/get 时直接读列不解密，
避免明文 api_key 在内存存活响应周期（安全考量，§4.3）。
"""

import hashlib
import json
import uuid
from typing import Any

import asyncpg

from app.biz.user_models.encryption import decrypt_api_key, encrypt_api_key
from app.biz.user_models.models import (
    UserModelCreate,
    UserModelResponse,
    UserModelUpdate,
    mask_api_key,
)


class UserModelInUseError(Exception):
    """UserModel 被 AgentModelMapping 引用时禁止删除"""

    def __init__(self, model_id: str, referrers: list[str]) -> None:
        self.model_id = model_id
        self.referrers = referrers
        super().__init__(f"UserModel '{model_id}' 被 {referrers} 引用，禁止删除")


class UserModelNotFoundError(Exception):
    pass


class UserModelService:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def list_models(self, user_id: str) -> list[UserModelResponse]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, user_id, model_id, provider, model_name, base_url, "
                "extra_config, api_key_masked FROM user_models "
                "WHERE user_id=$1 ORDER BY model_id",
                uuid.UUID(user_id),
            )
        return [self._to_response(row) for row in rows]

    async def get_model(self, user_id: str, model_id: str) -> UserModelResponse:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, user_id, model_id, provider, model_name, base_url, "
                "extra_config, api_key_masked FROM user_models "
                "WHERE user_id=$1 AND model_id=$2",
                uuid.UUID(user_id),
                model_id,
            )
        if row is None:
            raise UserModelNotFoundError(model_id)
        return self._to_response(row)

    async def create_model(self, user_id: str, request: UserModelCreate) -> UserModelResponse:
        model_uuid = uuid.uuid4()
        api_key_enc = encrypt_api_key(request.api_key.encode())
        api_key_hash = hashlib.sha256(request.api_key.encode()).hexdigest()
        api_key_masked = mask_api_key(request.api_key)
        async with self._pool.acquire() as conn:
            try:
                await conn.execute(
                    "INSERT INTO user_models (id, user_id, model_id, provider, model_name, base_url, "
                    "api_key_enc, api_key_hash, api_key_masked, extra_config) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)",
                    model_uuid,
                    uuid.UUID(user_id),
                    request.model_id,
                    request.provider,
                    request.model_name,
                    request.base_url,
                    api_key_enc,
                    api_key_hash,
                    api_key_masked,
                    json.dumps(request.extra_config),
                )
            except asyncpg.UniqueViolationError as e:
                raise ValueError(f"UserModel '{request.model_id}' 已存在") from e
        return await self.get_model(user_id, request.model_id)

    async def update_model(self, user_id: str, model_id: str, request: UserModelUpdate) -> UserModelResponse:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT api_key_enc, api_key_hash FROM user_models WHERE user_id=$1 AND model_id=$2",
                uuid.UUID(user_id),
                model_id,
            )
            if row is None:
                raise UserModelNotFoundError(model_id)

            # api_key_hash 变更检测：未传 api_key 时保持原 enc + hash + masked
            api_key_masked: str | None = None
            if request.api_key is not None:
                api_key_enc = encrypt_api_key(request.api_key.encode())
                api_key_hash = hashlib.sha256(request.api_key.encode()).hexdigest()
                api_key_masked = mask_api_key(request.api_key)
            else:
                api_key_enc = bytes(row["api_key_enc"])
                api_key_hash = row["api_key_hash"]

            updates: list[str] = []
            params: list[Any] = [uuid.UUID(user_id), model_id]
            param_idx = 3
            for field in ["provider", "model_name", "base_url"]:
                value = getattr(request, field)
                if value is not None:
                    updates.append(f"{field} = ${param_idx}")
                    params.append(value)
                    param_idx += 1
            if request.extra_config is not None:
                updates.append(f"extra_config = ${param_idx}::jsonb")
                params.append(json.dumps(request.extra_config))
                param_idx += 1
            updates.append(f"api_key_enc = ${param_idx}")
            params.append(api_key_enc)
            param_idx += 1
            updates.append(f"api_key_hash = ${param_idx}")
            params.append(api_key_hash)
            param_idx += 1
            if api_key_masked is not None:
                updates.append(f"api_key_masked = ${param_idx}")
                params.append(api_key_masked)
                param_idx += 1
            updates.append("updated_at = NOW()")

            await conn.execute(
                f"UPDATE user_models SET {', '.join(updates)} WHERE user_id=$1 AND model_id=$2",
                *params,
            )
        return await self.get_model(user_id, model_id)

    async def delete_model(self, user_id: str, model_id: str, referrers: list[str]) -> None:
        """删除前校验引用，被 AgentModelMapping 引用时抛 UserModelInUseError"""
        if referrers:
            raise UserModelInUseError(model_id, referrers)
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM user_models WHERE user_id=$1 AND model_id=$2",
                uuid.UUID(user_id),
                model_id,
            )
            if result == "DELETE 0":
                raise UserModelNotFoundError(model_id)

    async def get_model_with_key(self, user_id: str, model_id: str) -> tuple[str, str, str]:
        """内部用：返回 (model_name, base_url, 明文 api_key)

        仅在调用模型前解密，明文不写日志、不进内存缓存超过单次调用生命周期（§4.3）。
        """
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT model_name, base_url, api_key_enc FROM user_models WHERE user_id=$1 AND model_id=$2",
                uuid.UUID(user_id),
                model_id,
            )
        if row is None:
            raise UserModelNotFoundError(model_id)
        api_key = decrypt_api_key(bytes(row["api_key_enc"])).decode()
        return row["model_name"], row["base_url"], api_key

    async def list_model_ids(self, user_id: str) -> list[str]:
        """返回用户所有 model_id，供智能默认使用"""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT model_id FROM user_models WHERE user_id=$1", uuid.UUID(user_id))
        return [r["model_id"] for r in rows]

    def _to_response(self, row: asyncpg.Record) -> UserModelResponse:
        """从 DB 行构造响应，不解密 api_key（masked 已持久化）"""
        extra = row["extra_config"]
        if isinstance(extra, str):
            extra = json.loads(extra)
        return UserModelResponse(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            model_id=row["model_id"],
            provider=row["provider"],
            model_name=row["model_name"],
            base_url=row["base_url"],
            api_key_masked=row["api_key_masked"],
            extra_config=extra,
        )
