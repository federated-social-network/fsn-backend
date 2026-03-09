import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine, get_db
from app.main import app
from app.models import User
from app.routers.users import get_current_user


# Create schema once for the whole test session
@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    connection = engine.connect()
    transaction = connection.begin()

    session = SessionLocal(bind=connection)
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def fake_user(db: Session):
    user = User(
        id=str(uuid.uuid4()),
        username=f"testuser_{uuid.uuid4().hex[:6]}",
        email=f"{uuid.uuid4().hex[:6]}@test.com",
        password_hash=User.hash_password("testpassword"),
    )
    user.plain_password = "testpassword"  # Store the plain password for testing
    db.add(user)
    db.flush()  # important: do not commit
    db.refresh(user)
    return user


@pytest.fixture(autouse=True)
def override_db(db):
    app.dependency_overrides[get_db] = lambda: db
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture(autouse=True)
def override_auth(fake_user):
    app.dependency_overrides[get_current_user] = lambda: fake_user
    yield
    app.dependency_overrides.pop(get_current_user, None)
