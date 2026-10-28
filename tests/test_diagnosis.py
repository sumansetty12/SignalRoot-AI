from fastapi.testclient import TestClient

from app import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_demo_incident_ranks_deployment_regression_first():
    response = client.get("/incident")
    assert response.status_code == 200
    body = response.json()

    assert body["method"] == "deterministic_rules_baseline"
    assert body["hypotheses"][0]["cause"] == "Deployment regression"
    assert body["hypotheses"][0]["supporting_evidence"]
    assert "No action was executed" in body["safety_note"]


def test_diagnose_requires_signals():
    response = client.post(
        "/diagnose",
        json={"incident_id": "empty", "summary": "No evidence supplied", "signals": []},
    )
    assert response.status_code == 400


def test_custom_incident_with_release_and_errors():
    response = client.post(
        "/diagnose",
        json={
            "incident_id": "test-1",
            "summary": "Errors after a release",
            "signals": [
                {
                    "timestamp": "2026-01-01T10:00:00Z",
                    "source": "release_system",
                    "name": "deployment",
                    "value": "release v2",
                    "note": "rollout completed",
                },
                {
                    "timestamp": "2026-01-01T10:02:00Z",
                    "source": "metrics",
                    "name": "HTTP 5xx error rate",
                    "value": "10%",
                    "note": "server errors increased",
                },
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["hypotheses"][0]["cause"] == "Deployment regression"
