import base64
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.biz.credentials.models import (
    CreateCredentialRequest,
    Credential,
    CredentialResponse,
    CredentialType,
)
from app.config import Settings

_SALT = b"orbion-credential-encryption-key"


class CredentialService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._locks: dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def _get_lock(self, user_id: str) -> threading.Lock:
        with self._global_lock:
            if user_id not in self._locks:
                self._locks[user_id] = threading.Lock()
            return self._locks[user_id]

    def _derive_key(self, user_id: str) -> bytes:
        """HKDF 派生 per-user Fernet 密钥"""
        hkdf = HKDF(
            algorithm=SHA256(),
            length=32,
            salt=_SALT,
            info=user_id.encode(),
        )
        key = hkdf.derive(self._settings.jwt_secret.encode())
        return base64.urlsafe_b64encode(key)

    def _enc_path(self, user_id: str) -> Path:
        return Path(self._settings.root_dir) / "users" / user_id / "credentials.enc"

    def _read_credentials(self, user_id: str) -> list[Credential]:
        path = self._enc_path(user_id)
        if not path.exists():
            return []
        key = self._derive_key(user_id)
        fernet = Fernet(key)
        data = fernet.decrypt(path.read_bytes())
        items = json.loads(data)
        return [Credential(**item) for item in items]

    def _write_credentials(self, user_id: str, creds: list[Credential]) -> None:
        path = self._enc_path(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o700)
        key = self._derive_key(user_id)
        fernet = Fernet(key)
        data = json.dumps([c.model_dump(mode="json") for c in creds])
        path.write_bytes(fernet.encrypt(data.encode()))
        path.chmod(0o600)

    def list_credentials(self, user_id: str) -> list[CredentialResponse]:
        with self._get_lock(user_id):
            creds = self._read_credentials(user_id)
        return [CredentialResponse(id=c.id, type=c.type, name=c.name, created_at=c.created_at) for c in creds]

    def create_credential(self, user_id: str, request: CreateCredentialRequest) -> CredentialResponse:
        with self._get_lock(user_id):
            creds = self._read_credentials(user_id)
            now = datetime.now()
            new_credential = Credential(
                id=str(uuid.uuid4()),
                type=request.type,
                name=request.name,
                token=request.token,
                created_at=now,
            )
            creds.append(new_credential)
            self._write_credentials(user_id, creds)
        return CredentialResponse(
            id=new_credential.id,
            type=new_credential.type,
            name=new_credential.name,
            created_at=now,
        )

    def delete_credential(self, user_id: str, credential_id: str) -> None:
        with self._get_lock(user_id):
            creds = self._read_credentials(user_id)
            creds = [c for c in creds if c.id != credential_id]
            self._write_credentials(user_id, creds)

    def match_credential(self, user_id: str, url: str) -> Credential | None:
        """根据 URL 自动匹配凭据"""
        creds = self._read_credentials(user_id)
        if not creds:
            return None

        parsed = urlparse(url)
        host = parsed.hostname or ""

        # 匹配类型
        matched: list[Credential] = []
        if "github.com" in host:
            matched = [c for c in creds if c.type == CredentialType.GITHUB]

        if not matched:
            return None

        # 同类型多条取最新
        matched.sort(key=lambda c: c.created_at, reverse=True)
        return matched[0]

    def get_token(self, user_id: str, credential_id: str) -> str | None:
        """按 ID 获取凭据的 token（仅供 credential helper 使用）"""
        creds = self._read_credentials(user_id)
        for c in creds:
            if c.id == credential_id:
                return c.token
        return None
