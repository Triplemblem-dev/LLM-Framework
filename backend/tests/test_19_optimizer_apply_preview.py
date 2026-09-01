from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from types import SimpleNamespace
import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.config import settings
from app.db import SessionLocal
from app.deps import get_current_user
from app.models import Model, ModelProfile, OptimizationContextAudit, OptimizationRun
from app.optimizer.activity import ActivitySnapshot
from app.optimizer.apply_preview import build_context_apply_preview
from app.optimizer import context_apply
from app.optimizer.schemas import (
    ContextApplyRequest,
    CpuSnapshot,
    MemorySnapshot,
    OllamaEndpointSnapshot,
    OptimizerCapabilitiesOut,
    RuntimeHostSnapshot,
    SelectedModelSnapshot,
    StorageSnapshot,
)
from app.routers.chat import _options
from app.schemas import ModelProfileSet


def capability_report(
    *,
    digest: str = "digest-a",
    visibility: str = "full",
    tag: str = "test:latest",
) -> OptimizerCapabilitiesOut:
    return OptimizerCapabilitiesOut(
        captured_at="2026-08-27T10:00:00Z",
        requested_model_tag=tag,
        runtime_host=RuntimeHostSnapshot(
            runtime_kind="native",
            applies_to_ollama_device="yes",
            os_name="Test OS",
            os_release="1",
            cpu=CpuSnapshot(model="Test CPU", architecture="test64", logical_cores=8, physical_cores=4),
            memory=MemorySnapshot(total_bytes=16_000, available_bytes=8_000),
            storage=StorageSnapshot(observed_path="runtime root filesystem", total_bytes=100_000, available_bytes=50_000),
        ),
        ollama=OllamaEndpointSnapshot(
            endpoint="http://localhost:11434",
            relationship="same_runtime",
            hardware_visibility=visibility,
            reachable=True,
            version="1.2.3",
            installed_model_count=1,
        ),
        selected_model=SelectedModelSnapshot(
            tag=tag,
            name=tag,
            digest=digest,
            native_context_length=32_768,
        ),
        capabilities=[],
        warnings=[],
    )


def completed_run(report: OptimizerCapabilitiesOut):
    return SimpleNamespace(
        id=uuid.uuid4(),
        model_tag="test:latest",
        state="completed",
        runner_version="19.3-v2",
        endpoint_key="endpoint-key",
        ollama_version="1.2.3",
        completed_at=datetime.now(timezone.utc),
        hardware_snapshot=report.model_dump(mode="json"),
        summary={
            "measured_trials": 6,
            "planning_limits": {"current_profile_context": 8192},
            "recommendation": {
                "score_version": "context-objective-v2",
                "winner_candidate_id": "winner",
                "winning_context_length": 16_384,
                "confidence": "high",
                "candidate_results": [
                    {"candidate_id": "winner", "state": "completed", "measured_trials": 2}
                ],
            },
        },
    )


def profile(context_length: int = 8192):
    return SimpleNamespace(id=uuid.uuid4(), context_length=context_length, is_active=True)


def preview(run, saved_profile, report):
    return build_context_apply_preview(
        run=run,
        profile=saved_profile,
        report=report,
        current_endpoint_key="endpoint-key",
        current_activity=ActivitySnapshot(chats=0, embeddings=0, benchmark_run_id=None),
        safety_ceiling=65_536,
    )


def test_context_change_preview_is_exact_read_only_and_ready():
    report = capability_report()
    result = preview(completed_run(report), profile(), report)

    assert result.status == "ready"
    assert result.can_apply is True
    assert result.current_context_length == 8192
    assert result.recommended_context_length == 16_384
    assert result.target_context_length == 16_384
    assert result.selection_kind == "recommended"
    assert result.delta_tokens == 8192
    assert result.effect_timing == "next_model_request"
    assert result.restart_required is False
    assert result.blocking_reasons == []
    assert result.evidence.model_digest_status == "match"
    assert "num_ctx" in result.affected_scope


