def test_forgot_password_invalid_mail(client):
    response = client.post(
        "/auth/forgot-password", json={"email": "example1211@gmail.com"}
    )
    print(response.json())
    assert response.status_code == 404
