import json
import re
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Post, Activity, Connection, User
from app.dependencies import get_current_user
from app.config import settings
from app.services.crypto import sign_request, verify_http_signature
from urllib.parse import urlparse
from starlette.requests import ClientDisconnect



def _strip_html(html: str) -> str:
    """Strip HTML tags from content, keeping only text."""
    if not html:
        return html
    # Remove HTML tags
    text = re.sub(r'<br\s*/?>', '\n', html)  # Convert <br> to newline
    text = re.sub(r'</p>\s*<p>', '\n\n', text)  # Convert paragraph breaks
    text = re.sub(r'<[^>]+>', '', text)  # Remove all remaining tags
    text = text.strip()
    return text


def _resolve_actor_display_name(actor_url: str) -> str:
    """Fetch preferredUsername from actor profile and return username@domain."""
    try:
        parsed = urlparse(actor_url)
        domain = parsed.hostname

        resp = httpx.get(
            actor_url,
            headers={"Accept": "application/activity+json"},
            timeout=5,
        )
        if resp.status_code == 200:
            actor_data = resp.json()
            preferred = actor_data.get("preferredUsername")
            if preferred:
                return f"{preferred}@{domain}"
    except Exception:
        pass

    # Fallback: extract from URL
    try:
        parsed = urlparse(actor_url)
        path_username = actor_url.rstrip("/").split("/")[-1]
        return f"{path_username}@{parsed.hostname}"
    except Exception:
        return actor_url

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

    try:
        body = await request.body()
    except ClientDisconnect:
        # Remote instance disconnected early
        return Response(status_code=400)

    if not body:
        raise HTTPException(status_code=400, detail="Empty body")

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
        content = _strip_html(obj.get("content", ""))
        image_url = obj.get("image_url")

        # Check for image in attachment array (Mastodon format)
        if not image_url and obj.get("attachment"):
            for att in obj["attachment"]:
                if att.get("type") in ("Image", "Document"):
                    image_url = att.get("url")
                    break

        # Resolve friendly author name (preferredUsername@domain)
        author_display = _resolve_actor_display_name(actor)

        existing = db.query(Post).filter(Post.id == post_id).first()
        if not existing:
            post = Post(
                id=post_id,
                content=content,
                image_url=image_url,
                user_id=None,
                author=author_display,
                origin_instance=actor.split("/users/")[0] if "/users/" in actor else actor,
                is_remote=True,
                visibility="public",
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
                    Connection.local_user_id == target_user.id,
                    Connection.remote_actor_url == actor,
                )
                .first()
            )

            if not existing_conn:
                # Derive remote inbox URL from actor URL
                remote_inbox_url = actor.rsplit("/", 2)[0] + "/inbox"

                # Try to get actual inbox from actor object
                try:
                    resp = httpx.get(
                        actor,
                        headers={"Accept": "application/activity+json"},
                        timeout=5,
                    )
                    if resp.status_code == 200:
                        actor_data = resp.json()
                        remote_inbox_url = actor_data.get("inbox", remote_inbox_url)
                except Exception:
                    pass

                connection = Connection(
                    local_user_id=target_user.id,
                    target_local_user_id=None,
                    remote_actor_url=actor,
                    remote_inbox_url=remote_inbox_url,
                    status="pending",  # Show in pending list, user must accept
                )
                db.add(connection)

                # Store the original Follow activity JSON on the connection
                # so we can wrap it in Accept later
                connection._follow_activity = activity

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
            db.commit()
            # Fetch existing posts from the remote user's outbox
            _fetch_remote_outbox_posts(accepting_actor, db)

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
                        Connection.local_user_id == target_user.id,
                        Connection.remote_actor_url == actor,
                    )
                    .first()
                )
                if conn:
                    # Delete remote posts from this actor (match by post ID prefix)
                    db.query(Post).filter(
                        Post.is_remote == True,
                        Post.id.like(f"{actor}%"),
                    ).delete(synchronize_session=False)
                    db.delete(conn)

    db.commit()
    return {"status": "accepted"}


