def test_user_login(client, fake_user):
    response = client.post(
        "/auth/login",
        params={
            "username": fake_user.username,
            "password": fake_user.plain_password,
        },
    )

    assert response.status_code == 200


def test_user_login_accessToken(client, fake_user):
    response = client.post(
        "/auth/login",
        params={
            "username": fake_user.username,
            "password": fake_user.plain_password,
        },
    )

    assert "access_token" in response.json()
    assert response.status_code == 200
