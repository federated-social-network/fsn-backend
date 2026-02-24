from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, or_
from app.database import get_db
from app.models import User, Post, Connection
from app.dependencies import get_current_user
from app.config import settings
from app.services.federation import build_follow_activity, deliver_raw_activity
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
    Fast prefix-based user search using SQL ILIKE.
    Returns users whose username starts with the query string (case-insensitive).
    Includes connection status and self-detection.
    """
    if not q or not q.strip():
        return []

    search_pattern = f"{q.strip()}%"

    # Get matching users using ILIKE for case-insensitive prefix search
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
            {"id": u.id, "username": u.username, "email": u.email, "status": status}
        )

    return results


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

    # Ensure the logged-in user is the target of this connection request
    if connection.target_local_user_id != user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    # Mark original request as accepted
    connection.status = "accepted"

    # Create mirror connection (so both users see each other as connected)
    mirror = Connection(
        local_user_id=user.id,
        target_local_user_id=connection.local_user_id,
        status="accepted",
    )

    db.add(mirror)
    db.commit()

    return {"status": "connected"}


@router.get("/connections/pending")
def pending_connections(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    # Find connections where I am the target and status is pending
    pending = (
        db.query(Connection)
        .filter(
            Connection.target_local_user_id == user.id,
            Connection.status == "pending",
        )
        .all()
    )

    results = []

    for conn in pending:
        # For local connections, look up the requester
        if conn.local_user_id:
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
        # For remote connections (follow from remote instance)
        elif conn.remote_actor_url:
            results.append(
                {
                    "connection_id": conn.id,
                    "from_user_id": None,
                    "from_username": conn.remote_actor_url,
                    "is_remote": True,
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
            # Remote connection
            results.append(
                {
                    "user_id": None,
                    "username": conn.remote_actor_url,
                    "is_remote": True,
                }
            )

    return results


@router.post("/remove_connection/{username}")
def remove_connection(
    username: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
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
