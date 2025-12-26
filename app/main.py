from fastapi import FastAPI
from app.database import Base, engine
from app.models import Post,User
import uuid
from sqlalchemy.orm import Session
from fastapi import Depends
from app.database import SessionLocal
from app.config import settings
import httpx

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Federated Backend")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def send_to_other_instance(post):
    other_instance_inbox = "http://localhost:8001/inbox"
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


@app.post("/posts")
def create_post(content:str,author:str,db:Session=Depends(get_db)):
    post = Post(
        content = content,
        author=author,
        origin_instance=settings.INSTANCE_NAME,
        is_remote=False
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    if settings.SEND_TO_OTHER_INSTANCE:
        send_to_other_instance(post)
        
    return post

@app.post("/inbox")
def inbox(id:str,content:str,author:str,origin_instance:str,db:Session=Depends(get_db)):
    post = Post(
        id=id,
        content=content,
        author=author,
        origin_instance=origin_instance,
        is_remote=True
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return {"status":"accepted"}


@app.post("/register")
def register(username:str,password:str,db:Session=Depends(get_db)):
    user = User(
        id=str(uuid.uuid4()),
        username=username,
        password_hash=User.hash_password(password)
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message":"user created"}


@app.post("/login")
def login(username:str,password:str,db:Session=Depends(get_db)):
    user = db.query(User).filter(User.username==username).first()
    if not user or not user.verify_password(password):
        return {"error":"invalid credentials"}
    return {"message":"login success"}