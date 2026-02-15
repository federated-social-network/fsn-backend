from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel,  Field
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.database import get_db
from app.models import User, Post, Connection
from app.dependencies import get_current_user
from app.config import settings
from app.services.federation import build_follow_activity, deliver_raw_activity

router = APIRouter()

@router.get("/search_users")
def search_users(
    q: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
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
        db.query(User)
        .filter(User.username.ilike(search_pattern))
        .limit(10)
        .all()
    )
    
    if not matching_users:
        return []
    
    my_actor = f"{settings.BASE_URL}/users/{user.username}"
    
    # Get all connected actors for current user
    connected_actors = set()
    connections = db.query(Connection).filter(
        Connection.requester_id == user.id,
        Connection.status == "accepted"
    ).all()
    for conn in connections:
        connected_actors.add(conn.target_actor)
    
    # Get pending connection actors
    pending_actors = set()
    pending_connections = db.query(Connection).filter(
        Connection.requester_id == user.id,
        Connection.status == "pending"
    ).all()
    for conn in pending_connections:
        pending_actors.add(conn.target_actor)
    
    results = []
    for u in matching_users:
        user_actor = f"{settings.BASE_URL}/users/{u.username}"
        
        if u.id == user.id:
            status = "self"
        elif user_actor in connected_actors:
            status = "connected"
        elif user_actor in pending_actors:
            status = "pending"
        else:
            status = "none"
        
        results.append({
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "status": status
        })
    
    return results

@router.get("/get_current_user")
def get_current_user_info(user: User = Depends(get_current_user)):
    return {"id": user.id, "username": user.username, "email": user.email}

@router.get("/get_user/{username}")
def get_user_profile(
    username: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_user = db.query(User).filter(User.username == username).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    posts = (
        db.query(Post)
        .filter(
            Post.user_id == db_user.id,
            Post.is_remote == False
        )
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
                "created_at": post.created_at.isoformat()
            }
            for post in posts
        ]
    }

@router.get("/random_users")
def random_users(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    my_actor = f"{settings.BASE_URL}/users/{user.username}"

    # All actors I have ANY connection with (pending or accepted)
    connected_actors = (
        db.query(Connection.target_actor)
        .filter(Connection.requester_id == user.id)
        .union(
            db.query(
                func.concat(
                    settings.BASE_URL,
                    "/users/",
                    User.username
                )
            )
            .join(Connection, Connection.requester_id == User.id)
            .filter(Connection.target_actor == my_actor)
        )
        .subquery()
    )

    users = (
        db.query(User)
        .filter(
            User.id != user.id,  # exclude self
            ~func.concat(
                settings.BASE_URL,
                "/users/",
                User.username
            ).in_(connected_actors)
        )
        .order_by(func.random())
        .limit(5)
        .all()
    )

    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email
        }
        for u in users
    ]

