"""AgentModelMapping 加密文件存储（AR-2.7）

agent_models.enc 存用户级 Agent→Model 映射，复用 ORBION_ENCRYPTION_KEY
但用不同的 HKDF info 与 credentials.enc 隔离，确保两份加密文件互不能用错 key 解密。

文件路径：{root_dir}/users/{user_id}/agent_models.enc
加密方案：AES-256-GCM（与 user_models.api_key_enc 一致），密钥由 HKDF 派生。
"""

import base64
import json
import os
import threading
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_HKDF_INFO = b"orbion-agent-models-key"  # 与 credentials 隔离的关键
_HKDF_SALT = b"orbion-agent-models-encryption-salt"


def _derive_key() -> bytes:
    """从 ORBION_ENCRYPTION_KEY + HKDF 派生 32 字节 AES-GCM 密钥"""
    raw = os.environ.get("ORBION_ENCRYPTION_KEY")
    if not raw:
        raise RuntimeError("ORBION_ENCRYPTION_KEY 未配置")
    base_key = base64.b64decode(raw)
    hkdf = HKDF(
        algorithm=SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=_HKDF_INFO,
    )
    return hkdf.derive(base_key)


class AgentModelStore:
    """agent_models.enc 加密文件读写，per-user 锁保证并发安全

    Why threading.Lock 而非 asyncio.Lock: 文件 IO 是同步的（path.read_bytes/write_bytes），
    且加密文件极小（< 1KB），持锁时间 <1ms，阻塞 event loop 可忽略。
    与 CredentialService 保持一致的锁策略。dispatch 热路径若未来高频调用，
    再改为 asyncio.Lock + asyncio.to_thread 包裹文件 IO。
    """

    def __init__(self, root_dir: str) -> None:
        self._root_dir = root_dir
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _get_lock(self, user_id: str) -> threading.Lock:
        with self._global_lock:
            if user_id not in self._locks:
                self._locks[user_id] = threading.Lock()
            return self._locks[user_id]

    def _enc_path(self, user_id: str) -> Path:
        return Path(self._root_dir) / "users" / user_id / "agent_models.enc"

    def read(self, user_id: str) -> dict[str, str]:
        """读 agent_models.enc，文件不存在返回空 dict"""
        with self._get_lock(user_id):
            path = self._enc_path(user_id)
            if not path.exists():
                return {}
            key = _derive_key()
            raw = path.read_bytes()
            nonce = raw[:12]
            ciphertext_and_tag = raw[12:]
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(nonce, ciphertext_and_tag, associated_data=None)
            data: dict[str, str] = json.loads(plaintext.decode())
            return data

    def write(self, user_id: str, mapping: dict[str, str]) -> None:
        """写 agent_models.enc，原子写入（先写 tmp 再 rename）"""
        with self._get_lock(user_id):
            path = self._enc_path(user_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.parent.chmod(0o700)
            key = _derive_key()
            nonce = os.urandom(12)
            aesgcm = AESGCM(key)
            data = json.dumps(mapping).encode()
            ciphertext_and_tag = aesgcm.encrypt(nonce, data, associated_data=None)
            tmp_path = path.with_suffix(".enc.tmp")
            tmp_path.write_bytes(nonce + ciphertext_and_tag)
            tmp_path.replace(path)
            path.chmod(0o600)
