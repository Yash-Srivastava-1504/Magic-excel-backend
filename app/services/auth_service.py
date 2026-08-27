from app.config import settings
from app.models.schemas import User
from app.models.database import get_supabase
from jose import jwt
from datetime import datetime, timedelta
from typing import Optional


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=15))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


async def authenticate_user(username: str, passcode: str) -> Optional[User]:
    try:
        sb = get_supabase()
        res = sb.table("users").select("id, username, passcode").eq("username", username).single().execute()
        user_data = res.data
        if not user_data or user_data.get("passcode") != passcode:
            return None
        return User(id=str(user_data["id"]), username=user_data["username"])
    except Exception as e:
        print(f"Auth error: {e}")
        return None


async def register_user(username: str, passcode: str) -> Optional[User]:
    try:
        sb = get_supabase()
        # Check if username already exists
        existing = sb.table("users").select("id").eq("username", username).execute()
        if existing.data:
            return None
        # Insert new user
        res = sb.table("users").insert({"username": username, "passcode": passcode}).execute()
        new_user = res.data[0] if res.data else None
        if not new_user:
            return None
        return User(id=str(new_user["id"]), username=new_user["username"])
    except Exception as e:
        print(f"Register error: {e}")
        return None
