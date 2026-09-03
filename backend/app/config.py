from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Docker passes PostgreSQL components separately so passwords never need to
    # be interpolated into a URL. DATABASE_URL remains available for native
    # development and other deliberate overrides.
    database_url: str | None = None
    postgres_user: str = "llmframework"
    postgres_password: str | None = Field(default=None, repr=False)
    postgres_db: str = "llmframework"
    postgres_host: str = "localhost"
    postgres_port: int = Field(default=5432, ge=1, le=65535)
    app_access_token: str
    ollama_host: str = "http://localhost:11434"
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768
    document_storage_path: str = "./storage/documents"
    document_max_bytes: int = 20_000_000
    document_preview_max_characters: int = Field(default=200_000, ge=1_000, le=1_000_000)
    repository_max_archive_bytes: int = 100 * 1024 * 1024
    repository_max_uncompressed_bytes: int = 500 * 1024 * 1024
    repository_max_members: int = 20_000
    repository_max_file_bytes: int = 2 * 1024 * 1024
    repository_max_compression_ratio: int = 100
    repository_result_limit: int = 8
    repository_character_limit: int = 12_000
    optimizer_context_ceiling: int = Field(default=65_536, ge=512, le=262_144)
    remote_gateway_shared_secret: str = ""
    remote_gateway_transport: Literal["direct", "tailscale_serve"] = "direct"
    remote_gateway_public_url: str = "https://localhost:8443"
    remote_gateway_bind_address: str = "127.0.0.1"
    remote_gateway_hostname: str = "localhost"
    remote_gateway_ca_path: str = "/gateway-data/caddy/pki/authorities/local/root.crt"
    remote_api_default_rate_limit: int = Field(default=30, ge=1, le=600)
    remote_api_max_input_characters: int = Field(default=100_000, ge=1_000, le=1_000_000)
    remote_api_max_body_bytes: int = Field(default=1_000_000, ge=10_000, le=20_000_000)
    remote_api_max_concurrent_generations: int = Field(default=1, ge=1, le=16)
    remote_api_failed_auth_limit: int = Field(default=10, ge=1, le=120)
    local_openai_base_url: str = ""
    local_openai_api_key: str = ""
    local_openai_provider_name: str = "Local OpenAI-compatible runtime"
    allow_public_model_endpoints: bool = False
    cors_origins: str = "http://localhost:3000"
    """Comma-separated allowed origins for the frontend. Configurable rather than
    hardcoded so a downloaded copy of this framework works from whatever host/port
    the user actually runs the frontend on, not just this dev machine's default."""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
