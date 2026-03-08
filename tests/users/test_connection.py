def test_connect_user(client):
    client.post("auth/register", params={"username": "testuser",
                "password": "testpass", "email": "test@test.com"})
    response = client.post("/connect/testuser")
    assert response.status_code == 200


def test_pending_connections(client):
    response = client.get("/connections/pending")
    assert response.status_code == 200


def test_count_connections(client):
    response = client.get("/count_connections/")
    assert response.status_code == 200


def test_list_connections(client):
    response = client.get("/list_connections/")
    assert response.status_code == 200
