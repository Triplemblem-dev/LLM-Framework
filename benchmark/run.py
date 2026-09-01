#!/usr/bin/env python3
"""Model benchmark harness — runs benchmark/prompts.yaml against one or
more Ollama models, recording raw responses, latency (including
time-to-first-token), model settings, and resource use (VRAM/GPU
utilization sampled during generation, GPU/CPU split from /api/ps).

Usage:
    python3 benchmark/run.py
    python3 benchmark/run.py --models llama3.1:8b,qwen2.5-coder:7b
    python3 benchmark/run.py --only-prompt coding-pgvector-query

Results are written to benchmark/results/<run-id>/<model>/<prompt-id>.json
Then score with:  python3 benchmark/score.py <run-id>
And report with:  python3 benchmark/report.py <run-id>
"""
import argparse
import json
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import yaml

DEFAULT_MODELS = [
    "llama3.1:8b",
    "qwen2.5-coder:7b",
    "qwen3:8b",
    "gemma2:9b",
    "llama3.1:8b-instruct-q5_K_M",
]

BENCH_DIR = Path(__file__).parent
DEFAULT_PROMPTS_FILE = BENCH_DIR / "prompts.yaml"
DEFAULT_RESULTS_DIR = BENCH_DIR / "results"


class ResourceSampler:
    """Samples nvidia-smi in the background while a request is in flight."""

    def __init__(self, interval: float = 0.4):
        self.interval = interval
        self._samples: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _sample_loop(self):
        while not self._stop.is_set():
            try:
                out = subprocess.run(
                    [
                        "nvidia-smi",
                        "--query-gpu=memory.used,utilization.gpu,power.draw,temperature.gpu",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=2,
                ).stdout.strip()
                mem, util, power, temp = [x.strip() for x in out.split(",")]
                self._samples.append(
                    {
                        "vram_used_mb": float(mem),
                        "gpu_util_pct": float(util),
                        "power_draw_w": float(power),
                        "temperature_c": float(temp),
                    }
                )
            except Exception:
                pass
            self._stop.wait(self.interval)

    def start(self):
        self._stop.clear()
        self._samples = []
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def stop(self) -> dict:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        return self._summarize()

    def _summarize(self) -> dict:
        if not self._samples:
            return {"samples": 0}

        def agg(key: str) -> dict:
            vals = [s[key] for s in self._samples]
            return {"avg": sum(vals) / len(vals), "peak": max(vals)}

        return {
            "samples": len(self._samples),
            "vram_used_mb": agg("vram_used_mb"),
            "gpu_util_pct": agg("gpu_util_pct"),
            "power_draw_w": agg("power_draw_w"),
            "temperature_c": agg("temperature_c"),
        }


def unload_other_models(target_model: str, host: str):
    """Ollama keeps a model resident for several minutes by default
    (keep_alive), which would otherwise contaminate both the next model's
    cold-load timing and the background VRAM sampler's readings (system-wide,
    not per-model) with leftover VRAM from the previous model. Force-unload
    anything else before starting a new model's block of prompts."""
    try:
        resp = httpx.get(f"{host}/api/ps", timeout=5)
        resp.raise_for_status()
        loaded = [m.get("model") for m in resp.json().get("models", [])]
    except Exception:
        return
    for m in loaded:
        if m and m != target_model:
            try:
                httpx.post(f"{host}/api/generate", json={"model": m, "keep_alive": 0}, timeout=30)
            except Exception:
                pass
    # give Ollama a moment to actually free the VRAM before we start sampling
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            resp = httpx.get(f"{host}/api/ps", timeout=5)
            still_loaded = [m.get("model") for m in resp.json().get("models", [])]
            if all(m == target_model for m in still_loaded):
                return
        except Exception:
            return
        time.sleep(0.5)


def get_ollama_ps(model: str, host: str) -> dict | None:
    """Snapshot of how Ollama is currently running this model (GPU/CPU split,
    quantization, context length) via GET /api/ps."""
    try:
        resp = httpx.get(f"{host}/api/ps", timeout=5)
        resp.raise_for_status()
        for m in resp.json().get("models", []):
            if m.get("model") == model or m.get("name") == model:
                size = m.get("size") or 0
                size_vram = m.get("size_vram") or 0
                gpu_pct = round(100 * size_vram / size, 1) if size else None
                details = m.get("details", {})
                return {
                    "size_bytes": size,
                    "size_vram_bytes": size_vram,
                    "gpu_pct": gpu_pct,
                    "context_length": m.get("context_length"),
                    "quantization_level": details.get("quantization_level"),
                    "parameter_size": details.get("parameter_size"),
                }
    except Exception:
        return None
    return None


def run_prompt(model: str, prompt: dict, host: str, options: dict) -> dict:
    messages = []
    if prompt.get("system"):
        messages.append({"role": "system", "content": prompt["system"]})
    messages.append({"role": "user", "content": prompt["user"]})

    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "think": options.get("think", False),
        "options": {
            "num_ctx": options.get("num_ctx", 4096),
            "temperature": options.get("temperature", 0.7),
        },
    }

    sampler = ResourceSampler()
    sampler.start()

    content_parts: list[str] = []
    thinking_parts: list[str] = []
    first_token_time = None
    final_stats: dict = {}
    error = None
    wall_start = time.monotonic()

    try:
        with httpx.stream("POST", f"{host}/api/chat", json=payload, timeout=300) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line)
                msg = chunk.get("message", {})
                text = msg.get("content", "")
                think_text = msg.get("thinking", "")
                if (text or think_text) and first_token_time is None:
                    first_token_time = time.monotonic() - wall_start
                if text:
                    content_parts.append(text)
                if think_text:
                    thinking_parts.append(think_text)
                if chunk.get("done"):
                    final_stats = {
                        k: chunk.get(k)
                        for k in (
                            "total_duration",
                            "load_duration",
                            "prompt_eval_count",
                            "prompt_eval_duration",
                            "eval_count",
                            "eval_duration",
                        )
                    }
    except Exception as e:
        error = str(e)

    wall_total = time.monotonic() - wall_start
    resource_summary = sampler.stop()
    ps_info = get_ollama_ps(model, host)

    eval_count = final_stats.get("eval_count") or 0
    eval_duration_ns = final_stats.get("eval_duration") or 0
    tokens_per_second = eval_count / (eval_duration_ns / 1e9) if eval_duration_ns else None

    return {
        "model": model,
        "prompt_id": prompt["id"],
        "category": prompt["category"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request": {
            "system": prompt.get("system"),
            "user": prompt["user"],
            "options": payload["options"],
            "think": payload["think"],
        },
        "response": {
            "content": "".join(content_parts),
            "thinking": "".join(thinking_parts) or None,
        },
        "metrics": {
            "wall_clock_total_s": wall_total,
            "time_to_first_token_s": first_token_time,
            "total_duration_s": (final_stats.get("total_duration") or 0) / 1e9,
            "load_duration_s": (final_stats.get("load_duration") or 0) / 1e9,
            "prompt_eval_count": final_stats.get("prompt_eval_count"),
            "prompt_eval_duration_s": (final_stats.get("prompt_eval_duration") or 0) / 1e9,
            "eval_count": eval_count,
            "eval_duration_s": (eval_duration_ns or 0) / 1e9,
            "tokens_per_second": tokens_per_second,
        },
        "resource": resource_summary,
        "ollama_ps": ps_info,
        "error": error,
    }


