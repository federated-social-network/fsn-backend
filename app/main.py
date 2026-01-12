from fastapi import FastAPI, HTTPException
from app.database import Base, engine
from app.models import Post,User
import uuid
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi import Depends
from app.database import SessionLocal
from app.config import settings
import httpx
from jose import jwt, JWTError
from datetime import datetime, timedelta
from fastapi import Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func

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

@app.get("/")
def homePage():
    return{"message":"server is running..."}


@app.post("/posts")
def create_post(content:str,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
        
    post = Post(
        id=str(uuid.uuid4()),
        content = content,
        user_id=user.id,
        author=user.username,
        origin_instance=settings.INSTANCE_NAME,
        is_remote=False
    )

    db.add(post)
    db.commit()
    db.refresh(post)

    if settings.SEND_TO_OTHER_INSTANCE:
        pass
        
    return post

@app.post("/inbox")
def inbox(id:str,content:str,author:str,origin_instance:str,db:Session=Depends(get_db)):
    post = Post(
        id=id,
        content=content,
        user_id=None,
        author=author,
        origin_instance=origin_instance,
        is_remote=True
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return {"status":"accepted"}


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

@app.get("/get_posts")
def get_posts(db:Session=Depends(get_db)):
    posts = db.query(Post).order_by(Post.id.desc()).all()
    return posts

@app.delete("/delete/{post_id}")
def delete_post(post_id:str,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    post = db.query(Post).filter(Post.id==post_id).first()


    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if post.is_remote:
        raise HTTPException(status_code=403, detail="Cannot delete remote post")
    
    if post.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not allowed")
    
    db.delete(post)
    db.commit()

    if settings.SEND_TO_OTHER_INSTANCE: 
        pass
        

@app.post("/inbox/delete")
def delete_remote_post(id:str,db:Session=Depends(get_db)):
    post = db.query(Post).filter(Post.id==id,Post.is_remote==True).first()
    if not post:
        return {"status":"ignored"}

    db.delete(post)
    db.commit()
    return {"status":"deleted"}


@app.get("/get_user/{username}")
def getUser(username:str,user:User=Depends(get_current_user),db:Session=Depends(get_db)):
    db_user = db.query(User).filter(User.username==username).first()

    if not db_user:
        raise HTTPException(status_code=404,detail="User not found")
    

    post_count = (db.query(func.count(Post.id)).filter(Post.user_id == db_user.id).scalar())


    return {
        "id" : db_user.id,
        "username" : db_user.username,
        "email" : db_user.email,
        "post_count": post_count
    }