"""步骤7认证模块UT：密码哈希、JWT、依赖注入、RegistrationPolicy"""

import time

import jwt
import pytest

from app.config import Settings


class TestPasswordHashing:
    """TC-7.17: 密码哈希与验证"""

    def test_hash_and_verify_correct_password(self) -> None:
        """正确密码验证成功"""
        from app.hub.auth.service import hash_password, verify_password

        hashed = hash_password("mypassword123")
        assert verify_password("mypassword123", hashed)

    def test_hash_and_verify_wrong_password(self) -> None:
        """错误密码验证失败"""
        from app.hub.auth.service import hash_password, verify_password

        hashed = hash_password("mypassword123")
        assert not verify_password("wrongpassword", hashed)

    def test_hash_format_is_bcrypt(self) -> None:
        """哈希长度符合bcrypt格式"""
        from app.hub.auth.service import hash_password

        hashed = hash_password("mypassword123")
        # bcrypt hash: $2b$12$... 共60字符
        assert len(hashed) == 60
        assert hashed.startswith("$2b$")


class TestJWTGenerationAndVerification:
    """TC-7.16: JWT生成和验证"""

    def test_jwt_contains_required_fields(self) -> None:
        """payload含sub/username/display_name/is_admin/iss/exp/iat"""
        from app.hub.auth.service import create_access_token

        settings = Settings()
        token = create_access_token(
            user_id="user-1",
            username="morris",
            display_name="Morris",
            is_admin=True,
            settings=settings,
        )
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        assert payload["sub"] == "user-1"
        assert payload["username"] == "morris"
        assert payload["display_name"] == "Morris"
        assert payload["is_admin"] is True
        assert payload["iss"] == "orbion"
        assert "exp" in payload
        assert "iat" in payload

    def test_jwt_algorithm_is_hs256(self) -> None:
        """HS256算法"""
        from app.hub.auth.service import create_access_token

        settings = Settings()
        token = create_access_token(
            user_id="user-1",
            username="morris",
            display_name="Morris",
            is_admin=False,
            settings=settings,
        )
        # jwt.get_algorithm_header 检查算法
        header = jwt.get_unverified_header(token)
        assert header["alg"] == "HS256"

    def test_jwt_secret_from_config(self) -> None:
        """密钥从config读取"""
        from app.hub.auth.service import create_access_token

        settings = Settings(jwt_secret="test-secret-key")
        token = create_access_token(
            user_id="user-1",
            username="morris",
            display_name="Morris",
            is_admin=False,
            settings=settings,
        )
        # 用正确的密钥解码成功
        payload = jwt.decode(token, "test-secret-key", algorithms=["HS256"])
        assert payload["sub"] == "user-1"
        # 用错误的密钥解码失败
        with pytest.raises(jwt.InvalidSignatureError):
            jwt.decode(token, "wrong-secret", algorithms=["HS256"])


class TestJWTExpiration:
    """TC-7.8: JWT过期"""

    def test_expired_jwt_raises_401(self) -> None:
        """过期JWT抛出401异常"""
        from fastapi import HTTPException

        from app.hub.auth.dependencies import get_current_user_from_token

        settings = Settings()
        # 创建一个已过期的JWT（exp为1秒前）
        expired_token = jwt.encode(
            {
                "sub": "user-1",
                "username": "morris",
                "display_name": "Morris",
                "is_admin": False,
                "iss": "orbion",
                "exp": int(time.time()) - 1,
                "iat": int(time.time()) - 3600,
            },
            settings.jwt_secret,
            algorithm="HS256",
        )
        with pytest.raises(HTTPException) as exc_info:
            get_current_user_from_token(expired_token, settings)
        assert exc_info.value.status_code == 401


class TestGetCurrentUser:
    """TC-7.9: get_current_user正常返回"""

    def test_decode_valid_jwt_returns_user(self) -> None:
        """返回User对象，字段与JWT payload一致"""
        from app.hub.auth.dependencies import get_current_user_from_token

        settings = Settings()
        token = jwt.encode(
            {
                "sub": "user-1",
                "username": "morris",
                "display_name": "Morris Wang",
                "is_admin": True,
                "iss": "orbion",
                "exp": int(time.time()) + 3600,
                "iat": int(time.time()),
            },
            settings.jwt_secret,
            algorithm="HS256",
        )
        user = get_current_user_from_token(token, settings)
        assert user.id == "user-1"
        assert user.username == "morris"
        assert user.display_name == "Morris Wang"
        assert user.is_admin is True

    def test_jwt_with_wrong_issuer_raises_401(self) -> None:
        """iss不是orbion的JWT抛出401"""
        from fastapi import HTTPException

        from app.hub.auth.dependencies import get_current_user_from_token

        settings = Settings()
        token = jwt.encode(
            {
                "sub": "user-1",
                "username": "morris",
                "display_name": "Morris",
                "is_admin": False,
                "iss": "wrong-issuer",
                "exp": int(time.time()) + 3600,
                "iat": int(time.time()),
            },
            settings.jwt_secret,
            algorithm="HS256",
        )
        with pytest.raises(HTTPException) as exc_info:
            get_current_user_from_token(token, settings)
        assert exc_info.value.status_code == 401


class TestRequireAdmin:
    """TC-7.10: require_admin拦截非管理员"""

    def test_non_admin_raises_403(self) -> None:
        """is_admin=false抛出403"""
        from fastapi import HTTPException

        from app.hub.auth.dependencies import require_admin

        # 创建一个非admin用户
        from app.hub.auth.models import User

        user = User(id="user-1", username="viewer", display_name="Viewer", is_admin=False)
        with pytest.raises(HTTPException) as exc_info:
            require_admin(user)
        assert exc_info.value.status_code == 403
        assert "Admin" in exc_info.value.detail

    def test_admin_passes(self) -> None:
        """is_admin=true正常通过"""
        from app.hub.auth.dependencies import require_admin
        from app.hub.auth.models import User

        user = User(id="admin-1", username="admin", display_name="Admin", is_admin=True)
        result = require_admin(user)
        assert result.id == "admin-1"


class TestAdminApprovalPolicyProtocol:
    """TC-7.19: AdminApprovalPolicy Protocol契约验证"""

    def test_admin_approval_policy_satisfies_protocol(self) -> None:
        """AdminApprovalPolicy满足RegistrationPolicy Protocol"""
        from app.hub.auth.policy import AdminApprovalPolicy, RegistrationPolicy

        policy = AdminApprovalPolicy()
        assert isinstance(policy, RegistrationPolicy)
