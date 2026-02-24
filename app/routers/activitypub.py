"""
app/routers/activitypub.py

ActivityPub-compliant endpoints:

  GET  /.well-known/webfinger          — WebFinger resource discovery
  GET  /users/{username}               — Actor object (content-negotiated)
  POST /users/{username}/inbox         — Per-user inbox with HTTP sig verification
  GET  /users/{username}/outbox        — OrderedCollection of activities
  GET  /users/{username}/followers     — Followers OrderedCollection
  GET  /users/{username}/following     — Following OrderedCollection

Content-types served:
  WebFinger → application/jrd+json
  Actor     → application/activity+json
  Inbox/Outbox → application/activity+json

Mastodon compatibility notes:
  - @context includes both ActivityStreams and Security vocabulary in Actor
  - publicKey.id is "{actor_url}#main-key"
  - RSA key pair auto-generated on first actor request if absent
  - Inbox verifies Digest header then HTTP Signature before processing
  - All activity objects have unique id URLs
"""

import json
import uuid
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Activity, Connection, Like, Post, User
from app.services.crypto import (
    fetch_remote_public_key,
    generate_rsa_keypair,
    sha256_digest,
    verify_digest,
    verify_signature,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Content-type constants
# ---------------------------------------------------------------------------

AP_CONTENT_TYPE = "application/activity+json"
LD_CONTENT_TYPE = 'application/ld+json; profile="https://www.w3.org/ns/activitystreams"'
JRD_CONTENT_TYPE = "application/jrd+json"

AP_ACCEPT_TYPES = {AP_CONTENT_TYPE, LD_CONTENT_TYPE, "application/ld+json"}

AS_CONTEXT = "https://www.w3.org/ns/activitystreams"
AS_PUBLIC = "https://www.w3.org/ns/activitystreams#Public"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _actor_url(username: str) -> str:
    return f"{settings.BASE_URL}/users/{username}"


def _wants_activity_json(accept: Optional[str]) -> bool:
    """Return True if the Accept header signals ActivityPub / JSON-LD."""
    if not accept:
        return False
    for token in accept.split(","):
        token = token.split(";")[0].strip()
        if token in AP_ACCEPT_TYPES:
            return True
    return False


def _ensure_rsa_keys(user: User, db: Session) -> None:
    """Generate and persist RSA keys for *user* if they don't exist."""
    if not user.rsa_private_key or not user.rsa_public_key:
        priv, pub = generate_rsa_keypair()
        user.rsa_private_key = priv
        user.rsa_public_key = pub
        db.commit()


def _build_actor(user: User) -> dict:
    actor_url = _actor_url(user.username)
    return {
        "@context": [
            AS_CONTEXT,
            "https://w3id.org/security/v1",
        ],
        "id": actor_url,
        "type": "Person",
        "preferredUsername": user.username,
        "name": user.username,
        "summary": "",
        "inbox": f"{actor_url}/inbox",
        "outbox": f"{actor_url}/outbox",
        "followers": f"{actor_url}/followers",
        "following": f"{actor_url}/following",
        "publicKey": {
            "id": f"{actor_url}#main-key",
            "owner": actor_url,
            "publicKeyPem": user.rsa_public_key,
        },
        **({"icon": {"type": "Image", "url": user.avatar_url}} if user.avatar_url else {}),
    }


# ---------------------------------------------------------------------------
# 1. WebFinger
# ---------------------------------------------------------------------------


@router.get("/.well-known/webfinger")
def webfinger(resource: str, db: Session = Depends(get_db)):
    """
    GET /.well-known/webfinger?resource=acct:{username}@{domain}

    Returns a JSON Resource Descriptor (JRD) per RFC 7033.
    Content-Type: application/jrd+json
    """
    # Validate resource format
    if not resource.startswith("acct:"):
        raise HTTPException(status_code=400, detail="resource must be an acct: URI")

    acct = resource[len("acct:"):]  # e.g. "alice@example.com"
    if "@" not in acct:
        raise HTTPException(status_code=400, detail="Invalid acct: URI format")

    local_part, domain = acct.rsplit("@", 1)

    # Validate domain matches this server's BASE_URL
    parsed = urlparse(settings.BASE_URL)
    if domain != parsed.netloc:
        raise HTTPException(status_code=404, detail="User not found on this instance")

    user = db.query(User).filter(User.username == local_part).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    jrd = {
        "subject": resource,
        "aliases": [_actor_url(user.username)],
        "links": [
            {
                "rel": "self",
                "type": AP_CONTENT_TYPE,
                "href": _actor_url(user.username),
            },
            {
                "rel": "http://webfinger.net/rel/profile-page",
                "type": "text/html",
                "href": _actor_url(user.username),
            },
        ],
    }
    return JSONResponse(content=jrd, media_type=JRD_CONTENT_TYPE)


# ---------------------------------------------------------------------------
# 2. Actor endpoint (content-negotiated)
# ---------------------------------------------------------------------------


@router.get("/users/{username}")
def actor_or_profile(
    username: str,
    request: Request,
    db: Session = Depends(get_db),
    accept: Optional[str] = Header(None),
):
    """
    GET /users/{username}

    When the Accept header requests ActivityPub JSON, returns the Actor object.
    Otherwise falls through to normal behaviour (404 so the existing profile
    route in users.py handles it — both routers are registered).

    Note: FastAPI resolves routes in registration order, so the activitypub
    router's /users/{username} only fires when Accept signals ActivityPub.
    """
    if not _wants_activity_json(accept):
        # Not an AP request — let the rest of the app handle it (profile UI etc.)
        raise HTTPException(
            status_code=406,
            detail="Set Accept: application/activity+json to fetch the Actor object.",
        )

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    _ensure_rsa_keys(user, db)

    return JSONResponse(content=_build_actor(user), media_type=AP_CONTENT_TYPE)


# ---------------------------------------------------------------------------
# 3. Inbox — per user, with signature verification
# ---------------------------------------------------------------------------

INBOX_PAGE_SIZE = 20


@router.post("/users/{username}/inbox")
async def user_inbox(
    username: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    POST /users/{username}/inbox

    Processes incoming ActivityPub activities.
    Verifies Digest and HTTP Signature before accepting.

    Handles:
        Follow, Accept, Undo (Follow), Create (Note), Delete,
        Like, Announce
    """
    # ------------------------------------------------------------------ #
    # 0. Load target user
    # ------------------------------------------------------------------ #
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # ------------------------------------------------------------------ #
    # 1. Read and validate body
    # ------------------------------------------------------------------ #
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty request body")

    # ------------------------------------------------------------------ #
    # 2. Verify Digest header
    # ------------------------------------------------------------------ #
    digest_header = request.headers.get("digest") or request.headers.get("Digest")
    if not digest_header:
        raise HTTPException(status_code=400, detail="Missing Digest header")

    if not verify_digest(body, digest_header):
        raise HTTPException(status_code=400, detail="Digest mismatch")

    # ------------------------------------------------------------------ #
    # 3. Parse activity JSON
    # ------------------------------------------------------------------ #
    try:
        activity = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    activity_type = activity.get("type")
    actor_url: str = activity.get("actor", "")

    if not activity_type or not actor_url:
        raise HTTPException(status_code=400, detail="Missing type or actor")

    # ------------------------------------------------------------------ #
    # 4. Verify HTTP Signature
    # ------------------------------------------------------------------ #
    sig_header = request.headers.get("signature") or request.headers.get("Signature")
    if not sig_header:
        raise HTTPException(status_code=401, detail="Missing Signature header")

    # Derive key_id from Signature header
    key_id = None
    for part in sig_header.split(","):
        part = part.strip()
        if part.startswith('keyId="'):
            key_id = part[len('keyId="'):-1]
            break

    if not key_id:
        raise HTTPException(status_code=401, detail="keyId missing from Signature")

    pub_key_pem = fetch_remote_public_key(key_id, actor_url)
    if not pub_key_pem:
        raise HTTPException(
            status_code=401,
            detail=f"Could not fetch public key for actor: {actor_url}",
        )

    # Build lowercase header map for verification
    header_map = {k.lower(): v for k, v in request.headers.items()}
    path = request.url.path
    if request.url.query:
        path = f"{path}?{request.url.query}"

    if not verify_signature("post", path, header_map, body, pub_key_pem):
        raise HTTPException(status_code=401, detail="HTTP Signature verification failed")

    # ------------------------------------------------------------------ #
    # 5. Persist raw activity
    # ------------------------------------------------------------------ #
    new_activity = Activity(
        id=str(uuid.uuid4()),
        type=activity_type,
        actor=actor_url,
        object=activity.get("object", {}),
        is_local=False,
        is_delivered=True,
    )
    db.add(new_activity)

    # ------------------------------------------------------------------ #
    # 6. Dispatch
    # ------------------------------------------------------------------ #
    try:
        _dispatch_inbox(activity, activity_type, actor_url, user, db)
    except Exception:
        # Don't fail the whole request on dispatch error; activity is stored
        pass

    db.commit()
    return JSONResponse(content={"status": "accepted"}, status_code=202)


def _dispatch_inbox(
    activity: dict,
    activity_type: str,
    actor_url: str,
    target_user: User,
    db: Session,
) -> None:
    """Route an activity to the correct handler."""

    obj = activity.get("object") or {}
    obj_type = obj.get("type") if isinstance(obj, dict) else None
    obj_id = (obj.get("id") if isinstance(obj, dict) else obj) or ""

    # --- Follow ---
    if activity_type == "Follow":
        # Check if already has a connection record
        existing = (
            db.query(Connection)
            .filter(
                Connection.target_actor == _actor_url(target_user.username),
                Connection.requester_id == actor_url,
            )
            .first()
        )
        if not existing:
            db.add(
                Connection(
                    requester_id=actor_url,       # store actor URL for remote actors
                    target_actor=_actor_url(target_user.username),
                    status="pending",
                )
            )

    # --- Accept (of a Follow) ---
    elif activity_type == "Accept" and isinstance(obj, dict) and obj.get("type") == "Follow":
        follow_actor = obj.get("actor", "")
        conn = (
            db.query(Connection)
            .filter(Connection.requester_id == follow_actor, Connection.target_actor == actor_url)
            .first()
        )
        if conn:
            conn.status = "accepted"

    # --- Undo (Follow) ---
    elif activity_type == "Undo" and isinstance(obj, dict) and obj.get("type") == "Follow":
        conn = (
            db.query(Connection)
            .filter(
                Connection.requester_id == actor_url,
                Connection.target_actor == _actor_url(target_user.username),
            )
            .first()
        )
        if conn:
            db.delete(conn)

    # --- Create Note ---
    elif activity_type == "Create" and obj_type == "Note":
        post_id = obj.get("id")
        content = obj.get("content", "")
        image_url = _note_image_url(obj)
        published = obj.get("published")

        if post_id:
            existing = db.query(Post).filter(Post.id == post_id).first()
            if not existing:
                db.add(
                    Post(
                        id=post_id,
                        content=content,
                        image_url=image_url,
                        user_id=None,
                        author=actor_url,
                        origin_instance=actor_url.split("/users/")[0],
                        is_remote=True,
                    )
                )

    # --- Delete ---
    elif activity_type == "Delete":
        # obj may be a Tombstone dict or a plain string id
        target_id = obj_id or (obj if isinstance(obj, str) else "")
        if target_id:
            post = db.query(Post).filter(Post.id == target_id, Post.is_remote == True).first()
            if post:
                db.delete(post)

    # --- Like ---
    elif activity_type == "Like":
        post = db.query(Post).filter(Post.id == obj_id).first()
        if post:
            post.like_count = (post.like_count or 0) + 1

    # --- Announce (Boost) ---
    elif activity_type == "Announce" and obj_id:
        # Store as a remote activity; optionally fetch the original post
        pass


def _note_image_url(note: dict) -> Optional[str]:
    """Extract the first image attachment URL from a Note object, if any."""
    for att in note.get("attachment") or []:
        if isinstance(att, dict) and att.get("type") == "Image":
            return att.get("url")
    return None


# ---------------------------------------------------------------------------
# 4. Outbox — GET (OrderedCollection)
# ---------------------------------------------------------------------------

OUTBOX_PAGE_SIZE = 20


@router.get("/users/{username}/outbox")
def user_outbox(
    username: str,
    page: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """
    GET /users/{username}/outbox[?page=N]

    Returns an OrderedCollection (no page param) or OrderedCollectionPage (page=N).
    Content-Type: application/activity+json
    """
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    actor_url = _actor_url(username)
    outbox_url = f"{actor_url}/outbox"

    total = (
        db.query(Activity)
        .filter(Activity.actor == actor_url, Activity.is_local == True)
        .count()
    )

    if page is None:
        # Return the collection stub
        collection = {
            "@context": AS_CONTEXT,
            "id": outbox_url,
            "type": "OrderedCollection",
            "totalItems": total,
            "first": f"{outbox_url}?page=1",
        }
        return JSONResponse(content=collection, media_type=AP_CONTENT_TYPE)

    # Paginated page
    offset = (page - 1) * OUTBOX_PAGE_SIZE
    activities = (
        db.query(Activity)
        .filter(Activity.actor == actor_url, Activity.is_local == True)
        .order_by(Activity.created_at.desc())
        .offset(offset)
        .limit(OUTBOX_PAGE_SIZE)
        .all()
    )

    items = []
    for act in activities:
        obj = act.object if isinstance(act.object, dict) else {"id": str(act.object)}
        items.append(
            {
                "@context": AS_CONTEXT,
                "id": f"{settings.BASE_URL}/activities/{act.id}",
                "type": act.type,
                "actor": act.actor,
                "object": obj,
            }
        )

    page_doc = {
        "@context": AS_CONTEXT,
        "id": f"{outbox_url}?page={page}",
        "type": "OrderedCollectionPage",
        "partOf": outbox_url,
        "orderedItems": items,
        "totalItems": total,
    }

    if offset + OUTBOX_PAGE_SIZE < total:
        page_doc["next"] = f"{outbox_url}?page={page + 1}"
    if page > 1:
        page_doc["prev"] = f"{outbox_url}?page={page - 1}"

    return JSONResponse(content=page_doc, media_type=AP_CONTENT_TYPE)


# ---------------------------------------------------------------------------
# 5. Followers / Following (lightweight collections)
# ---------------------------------------------------------------------------


@router.get("/users/{username}/followers")
def user_followers(username: str, db: Session = Depends(get_db)):
    """
    GET /users/{username}/followers

    Returns an OrderedCollection with totalItems only (no enumeration
    by default, for privacy — this is Mastodon's default behaviour).
    """
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    actor_url = _actor_url(username)

    count = (
        db.query(Connection)
        .filter(Connection.target_actor == actor_url, Connection.status == "accepted")
        .count()
    )

    collection = {
        "@context": AS_CONTEXT,
        "id": f"{actor_url}/followers",
        "type": "OrderedCollection",
        "totalItems": count,
    }
    return JSONResponse(content=collection, media_type=AP_CONTENT_TYPE)


@router.get("/users/{username}/following")
def user_following(username: str, db: Session = Depends(get_db)):
    """
    GET /users/{username}/following

    Returns an OrderedCollection of actors this user follows.
    """
    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    actor_url = _actor_url(username)

    count = (
        db.query(Connection)
        .filter(Connection.requester_id == user.id, Connection.status == "accepted")
        .count()
    )

    collection = {
        "@context": AS_CONTEXT,
        "id": f"{actor_url}/following",
        "type": "OrderedCollection",
        "totalItems": count,
    }
    return JSONResponse(content=collection, media_type=AP_CONTENT_TYPE)
