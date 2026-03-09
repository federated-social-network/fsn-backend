from jose import jwt

from app.config import settings


def test_refresh_token_success(client, fake_user):
    # 1. Login to get initial tokens
    login_response = client.post(
        "/auth/login",
        params={
            "username": fake_user.username,
            "password": fake_user.plain_password,
        },
    )
    assert login_response.status_code == 200
    data = login_response.json()
    refresh_token = data["refresh_token"]

    # 2. Use refresh token to get a new access token
    refresh_response = client.post(
        "/auth/refresh",
        params={"refresh_token": refresh_token},
    )

    assert refresh_response.status_code == 200
    new_data = refresh_response.json()
    assert "access_token" in new_data

    # 3. Verify the new access token
    new_access_token = new_data["access_token"]
    payload = jwt.decode(
        new_access_token,
        settings.SECRET_KEY,
        algorithms=[settings.ALGORITHM],
    )

    assert payload["username"] == fake_user.username


def test_refresh_token_expired(client, fake_user):
    from datetime import datetime, timedelta

    to_encode = {
        "user_id": fake_user.id,
        "username": fake_user.username,
        "instance": "test",
        "type": "refresh",
        "exp": datetime.utcnow() - timedelta(days=1),
    }

    expired_token = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    response = client.post(
        "/auth/refresh",
        params={"refresh_token": expired_token},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Refresh token expired"
