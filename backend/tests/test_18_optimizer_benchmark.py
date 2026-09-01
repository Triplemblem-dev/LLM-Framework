import json
import threading

import httpx

from app.db import SessionLocal
from app.deps import get_current_user
from app.models import OptimizationCandidate, OptimizationRun
from app.optimizer import activity, jobs
from app.optimizer.benchmark import BenchmarkCancelled, TrialResult, run_streamed_trial
from app.optimizer.candidates import context_candidates
from app.optimizer.ollama_probe import ProbeResult
from app.optimizer.scoring import CandidateEvidence, score_candidates
from app.optimizer.schemas import (
    CapabilityStatus,
    CpuSnapshot,
    MemorySnapshot,
    OllamaEndpointSnapshot,
    OptimizerCapabilitiesOut,
    RuntimeHostSnapshot,
    SelectedModelSnapshot,
    StorageSnapshot,
)
from app.optimizer.workloads import MAX_PROMPT_CHARACTERS, MAX_RESPONSE_TOKENS, PROMPT_BANK, trial_plan
from app.routers import optimizer as optimizer_router


def fake_report() -> OptimizerCapabilitiesOut:
    return OptimizerCapabilitiesOut(
        captured_at="2026-08-27T10:00:00Z",
        requested_model_tag="test:latest",
        runtime_host=RuntimeHostSnapshot(
            runtime_kind="native",
            applies_to_ollama_device="yes",
            os_name="Test OS",
            os_release="1",
            cpu=CpuSnapshot(model="Test CPU", architecture="test64", logical_cores=8, physical_cores=4),
            memory=MemorySnapshot(total_bytes=16_000, available_bytes=8_000, swap_total_bytes=0, swap_used_bytes=0),
            storage=StorageSnapshot(observed_path="runtime root filesystem", total_bytes=100_000, available_bytes=50_000),
        ),
        ollama=OllamaEndpointSnapshot(
            endpoint="http://localhost:11434",
            relationship="same_runtime",
            hardware_visibility="full",
            reachable=True,
            version="1.2.3",
            installed_model_count=1,
        ),
        selected_model=SelectedModelSnapshot(
            tag="test:latest",
            name="test:latest",
            native_context_length=32_768,
            loaded=False,
        ),
        capabilities=[
            CapabilityStatus(
                key="power_metrics",
                label="Power metrics",
                status="unavailable",
                detail="Unavailable in test",
                source="test",
            )
        ],
        warnings=[],
    )


def fake_probe(*, loaded: bool = True, placement: str = "cpu") -> ProbeResult:
    model = SelectedModelSnapshot(
        tag="test:latest",
        name="test:latest",
        loaded=loaded,
        loaded_size_bytes=4_000 if loaded else None,
        accelerator_size_bytes=0 if loaded else None,
        accelerator_fraction=0 if loaded else None,
        placement=placement,
    )
    return ProbeResult(
        endpoint=fake_report().ollama,
        selected_model=model,
        requested_model_installed=True,
    )


def test_synthetic_workload_is_small_versioned_and_has_bounded_modes():
    assert all(len(case.prompt) <= MAX_PROMPT_CHARACTERS for case in PROMPT_BANK)
    assert len(trial_plan("quick")) == 3
    assert len(trial_plan("standard")) == 4
    assert sum(1 for warmup, _case in trial_plan("standard") if warmup) == 1
    assert len(trial_plan("quick", "context_comparison")) == 7
    assert len(trial_plan("standard", "context_comparison")) == 10
    assert all(
        sum(1 for warmup, item in trial_plan("standard", "context_comparison") if not warmup and item.key == case.key) == 3
        for case in PROMPT_BANK
    )
    combined = " ".join(case.prompt.lower() for case in PROMPT_BANK)
    assert "conversation" not in combined
    assert "repository" not in combined
    assert "document" not in combined


def test_streamed_trial_records_metrics_without_retaining_output():
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["options"]["num_predict"] == MAX_RESPONSE_TOKENS
        assert body["options"]["temperature"] == 0
        return httpx.Response(
            200,
            content=(
                b'{"message":{"content":"discard me"},"done":false}\n'
                b'{"message":{"content":""},"done":true,"prompt_eval_count":20,'
                b'"prompt_eval_duration":1000000000,"eval_count":10,'
                b'"eval_duration":2000000000,"load_duration":500000000,'
                b'"total_duration":3500000000,"done_reason":"stop"}\n'
            ),
        )

    result = run_streamed_trial(
        "http://localhost:11434",
        "test:latest",
        "Synthetic input",
        {"num_predict": 999, "num_ctx": 4096},
        threading.Event(),
        transport=httpx.MockTransport(handler),
    )
    assert result.prompt_tokens_per_second == 20
    assert result.generation_tokens_per_second == 5
    assert result.output_characters == len("discard me")
    assert not hasattr(result, "output")