def main():
    parser = argparse.ArgumentParser(description="Model benchmark harness")
    parser.add_argument(
        "--models", default=",".join(DEFAULT_MODELS), help="comma-separated Ollama model tags"
    )
    parser.add_argument("--prompts", default=str(DEFAULT_PROMPTS_FILE))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--host", default="http://localhost:11434")
    parser.add_argument("--num-ctx", type=int, default=4096)
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument(
        "--think",
        action="store_true",
        default=False,
        help="allow reasoning-capable models to use hidden chain-of-thought (default: off, "
        "for fair latency comparison)",
    )
    parser.add_argument("--only-prompt", default=None, help="run a single prompt id (for debugging)")
    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",") if m.strip()]
    with open(args.prompts) as f:
        prompts = yaml.safe_load(f)
    if args.only_prompt:
        prompts = [p for p in prompts if p["id"] == args.only_prompt]
        if not prompts:
            raise SystemExit(f"no prompt with id {args.only_prompt}")

    run_id = args.run_id or datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = DEFAULT_RESULTS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    options = {"num_ctx": args.num_ctx, "temperature": args.temperature, "think": args.think}

    print(f"Run ID: {run_id}")
    print(f"Models: {models}")
    print(f"Prompts: {len(prompts)}")
    print(f"Options: {options}")
    print(f"Output: {run_dir}")
    print()

    total = len(models) * len(prompts)
    done = 0
    for model in models:
        print(f"Unloading other models before starting {model} ...", flush=True)
        unload_other_models(model, args.host)
        model_dir = run_dir / model.replace(":", "_").replace("/", "_")
        model_dir.mkdir(parents=True, exist_ok=True)
        for prompt in prompts:
            done += 1
            print(f"[{done}/{total}] {model} :: {prompt['id']} ... ", end="", flush=True)
            result = run_prompt(model, prompt, args.host, options)
            out_file = model_dir / f"{prompt['id']}.json"
            out_file.write_text(json.dumps(result, indent=2))
            if result["error"]:
                print(f"ERROR: {result['error']}")
            else:
                tps = result["metrics"]["tokens_per_second"]
                ttft = result["metrics"]["time_to_first_token_s"]
                if tps and ttft is not None:
                    print(f"ok ({tps:.1f} tok/s, ttft {ttft:.2f}s)")
                else:
                    print("ok")

    print()
    print(f"Done. Results in {run_dir}")
    print(f"Next: python3 benchmark/score.py {run_id}")


if __name__ == "__main__":
    main()
