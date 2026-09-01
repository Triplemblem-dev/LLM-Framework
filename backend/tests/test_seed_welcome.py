from types import SimpleNamespace
from unittest.mock import MagicMock

from app import seed


def test_welcome_demo_is_seeded_only_once(monkeypatch):
    db = MagicMock()
    user = SimpleNamespace(demo_seeded=False)
    seed_demo_domain = MagicMock()
    monkeypatch.setattr(seed, "seed_demo_domain", seed_demo_domain)

    seed.seed_demo_once(db, user)
    seed.seed_demo_once(db, user)

    seed_demo_domain.assert_called_once_with(db, user)
    assert user.demo_seeded is True
