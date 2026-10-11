import pytest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from app.core.config import Settings

KEYS_DIR = Path(__file__).resolve().parents[1] / 'app' / 'core' / 'keys'
PRIVATE_KEY = (KEYS_DIR / 'private_key.pem').read_text(encoding='utf-8')
PUBLIC_KEY = (KEYS_DIR / 'public_key.pem').read_text(encoding='utf-8')


def make_test_settings() -> Settings:
    """Build the default settings used across backend tests."""
    return Settings(
        SECRET_KEY='a' * 32,
        DATABASE_URL='sqlite:///./test.db',
        REDIS_URL='redis://localhost:6379/0',
        CELERY_BROKER_URL='redis://localhost:6379/1',
        CELERY_RESULT_BACKEND='redis://localhost:6379/2',
        ENVIRONMENT='testing',
        DEBUG=False,
        JWT_PRIVATE_KEY_PATH='',
        JWT_PUBLIC_KEY_PATH='',
        EVAL_MODE='local',
        DEV_MOCK_JUDGE=True,
        DEV_MOCK_TARGET_AGENT=True,
        DEV_SEED_DATA=True,
        S3_ACCESS_KEY='test_access_key',
        S3_SECRET_KEY='test_secret_key',
    )


@pytest.fixture
def test_settings():
    """Provide test settings for all tests."""
    return make_test_settings()


@pytest.fixture(autouse=True)
def mock_settings(test_settings):
    """Override settings globally for tests."""
    with patch('app.core.config.get_settings', return_value=test_settings):
        yield


@pytest.fixture
def client():
    """Provide a FastAPI test client."""
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_access_token():
    """Generate a valid access token for testing."""
    from app.core.security import create_access_token

    with patch('app.core.security.load_private_key', return_value=(PRIVATE_KEY, 'RS256')), \
         patch('app.core.security.load_public_key', return_value=(PUBLIC_KEY, 'RS256')):
        return create_access_token(
            data={
                'sub': str(uuid4()),
                'username': 'test_user',
                'email': 'test@example.com',
                'roles': ['admin'],
                'scopes': ['admin', 'safety_engineer'],
                'type': 'access',
            },
            expires_delta=timedelta(hours=1),
        )


@pytest.fixture
def admin_headers(sample_access_token):
    """Provide authorization headers for admin requests."""
    return {'Authorization': f'Bearer {sample_access_token}'}


@pytest.fixture
def viewer_token():
    """Generate a viewer access token."""
    from app.core.security import create_access_token

    with patch('app.core.security.load_private_key', return_value=(PRIVATE_KEY, 'RS256')), \
         patch('app.core.security.load_public_key', return_value=(PUBLIC_KEY, 'RS256')):
        token = create_access_token(
            data={
                'sub': str(uuid4()),
                'username': 'viewer_user',
                'email': 'viewer@example.com',
                'roles': ['viewer'],
                'scopes': ['viewer'],
                'type': 'access',
            },
            expires_delta=timedelta(hours=1),
        )
    return token


@pytest.fixture
def viewer_headers(viewer_token):
    """Provide authorization headers for viewer requests."""
    return {'Authorization': f'Bearer {viewer_token}'}