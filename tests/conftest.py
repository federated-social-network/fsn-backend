import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine, SessionLocal, get_db

# IMPORTANT: ensure models are imported so SQLAlchemy registers them
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


# ---------------------------------------------------
# Fake user fixture used by tests
# ---------------------------------------------------
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








'''
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.database import SessionLocal, engine, get_db
from app.main import app
from app.models import User
from app.routers.users import get_current_user


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def db():
    connection = engine.connect()
    transaction = connection.begin()  # outer transaction

    session = SessionLocal(bind=connection)
    session.begin_nested()  # SAVEPOINT

    @event.listens_for(session, "after_transaction_end")
    def restart_savepoint(sess, trans):
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()  # full rollback
        connection.close()


@pytest.fixture
def fake_user(db: Session):
    user = User(
        id=str(uuid.uuid4()),
        username="testuser7",
        email="test@test.com",
        password_hash=User.hash_password("testpassword"),
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

'''