def test_context_change_preview_blocks_stale_profile_and_model_build():
    report = capability_report()
    changed_report = capability_report(digest="digest-b")
    run = completed_run(report)

    result = preview(run, profile(4096), changed_report)
    codes = {issue.code for issue in result.blocking_reasons}
    assert result.status == "blocked"
    assert result.can_apply is False
    assert {"profile_context_changed", "model_build_changed"}.issubset(codes)


def test_context_change_preview_marks_partial_visibility_and_no_change():
    report = capability_report(visibility="partial")
    run = completed_run(report)
    run.summary = deepcopy(run.summary)
    run.summary["recommendation"]["winning_context_length"] = 8192

    result = preview(run, profile(), report)
    assert result.status == "no_change"
    assert result.can_apply is False
    assert result.evidence.hardware_status == "partial"
    assert {item.code for item in result.warnings} == {
        "hardware_visibility_partial",
        "already_configured",
    }


def test_context_change_preview_allows_bounded_custom_choice_with_warning():
    report = capability_report()
    result = build_context_apply_preview(
        run=completed_run(report),
        profile=profile(),
        report=report,
        current_endpoint_key="endpoint-key",
        current_activity=ActivitySnapshot(chats=0, embeddings=0, benchmark_run_id=None),
        safety_ceiling=65_536,
        target_context_length=12_288,
    )
    assert result.status == "ready"
    assert result.target_context_length == 12_288
    assert result.recommended_context_length == 16_384
    assert result.selection_kind == "custom"
    assert "unmeasured_context_choice" in {item.code for item in result.warnings}


def test_only_apply_contract_accepts_bounded_context_input():
    with pytest.raises(ValidationError):
        ModelProfileSet(ollama_tag="test:latest", context_length=511)
    with pytest.raises(ValidationError):
        ContextApplyRequest(
            confirmation="apply_recommended_context",
            preview_version="v1",
            expected_current_context_length=8192,
            target_context_length=262_145,
        )


def test_chat_uses_saved_profile_context_as_ollama_num_ctx():
    saved_profile = SimpleNamespace(
        temperature=0.2,
        top_p=0.8,
        top_k=20,
        repeat_penalty=1.05,
        context_length=16_384,
    )
    assert _options(saved_profile)["num_ctx"] == 16_384


