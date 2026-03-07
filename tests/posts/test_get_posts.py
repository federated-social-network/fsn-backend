def test_posts_get_func(client):
    response = client.get("/get_posts/")
    assert response.status_code == 200