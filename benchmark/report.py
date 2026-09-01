#!/usr/bin/env python3
"""Comparison report generator. Aggregates raw results + human
scores for a run into a Markdown report: per-model overall and
per-category scores, speed, and resource use.

Usage:
    python3 benchmark/report.py <run-id>
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path
from statistics import mean

BENCH_DIR = Path(__file__).parent
DEFAULT_RESULTS_DIR = BENCH_DIR / "results"
DEFAULT_REPORTS_DIR = BENCH_DIR / "reports"


def load_run(run_dir: Path):
    results = []
    for f in sorted(run_dir.glob("*/*.json")):
        if f.name.endswith(".score.json"):
            continue
        result = json.loads(f.read_text())
        score_file = f.with_suffix(".score.json")
        result["score"] = json.loads(score_file.read_text()) if score_file.exists() else None
        results.append(result)
    return results


def fmt(x, decimals=1, suffix=""):
    return f"{x:.{decimals}f}{suffix}" if x is not None else "n/a"


def build_report(run_id: str, results: list[dict]) -> str:
    models = sorted({r["model"] for r in results})
    categories = sorted({r["category"] for r in results})

    by_model = defaultdict(list)
    for r in results:
        by_model[r["model"]].append(r)

    lines = []
    lines.append(f"# Model Comparison Benchmark Report — run `{run_id}`")
    lines.append("")
    lines.append(f"Models: {', '.join(models)}")
    lines.append(f"Prompts run: {len(results) // len(models) if models else 0} per model, "
                  f"{len(results)} total")
    n_scored = sum(1 for r in results if r["score"])
    lines.append(f"Scored: {n_scored}/{len(results)}"
                  + ("" if n_scored == len(results) else " — run benchmark/score.py to finish scoring"))
    n_errors = sum(1 for r in results if r["error"])
    if n_errors:
        lines.append(f"**{n_errors} result(s) had errors — see Errors section below.**")
    lines.append("")

    lines.append("## Overall comparison")
    lines.append("")
    lines.append(
        "| Model | Avg quality (1-5) | Pass rate | Avg tok/s | Avg TTFT (s) | "
        "Peak VRAM (MB) | GPU % | Quant | Errors |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for model in models:
        rows = by_model[model]
        scored = [r["score"] for r in rows if r["score"]]
        quality = mean([s["quality_1_5"] for s in scored]) if scored else None
        pass_rate = (
            100 * sum(1 for s in scored if s["meets_expected_behavior"]) / len(scored)
            if scored
            else None
        )
        tps_vals = [r["metrics"]["tokens_per_second"] for r in rows if r["metrics"].get("tokens_per_second")]
        ttft_vals = [
            r["metrics"]["time_to_first_token_s"]
            for r in rows
            if r["metrics"].get("time_to_first_token_s") is not None
        ]
        vram_vals = [
            r["resource"]["vram_used_mb"]["peak"]
            for r in rows
            if r.get("resource", {}).get("vram_used_mb")
        ]
        gpu_pct_vals = [r["ollama_ps"]["gpu_pct"] for r in rows if r.get("ollama_ps", {}).get("gpu_pct") is not None]
        quant = next((r["ollama_ps"]["quantization_level"] for r in rows if r.get("ollama_ps")), None)
        errors = sum(1 for r in rows if r["error"])

        lines.append(
            "| `{model}` | {q} | {pr} | {tps} | {ttft} | {vram} | {gpu} | {quant} | {err} |".format(
                model=model,
                q=fmt(quality, 2),
                pr=fmt(pass_rate, 0, "%"),
                tps=fmt(mean(tps_vals) if tps_vals else None),
                ttft=fmt(mean(ttft_vals) if ttft_vals else None, 2),
                vram=fmt(max(vram_vals) if vram_vals else None, 0),
                gpu=fmt(mean(gpu_pct_vals) if gpu_pct_vals else None, 0, "%"),
                quant=quant or "n/a",
                err=errors,
            )
        )
    lines.append("")

    lines.append("## By category (avg quality 1-5)")
    lines.append("")
    lines.append("| Category | " + " | ".join(f"`{m}`" for m in models) + " |")
    lines.append("|---|" + "---|" * len(models))
    for cat in categories:
        row = [cat]
        for model in models:
            scored = [
                r["score"]["quality_1_5"]
                for r in by_model[model]
                if r["category"] == cat and r["score"]
            ]
            row.append(fmt(mean(scored), 2) if scored else "n/a")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    lines.append("## By category (pass rate on expected behavior)")
    lines.append("")
    lines.append("| Category | " + " | ".join(f"`{m}`" for m in models) + " |")
    lines.append("|---|" + "---|" * len(models))
    for cat in categories:
        row = [cat]
        for model in models:
            scored = [
                r["score"]["meets_expected_behavior"]
                for r in by_model[model]
                if r["category"] == cat and r["score"]
            ]
            if scored:
                row.append(fmt(100 * sum(scored) / len(scored), 0, "%"))
            else:
                row.append("n/a")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")

    failed = [r for r in results if r["score"] and not r["score"]["meets_expected_behavior"]]
    if failed:
        lines.append("## Failed expected-behavior checks")
        lines.append("")
        for r in failed:
            note = f" — {r['score']['notes']}" if r["score"].get("notes") else ""
            lines.append(f"- `{r['model']}` / `{r['prompt_id']}` (quality {r['score']['quality_1_5']}/5){note}")
        lines.append("")

    if n_errors:
        lines.append("## Errors")
        lines.append("")
        for r in results:
            if r["error"]:
                lines.append(f"- `{r['model']}` / `{r['prompt_id']}`: {r['error']}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Model comparison report generator")
    parser.add_argument("run_id")
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    parser.add_argument("--reports-dir", default=str(DEFAULT_REPORTS_DIR))
    args = parser.parse_args()

    run_dir = Path(args.results_dir) / args.run_id
    if not run_dir.is_dir():
        raise SystemExit(f"no such run: {run_dir}")

    results = load_run(run_dir)
    if not results:
        raise SystemExit(f"no results found in {run_dir}")

    report = build_report(args.run_id, results)

    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    out_file = reports_dir / f"{args.run_id}.md"
    out_file.write_text(report)

    print(report)
    print(f"\n(written to {out_file})")


if __name__ == "__main__":
    main()
