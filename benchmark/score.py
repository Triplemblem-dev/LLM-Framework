#!/usr/bin/env python3
"""Human-scoring CLI. Walks through raw results for a run that
don't have a score yet, shows the prompt/expected-behavior/response, and
records a 1-5 quality score + pass/fail + notes to a paired .score.json
file next to the result.

Usage:
    python3 benchmark/score.py <run-id>
    python3 benchmark/score.py <run-id> --rescore   # re-score everything
    python3 benchmark/score.py <run-id> --model llama3.1:8b
"""
import argparse
import json
from pathlib import Path

import yaml

BENCH_DIR = Path(__file__).parent
DEFAULT_PROMPTS_FILE = BENCH_DIR / "prompts.yaml"
DEFAULT_RESULTS_DIR = BENCH_DIR / "results"


def load_prompts_by_id(prompts_file: Path) -> dict:
    with open(prompts_file) as f:
        prompts = yaml.safe_load(f)
    return {p["id"]: p for p in prompts}


def prompt_int(msg: str, lo: int, hi: int) -> int:
    while True:
        raw = input(msg).strip()
        if raw.isdigit() and lo <= int(raw) <= hi:
            return int(raw)
        print(f"  enter a number from {lo} to {hi}")


def prompt_yn(msg: str) -> bool:
    while True:
        raw = input(msg).strip().lower()
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("  enter y or n")


def main():
    parser = argparse.ArgumentParser(description="Benchmark human-scoring CLI")
    parser.add_argument("run_id")
    parser.add_argument("--results-dir", default=str(DEFAULT_RESULTS_DIR))
    parser.add_argument("--prompts", default=str(DEFAULT_PROMPTS_FILE))
    parser.add_argument("--model", default=None, help="only score results for this model tag")
    parser.add_argument("--rescore", action="store_true", help="re-score results that already have a score")
    args = parser.parse_args()

    run_dir = Path(args.results_dir) / args.run_id
    if not run_dir.is_dir():
        raise SystemExit(f"no such run: {run_dir}")

    prompts_by_id = load_prompts_by_id(Path(args.prompts))

    result_files = sorted(run_dir.glob("*/*.json"))
    result_files = [f for f in result_files if not f.name.endswith(".score.json")]
    if args.model:
        model_dirname = args.model.replace(":", "_").replace("/", "_")
        result_files = [f for f in result_files if f.parent.name == model_dirname]

    pending = []
    for f in result_files:
        score_file = f.with_suffix(".score.json")
        if score_file.exists() and not args.rescore:
            continue
        pending.append(f)

    if not pending:
        print("Nothing to score (use --rescore to redo existing scores).")
        return

    print(f"{len(pending)} response(s) to score. Enter 'q' at any prompt to stop and save progress.\n")

    for i, f in enumerate(pending, 1):
        result = json.loads(f.read_text())
        prompt_meta = prompts_by_id.get(result["prompt_id"], {})

        print("=" * 78)
        print(f"[{i}/{len(pending)}] {result['model']}  ::  {result['prompt_id']}  ({result['category']})")
        print("-" * 78)
        if result["request"].get("system"):
            print(f"SYSTEM: {result['request']['system'][:300]}")
        print(f"USER: {result['request']['user']}")
        print("-" * 78)
        expected = prompt_meta.get("expected_behavior", "").strip()
        if expected:
            print(f"EXPECTED BEHAVIOR (rubric, not sent to the model):\n  {expected}")
            print("-" * 78)
        if result["error"]:
            print(f"ERROR DURING GENERATION: {result['error']}")
        else:
            print("RESPONSE:")
            print(result["response"]["content"])
            if result["response"].get("thinking"):
                print("-" * 78)
                print(f"[hidden thinking, {len(result['response']['thinking'])} chars — not shown in full]")
        m = result["metrics"]
        tps = m.get("tokens_per_second")
        ttft = m.get("time_to_first_token_s")
        print("-" * 78)
        print(
            f"speed: {tps:.1f} tok/s" if tps else "speed: n/a",
            f"| first token: {ttft:.2f}s" if ttft is not None else "",
        )
        print()

        raw = input("Quality score 1-5 (or 'q' to stop, 's' to skip): ").strip().lower()
        if raw == "q":
            print("Stopping. Progress saved so far.")
            break
        if raw == "s":
            print("Skipped.\n")
            continue
        if not raw.isdigit() or not (1 <= int(raw) <= 5):
            print("  invalid input, skipping this one.\n")
            continue
        quality = int(raw)

        passed = prompt_yn("Meets the expected behavior? (y/n): ")
        notes = input("Notes (optional, enter to skip): ").strip()

        score = {
            "run_id": args.run_id,
            "model": result["model"],
            "prompt_id": result["prompt_id"],
            "category": result["category"],
            "quality_1_5": quality,
            "meets_expected_behavior": passed,
            "notes": notes or None,
        }
        f.with_suffix(".score.json").write_text(json.dumps(score, indent=2))
        print("Saved.\n")

    print("Done. Run: python3 benchmark/report.py " + args.run_id)


if __name__ == "__main__":
    main()
