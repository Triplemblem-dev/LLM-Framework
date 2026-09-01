import pytest
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError

from app.config import Settings
from app.db import build_database_url
from app import seed
from app.seed import database_startup_guidance


def make_settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "database_url": None,
        "postgres_user": "framework_user",
        "postgres_password": "safe-password",
        "postgres_db": "framework_db",
        "postgres_host": "postgres",
        "postgres_port": 5432,
        "app_access_token": "test-access-token",
    }
    values.update(overrides)
    return Settings(**values)


def test_database_url_preserves_reserved_password_characters():
    password = "p@ss:/?#[]%$ with spaces"
    target = build_database_url(make_settings(postgres_password=password))

    assert isinstance(target, URL)
    assert target.username == "framework_user"
    assert target.password == password
    assert target.host == "postgres"
    assert target.database == "framework_db"


def test_explicit_database_url_remains_supported():
    explicit = "postgresql+psycopg://legacy:encoded%40password@db:5432/legacy"
    assert build_database_url(make_settings(database_url=explicit)) == explicit


def test_database_password_is_required_without_explicit_url():
    with pytest.raises(RuntimeError, match="POSTGRES_PASSWORD or DATABASE_URL"):
        build_database_url(make_settings(postgres_password=None))


def test_password_authentication_failure_has_rotation_guidance():
    guidance = database_startup_guidance(
        RuntimeError('FATAL: password authentication failed for user "llmframework"')
    )

    assert guidance is not None
    assert "initialized postgres_data volume" in guidance
    assert "Recreating only the backend" in guidance
    assert "safe-password" not in guidance


def test_unrelated_database_failure_is_not_rewritten():
    assert database_startup_guidance(RuntimeError("connection timed out")) is None


def test_seed_startup_prints_safe_guidance_for_password_rejection(monkeypatch, capsys):
    failure = OperationalError(
        "connect",
        {},
        RuntimeError('password authentication failed for user "framework_user"'),
    )

    def reject_connection():
        raise failure

    monkeypatch.setattr(seed, "ensure_vector_extension", reject_connection)

    with pytest.raises(SystemExit) as stopped:
        seed.main()

    assert stopped.value.code == 1
    output = capsys.readouterr().err
    assert "PostgreSQL rejected the configured database password" in output
    assert "postgres_data" in output
    assert "p@ss" not in output
