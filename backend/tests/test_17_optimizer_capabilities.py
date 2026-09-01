import httpx
from fastapi.testclient import TestClient
import pytest

from app.config import settings
from app.main import app
from app.optimizer import discovery
from app.optimizer.adapters import commands
from app.optimizer.adapters.commands import run_allowed
from app.optimizer.adapters.platform import (
    parse_linux_cpuinfo,
    parse_linux_meminfo,
    parse_macos_displays,
    parse_nvidia_smi,
    parse_vm_stat,
)
from app.optimizer.ollama_probe import (
    classify_endpoint,
    probe_ollama,
    safe_endpoint_display,
)
from app.optimizer.schemas import (
    CpuSnapshot,
    MemorySnapshot,
    RuntimeHostSnapshot,
    StorageSnapshot,
)


def runtime_host(*, runtime_kind: str = "native") -> RuntimeHostSnapshot:
    return RuntimeHostSnapshot(
        runtime_kind=runtime_kind,
        applies_to_ollama_device="unknown",
        os_name="Test OS",
        os_release="1.0",
        cpu=CpuSnapshot(
            model="Test CPU",
            architecture="test64",
            logical_cores=8,
            physical_cores=4,
        ),
        memory=MemorySnapshot(
            total_bytes=16 * 1024**3,
            available_bytes=8 * 1024**3,
            swap_total_bytes=2 * 1024**3,
            swap_used_bytes=0,
        ),
        storage=StorageSnapshot(
            observed_path="runtime root filesystem",
            total_bytes=100 * 1024**3,
            available_bytes=50 * 1024**3,
        ),
    )


def test_linux_parsers_normalize_only_allow_listed_fields():
    memory = parse_linux_meminfo(
        """MemTotal:       16384000 kB
MemAvailable:    8192000 kB
SwapTotal:       2048000 kB
SwapFree:        1536000 kB
HardwareSerial:  secret
"""
    )
    assert memory.total_bytes == 16_384_000 * 1024
    assert memory.available_bytes == 8_192_000 * 1024
    assert memory.swap_used_bytes == 512_000 * 1024
    assert "HardwareSerial" not in memory.model_dump_json()

    model, physical = parse_linux_cpuinfo(
        """processor : 0
physical id : 0
core id : 0
model name : Example CPU

processor : 1
physical id : 0
core id : 1
model name : Example CPU
"""
    )
    assert model == "Example CPU"
    assert physical == 2


def test_nvidia_parser_handles_supported_and_unavailable_sensors():
    accelerators = parse_nvidia_smi(
        "NVIDIA RTX Test, 8192, 1024, 87, 74.5, 58, 555.10\n"
        "NVIDIA Sensorless, 4096, 0, N/A, [Not Supported], N/A, 555.10\n"
    )
    assert len(accelerators) == 2
    assert accelerators[0].memory_total_bytes == 8192 * 1024 * 1024
    assert accelerators[0].utilization_percent == 87
    assert accelerators[0].power_watts == 74.5
    assert accelerators[1].power_watts is None
    assert accelerators[1].temperature_celsius is None


def test_macos_parsers_keep_unified_memory_semantics():
    available, used = parse_vm_stat(
        """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               100.
Pages active:                             50.
Pages inactive:                           20.
Pages speculative:                        10.
Pages wired down:                         30.
Pages occupied by compressor:              5.
"""
    )
    assert available == 130 * 16384
    assert used == 85 * 16384

    accelerators = parse_macos_displays(
        '{"SPDisplaysDataType":[{"sppci_model":"Apple M4","spdisplays_metal":"Supported"}]}',
        24 * 1024**3,
    )
    assert len(accelerators) == 1
    assert accelerators[0].vendor == "apple"
    assert accelerators[0].memory_kind == "unified"
    assert accelerators[0].memory_total_bytes == 24 * 1024**3


def test_command_adapter_rejects_non_allow_listed_command():
    with pytest.raises(ValueError, match="Unknown fixed command"):
        run_allowed("user-provided-command")


def test_command_adapter_uses_fixed_arguments_timeout_and_minimal_environment(monkeypatch):
    captured = {}

    class Completed:
        returncode = 0
        stdout = "123\n"

    monkeypatch.setattr(commands.Path, "is_file", lambda _path: True)

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        captured.update(kwargs)
        return Completed()

    monkeypatch.setattr(commands.subprocess, "run", fake_run)
    assert run_allowed("mac_total_memory") == "123\n"
    assert captured["argv"] == ["/usr/sbin/sysctl", "-n", "hw.memsize"]
    assert captured["shell"] is False
    assert captured["timeout"] == 5.0
    assert captured["env"] == {
        "LC_ALL": "C",
        "LANG": "C",
        "PATH": "/usr/bin:/usr/sbin:/bin:/sbin",
    }


