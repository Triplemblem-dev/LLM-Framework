import uuid
import socket
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.config import settings
from app.db import get_db
from app.deps import get_current_user
from app.models import Domain, DomainStatus, RemoteAccessMode, RemoteApiKey
from app.remote_access import get_or_create_remote_config, issue_remote_token
from app.remote_schemas import (
    RemoteAccessStatusOut,
    RemoteAccessUpdate,
    RemoteConnectionTestOut,
    RemoteApiKeyCreate,
    RemoteApiKeyCreatedOut,
    RemoteApiKeyOut,
)
from app.remote_access import validate_remote_bind

router = APIRouter(
    prefix="/remote-access",
    tags=["remote access"],
    dependencies=[Depends(require_auth)],
)


def _key_out(api_key: RemoteApiKey) -> RemoteApiKeyOut:
    return RemoteApiKeyOut(
        id=api_key.id,
        name=api_key.name,
        token_prefix=api_key.token_prefix,
        domain_ids=[uuid.UUID(str(item)) for item in (api_key.allowed_domain_ids or [])],
        requests_per_minute=api_key.requests_per_minute,
        expires_at=api_key.expires_at,
        revoked_at=api_key.revoked_at,
        last_used_at=api_key.last_used_at,
        created_at=api_key.created_at,
    )


def _gateway_running() -> bool:
    try:
        with socket.create_connection(("gateway", 443), timeout=0.35):
            return True
    except OSError:
        return False


def _network_validation(mode: RemoteAccessMode) -> tuple[bool, str | None]:
    if mode == RemoteAccessMode.off:
        return True, None
    try:
        validate_remote_bind(mode, settings.remote_gateway_bind_address)
    except ValueError as exc:
        return False, str(exc)
    return True, None


@router.get("", response_model=RemoteAccessStatusOut)
def get_remote_access(db: Session = Depends(get_db)):
    user = get_current_user(db)
    config = get_or_create_remote_config(db, user.id)
    ca_path = Path(settings.remote_gateway_ca_path)
    network_valid, network_error = _network_validation(config.mode)
    active_keys = (
        db.query(RemoteApiKey)
        .filter_by(user_id=user.id, revoked_at=None)
        .count()
    )
    return RemoteAccessStatusOut(
        mode=config.mode,
        gateway_port=config.gateway_port,
        gateway_configured=bool(settings.remote_gateway_shared_secret.strip()),
        gateway_running=_gateway_running(),
        api_base_url=settings.remote_gateway_public_url.rstrip("/") + "/v1",
        bind_address=settings.remote_gateway_bind_address,
        hostname=settings.remote_gateway_hostname,
        network_configuration_valid=network_valid,
        network_configuration_error=network_error,
        tailscale_configured=(
            config.mode == RemoteAccessMode.private_vpn and network_valid
        ),
        certificate_available=ca_path.is_file(),
        active_key_count=active_keys,
    )


@router.put("", response_model=RemoteAccessStatusOut)
def update_remote_access(body: RemoteAccessUpdate, db: Session = Depends(get_db)):
    user = get_current_user(db)
    config = get_or_create_remote_config(db, user.id)
    if body.mode != RemoteAccessMode.off and not settings.remote_gateway_shared_secret.strip():
        raise HTTPException(
            status_code=409,
            detail="Configure REMOTE_GATEWAY_SHARED_SECRET before enabling remote access",
        )
    if body.mode != RemoteAccessMode.off:
        try:
            validate_remote_bind(body.mode, settings.remote_gateway_bind_address)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    config.mode = body.mode
    config.gateway_port = body.gateway_port
    db.commit()
    return get_remote_access(db)


@router.post("/connection-test", response_model=RemoteConnectionTestOut)
def test_remote_connection(db: Session = Depends(get_db)):
    user = get_current_user(db)
    config = get_or_create_remote_config(db, user.id)
    configured = bool(settings.remote_gateway_shared_secret.strip())
    running = _gateway_running()
    network_valid, network_error = _network_validation(config.mode)
    ready = config.mode != RemoteAccessMode.off and configured and running and network_valid
    if config.mode == RemoteAccessMode.off:
        detail = "Remote access is off. Local framework access remains available."
    elif not configured:
        detail = "The gateway secret is not configured."
    elif not network_valid:
        detail = network_error or "The selected interface is invalid."
    elif not running:
        detail = "The HTTPS gateway is not running."
    else:
        detail = "The gateway is reachable from the framework. Test the displayed HTTPS URL from the client device next."
    return RemoteConnectionTestOut(
        ready=ready,
        mode=config.mode,
        gateway_configured=configured,
        gateway_running=running,
        network_configuration_valid=network_valid,
        detail=detail,
    )


@router.get("/keys", response_model=list[RemoteApiKeyOut])
def list_remote_keys(db: Session = Depends(get_db)):
    user = get_current_user(db)
    keys = (
        db.query(RemoteApiKey)
        .filter_by(user_id=user.id)
        .order_by(RemoteApiKey.created_at.desc())
        .all()
    )
    return [_key_out(item) for item in keys]


@router.post("/keys", response_model=RemoteApiKeyCreatedOut, status_code=201)
def create_remote_key(body: RemoteApiKeyCreate, db: Session = Depends(get_db)):
    user = get_current_user(db)
    unique_ids = list(dict.fromkeys(body.domain_ids))
    owned_ids = {
        row[0]
        for row in db.query(Domain.id)
        .filter(
            Domain.user_id == user.id,
            Domain.status == DomainStatus.active,
            Domain.id.in_(unique_ids),
        )
        .all()
    }
    if owned_ids != set(unique_ids):
        raise HTTPException(status_code=400, detail="One or more domains are unavailable")
    if body.expires_at is not None:
        expiry = body.expires_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry <= datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Expiry must be in the future")

    token, prefix, token_hash = issue_remote_token()
    api_key = RemoteApiKey(
        user_id=user.id,
        name=body.name,
        token_prefix=prefix,
        token_hash=token_hash,
        allowed_domain_ids=[str(item) for item in unique_ids],
        can_chat=True,
        can_upload_documents=False,
        can_admin=False,
        requests_per_minute=body.requests_per_minute,
        expires_at=body.expires_at,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    return RemoteApiKeyCreatedOut(**_key_out(api_key).model_dump(), token=token)


@router.delete("/keys/{key_id}")
def revoke_remote_key(key_id: uuid.UUID, db: Session = Depends(get_db)):
    user = get_current_user(db)
    api_key = db.query(RemoteApiKey).filter_by(id=key_id, user_id=user.id).one_or_none()
    if api_key is None:
        raise HTTPException(status_code=404, detail="Remote API key not found")
    if api_key.revoked_at is None:
        api_key.revoked_at = datetime.now(timezone.utc)
        db.commit()
    return {"ok": True}


@router.get("/certificate")
def download_gateway_certificate():
    path = Path(settings.remote_gateway_ca_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Gateway certificate is not available yet")
    return FileResponse(path, media_type="application/x-x509-ca-cert", filename="llm-framework-ca.crt")
