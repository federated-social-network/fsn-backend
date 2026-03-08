from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import Base, engine
from app.routers import auth, posts, users, federation, moderation, chat, notifications

# Create Tables

app = FastAPI(title="Federated Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://heliix.live", "https://heliix.pages.dev", "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Include Routers
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(posts.router, tags=["Posts"])
app.include_router(users.router, tags=["Users"])
app.include_router(federation.router, tags=["Federation"])
app.include_router(moderation.router, tags=["Moderation"])
app.include_router(chat.router, tags=["Chat"])
app.include_router(notifications.router, tags=["Notification"])


@app.get("/")
def homePage():
    return {"message": "server is running..."}
