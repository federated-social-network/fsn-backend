from sqlalchemy import and_, desc, or_
from urllib.parse import urlparse
import uuid
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy.orm import Session
from app.database import get_db
from sqlalchemy import or_, and_, exists
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
from groq import Groq
import redis
import json

router = APIRouter()
client = Groq(api_key=settings.GROQ_API_KEY)


redis_client = redis.Redis(
    host="10.159.248.211",
    port=6379,
    decode_responses=True
)


@router.post("/posts")
async def create_post(
    visibility : str,
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
        visibility=visibility
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
def timeline(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    cache_key = f"timeline:{current_user.id}"
    cached = redis_client.get(cache_key)
    if cached:
        return json.loads(cached)

    # Subquery: does current_user have accepted connection with post author?
    connection_exists = (
        db.query(Connection)
        .filter(
            Connection.local_user_id == current_user.id,
            Connection.target_local_user_id == Post.user_id,
            Connection.status == "accepted",
        )
        .exists()
    )

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
        .filter(
            or_(
                Post.visibility == "public",
                and_(
                    Post.visibility == "followers",
                    connection_exists
                ),
                Post.user_id == current_user.id
            )
        )
        .order_by(Post.created_at.desc())
        .all()
    )

    response = [
        {
            "id": post.id,
            "content": post.content,
            "created_at": post.created_at.isoformat(),
            "author": user.username,
            "image_url": post.image_url,
            "avatar_url": user.avatar_url,
            "like_count": post.like_count,
            "is_liked": liked_post_id is not None,
            "display_name": user.display_name,
        }
        for post, user, liked_post_id in results
    ]

    redis_client.setex(cache_key, 60, json.dumps(response))
    return response


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

    # Collect connected local user IDs and remote actor URLs
    connected_local_user_ids = []
    connected_remote_actor_urls = []

    for c in connections:
        if c.target_local_user_id:
            connected_local_user_ids.append(c.target_local_user_id)
        elif c.remote_actor_url:
            connected_remote_actor_urls.append(c.remote_actor_url)

    if not connected_local_user_ids and not connected_remote_actor_urls:
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
    # Match by post ID prefix — ActivityPub post IDs start with the actor URL
    # e.g. "https://mastodon.social/ap/users/12345/statuses/67890"
    remote_results = []
    if connected_remote_actor_urls:
        actor_conditions = [Post.id.like(f"{url}%") for url in connected_remote_actor_urls]
        remote_posts = (
            db.query(Post)
            .filter(
                Post.is_remote == True,
                or_(*actor_conditions),
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


@router.get("/debug/timeline_state")
def debug_timeline_state(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Debug endpoint to see exactly what's in the DB for the following timeline."""
    connections = (
        db.query(Connection)
        .filter(Connection.local_user_id == user.id, Connection.status == "accepted")
        .all()
    )

    remote_connections = []
    derived_authors = []
    derived_actor_urls = []

    for c in connections:
        if c.remote_actor_url:
            parsed = urlparse(c.remote_actor_url)
            path_name = c.remote_actor_url.rstrip("/").split("/")[-1]
            friendly = f"{path_name}@{parsed.hostname}"
            derived_authors.append(friendly)
            derived_actor_urls.append(c.remote_actor_url)
            remote_connections.append({
                "connection_id": c.id,
                "remote_actor_url": c.remote_actor_url,
                "remote_inbox_url": c.remote_inbox_url,
                "status": c.status,
                "derived_friendly_name": friendly,
            })

    remote_posts = (
        db.query(Post)
        .filter(Post.is_remote == True)
        .order_by(Post.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        "accepted_remote_connections": remote_connections,
        "derived_author_names": derived_authors,
        "derived_actor_urls": derived_actor_urls,
        "remote_posts_in_db": [
            {
                "id": p.id,
                "author": p.author,
                "origin_instance": p.origin_instance,
                "content_preview": p.content[:50] if p.content else None,
                "created_at": str(p.created_at),
            }
            for p in remote_posts
        ],
    }

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


@router.post("/post/completePost")
async def complete_post(content: str = Form(...)):

    # ---- validation ----
    if not content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": """
                            You are a professional writing enhancement engine.

                            Rewrite and expand the user's input while preserving its original meaning and intent.

                            Rules:
                            - Do NOT reply conversationally.
                            - Do NOT answer questions.
                            - Do NOT add new facts, opinions, or assumptions.
                            - Do NOT change the core message.
                            - Improve clarity, depth, flow, and engagement.
                            - Expand short inputs into a richer, well-structured version.
                            - Keep tone neutral and suitable for a social platform.
                            - Return ONLY the improved text.
                            """
                },
                {
                    "role": "user",
                    "content": content
                }
            ],
            temperature=0.5,
            max_tokens=300
        )

        improved_text = response.choices[0].message.content.strip()

        return {
            "original": content,
            "completed": improved_text
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/post/eloboratePost")
async def eloborate_post(content: str = Form(...)):

    # ---- validation ----
    if not content.strip():
        raise HTTPException(status_code=400, detail="Content cannot be empty")

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[
                {
                    "role": "system",
                    "content": """
                            You are a professional writing enhancement engine.

                            Rewrite and expand the user's input for around 45 to 50 words while preserving its original meaning and intent.

                            Rules:
                            - Do NOT reply conversationally.
                            - Do NOT answer questions.
                            - Do NOT change the core message.
                            - Improve clarity, depth, flow, and engagement.
                            - Expand short inputs into a richer, well-structured version.
                            - Keep tone neutral and suitable for a social platform.
                            - Return ONLY the improved text.
                            """
                },
                {
                    "role": "user",
                    "content": content
                }
            ],
            temperature=0.5,
            max_tokens=3000
        )

        improved_text = response.choices[0].message.content.strip()

        return {
            "original": content,
            "completed": improved_text
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.get("/debug/redis-health")
async def redis_health():
    try:
        # Test write
        redis_client.set("health:test", "ok", ex=30)

        # Test read
        value = redis_client.get("health:test")

        # Fetch stats
        info = redis_client.info("stats")

        return {
            "status": "connected",
            "ping": redis_client.ping(),
            "test_value": value,
            "keyspace_hits": info.get("keyspace_hits"),
            "keyspace_misses": info.get("keyspace_misses"),
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }