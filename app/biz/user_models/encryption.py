"""UserModel 加密底座（AR-2.1, AR-2.2）

AES-256-GCM 加密 api_key，密钥来源 ORBION_ENCRYPTION_KEY 环境变量。
密文格式：nonce(12B) || ciphertext || tag(16B)（AES-GCM 标准布局）。
"""

import base64
import os
import re

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# api_key 防泄露正则——redact_secrets 过滤日志/异常堆栈中的敏感信息
# 收紧：sk- 开头需 ≥20 字符（OpenAI key 通常 ≥40），避免误伤 sk-learning 等正常词
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9_.~+/=-]{20,}"),
    re.compile(r"api_key\s*=\s*[A-Za-z0-9_-]{20,}"),
]


def _get_encryption_key() -> bytes:
    """从 ORBION_ENCRYPTION_KEY 读取 32 字节密钥（base64 编码）"""
    raw = os.environ.get("ORBION_ENCRYPTION_KEY")
    if not raw:
        raise RuntimeError("ORBION_ENCRYPTION_KEY 未配置：无法加解密 api_key，请在环境变量中设置 32 字节 base64 密钥")
    try:
        key = base64.b64decode(raw)
    except Exception as e:
        raise RuntimeError(f"ORBION_ENCRYPTION_KEY 必须为合法 base64：{e}") from e
    if len(key) != 32:
        raise RuntimeError(f"ORBION_ENCRYPTION_KEY 必须为 32 字节 base64 编码，实际 {len(key)} 字节")
    return key


def validate_encryption_key() -> None:
    """启动自检：密钥存在且长度正确，否则拒绝启动"""
    _get_encryption_key()


def encrypt_api_key(plaintext: bytes) -> bytes:
    """AES-256-GCM 加密，返回 nonce(12B) || ciphertext || tag(16B)

    AESGCM.encrypt 默认把 tag 附在 ciphertext 末尾，无需手动拼接。
    """
    key = _get_encryption_key()
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    # AESGCM.encrypt 返回 ciphertext + tag（tag 在末尾，16 字节）
    ciphertext_and_tag = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    return nonce + ciphertext_and_tag


def decrypt_api_key(ciphertext: bytes) -> bytes:
    """AES-256-GCM 解密，输入格式 nonce(12B) || ciphertext || tag(16B)"""
    key = _get_encryption_key()
    nonce = ciphertext[:12]
    ciphertext_and_tag = ciphertext[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext_and_tag, associated_data=None)


def redact_secrets(text: str) -> str:
    """过滤日志/异常堆栈中的 api_key、Authorization、api_key=xxx 等敏感模式"""
    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("***", redacted)
    return redacted
