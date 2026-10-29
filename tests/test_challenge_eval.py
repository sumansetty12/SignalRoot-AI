import json
import pytest
from benchmark.challenge_eval import (DATASET, MANIFEST, validate_dataset, evaluate, metrics)


def test_manifest_and_scenarios_are_valid():
    cases, digest = validate_dataset(DATASET, MANIFEST)
    assert len(cases) == 30
    assert len(digest) == 64
    assert len(set(x['id'] for x in cases)) == len(cases)


def test_baseline_full_challenge_evaluates_without_network():
    cases, _ = validate_dataset(DATASET, MANIFEST)
    result = evaluate(cases, engine='baseline')
    assert result['metrics']['total'] == 30
    assert result['metrics']['provider_errors'] == 0
    assert result['metrics']['accuracy'] is not None


def test_metrics_separate_provider_failure_from_abstention():
    rows = [
        dict(id='1',expected='Deployment regression',predicted=None,status='provider_error',correct=False,abstained=False),
        dict(id='2',expected='Insufficient evidence',predicted='Insufficient evidence',status='ok',correct=True,abstained=True),
        dict(id='3',expected='Deployment regression',predicted='Dependency or database degradation',status='ok',correct=False,abstained=False),
    ]
    m = metrics(rows)
    assert m['provider_errors'] == 1
    assert m['evaluated'] == 2
    assert m['abstention_rate'] == 0.5
    assert m['wrong_non_abstaining_diagnoses'] == 1
    assert m['overall_accuracy_treating_errors_as_wrong'] == 0.3333


def test_ai_call_cap_is_enforced_before_provider_invocation():
    cases, _ = validate_dataset(DATASET, MANIFEST)
    with pytest.raises(ValueError, match='call cap'):
        evaluate(cases, engine='ai', provider=lambda _: 'bad', max_ai_calls=1)


def test_mock_ai_outputs_can_be_evaluated_without_api_key():
    cases, _ = validate_dataset(DATASET, MANIFEST)
    subset = [x for x in cases if x['signals']][:2]
    def fake(messages):
        evidence = json.loads(messages[1]['content'])['signals']
        return json.dumps({'diagnosis':'Insufficient evidence', 'supporting_evidence_ids':[],
                           'counterevidence_ids':[], 'explanation':'Not enough proof',
                           'recommendations':['Inspect logs']})
    result = evaluate(subset, engine='ai', provider=fake, max_ai_calls=2)
    assert result['metrics']['total'] == 2
    assert result['metrics']['provider_errors'] == 0
    assert result['metrics']['abstention_rate'] == 1.0


def test_invalid_model_output_is_counted_as_validation_abstention():
    cases, _ = validate_dataset(DATASET, MANIFEST)
    case = next(x for x in cases if x['signals'])
    result = evaluate([case], engine='ai', provider=lambda _: 'not json', max_ai_calls=1)
    assert result['rows'][0]['validation_abstained'] is True
    assert result['rows'][0]['abstained'] is True


def test_manifest_detects_modified_dataset(tmp_path):
    cases, _ = validate_dataset(DATASET, MANIFEST)
    changed = tmp_path/'changed.json'
    changed.write_text(json.dumps(cases))
    with pytest.raises(ValueError, match='manifest'):
        validate_dataset(changed, MANIFEST)


def test_per_label_and_coverage_consistency():
    cases, _ = validate_dataset(DATASET, MANIFEST)
    m = evaluate(cases)['metrics']
    assert sum(v['n'] for v in m['per_label'].values()) == m['evaluated']
    assert sum(sum(x.values()) for x in m['confusion_matrix'].values()) == m['evaluated']
