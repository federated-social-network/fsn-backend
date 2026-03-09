def test_register_success(client):
    response = client.post(
        "/auth/register",
        params={
            "username": "newuser13",
            "email": "example12@gmail.com",
            "password": "newpassword1",
        },
    )
    print(response.json())
    assert response.status_code == 200
