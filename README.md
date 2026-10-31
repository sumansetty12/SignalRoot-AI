# SignalRoot AI v0.9.0 — combined automatic monitoring + pilot UX

Combines the proposed v0.8.0 and v0.9.0 work into **one local single-account pilot release**. It is **not a finished production SaaS**: no login, multi-tenant boundary, customer onboarding, hosted service, SLA, independent accuracy validation or production incident response support.

## Local installation (Windows PowerShell)

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest -v
uvicorn app:app --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/dashboard` and choose **Monitoring & History**. The existing Incident Explorer, AWS Explorer, benchmarks and AI endpoints remain available.

## Safe startup

By default, automatic polling, AWS access, automatic AI and notifications are **all OFF**. To connect your existing personal AWS test account using your existing AWS CLI profile, set environment variables in the same PowerShell terminal before launching the server:

```powershell
$env:AWS_PROFILE="signalroot-sandbox"  # replace with your configured AWS CLI profile
$env:SIGNALROOT_AWS_ENABLED="1"
$env:SIGNALROOT_AWS_REGION="us-east-2"
$env:SIGNALROOT_AUTO_MONITOR="1"
$env:SIGNALROOT_POLL_SECONDS="300"
uvicorn app:app --host 127.0.0.1 --port 8001
```

The background worker starts only when both AWS and automatic monitoring are enabled, and polls on the interval after startup. Keep **one Uvicorn worker**, no multi-worker deployment or `--reload` during monitoring, or you risk duplicate scans. Scans are read-only but may incur CloudWatch costs. The process must stay running for polling to continue. Click **Run AWS scan & save** for an immediate one-time test.

An embedded SQLite database is created at `data/incidents.sqlite3`; it stores sanitized observations and scan summaries. `data/` is git-ignored. This is local test data, **not hardened at-rest encryption or a secure multi-user data store**. Limit local file permissions and never persist sensitive telemetry. History deduplicates identical event/time/resource observations. You can acknowledge them in the dashboard. Acknowledgement does not change AWS state.

## Notifications (optional)

Set `SIGNALROOT_WEBHOOK_URL` to a trusted HTTPS webhook URL in your **local environment only**, not in Git. This sends only a minimal event category/notification message, not raw logs, but the URL itself may contain a secret. Notifications are best effort; repeated failures are not automatically retried. Automatic notifications are sent only for **newly observed** records from background polls.

## Optional automatic AI (PAID and opt-in)

Requires ALL of `SIGNALROOT_AWS_AI_ENABLED=1`, `SIGNALROOT_AUTO_AI_ENABLED=1`, a locally configured `OPENAI_API_KEY`, and a positive `SIGNALROOT_DAILY_AI_LIMIT` (maximum 20). The default daily AI limit is **0**. Only *new* sanitized AWS observations are analyzed. The system reserves daily quota before making a request, so errors count toward the limit. Do not enable this with customer or confidential data. It is an experimental AI comparison, **not autonomous remediation**. Explicit manual AI analysis remains available in AWS Explorer separately.

```powershell
$env:SIGNALROOT_AWS_AI_ENABLED="1"
$env:SIGNALROOT_AUTO_AI_ENABLED="1"
$env:SIGNALROOT_DAILY_AI_LIMIT="2"
# Supply OPENAI_API_KEY via your local secret handling, never commit it.
```

## Important boundaries

- Bind only to `127.0.0.1`; ops endpoints have an additional localhost client-address check, **not authentication**. Never expose them through a public proxy or internet-facing host.
- IAM access remains read-only; verify `aws_readonly_policy.json` and the profile/account before use. No automatic EC2/RDS modification is implemented.
- Scope is one trusted test AWS account, local application, single worker and local SQLite. Commercial cross-account onboarding, identity, isolation, tenancy, audit logs, rate limiting, observability, secrets management, backup, billing, hosted deployment, alert reliability and external evaluation remain future work.
- AWS records and time proximity do not prove cause and effect. Real AI tests and independent benchmark results are still pending.
- Remove AWS test resources when not in use to avoid costs.

## Test commands

```powershell
python -m pytest -v
python benchmark\run_benchmark.py
python benchmark\challenge_eval.py --engine baseline
```

## New research evaluation (v0.9.1 add-on)

See [`research/README.md`](research/README.md) for 100 synthetic cases, independent label caveats, baseline/AI commands, opt-in paid test, and evaluation caveats. This does not alter AWS monitoring or diagnosis production flows.
