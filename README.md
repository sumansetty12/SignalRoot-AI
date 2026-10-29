# SignalRoot AI — v0.5.0

**Understand incidents. Find root causes. Restore reliability.**

Read-only research prototype. **Preserves the entire v0.4.0 baseline and optional AI endpoint**, and introduces a **separate synthetic challenge dataset** with transparent safety-oriented evaluation metrics.

> **Important:** The 30 new challenge scenarios are written by the project developer; they have not been independently labeled and are **not** proof of real-world diagnosis accuracy. Live LLM performance has **not** been measured unless you explicitly configure and run the live test yourself. This ZIP does not include an AI model or an API key.

## Windows setup (extract into separate folder first)

Open VS Code terminal in the extracted `SignalRoot-AI` folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -v
python benchmark\run_benchmark.py
python benchmark\evaluate.py --engine baseline
python benchmark\challenge_eval.py --engine baseline
uvicorn app:app --reload
```

If PowerShell blocks activation: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` then activate again. Open <http://127.0.0.1:8000/docs>. Stop with `Ctrl+C`.

The last baseline command creates a `benchmark/challenge_report_baseline.json` report (ignored by Git). It prints **accuracy, coverage, selective accuracy, abstention rate, incorrect confident diagnoses, per-label accuracy and confusion matrix.** The challenge dataset has a SHA-256 manifest to detect unreviewed edits.

## Optional live AI evaluation — paid, NOT required

Only use synthetic cases. Real incident logs may disclose confidential information to the API provider. API billing and quota are separate from ChatGPT subscription.

In PowerShell, set the key *only* in your current session:

```powershell
$env:OPENAI_API_KEY = '<your API key>'
$env:SIGNALROOT_MODEL = 'gpt-4o-mini'
```

**Live AI evaluation is deliberately locked** unless you supply `--allow-live-ai`. It can issue external paid API calls; the challenge set has 29 cases with signals, so the default 10-call cap intentionally blocks the full run. To run the full set, explicitly raise the cap:

```powershell
python benchmark\challenge_eval.py --engine compare --allow-live-ai --max-ai-calls 30
```

This can use **up to 29 paid requests**; evaluate billing and usage limits first. The model must support Chat Completions and JSON-object mode. You can also test one synthetic incident in `POST /diagnose/ai` at `/docs` before doing a batch run. Provider failures are reported separately from abstentions. Model outputs are validated for evidence IDs, but this does not establish explanation correctness.

`Remove-Item Env:OPENAI_API_KEY` removes the key from the current session.

## Files and version boundaries

- `app.py`: original rules-based diagnosis + optional `/diagnose/ai` endpoint; version only updated.
- `ai_engine.py`: existing opt-in model adapter, evidence-ID checks, and fail-closed handling.
- `benchmark/run_benchmark.py`: original 18 synthetic regression scenarios.
- `benchmark/evaluate.py`: original 6 developer-authored development scenarios.
- **`benchmark/challenge_cases.json`: 30 additional synthetic challenge scenarios with labeling rationales.**
- **`benchmark/challenge_manifest.json`: SHA-256 fingerprint and labeling policy.**
- **`benchmark/challenge_eval.py`: expanded offline/live comparative evaluator and metrics.**
- **`tests/test_challenge_eval.py`: tests for manifest checks, metrics and safe evaluation.**

## Research limitations and next step

The new challenge set is still authored in the same project and not blinded. A credible research claim requires independently sourced incidents (appropriately anonymized), labeling by multiple external reviewers, pre-registered comparison methods, and tests of diagnosis correctness and evidence faithfulness. We should not adjust the frozen challenge labels to make model scores look better. This system does not perform remediation or production integrations.
