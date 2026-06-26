"""UserModel 加密底座测试（AR-2.1, AR-2.2）

测试 AES-256-GCM 加密-解密往返 + ORBION_ENCRYPTION_KEY 缺失拒绝启动。
"""

import pytest

from app.biz.user_models.encryption import (
    decrypt_api_key,
    encrypt_api_key,
    validate_encryption_key,
)


def test_ar_2_1_aes_gcm_encrypt_decrypt_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """AR-2.1 AES-GCM 加密-解密往返一致性"""
    monkeypatch.setenv("ORBION_ENCRYPTION_KEY", "YWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWFhYWE=")  # 32 字节 base64

    plaintext = b"sk-test-key-123"
    ciphertext = encrypt_api_key(plaintext)

    # 密文格式：nonce(12B) || ciphertext || tag(16B)
    assert len(ciphertext) >= 12 + 16, "密文应含 nonce(12B) + tag(16B)"
    # 密文不等于明文
    assert ciphertext != plaintext, "密文不应等于明文"

    # 解密结果与原文严格相等
    decrypted = decrypt_api_key(ciphertext)
    assert decrypted == plaintext, "解密结果应与原文严格相等"

    # 同一明文加密两次，密文不同（nonce 随机）
    ciphertext2 = encrypt_api_key(plaintext)
    assert ciphertext != ciphertext2, "同明文两次加密密文应不同（nonce 随机）"

    # 第二次解密也对
    assert decrypt_api_key(ciphertext2) == plaintext


def test_ar_2_2_encryption_key_missing_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    """AR-2.2 ORBION_ENCRYPTION_KEY 缺失时 validate_encryption_key 拒绝"""
    monkeypatch.delenv("ORBION_ENCRYPTION_KEY", raising=False)

    with pytest.raises((RuntimeError, AssertionError)):
        validate_encryption_key()


async def test_ar_2_2_lifespan_rejects_when_key_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """AR-2.2 ORBION_ENCRYPTION_KEY 缺失时 lifespan 启动拒绝（服务未绑定端口）

    验证 validate_encryption_key 在 lifespan 第一行调用，密钥缺失时整个 app 启动失败。
    """
    monkeypatch.delenv("ORBION_ENCRYPTION_KEY", raising=False)

    from app.main import app, lifespan

    # lifespan 是 async context manager，密钥缺失时 __aenter__ 在第一行抛 RuntimeError
    with pytest.raises((RuntimeError, AssertionError)):
        async with lifespan(app):
            pass
