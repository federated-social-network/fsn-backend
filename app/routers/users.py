from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_
from app.database import get_db
from app.models import User, Post, Connection
from app.dependencies import get_current_user
from app.config import settings
from app.services.federation import build_follow_activity, deliver_raw_activity
from app.routers.federation import _resolve_actor_display_name
from app.services.supabase_client import supabase
from PIL import Image
from io import BytesIO
import uuid

router = APIRouter()


@router.get("/search_users")
def search_users(
    q: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """
    Search for users. Supports:
    - Local prefix search: "alice" → finds local users starting with 'alice'
    - Remote handle lookup: "alice@mastodon.social" → resolves via WebFinger
    """
    if not q or not q.strip():
        return []

    q = q.strip().lstrip("@")

    # --- Remote handle lookup (contains @) ---
    if "@" in q:
        return _search_remote_user(q, user, db)

    # --- Local prefix search ---
    search_pattern = f"{q}%"

    matching_users = (
        db.query(User).filter(User.username.ilike(search_pattern)).limit(10).all()
    )

    if not matching_users:
        return []

    # Get all connected local user IDs for current user (accepted)
    connected_ids = set()
    connections = (
        db.query(Connection)
        .filter(Connection.local_user_id == user.id, Connection.status == "accepted")
        .all()
    )
    for conn in connections:
        if conn.target_local_user_id:
            connected_ids.add(conn.target_local_user_id)

    # Also check reverse direction (someone connected to me, accepted)
    reverse_connections = (
        db.query(Connection)
        .filter(
            Connection.target_local_user_id == user.id,
            Connection.status == "accepted",
        )
        .all()
    )
    for conn in reverse_connections:
        connected_ids.add(conn.local_user_id)

    # Get pending connection target IDs
    pending_ids = set()
    pending_connections = (
        db.query(Connection)
        .filter(Connection.local_user_id == user.id, Connection.status == "pending")
        .all()
    )
    for conn in pending_connections:
        if conn.target_local_user_id:
            pending_ids.add(conn.target_local_user_id)

    results = []
    for u in matching_users:
        if u.id == user.id:
            status = "self"
        elif u.id in connected_ids:
            status = "connected"
        elif u.id in pending_ids:
            status = "pending"
        else:
            status = "none"

        results.append(
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "status": status,
                "is_remote": False,
            }
        )

    return results


def _search_remote_user(handle: str, user, db):
    """
    Resolve a remote user handle via WebFinger and return search results.
    """
    import httpx

    handle = handle.lstrip("@")
    parts = handle.split("@", 1)
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return []

    remote_username, remote_domain = parts

    # Check if we already have a connection to this remote user
    # We need to resolve the actor URL first
    webfinger_url = (
        f"https://{remote_domain}/.well-known/webfinger?resource=acct:{handle}"
    )

    try:
        wf_resp = httpx.get(webfinger_url, timeout=10)
        if wf_resp.status_code != 200:
            return []
        wf_data = wf_resp.json()
    except Exception:
        return []

    # Extract actor URL
    actor_url = None
    for link in wf_data.get("links", []):
        if link.get("rel") == "self" and "activity" in link.get("type", ""):
            actor_url = link["href"]
            break

    if not actor_url:
        return []

    # Fetch actor profile for display info
    display_name = f"{remote_username}@{remote_domain}"
    avatar_url = None
    try:
        actor_resp = httpx.get(
            actor_url,
            headers={"Accept": "application/activity+json"},
            timeout=10,
        )
        if actor_resp.status_code == 200:
            actor_data = actor_resp.json()
            preferred = actor_data.get("preferredUsername", remote_username)
            name = actor_data.get("name", preferred)
            display_name = f"{preferred}@{remote_domain}"

            # Get avatar
            icon = actor_data.get("icon")
            if icon and isinstance(icon, dict):
                avatar_url = icon.get("url")
    except Exception:
        pass

    # Check existing connection status
    existing = (
        db.query(Connection)
        .filter(
            Connection.local_user_id == user.id,
            Connection.remote_actor_url == actor_url,
        )
        .first()
    )

    if existing:
        status = existing.status  # "pending" or "accepted"
    else:
        status = "none"

    return [
        {
            "id": None,
            "username": display_name,
            "email": None,
            "status": status,
            "is_remote": True,
            "actor_url": actor_url,
            "avatar_url": avatar_url,
            "handle": handle,
        }
    ]


