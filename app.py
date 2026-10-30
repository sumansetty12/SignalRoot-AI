"""SignalRoot AI: transparent, read-only incident diagnosis baseline.

This is a research prototype, not an AI model or a production remediation tool.
"""
from __future__ import annotations

import re
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

app = FastAPI(title="SignalRoot AI", version="0.6.1",
              description="Evidence-grounded synthetic incident diagnosis baseline")

class Signal(BaseModel):
    timestamp: str = "unknown"
    source: str = "unknown"
    name: str
    value: Any = None
    note: str = ""

class Incident(BaseModel):
    incident_id: str = "manual-incident"
    summary: str = "Incident under investigation"
    signals: list[Signal] = Field(default_factory=list)

# Deliberately small and explainable heuristic baseline. No learned weights.
DEPLOY_WORDS = ("deployment", "deploy", "release", "rollout", "new version", "new build")
DATABASE_WORDS = ("database", "postgres", "aurora", "sql", "db connection", "query pool")
DEPENDENCY_WORDS = ("dependency", "upstream", "third-party", "external service", "payment service", "identity service")
ERROR_WORDS = ("5xx", "500 error", "error rate", "failed request", "server error", "http error")
LATENCY_WORDS = ("latency", "p95", "response time", "timeout")
NEGATIVE_WORDS = ("unhealthy", "unavailable", "disconnected", "failed", "failure", "timeout", "timed out", "degraded", "saturated", "exhausted", "elevated", "increased", "spiked", "slow", "high error")
POSITIVE_WORDS = ("healthy", "normal", "operational", "connected", "successful", "no errors", "within threshold")


def contains(text: str, words: tuple[str, ...]) -> bool:
    return any(w in text for w in words)


def state(text: str) -> str:
    """Coarse signal health. Generic numbers are not interpreted as failures."""
    if contains(text, NEGATIVE_WORDS):
        return "unhealthy"
    if contains(text, POSITIVE_WORDS):
        return "healthy"
    return "unknown"


def evidence(signal: Signal) -> str:
    return f"{signal.timestamp} | {signal.source} | {signal.name}: {signal.value} {signal.note}".strip()


def unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(items))


def diagnose(incident: Incident) -> dict:
    scores = {"Deployment regression": 0, "Dependency or database degradation": 0}
    support: dict[str, list[str]] = {k: [] for k in scores}
    counter: dict[str, list[str]] = {k: [] for k in scores}
    deployment_seen = False
    app_symptom_seen = False
    for sig in incident.signals:
        text = f"{sig.source} {sig.name} {sig.value} {sig.note}".lower()
        health = state(text)
        item = evidence(sig)
        is_deployment = contains(text, DEPLOY_WORDS)
        is_database = contains(text, DATABASE_WORDS)
        is_dependency = contains(text, DEPENDENCY_WORDS)
        is_app_symptom = contains(text, ERROR_WORDS + LATENCY_WORDS) and health == "unhealthy"

        if is_deployment:
            deployment_seen = True
            support["Deployment regression"].append(item)
        if is_app_symptom and not (is_database or is_dependency):
            app_symptom_seen = True
            # Application symptoms alone do NOT establish a deployment cause.
            support["Deployment regression"].append(item)
        if is_database or is_dependency:
            if health == "unhealthy":
                scores["Dependency or database degradation"] += 3
                support["Dependency or database degradation"].append(item)
            elif health == "healthy":
                counter["Dependency or database degradation"].append(item)

    # A release plus an independently observed application symptom is a
    # plausible deployment hypothesis, not proof of causation.
    if deployment_seen and app_symptom_seen:
        scores["Deployment regression"] = 4
    elif deployment_seen:
        scores["Deployment regression"] = 1

    ordered = sorted(scores, key=lambda key: scores[key], reverse=True)
    top, runner_up = ordered
    top_score = scores[top]
    margin = top_score - scores[runner_up]
    # Abstain on weak, indistinguishable, or conflicting evidence.
    if top_score < 3 or margin < 2:
        diagnosis = "Insufficient evidence"
        status = "insufficient_evidence"
        confidence = "low"
    else:
        diagnosis = top
        status = "hypothesis_available"
        confidence = "medium"  # not a calibrated probability

    hypotheses = [
        {"name": name, "score": scores[name],
         "supporting_evidence": unique(support[name]),
         "counterevidence": unique(counter[name])}
        for name in ordered
    ]
    if diagnosis == "Deployment regression":
        steps = ["Compare metrics before and after the release.",
                 "Inspect release changes and error logs; do not automatically roll back."]
    elif diagnosis == "Dependency or database degradation":
        steps = ["Check database and upstream dependency telemetry around incident start.",
                 "Verify failure scope; do not automatically restart services."]
    else:
        steps = ["Collect timestamped errors, deployment events, dependency health, and database metrics.",
                 "Do not select a root cause until competing hypotheses can be distinguished."]
    return {
        "incident_id": incident.incident_id,
        "summary": incident.summary,
        "status": status,
        "diagnosis": diagnosis,
        "confidence": confidence,
        "score_type": "heuristic_points_not_probability",
        "hypotheses": hypotheses,
        "supporting_evidence": unique(support.get(diagnosis, [])),
        "counterevidence": unique(counter.get(diagnosis, [])),
        "recommendations": steps,
        "safety_note": "Read-only prototype; no remediation actions are executed.",
    }

