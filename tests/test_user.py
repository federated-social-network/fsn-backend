def test_get_current_user(client):
    response = client.get("/get_current_user")

    assert response.status_code == 200
    data = response.json()

    assert data["username"] == "testuser"
    assert data["email"] == "test@test.com"