from app.config import settings
from app.models.schemas import Token, User
from app.models.database import get_db
from jose import jwt
from datetime import datetime, timedelta
from typing import Optional

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

async def authenticate_user(username: str, passcode: str) -> Optional[User]:
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, username, passcode FROM users WHERE username = %s",
                    (username,)
                )
                user_data = cur.fetchone()

                if not user_data or user_data.get("passcode") != passcode:
                    return None

                return User(id=str(user_data["id"]), username=user_data["username"], full_name=user_data.get("full_name"))
    except Exception as e:
        print(f"Auth error: {str(e)}")
        return None

async def get_user_stacks(user_id: str):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM stacks WHERE user_id = %s",
                    (user_id,)
                )
                return cur.fetchall()
    except Exception as e:
        print(f"DB Error fetching stacks: {str(e)}")
        return []
