import pytest
from fastapi.testclient import TestClient
from app.main import app, get_current_user
from app.models import User

@pytest.fixture
def client():
    return TestClient(app)

@pytest.fixture
def fake_user():
    return User(
        id="user-123",
        username="testuser",
        email="test@test.com"
    )

@pytest.fixture(autouse=True)
def override_auth(fake_user):
    app.dependency_overrides[get_current_user] = lambda: fake_user
    yield
    app.dependency_overrides.clear()