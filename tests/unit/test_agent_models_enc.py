"""agent_models.enc 加密文件读写测试（AR-2.7）

测试 AgentModelMapping 加密存储：文件内容是加密字节（非明文），
读写往返一致，HKDF info 与 credentials 隔离（用错 key 解密失败）。
"""

import pytest

from app.biz.agent_models.store import AgentModelStore
from app.biz.credentials.service import CredentialService


def test_ar_2_7_agent_models_enc_roundtrip(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pytest.TempPathFactory,
) -> None:
    """AR-2.7 agent_models.enc 加密文件读写"""
    # 32 字节 base64 密钥
    monkeypatch.setenv("ORBION_ENCRYPTION_KEY", "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE=")

    user_id = "user-001"
    store = AgentModelStore(root_dir=str(tmp_path))

    # 写入映射
    mapping = {
        "analyst": "我的 GLM-4",
        "architect": "Claude Sonnet",
        "implementer": "GLM-4-Plus",
    }
    store.write(user_id, mapping)

    # 文件内容是加密字节（非明文 JSON）
    enc_path = store._enc_path(user_id)  # noqa: SLF001 — 测试需要验证文件内容
    raw = enc_path.read_bytes()
    assert b"analyst" not in raw, "加密文件不应含明文 agent_type"
    assert b"GLM-4" not in raw, "加密文件不应含明文 model_id"

    # 读出与写入一致
    read_mapping = store.read(user_id)
    assert read_mapping == mapping, "读出的 dict 应与写入一致"

    # 修改后再读
    mapping["critic"] = "Claude Sonnet"
    mapping.pop("analyst")
    store.write(user_id, mapping)
    assert store.read(user_id) == mapping, "修改后读出应与最新写入一致"


def test_ar_2_7_agent_models_enc_isolated_from_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: pytest.TempPathFactory,
) -> None:
    """AR-2.7 agent_models.enc 的 HKDF info 与 credentials 隔离（用错 key 解密失败）"""
    monkeypatch.setenv("ORBION_ENCRYPTION_KEY", "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE=")

    user_id = "user-002"
    agent_store = AgentModelStore(root_dir=str(tmp_path))
    agent_store.write(user_id, {"analyst": "GLM-4"})

    # 用 CredentialService 的密钥派生尝试解密 agent_models.enc（应失败）
    from app.config import get_settings

    settings = get_settings()
    settings.root_dir = str(tmp_path)
    cred_service = CredentialService(settings)

    # CredentialService 内部用 jwt_secret + salt=orbion-credential-encryption-key 派生
    # agent_models.enc 用 ORBION_ENCRYPTION_KEY + 不同 HKDF info 派生
    # 两者密钥不同，解密应失败
    enc_path = agent_store._enc_path(user_id)  # noqa: SLF001
    raw = enc_path.read_bytes()
    # 用 CredentialService 的 key 尝试解密——Fernet 会抛 InvalidToken
    from cryptography.fernet import Fernet, InvalidToken

    key = cred_service._derive_key(user_id)  # noqa: SLF001
    fernet = Fernet(key)
    with pytest.raises(InvalidToken):
        fernet.decrypt(raw)
