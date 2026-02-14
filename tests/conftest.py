from fastapi import Depends
import pytest
import os

# Set environment variables for testing BEFORE importing app
os.environ["INSTANCE_NAME"] = "testinfo.com"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"  # Use in-memory DB for tests if possible, or a file
os.environ["SECRET_KEY"] = "supersecretkey"
os.environ["BASE_URL"] = "http://testinfo.com"

from fastapi.testclient import TestClient
from app.main import app
from app.routers.users import get_current_user
from app.models import User
import uuid
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Post, User
from sqlalchemy import event
from sqlalchemy.orm import Session
from app.database import engine, SessionLocal

@pytest.fixture
def client():   
    return TestClient(app)


@pytest.fixture
def db():
    connection = engine.connect()
    transaction = connection.begin()      # outer transaction

    session = SessionLocal(bind=connection)
    session.begin_nested()                # SAVEPOINT

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()            # full rollback
        connection.close()


@pytest.fixture
def fake_user(db: Session):
    uid = str(uuid.uuid4())
    unique_suffix = uid[:8]
    user = User(
        id=uid,
        username=f"user_{unique_suffix}",
        email=f"user_{unique_suffix}@test.com",
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

@pytest.fixture(autouse=True)
def override_db(db):
    app.dependency_overrides[get_db] = lambda: db
    yield
    app.dependency_overrides.clear()