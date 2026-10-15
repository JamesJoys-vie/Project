from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.db import get_db
from app.domain.models import User
from app.schemas.auth import LoginRequest, TokenResponse, UserProfile
from shared.security import create_access_token, hash_password, verify_password

router = APIRouter()

# Compared against when the username is unknown, so a miss costs the same bcrypt time as a wrong password
# (response time does not reveal which usernames exist).
_DUMMY_HASH = hash_password("not-a-real-password")


def _profile(user: User) -> UserProfile:
    return UserProfile(id=user.id, username=user.username, full_name=user.full_name, phone=user.phone, email=user.email)


@router.post("/auth/login", response_model=TokenResponse, responses={401: {"description": "Invalid credentials"}})
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == body.username))
    try:
        ok = verify_password(body.password, user.password_hash if user else _DUMMY_HASH)
    except ValueError:  # malformed stored hash
        ok = False
    if not (user and ok):
        raise HTTPException(401, "Invalid username or password")
    token = create_access_token(user.id, settings.jwt_secret, settings.jwt_expire_minutes)
    return TokenResponse(access_token=token, expires_in=settings.jwt_expire_minutes * 60)


@router.get("/users/me", response_model=UserProfile, responses={401: {"description": "Unauthenticated"}})
def me(x_user_id: str = Header(...), db: Session = Depends(get_db)):
    """Profile of the user id injected by the gateway (X-User-Id). Read-only for the client."""
    user = db.get(User, x_user_id)
    if user is None:  # token for a user that no longer exists
        raise HTTPException(401, "Unknown user")
    return _profile(user)


# ---- internal endpoint (called by payment-service only; NOT routed by the gateway) ----
@router.get("/internal/users/{user_id}", response_model=UserProfile, responses={404: {"description": "Not found"}})
def get_user(user_id: str, db: Session = Depends(get_db)):
    """Payer contact details (email, name) needed for the OTP / receipt emails."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "User not found")
    return _profile(user)
