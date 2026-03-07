def test_create_posts(client):
    response = client.post(
        "/posts/",
        data={
            "visibility": "public",
            "content": "This is a test post.",
        }
    )

    assert response.status_code == 200

