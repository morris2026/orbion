import json
from pathlib import Path

import pytest

from app.biz.credentials.models import CreateCredentialRequest, CredentialType
from app.biz.credentials.service import CredentialService
from app.config import Settings


@pytest.fixture
def credential_service(tmp_path: Path) -> CredentialService:
    settings = Settings(jwt_secret="test-secret-for-credential-service", root_dir=str(tmp_path))
    return CredentialService(settings)


class TestCreateCredential:
    """MVP-FL-8.1: 创建凭据 — GitHub 类型"""

    def test_create_github_credential(self, credential_service: CredentialService, tmp_path: Path) -> None:
        req = CreateCredentialRequest(type=CredentialType.GITHUB, name="我的GitHub", token="ghp_xxx")
        result = credential_service.create_credential("user-1", req)

        assert result.type == CredentialType.GITHUB
        assert result.name == "我的GitHub"
        assert result.id  # 自动生成 UUID

        # 加密文件存在
        enc_path = tmp_path / "users" / "user-1" / "credentials.enc"
        assert enc_path.exists()

        # 文件内容不是明文 JSON
        raw = enc_path.read_bytes()
        with pytest.raises(json.JSONDecodeError):
            json.loads(raw)

        # list_credentials 返回含 1 条凭据，不含 token
        creds = credential_service.list_credentials("user-1")
        assert len(creds) == 1
        assert creds[0].type == CredentialType.GITHUB
        assert creds[0].name == "我的GitHub"
        assert "token" not in type(creds[0]).model_fields


class TestListCredentials:
    """MVP-FL-8.2: 列出凭据不含 token"""

    def test_list_excludes_token(self, credential_service: CredentialService) -> None:
        req1 = CreateCredentialRequest(type=CredentialType.GITHUB, name="GitHub1", token="ghp_aaa")
        req2 = CreateCredentialRequest(type=CredentialType.GITHUB, name="GitHub2", token="ghp_bbb")
        credential_service.create_credential("user-1", req1)
        credential_service.create_credential("user-1", req2)

        creds = credential_service.list_credentials("user-1")
        assert len(creds) == 2
        for c in creds:
            assert c.id
            assert c.type
            assert c.name
            assert c.created_at
            assert "token" not in type(c).model_fields

    def test_list_empty_when_no_file(self, credential_service: CredentialService) -> None:
        creds = credential_service.list_credentials("user-no-exist")
        assert creds == []


class TestDeleteCredential:
    """MVP-FL-8.3: 删除凭据"""

    def test_delete_credential(self, credential_service: CredentialService) -> None:
        req1 = CreateCredentialRequest(type=CredentialType.GITHUB, name="Keep", token="ghp_aaa")
        req2 = CreateCredentialRequest(type=CredentialType.GITHUB, name="Delete", token="ghp_bbb")
        credential_service.create_credential("user-1", req1)
        c2 = credential_service.create_credential("user-1", req2)

        credential_service.delete_credential("user-1", c2.id)

        creds = credential_service.list_credentials("user-1")
        assert len(creds) == 1
        assert creds[0].name == "Keep"

    """MVP-FL-8.4: 删除不存在的凭据"""

    def test_delete_nonexistent_credential(self, credential_service: CredentialService) -> None:
        # 不抛异常
        credential_service.delete_credential("user-1", "nonexistent-id")


class TestPerUserKeyIsolation:
    """MVP-FL-8.5: per-user key 隔离"""

    def test_different_users_cannot_decrypt_each_other(
        self, credential_service: CredentialService, tmp_path: Path
    ) -> None:
        req = CreateCredentialRequest(type=CredentialType.GITHUB, name="Same", token="ghp_same")
        credential_service.create_credential("user-a", req)
        credential_service.create_credential("user-b", req)

        # user-a 的文件用 user-b 的密钥解密应该失败
        from cryptography.fernet import InvalidToken

        enc_path_a = tmp_path / "users" / "user-a" / "credentials.enc"
        raw = enc_path_a.read_bytes()

        key_b = credential_service._derive_key("user-b")
        from cryptography.fernet import Fernet

        fernet_b = Fernet(key_b)

        with pytest.raises(InvalidToken):
            fernet_b.decrypt(raw)


class TestMatchCredential:
    """MVP-FL-8.6: match_credential — GitHub URL 自动匹配"""

    def test_match_github_url(self, credential_service: CredentialService) -> None:
        req = CreateCredentialRequest(type=CredentialType.GITHUB, name="我的GitHub", token="ghp_xxx")
        c = credential_service.create_credential("user-1", req)

        matched = credential_service.match_credential("user-1", "https://github.com/morris2026/orbion")
        assert matched is not None
        assert matched.id == c.id

    def test_match_github_url_with_git_suffix(self, credential_service: CredentialService) -> None:
        req = CreateCredentialRequest(type=CredentialType.GITHUB, name="我的GitHub", token="ghp_xxx")
        c = credential_service.create_credential("user-1", req)

        matched = credential_service.match_credential("user-1", "https://github.com/morris2026/orbion.git")
        assert matched is not None
        assert matched.id == c.id

    """MVP-FL-8.7: match_credential — 无匹配"""

    def test_no_match_for_unknown_host(self, credential_service: CredentialService) -> None:
        req = CreateCredentialRequest(type=CredentialType.GITHUB, name="我的GitHub", token="ghp_xxx")
        credential_service.create_credential("user-1", req)

        matched = credential_service.match_credential("user-1", "https://git.unknown.com/repo.git")
        assert matched is None

    def test_no_match_when_no_credentials(self, credential_service: CredentialService) -> None:
        matched = credential_service.match_credential("user-1", "https://github.com/user/repo.git")
        assert matched is None

    """MVP-FL-8.8: match_credential — 同类型多条取最新"""

    def test_multiple_github_credentials_returns_latest(self, credential_service: CredentialService) -> None:
        req1 = CreateCredentialRequest(type=CredentialType.GITHUB, name="旧GitHub", token="ghp_old")
        req2 = CreateCredentialRequest(type=CredentialType.GITHUB, name="新GitHub", token="ghp_new")
        credential_service.create_credential("user-1", req1)
        c2 = credential_service.create_credential("user-1", req2)

        matched = credential_service.match_credential("user-1", "https://github.com/user/repo.git")
        assert matched is not None
        assert matched.id == c2.id  # 最新的
