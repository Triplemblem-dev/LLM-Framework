"""Per-domain generation settings and context-budget safety."""

import app.routers.domains as domains_router
from app.domain_model_settings import EffectiveModelSettings, fit_messages_to_context, ollama_options
from tests.helpers import uniq


def test_context_budget_drops_oldest_turns_and_keeps_latest_request():
    messages = [
        {"role": "system", "content": "rules" * 100},
        {"role": "user", "content": "old question" * 300},
        {"role": "assistant", "content": "old answer" * 300},
        {"role": "user", "content": "latest request"},
    ]

    fitted = fit_messages_to_context(messages, context_length=1024, output_reserve=256)

    assert fitted[0]["role"] == "system"
    assert fitted[-1]["content"] == "latest request"
    assert all(item["content"] != messages[1]["content"] for item in fitted)
    assert messages[0]["content"] == "rules" * 100  # input is never mutated


def test_ollama_options_include_request_and_answer_limits():
    settings = EffectiveModelSettings(
        model_tag="test:latest",
        context_length=8192,
        max_output_tokens=2048,
        temperature=0.2,
        top_p=0.8,
        top_k=20,
        repeat_penalty=1.1,
        source="domain",
    )

    assert ollama_options(settings) == {
        "temperature": 0.2,
        "top_p": 0.8,
        "top_k": 20,
        "repeat_penalty": 1.1,
        "num_ctx": 8192,
        "num_predict": 2048,
    }


def test_domain_remembers_its_generation_settings(client, domain_factory, monkeypatch):
    domain = domain_factory(uniq("Remember model settings"))
    monkeypatch.setattr(
        domains_router,
        "list_installed_models",
        lambda: [{
            "model": "test-domain:latest",
            "name": "test-domain:latest",
            "size": 123,
            "details": {"family": "test", "parameter_size": "1B", "quantization_level": "Q4"},
        }],
    )
    monkeypatch.setattr(domains_router, "discover_capabilities", lambda _tag: (_ for _ in ()).throw(RuntimeError()))

    payload = {
        "model_tag": "test-domain:latest",
        "context_length": 16384,
        "max_output_tokens": 2048,
        "temperature": 0.2,
        "top_p": 0.8,
        "top_k": 20,
        "repeat_penalty": 1.1,
    }
    saved = client.put(f"/domains/{domain['id']}/model-settings", json=payload)
    saved.raise_for_status()
    loaded = client.get(f"/domains/{domain['id']}/model-settings")
    loaded.raise_for_status()

    assert {key: loaded.json()[key] for key in payload} == payload
    assert loaded.json()["source"] == "domain"
    assert loaded.json()["recommended_context_length"] == 16384

