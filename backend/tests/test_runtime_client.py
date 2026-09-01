import json

import pytest

from app import runtime_client


class FakeResponse:
    def __init__(self, payload=None, lines=None):
        self.payload = payload or {}
        self.lines = lines or []

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload

    def iter_lines(self):
        return iter(self.lines)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def test_generic_runtime_rejects_public_endpoints_by_default(monkeypatch):
    monkeypatch.setattr(runtime_client.settings, "allow_public_model_endpoints", False)
    assert runtime_client.validate_local_runtime_url("http://127.0.0.1:8080/v1") == "http://127.0.0.1:8080/v1"
    assert runtime_client.validate_local_runtime_url("http://host.docker.internal:8080/v1") == "http://host.docker.internal:8080/v1"
    assert runtime_client.validate_local_runtime_url("http://llama-server:8080/v1") == "http://llama-server:8080/v1"
    with pytest.raises(runtime_client.UnsafeRuntimeEndpoint):
        runtime_client.validate_local_runtime_url("https://api.openai.com/v1")
    with pytest.raises(runtime_client.UnsafeRuntimeEndpoint):
        runtime_client.validate_local_runtime_url("https://8.8.8.8/v1")


def test_generic_runtime_models_and_stream_use_prefixed_local_identity(monkeypatch):
    monkeypatch.setattr(runtime_client.settings, "local_openai_base_url", "http://llama-server:8080/v1")
    monkeypatch.setattr(runtime_client.settings, "local_openai_api_key", "local-runtime-secret")
    monkeypatch.setattr(runtime_client.settings, "allow_public_model_endpoints", False)
    monkeypatch.setattr(runtime_client, "list_ollama_models", lambda: [])

    def fake_get(url, headers, timeout):
        assert url == "http://llama-server:8080/v1/models"
        assert headers == {"Authorization": "Bearer local-runtime-secret"}
        assert timeout == 10
        return FakeResponse({"data": [{"id": "hf-model-q4"}]})

    monkeypatch.setattr(runtime_client.httpx, "get", fake_get)
    models = runtime_client.list_installed_models()
    assert models[0]["model"] == "openai-local/hf-model-q4"

    lines = [
        "data: " + json.dumps({"choices": [{"delta": {"content": "Local "}, "finish_reason": None}]}),
        "data: " + json.dumps({"choices": [{"delta": {"content": "model"}, "finish_reason": "stop"}]}),
        "data: " + json.dumps({"choices": [], "usage": {"prompt_tokens": 4, "completion_tokens": 2}}),
        "data: [DONE]",
    ]

    def fake_stream(method, url, headers, json, timeout):
        assert method == "POST"
        assert url == "http://llama-server:8080/v1/chat/completions"
        assert headers == {"Authorization": "Bearer local-runtime-secret"}
        assert json["model"] == "hf-model-q4"
        assert json["stream"] is True
        return FakeResponse(lines=lines)

    monkeypatch.setattr(runtime_client.httpx, "stream", fake_stream)
    events = list(
        runtime_client.chat_stream(
            "openai-local/hf-model-q4",
            [{"role": "user", "content": "Hello"}],
            {"temperature": 0.4, "top_p": 0.9, "num_predict": 100},
        )
    )
    assert [event.get("text") for event in events if event["type"] == "token"] == ["Local ", "model"]
    assert events[-1] == {
        "type": "metrics",
        "prompt_tokens": 4,
        "output_tokens": 2,
        "finish_reason": "stop",
    }
