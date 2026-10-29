# SignalRoot AI — v0.4.0

**Understand incidents. Find root causes. Restore reliability.**

Read-only research prototype for incident diagnosis. The original **v0.3.0 heuristic diagnosis** is preserved at `POST /diagnose`; a separate **optional live LLM-powered analysis** is available at `POST /diagnose/ai`.

> The AI model is not included in the ZIP. Live AI calls require **your own API key**, internet access, and may incur API charges. You can run all 28 tests and the baseline evaluation without a key. The tests mock model responses; they do not establish AI diagnostic accuracy.

## Windows PowerShell quick start

1. Extract the ZIP and open `SignalRoot-AI` in VS Code, with the terminal in that folder.
2. Run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -v
python benchmark\run_benchmark.py
python benchmark\evaluate.py
uvicorn app:app --reload
```

If activation is blocked, run `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, then retry activation. Open <http://127.0.0.1:8000/docs> for the API interface. `GET /incident` returns a synthetic incident you can copy into `POST /diagnose`.

## Optional: enable a live AI call

**Do not send employer data, real production logs, personal information, credentials or customer details. Only use synthetic test incidents.** Data entered in `/diagnose/ai` is transmitted to the API provider. Review API billing and data processing terms before enabling.

In your current PowerShell session, set environment variables (do not add keys to source files or Git):

```powershell
$env:OPENAI_API_KEY = "<your API key>"
$env:SIGNALROOT_MODEL = "gpt-4o-mini"
```

Then use `POST /diagnose/ai` in `/docs` with synthetic inputs. This is an example model name; use a model with Chat Completions JSON-object support available to your API account. **A ChatGPT subscription does not automatically include API usage.** The model call may fail if your account lacks API access, quota, or a compatible model.

To disable live calls: `Remove-Item Env:OPENAI_API_KEY`.

## Architecture

- `app.py`: unchanged v0.3.0 `diagnose()` heuristic baseline, plus a new endpoint.
- `ai_engine.py`: explicit evidence IDs, fixed prompt, optional API call, validation, and fail-closed abstention.
- `tests/test_diagnosis.py`: the original 13 baseline tests.
- `tests/test_ai_engine.py`: deterministic unit tests using fake model responses (no external calls).
- `benchmark/run_benchmark.py`: original 18-case synthetic baseline benchmark.
- `benchmark/evaluate.py`: configurable evaluator for baseline or live AI; writes separate report files.
- `benchmark/development_cases.json`: separate *developer-authored* development cases, not a held-out independent benchmark.

## API

- `GET /health` — app version and status
- `GET /incident` — example synthetic incident
- `POST /diagnose` — baseline, offline, free
- `POST /diagnose/ai` — optional live LLM, needs API key

The AI endpoint returns one of three labels: `Deployment regression`, `Dependency or database degradation`, or `Insufficient evidence`. It also returns evidence IDs citing input signals and read-only next steps. Invalid hallucinated IDs, unsupported labels, and remediation recommendations cause abstention. A provider outage is reported as an error, not miscounted as a diagnosis.

## Evaluate research progress

Offline, without API key:

```powershell
python benchmark\run_benchmark.py
python benchmark\evaluate.py --engine baseline
```

Optional paid live comparison (after configuring API key):

```powershell
python benchmark\evaluate.py --engine ai
```

Both evaluation files use **handwritten synthetic examples created by the developer**. They are useful for smoke testing, not proof of superior AI performance. Never claim the v0.3.0 baseline has been beaten until a larger pre-registered, independently labeled, blinded dataset has been used with fair baselines. The model's response is not guaranteed reproducible, even with temperature zero.

## Safety limits

Read-only; no remediation execution. No system integrations. AI prompts and output are untrusted. Provider failures, invalid output, and unsupported evidence do not become confident diagnoses. Evidence IDs validate references, but **do not validate the factual correctness of the model's explanation**; human review is essential. This prototype is not production-ready.
