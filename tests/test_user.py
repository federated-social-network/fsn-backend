def test_get_current_user(client, override_auth, fake_user):
    response = client.get("/get_current_user")

    assert response.status_code == 200
    data = response.json()

    assert data["username"] == fake_user.username
    assert data["email"] == fake_user.email
