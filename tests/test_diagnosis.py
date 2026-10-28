import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from app import app, diagnose, Incident, Signal

client = TestClient(app)


def case(*signals):
    return Incident(signals=[Signal(**s) for s in signals])


def sig(name, value, source="metrics", timestamp="10:00"):
    return {"name": name, "value": value, "source": source, "timestamp": timestamp}


def test_health():
    result = client.get('/health')
    assert result.status_code == 200
    assert result.json()['status'] == 'ok'


def test_example_deployment():
    demo = client.get('/incident').json()
    result = client.post('/diagnose', json=demo)
    assert result.status_code == 200
    assert result.json()['diagnosis'] == 'Deployment regression'


def test_empty_signals_abstain():
    result = client.post('/diagnose', json={'signals': []}).json()
    assert result['diagnosis'] == 'Insufficient evidence'
    assert result['status'] == 'insufficient_evidence'


def test_database_timeout():
    result = diagnose(case(sig('Database connection', 'failed timeout', 'database')))
    assert result['diagnosis'] == 'Dependency or database degradation'


def test_upstream_unavailable():
    result = diagnose(case(sig('Payment service dependency', 'unavailable', 'dependencies')))
    assert result['diagnosis'] == 'Dependency or database degradation'


def test_generic_error_without_release_abstains():
    result = diagnose(case(sig('HTTP 5xx error rate', 'elevated')))
    assert result['diagnosis'] == 'Insufficient evidence'


def test_generic_alert_abstains():
    result = diagnose(case(sig('Alert', 'fired')))
    assert result['diagnosis'] == 'Insufficient evidence'


def test_healthy_database_not_failure():
    result = diagnose(case(sig('Database health', 'healthy and connected', 'database')))
    assert result['diagnosis'] == 'Insufficient evidence'
    infrastructure = next(h for h in result['hypotheses'] if h['name'].startswith('Dependency'))
    assert infrastructure['counterevidence']
    assert infrastructure['score'] == 0


def test_healthy_database_and_generic_errors_abstains():
    result = diagnose(case(sig('Database health', 'healthy', 'database'),
                           sig('HTTP 5xx error rate', 'elevated')))
    assert result['diagnosis'] == 'Insufficient evidence'


def test_mixed_competing_causes_abstains():
    result = diagnose(case(sig('Release rollout', 'v2 deployed', 'deployments'),
                           sig('HTTP 5xx error rate', 'elevated'),
                           sig('Database connection', 'failed timeout', 'database')))
    assert result['diagnosis'] == 'Insufficient evidence'


def test_duplicate_evidence_removed():
    result = diagnose(case(sig('Release rollout', 'v2 deployed', 'deployments'),
                           sig('Release rollout', 'v2 deployed', 'deployments'),
                           sig('HTTP 5xx error rate', 'elevated')))
    assert len(result['supporting_evidence']) == len(set(result['supporting_evidence']))


def test_score_not_claimed_probability():
    result = diagnose(case(sig('Release rollout', 'v2 deployed', 'deployments'),
                           sig('HTTP 5xx error rate', 'elevated')))
    assert result['score_type'] == 'heuristic_points_not_probability'
    assert 'no remediation actions' in result['safety_note'].lower()


def test_benchmark_file_has_valid_ground_truth():
    path = Path(__file__).resolve().parents[1] / 'benchmark' / 'scenarios.json'
    cases = json.loads(path.read_text())
    assert len(cases) >= 12
    assert len({case['id'] for case in cases}) == len(cases)
    assert {case['expected'] for case in cases} == {
        'Deployment regression', 'Dependency or database degradation', 'Insufficient evidence'}