@router.get("/get_current_user")
def get_current_user_info(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "email": user.email}


@router.get("/get_user/{username}")
def get_user_profile(
    username: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    db_user = db.query(User).filter(User.username == username).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    posts = (
        db.query(Post)
        .filter(Post.user_id == db_user.id, Post.is_remote == False)
        .order_by(desc(Post.created_at))
        .all()
    )

    return {
        "id": db_user.id,
        "username": db_user.username,
        "email": db_user.email,
        "post_count": len(posts),
        "posts": [
            {
                "id": post.id,
                "content": post.content,
                "image_url": post.image_url,
                "created_at": post.created_at.isoformat(),
                "like_count": post.like_count,
            }
            for post in posts
        ],
        "profile_url": db_user.avatar_url,
    }


@router.get("/random_users")
def random_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # All local user IDs I have ANY connection with (pending or accepted), either direction
    connected_user_ids_outgoing = (
        db.query(Connection.target_local_user_id)
        .filter(
            Connection.local_user_id == user.id,
            Connection.target_local_user_id.isnot(None),
        )
    )

    connected_user_ids_incoming = (
        db.query(Connection.local_user_id)
        .filter(Connection.target_local_user_id == user.id)
    )

    connected_user_ids = connected_user_ids_outgoing.union(
        connected_user_ids_incoming
    ).subquery()

    users = (
        db.query(User)
        .filter(
            User.id != user.id,  # exclude self
            ~User.id.in_(connected_user_ids),
        )
        .order_by(func.random())
        .limit(5)
        .all()
    )

    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "avatar_url": u.avatar_url,
        }
        for u in users
    ]


