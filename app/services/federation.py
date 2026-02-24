"""
app/services/federation.py

Outgoing federation helpers:

- build_create_activity   — spec-compliant Create(Note) with @context and id
- build_delete_activity   — spec-compliant Delete(Tombstone) with @context and id
- build_follow_activity   — spec-compliant Follow with @context and id
- build_accept_activity   — Accept(Follow) response
- build_like_activity     — Like activity
- deliver_to_actor        — Fetch remote actor's inbox URL then POST with HTTP Signature
- deliver_activity        — Legacy delivery helper (uses REMOTE_INBOX_URL)
- deliver_raw_activity    — Legacy raw delivery
"""

import uuid
import httpx

from app.config import settings
from app.services.crypto import sign_request

AS_CONTEXT = "https://www.w3.org/ns/activitystreams"
AS_PUBLIC = "https://www.w3.org/ns/activitystreams#Public"


# ---------------------------------------------------------------------------
# Activity builders
# ---------------------------------------------------------------------------

def _new_activity_id() -> str:
    return f"{settings.BASE_URL}/activities/{uuid.uuid4()}"


def build_create_activity(post, base_url: str) -> dict:
    """Build a compliant Create(Note) activity for *post*."""
    actor_url = f"{base_url}/users/{post.author}"
    note_id = f"{base_url}/posts/{post.id}"

    note: dict = {
        "@context": AS_CONTEXT,
        "id": note_id,
        "type": "Note",
        "attributedTo": actor_url,
        "content": post.content,
        "to": [AS_PUBLIC],
        "cc": [f"{actor_url}/followers"],
        "published": post.created_at.isoformat() + "Z" if post.created_at else None,
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
        "@context": AS_CONTEXT,
        "id": _new_activity_id(),
        "type": "Create",
        "actor": actor_url,
        "to": [AS_PUBLIC],
        "cc": [f"{actor_url}/followers"],
        "object": note,
    }


def build_delete_activity(post, base_url: str) -> dict:
    """Build a compliant Delete(Tombstone) activity for *post*."""
    actor_url = f"{base_url}/users/{post.author}"
    return {
        "@context": AS_CONTEXT,
        "id": _new_activity_id(),
        "type": "Delete",
        "actor": actor_url,
        "object": {
            "id": f"{base_url}/posts/{post.id}",
            "type": "Tombstone",
        },
    }


def build_follow_activity(actor_url: str, target_actor: str) -> dict:
    """Build a compliant Follow activity."""
    return {
        "@context": AS_CONTEXT,
        "id": _new_activity_id(),
        "type": "Follow",
        "actor": actor_url,
        "object": target_actor,
    }


def build_accept_activity(actor_url: str, follow_activity: dict) -> dict:
    """Build an Accept(Follow) activity in response to *follow_activity*."""
    return {
        "@context": AS_CONTEXT,
        "id": _new_activity_id(),
        "type": "Accept",
        "actor": actor_url,
        "object": follow_activity,
    }


def build_like_activity(actor_url: str, object_id: str) -> dict:
    """Build a Like activity."""
    return {
        "@context": AS_CONTEXT,
        "id": _new_activity_id(),
        "type": "Like",
        "actor": actor_url,
        "object": object_id,
    }


# ---------------------------------------------------------------------------
# Delivery — with HTTP Signature signing
# ---------------------------------------------------------------------------

def _fetch_inbox_url(actor_url: str) -> str | None:
    """Fetch the inbox URL from a remote actor document."""
    try:
        resp = httpx.get(
            actor_url,
            headers={"Accept": "application/activity+json"},
            timeout=10,
            follow_redirects=True,
        )
        resp.raise_for_status()
        return resp.json().get("inbox")
    except Exception:
        return None


def deliver_to_actor(
    activity_json: dict,
    target_actor_url: str,
    sender_actor_url: str,
    private_key_pem: str,
    key_id: str,
) -> bool:
    """
    Deliver *activity_json* to the inbox of *target_actor_url*.

    Signs the request with the sender's RSA private key.

    Returns True on success (2xx response), False otherwise.
    """
    if not settings.DELIVERY_ENABLED and not settings.SEND_TO_OTHER_INSTANCE:
        return False

    inbox_url = _fetch_inbox_url(target_actor_url)
    if not inbox_url:
        return False

    import json as _json
    body_bytes = _json.dumps(activity_json).encode("utf-8")

    headers = sign_request(
        method="post",
        url=inbox_url,
        body=body_bytes,
        private_key_pem=private_key_pem,
        key_id=key_id,
    )

    try:
        resp = httpx.post(
            inbox_url,
            content=body_bytes,
            headers=headers,
            timeout=10,
        )
        return resp.status_code in (200, 201, 202)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Legacy helpers (backward-compatible)
# ---------------------------------------------------------------------------

def deliver_activity(activity) -> None:
    """Legacy delivery — uses the configured REMOTE_INBOX_URL, unsigned."""
    if not settings.DELIVERY_ENABLED:
        return

    payload = {
        "@context": AS_CONTEXT,
        "type": activity.type,
        "actor": activity.actor,
        "object": activity.object,
    }
    try:
        resp = httpx.post(settings.REMOTE_INBOX_URL, json=payload, timeout=5)
        if resp.status_code in (200, 202):
            activity.is_delivered = True
    except Exception:
        pass


def deliver_raw_activity(activity_json: dict) -> None:
    """Legacy raw delivery — uses the configured REMOTE_INBOX_URL, unsigned."""
    if not settings.SEND_TO_OTHER_INSTANCE:
        return
    try:
        httpx.post(settings.REMOTE_INBOX_URL, json=activity_json, timeout=5)
    except Exception:
        pass
