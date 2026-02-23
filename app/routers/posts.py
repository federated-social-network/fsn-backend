from sqlalchemy import desc
import uuid
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Post, User, Activity, Connection, Like
from app.dependencies import get_current_user
from app.config import settings
from app.services.federation import (
    build_create_activity,
    build_delete_activity,
    deliver_activity,
)
from app.services.supabase_client import supabase
from PIL import Image
from io import BytesIO

router = APIRouter()


@router.post("/posts")
async def create_post(
    content: str,
    image: UploadFile = File(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    image_url = None

    if image:
        contents = await image.read()

        # Validate actual image
        try:
            Image.open(BytesIO(contents)).verify()
        except:
            raise HTTPException(status_code=400, detail="Invalid image")

        filename = f"{uuid.uuid4()}.jpg"

        # Upload to Supabase
        supabase.storage.from_("posts").upload(
            filename, contents, {"content-type": image.content_type}
        )

        image_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/posts/{filename}"

    post = Post(
        id=str(uuid.uuid4()),
        content=content,
        image_url=image_url,
        user_id=user.id,
        author=user.username,
        origin_instance=settings.INSTANCE_NAME,
        is_remote=False,
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
        is_delivered=False,
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
    results = (
        db.query(Post, User)
        .join(User, Post.user_id == User.id)
        .order_by(Post.created_at.desc())
        .all()
    )

    return [
        {
            "id": post.id,
            "content": post.content,
            "created_at": post.created_at,
            "author": user.username,
            "image_url": post.image_url,
            "avatar_url": user.avatar_url,
            "like_count": post.like_count,
        }
        for post, user in results
    ]


@router.get("/timeline_connected_users")
def timeline_connected_users(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    # Get accepted connections
    connections = (
        db.query(Connection)
        .filter(Connection.requester_id == user.id, Connection.status == "accepted")
        .all()
    )

    connected_usernames = [
        c.target_actor.rstrip("/").split("/")[-1] for c in connections
    ]

    if not connected_usernames:
        return []

    # Manual JOIN
    results = (
        db.query(Post, User)
        .join(User, Post.user_id == User.id)
        .filter(Post.author.in_(connected_usernames))
        .order_by(desc(Post.created_at))
        .all()
    )

    return [
        {
            "id": post.id,
            "content": post.content,
            "author": user.username,
            "avatar_url": user.avatar_url,
            "image_url": post.image_url,
            "created_at": post.created_at,
            "like_count": post.like_count,
        }
        for post, user in results
    ]


@router.delete("/delete/{post_id}")
def delete_post(
    post_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.is_remote:
        raise HTTPException(status_code=403, detail="Cannot delete remote post")
    if post.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not allowed")

    activity_payload = build_delete_activity(post, settings.BASE_URL)
    activity = Activity(
        type="Delete",
        actor=activity_payload["actor"],
        object=activity_payload["object"],
        is_local=True,
        is_delivered=False,
    )
    db.add(activity)
    db.delete(post)
    db.commit()
    deliver_activity(activity)
    return {"status": "deleted"}


@router.post("/posts/{post_id}/like")
def like_post(
    post_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    existing = (
        db.query(Like).filter(Like.user_id == user.id, Like.post_id == post_id).first()
    )

    if existing:
        raise HTTPException(status_code=400, detail="Already liked")

    like = Like(id=str(uuid.uuid4()), user_id=user.id, post_id=post_id)

    db.add(like)
    post.like_count += 1

    db.commit()

    return {"message": "Liked"}


@router.delete("/posts/{post_id}/like")
def unlike_post(
    post_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    like = (
        db.query(Like).filter(Like.user_id == user.id, Like.post_id == post_id).first()
    )

    if not like:
        raise HTTPException(status_code=404, detail="Like not found")

    post = db.query(Post).filter(Post.id == post_id).first()

    db.delete(like)
    post.like_count = max(0, post.like_count - 1)

    db.commit()

    return {"message": "Unliked"}
