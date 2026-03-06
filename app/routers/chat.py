from fastapi import APIRouter, WebSocket, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, case, func
from app.database import get_db, SessionLocal
from app.models import Message, User
from app.services.connection_manager import manager
from app.dependencies import get_current_user

router = APIRouter()

@router.websocket("/ws/chat/{user_id}")
async def chat_socket(websocket: WebSocket, user_id: str):

    await manager.connect(user_id, websocket)

    try:
        while True:
            data = await websocket.receive_json()

            receiver_id = data["receiver_id"]
            content = data["content"]

            # Save to database using a fresh session
            with SessionLocal() as db:
                msg = Message(
                    sender_id=user_id,
                    receiver_id=receiver_id,
                    content=content
                )
                db.add(msg)
                db.commit()

            # Broadcast real-time message
            await manager.send_personal_message(
                receiver_id,
                {
                    "sender_id": user_id,
                    "content": content
                }
            )

    except Exception as e:
        print(f"WebSocket closed or error for user {user_id}: {e}")
        manager.disconnect(user_id)


@router.get("/messages/{user1}/{user2}")
def get_messages(user1: str, user2: str, db: Session = Depends(get_db)):

    messages = db.query(Message).filter(
        or_(
            and_(Message.sender_id == user1, Message.receiver_id == user2),
            and_(Message.sender_id == user2, Message.receiver_id == user1)
        )
    ).order_by(Message.created_at).all()

    return messages


@router.get("/conversations")
def get_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    user_id = current_user.id

    subq = (
        db.query(
            case(
                (Message.sender_id == user_id, Message.receiver_id),
                else_=Message.sender_id
            ).label("other_user"),
            func.max(Message.created_at).label("latest_time")
        )
        .filter(
            or_(
                Message.sender_id == user_id,
                Message.receiver_id == user_id
            )
        )
        .group_by("other_user")
        .subquery()
    )

    results = (
        db.query(
            subq.c.other_user,
            User.username,
            User.avatar_url,
            Message.content,
            Message.created_at
        )
        .join(User, User.id == subq.c.other_user)
        .join(
            Message,
            (Message.created_at == subq.c.latest_time)
        )
        .order_by(Message.created_at.desc())
        .all()
    )

    return results