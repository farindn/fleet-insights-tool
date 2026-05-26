"""Shared FastAPI dependencies."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings

bearer = HTTPBearer()
ALGORITHM = "HS256"


def get_credentials(
    auth: HTTPAuthorizationCredentials = Depends(bearer),
) -> dict:
    """Decode the JWT and return the credentials dict."""
    try:
        payload = jwt.decode(auth.credentials, settings.SESSION_SECRET, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
        )
    return {
        "username": payload["sub"],
        "password": payload["password"],
        "database": payload["database"],
        "server": payload.get("server", "my.geotab.com"),
    }
