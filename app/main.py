from fastapi import FastAPI, HTTPException
from app.database import Base, engine
from app.models import Post,User
import uuid
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import Depends
from app.database import SessionLocal
from sqlalchemy.sql import func
from app.config import settings
import httpx
from jose import jwt, JWTError
from datetime import datetime, timedelta
from fastapi import Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, desc
from app.models import Activity
import httpx
from app.config import settings

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Federated Backend")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # dev only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def send_to_other_instance(post):
    other_instance_inbox = "https://instance-b.onrender.com/inbox"
    payload = {
        "id":post.id,
        "content":post.content,
        "author":post.author,
        "origin_instance":post.origin_instance
    }

    try:
        httpx.post(other_instance_inbox,params=payload,timeout=2)
    except Exception :
        pass

def authenticate(username: str, password: str, db):
    user = db.query(User).filter(User.username == username).first()
    if not user or not user.verify_password(password):
        raise HTTPException(status_code=401, detail="Invalid Credentials")
    return user

def create_access_token(data:dict,expires_minutes:int=60):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=expires_minutes)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def verify_token(token: str):
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_current_user(authorization: str = Header(...), db: Session = Depends(get_db)):
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth header")

    token = authorization.split(" ")[1]
    payload = verify_token(token)

    user = db.query(User).filter(User.id == payload["user_id"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user

def send_delete_to_other_instance(post_id:str):
    delete_other_instance_post = "https://instance-b.onrender.com/inbox/delete"
    try:
        httpx.post(delete_other_instance_post,params={"id":post_id},timeout=2)
    except Exception:
        pass


def build_create_activity(post, base_url):
    actor_url = f"{base_url}/users/{post.author}"

    return {
        "type": "Create",
        "actor": actor_url,
        "object": {
            "type": "Note",
            "id": f"{base_url}/posts/{post.id}",
            "content": post.content,
            "attributedTo": actor_url,
            "published": post.created_at.isoformat()
        }
    }


def deliver_activity(activity):
    if not settings.DELIVERY_ENABLED:
        return

    payload = {
        "type": activity.type,
        "actor": activity.actor,
        "object": activity.object
    }

    try:
        resp = httpx.post(
            settings.REMOTE_INBOX_URL,
            json=payload,
            timeout=5
        )

        if resp.status_code in (200, 202):
            activity.is_delivered = True

    except Exception as e:
        # silent fail for now (demo-safe)
        pass


def build_delete_activity(post, base_url):
    actor_url = f"{base_url}/users/{post.author}"
    return {
        "type": "Delete",
        "actor": actor_url,
        "object": {
            "id": f"{base_url}/posts/{post.id}"
        }
    }



@app.get("/")
def homePage():
    return{"message":"server is running..."}


@app.post("/posts")
def create_post(
    content: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    post = Post(
        id=str(uuid.uuid4()),
        content=content,
        user_id=user.id,
        author=user.username,
        origin_instance=settings.INSTANCE_NAME,
        is_remote=False
    )

    db.add(post)
    db.commit()
    db.refresh(post)

    # 🔹 NEW: emit Create activity (local only)
    activity_payload = build_create_activity(post, settings.BASE_URL)

    activity = Activity(
        type="Create",
        actor=activity_payload["actor"],
        object=activity_payload["object"],
        is_local=True,
        is_delivered=False
    )

    db.add(activity)
    db.commit()
    db.refresh(activity)

    # 🔹 STEP 8: real delivery
    deliver_activity(activity)
    return post


@app.post("/inbox")
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

    db.commit()
    return {"status": "accepted"}



@app.post("/register")
def register(username: str, password: str,email: str, db: Session = Depends(get_db)):
    try:
        user = User(
            id=str(uuid.uuid4()),
            username=username,
            password_hash=User.hash_password(password),
            email=email
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        return {"message": "user created"}

    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="username already exists"
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="internal server error"
        )


@app.post("/login")
def login(username: str, password: str, db: Session = Depends(get_db)):
    user = authenticate(username, password, db)

    token = create_access_token({
        "user_id": user.id,
        "username": user.username,
        "instance": settings.INSTANCE_NAME
    })

    return {"access_token": token}

#Need to change ---
@app.get("/get_posts")
def get_posts(db:Session=Depends(get_db)):
    posts = db.query(Post).order_by(Post.id.desc()).all()
    return posts
#               ----------------

@app.get("/timeline")
def timeline(db: Session = Depends(get_db)):
    posts = (
        db.query(Post)
        .order_by(Post.created_at.desc())
        .all()
    )

    return [
        {
            "id": post.id,
            "content": post.content,
            "author": post.author,
            "origin_instance": post.origin_instance,
            "is_remote": post.is_remote,
            "created_at": post.created_at.isoformat()
        }
        for post in posts
    ]



@app.delete("/delete/{post_id}")
def delete_post(post_id:str,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    post = db.query(Post).filter(Post.id==post_id).first()


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
        is_delivered=False
    )
    db.add(activity)
    db.delete(post)
    db.commit()
    db.refresh(activity)

    deliver_activity(activity)
    db.commit()

    return {"status":"deleted"}
        

@app.post("/inbox/delete")
def delete_remote_post(id:str,db:Session=Depends(get_db)):
    post = db.query(Post).filter(Post.id==id,Post.is_remote==True).first()
    if not post:
        return {"status":"ignored"}

    db.delete(post)
    db.commit()
    return {"status":"deleted"}


# @app.get("/get_user/{username}")
# def getUser(username:str,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
#     db_user = db.query(User).filter(User.username==username).first()

#     if not db_user:
#         raise HTTPException(status_code=404,detail="User not found")
    

#     post_count = (db.query(func.count(Post.id)).filter(Post.user_id == db_user.id).scalar())


#     return {
#         "id" : db_user.id,
#         "username" : db_user.username,
#         "email" : db_user.email,
#         "post_count": post_count
#     }

@app.get("/get_user/{username}")
def get_user_profile(
    username: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_user = db.query(User).filter(User.username == username).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    posts = (
        db.query(Post)
        .filter(
            Post.user_id == db_user.id,
            Post.is_remote == False
        )
        .order_by(desc(Post.created_at))
        .all()
    )

    return {
        "id": db_user.id,
        "username": db_user.username,
        "email": db_user.email,
        "post_count": len(posts),
        "posts": [
            {
                "id": post.id,
                "content": post.content,
                "created_at": post.created_at.isoformat()
            }
            for post in posts
        ]
    }

@app.post("/users/{username}/outbox")
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



@app.get("/random_users")
def random_users(db: Session = Depends(get_db)):
    users = (
        db.query(User)
        .order_by(func.random())
        .limit(5)
        .all()
    )

    return [
        {
            "id": u.id,
            "username": u.username,
            "email": u.email
        }
        for u in users
    ]