DEMO = Incident(incident_id="deployment-demo", summary="API failures after release", signals=[
    Signal(timestamp="10:00", source="deployments", name="Release rollout", value="v2 deployed"),
    Signal(timestamp="10:04", source="metrics", name="HTTP 5xx error rate", value="elevated"),
])

@app.get("/health")
def health():
    return {"status": "ok", "version": app.version}

@app.get("/incident")
def incident():
    return DEMO.model_dump()

@app.post("/diagnose")
def diagnose_endpoint(incident: Incident):
    return diagnose(incident)

@app.get("/", response_class=HTMLResponse)
def index():
    return """<!doctype html><html><head><title>SignalRoot AI</title></head>
    <body style='font:16px Arial;max-width:760px;margin:60px auto;line-height:1.6'>
    <h1>SignalRoot AI</h1><p>Evidence-grounded incident diagnosis research baseline.</p>
    <p><a href='/docs'>Interactive API docs</a> | <a href='/health'>Health</a> |
    <a href='/incident'>Example incident</a></p>
    <p>This is a read-only heuristic research prototype using synthetic incident data.</p>
    </body></html>"""


@app.post("/diagnose/ai")
def diagnose_ai_endpoint(incident: Incident):
    """Optional live LLM call. Sends user-supplied synthetic telemetry to provider."""
    from fastapi import HTTPException
    from ai_engine import ProviderError, analyze_ai
    try:
        return analyze_ai(incident)
    except ProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc


# Offline, read-only visualization endpoints. No external APIs or keys needed.
from pathlib import Path as _Path
from fastapi.responses import FileResponse
import json as _json

_UI_ROOT = _Path(__file__).resolve().parent

@app.get('/dashboard', include_in_schema=False)
def dashboard():
    return FileResponse(_UI_ROOT / 'dashboard' / 'index.html', media_type='text/html')

@app.get('/api/dashboard/cases')
def dashboard_cases():
    """Expose synthetic challenge cases and baseline diagnoses, without model calls."""
    from benchmark.challenge_eval import validate_dataset, DATASET, MANIFEST
    cases, digest = validate_dataset(DATASET, MANIFEST)
    output = []
    for c in cases:
        pred = diagnose(Incident(incident_id=c['id'], summary=c['summary'], signals=c['signals']))
        output.append({
            'id': c['id'], 'summary': c['summary'], 'signals': c['signals'],
            'expected': c['expected'], 'label_rationale': c.get('label_rationale', ''),
            'prediction': pred, 'correct': pred['diagnosis'] == c['expected']
        })
    return {'source': 'Developer-authored synthetic challenge set (not independently validated)',
            'engine': 'rules_baseline', 'dataset_sha256': digest, 'cases': output}

@app.get('/api/dashboard/metrics')
def dashboard_metrics():
    from benchmark.challenge_eval import validate_dataset, DATASET, MANIFEST, evaluate
    cases, digest = validate_dataset(DATASET, MANIFEST)
    results = evaluate(cases, engine='baseline')
    return {'source': 'Synthetic developer-authored challenge benchmark',
            'dataset_sha256': digest, 'engine': 'rules_baseline', 'metrics': results['metrics'],
            'rows': results['rows'], 'warning': results['warning']}


# v0.6.0: explicit, user-triggered, read-only AWS snapshot.
from aws_integration import AWSIntegrationError, collect_aws_snapshot, demo_aws_snapshot
from fastapi import HTTPException as _HTTPException

@app.get('/api/aws/status')
def aws_status():
    import os
    return {'enabled': os.environ.get('SIGNALROOT_AWS_ENABLED') == '1',
            'mode': 'live_enabled' if os.environ.get('SIGNALROOT_AWS_ENABLED') == '1' else 'demo_only',
            'manual_refresh_only': True, 'read_only': True}

@app.get('/api/aws/demo')
def aws_demo():
    return demo_aws_snapshot(diagnose)

@app.post('/api/aws/scan')
def aws_scan():
    import os
    if os.environ.get('SIGNALROOT_AWS_ENABLED') != '1':
        raise _HTTPException(403, detail='AWS access is disabled. Set SIGNALROOT_AWS_ENABLED=1 explicitly to enable.')
    try:
        return collect_aws_snapshot(diagnose)
    except AWSIntegrationError as exc:
        raise _HTTPException(503, detail=str(exc)) from exc