@router.post("/connect/{username}")
def connect_user(
    username: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target = db.query(User).filter(User.username == username).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    if target.id == user.id:
        raise HTTPException(status_code=400, detail="Cannot connect to yourself")

    target_actor = f"{settings.BASE_URL}/users/{username}"

    existing = db.query(Connection).filter(
        Connection.requester_id == user.id,
        Connection.target_actor == target_actor
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Request already sent")

    connection = Connection(
        requester_id=user.id,
        target_actor=target_actor,
        status="pending"
    )

    db.add(connection)
    db.commit()
    db.refresh(connection)

    # 🔹 Build Follow activity
    follow_activity = build_follow_activity(
        actor_url=f"{settings.BASE_URL}/users/{user.username}",
        target_actor=target_actor
    )

    # 🔹 Deliver ONLY if enabled
    if settings.SEND_TO_OTHER_INSTANCE:
        deliver_raw_activity(follow_activity)

    return {"status": "request_sent","connection_id":connection.id}



@router.post("/connect/accept/{connection_id}")
def accept_connection(
    connection_id: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    connection = db.query(Connection).filter(
        Connection.id == connection_id,
        Connection.status == "pending"
    ).first()

    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")

    my_actor = f"{settings.BASE_URL}/users/{user.username}"

    # Ensure the logged-in user is the target
    if connection.target_actor != my_actor:
        raise HTTPException(status_code=403, detail="Not allowed")

    # 1️⃣ Mark original request as accepted
    connection.status = "accepted"

    # 2️⃣ Create mirror connection (THIS IS THE FIX)
    mirror = Connection(
        requester_id = user.id,
        target_actor = f"{settings.BASE_URL}/users/" + (
            db.query(User)
            .filter(User.id == connection.requester_id)
            .first()
            .username
        ),
        status = "accepted"
    )

    db.add(mirror)
    db.commit()

    return {"status": "connected"}

@router.get("/connections/pending")
def pending_connections(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    my_actor = f"{settings.BASE_URL}/users/{user.username}"

    pending = db.query(Connection).filter(
        Connection.target_actor == my_actor,
        Connection.status == "pending"
    ).all()

    results = []

    for conn in pending:
        requester = db.query(User).filter(
            User.id == conn.requester_id
        ).first()

        if requester:
            results.append({
                "connection_id": conn.id,
                "from_user_id": requester.id,
                "from_username": requester.username
            })

    return results

@router.get("/count_connections")
def count_connections(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    my_actor = f"{settings.BASE_URL}/users/{user.username}"

    count = db.query(Connection).filter(
        Connection.target_actor == my_actor,
        Connection.status == "accepted"
    ).count()

    return {"connection_count": count}

@router.get("/list_connections")
def list_connections(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    my_actor = f"{settings.BASE_URL}/users/{user.username}"

    connections = db.query(Connection).filter(
        Connection.target_actor == my_actor,
        Connection.status == "accepted"
    ).all()

    results = []

    for conn in connections:
        requester = db.query(User).filter(
            User.id == conn.requester_id
        ).first()

        if requester:
            results.append({
                "user_id": requester.id,
                "username": requester.username
            })

    return results

@router.post("/remove_connection/{username}")
def remove_connection(
    username: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    target_user = db.query(User).filter(User.username == username).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    target_actor = f"{settings.BASE_URL}/users/{username}"
    my_actor = f"{settings.BASE_URL}/users/{user.username}"

    # Remove my request to target
    conn1 = db.query(Connection).filter(
        Connection.requester_id == user.id,
        Connection.target_actor == target_actor,
        Connection.status == "accepted"
    ).first()

    # Remove target's request to me
    conn2 = db.query(Connection).filter(
        Connection.requester_id == target_user.id,
        Connection.target_actor == my_actor,
        Connection.status == "accepted"
    ).first()

    if not conn1 and not conn2:
        raise HTTPException(status_code=400, detail="Not connected to this user")
    
    if conn1:
        db.delete(conn1)
    if conn2:
        db.delete(conn2)

    db.commit()

    return {"status": "connection_removed"}

class ProfileUpdate(BaseModel):
    # 'username' maps to 'displayName' conceptually for now, per user request
    # but the DB field is 'username'.
    username: str | None = Field(None, min_length=3, max_length=50)
    email: str | None = None

@router.put("/update_profile")
def update_profile(
    profile_update: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Update Username if provided and different
    if profile_update.username and profile_update.username != user.username:
        # Check uniqueness
        existing_user = db.query(User).filter(User.username == profile_update.username).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="Username already taken")
        old_username = user.username
        new_username = profile_update.username
        
        old_actor = f"{settings.BASE_URL}/users/{old_username}"
        new_actor = f"{settings.BASE_URL}/users/{new_username}"

        # Update User
        user.username = new_username

        # Cascade Update 1: Fix 'target_actor' in Connections (where others follow me)
        db.query(Connection).filter(
            Connection.target_actor == old_actor
        ).update(
            {"target_actor": new_actor},
            synchronize_session=False
        )

        # Cascade Update 2: Fix 'author' in Posts
        db.query(Post).filter(
            Post.author == old_username
        ).update(
            {"author": new_username},
            synchronize_session=False
        )

    # 2. Update Email if provided and different
    if profile_update.email and profile_update.email != user.email:
        # Optional: Check email uniqueness if that's a requirement (not explicitly stated but good practice)
        # For now, let's assume we just update it.
        user.email = profile_update.email

    db.commit()
    db.refresh(user)

    return {
        "id": user.id,
        "username": user.username,
        "email": user.email
    }
