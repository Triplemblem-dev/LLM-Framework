import enum
import uuid
from datetime import datetime
from pathlib import Path

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, BigInteger, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.db import Base


def _uuid_col():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class InheritancePolicy(str, enum.Enum):
    private = "private"
    inherited = "inherited"


class DomainStatus(str, enum.Enum):
    active = "active"
    archived = "archived"


class MessageRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"


class DocumentStatus(str, enum.Enum):
    pending = "pending"
    ready = "ready"
    failed = "failed"


class RepositoryStatus(str, enum.Enum):
    validating = "validating"
    indexing = "indexing"
    ready = "ready"
    failed = "failed"
    deleting = "deleting"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_col()
    email: Mapped[str] = mapped_column(unique=True)
    demo_seeded: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Model(Base):
    """Static artifact info for a model known to the framework (mirrors an Ollama tag)."""

    __tablename__ = "models"

    id: Mapped[uuid.UUID] = _uuid_col()
    name: Mapped[str]
    ollama_tag: Mapped[str] = mapped_column(unique=True)
    architecture: Mapped[str | None]
    parameter_count: Mapped[str | None]
    quantization: Mapped[str | None]
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    profiles: Mapped[list["ModelProfile"]] = relationship(back_populates="model")


class ModelProfile(Base):
    """Runtime configuration for a model. Exactly one row across the table has is_active=True."""

    __tablename__ = "model_profiles"

    id: Mapped[uuid.UUID] = _uuid_col()
    model_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(default="default")
    context_length: Mapped[int] = mapped_column(default=8192)
    temperature: Mapped[float] = mapped_column(default=0.7)
    top_p: Mapped[float] = mapped_column(default=0.9)
    top_k: Mapped[int] = mapped_column(default=40)
    repeat_penalty: Mapped[float] = mapped_column(default=1.1)
    is_active: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    model: Mapped["Model"] = relationship(back_populates="profiles")


class Domain(Base):
    """A domain or sub-domain. Sub-domains are rows with a non-null parent_domain_id.

    Two-level nesting is enforced at the application layer in routers/domains.py,
    rather than by the database schema.
    """

    __tablename__ = "domains"

    id: Mapped[uuid.UUID] = _uuid_col()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    parent_domain_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("domains.id", ondelete="CASCADE")
    )
    name: Mapped[str]
    slug: Mapped[str]
    description: Mapped[str] = mapped_column(Text, default="")
    scope_prompt: Mapped[str] = mapped_column(Text, default="")
    prompt_layer_overrides: Mapped[dict] = mapped_column(JSON, default=dict)
    model_settings: Mapped[dict] = mapped_column(JSON, default=dict)
    """Sparse, per-scope owner opt-outs keyed by stable prompt-layer key.

    Missing keys are enabled by default. The API only accepts the allowlisted keys in
    prompt_assembly. This changes model input, never server-side authorization.
    """
    inheritance: Mapped[InheritancePolicy] = mapped_column(default=InheritancePolicy.inherited)
    share_with_siblings: Mapped[bool] = mapped_column(default=False)
    """Off by default. When on, this sub-domain's own prompt is additionally exposed to its
    siblings (other sub-domains under the same parent) as a shared-context layer. One-directional
    and per-domain, not a mutual pair-wise agreement: enabling it on domain A lets A's siblings
    read A, regardless of whether they enable it themselves. Conversation history remains
    isolated per conversation unconditionally."""
    status: Mapped[DomainStatus] = mapped_column(default=DomainStatus.active)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    parent: Mapped["Domain | None"] = relationship(remote_side=[id], back_populates="children")
    children: Mapped[list["Domain"]] = relationship(back_populates="parent")


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = _uuid_col()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    domain_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"))
    title: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = _uuid_col()
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    role: Mapped[MessageRole]
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    generation_metrics: Mapped[dict | None] = mapped_column(JSON)
    learning_cards: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class PromptTemplate(Base):
    __tablename__ = "prompt_templates"

    id: Mapped[uuid.UUID] = _uuid_col()
    name: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    versions: Mapped[list["PromptVersion"]] = relationship(back_populates="template")


