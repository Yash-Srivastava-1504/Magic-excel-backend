from supabase import create_client, Client
from app.config import settings

def get_supabase() -> Client:
    if not settings.SUPABASE_URL or not settings.SUPABASE_SECRET_KEY:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SECRET_KEY must be set in .env")
    return create_client(settings.SUPABASE_URL, settings.SUPABASE_SECRET_KEY)
