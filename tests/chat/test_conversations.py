def test_get_conversations(client):
    response = client.get("/conversations/")
    assert response.status_code == 200
