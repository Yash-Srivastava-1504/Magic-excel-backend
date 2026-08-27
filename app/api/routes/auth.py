from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from app.services.auth_service import authenticate_user, create_access_token, register_user
from app.models.schemas import Token, User
from datetime import timedelta
from app.config import settings
from pydantic import BaseModel

router = APIRouter()

class UserRegister(BaseModel):
    username: str
    password: str

@router.post("/login", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer", "user_id": user.id}

@router.post("/signup", response_model=User)
async def signup(user_data: UserRegister):
    user = await register_user(user_data.username, user_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already exists"
        )
    return user

@router.get("/me", response_model=User)
async def read_users_me(current_user: User = Depends(authenticate_user)):
    # This is a bit circular for now but demonstrates the pattern.
    # Usually you'd have a get_current_user dependency that decodes the JWT.
    return current_user
