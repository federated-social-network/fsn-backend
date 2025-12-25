from fastapi import FastAPI
from app.database import Base, engine
from app.models import Post

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
    other_instance_inbox = "https://localhost:8001/inbox"
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