from fastapi import FastAPI
from app.database import Base, engine
from app.models import Post

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Federated Backend")
