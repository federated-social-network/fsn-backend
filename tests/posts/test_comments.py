def test_comment_post(client):
    # First, create a post to like
    response = client.post(
        "/posts/",
        data={
            "visibility": "public",
            "content": "This is a test post to comment.",
        },
    )
    assert response.status_code == 200
    post_id = response.json().get("id")
    print(post_id)

    # # Now, like the post
    comment_response = client.post(
        f"/{post_id}/comments", json={"content": "This is a test comment."})
    assert comment_response.status_code == 200


def test_get_comments(client):
    # First, create a post to comment on
    response = client.post(
        "/posts/",
        data={
            "visibility": "public",
            "content": "This is a test post to get comments.",
        },
    )
    assert response.status_code == 200
    post_id = response.json().get("id")

    # Add a comment to the post
    client.post(f"/{post_id}/comments",
                json={"content": "This is a test comment."})

    # Now, get the comments for the post
    get_comments_response = client.get(f"/{post_id}/comments")
    assert get_comments_response.status_code == 200


def test_delete_comment(client):
    # First, create a post to comment on
    response = client.post(
        "/posts/",
        data={
            "visibility": "public",
            "content": "This is a test post to delete comment.",
        },
    )
    assert response.status_code == 200
    post_id = response.json().get("id")

    # Add a comment to the post
    comment_response = client.post(
        f"/{post_id}/comments", json={"content": "This is a test comment to delete."})
    assert comment_response.status_code == 200
    comment_id = comment_response.json().get("id")

    # Now, delete the comment
    delete_comment_response = client.delete(f"/comments/{comment_id}")
    assert "Comment deleted" in delete_comment_response.json().get("message", "")
