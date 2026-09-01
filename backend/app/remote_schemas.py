import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import RemoteAccessMode


class RemoteAccessUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: RemoteAccessMode
    gateway_port: int = Field(default=8443, ge=1, le=65_535)


class RemoteAccessStatusOut(BaseModel):
    mode: RemoteAccessMode
    gateway_port: int
    gateway_configured: bool
    gateway_running: bool
    api_base_url: str
    bind_address: str
    hostname: str
    network_configuration_valid: bool
    network_configuration_error: str | None
    tailscale_configured: bool
    certificate_available: bool
    active_key_count: int


class RemoteConnectionTestOut(BaseModel):
    ready: bool
    mode: RemoteAccessMode
    gateway_configured: bool
    gateway_running: bool
    network_configuration_valid: bool
    detail: str


class RemoteApiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=80)
    domain_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    requests_per_minute: int = Field(default=30, ge=1, le=600)
    expires_at: datetime | None = None


class RemoteApiKeyOut(BaseModel):
    id: uuid.UUID
    name: str
    token_prefix: str
    domain_ids: list[uuid.UUID]
    requests_per_minute: int
    expires_at: datetime | None
    revoked_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class RemoteApiKeyCreatedOut(RemoteApiKeyOut):
    token: str


class OpenAIMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["system", "developer", "user", "assistant"]
    content: str = Field(min_length=1)


class ChatCompletionsRequest(BaseModel):
    """The supported OpenAI-compatible subset.

    Sampling fields are accepted for client compatibility but deliberately
    ignored: each domain's saved tuning remains authoritative.
    """

    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1, max_length=128)
    messages: list[OpenAIMessage] = Field(min_length=1, max_length=100)
    stream: bool = False
    n: Literal[1] = 1
    user: str | None = Field(default=None, max_length=200)
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
