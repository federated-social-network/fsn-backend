def test_create_posts(client):
    response = client.post('/posts', params={
        "content": "This is a test post."
    })
    print(response.json())
    assert response.status_code == 200
    