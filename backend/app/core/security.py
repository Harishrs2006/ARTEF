import base64
import hashlib
import os
import types
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, SecurityScopes

if not hasattr(bcrypt, "__about__"):
    bcrypt.__about__ = types.SimpleNamespace(__version__="4.0.0")

from jose import JWTError, jwt
from pydantic import BaseModel

from app.core.config import get_settings

settings = get_settings()

# bcrypt silently ignores everything past 72 bytes. Truncating the password
# would make two different passwords with a shared 72-byte prefix
# interchangeable, so the password is pre-hashed with SHA-256 and base64
# encoded first: the full entropy is preserved and the bcrypt input is always
# 44 bytes.
BCRYPT_MAX_BYTES = 72
BCRYPT_ROUNDS = 12


def _prepare_password(password: str) -> bytes:
    """Return a fixed-length, entropy-preserving representation for bcrypt."""
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_PREFIX}/auth/login",
    scopes={
        "admin": "Full administrative access",
        "safety_engineer": "Create and manage test suites, baselines",
        "ml_engineer": "Run evaluations, view results",
        "qa_engineer": "Run evaluations, manage test cases",
        "reviewer": "Review and label findings",
        "viewer": "Read-only access to dashboards and reports",
    },
    auto_error=True,  # SECURITY: Always enforce authentication, fail-closed
)


class TokenData(BaseModel):
    sub: str
    username: str
    email: str
    roles: list[str]
    scopes: list[str]
    exp: int


class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


def _bcrypt_verify(secret: bytes, hashed_password: str) -> bool:
    """Verify a bcrypt hash, tolerating a malformed or empty stored hash."""
    if not hashed_password:
        return False
    try:
        return bcrypt.checkpw(secret, hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a stored hash.

    Hashes created before the SHA-256 pre-hashing change were computed over
    the raw password. Both formats are accepted, and a successful legacy
    verification is transparently upgraded by :func:`get_password_hash`.
    """
    if _bcrypt_verify(_prepare_password(plain_password), hashed_password):
        return True
    # Legacy format: the raw password was hashed directly.
    raw = plain_password.encode("utf-8")
    if len(raw) > BCRYPT_MAX_BYTES:
        raw = raw[:BCRYPT_MAX_BYTES]
    return _bcrypt_verify(raw, hashed_password)


def needs_rehash(plain_password: str, hashed_password: str) -> bool:
    """True when the stored hash uses the legacy (pre-hashing) format."""
    return not _bcrypt_verify(_prepare_password(plain_password), hashed_password)


def get_password_hash(password: str) -> str:
    return bcrypt.hashpw(
        _prepare_password(password), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    ).decode("utf-8")


def _default_key_path(key_name: str) -> str:
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    default = os.path.normpath(os.path.join(project_root, "backend", "app", "core", "keys", key_name))
    if os.path.exists(default):
        return default

    local = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys", key_name))
    if os.path.exists(local):
        return local

    return default


def _resolve_key_path(path: str | None, key_name: str) -> str:
    """
    Resolve key path with security constraints.
    SECURITY: Only allows absolute paths or paths within project root to prevent path traversal.
    """
    if not path:
        return _default_key_path(key_name)

    path = os.path.normpath(path)

    if ".." in path or path.startswith("/etc") or path.startswith("\\\\"):
        raise ValueError(f"Invalid key path (potential path traversal): {path}")

    if os.path.isabs(path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Key file not found: {path}")
        if not os.path.isfile(path):
            raise ValueError(f"Key path must be a regular file: {path}")
        return path

    try:
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

        candidate = os.path.normpath(os.path.join(project_root, path))

        if not candidate.startswith(project_root):
            raise ValueError(f"Key path escapes project root: {path}")

        if os.path.exists(candidate) and os.path.isfile(candidate):
            return candidate

        candidate2 = os.path.normpath(os.path.join(project_root, "backend", "app", "core", "keys", os.path.basename(path)))
        if candidate2.startswith(project_root) and os.path.exists(candidate2) and os.path.isfile(candidate2):
            return candidate2

    except Exception as e:
        raise ValueError(f"Failed to resolve key path: {e}")
    keys_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keys")
    candidate3 = os.path.join(keys_dir, os.path.basename(path))
    if os.path.exists(candidate3):
        return candidate3
    return path


def _read_key_file(path: str) -> str:
    """Read a key file, raising FileNotFoundError if it doesn't exist."""
    resolved = _resolve_key_path(path, "private_key.pem" if "private" in (path or "") else "public_key.pem")
    if not os.path.exists(resolved):
        raise FileNotFoundError(f"Key file not found: {path} (resolved: {resolved})")
    with open(resolved) as f:
        return f.read()


def load_private_key() -> tuple[str, str]:
    settings = get_settings()
    key_path = settings.JWT_PRIVATE_KEY_PATH or _default_key_path("private_key.pem")
    return _read_key_file(key_path), settings.JWT_ALGORITHM


def load_public_key() -> tuple[str, str]:
    settings = get_settings()
    key_path = settings.JWT_PUBLIC_KEY_PATH or _default_key_path("public_key.pem")
    return _read_key_file(key_path), settings.JWT_ALGORITHM


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    private_key, algorithm = load_private_key()
    return jwt.encode(to_encode, private_key, algorithm=algorithm)


def create_refresh_token(data: dict[str, Any]) -> str:
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    private_key, algorithm = load_private_key()
    return jwt.encode(to_encode, private_key, algorithm=algorithm)


def _decode_and_validate(token: str, expected_type: str) -> TokenData:
    """Decode a JWT and validate its payload.

    A structurally valid but semantically wrong token is an authentication
    failure (401), not a server misconfiguration (500).
    """
    public_key, algorithm = load_public_key()
    payload = jwt.decode(
        token,
        public_key,
        algorithms=[algorithm],
        options={"verify_aud": False},
    )
    if payload.get("type") != expected_type:
        raise JWTError("Invalid token type")
    try:
        return TokenData(**payload)
    except Exception as e:
        raise JWTError("Invalid token payload") from e


def decode_token(token: str) -> TokenData:
    try:
        return _decode_and_validate(token, "access")
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server authentication configuration error",
        ) from e


