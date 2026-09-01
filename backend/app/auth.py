import hmac

from fastapi import Header, HTTPException

from app.config import settings


def require_auth(authorization: str | None = Header(default=None)) -> None:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    if not hmac.compare_digest(token, settings.app_access_token):
        raise HTTPException(status_code=401, detail="Invalid token")
