from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pwdlib import PasswordHash
from pydantic import BaseModel
from sqlmodel import select

from db import SessionDep
from models import User

password_hasher = PasswordHash.recommended()  # argon2

# Verified against when the username doesn't exist, so a wrong username takes
# as long as a wrong password and can't be told apart by timing.
_DUMMY_HASH = password_hasher.hash("not-a-real-password")


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def get_current_user(request: Request, session: SessionDep) -> User:
    user_id = request.session.get("user_id")
    user = session.get(User, user_id) if user_id is not None else None
    if user is None:
        request.session.clear()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class Me(BaseModel):
    username: str


@router.post("/login", response_model=Me)
def login(req: LoginRequest, request: Request, session: SessionDep):
    user = session.exec(select(User).where(User.username == req.username)).first()
    if user is None:
        password_hasher.verify(req.password, _DUMMY_HASH)
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid username or password"
        )
    if not password_hasher.verify(req.password, user.password_hash):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid username or password"
        )

    request.session.clear()
    request.session["user_id"] = user.id
    return Me(username=user.username)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request) -> None:
    request.session.clear()


@router.get("/me", response_model=Me)
def me(user: CurrentUser):
    return Me(username=user.username)
