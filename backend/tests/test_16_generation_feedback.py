"""Visible chat outcomes, clarification policy, and Ollama generation metrics."""

import httpx

import app.ollama_client as ollama_client
import app.routers.chat as chat_router
from tests.helpers import preview, send_chat, uniq


def test_generation_metrics_are_streamed_and_persisted(client, domain_factory, monkeypatch):
    domain = domain_factory(uniq("Generation metrics"))

    def measured_stream(_model_tag, _messages, _options):
        yield {"type": "token", "text": "A measured local response."}
        yield {
            "type": "metrics",
            "prompt_tokens": 120,
            "output_tokens": 50,
            "prompt_eval_duration_ns": 1_000_000_000,
            "generation_duration_ns": 2_000_000_000,
            "load_duration_ns": 500_000_000,
            "total_duration_ns": 3_500_000_000,
            "finish_reason": "stop",
        }

    monkeypatch.setattr(chat_router, "chat_stream", measured_stream)
    result = send_chat(client, domain["id"], "Give me a measured response")

    assert result["text"] == "A measured local response."
    assert result["metrics"]["output_tokens"] == 50
    assert result["metrics"]["prompt_tokens"] == 120
    assert result["metrics"]["tokens_per_second"] == 25.0
    assert result["metrics"]["time_to_first_token_ms"] is not None
    assert result["metrics"]["status"] == "completed"

    conversation = client.get(f"/conversations/{result['conversation_id']}")
    conversation.raise_for_status()
    assistant = conversation.json()["messages"][-1]
    assert assistant["content"] == result["text"]
    assert assistant["generation_metrics"] == result["metrics"]


def test_empty_model_output_becomes_a_visible_clarifying_question(client, domain_factory, monkeypatch):
    domain = domain_factory(uniq("Empty generation fallback"))

    def empty_stream(_model_tag, _messages, _options):
        yield {
            "type": "metrics",
            "prompt_tokens": 30,
            "output_tokens": 0,
            "prompt_eval_duration_ns": 100_000_000,
            "generation_duration_ns": 1,
            "load_duration_ns": 0,
            "total_duration_ns": 100_000_001,
            "finish_reason": "stop",
        }

    monkeypatch.setattr(chat_router, "chat_stream", empty_stream)
    result = send_chat(client, domain["id"], "An intentionally unclear request")

    assert "Could you rephrase" in result["text"]
    assert "specific outcome or information" in result["text"]
    assert result["metrics"]["status"] == "empty_fallback"
    assert result["message_id"] is not None


def test_answer_limit_is_reported_instead_of_silently_cutting_off(client, domain_factory, monkeypatch):
    domain = domain_factory(uniq("Answer limit feedback"))

    def limited_stream(_model_tag, _messages, _options):
        yield {"type": "token", "text": "A partial answer"}
        yield {
            "type": "metrics",
            "prompt_tokens": 6000,
            "output_tokens": 2048,
            "generation_duration_ns": 1_000_000_000,
            "finish_reason": "length",
        }

    monkeypatch.setattr(chat_router, "chat_stream", limited_stream)
    result = send_chat(client, domain["id"], "Explain this fully")

    assert result["metrics"]["status"] == "truncated"
    assert "reached the domain's answer-length limit" in result["text"]


def test_model_failure_becomes_a_visible_persisted_response(client, domain_factory, monkeypatch):
    domain = domain_factory(uniq("Generation error fallback"))

    def failing_stream(_model_tag, _messages, _options):
        if False:
            yield None
        raise httpx.ConnectError("simulated Ollama outage")

    monkeypatch.setattr(chat_router, "chat_stream", failing_stream)
    result = send_chat(client, domain["id"], "This prompt must still have an outcome")

    assert "local model could not complete this response" in result["text"]
    assert "retry your prompt" in result["text"]
    assert result["metrics"]["status"] == "error_fallback"
    conversation = client.get(f"/conversations/{result['conversation_id']}").json()
    assert conversation["messages"][-1]["content"] == result["text"]


def test_model_policy_requires_questions_instead_of_low_confidence_guesses(client, domain_factory):
    domain = domain_factory(uniq("Clarification policy"))
    layers = preview(client, domain["id"], "an ambiguous request")
    instructions = layers["2. Main model operating instructions"]["content"]

    assert "visible, non-empty response" in instructions
    assert "cannot be answered with reasonable confidence" in instructions
    assert "ask one or more concise clarifying questions" in instructions
    assert "Use Markdown only when it improves scanning" in instructions
    assert "avoid headings deeper than level three" in instructions


def test_ollama_chat_disables_hidden_reasoning(monkeypatch):
    captured: dict = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def raise_for_status(self):
            return None

        def iter_lines(self):
            return iter(['{"message":{"content":"OK"},"done":true,"eval_count":1}'])

    def fake_stream(method, url, *, json, timeout):
        captured.update({"method": method, "url": url, "json": json, "timeout": timeout})
        return FakeResponse()

    monkeypatch.setattr(ollama_client.httpx, "stream", fake_stream)

    events = list(ollama_client.chat_stream("qwen3.5:9b", [{"role": "user", "content": "hi"}], {}))

    assert captured["json"]["think"] is False
    assert events[0] == {"type": "token", "text": "OK"}
