from fastapi import APIRouter
import time
from routers.posts import redis_client

router = APIRouter()

@router.get("/debug/redis-health")
async def redis_health():
    try:
        # Test write
        redis_client.set("health:test", "ok", ex=30)

        # Test read
        value = redis_client.get("health:test")

        # Fetch stats
        info = redis_client.info("stats")

        return {
            "status": "connected",
            "ping": redis_client.ping(),
            "test_value": value,
            "keyspace_hits": info.get("keyspace_hits"),
            "keyspace_misses": info.get("keyspace_misses"),
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
        }