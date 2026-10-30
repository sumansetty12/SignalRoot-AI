from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app import app
import advanced_investigation as ai
import aws_integration as aws
from app import diagnose


def test_rds_message_classification_never_returns_raw_message():
    secret='secret-token-123'
    e={'Message':f'DB instance reboot completed; {secret}', 'Date':datetime.now(timezone.utc)}
    result=ai.sanitize_rds_event(e)
    assert 'restart' in result['categories_detected']
    assert secret not in str(result)
    assert secret not in str(ai.sanitized_rds_signal(e))


def test_log_summary_only_safe_pattern_counts():
    out=ai.summarize_log_events([{'message':'customer token supersecret: database connection refused'},
                                 {'message':'HTTP 500 and timeout'}])
    assert out['pattern_counts']['connection_error']==1
    assert out['pattern_counts']['timeout']==1
    assert 'supersecret' not in str(out)


def test_log_read_disabled_no_client(monkeypatch):
    monkeypatch.delenv('SIGNALROOT_LOG_GROUPS',raising=False)
    class Nope:
        def client(self,*args,**kwargs):raise AssertionError('should not call AWS')
    assert ai.read_logs(Nope(),None)['enabled'] is False


def test_log_read_rejects_arbitrary_groups(monkeypatch):
    monkeypatch.setenv('SIGNALROOT_LOG_GROUPS','/production/customer-api')
    try:
        ai.read_logs(None,None)
    except ValueError as e:
        assert 'signalroot-lab' in str(e)
    else:raise AssertionError('must reject arbitrary groups')


def test_log_read_bounded_and_does_not_reveal_content(monkeypatch):
    monkeypatch.setenv('SIGNALROOT_LOG_GROUPS','/signalroot-lab/app')
    class Logs:
        def filter_log_events(self,**kwargs):
            assert kwargs['limit']==50
            assert kwargs['logGroupName']=='/signalroot-lab/app'
            return {'events':[{'message':'password=very-sensitive HTTP 500'}]}
    class Sess:
        def client(self,name,config=None):assert name=='logs';return Logs()
    output=ai.read_logs(Sess(),None)
    assert output['summaries'][0]['pattern_counts']['server_error']==1
    assert 'very-sensitive' not in str(output)


def test_investigation_does_not_claim_cause():
    incidents=[{'id':'a','kind':'RDS event','rds_indicators':{'categories_detected':['restart']}},
               {'id':'b','kind':'CloudWatch alarm'}]
    window={'id':'w','events':[{'id':'a'},{'id':'b'}]}
    result=ai.analyze_window(window,incidents)
    assert not result['root_cause_confirmed']
    assert 'temporally' in str(result).lower()


def test_ai_optin_off_by_default(monkeypatch):
    monkeypatch.delenv('SIGNALROOT_AWS_AI_ENABLED',raising=False)
    client=TestClient(app)
    r=client.post('/api/aws/analyze-window-ai',json={'signals':[]})
    assert r.status_code==403


def test_ai_optin_provider_mock(monkeypatch):
    monkeypatch.setenv('SIGNALROOT_AWS_AI_ENABLED','1')
    import ai_engine
    monkeypatch.setattr(ai_engine,'openai_chat',lambda messages: '{"diagnosis":"Insufficient evidence","supporting_evidence_ids":[],"counterevidence_ids":[],"explanation":"Events are ambiguous.","recommendations":["Inspect metrics."]}')
    client=TestClient(app)
    r=client.post('/api/aws/analyze-window-ai',json={'incident_id':'w','signals':[{'timestamp':'now','source':'rds','name':'Database RDS event','value':'availability category'}]})
    assert r.status_code==200
    assert r.json()['ai']['diagnosis']=='Insufficient evidence'
    assert 'baseline' in r.json()


def test_ai_rejects_untrusted_source(monkeypatch):
    monkeypatch.setenv('SIGNALROOT_AWS_AI_ENABLED','1')
    client=TestClient(app)
    r=client.post('/api/aws/analyze-window-ai',json={'signals':[{'name':'X','source':'arbitrary','value':'test'}]})
    assert r.status_code==400


def test_aws_snapshot_enriches_rds_without_message_leak():
    incident=aws._snapshot([],[{'SourceIdentifier':'signalroot-lab-db','EventCategories':['availability'],'Date':datetime.now(timezone.utc)}],diagnose,mode='test',region='us-east-2')
    class CW: pass
    class Session:
        def client(self,name,config=None): raise RuntimeError('no ec2')
    e={'SourceIdentifier':'signalroot-lab-db','EventCategories':['availability'],
       'Date':datetime.now(timezone.utc),'Message':'Database rebooted customer-secret-456'}
    result=aws.enrich_snapshot(incident,CW(),Session(),None,[],'us-east-2',diagnose,raw_rds_events=[e])
    assert result['incidents'][0]['rds_indicators']['categories_detected']==['restart']
    assert 'customer-secret-456' not in str(result)
    assert result['investigations']
