# SignalRoot AI v0.6.0 — AWS Read-Only Incident Explorer

SignalRoot AI is a research prototype for evidence-grounded incident investigation. v0.6.0 adds **manual, read-only AWS snapshot retrieval** for CloudWatch ALARM states and recent RDS instance events, alongside the existing incident dashboard and synthetic evaluations.

**This is not always-on monitoring or validated root-cause analysis.** AWS events may be incomplete, benign, or historical. The app does not run autonomous remediation, access CloudWatch Logs, or pull time-series metrics. A local browser app should **never** be exposed publicly without authentication and network protections.

## Quick start — demo, no AWS account required

Windows PowerShell from the `SignalRoot-AI` folder:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -v
uvicorn app:app --reload --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/dashboard`, select **AWS Explorer** and click **Load demo events**. This returns clearly marked synthetic AWS alarm and RDS event data without AWS access. Existing Incident Explorer, Evaluation, Playground and API `/docs` remain available.

## Optional: scan your own AWS sandbox account (read-only)

1. In your own AWS sandbox account, prepare a narrowly scoped IAM **role** with the supplied [`aws_readonly_policy.json`](aws_readonly_policy.json). That policy allows `cloudwatch:DescribeAlarms` and `rds:DescribeEvents` only. You should review its trust policy and limit who can assume it. AWS often requires Resource `*` for these Describe operations.
2. Configure AWS CLI authentication locally with an SSO profile or temporary credentials. **Never** enter access keys in this app or commit `.env` files. Test with `aws sts get-caller-identity --profile signalroot-sandbox`. An existing temporary/session credential setup is preferable to permanent access keys.
3. In a PowerShell session, set:

```powershell
$env:SIGNALROOT_AWS_ENABLED="1"
$env:SIGNALROOT_AWS_REGION="us-east-1"  # your sandbox region
$env:AWS_PROFILE="signalroot-sandbox"   # your configured profile
# If cross-account AssumeRole is needed, supply a trusted role ARN and unique ExternalId:
# $env:SIGNALROOT_AWS_ROLE_ARN="arn:aws:iam::123456789012:role/SignalRootReadOnly"
# $env:SIGNALROOT_AWS_EXTERNAL_ID="unique-generated-external-id"
uvicorn app:app --reload --host 127.0.0.1 --port 8001
```

4. In **AWS Explorer**, click **Scan AWS (read-only)**. The scan returns a **point-in-time snapshot**, not real-time continuous detection. It reads at most **30 ALARM-state CloudWatch alarms** and **40 RDS DB-instance events from the last 60 minutes** for a **single region**. Alarms that are OK/INSUFFICIENT_DATA are excluded. RDS cluster event sources are not covered. If no alarms or events exist, the dashboard correctly shows an empty snapshot.
5. To disable AWS access, stop the server and set `$env:SIGNALROOT_AWS_ENABLED="0"` before restarting. No AWS credentials or raw event descriptions are returned to the browser or saved by this app.

**Important limits:** AWS may bill for some monitoring usage and API requests; review your account and current AWS pricing. The app does not create AWS infrastructure. Scan does not fetch log bodies or metric time series; a single alarm is not proof of outage or root cause. No background poller or automatic incident notification is enabled. Profile-based auth works from your local computer only. For a future hosted, multi-tenant service we will need proper tenant authorization, secure role onboarding, encryption, audit logs, retention policies and rate limiting.

## Code and API

- `GET /api/aws/status`: whether live scan is enabled (without accessing AWS)
- `GET /api/aws/demo`: synthetic AWS snapshot, no credentials
- `POST /api/aws/scan`: manual read-only snapshot (disabled by default)
- `GET /dashboard`: dashboard including AWS Explorer
- Existing `/diagnose`, `/diagnose/ai`, synthetic benchmarks, tests preserved.

The current heuristic classifies hypotheses, not confirmed root causes; misleading evidence is possible. No data is sent to an LLM by the AWS scan. See `PROJECT.md` for limitations.
