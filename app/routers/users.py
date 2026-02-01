from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.database import get_db
from app.models import User, Post, Connection
from app.dependencies import get_current_user
from app.config import settings
from app.services.federation import build_follow_activity, deliver_raw_activity

router = APIRouter()

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