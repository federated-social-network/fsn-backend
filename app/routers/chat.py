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
            msg_type = data.get("type", "chat")

            if msg_type == "read_receipt":
                sender_id = data.get("sender_id")
                if sender_id:
                    with SessionLocal() as db:
                        unread_msgs = db.query(Message).filter(
                            Message.sender_id == sender_id,
                            Message.receiver_id == user_id,
                            Message.is_read == False
                        ).all()
                        
                        if unread_msgs:
                            for msg in unread_msgs:
                                msg.is_read = True
                            db.commit()
                            
                            await manager.send_personal_message(
                                sender_id,
                                {
                                    "type": "read_receipt",
                                    "reader_id": user_id
                                }
                            )

            elif msg_type == "chat":
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
                    msg_id = msg.id
                    created_at = msg.created_at.isoformat()

                # Broadcast real-time message
                await manager.send_personal_message(
                    receiver_id,
                    {
                        "type": "chat",
                        "id": msg_id,
                        "sender_id": user_id,
                        "content": content,
                        "is_read": False,
                        "created_at": created_at
                    }
                )

            elif msg_type.startswith("webrtc_"):
                # Forward WebRTC signaling messages directly to the receiver without saving to DB
                receiver_id = data.get("receiver_id")
                if receiver_id:
                    # Fetch sender details to include in signaling (useful for receiver UI)
                    sender_info = {}
                    with SessionLocal() as db:
                        sender = db.query(User).filter(User.id == user_id).first()
                        if sender:
                            sender_info = {
                                "display_name": sender.display_name,
                                "avatar_url": sender.avatar_url,
                                "username": sender.username
                            }
                    
                    # Pass along the entire payload to the receiver
                    # The sender_id and sender_info are explicitly injected so the receiver knows who it's from
                    payload = {**data, "sender_id": user_id, "sender_info": sender_info}
                    success = await manager.send_personal_message(receiver_id, payload)

                    if not success and msg_type == "webrtc_offer":
                        await manager.send_personal_message(user_id, {
                            "type": "webrtc_error",
                            "message": "User is currently offline."
                        })

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

    return [
        {
            "id": msg.id,
            "sender_id": msg.sender_id,
            "receiver_id": msg.receiver_id,
            "content": msg.content,
            "is_read": msg.is_read,
            "created_at": msg.created_at
        }
        for msg in messages
    ]


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

    return [
        {
            "other_user": r.other_user,
            "username": r.username,
            "avatar_url": r.avatar_url,
            "content": r.content,
            "created_at": r.created_at
        }
        for r in results
    ]