def decode_refresh_token(token: str) -> TokenData:
    try:
        return _decode_and_validate(token, "refresh")
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server authentication configuration error",
        ) from e


async def get_current_user(
    security_scopes: SecurityScopes,
    token: str | None = Depends(oauth2_scheme),
) -> TokenData:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = decode_token(token)
    if security_scopes.scopes:
        for scope in security_scopes.scopes:
            if scope not in token_data.scopes:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Not enough permissions",
                    headers={"WWW-Authenticate": f'Bearer scope="{security_scopes.scope_str}"'},
                )
    return token_data


def require_role(required_roles: list[str]):
    async def role_checker(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        if not any(role in current_user.roles for role in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient role permissions",
            )
        return current_user

    return role_checker


def require_scope(required_scopes: list[str]):
    async def scope_checker(current_user: TokenData = Depends(get_current_user)) -> TokenData:
        if not any(scope in current_user.scopes for scope in required_scopes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient scope permissions",
            )
        return current_user

    return scope_checker


ROLE_SCOPES = {
    "admin": ["admin", "safety_engineer", "ml_engineer", "qa_engineer", "reviewer", "viewer"],
    "safety_engineer": ["safety_engineer", "ml_engineer", "qa_engineer", "reviewer", "viewer"],
    "ml_engineer": ["ml_engineer", "qa_engineer", "viewer"],
    "qa_engineer": ["qa_engineer", "viewer"],
    "reviewer": ["reviewer", "viewer"],
    "viewer": ["viewer"],
}


def get_scopes_for_roles(roles: list[str]) -> list[str]:
    scopes = set()
    for role in roles:
        scopes.update(ROLE_SCOPES.get(role, []))
    return list(scopes)


def resolve_user_roles(user: Any) -> list[str]:
    """Resolve the effective role names of a user.

    A user may carry no role at all - for example an account created through
    ``/auth/register`` before any role was assigned, or a bootstrap admin
    flagged only with ``is_superuser``. Without a role the token carried an
    empty scope list, and every protected endpoint answered 403, which locked
    the user out of the console they had just signed in to.

    Superusers therefore fall back to the ``admin`` role, and a user without
    any role falls back to ``viewer`` so that the console remains reachable
    in a read-only capacity instead of failing every request.
    """
    roles = [role.name for role in getattr(user, "roles", None) or []]

    if not roles and getattr(user, "is_superuser", False):
        roles = ["admin"]
    if not roles:
        roles = ["viewer"]

    return roles
