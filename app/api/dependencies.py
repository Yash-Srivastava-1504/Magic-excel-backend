from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from app.config import settings
from app.models.schemas import TokenData, User
from app.models.database import get_supabase

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/v1/auth/login")

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        token_data = TokenData(username=username)
    except JWTError:
        raise credentials_exception

    try:
        sb = get_supabase()
        res = sb.table("users").select("username, full_name").eq("username", token_data.username).execute()
        user_data = res.data[0] if res.data else None
    except Exception as e:
        print(f"Error fetching user: {e}")
        user_data = None

    if user_data is None:
        raise credentials_exception
    return User(username=user_data["username"], full_name=user_data.get("full_name"))
