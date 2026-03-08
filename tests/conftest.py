import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine, SessionLocal, get_db

import app.models


@pytest.fixture(scope="session", autouse=True)
def create_test_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client(db):

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()

@pytest.fixture()
def fake_user(db):
    from app.models import User
    import uuid

    user = User(
        id=str(uuid.uuid4()),
        username="testuser7",
        email="test@test.com",
        password_hash="$argon2id$v=19$m=65536,t=3,p=4$testhash",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return user