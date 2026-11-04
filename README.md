# AI Agents for Beginners — Day 3: Production Lab

A **fully independent Day 3** lab implementation, based on Taller Academy's six-exercise brief, using only **synthetic** contracts, order history, and vendors. This is **not** Day 2 and contains no employer/client records, API secrets or real refund integration.

## What is included

| Exercise | Implementation / evidence |
|---|---|
| **3.1** Iterative retrieval | `retrieval_agent.py`, eight-document corpus; search traces, citations and four controlled experiments in `run_experiments.py` |
| **3.2** Statistical evaluation | `eval_harness.py`, three original cases plus a fourth stress case; outcome and process checks, strict rate, token totals, 5-step cap, vague-tool regression, precommitted release bar |
| **3.3** Human approval and safety | `guardrails.py`, validation, quotas, simulated refund actions, human-in-the-loop demonstration and four adversarial scenarios |
| **3.4** Prompt caching/cost | `cost_lab.py` for **hosted Anthropic** usage; `COST_WORKSHEET.md` for explicitly theoretical cost arithmetic |
| **3.5** Production design | `PRODUCTION_READINESS.md`, five-section independent review with numerical release thresholds |
| **3.6** Tests without a model | `test_guardrails.py` (16 course checks), `tests/test_production.py` and `tests/test_runtime.py` (40 additional checks), including boundary, check order, scorer, and intentional broken-validator detection |

## Test locally (no key, no Ollama)

```bash
python3 -m unittest discover -s tests -v
python3 test_guardrails.py
```

## Run real model experiments on local Ollama

Install Ollama from its official website, then:

```bash
ollama serve            # separate terminal, if not already running
ollama pull qwen2.5:3b
python3 run_experiments.py --full
python3 finalize_submission.py
```

`--full` runs the evaluation suite **three times per case** as requested by the brief. This may be slow on consumer hardware; for a quicker smoke test omit `--full` (one run per case). The scripts call Ollama's real `/api/chat` endpoint, and token counts come directly from `prompt_eval_count` and `eval_count`. A model failing a question is real evidence, **not** an excuse to fill in invented data.

The real-model result goes into `results/experiments.json`; the finalizer writes `results/EVIDENCE.md` and adds the observed sections to `SUBMISSION.md`. If the model cannot run, those observations remain clearly marked pending.

## Hosted Anthropic (optional)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U anthropic
export ANTHROPIC_API_KEY='your-key-in-this-shell-only'
export FDE_PROVIDER=anthropic
export FDE_MODEL='a-current-model-accessible-to-your-key'
python3 run_experiments.py --full
python3 finalize_submission.py
python3 cost_lab.py
```

**Important:** `cost_lab.py` measures Anthropic prompt caching. **Ollama cannot produce real Anthropic cache-write/cache-read token tables**; `COST_WORKSHEET.md` labels its examples as theoretical. Do not fabricate API data or publish an API key.

## GitHub Actions

`.github/workflows/tests.yml` runs deterministic security tests on each push. `.github/workflows/live_model_lab.yml` executes real experiments using Ollama on a GitHub runner, records complete raw traces, and commits the observed-evidence sections when all experiments complete successfully. If the workflow fails or the model returns poor answers, inspect its logs and leave failures visible rather than silently changing evaluation thresholds.

## Submission

Submit the **Day 3 repository root URL**, e.g. `https://github.com/kNightRunner/taller-academy-fde-day3-production`, **not** the Day 2 Building Blocks repository. The prior **2/3** grade came from submitting Day 2 materials to Day 3's assignment. Read `SUBMISSION.md` for all six exercises and source links. `TEST_RESULTS.md` records real, offline test evidence.

All samples are fictional and historical, not legal/procurement, financial, or operational advice. Every refund is recorded **in-memory only**. No real payment is performed.