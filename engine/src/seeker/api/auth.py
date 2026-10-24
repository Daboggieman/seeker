"""Bearer-token authentication for the Seeker API.

All routes except /health require a valid Authorization: Bearer <token> header.
The token is read from the SEEKER_TOKEN environment variable at startup.
When SEEKER_TOKEN is empty (local dev), auth is bypassed entirely.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Read once at startup.
_TOKEN = os.environ.get("SEEKER_TOKEN", "")
AUTH_ENABLED = bool(_TOKEN)

_scheme = HTTPBearer(auto_error=False)


def _reject() -> None:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_auth(
    creds: Annotated[HTTPAuthorizationCredentials | None, Security(_scheme)] = None,
) -> None:
    """FastAPI dependency. Bypassed when AUTH_ENABLED is False (local dev)."""
    if not AUTH_ENABLED:
        return
    if creds is None or creds.scheme.lower() != "bearer":
        _reject()
    if creds.credentials != _TOKEN:
        _reject()
