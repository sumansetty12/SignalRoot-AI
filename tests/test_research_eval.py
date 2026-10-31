import json, hashlib
from pathlib import Path
from research.run import run
HERE=Path(__file__).resolve().parents[1]/'research'

def test_case_count_and_labels():
    data=json.loads((HERE/'cases.json').read_text(encoding='utf-8'))
    assert len(data)==100
    assert len({x['id'] for x in data})==100
    assert sum(x['expected']=='Deployment regression' for x in data)==25
    assert sum(x['expected']=='Dependency or database degradation' for x in data)==50
    assert sum(x['expected']=='Insufficient evidence' for x in data)==25
    assert all(x['label_rationale'] and x['scenario_family'] for x in data)

def test_manifest_fingerprint():
    manifest=json.loads((HERE/'manifest.json').read_text(encoding='utf-8'))
    assert hashlib.sha256((HERE/'cases.json').read_bytes()).hexdigest()==manifest['sha256_cases_json']

def test_baseline_evaluation_nonpaid(tmp_path):
    result=run(HERE/'cases.json',results=tmp_path/'baseline.json')
    assert result['total_cases']==100
    assert 'confusion_matrix' in result
    assert result['mode']=='baseline'

def test_ai_requires_explicit_paid_consent(tmp_path):
    import pytest
    with pytest.raises(ValueError,match='confirm-paid'):
      run(HERE/'cases.json','ai',limit=4,confirm=False,results=tmp_path/'never.json')
