from sqlalchemy import and_, desc, or_
from urllib.parse import urlparse
import uuid
from fastapi import APIRouter, Depends, HTTPException, File, Form, UploadFile
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
    content: str = Form(...),
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

    deliver_activity(activity, user=user, db=db)
    return post


@router.get("/get_posts")
def get_posts(db: Session = Depends(get_db)):
    return db.query(Post).order_by(Post.id.desc()).all()


@router.get("/timeline")
def timeline(db: Session = Depends(get_db), current_user:User=Depends(get_current_user)):
    
    results = (
    db.query(Post, User, Like.post_id)
    .join(User, Post.user_id == User.id)
    .outerjoin(
        Like,
        and_(
            Like.post_id == Post.id,
            Like.user_id == current_user.id,
        ),
    )
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
            "is_liked":liked_post_id is not None
        }
        for post, user, liked_post_id in results
    ]


@router.get("/timeline_connected_users")
def timeline_connected_users(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    # Get accepted connections where I am the local_user_id
    connections = (
        db.query(Connection)
        .filter(Connection.local_user_id == user.id, Connection.status == "accepted")
        .all()
    )

    # Collect connected local user IDs and remote author identifiers
    connected_local_user_ids = []
    connected_remote_authors = []  # friendly author names (username@domain)
    connected_remote_actor_urls = []  # raw actor URLs (for backward compat)

    for c in connections:
        if c.target_local_user_id:
            connected_local_user_ids.append(c.target_local_user_id)
        elif c.remote_actor_url:
            connected_remote_actor_urls.append(c.remote_actor_url)
            # Convert actor URL to friendly author name (e.g. alice@mastodon.social)
            parsed = urlparse(c.remote_actor_url)
            path_name = c.remote_actor_url.rstrip("/").split("/")[-1]
            connected_remote_authors.append(f"{path_name}@{parsed.hostname}")

    if not connected_local_user_ids and not connected_remote_authors:
        return []

    # Get posts from connected local users
    local_results = []
    if connected_local_user_ids:
        local_results = (
            db.query(Post, User)
            .join(User, Post.user_id == User.id)
            .filter(Post.user_id.in_(connected_local_user_ids))
            .order_by(desc(Post.created_at))
            .all()
        )

    # Get posts from connected remote actors
    # Match by friendly name (username@domain) OR raw actor URL (backward compat)
    remote_results = []
    if connected_remote_authors:
        remote_posts = (
            db.query(Post)
            .filter(
                Post.is_remote == True,
                or_(
                    Post.author.in_(connected_remote_authors),
                    Post.author.in_(connected_remote_actor_urls),
                ),
            )
            .order_by(desc(Post.created_at))
            .all()
        )
        remote_results = [(post, None) for post in remote_posts]

    # Combine and sort by created_at
    all_results = local_results + remote_results
    all_results.sort(key=lambda x: x[0].created_at, reverse=True)

    return [
        {
            "id": post.id,
            "content": _strip_html_for_display(post.content),
            "author": u.username if u else post.author,
            "avatar_url": u.avatar_url if u else None,
            "image_url": post.image_url,
            "created_at": post.created_at,
            "like_count": post.like_count,
            "is_remote": post.is_remote,
        }
        for post, u in all_results
    ]


def _strip_html_for_display(content: str) -> str:
    """Strip any remaining HTML from post content for clean display."""
    if not content:
        return content
    import re
    # If content looks like it has HTML tags, strip them
    if "<" in content and ">" in content:
        text = re.sub(r'<br\s*/?>', '\n', content)
        text = re.sub(r'</p>\s*<p>', '\n\n', text)
        text = re.sub(r'<[^>]+>', '', text)
        return text.strip()
    return content


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
    deliver_activity(activity, user=user, db=db)
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
