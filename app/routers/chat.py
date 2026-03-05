from fastapi import APIRouter, WebSocket, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.database import get_db
from app.models import Message
from app.services.connection_manager import manager

router = APIRouter()

@router.websocket("/ws/chat/{user_id}")
async def chat_socket(websocket: WebSocket, user_id: str, db: Session = Depends(get_db)):

    await manager.connect(user_id, websocket)

    try:
        while True:
            data = await websocket.receive_json()

            receiver_id = data["receiver_id"]
            content = data["content"]

            msg = Message(
                sender_id=user_id,
                receiver_id=receiver_id,
                content=content
            )

            db.add(msg)
            db.commit()

            await manager.send_personal_message(
                receiver_id,
                {
                    "sender_id": user_id,
                    "content": content
                }
            )

    except:
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