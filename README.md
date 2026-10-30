# SignalRoot AI v0.7.0 — AWS investigation + optional live AI

This release combines the **read-only AWS investigation** features and a separately enabled **live LLM comparison**. It is an experimental SRE research tool, **not** a production monitoring service or verified root-cause engine.

## Start locally on Windows

Unzip into its own folder. Open `SignalRoot-AI` in VS Code PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -v
python benchmark\challenge_eval.py --engine baseline
uvicorn app:app --reload --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/dashboard` and use **AWS Explorer → Load demo events**. No AWS credentials or API key required.

## Connect your own AWS account (manual read-only scan)

Use a *personal sandbox account* with SSO/temporary credentials and update your existing restricted IAM role using `aws_readonly_policy.json`. Account and permissions should be verified separately. The allowed actions are:

- `cloudwatch:DescribeAlarms`, `cloudwatch:GetMetricStatistics`
- `rds:DescribeEvents`
- `ec2:DescribeInstances`, `ec2:DescribeInstanceStatus`
- Optional `logs:FilterLogEvents`, scoped to `/signalroot-lab/*` log group ARNs

PowerShell, in the **same terminal** where you start uvicorn:

```powershell
$env:AWS_PROFILE="signalroot-sandbox"  # change to your existing profile
$env:SIGNALROOT_AWS_ENABLED="1"
$env:SIGNALROOT_AWS_REGION="us-east-2"
# Optional, only if YOUR log group exists, and you trust its contents:
# $env:SIGNALROOT_LOG_GROUPS="/signalroot-lab/app"
uvicorn app:app --reload --host 127.0.0.1 --port 8001
```

Click **Scan AWS (read-only)**. It searches the last 180 minutes of RDS events, active metric alarms and selected lab EC2 instances, and reads a limited number of metric samples. RDS free-text event messages are parsed locally into **category flags only** (e.g. restart/failover); the raw messages are not sent to the browser. For configured log groups, at most 50 log events/group from the last 45 minutes are examined locally for error/timeout patterns; **only counts** appear in the UI. This is keyword pattern analysis, not log-based causality detection. The app does not retrieve CloudWatch alarm reasons/descriptions. If a read fails, the dashboard should show a warning and retain the base scan.

> Keep the app bound to `127.0.0.1`. There is no user authentication; **never expose it on a public IP**. Only use your own sandbox telemetry. Do not use employer/customer information or unknown sensitive log streams. Read-only does not mean zero cost: CloudWatch logs and AI calls can incur charges.

## Optional LIVE AI comparison — separate explicit opt-in

The old `/diagnose/ai` route remains. New AWS Explorer includes **Analyze first AWS window with AI**. The browser asks permission each time. Server-side enablement is **off** unless explicitly set.

In your PowerShell terminal **before launching uvicorn**:

```powershell
$env:SIGNALROOT_AWS_AI_ENABLED="1"
$env:OPENAI_API_KEY="YOUR_KEY_IN_YOUR_LOCAL_TERMINAL_ONLY"
$env:SIGNALROOT_MODEL="gpt-4o-mini"   # optional; use a model your account can access
uvicorn app:app --reload --host 127.0.0.1 --port 8001
```

Click **AWS Explorer → Scan AWS → Analyze first AWS window with AI**. This performs a **paid external AI request**, not a local inference; your sanitized event signals and timestamps are sent to the provider. Never paste/share your API key, and never commit it to Git. Set `$env:SIGNALROOT_AWS_AI_ENABLED="0"` and remove the environment key afterward to disable.

The AI selects one of the existing three labels and is required to cite evidence IDs from the supplied input. Invalid outputs are rejected or converted to abstention. Evidence-ID validation prevents invented references, **not invented reasoning or factual inaccuracies**. The tool makes no AWS writes or remediation calls. Model performance on **real** AWS incidents has not been measured, and no guarantee of improved accuracy is made.

## What is tested / not tested

- Python unit/API tests use **mock AWS and AI responses**, verifying safety gates, sanitization, basic functionality and backward compatibility.
- The old 18-case and 30-case synthetic baseline benchmarks remain developer-authored and are **not independent evaluations**.
- Run baseline evaluation without API charges: `python benchmark\evaluate.py --engine baseline`
- Optional live AI evaluation on the **6-case developer set** (paid): `python benchmark\evaluate.py --engine ai`
- For a stronger comparison, label a separate test set **before** evaluation, do not tune to that set, review model explanations, and report errors and costs.
- A future production release still requires automatic monitoring, authenticated access, durable storage, tenant isolation, secrets management, and audited threat modelling.

## Cleanup

This app only reads AWS: it doesn't create or delete infrastructure. The **separate live AWS lab** is still chargeable. Delete its EC2/RDS/CloudWatch resources using the lab's own cleanup script after testing.
