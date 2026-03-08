from sqlalchemy import and_, desc, or_
from urllib.parse import urlparse
import uuid
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Request
from sqlalchemy.orm import Session, aliased
from app.database import get_db
from sqlalchemy import or_, and_, exists
from app.models import Notification, Post, User, Activity, Connection, Like, Comment
from app.dependencies import get_current_user
from app.config import settings

router = APIRouter()


@router.get("/notifications")
def get_notifications(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    Actor = aliased(User)
    Recipient = aliased(User)

    rows = (
        db.query(Notification, Actor, Recipient)
        .join(Actor, Notification.actor_id == Actor.id)
        .join(Recipient, Notification.recipient_id == Recipient.id)
        .filter(Notification.recipient_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(10)
        .all()
    )

    result = []

    for notif, actor, recipient in rows:
        result.append(
            {
                "id": notif.id,
                "type": notif.type,
                "object_id": notif.object_id,
                "created_at": notif.created_at,
                "is_read": notif.is_read,
                "actor": {
                    "id": actor.id,
                    "display_name": actor.display_name,
                    "avatar_url": actor.avatar_url,
                    "username": actor.username,
                },
                "recipient": {
                    "id": recipient.id,
                    "display_name": recipient.display_name,
                    "avatar_url": recipient.avatar_url,
                    "username": recipient.username,
                },
            }
        )

    return result