# ---------------------------------------------------------------------------
# Fetch remote outbox posts
# ---------------------------------------------------------------------------
def _fetch_remote_outbox_posts(actor_url: str, db: Session):
    """
    Fetch existing posts from a remote actor's outbox and store them locally.
    This is called when a follow is accepted so user sees existing posts.
    """
    try:
        # Fetch actor profile to get outbox URL and preferredUsername
        actor_resp = httpx.get(
            actor_url,
            headers={"Accept": "application/activity+json"},
            timeout=10,
        )
        if actor_resp.status_code != 200:
            return

        actor_data = actor_resp.json()
        outbox_url = actor_data.get("outbox")
        if not outbox_url:
            return

        # Build friendly author name from actor profile
        parsed = urlparse(actor_url)
        domain = parsed.hostname
        preferred = actor_data.get("preferredUsername", "")
        if preferred:
            author_display = f"{preferred}@{domain}"
        else:
            path_name = actor_url.rstrip("/").split("/")[-1]
            author_display = f"{path_name}@{domain}"

        # Fetch outbox collection
        outbox_resp = httpx.get(
            outbox_url,
            headers={"Accept": "application/activity+json"},
            timeout=10,
        )
        if outbox_resp.status_code != 200:
            return

        outbox_data = outbox_resp.json()

        # Handle OrderedCollection — get first page
        items = outbox_data.get("orderedItems", [])
        if not items and outbox_data.get("first"):
            first_url = outbox_data["first"]
            if isinstance(first_url, str):
                page_resp = httpx.get(
                    first_url,
                    headers={"Accept": "application/activity+json"},
                    timeout=10,
                )
                if page_resp.status_code == 200:
                    page_data = page_resp.json()
                    items = page_data.get("orderedItems", [])

        # Process items (limit to 20 most recent)
        for item in items[:20]:
            try:
                activity_obj = item
                if isinstance(item, str):
                    continue

                item_type = activity_obj.get("type", "")

                # Handle both wrapped (Create) and unwrapped (Note) activities
                if item_type == "Create":
                    note = activity_obj.get("object", {})
                elif item_type == "Note":
                    note = activity_obj
                else:
                    continue

                if not isinstance(note, dict) or note.get("type") != "Note":
                    continue

                post_id = note.get("id")
                content = _strip_html(note.get("content", ""))

                if not post_id or not content:
                    continue

                # Skip if already exists
                existing = db.query(Post).filter(Post.id == post_id).first()
                if existing:
                    continue

                # Extract image from attachments
                image_url = None
                for att in note.get("attachment", []):
                    if att.get("type") in ("Image", "Document"):
                        image_url = att.get("url")
                        break

                post = Post(
                    id=post_id,
                    content=content,
                    image_url=image_url,
                    user_id=None,
                    author=author_display,
                    origin_instance=actor_url.split("/users/")[0] if "/users/" in actor_url else actor_url,
                    is_remote=True,
                    visibility="public",
                )
                db.add(post)

            except Exception:
                continue

        db.commit()

    except Exception:
        pass