class PromptVersion(Base):
    """Versioned text for the two static model-input layers."""

    __tablename__ = "prompt_versions"

    id: Mapped[uuid.UUID] = _uuid_col()
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prompt_templates.id", ondelete="CASCADE")
    )
    version_number: Mapped[int]
    layer1_security_rules: Mapped[str] = mapped_column(Text)
    layer2_model_instructions: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    template: Mapped["PromptTemplate"] = relationship(back_populates="versions")


class ScopeAccessLog(Base):
    """Log scope-access checks and retrieval queries."""

    __tablename__ = "scope_access_log"

    id: Mapped[uuid.UUID] = _uuid_col()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    scope_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"))
    approved_scope_ids: Mapped[list] = mapped_column(JSON)
    context: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Document(Base):
    """A single uploaded file owned by exactly one domain or sub-domain.

    Retrievability follows the owning scope's inheritance/share_with_siblings flags exactly like
    a scope's prompt does (see prompt_assembly.approved_scope_ids) - a document does not carry its
    own independent sharing state in v1.
    """

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = _uuid_col()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    scope_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"))
    filename: Mapped[str]
    """Original client-supplied filename, kept for display only - never used to build a path."""
    sanitized_filename: Mapped[str]
    content_hash: Mapped[str]
    source_type: Mapped[str]
    storage_path: Mapped[str]
    folder_path: Mapped[str] = mapped_column(Text, default="")
    tags: Mapped[list] = mapped_column(JSON, default=list)
    version: Mapped[int] = mapped_column(default=1)
    status: Mapped[DocumentStatus] = mapped_column(default=DocumentStatus.pending)
    error: Mapped[str | None] = mapped_column(Text)
    chunk_count: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    @property
    def markdown_filename(self) -> str | None:
        if self.source_type != "pdf":
            return None
        return f"{Path(self.sanitized_filename).stem or 'document'}.md"

    @property
    def markdown_available(self) -> bool:
        if self.source_type != "pdf" or not self.storage_path:
            return False
        return (Path(self.storage_path).parent / f"{self.id}_derived.md").is_file()

    scope: Mapped["Domain"] = relationship()
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentChunk.chunk_index"
    )


class DocumentChunk(Base):
    """One retrievable unit of a document. scope_id is denormalized from the parent document so
    retrieval can filter with `WHERE scope_id = ANY(:approved_scope_ids)` directly against this
    table, so no join back to documents is required on
    the request-latency path.
    """

    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = _uuid_col()
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    scope_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    heading: Mapped[str | None]
    page_number: Mapped[int | None]
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dimensions))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    document: Mapped["Document"] = relationship(back_populates="chunks")


class Memory(Base):
    """A manually saved, scope-owned note. Retrievability follows the
    owning scope's inheritance/share_with_siblings flags exactly like a document does (see
    prompt_assembly.approved_scope_ids) - a memory does not carry its own independent sharing
    state in v1. Unlike documents, memories are not chunked or embedded: v1 expects a small,
    manually-curated set per scope, so every approved memory is included directly in the prompt
    rather than similarity-ranked (see prompt_assembly.MEMORY_LIMIT_LOCAL/SHARED for the cap).
    """

    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = _uuid_col()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    scope_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    """Traceable to its source conversation when saved from chat. Null for
    a memory typed directly into the Memory panel. Deleting the source conversation clears this
    link but keeps the memory - a saved memory is meant to outlive the conversation history it
    came from, unlike a citation, which is tied to the message itself."""
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    scope: Mapped["Domain"] = relationship()


