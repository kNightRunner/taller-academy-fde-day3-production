# Offline test evidence — Day 3

**Environment:** Python 3.13 on the artifact-building host, November 4, 2026. No API keys, Ollama model, network or customer records were used.

Commands executed:

```bash
python -m unittest discover -s tests -v
python test_guardrails.py
python -m compileall -q .
```

**Observed result:**

```text
Ran 40 tests in 0.004s
OK

16 passed, 0 failed
```

The surrounding command process, startup and test discovery completed in approximately **1.22 seconds** on this host. The 40 tests include arguments, boundaries, security check order, fail-closed approval, prompt injection, model response translation, and the intentionally broken validator control. The 16 additional tests follow the course's original `test_guardrails.py` exercise.

**Scope limitation:** these are deterministic tests, not proof of a model's retrieval quality or Anthropic caching behavior. The model-driven experiments must be executed against Ollama/Anthropic to measure actual agent responses and token counts.