def test_streamed_trial_honors_cancellation():
    event = threading.Event()
    event.set()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b'{"message":{"content":"x"},"done":false}\n')

    try:
        run_streamed_trial(
            "http://localhost:11434",
            "test:latest",
            "Synthetic input",
            {},
            event,
            transport=httpx.MockTransport(handler),
        )
    except BenchmarkCancelled:
        pass
    else:
        raise AssertionError("Expected cancellation")


def test_activity_registry_prevents_overlap():
    with activity.ordinary_activity("chat"):
        assert activity.try_acquire_benchmark("run-a") is False
    assert activity.try_acquire_benchmark("run-a") is True
    try:
        try:
            with activity.ordinary_activity("embedding"):
                pass
        except activity.OllamaBusyError:
            pass
        else:
            raise AssertionError("Expected benchmark conflict")
    finally:
        activity.release_benchmark("run-a")


def test_run_api_creates_reviewable_plan_and_can_cancel_and_delete(client, monkeypatch):
    monkeypatch.setattr(optimizer_router, "discover_capabilities", lambda _tag: fake_report())
    created = client.post(
        "/optimizer/runs",
        json={"model_tag": "test:latest", "objective": "balanced", "mode": "quick"},
    )
    assert created.status_code == 201
    run = created.json()
    assert run["state"] == "planned"
    assert run["total_trials"] == 3
    assert run["candidates"][0]["settings"]["num_predict"] == 96
    assert run["hardware_snapshot"]["selected_model"]["tag"] == "test:latest"
    assert "conversations" in run["disruption_notice"].lower() or "chat" in run["disruption_notice"].lower()

    preview = client.get(f"/optimizer/runs/{run['id']}/context-apply-preview")
    assert preview.status_code == 200
    assert preview.json()["status"] == "blocked"
    assert preview.json()["can_apply"] is False
    assert preview.json()["restart_required"] is False

    cancelled = client.post(f"/optimizer/runs/{run['id']}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"
    assert client.post(f"/optimizer/runs/{run['id']}/cancel").json()["state"] == "cancelled"
    assert client.delete(f"/optimizer/runs/{run['id']}").status_code == 204
    assert client.get(f"/optimizer/runs/{run['id']}").status_code == 404


def test_complete_background_run_persists_cpu_placement_and_metrics(client, monkeypatch):
    monkeypatch.setattr(optimizer_router, "discover_capabilities", lambda _tag: fake_report())
    created = client.post(
        "/optimizer/runs",
        json={"model_tag": "test:latest", "objective": "balanced", "mode": "quick"},
    ).json()

    with SessionLocal() as db:
        run = db.get(OptimizationRun, created["id"])
        jobs.transition(run, "queued", "test")
        db.commit()

    monkeypatch.setattr(jobs, "discover_capabilities", lambda _tag: fake_report())
    monkeypatch.setattr(jobs, "probe_ollama", lambda *_args, **_kwargs: fake_probe())
    monkeypatch.setattr(jobs, "inspect_runtime_host", lambda: fake_report().runtime_host)
    monkeypatch.setattr(
        jobs,
        "run_streamed_trial",
        lambda *_args, **_kwargs: TrialResult(
            ttft_ms=100,
            prompt_tokens=20,
            generated_tokens=10,
            prompt_tokens_per_second=40,
            generation_tokens_per_second=5,
            load_duration_ms=10,
            total_duration_ms=2200,
            wall_duration_ms=2250,
            output_characters=50,
            finish_reason="stop",
        ),
    )
    jobs.execute_run(uuid_from(created["id"]), threading.Event())

    result = client.get(f"/optimizer/runs/{created['id']}").json()
    assert result["state"] == "completed"
    assert result["completed_trials"] == 3
    assert result["summary"]["measured_trials"] == 2
    assert result["summary"]["medians"]["generation_tokens_per_second"] == 5
    assert result["summary"]["latest_placement"]["kind"] == "cpu"
    assert result["summary"]["generated_text_retained"] is False
    assert client.delete(f"/optimizer/runs/{created['id']}").status_code == 204


def test_cancelled_background_run_keeps_completed_partial_results(client, monkeypatch):
    monkeypatch.setattr(optimizer_router, "discover_capabilities", lambda _tag: fake_report())
    created = client.post(
        "/optimizer/runs",
        json={"model_tag": "test:latest", "objective": "balanced", "mode": "standard"},
    ).json()
    with SessionLocal() as db:
        run = db.get(OptimizationRun, uuid_from(created["id"]))
        jobs.transition(run, "queued", "test")
        db.commit()

    monkeypatch.setattr(jobs, "discover_capabilities", lambda _tag: fake_report())
    monkeypatch.setattr(jobs, "probe_ollama", lambda *_args, **_kwargs: fake_probe())
    monkeypatch.setattr(jobs, "inspect_runtime_host", lambda: fake_report().runtime_host)
    calls = 0

    def trial(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise BenchmarkCancelled("test cancellation")
        return TrialResult(
            ttft_ms=100,
            prompt_tokens=20,
            generated_tokens=10,
            prompt_tokens_per_second=40,
            generation_tokens_per_second=5,
            load_duration_ms=10,
            total_duration_ms=2200,
            wall_duration_ms=2250,
            output_characters=50,
            finish_reason="stop",
        )

    monkeypatch.setattr(jobs, "run_streamed_trial", trial)
    jobs.execute_run(uuid_from(created["id"]), threading.Event())
    result = client.get(f"/optimizer/runs/{created['id']}").json()
    assert result["state"] == "cancelled"
    assert result["completed_trials"] == 1
    assert [item["state"] for item in result["candidates"][0]["measurements"]] == [
        "completed",
        "cancelled",
    ]
    assert result["summary"]["warmup_trials"] == 1
    assert client.delete(f"/optimizer/runs/{created['id']}").status_code == 204


def test_endpoint_lock_rejects_a_second_active_run(client, monkeypatch):
    monkeypatch.setattr(optimizer_router, "discover_capabilities", lambda _tag: fake_report())
    monkeypatch.setattr(optimizer_router, "launch", lambda _run_id: None)
    first = client.post(
        "/optimizer/runs",
        json={"model_tag": "test:latest", "objective": "balanced", "mode": "quick"},
    ).json()
    second = client.post(
        "/optimizer/runs",
        json={"model_tag": "test:latest", "objective": "balanced", "mode": "quick"},
    ).json()
    assert client.post(f"/optimizer/runs/{first['id']}/start").status_code == 200
    blocked = client.post(f"/optimizer/runs/{second['id']}/start")
    assert blocked.status_code == 409
    assert "already" in blocked.json()["detail"].lower()

    with SessionLocal() as db:
        run = db.get(OptimizationRun, uuid_from(first["id"]))
        run.state = "failed"
        run.error_code = "test_cleanup"
        run.error_message = "test cleanup"
        db.commit()
    assert client.delete(f"/optimizer/runs/{first['id']}").status_code == 204
    assert client.delete(f"/optimizer/runs/{second['id']}").status_code == 204


def uuid_from(value: str):
    import uuid

    return uuid.UUID(value)


def test_restart_recovery_preserves_partial_report(client):
    with SessionLocal() as db:
        user = get_current_user(db)
        run = OptimizationRun(
            user_id=user.id,
            model_tag="test:latest",
            endpoint_key="restart-test",
            endpoint_display="http://localhost:11434",
            state="measuring",
            total_trials=3,
            completed_trials=0,
        )
        db.add(run)
        db.flush()
        db.add(OptimizationCandidate(run_id=run.id, position=0, settings={}))
        db.commit()
        run_id = run.id

    assert jobs.recover_interrupted_runs() >= 1
    recovered = client.get(f"/optimizer/runs/{run_id}").json()
    assert recovered["state"] == "failed"
    assert recovered["error_code"] == "backend_restarted"
    assert client.delete(f"/optimizer/runs/{run_id}").status_code == 204


def evidence(context: int, rate: float, *, current: bool = False) -> CandidateEvidence:
    return CandidateEvidence(
        candidate_id=str(context),
        label=f"{context} context",
        context_length=context,
        is_current=current,
        state="completed",
        expected_measured_trials=3,
        ttft_values=(100.0, 101.0, 99.0),
        generation_rate_values=(rate, rate, rate),
        prompt_rate_values=(40.0, 40.0, 40.0),
        total_latency_values=(2200.0, 2200.0, 2200.0),
        generated_token_values=(10, 10, 10),
        power_watt_values=(),
        tokens_per_joule_values=(),
        placement={"kind": "cpu", "accelerator_fraction": 0, "loaded_size_bytes": 4000},
        workload_samples={
            "same_workload": {
                "ttft": (100.0, 101.0, 99.0),
                "generation_rate": (rate, rate, rate),
                "power": (),
            }
        },
    )


def test_context_candidate_plan_is_bounded_unique_and_keeps_current():
    plans = context_candidates(current_context=8192, native_context_limit=131072, safety_ceiling=32768)
    assert 1 <= len(plans) <= 4
    assert [item.context_length for item in plans] == sorted({item.context_length for item in plans})
    assert all(item.context_length <= 32768 for item in plans)
    assert [item.context_length for item in plans if item.is_current] == [8192]


def test_scoring_does_not_reward_unused_context_for_balanced_goal():
    result = score_candidates(
        [evidence(4096, 10, current=True), evidence(32768, 10)],
        "balanced",
        workload_context_need=4096,
        hardware_visibility="full",
    )
    assert result["winning_context_length"] == 4096
    assert result["score_version"] == "context-objective-v2"
    assert result["confidence"] == "high"


def test_context_comparison_runs_all_cpu_candidates_and_recommends_without_applying(client, monkeypatch):
    monkeypatch.setattr(optimizer_router, "discover_capabilities", lambda _tag: fake_report())
    created = client.post(
        "/optimizer/runs",
        json={
            "model_tag": "test:latest",
            "objective": "balanced",
            "mode": "quick",
            "benchmark_kind": "context_comparison",
        },
    ).json()
    assert created["benchmark_kind"] == "context_comparison"
    assert len(created["candidates"]) == 4
    assert created["total_trials"] == 28

    with SessionLocal() as db:
        run = db.get(OptimizationRun, uuid_from(created["id"]))
        jobs.transition(run, "queued", "test")
        db.commit()

    monkeypatch.setattr(jobs, "discover_capabilities", lambda _tag: fake_report())
    monkeypatch.setattr(jobs, "probe_ollama", lambda *_args, **_kwargs: fake_probe())
    monkeypatch.setattr(jobs, "inspect_runtime_host", lambda: fake_report().runtime_host)

    def trial(_endpoint, _tag, _prompt, options, _event):
        rate = 12 - (options["num_ctx"] / 32768)
        return TrialResult(
            ttft_ms=100 + options["num_ctx"] / 4096,
            prompt_tokens=20,
            generated_tokens=10,
            prompt_tokens_per_second=40,
            generation_tokens_per_second=rate,
            load_duration_ms=10,
            total_duration_ms=2200,
            wall_duration_ms=2250,
            output_characters=50,
            finish_reason="stop",
        )

    monkeypatch.setattr(jobs, "run_streamed_trial", trial)
    jobs.execute_run(uuid_from(created["id"]), threading.Event())
    result = client.get(f"/optimizer/runs/{created['id']}").json()
    assert result["state"] == "completed"
    assert result["completed_trials"] == 28
    assert all(item["state"] == "completed" for item in result["candidates"])
    assert result["summary"]["recommendation"]["winning_context_length"] == 4096
    assert result["summary"]["settings_changed"] is False

    exported = client.get(f"/optimizer/runs/{created['id']}/export")
    assert exported.status_code == 200
    assert "text/markdown" in exported.headers["content-type"]
    assert created["id"] not in exported.text
    assert "http://localhost:11434" not in exported.text
    assert "runtime root filesystem" not in exported.text
    assert "Generated text retained: no" in exported.text
    assert client.delete(f"/optimizer/runs/{created['id']}").status_code == 204


def test_confidence_uses_within_workload_repeats_not_different_workload_means():
    item = evidence(8192, 10, current=True)
    item = CandidateEvidence(
        **{
            **item.__dict__,
            "ttft_values": (100.0, 101.0, 900.0, 910.0),
            "generation_rate_values": (10.0, 10.1, 9.9, 10.0),
            "expected_measured_trials": 4,
            "workload_samples": {
                "short": {
                    "ttft": (100.0, 101.0),
                    "generation_rate": (10.0, 10.1),
                    "power": (),
                },
                "long": {
                    "ttft": (900.0, 910.0),
                    "generation_rate": (9.9, 10.0),
                    "power": (),
                },
            },
        }
    )
    result = score_candidates([item], "balanced", 4096, "full")
    assert result["confidence"] == "medium"
    assert "Within-workload repeat variance exceeded 25%." not in result["confidence_reasons"]
    assert result["candidate_results"][0]["variance"]["method"] == "maximum_within_workload_cv"
