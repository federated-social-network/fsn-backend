import json
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Post, Activity, Connection, User
from app.dependencies import get_current_user
from app.config import settings
from app.services.crypto import sign_request, verify_http_signature
from urllib.parse import urlparse

router = APIRouter()


# ---------------------------------------------------------------------------
# WebFinger — resource discovery
# ---------------------------------------------------------------------------
@router.get("/.well-known/webfinger")
def webfinger(resource: str = Query(...), db: Session = Depends(get_db)):
    """
    WebFinger endpoint for ActivityPub actor discovery.
    Mastodon queries: /.well-known/webfinger?resource=acct:alice@domain.com
    """
    if not resource.startswith("acct:"):
        raise HTTPException(status_code=400, detail="Resource must start with acct:")

    # Parse "acct:alice@domain.com"
    acct = resource[5:]  # remove "acct:"
    if "@" not in acct:
        raise HTTPException(status_code=400, detail="Invalid acct format")

    username = acct.split("@")[0]

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    actor_url = f"{settings.BASE_URL}/users/{username}"
    parsed = urlparse(settings.BASE_URL)
    domain = parsed.hostname
    if parsed.port and parsed.port not in (80, 443):
        domain = f"{domain}:{parsed.port}"

    return JSONResponse(
        content={
            "subject": f"acct:{username}@{domain}",
            "links": [
                {
                    "rel": "self",
                    "type": "application/activity+json",
                    "href": actor_url,
                }
            ],
        },
        media_type="application/jrd+json",
    )


# ---------------------------------------------------------------------------
# Actor endpoint — ActivityPub actor JSON-LD
# ---------------------------------------------------------------------------
@router.get("/users/{username}")
def get_actor(username: str, db: Session = Depends(get_db)):
    """
    ActivityPub Actor endpoint.
    Returns JSON-LD actor object with inbox, outbox, publicKey, etc.
    """
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    actor_url = f"{settings.BASE_URL}/users/{username}"

    actor = {
        "@context": [
            "https://www.w3.org/ns/activitystreams",
            "https://w3id.org/security/v1",
        ],
        "id": actor_url,
        "type": "Person",
        "preferredUsername": username,
        "name": username,
        "inbox": f"{actor_url}/inbox",
        "outbox": f"{actor_url}/outbox",
        "followers": f"{actor_url}/followers",
        "following": f"{actor_url}/following",
        "url": actor_url,
        "endpoints": {
            "sharedInbox": f"{settings.BASE_URL}/inbox",
        },
    }

    if user.public_key:
        actor["publicKey"] = {
            "id": f"{actor_url}#main-key",
            "owner": actor_url,
            "publicKeyPem": user.public_key,
        }

    if user.avatar_url:
        actor["icon"] = {
            "type": "Image",
            "mediaType": "image/jpeg",
            "url": user.avatar_url,
        }

    return JSONResponse(
        content=actor,
        media_type="application/activity+json",
    )


# ---------------------------------------------------------------------------
# Per-user inbox
# ---------------------------------------------------------------------------
@router.post("/users/{username}/inbox")
async def user_inbox(
    username: str, request: Request, db: Session = Depends(get_db)
):
    """
    Per-user inbox. Mastodon sends Follow, Undo, etc. here.
    Delegates to shared inbox logic.
    """
    body = await request.body()
    try:
        activity = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Verify the target user exists
    target_user = db.query(User).filter(User.username == username).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Process the activity using shared logic
    return _process_inbox_activity(activity, db)


# ---------------------------------------------------------------------------
# Shared inbox
# ---------------------------------------------------------------------------
@router.post("/inbox")
async def shared_inbox(request: Request, db: Session = Depends(get_db)):
    """
    Shared inbox endpoint. Receives activities from remote instances.
    """
    body = await request.body()
    try:
        activity = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    return _process_inbox_activity(activity, db)


