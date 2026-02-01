from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Post, Activity, Connection, User
from app.dependencies import get_current_user
from app.config import settings

router = APIRouter()

@router.post("/inbox")
def inbox(activity: dict, db: Session = Depends(get_db)):
    activity_type = activity.get("type")
    actor = activity.get("actor")
    obj = activity.get("object")

    if not activity_type or not actor or not obj:
        raise HTTPException(status_code=400, detail="Invalid activity")

    # Store activity (remote)
    new_activity = Activity(
        type=activity_type,
        actor=actor,
        object=obj,
        is_local=False,
        is_delivered=True
    )
    db.add(new_activity)

    # Handle Create
    if activity_type == "Create" and obj.get("type") == "Note":
        post_id = obj.get("id")
        content = obj.get("content")

        # prevent duplicates
        existing = db.query(Post).filter(Post.id == post_id).first()
        if not existing:
            post = Post(
                id=post_id,
                content=content,
                user_id=None,
                author=actor,
                origin_instance=actor.split("/users/")[0],
                is_remote=True
            )
            db.add(post)

    # Handle Delete
    if activity_type == "Delete":
        target_id = obj.get("id")
        post = (
            db.query(Post)
            .filter(Post.is_remote == True)
            .filter(Post.id.endswith(target_id.split("/")[-1]))
            .first()
        )   
        if post:
            db.delete(post)

    if activity_type == "Follow":
        connection = Connection(
            requester_id="REMOTE",  # placeholder
            target_actor=activity["object"],
            status="pending"
        )
        db.add(connection)

    if activity_type == "Accept":
        follow = activity["object"]
        actor = follow["actor"]
        target = follow["object"]

        conn = db.query(Connection).filter(
            Connection.target_actor == actor
        ).first()

        if conn:
            conn.status = "accepted"

    db.commit()
    return {"status": "accepted"}

@router.post("/inbox/delete")
def delete_remote_post(id:str,db:Session=Depends(get_db)):
    post = db.query(Post).filter(Post.id==id,Post.is_remote==True).first()
    if not post:
        return {"status":"ignored"}

    db.delete(post)
    db.commit()
    return {"status":"deleted"}

@router.post("/users/{username}/outbox")
def outbox(username: str, activity: dict, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    if user.username != username:
        raise HTTPException(
            status_code=403,
            detail="Cannot write to another actor's outbox"
        )

    if activity.get("actor") != f"{settings.BASE_URL}/users/{username}": 
        raise HTTPException(
            status_code=400,
            detail="Actor mismatch"
        )

    new_activity = Activity(
        type=activity.get("type"),
        actor=activity.get("actor"),
        object=activity.get("object"),
        is_local=True,
        is_delivered=False
    )

    db.add(new_activity)
    db.commit()
    db.refresh(new_activity)

    return {
        "status": "stored",
        "activity_id": new_activity.id
    }