"""Authentication and policy enforcement for the optional remote API."""

import hashlib
import hmac
import secrets
import ipaddress
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import RemoteAccessConfig, RemoteAccessMode, RemoteApiKey, User


@dataclass(frozen=True)
class RemotePrincipal:
    user: User
    api_key: RemoteApiKey


_request_windows: dict[uuid.UUID, deque[float]] = defaultdict(deque)
_request_windows_lock = threading.Lock()
_failed_auth_windows: dict[str, deque[float]] = defaultdict(deque)


def issue_remote_token() -> tuple[str, str, str]:
    """Return (plaintext, display prefix, hash); plaintext is never persisted."""
    token = "llmf_" + secrets.token_urlsafe(32)
    return token, token[:13], hash_remote_token(token)


def hash_remote_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_or_create_remote_config(db: Session, user_id: uuid.UUID) -> RemoteAccessConfig:
    config = db.query(RemoteAccessConfig).filter_by(user_id=user_id).one_or_none()
    if config is None:
        config = RemoteAccessConfig(user_id=user_id, mode=RemoteAccessMode.off)
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def validate_remote_bind(mode: RemoteAccessMode, raw_address: str) -> str:
    address = raw_address.strip()
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as exc:
        raise ValueError("Choose one explicit host interface IP address") from exc
    if mode == RemoteAccessMode.off:
        return address
    if parsed.is_unspecified or parsed.is_loopback or parsed.is_multicast:
        raise ValueError("Remote access cannot use a wildcard, loopback, or multicast address")
    if mode == RemoteAccessMode.local_network:
        if not (parsed.is_private or parsed.is_link_local):
            raise ValueError("Local-network mode requires a private LAN address")
        return address
    tailscale_v4 = ipaddress.ip_network("100.64.0.0/10")
    tailscale_v6 = ipaddress.ip_network("fd7a:115c:a1e0::/48")
    if parsed not in tailscale_v4 and parsed not in tailscale_v6:
        raise ValueError("Private VPN mode requires this host's Tailscale IP address")
    return address


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=401,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _failed_authentication(client_address: str) -> HTTPException:
    now = time.monotonic()
    cutoff = now - 60
    limit = settings.remote_api_failed_auth_limit
    with _request_windows_lock:
        window = _failed_auth_windows[client_address]
        while window and window[0] <= cutoff:
            window.popleft()
        if len(window) >= limit:
            retry_after = max(1, int(60 - (now - window[0])))
            return HTTPException(
                status_code=429,
                detail="Too many failed authentication attempts",
                headers={"Retry-After": str(retry_after)},
            )
        window.append(now)
    return _unauthorized("Invalid remote API key")


def _enforce_rate_limit(api_key: RemoteApiKey) -> None:
    now = time.monotonic()
    cutoff = now - 60
    limit = max(1, min(600, api_key.requests_per_minute))
    with _request_windows_lock:
        window = _request_windows[api_key.id]
        while window and window[0] <= cutoff:
            window.popleft()
        if len(window) >= limit:
            retry_after = max(1, int(60 - (now - window[0])))
            raise HTTPException(
                status_code=429,
                detail="Remote API rate limit exceeded",
                headers={"Retry-After": str(retry_after)},
            )
        window.append(now)


def require_remote_principal(
    authorization: str | None = Header(default=None),
    gateway_secret: str | None = Header(default=None, alias="X-LLMF-Gateway-Secret"),
    client_address: str | None = Header(default=None, alias="X-LLMF-Client-IP"),
    db: Session = Depends(get_db),
) -> RemotePrincipal:
    """Require a gateway-originated request and a valid per-device API key."""
    expected_gateway_secret = settings.remote_gateway_shared_secret.strip()
    if not expected_gateway_secret:
        raise HTTPException(status_code=503, detail="Remote API gateway is not configured")
    if gateway_secret is None or not hmac.compare_digest(gateway_secret, expected_gateway_secret):
        raise _unauthorized("Request did not come through the configured gateway")

    config = db.query(RemoteAccessConfig).first()
    if config is None or config.mode == RemoteAccessMode.off:
        raise HTTPException(status_code=503, detail="Remote access is turned off")

    if authorization is None or not authorization.startswith("Bearer "):
        raise _failed_authentication(client_address or "unknown")
    token = authorization.removeprefix("Bearer ").strip()
    if not token.startswith("llmf_"):
        raise _failed_authentication(client_address or "unknown")

    api_key = db.query(RemoteApiKey).filter_by(token_hash=hash_remote_token(token)).one_or_none()
    if api_key is None or not hmac.compare_digest(api_key.token_hash, hash_remote_token(token)):
        raise _failed_authentication(client_address or "unknown")
    if api_key.revoked_at is not None:
        raise _failed_authentication(client_address or "unknown")
    now = datetime.now(timezone.utc)
    if api_key.expires_at is not None:
        expiry = api_key.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= now:
            raise _failed_authentication(client_address or "unknown")
    if not api_key.can_chat:
        raise HTTPException(status_code=403, detail="This remote API key cannot use chat")

    _enforce_rate_limit(api_key)
    user = db.get(User, api_key.user_id)
    if user is None:
        raise _unauthorized("Remote API key owner no longer exists")
    api_key.last_used_at = now
    db.commit()
    return RemotePrincipal(user=user, api_key=api_key)


def require_domain_access(principal: RemotePrincipal, domain_id: uuid.UUID) -> None:
    allowed = {str(item) for item in (principal.api_key.allowed_domain_ids or [])}
    if str(domain_id) not in allowed:
        # A 404 avoids confirming that an unapproved private domain exists.
        raise HTTPException(status_code=404, detail="Model not found")
