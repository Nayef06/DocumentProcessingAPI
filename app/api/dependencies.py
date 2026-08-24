import logging
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.models.user import User


logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(
    bearerFormat="JWT",
    description="JWT access token returned by the login endpoint.",
    auto_error=False,
)


def _credentials_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None:
        logger.info("Protected endpoint requested without Bearer credentials")
        raise _credentials_exception()

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            options={"require": ["sub", "exp"]},
        )
        subject = payload.get("sub")
        if not isinstance(subject, str):
            raise _credentials_exception()
        user_id = int(subject)
    except (InvalidTokenError, TypeError, ValueError) as exc:
        logger.info("Protected endpoint requested with invalid Bearer credentials")
        raise _credentials_exception() from exc

    user = db.get(User, user_id)
    if user is None:
        logger.info("Bearer token subject does not identify an active user")
        raise _credentials_exception()
    return user
