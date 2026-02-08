def test_user_login(client):
    response = client.post('/auth/login', params={
        "username": "newuser13",
        "password": "newpassword1"
    })
    print(response.json())
    assert response.status_code == 200