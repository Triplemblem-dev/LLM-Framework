from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
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
    cors_origins: str = "http://localhost:3000"
    """Comma-separated allowed origins for the frontend. Configurable rather than
    hardcoded so a downloaded copy of this framework works from whatever host/port
    the user actually runs the frontend on, not just this dev machine's default."""

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
