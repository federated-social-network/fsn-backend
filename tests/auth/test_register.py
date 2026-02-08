def test_register_success(client):
    response = client.post('/auth/register', params={
        "username": "newuser11",
        "email": "example11@gmail.com",
        "password": "newpassword1"
    })
    print(response.json())
    assert response.status_code == 200