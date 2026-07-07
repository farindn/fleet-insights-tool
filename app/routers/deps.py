"""Shared FastAPI dependencies."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings

bearer = HTTPBearer()
# HS256 + SESSION_SECRET are the JWT signing basis: tokens are minted with this
# symmetric algorithm and secret in app/routers/auth.py, and verified with the
# same pair here. This is the inverse of the encode step in auth.py.
ALGORITHM = "HS256"


def get_credentials(
    auth: HTTPAuthorizationCredentials = Depends(bearer),
) -> dict:
    """Decode the Bearer JWT back into the MyGeotab credentials dict.

    Used as a FastAPI dependency to authenticate protected endpoints. Verifies
    the token's signature/expiry against SESSION_SECRET using HS256, then returns
    the embedded credentials: ``username``, ``password``, ``database``, and
    ``server`` (defaulting to "my.geotab.com" when the claim is absent).

    Raises HTTP 401 if the token is missing required claims, tampered with, or
    expired (surfaced as a JWTError).
    """
    try:
        payload = jwt.decode(auth.credentials, settings.SESSION_SECRET, algorithms=[ALGORITHM])
    except JWTError as exc:
        # Signature mismatch, malformed token, or expiry all raise JWTError —
        # collapse them into a single 401 so the client re-authenticates.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
        )
    return {
        "username": payload["sub"],
        "password": payload["password"],
        "database": payload["database"],
        # server was optional on older tokens; default to the federation server.
        "server": payload.get("server", "my.geotab.com"),
    }
