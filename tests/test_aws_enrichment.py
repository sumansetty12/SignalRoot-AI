from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from app import app, diagnose
import aws_integration as aws

def test_demo_has_correlation():
    snapshot = aws.demo_aws_snapshot(diagnose)
    assert snapshot['correlation_windows']
    assert snapshot['correlation_windows'][0]['interpretation'].startswith('Time proximity')

def test_metric_samples_sorted_and_bounded():
    now=datetime.now(timezone.utc)
    class CW:
        def get_metric_statistics(self, **args):
            assert args['Period']==300
            return {'Datapoints':[{'Timestamp':now,'Average':7.0},{'Timestamp':now-timedelta(minutes=5),'Average':1.0}]}
    vals,err=aws._metric_samples(CW(),{'Namespace':'AWS/EC2','MetricName':'CPUUtilization',
           'Statistic':'Average','Dimensions':[]}, now=now)
    assert err is None and [x['value'] for x in vals]==[1.0,7.0]

def test_metric_math_skipped_without_fetch():
    class CW:
        def get_metric_statistics(self,**kwargs):raise AssertionError('must not run')
    points,reason=aws._metric_samples(CW(),{'Metrics':[{'Id':'x'}]})
    assert points==[] and reason

def test_ec2_only_lab_tagged():
    class Client:
        def describe_instances(self, **kwargs):
            assert kwargs['Filters'][0]['Values']==['signalroot-lab*']
            return {'Reservations':[{'Instances':[{'State':{'Name':'stopped'},'Tags':[{'Key':'Name','Value':'signalroot-lab-ec2'}]}]}]}
    class Session:
        def client(self,name,config=None):assert name=='ec2';return Client()
    data=aws._ec2_records(Session(),None,'us-east-2')
    assert len(data)==1 and data[0]['state']=='stopped'

def test_correlation_never_asserts_root_cause():
    now=datetime.now(timezone.utc)
    records=[{'id':'1','kind':'RDS event','summary':'event','observed_at':now.isoformat()},
             {'id':'2','kind':'CloudWatch alarm','summary':'alarm','observed_at':(now+timedelta(minutes=3)).isoformat()}]
    windows=aws.correlate_observations(records)
    assert len(windows)==1 and windows[0]['event_count']==2
    assert 'not established' in windows[0]['interpretation']

def test_existing_aws_endpoint_unchanged():
    client=TestClient(app)
    assert client.get('/api/aws/demo').status_code==200
    assert client.get('/health').json()['version']=='0.9.0'
    assert 'Correlated event windows' in client.get('/dashboard').text

def test_optional_failures_do_not_abort_snapshot():
    class CW:
        def get_metric_statistics(self,**kwargs):raise RuntimeError('denied')
    class Session:
        def client(self,*args,**kwargs):raise RuntimeError('denied')
    base=aws._snapshot([{'AlarmName':'test','Namespace':'AWS/EC2','MetricName':'CPUUtilization','StateValue':'ALARM'}],[],diagnose_fn=diagnose,mode='test',region='us-east-2')
    result=aws.enrich_snapshot(base,CW(),Session(),None,[{'Namespace':'AWS/EC2','MetricName':'CPUUtilization'}],'us-east-2',diagnose)
    assert result['counts']['incidents']==1
    assert len(result['collection_notes'])==2
