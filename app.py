from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

app = FastAPI(
    title="SignalRoot AI",
    description="SignalRoot AI prototype for evidence-grounded diagnosis of simulated incidents.",
    version="0.1.0",
)

SCENARIO_PATH = Path(__file__).parent / "scenarios" / "deployment_regression.json"


class Signal(BaseModel):
    timestamp: str
    source: str
    name: str
    value: str
    note: str = ""


class Incident(BaseModel):
    incident_id: str = "custom-incident"
    summary: str
    signals: list[Signal] = Field(default_factory=list)


def load_demo_incident() -> dict[str, Any]:
    with SCENARIO_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def diagnose(incident: Incident) -> dict[str, Any]:
    """Small deterministic baseline; deliberately not an LLM or production RCA engine."""
    signal_text = " ".join(
        f"{s.source} {s.name} {s.value} {s.note}".lower()
        for s in incident.signals
    )

    hypotheses: list[dict[str, Any]] = []

    deployment_terms = ("deployment", "release", "version", "rollout")
    error_terms = ("5xx", "error rate", "http errors", "server errors")
    latency_terms = ("latency", "p95", "response time")

    deployment_evidence = [
        s for s in incident.signals
        if any(term in f"{s.name} {s.note} {s.value}".lower() for term in deployment_terms)
    ]
    error_evidence = [
        s for s in incident.signals
        if any(term in f"{s.name} {s.note} {s.value}".lower() for term in error_terms)
    ]
    latency_evidence = [
        s for s in incident.signals
        if any(term in f"{s.name} {s.note} {s.value}".lower() for term in latency_terms)
    ]

    score = 0
    evidence: list[str] = []
    if deployment_evidence:
        score += 2
        evidence.extend(
            f"{s.timestamp}: {s.name} — {s.value}" for s in deployment_evidence
        )
    if error_evidence:
        score += 2
        evidence.extend(
            f"{s.timestamp}: {s.name} — {s.value}" for s in error_evidence
        )
    if latency_evidence:
        score += 1
        evidence.extend(
            f"{s.timestamp}: {s.name} — {s.value}" for s in latency_evidence
        )

    hypotheses.append({
        "cause": "Deployment regression",
        "score": score,
        "supporting_evidence": evidence,
        "explanation": (
            "A release event and post-release error/latency symptoms are present. "
            "This is a plausible hypothesis, not proof that the release caused the incident."
        ),
        "confidence": "medium" if score >= 4 else "low",
    })

    hypotheses.append({
        "cause": "Dependency or database degradation",
        "score": 1 if any(
            term in signal_text for term in ("database", "dependency", "timeout", "connection")
        ) else 0,
        "supporting_evidence": [
            f"{s.timestamp}: {s.name} — {s.value}"
            for s in incident.signals
            if any(term in f"{s.name} {s.note} {s.value}".lower()
                   for term in ("database", "dependency", "timeout", "connection"))
        ],
        "explanation": "Check dependency health if supporting telemetry is available.",
        "confidence": "low",
    })

    hypotheses.sort(key=lambda item: item["score"], reverse=True)
    return {
        "incident_id": incident.incident_id,
        "summary": incident.summary,
        "method": "deterministic_rules_baseline",
        "hypotheses": hypotheses,
        "recommended_checks": [
            "Compare error rate and latency before and after the release timestamp.",
            "Inspect the release diff and application errors for the affected service.",
            "Check dependency health before concluding that the deployment is the cause.",
            "If the evidence is inconclusive, gather more telemetry rather than guessing.",
        ],
        "safety_note": (
            "No action was executed. Treat these results as hypotheses; use a human "
            "reviewer and a tested rollback procedure before making production changes."
        ),
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/incident")
def demo_incident() -> dict[str, Any]:
    payload = load_demo_incident()
    incident = Incident(
        incident_id=payload["incident_id"],
        summary=payload["summary"],
        signals=[Signal(**signal) for signal in payload["signals"]],
    )
    return diagnose(incident)


@app.post("/diagnose")
def diagnose_custom(incident: Incident) -> dict[str, Any]:
    if not incident.signals:
        raise HTTPException(status_code=400, detail="Provide at least one evidence signal.")
    return diagnose(incident)


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return """
    <!doctype html>
    <html lang="en">
      <head><meta charset="utf-8"><title>Startup SRE Copilot</title></head>
      <body style="font-family: system-ui; max-width: 820px; margin: 3rem auto; padding: 0 1rem;">
        <h1>Startup SRE Copilot</h1>
        <p>Prototype: evidence-grounded diagnosis for simulated incidents.</p>
        <ul>
          <li><a href="/incident">Run the deployment-regression example</a></li>
          <li><a href="/docs">Explore the API</a></li>
          <li><a href="/health">Check service health</a></li>
        </ul>
        <p><strong>Safety:</strong> synthetic data only; no production actions are performed.</p>
      </body>
    </html>
    """
