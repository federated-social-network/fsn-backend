def test_get_user(client):
    client.post(
        "auth/register",
        params={
            "username": "testuser",
            "password": "testpass",
            "email": "test@test.com",
        },
    )
    response = client.get("/get_user/testuser")
    assert response.status_code == 200


def test_get_user_not_found(client):
    response = client.get("/get_user/nonexistentuser")
    assert response.status_code == 404


def test_random_users(client):
    response = client.get("/random_users/")
    assert response.status_code == 200
