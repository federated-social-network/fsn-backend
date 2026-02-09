from fastapi import Depends
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.routers.users import get_current_user
from app.models import User
import uuid
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Post, User

@pytest.fixture
def client():   
    return TestClient(app)

@pytest.fixture
def db():
    db = next(get_db())
    trans = db.begin()
    try:
        yield db
    finally:
        trans.rollback()
        db.close()

@pytest.fixture
def fake_user(db: Session):
    user = User(
        id=str(uuid.uuid4()),
        username="testuser2",
        email="test@test.com",
        password_hash=User.hash_password("testpassword")
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture(autouse=True)
def override_auth(fake_user):
    app.dependency_overrides[get_current_user] = lambda: fake_user
    yield
    app.dependency_overrides.clear()