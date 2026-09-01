import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import DocumentStatus, InheritancePolicy, MessageRole, RepositoryStatus


class DomainCreate(BaseModel):
    name: str
    description: str = ""
    prompt: str = ""


class DomainUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    prompt: str | None = None
    inheritance: InheritancePolicy | None = None
    share_with_siblings: bool | None = None


class DomainOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str
    prompt: str = Field(validation_alias="scope_prompt")
    inheritance: InheritancePolicy
    share_with_siblings: bool
    created_at: datetime
    updated_at: datetime


class SubDomainOut(DomainOut):
    pass


class DomainTreeOut(DomainOut):
    subdomains: list[SubDomainOut] = Field(default_factory=list, validation_alias="children")


class DomainModelSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_tag: str = Field(min_length=1, max_length=200)
    context_length: int = Field(ge=512, le=262_144)
    max_output_tokens: int = Field(ge=128, le=16_384)
    temperature: float = Field(ge=0, le=2)
    top_p: float = Field(ge=0.05, le=1)
    top_k: int = Field(ge=1, le=200)
    repeat_penalty: float = Field(ge=0.8, le=2)


class DomainModelSettingsOut(DomainModelSettingsUpdate):
    domain_id: uuid.UUID
    source: Literal["domain", "framework_default"]
    native_context_length: int | None = None
    detected_allocated_context_length: int | None = None
    recommended_context_length: int
    recommendation_basis: str


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime


class CitationOut(BaseModel):
    source_type: Literal["document", "repository"] = "document"
    document_id: uuid.UUID | None = None
    document_name: str | None = None
    scope_id: uuid.UUID
    scope_name: str
    heading: str | None = None
    page_number: int | None = None
    chunk_index: int
    repository_id: uuid.UUID | None = None
    repository_name: str | None = None
    revision_label: str | None = None
    snapshot_hash: str | None = None
    relative_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None


class GenerationMetricsOut(BaseModel):
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    tokens_per_second: float | None = None
    time_to_first_token_ms: float | None = None
    prompt_eval_duration_ms: float | None = None
    generation_duration_ms: float | None = None
    load_duration_ms: float | None = None
    total_duration_ms: float | None = None
    finish_reason: str | None = None
    status: Literal["completed", "truncated", "empty_fallback", "error_fallback", "stopped", "client_error"] = "completed"


class LearningCard(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    category: Literal["key_idea", "action", "caution", "example"]
    title: str = Field(min_length=1, max_length=56)
    takeaway: str = Field(min_length=1, max_length=180)


class LearningCardDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=240)
    cards: list[LearningCard] = Field(min_length=4, max_length=4)


class LearningCardSetOut(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=240)
    # Historical decks may contain two or three cards. New generation uses the
    # stricter LearningCardDraft contract above and always produces four.
    cards: list[LearningCard] = Field(min_length=2, max_length=4)
    source_message_id: uuid.UUID
    model_tag: str
    created_at: datetime


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: MessageRole
    content: str
    citations: list[CitationOut] = Field(default_factory=list)
    generation_metrics: GenerationMetricsOut | None = None
    learning_cards: LearningCardSetOut | None = None
    created_at: datetime


class ConversationDetailOut(ConversationOut):
    messages: list[MessageOut] = []


class ModelInstalledOut(BaseModel):
    name: str
    tag: str
    size_bytes: int
    parameter_size: str | None
    quantization_level: str | None
    context_length: int | None
    modified_at: str | None


class ModelProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ollama_tag: str = Field(validation_alias="tag")
    name: str
    context_length: int
    temperature: float
    top_p: float
    top_k: int
    repeat_penalty: float


class ModelProfileSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ollama_tag: str


class PromptLayer(BaseModel):
    key: str
    name: str
    category: Literal["rules", "scope", "knowledge", "conversation"]
    content: str
    applied: bool
    state: Literal["included", "not_included", "planned"]
    reason: str
    source_type: str
    source_name: str | None = None
    edit_target: Literal["scope_settings", "parent_scope", "memory", "documents", "repositories"] | None = None
    model_role: Literal["system", "conversation", "user"] | None = None
    control: Literal["standard", "advanced", "fixed", "planned"]
    owner_enabled: bool | None = None


class PromptLayerControlUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    risk_acknowledged: bool = False


class PromptLayerControlOut(BaseModel):
    key: str
    enabled: bool


class PromptPreviewOut(BaseModel):
    layers: list[PromptLayer]


class ChatMessageIn(BaseModel):
    conversation_id: uuid.UUID | None = None
    text: str


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    source_type: str
    folder_path: str
    tags: list[str]
    version: int
    status: DocumentStatus
    error: str | None
    chunk_count: int
    created_at: datetime
    markdown_available: bool = False
    markdown_filename: str | None = None


class InheritedDocumentOut(DocumentOut):
    scope_id: uuid.UUID
    scope_name: str


class DocumentPreviewOut(BaseModel):
    filename: str
    source_type: str
    format: Literal["markdown", "text"]
    content: str
    character_count: int
    truncated: bool
    markdown_copy: bool


class DocumentOrganizationPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_tag: str | None = Field(default=None, max_length=200)


class DocumentOrganizationSuggestion(BaseModel):
    document_id: uuid.UUID
    filename: str
    folder_path: str
    tags: list[str]
    reason: str


class DocumentOrganizationPreviewOut(BaseModel):
    model_tag: str
    document_set_hash: str
    suggestions: list[DocumentOrganizationSuggestion]
    warnings: list[str] = Field(default_factory=list)


class DocumentOrganizationApplyItem(BaseModel):
    document_id: uuid.UUID
    folder_path: str
    tags: list[str]


class DocumentOrganizationApplyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_set_hash: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    suggestions: list[DocumentOrganizationApplyItem] = Field(min_length=1, max_length=50)
    confirmation: Literal["apply_document_organization"]


class MemoryCreate(BaseModel):
    content: str
    conversation_id: uuid.UUID | None = None


class MemoryUpdate(BaseModel):
    content: str


class MemoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    content: str
    conversation_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class InheritedMemoryOut(MemoryOut):
    scope_id: uuid.UUID
    scope_name: str


class RepositoryExclusionOut(BaseModel):
    path: str
    reason: str
    security: bool = False


class CodeRepositoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    scope_id: uuid.UUID
    name: str
    archive_filename: str
    revision_label: str | None
    content_hash: str
    status: RepositoryStatus
    error: str | None
    file_count: int
    skipped_file_count: int
    security_excluded_count: int
    chunk_count: int
    exclusions: list[RepositoryExclusionOut] = []
    created_at: datetime
    updated_at: datetime


class CodeSearchResultOut(BaseModel):
    repository_id: uuid.UUID
    repository_name: str
    revision_label: str | None
    snapshot_hash: str
    relative_path: str
    start_line: int
    end_line: int
    symbol: str | None
    content: str
