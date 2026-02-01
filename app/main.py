from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import Base, engine
from app.routers import auth, posts, users, federation

# Create Tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Federated Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth.router, tags=["Auth"])
app.include_router(posts.router, tags=["Posts"])
app.include_router(users.router, tags=["Users"])
app.include_router(federation.router, tags=["Federation"])

@app.get("/")
def homePage():
    return {"message": "server is running..."}