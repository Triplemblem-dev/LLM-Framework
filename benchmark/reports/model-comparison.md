# Model Comparison Benchmark Report

Models: gemma2:9b, llama3.1:8b, llama3.1:8b-instruct-q5_K_M, qwen2.5-coder:7b, qwen3:8b
Prompts run: 18 per model, 90 total
Scored: 0/90 — run benchmark/score.py to finish scoring

## Overall comparison

| Model | Avg quality (1-5) | Pass rate | Avg tok/s | Avg TTFT (s) | Peak VRAM (MB) | GPU % | Quant | Errors |
|---|---|---|---|---|---|---|---|---|
| `gemma2:9b` | n/a | n/a | 32.2 | 0.82 | 6510 | 100% | Q4_0 | 0 |
| `llama3.1:8b` | n/a | n/a | 39.8 | 0.54 | 5281 | 100% | Q4_K_M | 0 |
| `llama3.1:8b-instruct-q5_K_M` | n/a | n/a | 35.4 | 0.73 | 5944 | 100% | Q5_K_M | 0 |
| `qwen2.5-coder:7b` | n/a | n/a | 41.3 | 0.46 | 4923 | 100% | Q4_K_M | 0 |
| `qwen3:8b` | n/a | n/a | 39.0 | 0.65 | 5554 | 100% | Q4_K_M | 0 |

## By category (avg quality 1-5)

| Category | `gemma2:9b` | `llama3.1:8b` | `llama3.1:8b-instruct-q5_K_M` | `qwen2.5-coder:7b` | `qwen3:8b` |
|---|---|---|---|---|---|
| coding | n/a | n/a | n/a | n/a | n/a |
| domain_adherence | n/a | n/a | n/a | n/a | n/a |
| general_reasoning | n/a | n/a | n/a | n/a | n/a |
| hallucination_resistance | n/a | n/a | n/a | n/a | n/a |
| instruction_following | n/a | n/a | n/a | n/a | n/a |
| language | n/a | n/a | n/a | n/a | n/a |
| requirements_engineering | n/a | n/a | n/a | n/a | n/a |

## By category (pass rate on expected behavior)

| Category | `gemma2:9b` | `llama3.1:8b` | `llama3.1:8b-instruct-q5_K_M` | `qwen2.5-coder:7b` | `qwen3:8b` |
|---|---|---|---|---|---|
| coding | n/a | n/a | n/a | n/a | n/a |
| domain_adherence | n/a | n/a | n/a | n/a | n/a |
| general_reasoning | n/a | n/a | n/a | n/a | n/a |
| hallucination_resistance | n/a | n/a | n/a | n/a | n/a |
| instruction_following | n/a | n/a | n/a | n/a | n/a |
| language | n/a | n/a | n/a | n/a | n/a |
| requirements_engineering | n/a | n/a | n/a | n/a | n/a |
