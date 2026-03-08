def test_notifications_get_func(client):
    response = client.get("/notifications/")
    assert response.status_code == 200