class RetrievalLog(Base):
    """Record what a retrieval query actually returned,
    distinct from ScopeAccessLog's coarser per-request access check. Needed for
    citation-correctness and leakage tests to have something concrete to assert against.
    """

    __tablename__ = "retrieval_logs"

    id: Mapped[uuid.UUID] = _uuid_col()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    scope_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    query_text: Mapped[str] = mapped_column(Text)
    approved_scope_ids: Mapped[list] = mapped_column(JSON)
    retrieved_chunk_ids: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CodeRepository(Base):
    """One immutable, user-approved repository snapshot owned by one exact scope."""

    __tablename__ = "code_repositories"

    id: Mapped[uuid.UUID] = _uuid_col()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    scope_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"))
    name: Mapped[str]
    archive_filename: Mapped[str]
    revision_label: Mapped[str | None]
    content_hash: Mapped[str] = mapped_column(default="")
    storage_path: Mapped[str] = mapped_column(default="")
    status: Mapped[RepositoryStatus] = mapped_column(default=RepositoryStatus.validating)
    error: Mapped[str | None] = mapped_column(Text)
    file_count: Mapped[int] = mapped_column(default=0)
    skipped_file_count: Mapped[int] = mapped_column(default=0)
    security_excluded_count: Mapped[int] = mapped_column(default=0)
    chunk_count: Mapped[int] = mapped_column(default=0)
    exclusions: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    scope: Mapped["Domain"] = relationship()
    grants: Mapped[list["RepositoryGrant"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    files: Mapped[list["CodeFile"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )
    chunks: Mapped[list["CodeChunk"]] = relationship(
        back_populates="repository", cascade="all, delete-orphan"
    )


class RepositoryGrant(Base):
    """Application-enforced exact-scope repository permission; never inherited."""

    __tablename__ = "repository_grants"
    __table_args__ = (UniqueConstraint("repository_id", "scope_id", name="uq_repository_scope_grant"),)

    id: Mapped[uuid.UUID] = _uuid_col()
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("code_repositories.id", ondelete="CASCADE")
    )
    scope_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    repository: Mapped["CodeRepository"] = relationship(back_populates="grants")


class CodeFile(Base):
    __tablename__ = "code_files"
    __table_args__ = (UniqueConstraint("repository_id", "relative_path", name="uq_repository_file_path"),)

    id: Mapped[uuid.UUID] = _uuid_col()
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("code_repositories.id", ondelete="CASCADE")
    )
    relative_path: Mapped[str]
    language: Mapped[str]
    size_bytes: Mapped[int]
    content_hash: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    repository: Mapped["CodeRepository"] = relationship(back_populates="files")
    chunks: Mapped[list["CodeChunk"]] = relationship(
        back_populates="file", cascade="all, delete-orphan"
    )


class CodeChunk(Base):
    __tablename__ = "code_chunks"

    id: Mapped[uuid.UUID] = _uuid_col()
    repository_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("code_repositories.id", ondelete="CASCADE")
    )
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("code_files.id", ondelete="CASCADE"))
    scope_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"))
    chunk_index: Mapped[int] = mapped_column(Integer)
    start_line: Mapped[int]
    end_line: Mapped[int]
    symbol: Mapped[str | None]
    content: Mapped[str] = mapped_column(Text)
    search_text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dimensions))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    repository: Mapped["CodeRepository"] = relationship(back_populates="chunks")
    file: Mapped["CodeFile"] = relationship(back_populates="chunks")


