import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.database import get_db
from app.models import Post, User, Activity, Connection
from app.dependencies import get_current_user
from app.config import settings
from app.services.federation import build_create_activity, build_delete_activity, deliver_activity

router = APIRouter()

@router.post("/posts")
def create_post(content: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    post = Post(
        id=str(uuid.uuid4()),
        content=content,
        user_id=user.id,
        author=user.username,
        origin_instance=settings.INSTANCE_NAME,
        is_remote=False
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    activity_payload = build_create_activity(post, settings.BASE_URL)
    activity = Activity(
        type="Create",
        actor=activity_payload["actor"],
        object=activity_payload["object"],
        is_local=True,
        is_delivered=False
    )
    db.add(activity)
    db.commit()
    
    deliver_activity(activity)
    return post

@router.get("/get_posts")
def get_posts(db: Session = Depends(get_db)):
    return db.query(Post).order_by(Post.id.desc()).all()

@router.get("/timeline")
def timeline(db: Session = Depends(get_db)):
    posts = db.query(Post).order_by(Post.created_at.desc()).all()
    # ... logic to format response ...
    return posts

@router.get("/timeline_connected_users")
def timeline_connected_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    connections = db.query(Connection).filter(
        Connection.requester_id == user.id,
        Connection.status == "accepted"
    ).all()

    connected_usernames = [c.target_actor.rstrip("/").split("/")[-1] for c in connections]
    
    posts = db.query(Post).filter(Post.author.in_(connected_usernames)).order_by(desc(Post.created_at)).all()
    
    return [{"id": p.id, "content": p.content, "author": p.author, "created_at": p.created_at} for p in posts]

@router.delete("/delete/{post_id}")
def delete_post(post_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.is_remote:
        raise HTTPException(status_code=403, detail="Cannot delete remote post")
    if post.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    activity_payload = build_delete_activity(post, settings.BASE_URL)
    activity = Activity(
        type="Delete", actor=activity_payload["actor"], object=activity_payload["object"],
        is_local=True, is_delivered=False
    )
    db.add(activity)
    db.delete(post)
    db.commit()
    deliver_activity(activity)
    return {"status": "deleted"}