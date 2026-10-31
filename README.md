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

## v0.9.2 — Final development audit and calibration

**This release closes the local pilot feature-development phase; it is not independent publication validation or a production-grade multi-tenant SaaS.** All v0.9.1 code, AWS monitoring, dashboard and 100-case frozen data are preserved.

### Why AI accuracy was 30% in the original 100 cases

The original report mixed valid model abstentions with validator fallback abstentions. We cannot recover every original model decision from its saved final responses. This release adds a separate trace for *new synthetic development examples*. **Do not claim the revised prompt improved performance without live testing and independent holdout cases.**

Copy `research/report_ai.json` from the previous v0.9.1 project folder if available. Then:

```powershell
python research\audit.py --report research\report_ai.json
python research\calibrate.py --engine baseline
```

Run a small **paid AI development experiment** on 6 examples (not a holdout):

```powershell
$secret = Read-Host "OpenAI API key" -AsSecureString
$env:OPENAI_API_KEY = [System.Net.NetworkCredential]::new("", $secret).Password
Remove-Variable secret
$env:SIGNALROOT_MODEL="gpt-4o-mini"
python research\calibrate.py --engine ai --variant hypothesis --max-calls 6 --confirm-paid
```

The new `research/calibration_ai_hypothesis.json` records model raw label, validator disposition and final label for synthetic-only cases. It does not send any real AWS customer logs or secrets, and it cannot diagnose live infrastructure from this report. The request cap counts actual model invocations. Runs may be billable; the project does not impose a dollar spending cap. Review OpenAI billing controls separately.

For comparison, use `--variant conservative` as another explicitly authorized run; these are **new paid calls**, not the original old results. Prompt variants affect the AI evaluation only; the heuristic baseline remains unchanged. The hypothesis prompt asks for evidence-supported failure categories without claiming ultimate root-cause proof, and deliberately removes the baseline guess from the model input. This reduces one source of answer leakage but does not by itself prove any improvement.

The 100 original cases have already been used for development analysis. They are not an independent holdout. Do not publish new scores on them as an unbiased test. Independent labeled incident reports, reviewer agreement, repeated trials, semantic citation audits and cost accounting remain research work.

The audit and calibration artifacts include model output derived from **synthetic** data and are excluded from Git. Never use these raw-output diagnostics with sensitive customer telemetry. Do not commit API keys or `.env` files.
