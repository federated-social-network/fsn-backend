import httpx
from app.config import settings

def build_create_activity(post, base_url):
    actor_url = f"{base_url}/users/{post.author}"
    return {
        "type": "Create",
        "actor": actor_url,
        "object": {
            "type": "Note",
            "id": f"{base_url}/posts/{post.id}",
            "content": post.content,
            "attributedTo": actor_url,
            "published": post.created_at.isoformat()
        }
    }

def build_delete_activity(post, base_url):
    actor_url = f"{base_url}/users/{post.author}"
    return {
        "type": "Delete",
        "actor": actor_url,
        "object": {
            "id": f"{base_url}/posts/{post.id}"
        }
    }

def build_follow_activity(actor_url: str, target_actor: str):
    return {
        "type": "Follow",
        "actor": actor_url,
        "object": target_actor
    }

def deliver_activity(activity):
    if not settings.DELIVERY_ENABLED:
        return
    
    payload = {
        "type": activity.type,
        "actor": activity.actor,
        "object": activity.object
    }
    try:
        resp = httpx.post(settings.REMOTE_INBOX_URL, json=payload, timeout=5)
        if resp.status_code in (200, 202):
            activity.is_delivered = True
    except Exception:
        pass

def deliver_raw_activity(activity_json: dict):
    if not settings.SEND_TO_OTHER_INSTANCE:
        return
    try:
        httpx.post(settings.REMOTE_INBOX_URL, json=activity_json, timeout=5)
    except Exception:
        pass