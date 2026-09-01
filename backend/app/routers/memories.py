import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.auth import require_auth
from app.db import get_db
from app.deps import get_current_user
from app.models import Conversation, Memory
from app.prompt_assembly import sharing_siblings
from app.routers.domains import get_domain_or_404
from app.schemas import InheritedMemoryOut, MemoryCreate, MemoryOut, MemoryUpdate

router = APIRouter(prefix="/domains", tags=["memories"], dependencies=[Depends(require_auth)])


def get_memory_or_404(db: Session, domain_id: uuid.UUID, memory_id: uuid.UUID) -> Memory:
    memory = db.get(Memory, memory_id)
    if memory is None or memory.scope_id != domain_id:
        raise HTTPException(status_code=404, detail="Memory not found in this scope")
    return memory


@router.post("/{domain_id}/memories", response_model=MemoryOut)
def create_memory(domain_id: uuid.UUID, body: MemoryCreate, db: Session = Depends(get_db)):
    user = get_current_user(db)
    scope = get_domain_or_404(db, domain_id)

    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Memory content is required")

    conversation_id = None
    if body.conversation_id is not None:
        conv = db.get(Conversation, body.conversation_id)
        # a conversation_id from a different scope is silently dropped rather than erroring -
        # Same unauthorized-scope-reference posture as prompt-preview.
        if conv is not None and conv.domain_id == scope.id:
            conversation_id = conv.id

    memory = Memory(user_id=user.id, scope_id=scope.id, conversation_id=conversation_id, content=content)
    db.add(memory)
    db.commit()
    db.refresh(memory)
    return memory


@router.get("/{domain_id}/memories", response_model=list[MemoryOut])
def list_memories(domain_id: uuid.UUID, db: Session = Depends(get_db)):
    get_domain_or_404(db, domain_id)
    return (
        db.query(Memory)
        .filter_by(scope_id=domain_id)
        .order_by(Memory.created_at.desc())
        .all()
    )


@router.get("/{domain_id}/memories/inherited", response_model=list[InheritedMemoryOut])
def list_inherited_memories(domain_id: uuid.UUID, db: Session = Depends(get_db)):
    """Read-only view of memories visible to this scope via inheritance/sibling-sharing but
    owned elsewhere - mirrors documents/inherited and prompt_assembly.approved_scope_ids
    so this list always matches what the assembled prompt can actually see."""
    scope = get_domain_or_404(db, domain_id)
    other_scopes = []
    if scope.parent_domain_id is not None and scope.inheritance.value == "inherited":
        other_scopes.append(scope.parent)
    other_scopes += sharing_siblings(db, scope)
    if not other_scopes:
        return []

    results = []
    for other in other_scopes:
        memories = db.query(Memory).filter_by(scope_id=other.id).order_by(Memory.created_at.desc()).all()
        for m in memories:
            results.append(
                InheritedMemoryOut(
                    id=m.id,
                    content=m.content,
                    conversation_id=m.conversation_id,
                    created_at=m.created_at,
                    updated_at=m.updated_at,
                    scope_id=other.id,
                    scope_name=other.name,
                )
            )
    return results


@router.patch("/{domain_id}/memories/{memory_id}", response_model=MemoryOut)
def update_memory(domain_id: uuid.UUID, memory_id: uuid.UUID, body: MemoryUpdate, db: Session = Depends(get_db)):
    memory = get_memory_or_404(db, domain_id, memory_id)
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Memory content is required")
    memory.content = content
    db.commit()
    db.refresh(memory)
    return memory


@router.delete("/{domain_id}/memories/{memory_id}")
def delete_memory(domain_id: uuid.UUID, memory_id: uuid.UUID, db: Session = Depends(get_db)):
    get_memory_or_404(db, domain_id, memory_id)
    db.execute(delete(Memory).where(Memory.id == memory_id))
    db.commit()
    return {"ok": True}
