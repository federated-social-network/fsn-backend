def test_verify_otp_failure(client):
    response = client.post(
        "/auth/verify-otp", json={"otp": "123456", "email": "example12@gmail.com"}
    )
    assert response.status_code == 400
