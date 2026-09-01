import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.db import get_db
from app.models import Model, ModelProfile
from app.runtime_client import list_installed_models, provider_capabilities
from app.schemas import ModelInstalledOut, ModelProfileOut, ModelProfileSet

router = APIRouter(prefix="/models", tags=["models"], dependencies=[Depends(require_auth)])


@router.get("/providers")
def providers():
    return provider_capabilities()


@router.get("/installed", response_model=list[ModelInstalledOut])
def installed():
    try:
        raw = list_installed_models()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach a configured local model runtime: {exc}") from exc
    return [
        ModelInstalledOut(
            name=m["name"],
            tag=m["model"],
            size_bytes=m.get("size", 0),
            parameter_size=m.get("details", {}).get("parameter_size"),
            quantization_level=m.get("details", {}).get("quantization_level"),
            context_length=m.get("details", {}).get("context_length"),
            modified_at=m.get("modified_at"),
        )
        for m in raw
    ]


@router.get("/profile", response_model=ModelProfileOut | None)
def get_active_profile(db: Session = Depends(get_db)):
    profile = db.query(ModelProfile).filter_by(is_active=True).one_or_none()
    if profile is None:
        return None
    return ModelProfileOut(
        id=profile.id,
        tag=profile.model.ollama_tag,
        name=profile.name,
        context_length=profile.context_length,
        temperature=profile.temperature,
        top_p=profile.top_p,
        top_k=profile.top_k,
        repeat_penalty=profile.repeat_penalty,
    )


@router.put("/profile", response_model=ModelProfileOut)
def set_active_profile(body: ModelProfileSet, db: Session = Depends(get_db)):
    try:
        installed_models = {m["model"]: m for m in list_installed_models()}
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach a configured local model runtime: {exc}") from exc

    info = installed_models.get(body.ollama_tag)
    if info is None:
        raise HTTPException(status_code=400, detail=f"'{body.ollama_tag}' is not available from a configured local runtime")

    model = db.query(Model).filter_by(ollama_tag=body.ollama_tag).one_or_none()
    if model is None:
        details = info.get("details", {})
        model = Model(
            name=info["name"],
            ollama_tag=body.ollama_tag,
            architecture=details.get("family"),
            parameter_count=details.get("parameter_size"),
            quantization=details.get("quantization_level"),
            file_size_bytes=info.get("size"),
        )
        db.add(model)
        db.flush()

    profile = db.query(ModelProfile).filter_by(model_id=model.id).one_or_none()
    if profile is None:
        profile = ModelProfile(model_id=model.id)
        db.add(profile)
        db.flush()

    db.query(ModelProfile).filter(ModelProfile.id != profile.id).update({"is_active": False})
    profile.is_active = True
    db.commit()
    db.refresh(profile)

    return ModelProfileOut(
        id=profile.id,
        tag=model.ollama_tag,
        name=profile.name,
        context_length=profile.context_length,
        temperature=profile.temperature,
        top_p=profile.top_p,
        top_k=profile.top_k,
        repeat_penalty=profile.repeat_penalty,
    )
