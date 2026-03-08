from supabase import create_client

from app.config import settings

SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_KEY = settings.SUPABASE_SERVICE_KEY

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