def _process_inbox_activity(activity: dict, db: Session) -> dict:
    """
    Process an incoming ActivityPub activity.
    Handles Create, Delete, Follow, Accept, Undo.
    """
    activity_type = activity.get("type")
    actor = activity.get("actor")
    obj = activity.get("object")

    if not activity_type or not actor or obj is None:
        raise HTTPException(status_code=400, detail="Invalid activity")

    # Store activity (remote)
    new_activity = Activity(
        type=activity_type,
        actor=actor,
        object=obj if isinstance(obj, dict) else {"id": obj},
        is_local=False,
        is_delivered=True,
    )
    db.add(new_activity)

    # Handle Create (Note)
    if activity_type == "Create" and isinstance(obj, dict) and obj.get("type") == "Note":
        post_id = obj.get("id")
        content = obj.get("content")
        image_url = obj.get("image_url")

        # Check for image in attachment array (Mastodon format)
        if not image_url and obj.get("attachment"):
            for att in obj["attachment"]:
                if att.get("type") == "Image":
                    image_url = att.get("url")
                    break

        existing = db.query(Post).filter(Post.id == post_id).first()
        if not existing:
            post = Post(
                id=post_id,
                content=content,
                image_url=image_url,
                user_id=None,
                author=actor,
                origin_instance=actor.split("/users/")[0] if "/users/" in actor else actor,
                is_remote=True,
            )
            db.add(post)

    # Handle Delete
    if activity_type == "Delete":
        target_id = obj.get("id") if isinstance(obj, dict) else obj
        if target_id:
            post = (
                db.query(Post)
                .filter(Post.is_remote == True)
                .filter(Post.id.endswith(target_id.split("/")[-1]))
                .first()
            )
            if post:
                db.delete(post)

    # Handle Follow
    if activity_type == "Follow":
        target_actor_url = obj if isinstance(obj, str) else obj.get("id", "")
        target_username = target_actor_url.rstrip("/").split("/")[-1]
        target_user = db.query(User).filter(User.username == target_username).first()

        if target_user:
            # Check for duplicate
            existing_conn = (
                db.query(Connection)
                .filter(
                    Connection.target_local_user_id == target_user.id,
                    Connection.remote_actor_url == actor,
                )
                .first()
            )

            if not existing_conn:
                # Derive remote inbox URL from actor URL
                remote_inbox_url = actor.rsplit("/", 2)[0] + "/inbox"

                connection = Connection(
                    local_user_id=target_user.id,
                    target_local_user_id=None,
                    remote_actor_url=actor,
                    remote_inbox_url=remote_inbox_url,
                    status="accepted",  # Auto-accept remote follows
                )
                db.add(connection)

            # Send Accept back to the remote actor
            _send_accept(
                local_user=target_user,
                follow_activity=activity,
                remote_actor_url=actor,
            )

    # Handle Accept (remote accepted our follow)
    if activity_type == "Accept":
        accepting_actor = activity["actor"]

        conn = (
            db.query(Connection)
            .filter(
                Connection.remote_actor_url == accepting_actor,
                Connection.status == "pending",
            )
            .first()
        )

        if conn:
            conn.status = "accepted"

    # Handle Undo (e.g., unfollow)
    if activity_type == "Undo" and isinstance(obj, dict) and obj.get("type") == "Follow":
        target_actor_url = obj.get("object", "")
        if isinstance(target_actor_url, str):
            target_username = target_actor_url.rstrip("/").split("/")[-1]
            target_user = db.query(User).filter(User.username == target_username).first()

            if target_user:
                conn = (
                    db.query(Connection)
                    .filter(
                        Connection.target_local_user_id == target_user.id,
                        Connection.remote_actor_url == actor,
                    )
                    .first()
                )
                if conn:
                    db.delete(conn)

    db.commit()
    return {"status": "accepted"}


def _send_accept(local_user: User, follow_activity: dict, remote_actor_url: str):
    """
    Send an Accept activity back to the remote actor's inbox.
    Signed with the local user's private key.
    """
    actor_url = f"{settings.BASE_URL}/users/{local_user.username}"
    key_id = f"{actor_url}#main-key"

    accept_activity = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "type": "Accept",
        "actor": actor_url,
        "object": follow_activity,
    }

    body = json.dumps(accept_activity).encode("utf-8")

    # Determine the remote inbox URL
    remote_inbox = remote_actor_url.rsplit("/", 2)[0] + "/inbox"

    # Fetch the actual inbox from the remote actor if possible
    try:
        resp = httpx.get(
            remote_actor_url,
            headers={"Accept": "application/activity+json"},
            timeout=5,
        )
        if resp.status_code == 200:
            actor_data = resp.json()
            remote_inbox = actor_data.get("inbox", remote_inbox)
    except Exception:
        pass

    if not local_user.private_key:
        return

    try:
        signed_headers = sign_request(
            private_key_pem=local_user.private_key,
            method="POST",
            url=remote_inbox,
            body=body,
            key_id=key_id,
        )

        httpx.post(
            remote_inbox,
            content=body,
            headers=signed_headers,
            timeout=10,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Existing endpoints (kept for backward compatibility)
# ---------------------------------------------------------------------------
@router.post("/inbox/delete")
def delete_remote_post(id: str, db: Session = Depends(get_db)):
    post = db.query(Post).filter(Post.id == id, Post.is_remote == True).first()
    if not post:
        return {"status": "ignored"}

    db.delete(post)
    db.commit()
    return {"status": "deleted"}


@router.post("/users/{username}/outbox")
def outbox(
    username: str,
    activity: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.username != username:
        raise HTTPException(
            status_code=403, detail="Cannot write to another actor's outbox"
        )

    if activity.get("actor") != f"{settings.BASE_URL}/users/{username}":
        raise HTTPException(status_code=400, detail="Actor mismatch")

    new_activity = Activity(
        type=activity.get("type"),
        actor=activity.get("actor"),
        object=activity.get("object"),
        is_local=True,
        is_delivered=False,
    )

    db.add(new_activity)
    db.commit()
    db.refresh(new_activity)

    return {"status": "stored", "activity_id": new_activity.id}
