"""Pydantic models for the MyGeotab authentication flow.

Defines the request/response payloads exchanged by the login endpoint:
``AuthRequest`` carries the credentials the user submits on the login screen,
and ``AuthResponse`` carries the session token and profile details returned on
a successful sign-in. See USER_GUIDE.md -> "Logging In".
"""

from pydantic import BaseModel


class AuthRequest(BaseModel):
    """Credentials submitted from the login screen to authenticate with MyGeotab."""

    username: str
    password: str
    database: str
    # Federation entry point, not the user's specific server. Authentication
    # always goes through the standard my.geotab.com federation server, which
    # resolves the account's actual data server automatically (guide -> "Logging In").
    server: str = "my.geotab.com"


class AuthResponse(BaseModel):
    """Session details returned to the client after a successful sign-in."""

    token: str
    username: str
    database: str
    # Fallback only. The real currency is auto-detected from the user's MyGeotab
    # profile and pre-selected on the config screen (the user can still change it);
    # USD is used only when detection yields nothing (guide -> "Logging In").
    currency: str = "USD"