class CodeRetrievalLog(Base):
    __tablename__ = "code_retrieval_logs"

    id: Mapped[uuid.UUID] = _uuid_col()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    scope_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("domains.id", ondelete="CASCADE"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE")
    )
    query_text: Mapped[str] = mapped_column(Text)
    repository_ids: Mapped[list] = mapped_column(JSON)
    retrieved_chunk_ids: Mapped[list] = mapped_column(JSON)
    outcome: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class OptimizationRun(Base):
    """A durable, owner-scoped Model Performance Optimizer job.

    Benchmark prompts are identified by ``workload_version`` and never stored
    here. Only normalized hardware observations, timings, and errors survive.
    """

    __tablename__ = "optimization_runs"

    id: Mapped[uuid.UUID] = _uuid_col()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    model_tag: Mapped[str]
    objective: Mapped[str] = mapped_column(default="balanced")
    mode: Mapped[str] = mapped_column(default="quick")
    workload_version: Mapped[str] = mapped_column(default="baseline-v1")
    runner_version: Mapped[str] = mapped_column(default="19.2-v1")
    endpoint_key: Mapped[str]
    endpoint_display: Mapped[str]
    state: Mapped[str] = mapped_column(default="planned")
    current_stage_detail: Mapped[str | None]
    total_trials: Mapped[int] = mapped_column(default=0)
    completed_trials: Mapped[int] = mapped_column(default=0)
    cancel_requested: Mapped[bool] = mapped_column(default=False)
    ollama_version: Mapped[str | None]
    hardware_snapshot: Mapped[dict | None] = mapped_column(JSON)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    error_code: Mapped[str | None]
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]

    candidates: Mapped[list["OptimizationCandidate"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="OptimizationCandidate.position"
    )


class OptimizationCandidate(Base):
    """One bounded setting set in a multi-candidate context comparison."""

    __tablename__ = "optimization_candidates"
    __table_args__ = (
        UniqueConstraint("run_id", "position", name="uq_optimization_candidate_position"),
    )

    id: Mapped[uuid.UUID] = _uuid_col()
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("optimization_runs.id", ondelete="CASCADE")
    )
    position: Mapped[int] = mapped_column(default=0)
    label: Mapped[str] = mapped_column(default="Current baseline")
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    state: Mapped[str] = mapped_column(default="pending")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    run: Mapped["OptimizationRun"] = relationship(back_populates="candidates")
    measurements: Mapped[list["OptimizationMeasurement"]] = relationship(
        back_populates="candidate",
        cascade="all, delete-orphan",
        order_by="OptimizationMeasurement.trial_index",
    )


class OptimizationMeasurement(Base):
    """One warm-up or measured trial; generated model text is intentionally absent."""

    __tablename__ = "optimization_measurements"
    __table_args__ = (
        UniqueConstraint("candidate_id", "trial_index", name="uq_optimization_measurement_trial"),
    )

    id: Mapped[uuid.UUID] = _uuid_col()
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("optimization_candidates.id", ondelete="CASCADE")
    )
    trial_index: Mapped[int]
    workload_case: Mapped[str]
    is_warmup: Mapped[bool] = mapped_column(default=False)
    cold_load: Mapped[bool | None]
    state: Mapped[str] = mapped_column(default="pending")
    ttft_ms: Mapped[float | None]
    prompt_tokens: Mapped[int | None]
    generated_tokens: Mapped[int | None]
    prompt_tokens_per_second: Mapped[float | None]
    generation_tokens_per_second: Mapped[float | None]
    load_duration_ms: Mapped[float | None]
    total_duration_ms: Mapped[float | None]
    wall_duration_ms: Mapped[float | None]
    output_characters: Mapped[int] = mapped_column(default=0)
    finish_reason: Mapped[str | None]
    placement: Mapped[dict | None] = mapped_column(JSON)
    resource_snapshot: Mapped[dict | None] = mapped_column(JSON)
    error_code: Mapped[str | None]
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]

    candidate: Mapped["OptimizationCandidate"] = relationship(back_populates="measurements")


class OptimizationContextAudit(Base):
    """Append-only evidence for a successful profile context apply or rollback."""

    __tablename__ = "optimization_context_audits"
    __table_args__ = (
        UniqueConstraint("source_audit_id", name="uq_context_audit_single_rollback"),
    )

    id: Mapped[uuid.UUID] = _uuid_col()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Immutable identifier snapshots, deliberately not foreign keys: deleting a
    # benchmark report or model profile must not update or delete its audit.
    run_id: Mapped[uuid.UUID | None]
    profile_id: Mapped[uuid.UUID | None]
    source_audit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("optimization_context_audits.id", ondelete="CASCADE")
    )
    model_tag: Mapped[str]
    action: Mapped[str]
    previous_context_length: Mapped[int]
    new_context_length: Mapped[int]
    effective_context_length: Mapped[int]
    preview_version: Mapped[str]
    score_version: Mapped[str | None]
    runner_version: Mapped[str]
    acknowledged_warning_codes: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
