from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def test_dashboard_returns_interactive_html():
    response = client.get('/dashboard')
    assert response.status_code == 200
    assert 'Incident Explorer' in response.text
    assert 'Incident Playground' in response.text
    assert '/api/dashboard/cases' in response.text

def test_cases_endpoint_contains_30_synthetic_cases():
    response = client.get('/api/dashboard/cases')
    assert response.status_code == 200
    data = response.json()
    assert len(data['cases']) == 30
    assert all('prediction' in c and 'signals' in c for c in data['cases'])
    assert data['engine'] == 'rules_baseline'

def test_dashboard_summary_matches_evaluator():
    response = client.get('/api/dashboard/metrics')
    assert response.status_code == 200
    data = response.json()
    assert data['metrics']['total'] == 30
    assert data['metrics']['coverage'] == 0.6
    assert data['metrics']['accuracy'] == 1.0
    assert data['metrics']['abstention_rate'] == 0.4

def test_dashboard_preserves_existing_diagnose_endpoint():
    incident = client.get('/incident').json()
    result = client.post('/diagnose',json=incident)
    assert result.status_code == 200
    assert result.json()['diagnosis'] == 'Deployment regression'
