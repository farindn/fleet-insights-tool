"""Authentication router: POST /api/auth"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import mygeotab
from fastapi import APIRouter, HTTPException
from jose import jwt

from app.config import settings
from app.schemas.auth import AuthRequest, AuthResponse
from app.services.geotab import GeotabClient

router = APIRouter()

ALGORITHM = "HS256"


@router.post("/api/auth", response_model=AuthResponse)
async def authenticate(body: AuthRequest):
    """Authenticate against MyGeotab and return a signed JWT."""
    import asyncio

    api = mygeotab.API(
        username=body.username,
        password=body.password,
        database=body.database,
        server=body.server,
    )
    try:
        await asyncio.to_thread(api.authenticate)
    except mygeotab.exceptions.AuthenticationException as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"MyGeotab error: {exc}")

    # Fetch user's displayCurrency using the authenticated API
    import logging
    currency = "USD"
    try:
        users = await asyncio.to_thread(api.get, "User", search={"name": body.username})
        if users and len(users) > 0:
            user = users[0]
            dc = user.get("displayCurrency")
            logging.info(f"MyGeotab displayCurrency for {body.username}: {dc!r}")
            if dc:
                raw = ""
                if isinstance(dc, str):
                    raw = dc
                elif isinstance(dc, dict):
                    raw = dc.get("id", "") or dc.get("code", "")
                # Strip "Currency" prefix if present (MyGeotab returns "CurrencyIDR" etc.)
                if raw.startswith("Currency"):
                    raw = raw[len("Currency"):]
                raw = raw.upper().strip()
                # Validate that we have a 3-letter code
                if len(raw) == 3:
                    currency = raw
                else:
                    logging.warning(f"Invalid currency code after parsing: {raw!r} (from {dc!r})")
    except Exception as e:
        logging.warning(f"Failed to fetch user currency: {e}")
        currency = "USD"

    logging.info(f"Final currency for {body.username}: {currency}")

    payload = {
        "sub": body.username,
        "database": body.database,
        "server": body.server,
        "password": body.password,  # stored in JWT, transmitted over HTTPS only
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS),
    }
    token = jwt.encode(payload, settings.SESSION_SECRET, algorithm=ALGORITHM)

    return AuthResponse(token=token, username=body.username, database=body.database, currency=currency)
