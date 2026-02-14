import pytest
from app.models import User

def test_update_profile_success(client, fake_user, db):
    # Initial state
    assert fake_user.username.startswith("user_")
    assert fake_user.email.startswith("user_")
    assert fake_user.email.endswith("@test.com")

    # Update both
    response = client.put(
        "/update_profile",
        json={"username": "newname", "email": "new@test.com"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "newname"
    assert data["email"] == "new@test.com"

    # Verify DB
    db.refresh(fake_user)
    assert fake_user.username == "newname"
    assert fake_user.email == "new@test.com"

def test_update_profile_partial(client, fake_user, db):
    # Update only username
    response = client.put(
        "/update_profile",
        json={"username": "onlyname"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "onlyname"
    # Email should remain same
    assert response.json()["email"] == fake_user.email

    # Update only email
    response = client.put(
        "/update_profile",
        json={"email": "only@test.com"}
    )
    assert response.status_code == 200
    assert response.json()["username"] == "onlyname"
    assert response.json()["email"] == "only@test.com"

def test_update_profile_duplicate_username(client, fake_user, db):
    # Create another user first
    other_user = User(
        id="unique_id_123",
        username="taken",
        password_hash="hash",
        email="other@test.com"
    )
    db.add(other_user)
    db.commit()

    # Try to take 'taken' username
    response = client.put(
        "/update_profile",
        json={"username": "taken"}
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Username already taken"

def test_update_profile_invalid_username_length(client, fake_user):
    response = client.put(
        "/update_profile",
        json={"username": "ab"} # Too short
    )
    assert response.status_code == 422 # Validation error