@router.post("/connect/{username}")
def connect_user(
    username: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    target = db.query(User).filter(User.username == username).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if target.id == user.id:
        raise HTTPException(status_code=400, detail="Cannot connect to yourself")

    # Check if connection already exists in either direction
    existing = (
        db.query(Connection)
        .filter(
            Connection.local_user_id == user.id,
            Connection.target_local_user_id == target.id,
        )
        .first()
    )

    if existing:
        raise HTTPException(status_code=400, detail="Request already sent")

    connection = Connection(
        local_user_id=user.id,
        target_local_user_id=target.id,
        status="pending",
    )

    db.add(connection)
    db.commit()
    db.refresh(connection)

    # Build Follow activity
    target_actor = f"{settings.BASE_URL}/users/{username}"
    follow_activity = build_follow_activity(
        actor_url=f"{settings.BASE_URL}/users/{user.username}",
        target_actor=target_actor,
    )

    # Deliver ONLY if enabled
    if settings.SEND_TO_OTHER_INSTANCE:
        deliver_raw_activity(follow_activity, user=user)

    return {"status": "request_sent", "connection_id": connection.id}


@router.post("/connect/remote")
def connect_remote_user(
    handle: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Follow a remote user (e.g., alice@mastodon.social).
    Resolves via WebFinger, fetches actor profile, sends signed Follow.
    """
    import httpx
    import json
    from urllib.parse import urlparse
    from app.services.crypto import sign_request

    # Parse handle: "alice@mastodon.social" or "@alice@mastodon.social"
    handle = handle.lstrip("@")
    if "@" not in handle:
        raise HTTPException(
            status_code=400,
            detail="Invalid handle. Use format: username@domain.com",
        )

    remote_username, remote_domain = handle.split("@", 1)

    # Step 1: WebFinger lookup
    webfinger_url = f"https://{remote_domain}/.well-known/webfinger?resource=acct:{handle}"
    try:
        wf_resp = httpx.get(webfinger_url, timeout=10)
        if wf_resp.status_code != 200:
            raise HTTPException(
                status_code=404,
                detail=f"Could not find user {handle} via WebFinger",
            )
        wf_data = wf_resp.json()
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail=f"Could not reach {remote_domain}",
        )

    # Extract actor URL from WebFinger links
    actor_url = None
    for link in wf_data.get("links", []):
        if link.get("rel") == "self" and "activity" in link.get("type", ""):
            actor_url = link["href"]
            break

    if not actor_url:
        raise HTTPException(status_code=404, detail="Actor URL not found in WebFinger")

    # Step 2: Fetch actor profile for inbox URL
    try:
        actor_resp = httpx.get(
            actor_url,
            headers={"Accept": "application/activity+json"},
            timeout=10,
        )
        if actor_resp.status_code != 200:
            raise HTTPException(
                status_code=404,
                detail="Could not fetch remote actor profile",
            )
        actor_data = actor_resp.json()
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Could not reach remote actor",
        )

    remote_inbox = actor_data.get("inbox")
    if not remote_inbox:
        raise HTTPException(status_code=400, detail="Remote actor has no inbox")

    # Step 3: Check for duplicate connection
    existing = (
        db.query(Connection)
        .filter(
            Connection.local_user_id == user.id,
            Connection.remote_actor_url == actor_url,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Already following this user")

    # Step 4: Create connection
    connection = Connection(
        local_user_id=user.id,
        target_local_user_id=None,
        remote_actor_url=actor_url,
        remote_inbox_url=remote_inbox,
        status="pending",
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)

    # Step 5: Send signed Follow activity to remote inbox
    my_actor_url = f"{settings.BASE_URL}/users/{user.username}"
    follow_activity = {
        "@context": "https://www.w3.org/ns/activitystreams",
        "id": f"{my_actor_url}/follows/{connection.id}",
        "type": "Follow",
        "actor": my_actor_url,
        "object": actor_url,
    }

    if user.private_key:
        try:
            body = json.dumps(follow_activity).encode("utf-8")
            key_id = f"{my_actor_url}#main-key"
            signed_headers = sign_request(
                private_key_pem=user.private_key,
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
            pass  # Best-effort delivery

    return {
        "status": "follow_sent",
        "connection_id": connection.id,
        "remote_actor": actor_url,
        "remote_username": f"{remote_username}@{remote_domain}",
    }


@router.post("/connect/accept/{connection_id}")
def accept_connection(
    connection_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    connection = (
        db.query(Connection)
        .filter(Connection.id == connection_id, Connection.status == "pending")
        .first()
    )

    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    # Check authorization: user must be the target of this follow request
    is_local_target = connection.target_local_user_id == user.id
    is_remote_follow_target = (
        connection.remote_actor_url is not None
        and connection.local_user_id == user.id
    )

    if not is_local_target and not is_remote_follow_target:
        raise HTTPException(status_code=403, detail="Not allowed")

    # Mark as accepted
    connection.status = "accepted"

    if is_local_target:
        # Local-to-local: create mirror connection
        mirror = Connection(
            local_user_id=user.id,
            target_local_user_id=connection.local_user_id,
            status="accepted",
        )
        db.add(mirror)
    elif is_remote_follow_target:
        # Remote follow: send Accept activity back to the remote actor
        import json
        from app.services.crypto import sign_request

        actor_url = f"{settings.BASE_URL}/users/{user.username}"
        follow_activity = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "type": "Follow",
            "actor": connection.remote_actor_url,
            "object": actor_url,
        }
        accept_activity = {
            "@context": "https://www.w3.org/ns/activitystreams",
            "type": "Accept",
            "actor": actor_url,
            "object": follow_activity,
        }

        remote_inbox = connection.remote_inbox_url
        if remote_inbox and user.private_key:
            try:
                body = json.dumps(accept_activity).encode("utf-8")
                key_id = f"{actor_url}#main-key"
                import httpx
                signed_headers = sign_request(
                    private_key_pem=user.private_key,
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
                pass  # Best-effort delivery

    db.commit()

    return {"status": "connected"}


@router.get("/connections/pending")
def pending_connections(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    # Find pending connections where I am the target:
    # 1. Local-to-local: target_local_user_id == my id
    # 2. Remote-to-local: local_user_id == my id AND remote_actor_url is not null
    pending = (
        db.query(Connection)
        .filter(
            Connection.status == "pending",
            or_(
                # Local follow requests targeting me
                Connection.target_local_user_id == user.id,
                # Remote follow requests targeting me
                (
                    (Connection.local_user_id == user.id)
                    & (Connection.remote_actor_url.isnot(None))
                ),
            ),
        )
        .all()
    )

    results = []

    for conn in pending:
        if conn.remote_actor_url:
            # Remote follow — resolve friendly display name from actor profile
            display_name = _resolve_actor_display_name(conn.remote_actor_url)

            results.append(
                {
                    "connection_id": conn.id,
                    "from_user_id": None,
                    "from_username": display_name,
                    "is_remote": True,
                }
            )
        elif conn.local_user_id:
            # Local follow request
            requester = db.query(User).filter(User.id == conn.local_user_id).first()
            if requester:
                results.append(
                    {
                        "connection_id": conn.id,
                        "from_user_id": requester.id,
                        "from_username": requester.username,
                        "is_remote": False,
                    }
                )

    return results


@router.get("/count_connections")
def count_connections(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    # Count accepted connections where I am the local_user_id
    count = (
        db.query(Connection)
        .filter(
            Connection.local_user_id == user.id,
            Connection.status == "accepted",
        )
        .count()
    )

    return {"connection_count": count}


@router.get("/list_connections")
def list_connections(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    # Get accepted connections where I am the local_user_id
    connections = (
        db.query(Connection)
        .filter(
            Connection.local_user_id == user.id,
            Connection.status == "accepted",
        )
        .all()
    )

    results = []

    for conn in connections:
        if conn.target_local_user_id:
            # Local connection — look up the user
            target = (
                db.query(User).filter(User.id == conn.target_local_user_id).first()
            )
            if target:
                results.append(
                    {
                        "user_id": target.id,
                        "username": target.username,
                        "is_remote": False,
                    }
                )
        elif conn.remote_actor_url:
            # Remote connection — resolve friendly username@domain from actor profile
            display_name = _resolve_actor_display_name(conn.remote_actor_url)
            results.append(
                {
                    "user_id": None,
                    "username": display_name,
                    "is_remote": True,
                }
            )

    return results


@router.post("/remove_connection/{username:path}")
def remove_connection(
    username: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    # Check if this is a remote user handle (contains @)
    if "@" in username:
        # Remote user — find the connection by matching remote_actor_url
        remote_connections = (
            db.query(Connection)
            .filter(
                Connection.local_user_id == user.id,
                Connection.remote_actor_url.isnot(None),
                Connection.status == "accepted",
            )
            .all()
        )

        conn_to_remove = None
        for conn in remote_connections:
            display_name = _resolve_actor_display_name(conn.remote_actor_url)
            if display_name == username:
                conn_to_remove = conn
                break

        if not conn_to_remove:
            raise HTTPException(status_code=400, detail="Not connected to this user")

        # Delete remote posts from this user (match by post ID prefix)
        actor_url = conn_to_remove.remote_actor_url
        db.query(Post).filter(
            Post.is_remote == True,
            Post.id.like(f"{actor_url}%"),
        ).delete(synchronize_session=False)

        db.delete(conn_to_remove)
        db.commit()
        return {"status": "connection_removed"}

    # Local user
    target_user = db.query(User).filter(User.username == username).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Remove my request to target
    conn1 = (
        db.query(Connection)
        .filter(
            Connection.local_user_id == user.id,
            Connection.target_local_user_id == target_user.id,
            Connection.status == "accepted",
        )
        .first()
    )

    # Remove target's request to me (mirror)
    conn2 = (
        db.query(Connection)
        .filter(
            Connection.local_user_id == target_user.id,
            Connection.target_local_user_id == user.id,
            Connection.status == "accepted",
        )
        .first()
    )

    if not conn1 and not conn2:
        raise HTTPException(status_code=400, detail="Not connected to this user")

    if conn1:
        db.delete(conn1)
    if conn2:
        db.delete(conn2)

    db.commit()

    return {"status": "connection_removed"}


ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"]
MAX_SIZE = 2 * 1024 * 1024  # 2MB


@router.post("/users/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Validate type
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail="Invalid file type")

    contents = await file.read()

    # Validate size
    if len(contents) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File too large")

    # Validate actual image
    try:
        Image.open(BytesIO(contents)).verify()
    except:
        raise HTTPException(status_code=400, detail="Invalid image")

    filename = f"{uuid.uuid4()}.jpg"

    # Upload to Supabase
    supabase.storage.from_("avatars").upload(
        filename, contents, {"content-type": file.content_type}
    )

    public_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/avatars/{filename}"

    # Save to DB
    user.avatar_url = public_url
    db.commit()

    return {"avatar_url": public_url}
