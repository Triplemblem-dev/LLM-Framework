from fastapi import APIRouter, Depends

from app.auth import require_auth

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/verify", dependencies=[Depends(require_auth)])
def verify() -> dict:
    return {"ok": True}
