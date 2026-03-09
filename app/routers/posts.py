import json
import re
import uuid
from io import BytesIO
from urllib.parse import urlparse

import redis
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from groq import Groq
from PIL import Image
from sqlalchemy import and_, desc, func, or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models import Activity, Comment, Connection, Like, Notification, Post, User
from app.services.federation import (
    build_create_activity,
    build_delete_activity,
    deliver_activity,
)
from app.services.supabase_client import supabase

router = APIRouter()
client = Groq(api_key=settings.GROQ_API_KEY)


redis_client = redis.Redis(host="10.159.248.211", port=6379, decode_responses=True)


@router.post("/posts")
async def create_post(
    visibility: str = "public",
    content: str | None = Form(None),
    image: UploadFile = File(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if content is None:
        content = ""

    if not content.strip() and not image:
        raise HTTPException(status_code=400, detail="Post must contain text or an image")

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
        supabase.storage.from_("posts").upload(filename, contents, {"content-type": image.content_type})

        image_url = f"{settings.SUPABASE_URL}/storage/v1/object/public/posts/{filename}"

    post = Post(
        id=str(uuid.uuid4()),
        content=content,
        image_url=image_url,
        user_id=user.id,
        author=user.username,
        origin_instance=settings.INSTANCE_NAME,
        is_remote=False,
        visibility=visibility,
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

    # ---- Handle mentions ----
    if post.content:
        # Find all @username patterns
        mentioned_usernames = set(re.findall(r"@([\w.-]+)", post.content))
        if mentioned_usernames:
            # Look up mentioned local users, excluding the author
            mentioned_users = db.query(User).filter(User.username.in_(mentioned_usernames), User.id != user.id).all()

            for mentioned_user in mentioned_users:
                notification = Notification(
                    recipient_id=mentioned_user.id,
                    actor_id=user.id,
                    type="mention",
                    object_id=post.id,
                )
                db.add(notification)

            if mentioned_users:
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
        .outerjoin(User, Post.user_id == User.id)
        .outerjoin(
            Like,
            and_(
                Like.post_id == Post.id,
                Like.user_id == current_user.id,
            ),
        )
        .filter(
            Post.is_remote == False,
            or_(
                Post.visibility == "public",
                and_(Post.visibility == "followers", connection_exists),
                Post.user_id == current_user.id,
            ),
        )
        .order_by(Post.created_at.desc())
        .all()
    )

    posts = [post.id for post, _, _ in results]

    # ONE query to fetch likes
    like_rows = (
        db.query(Like.post_id, User.avatar_url)
        .join(User, Like.user_id == User.id)
        .filter(Like.post_id.in_(posts), User.avatar_url.isnot(None))
        .all()
    )

    # group avatars per post
    like_map = {}
    for post_id, avatar in like_rows:
        if post_id not in like_map:
            like_map[post_id] = []
        if len(like_map[post_id]) < 3:
            like_map[post_id].append(avatar)

    response = [
        {
            "id": post.id,
            "content": post.content,
            "created_at": post.created_at.isoformat(),
            "author": user.username if user else post.author,
            "image_url": post.image_url,
            "avatar_url": user.avatar_url if user else None,
            "display_name": user.display_name if user else (post.author if post.is_remote else "Unknown"),
            "like_count": post.like_count,
            "is_liked": liked_post_id is not None,
            "liked_by": like_map.get(post.id, []),
            "comment_count": post.comment_count,
            "is_remote": post.is_remote,
        }
        for post, user, liked_post_id in results
    ]

    redis_client.setex(cache_key, 60, json.dumps(response))
    return response


@router.get("/timeline_connected_users")
def timeline_connected_users(user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    connections = (
        db.query(Connection).filter(Connection.local_user_id == user.id, Connection.status == "accepted").all()
    )

    connected_local_user_ids = []
    connected_remote_actor_urls = []

    for c in connections:
        if c.target_local_user_id:
            connected_local_user_ids.append(c.target_local_user_id)
        elif c.remote_actor_url:
            connected_remote_actor_urls.append(c.remote_actor_url)

    if not connected_local_user_ids and not connected_remote_actor_urls:
        return []

    # LOCAL POSTS
    local_results = []
    if connected_local_user_ids:
        local_results = (
            db.query(Post, User)
            .join(User, Post.user_id == User.id)
            .filter(Post.user_id.in_(connected_local_user_ids))
            .order_by(desc(Post.created_at))
            .all()
        )

    # REMOTE POSTS
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

    all_results = local_results + remote_results
    all_results.sort(key=lambda x: x[0].created_at, reverse=True)

    post_ids = [post.id for post, _ in all_results]

    # avatars of people who liked
    like_rows = (
        db.query(Like.post_id, User.avatar_url)
        .join(User, Like.user_id == User.id)
        .filter(Like.post_id.in_(post_ids), User.avatar_url.isnot(None))
        .all()
    )

    like_map = {}
    for post_id, avatar in like_rows:
        if post_id not in like_map:
            like_map[post_id] = []
        if len(like_map[post_id]) < 3:
            like_map[post_id].append(avatar)

    # check if current user liked
    liked_posts = db.query(Like.post_id).filter(Like.post_id.in_(post_ids), Like.user_id == user.id).all()

    liked_set = {p[0] for p in liked_posts}

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
            "display_name": u.display_name if u else None,
            "liked_by": like_map.get(post.id, []),
            "is_liked": post.id in liked_set,
            "comment_count": post.comment_count,
        }
        for post, u in all_results
    ]


@router.get("/debug/timeline_state")
def debug_timeline_state(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Debug endpoint to see exactly what's in the DB for the following timeline."""
    connections = (
        db.query(Connection).filter(Connection.local_user_id == user.id, Connection.status == "accepted").all()
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
            remote_connections.append(
                {
                    "connection_id": c.id,
                    "remote_actor_url": c.remote_actor_url,
                    "remote_inbox_url": c.remote_inbox_url,
                    "status": c.status,
                    "derived_friendly_name": friendly,
                }
            )

    remote_posts = db.query(Post).filter(Post.is_remote == True).order_by(Post.created_at.desc()).limit(20).all()

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
        text = re.sub(r"<br\s*/?>", "\n", content)
        text = re.sub(r"</p>\s*<p>", "\n\n", text)
        text = re.sub(r"<[^>]+>", "", text)
        return text.strip()
    return content


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
def like_post(post_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    post = db.query(Post).filter(Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    existing = db.query(Like).filter(Like.user_id == user.id, Like.post_id == post_id).first()

    if existing:
        raise HTTPException(status_code=400, detail="Already liked")

    like = Like(id=str(uuid.uuid4()), user_id=user.id, post_id=post_id)

    db.add(like)
    post.like_count += 1

    if post.user_id != user.id:
        notification = Notification(recipient_id=post.user_id, actor_id=user.id, type="like", object_id=post.id)
        db.add(notification)

    db.commit()
    redis_client.delete(f"timeline:{user.id}")
    return {"message": "Liked"}


@router.delete("/posts/{post_id}/like")
def unlike_post(post_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    like = db.query(Like).filter(Like.user_id == user.id, Like.post_id == post_id).first()

    if not like:
        raise HTTPException(status_code=404, detail="Like not found")

    post = db.query(Post).filter(Post.id == post_id).first()

    db.delete(like)
    post.like_count = max(0, post.like_count - 1)

    db.commit()
    redis_client.delete(f"timeline:{user.id}")

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
                            """,
                },
                {"role": "user", "content": content},
            ],
            temperature=0.5,
            max_tokens=300,
        )

        improved_text = response.choices[0].message.content.strip()

        return {"original": content, "completed": improved_text}

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
                            """,
                },
                {"role": "user", "content": content},
            ],
            temperature=0.5,
            max_tokens=3000,
        )

        improved_text = response.choices[0].message.content.strip()

        return {"original": content, "completed": improved_text}

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


@router.post("/{post_id}/comments")
async def create_comment(
    post_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):

    body = await request.json()
    content = body.get("content")

    if not content:
        raise HTTPException(status_code=400, detail="Content required")

    post = db.query(Post).filter(Post.id == post_id).first()

    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    comment = Comment(
        id=str(uuid.uuid4()),
        content=content,
        user_id=current_user.id,
        post_id=post_id,
    )

    db.add(comment)

    post.comment_count += 1

    if post.user_id != current_user.id:
        notification = Notification(
            recipient_id=post.user_id,
            actor_id=current_user.id,
            type="comment",
            object_id=post.id,
        )
        db.add(notification)

    db.commit()
    db.commit()

    return {
        "id": comment.id,
        "content": comment.content,
        "user_id": comment.user_id,
        "post_id": comment.post_id,
        "created_at": comment.created_at,
    }


@router.get("/{post_id}/comments")
def get_comments(post_id: str, db: Session = Depends(get_db)):

    comments = (
        db.query(Comment, User)
        .join(User, Comment.user_id == User.id)
        .filter(Comment.post_id == post_id)
        .order_by(Comment.created_at.desc())
        .all()
    )

    return [
        {
            "id": comment.id,
            "content": comment.content,
            "user_id": comment.user_id,
            "post_id": comment.post_id,
            "avatar_url": user.avatar_url,
            "display_name": user.display_name,
            "created_at": comment.created_at,
            "username": user.username,
        }
        for comment, user in comments
    ]


@router.delete("/comments/{comment_id}")
def delete_comment(
    comment_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):

    comment = db.query(Comment).filter(Comment.id == comment_id).first()

    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")

    # allow only the comment author
    if comment.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this comment")

    post = db.query(Post).filter(Post.id == comment.post_id).first()

    db.delete(comment)

    if post and post.comment_count > 0:
        post.comment_count -= 1

    db.commit()

    return {"message": "Comment deleted"}
