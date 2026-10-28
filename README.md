# SignalRoot AI

Evidence-grounded incident diagnosis for startups and small engineering teams.

> Prototype status: local, synthetic data only. Not for production use.

The first milestone is a local, reproducible deployment-failure scenario. The tool inspects structured incident evidence, ranks root-cause hypotheses, and shows which signals support each hypothesis. It does not connect to production systems or execute remediation.

## Status

Early prototype — research and product hypotheses are not yet validated. Do not use for production incident response.

## Project goals

- Explain a simulated deployment regression using supplied evidence.
- Establish a reproducible baseline for evidence-grounded incident diagnosis.
- Test that the known deployment cause is ranked first for the initial fixture.
- Expand later to 30–50 reproducible scenarios and evaluate accuracy, investigation time, evidence quality, uncertainty handling, and unsafe recommendations.

## Quick start

Requires Python 3.10+.

### Windows PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app:app --reload
```

If PowerShell blocks activation, use `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` and `.\.venv\Scripts\python.exe -m uvicorn app:app --reload`.

Open http://127.0.0.1:8000/docs to try the API, or http://127.0.0.1:8000/incident to view the starter report.

### Run tests

```powershell
python -m pytest
```

## API

- `GET /health` — health check
- `GET /incident` — investigate the included simulated incident
- `POST /diagnose` — submit an incident payload

Example:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/incident
```

## Initial scenario

A simulated release is followed by increased HTTP 5xx errors and API latency. The fixture includes an expected cause for testing. In a real system, expected labels would be kept separate from the diagnosis input to avoid data leakage.

## Safety boundaries

- Read-only, synthetic data only in this version.
- No AWS credentials required.
- No production integrations or automatic remediation.
- Never commit secrets, real customer data, employer data, or unredacted logs.
- Treat generated diagnoses as hypotheses, not facts.

## Research integrity

The initial scenario is a software smoke test, not evidence of superiority over commercial products. Claims about accuracy, time savings, safety, novelty, or startup value must wait for a defined benchmark and reproducible results.

## Roadmap

1. One deployment-regression scenario and automated tests.
2. Separate rules-only and evidence-grounded approaches.
3. Add database saturation, resource pressure, dependency timeout, and traffic-spike scenarios.
4. Build a benchmark runner and report metrics.
5. Interview startup engineers before prioritizing integrations.
6. Add optional sandbox integrations only after reviewing permissions and data handling.
