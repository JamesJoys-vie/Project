from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.schemas.auth import LoginRequest, TokenResponse, UserProfile

router = APIRouter()


@router.post("/auth/login", response_model=TokenResponse, responses={401: {"description": "Invalid credentials"}})
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """TODO: look up user, verify bcrypt hash (shared.security.verify_password), return JWT (create_access_token)."""
    raise HTTPException(501, "Not implemented")


@router.get("/users/me", response_model=UserProfile, responses={401: {"description": "Unauthenticated"}})
def me(x_user_id: str = Header(...), db: Session = Depends(get_db)):
    """TODO: return profile of the user id injected by the gateway (X-User-Id). Read-only for the client."""
    raise HTTPException(501, "Not implemented")
