from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app import app, diagnose
import aws_integration as aws

client=TestClient(app)

def test_aws_disabled_by_default(monkeypatch):
    monkeypatch.delenv('SIGNALROOT_AWS_ENABLED',raising=False)
    assert client.get('/api/aws/status').json()['enabled'] is False
    response=client.post('/api/aws/scan')
    assert response.status_code == 403

def test_aws_demo_safe_and_browsable():
    response=client.get('/api/aws/demo')
    assert response.status_code == 200
    body=response.json()
    assert body['mode']=='synthetic_demo'
    assert body['counts']['incidents'] == 3
    assert body['read_only'] and not body['live_ai_used']
    assert len(body['incidents'])==3
    assert all('prediction' in x for x in body['incidents'])
    assert 'Not exposed' not in str(body)

def test_alarm_state_does_not_claim_db_unavailable():
    record=aws._normalize_alarm({'AlarmName':'cpu-high','Namespace':'AWS/RDS',
          'MetricName':'CPUUtilization','StateValue':'ALARM'},1)
    assert 'unavailable' not in str(record).lower()
    assert 'threshold breached' in record['signals'][0]['value']

def test_rds_event_redacts_message_and_does_not_assert_outage():
    result=aws._normalize_rds_event({'Date':datetime.now(timezone.utc),'SourceIdentifier':'sandbox-db',
            'EventCategories':['failover'], 'Message':'customer password 123'},1)
    assert 'password' not in str(result)
    assert 'not proof' in result['signals'][0]['note']

def test_aws_live_scan_uses_bounded_read_calls(monkeypatch):
    calls=[]
    class CW:
        def describe_alarms(self, **kwargs):
            calls.append(('cloudwatch',kwargs))
            return {'MetricAlarms':[{'AlarmName':'app-errors','StateValue':'ALARM','Namespace':'AWS/ApplicationELB',
                          'MetricName':'HTTPCode_Target_5XX_Count'}]}
    class RDS:
        def describe_events(self, **kwargs):
            calls.append(('rds',kwargs))
            return {'Events':[{'SourceIdentifier':'mydb','EventCategories':['availability'],
                      'Message':'never return this secret'}]}
    class Session:
        def client(self, name,config=None):return {'cloudwatch':CW(),'rds':RDS()}[name]
    monkeypatch.setattr(aws,'_session',lambda region:(Session(),None))
    monkeypatch.setenv('SIGNALROOT_AWS_REGION','us-east-1')
    result=aws.collect_aws_snapshot(diagnose)
    assert len(calls)==2
    assert result['counts']['incidents']==2
    assert 'never return this secret' not in str(result)

def test_invalid_region_rejected_before_credentials(monkeypatch):
    monkeypatch.setenv('SIGNALROOT_AWS_REGION','us-east-1; rm -rf')
    try: aws.collect_aws_snapshot(diagnose)
    except aws.AWSIntegrationError as exc: assert 'region' in str(exc).lower()
    else: raise AssertionError('Expected region validation')

def test_dashboard_includes_aws_explorer():
    response=client.get('/dashboard')
    assert response.status_code == 200
    assert 'AWS Incident Explorer' in response.text
    assert '/api/aws/demo' in response.text
