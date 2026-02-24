import json
import httpx
from app.config import settings
from app.services.crypto import sign_request


def build_create_activity(post, base_url):
    actor_url = f"{base_url}/users/{post.author}"

    note = {
        "type": "Note",
        "id": f"{base_url}/posts/{post.id}",
        "content": post.content,
        "attributedTo": actor_url,
        "published": post.created_at.isoformat(),
    }

    if post.image_url:
        note["attachment"] = [
            {
                "type": "Image",
                "mediaType": "image/jpeg",
                "url": post.image_url,
            }
        ]

    return {
        "@context": "https://www.w3.org/ns/activitystreams",
        "type": "Create",
        "actor": actor_url,
        "object": note,
    }


def build_delete_activity(post, base_url):
    actor_url = f"{base_url}/users/{post.author}"
    return {
        "@context": "https://www.w3.org/ns/activitystreams",
        "type": "Delete",
        "actor": actor_url,
        "object": {"id": f"{base_url}/posts/{post.id}"},
    }


def build_follow_activity(actor_url: str, target_actor: str):
    return {
        "@context": "https://www.w3.org/ns/activitystreams",
        "type": "Follow",
        "actor": actor_url,
        "object": target_actor,
    }


def build_accept_activity(actor_url: str, follow_activity: dict):
    return {
        "@context": "https://www.w3.org/ns/activitystreams",
        "type": "Accept",
        "actor": actor_url,
        "object": follow_activity,
    }


def deliver_activity(activity, user=None):
    """Deliver an activity to the configured remote inbox."""
    if not settings.DELIVERY_ENABLED:
        return

    payload = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "type": activity.type,
        "actor": activity.actor,
        "object": activity.object,
    }

    body = json.dumps(payload).encode("utf-8")

    try:
        headers = {"Content-Type": "application/activity+json"}

        # Sign the request if the user has a private key
        if user and user.private_key:
            key_id = f"{settings.BASE_URL}/users/{user.username}#main-key"
            headers = sign_request(
                private_key_pem=user.private_key,
                method="POST",
                url=settings.REMOTE_INBOX_URL,
                body=body,
                key_id=key_id,
            )

        resp = httpx.post(
            settings.REMOTE_INBOX_URL,
            content=body,
            headers=headers,
            timeout=5,
        )
        if resp.status_code in (200, 202):
            activity.is_delivered = True
    except Exception:
        pass


def deliver_raw_activity(activity_json: dict, user=None):
    """Deliver a raw activity dict to the configured remote inbox, with HTTP Signatures."""
    if not settings.SEND_TO_OTHER_INSTANCE:
        return

    body = json.dumps(activity_json).encode("utf-8")

    try:
        headers = {"Content-Type": "application/activity+json"}

        # Sign the request if the user has a private key
        if user and user.private_key:
            key_id = f"{settings.BASE_URL}/users/{user.username}#main-key"
            headers = sign_request(
                private_key_pem=user.private_key,
                method="POST",
                url=settings.REMOTE_INBOX_URL,
                body=body,
                key_id=key_id,
            )

        httpx.post(
            settings.REMOTE_INBOX_URL,
            content=body,
            headers=headers,
            timeout=5,
        )
    except Exception:
        pass


def deliver_to_inbox(activity_json: dict, inbox_url: str, user=None):
    """Deliver an activity to a specific inbox URL, with HTTP Signatures."""
    body = json.dumps(activity_json).encode("utf-8")

    try:
        headers = {"Content-Type": "application/activity+json"}

        if user and user.private_key:
            key_id = f"{settings.BASE_URL}/users/{user.username}#main-key"
            headers = sign_request(
                private_key_pem=user.private_key,
                method="POST",
                url=inbox_url,
                body=body,
                key_id=key_id,
            )

        httpx.post(
            inbox_url,
            content=body,
            headers=headers,
            timeout=10,
        )
    except Exception:
        pass
