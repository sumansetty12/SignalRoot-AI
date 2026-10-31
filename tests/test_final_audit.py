import json
from pathlib import Path
import pytest
from app import Incident,Signal,diagnose
from ai_engine import build_messages,build_evidence,_validate
from research.calibrate import run,evaluate_case
from research.audit import audit
ROOT=Path(__file__).resolve().parents[1]

def test_hypothesis_prompt_never_includes_baseline(monkeypatch):
    monkeypatch.setenv('SIGNALROOT_PROMPT_VARIANT','hypothesis')
    inc=Incident(signals=[Signal(name='Aurora database',value='unavailable')])
    msg=build_messages(inc,build_evidence(inc),diagnose(inc))
    assert 'baseline_for_comparison_only' not in msg[1]['content']
    assert 'SUPPORTED FAILURE CATEGORY' in msg[0]['content']

def test_conservative_prompt_retains_legacy(monkeypatch):
    monkeypatch.setenv('SIGNALROOT_PROMPT_VARIANT','conservative')
    inc=Incident(signals=[Signal(name='generic alert',value='triggered')])
    msg=build_messages(inc,build_evidence(inc),diagnose(inc))
    assert 'baseline_for_comparison_only' in msg[1]['content']

def test_invalid_prompt_variant_raises(monkeypatch):
    monkeypatch.setenv('SIGNALROOT_PROMPT_VARIANT','other')
    inc=Incident(signals=[Signal(name='Aurora database',value='unavailable')])
    with pytest.raises(ValueError,match='PROMPT_VARIANT'):
        build_messages(inc,build_evidence(inc),diagnose(inc))

def test_development_baseline_is_free(tmp_path):
    result=run(engine='baseline',output=tmp_path/'a.json')
    assert result['cases_evaluated']==18
    assert result['provider_calls_attempted']==0

def test_paid_ai_without_consent_fails(tmp_path):
    with pytest.raises(ValueError,match='confirm-paid'):
        run(engine='ai',max_calls=1,output=tmp_path/'never.json')

def test_valid_model_diagnosis_with_injected_mock():
    case={'id':'x','summary':'DB down','signals':[{'timestamp':'10','source':'rds','name':'Aurora database','value':'unavailable'}],'expected':'Dependency or database degradation'}
    model=lambda _: json.dumps({'diagnosis':'Dependency or database degradation','supporting_evidence_ids':['S1'],'counterevidence_ids':[], 'explanation':'Aurora unavailable supports a database degradation hypothesis, not proven underlying cause.', 'recommendations':['Inspect RDS event message.']})
    r=evaluate_case(case,model,'hypothesis')
    assert r['decision']=='validated_model_output'
    assert r['validated_diagnosis']==case['expected']

def test_validator_rejection_is_not_model_abstention():
    case={'id':'x','summary':'DB down','signals':[{'timestamp':'10','source':'rds','name':'Aurora database','value':'unavailable'}],'expected':'Dependency or database degradation'}
    bad=lambda _: json.dumps({'diagnosis':'Dependency or database degradation','supporting_evidence_ids':['S99'],'counterevidence_ids':[], 'explanation':'DB down','recommendations':[]})
    r=evaluate_case(case,bad,'hypothesis')
    assert r['raw_model_diagnosis']=='Dependency or database degradation'
    assert r['decision']=='validator_rejected_abstain'
    assert r['validated_diagnosis']=='Insufficient evidence'

def test_audit_existing_report(tmp_path):
    p=tmp_path/'report.json'
    p.write_text(json.dumps({'rows':[{'id':'one','expected':'Deployment regression','predicted':'Insufficient evidence','status':'ok','explanation':'No evidence'}, {'id':'two','expected':'Insufficient evidence','predicted':'Insufficient evidence','status':'ok'}]}))
    result=audit(p)
    assert result['incorrect_abstentions']==1
    assert result['total']==2
