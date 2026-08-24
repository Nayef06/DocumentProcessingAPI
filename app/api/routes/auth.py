import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, Token, UserCreate, UserPublic
from app.schemas.error import ErrorResponse


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Register a user",
    responses={
        status.HTTP_409_CONFLICT: {
            "model": ErrorResponse,
            "description": "The email address is already registered.",
        }
    },
)
def register_user(
    registration: UserCreate,
    db: Annotated[Session, Depends(get_db)],
) -> User:
    email = str(registration.email).lower()
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user is not None:
        logger.info("Duplicate user registration rejected")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )

    user = User(
        email=email,
        hashed_password=hash_password(registration.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.info("Concurrent duplicate user registration rejected")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        ) from exc
    db.refresh(user)
    logger.info("User registered user_id=%s", user.id)
    return user


@router.post(
    "/login",
    response_model=Token,
    summary="Log in",
    description="Validate credentials and return a Bearer access token.",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "The supplied credentials are invalid.",
        }
    },
)
def login(
    credentials: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> Token:
    email = str(credentials.email).lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(
        credentials.password, user.hashed_password
    ):
        logger.info("Login rejected due to invalid credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.info("User authenticated user_id=%s", user.id)
    return Token(
        access_token=create_access_token(user.id),
        token_type="bearer",
    )


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Get the current user",
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "model": ErrorResponse,
            "description": "A valid Bearer token is required.",
        }
    },
)
def read_current_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    return current_user