def test_endpoint_classification_and_display_redact_credentials():
    assert classify_endpoint("http://localhost:11434", "native") == "same_runtime"
    assert classify_endpoint("http://ollama:11434", "container") == "container_service"
    assert classify_endpoint("http://host.docker.internal:11434", "container") == "native_host"
    assert classify_endpoint("https://ollama.example.test", "native") == "remote"
    assert (
        safe_endpoint_display("http://owner:secret@example.test:11434/path?token=hidden")
        == "http://example.test:11434"
    )


def test_ollama_probe_combines_tags_show_and_running_model_evidence():
    gib = 1024**3

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "test:latest",
                            "model": "test:latest",
                            "digest": "abc123",
                            "size": 4 * gib,
                            "details": {
                                "family": "test",
                                "parameter_size": "7B",
                                "quantization_level": "Q4_K_M",
                            },
                        }
                    ]
                },
            )
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "1.2.3"})
        if request.url.path == "/api/show":
            assert request.method == "POST"
            return httpx.Response(
                200,
                json={
                    "capabilities": ["completion", "tools"],
                    "model_info": {"test.context_length": 32768},
                },
            )
        if request.url.path == "/api/ps":
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "test:latest",
                            "model": "test:latest",
                            "size": 5 * gib,
                            "size_vram": 4 * gib,
                            "context_length": 8192,
                            "expires_at": "2026-08-26T12:00:00Z",
                        }
                    ]
                },
            )
        return httpx.Response(404)

    result = probe_ollama(
        "http://localhost:11434",
        "native",
        "test:latest",
        transport=httpx.MockTransport(handler),
    )
    assert result.endpoint.reachable is True
    assert result.endpoint.version == "1.2.3"
    assert result.endpoint.installed_model_count == 1
    assert result.requested_model_installed is True
    assert result.selected_model is not None
    assert result.selected_model.native_context_length == 32768
    assert result.selected_model.allocated_context_length == 8192
    assert result.selected_model.placement == "split"
    assert result.selected_model.accelerator_fraction == 0.8
    assert result.selected_model.capabilities == ["completion", "tools"]


def test_ollama_probe_returns_structured_unreachable_result():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    result = probe_ollama(
        "http://localhost:11434",
        "native",
        "test:latest",
        transport=httpx.MockTransport(handler),
    )
    assert result.endpoint.reachable is False
    assert result.endpoint.error is not None
    assert result.endpoint.error.code == "ollama_unreachable"
    assert "no route" not in result.endpoint.error.message
    assert result.selected_model is None


def test_discovery_does_not_mislabel_container_as_native_ollama_host(monkeypatch):
    monkeypatch.setattr(discovery, "inspect_runtime_host", lambda: runtime_host(runtime_kind="container"))
    monkeypatch.setattr(settings, "ollama_host", "http://host.docker.internal:1")

    report = discovery.discover_capabilities("test:latest")
    assert report.read_only is True
    assert report.runtime_host.applies_to_ollama_device == "no"
    assert report.ollama.relationship == "native_host"
    assert report.ollama.reachable is False
    assert next(item for item in report.capabilities if item.key == "ollama_device_hardware").status == "unavailable"
    assert any(item.code == "native_host_partial_visibility" for item in report.warnings)
    assert any(item.code == "ollama_unreachable" for item in report.warnings)
    assert next(item for item in report.capabilities if item.key == "persistent_changes").status == "unsupported"


def test_optimizer_route_is_authenticated_and_unreachable_is_report_data(client, monkeypatch):
    with TestClient(app) as unauthenticated:
        assert unauthenticated.get("/optimizer/capabilities").status_code == 401

    monkeypatch.setattr(discovery, "inspect_runtime_host", lambda: runtime_host())
    monkeypatch.setattr(settings, "ollama_host", "http://host.docker.internal:1")
    response = client.get("/optimizer/capabilities", params={"model_tag": "test:latest"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["read_only"] is True
    assert payload["ollama"]["reachable"] is False
    assert payload["ollama"]["error"]["code"] == "ollama_unreachable"
    hardware = next(item for item in payload["capabilities"] if item["key"] == "ollama_device_hardware")
    assert hardware["status"] == "unavailable"


def test_optimizer_route_rejects_invalid_model_tag_before_discovery(client):
    response = client.get("/optimizer/capabilities", params={"model_tag": "bad tag\nwith whitespace"})
    assert response.status_code == 422
