from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from apps.api.dependencies import DbSession
from procureai.db.models import User
from procureai.security.auth import create_access_token, verify_password

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/token")
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession) -> dict[str, str]:
    user = db.scalar(select(User).where(User.email == form.username, User.is_active.is_(True)))
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return {
        "access_token": create_access_token(user.email, user.role.value),
        "token_type": "bearer",
    }