def test_authenticated_apply_audit_verification_and_one_click_rollback(client, monkeypatch):
    tag = f"audit-test-{uuid.uuid4().hex}:latest"
    report = capability_report(tag=tag)
    endpoint_key = hashlib.sha256(settings.ollama_host.rstrip("/").encode("utf-8")).hexdigest()
    with SessionLocal() as db:
        user = get_current_user(db)
        model = Model(name=tag, ollama_tag=tag)
        db.add(model)
        db.flush()
        saved_profile = ModelProfile(model_id=model.id, context_length=8192, is_active=False)
        db.add(saved_profile)
        db.flush()
        run = OptimizationRun(
            user_id=user.id,
            model_tag=tag,
            objective="balanced",
            mode="standard",
            workload_version="context-comparison-v1",
            runner_version="19.3-v2",
            endpoint_key=endpoint_key,
            endpoint_display="http://localhost:11434",
            state="completed",
            ollama_version="1.2.3",
            hardware_snapshot=report.model_dump(mode="json"),
            summary={
                "benchmark_kind": "context_comparison",
                "measured_trials": 9,
                "planning_limits": {"current_profile_context": 8192},
                "recommendation": {
                    "score_version": "context-objective-v2",
                    "winner_candidate_id": "winner",
                    "winning_context_length": 16_384,
                    "confidence": "high",
                    "candidate_results": [
                        {"candidate_id": "winner", "state": "completed", "measured_trials": 9}
                    ],
                },
            },
            completed_at=datetime.now(timezone.utc),
        )
        db.add(run)
        db.commit()
        run_id = str(run.id)
        model_id = model.id

    monkeypatch.setattr(context_apply, "discover_capabilities", lambda _tag: report)
    preview_response = client.get(
        f"/optimizer/runs/{run_id}/context-apply-preview?target_context_length=12288"
    )
    assert preview_response.status_code == 200
    preview_body = preview_response.json()
    assert preview_body["status"] == "ready"
    assert preview_body["selection_kind"] == "custom"
    assert preview_body["recommended_context_length"] == 16_384
    assert preview_body["target_context_length"] == 12_288
    warning_codes = [item["code"] for item in preview_body["warnings"]]
    assert warning_codes == ["unmeasured_context_choice"]

    original_verify = context_apply._verify_profile_context
    monkeypatch.setattr(context_apply, "_verify_profile_context", lambda *_args: False)
    failed = client.post(
        f"/optimizer/runs/{run_id}/context-apply",
        json={
            "confirmation": "apply_recommended_context",
            "preview_version": preview_body["preview_version"],
            "expected_current_context_length": 8192,
            "target_context_length": 12_288,
            "acknowledged_warning_codes": warning_codes,
        },
    )
    assert failed.status_code == 500
    with SessionLocal() as db:
        assert db.query(ModelProfile).filter_by(model_id=model_id).one().context_length == 8192
        assert db.query(OptimizationContextAudit).filter_by(model_tag=tag).count() == 0
    monkeypatch.setattr(context_apply, "_verify_profile_context", original_verify)

    applied = client.post(
        f"/optimizer/runs/{run_id}/context-apply",
        json={
            "confirmation": "apply_recommended_context",
            "preview_version": preview_body["preview_version"],
            "expected_current_context_length": 8192,
            "target_context_length": 12_288,
            "acknowledged_warning_codes": warning_codes,
        },
    )
    assert applied.status_code == 200
    applied_body = applied.json()
    assert applied_body["verified"] is True
    assert applied_body["effective_context_length"] == 12_288
    assert applied_body["audit"]["rollback_available"] is True
    source_audit_id = applied_body["audit"]["id"]

    with SessionLocal() as db:
        assert db.query(ModelProfile).filter_by(model_id=model_id).one().context_length == 12_288
        with pytest.raises(DBAPIError):
            db.execute(
                text("UPDATE optimization_context_audits SET action='tampered' WHERE id=:id"),
                {"id": uuid.UUID(source_audit_id)},
            )
            db.commit()
        db.rollback()

    assert client.delete(f"/optimizer/runs/{run_id}").status_code == 204
    history = client.get(f"/optimizer/context-audits?model_tag={tag}")
    assert history.status_code == 200
    assert history.json()[0]["previous_context_length"] == 8192
    assert history.json()[0]["run_id"] == run_id

    rolled_back = client.post(
        f"/optimizer/context-audits/{source_audit_id}/rollback",
        json={
            "confirmation": "rollback_context_change",
            "expected_current_context_length": 12_288,
        },
    )
    assert rolled_back.status_code == 200
    assert rolled_back.json()["effective_context_length"] == 8192
    assert rolled_back.json()["audit"]["action"] == "rollback"

    repeated = client.post(
        f"/optimizer/context-audits/{source_audit_id}/rollback",
        json={
            "confirmation": "rollback_context_change",
            "expected_current_context_length": 12_288,
        },
    )
    assert repeated.status_code == 200
    assert repeated.json()["audit"]["id"] == rolled_back.json()["audit"]["id"]

    with SessionLocal() as db:
        assert db.query(ModelProfile).filter_by(model_id=model_id).one().context_length == 8192
        audits = db.query(OptimizationContextAudit).filter_by(model_tag=tag).all()
        assert len(audits) == 2
        for item in sorted(audits, key=lambda value: value.action == "apply"):
            db.delete(item)
            db.commit()
        db.delete(db.query(ModelProfile).filter_by(model_id=model_id).one())
        db.flush()
        db.delete(db.get(Model, model_id))
        db.commit()