# ---------------------------------------------------------------------------
# Debug: show connection statuses
# ---------------------------------------------------------------------------
@router.get("/debug/connections")
def debug_connections(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Debug endpoint to view all connections and their statuses."""
    connections = (
        db.query(Connection)
        .filter(Connection.local_user_id == user.id)
        .all()
    )

    return [
        {
            "id": conn.id,
            "local_user_id": conn.local_user_id,
            "target_local_user_id": conn.target_local_user_id,
            "remote_actor_url": conn.remote_actor_url,
            "remote_inbox_url": conn.remote_inbox_url,
            "status": conn.status,
            "created_at": str(conn.created_at) if conn.created_at else None,
        }
        for conn in connections
    ]


# ---------------------------------------------------------------------------
# Sync: manually pull posts from followed remote users
# ---------------------------------------------------------------------------
@router.post("/sync/remote_posts")
def sync_remote_posts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Manually sync posts from all followed remote users.
    Fetches their outbox and stores any new posts.
    """
    connections = (
        db.query(Connection)
        .filter(
            Connection.local_user_id == user.id,
            Connection.remote_actor_url.isnot(None),
            Connection.status.in_(["accepted", "pending"]),
        )
        .all()
    )

    synced = 0
    for conn in connections:
        before_count = db.query(Post).filter(
            Post.is_remote == True,
            Post.author == conn.remote_actor_url,
        ).count()

        _fetch_remote_outbox_posts(conn.remote_actor_url, db)

        after_count = db.query(Post).filter(
            Post.is_remote == True,
            Post.author == conn.remote_actor_url,
        ).count()

        synced += (after_count - before_count)

    return {
        "status": "synced",
        "remote_connections": len(connections),
        "new_posts_fetched": synced,
    }


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
# Helper: extract friendly display name from actor URL
# ---------------------------------------------------------------------------
def _get_friendly_actor_name(actor_url: str) -> str:
    """
    Given an actor URL like 'https://mastodon.social/users/alice',
    return a friendly display name like 'alice@mastodon.social'.
    Tries to fetch the actor profile first for the preferredUsername.
    """
    try:
        parsed = urlparse(actor_url)
        domain = parsed.hostname

        # Try to fetch actor JSON for preferredUsername
        resp = httpx.get(
            actor_url,
            headers={"Accept": "application/activity+json"},
            timeout=5,
        )
        if resp.status_code == 200:
            actor_data = resp.json()
            preferred = actor_data.get("preferredUsername")
            if preferred:
                return f"{preferred}@{domain}"
    except Exception:
        pass

    # Fallback: extract from URL path
    try:
        parsed = urlparse(actor_url)
        path_username = actor_url.rstrip("/").split("/")[-1]
        return f"{path_username}@{parsed.hostname}"
    except Exception:
        return actor_url


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


# ---------------------------------------------------------------------------
# Outbox endpoint (GET) — returns post count and posts for Mastodon
# ---------------------------------------------------------------------------
@router.get("/users/{username}/outbox")
def get_outbox(username: str, page: bool = False, db: Session = Depends(get_db)):
    """
    ActivityPub Outbox endpoint (GET).
    Returns an OrderedCollection with the user's post count.
    Mastodon fetches this to display the post count on profiles.
    """
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    actor_url = f"{settings.BASE_URL}/users/{username}"
    outbox_url = f"{actor_url}/outbox"

    # Count only local posts by this user
    post_count = (
        db.query(Post)
        .filter(Post.user_id == user.id, Post.is_remote == False)
        .count()
    )

    if not page:
        return JSONResponse(
            content={
                "@context": "https://www.w3.org/ns/activitystreams",
                "id": outbox_url,
                "type": "OrderedCollection",
                "totalItems": post_count,
                "first": f"{outbox_url}?page=true",
                "last": f"{outbox_url}?page=true",
            },
            media_type="application/activity+json",
        )

    # Return the first page with actual posts
    from sqlalchemy import desc
    posts = (
        db.query(Post)
        .filter(Post.user_id == user.id, Post.is_remote == False)
        .order_by(desc(Post.created_at))
        .limit(20)
        .all()
    )

    items = []
    for post in posts:
        note = {
            "type": "Note",
            "id": f"{settings.BASE_URL}/posts/{post.id}",
            "content": post.content,
            "attributedTo": actor_url,
            "published": post.created_at.isoformat() if post.created_at else None,
            "to": ["https://www.w3.org/ns/activitystreams#Public"],
        }
        if post.image_url:
            note["attachment"] = [{
                "type": "Image",
                "mediaType": "image/jpeg",
                "url": post.image_url,
            }]

        items.append({
            "type": "Create",
            "actor": actor_url,
            "published": post.created_at.isoformat() if post.created_at else None,
            "object": note,
        })

    return JSONResponse(
        content={
            "@context": "https://www.w3.org/ns/activitystreams",
            "id": f"{outbox_url}?page=true",
            "type": "OrderedCollectionPage",
            "partOf": outbox_url,
            "totalItems": post_count,
            "orderedItems": items,
        },
        media_type="application/activity+json",
    )


# ---------------------------------------------------------------------------
# Outbox endpoint (POST) — store local activities
# ---------------------------------------------------------------------------
@router.post("/users/{username}/outbox")
def post_outbox(
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

