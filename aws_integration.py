"""Read-only, manually invoked regional AWS snapshot. No mutations, no automatic polling.

Supports local AWS profile/role credential chain; optionally STS AssumeRole.
Never returns credential material, raw AWS alarm reasons, or raw RDS messages.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Callable

REGION_RE = re.compile(r"^[a-z]{2}(?:-gov)?-[a-z]+-\d$")
ARN_RE = re.compile(r"^arn:(?:aws|aws-us-gov|aws-cn):iam::\d{12}:role/[a-zA-Z0-9+=,.@_/-]+$")
MAX_ALARMS = 30
MAX_EVENTS = 40
MAX_METRIC_ALARMS = 8
MAX_EC2_INSTANCES = 20
EVENT_WINDOW_MINUTES = 180

class AWSIntegrationError(Exception):
    pass

def _timestamp(dt):
    if dt is None:
        return "unknown"
    if isinstance(dt, datetime):
        return dt.astimezone(timezone.utc).isoformat()
    return str(dt)

def _identity(name):
    # No access to full AWS descriptions, ARN or account identifier in UI.
    return str(name or 'unknown')[:100]

def _make_incident(incident_cls, signal_cls, case_id, summary, signals):
    return incident_cls(incident_id=case_id, summary=summary, signals=[signal_cls(**s) for s in signals])

def _diagnose_record(diagnose_fn, inc):
    from app import Incident, Signal
    payload = _make_incident(Incident, Signal, inc['id'], inc['summary'], inc['signals'])
    return {**inc, 'prediction': diagnose_fn(payload)}

def _normalize_alarm(alarm, idx):
    name = _identity(alarm.get('AlarmName'))
    state = alarm.get('StateValue', 'INSUFFICIENT_DATA')
    ts = _timestamp(alarm.get('StateTransitionedTimestamp') or alarm.get('StateUpdatedTimestamp'))
    namespace = _identity(alarm.get('Namespace'))
    metric = _identity(alarm.get('MetricName'))
    resource = next((str(d.get('Value', ''))[:100] for d in alarm.get('Dimensions', [])
                     if d.get('Name') in ('DBInstanceIdentifier', 'DBClusterIdentifier')), '')
    is_db = namespace == 'AWS/RDS' or bool(resource)
    # An ALARM only means threshold breach; it doesn't establish unavailability.
    if is_db:
        signal_name = 'Database CloudWatch alarm'
        val = f'{metric or name}: alarm threshold breached' if state == 'ALARM' else f'{metric or name}: {state}'
    else:
        signal_name = 'CloudWatch alarm'
        val = f'{metric or name}: {state}'
    return {'id': f'aws-alarm-{idx}', 'summary': f'CloudWatch {state}: {name}',
            'kind': 'CloudWatch alarm', 'observed_at': ts,
            'resource': resource or None,
            'signals': [{'timestamp': ts, 'source':'cloudwatch', 'name': signal_name, 'value': val,
                         'note': f'namespace={namespace or "unknown"}; state={state}'}]}

def _normalize_rds_event(event, idx):
    ts = _timestamp(event.get('Date'))
    source = _identity(event.get('SourceIdentifier'))
    categories = [str(x).lower() for x in event.get('EventCategories', [])]
    # AWS may report messages containing arbitrary content; don't forward or store them here.
    kind = 'availability' if any(x in ('failure','failover','availability','recovery') for x in categories) else 'rds event'
    # Categories alone are not proof of a current outage (e.g. recovery/failover).
    val = f'RDS event category: {", ".join(categories) or "unspecified"}; review AWS console for details'
    return {'id': f'aws-rds-{idx}', 'summary': f'RDS event ({kind}) for {source}',
            'kind': 'RDS event', 'observed_at': ts, 'resource': source,
            'signals': [{'timestamp': ts, 'source': 'rds', 'name': 'Database RDS event',
                         'value': val, 'note': 'An event is not proof of active unavailability'}]}

def _snapshot(alarms, events, diagnose_fn, *, mode, region):
    incidents = [_diagnose_record(diagnose_fn, _normalize_alarm(a, i+1)) for i,a in enumerate(alarms[:MAX_ALARMS])]
    incidents += [_diagnose_record(diagnose_fn, _normalize_rds_event(e, i+1)) for i,e in enumerate(events[:MAX_EVENTS])]
    return {'mode':mode, 'region':region, 'read_only':True, 'live_ai_used':False,
            'manual_refresh_only':True, 'fetched_at': datetime.now(timezone.utc).isoformat(),
            'warning': ('Observed AWS alarm states and event categories are not confirmed root causes. '
                        'RDS event messages and alarm descriptions are withheld. Metric samples and EC2 state are observations, not root causes.'),
            'counts':{'cloudwatch_alarms':len(alarms), 'rds_events':len(events), 'incidents':len(incidents)},
            'incidents':incidents}

def demo_aws_snapshot(diagnose_fn):
    dt = datetime(2026,10,28,10,0,tzinfo=timezone.utc)
    alarms = [
        {'AlarmName':'demo-aurora-cpu-high','StateValue':'ALARM','Namespace':'AWS/RDS',
         'MetricName':'CPUUtilization','StateUpdatedTimestamp':dt,
         'Dimensions':[{'Name':'DBClusterIdentifier','Value':'demo-aurora-cluster'}]},
        {'AlarmName':'demo-api-errors','StateValue':'ALARM','Namespace':'AWS/ApplicationELB',
         'MetricName':'HTTPCode_Target_5XX_Count','StateUpdatedTimestamp':dt+timedelta(minutes=3)},
    ]
    events = [{'SourceIdentifier':'demo-aurora-cluster','Date':dt+timedelta(minutes=2),
               'EventCategories':['failover'], 'Message':'Not exposed to dashboard'}]
    snapshot=_snapshot(alarms,events,diagnose_fn,mode='synthetic_demo',region='us-east-1')
    snapshot['correlation_windows']=correlate_observations(snapshot['incidents'])
    snapshot['counts']['ec2_instances']=0
    snapshot['collection_notes']=[]
    return snapshot

def _session(region):
    try:
        import boto3
        from botocore.config import Config
        profile = os.environ.get('AWS_PROFILE') or None
        session = boto3.Session(profile_name=profile, region_name=region)
        opts = Config(connect_timeout=3, read_timeout=10, retries={'max_attempts':2,'mode':'standard'})
        role_arn = os.environ.get('SIGNALROOT_AWS_ROLE_ARN')
        if role_arn:
            if not ARN_RE.fullmatch(role_arn):
                raise AWSIntegrationError('Invalid SIGNALROOT_AWS_ROLE_ARN')
            assume = {'RoleArn':role_arn, 'RoleSessionName':'SignalRootReadOnly'}
            external_id = os.environ.get('SIGNALROOT_AWS_EXTERNAL_ID')
            if external_id:
                assume['ExternalId'] = external_id
            sts = session.client('sts', config=opts)
            creds = sts.assume_role(**assume)['Credentials']
            session = boto3.Session(aws_access_key_id=creds['AccessKeyId'],
                     aws_secret_access_key=creds['SecretAccessKey'],
                     aws_session_token=creds['SessionToken'], region_name=region)
        return session,opts
    except AWSIntegrationError:
        raise
    except Exception as exc:
        raise AWSIntegrationError(f'AWS credential setup failed ({type(exc).__name__}). Check your profile/role and region.') from None

def collect_aws_snapshot(diagnose_fn):
    region = os.environ.get('SIGNALROOT_AWS_REGION', 'us-east-1')
    if not REGION_RE.fullmatch(region):
        raise AWSIntegrationError('Invalid SIGNALROOT_AWS_REGION')
    session, opts = _session(region)
    try:
        cw = session.client('cloudwatch',config=opts)
        rds = session.client('rds', config=opts)
        alarms=[]; token=None
        while len(alarms) < MAX_ALARMS:
            args={'StateValue':'ALARM','MaxRecords':min(100,MAX_ALARMS-len(alarms))}
            if token: args['NextToken']=token
            response=cw.describe_alarms(**args)
            alarms.extend(response.get('MetricAlarms', []))
            alarms.extend(response.get('CompositeAlarms', []))
            # Stop at cap; do not enumerate entire accounts.
            token=response.get('NextToken')
            if not token: break
        alarms=alarms[:MAX_ALARMS]
        # RDS describe_events supports Duration in minutes; no payload of log messages returned in JSON.
        resp = rds.describe_events(SourceType='db-instance',Duration=EVENT_WINDOW_MINUTES,MaxRecords=MAX_EVENTS)
        events=resp.get('Events',[])[:MAX_EVENTS]
        snapshot = _snapshot(alarms,events,diagnose_fn,mode='aws_read_only_snapshot',region=region)
        return enrich_snapshot(snapshot, cw, session, opts, alarms, region, diagnose_fn)
    except Exception as exc:
        raise AWSIntegrationError(f'AWS read failed ({type(exc).__name__}). Check CloudWatch/RDS read permissions and AWS region.') from None


# v0.6.1: bounded, optional read-only enrichment. Failure of optional APIs must
# not erase the previously working CloudWatch / RDS event snapshot.
def _metric_samples(cw, alarm, now=None):
    """Fetch recent points for an ordinary single-metric alarm (never raw logs)."""
    if alarm.get('Metrics') or not alarm.get('MetricName') or not alarm.get('Namespace'):
        return [], 'Unsupported alarm metric configuration (metric math/composite or missing metric).'
    name = str(alarm['MetricName'])
    namespace = str(alarm['Namespace'])
    if len(name) > 255 or len(namespace) > 255:
        return [], 'Metric identifier was too long.'
    dims = alarm.get('Dimensions', [])
    if len(dims) > 10:
        return [], 'Metric has too many dimensions for this limited scan.'
    stat = alarm.get('Statistic') or 'Average'
    if stat not in ('Average','Sum','Minimum','Maximum','SampleCount'):
        return [], 'Unsupported statistic.'
    now = now or datetime.now(timezone.utc)
    response = cw.get_metric_statistics(Namespace=namespace,MetricName=name,
        Dimensions=dims,StartTime=now-timedelta(minutes=45),EndTime=now,
        Period=300,Statistics=[stat])
    points=[]
    for p in sorted(response.get('Datapoints',[]), key=lambda x:x.get('Timestamp',now))[:12]:
        v=p.get(stat)
        if isinstance(v,(int,float)):
            points.append({'timestamp':_timestamp(p.get('Timestamp')),'value':round(v,4),'statistic':stat,'unit':p.get('Unit','None')})
    return points,None


def _ec2_records(session, opts, region):
    """Only describe instances carrying the SignalRoot test-lab Name tag."""
    ec2=session.client('ec2',config=opts)
    res=ec2.describe_instances(Filters=[{'Name':'tag:Name','Values':['signalroot-lab*']}],MaxResults=MAX_EC2_INSTANCES)
    records=[]
    for reservation in res.get('Reservations',[]):
        for inst in reservation.get('Instances',[]):
            if len(records)>=MAX_EC2_INSTANCES: break
            # No instance IDs, addresses, custom user-data or arbitrary tags exposed.
            state=str(inst.get('State',{}).get('Name','unknown')).lower()
            tags=inst.get('Tags',[])
            name=next((str(t.get('Value',''))[:80] for t in tags if t.get('Key')=='Name'), 'signalroot-lab-ec2')
            if not name.startswith('signalroot-lab'):continue
            records.append({'name':name,'state':state,'observed_at':datetime.now(timezone.utc).isoformat()})
    return records


def _clock(value):
    try:
        dt=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (ValueError, TypeError):return None


def correlate_observations(incidents, window_minutes=20):
    """Temporal grouping only; no claim that one event caused another."""
    dated=sorted(((t,c) for c in incidents if (t:=_clock(c.get('observed_at')))),key=lambda pair:pair[0])
    groups=[]
    for t, event in dated:
        if groups and (t-groups[-1]['_last']).total_seconds() <= window_minutes*60:
            g=groups[-1]
        else:
            g={'id':f'window-{len(groups)+1}','_last':t,'events':[],'observed_at':t.isoformat()}
            groups.append(g)
        g['events'].append({'id':event['id'],'kind':event['kind'],
                            'summary':event['summary'],'observed_at':event['observed_at']})
        g['_last']=t
    for g in groups:
        del g['_last']
        g['event_count']=len(g['events'])
        g['interpretation']='Time proximity only. A shared incident or causal relationship is not established.'
    return groups


def enrich_snapshot(snapshot, cw, session, opts, alarms, region, diagnose_fn):
    warnings=[]
    alarm_records=[c for c in snapshot['incidents'] if c['kind']=='CloudWatch alarm']
    for incident, alarm in zip(alarm_records[:MAX_METRIC_ALARMS], alarms[:MAX_METRIC_ALARMS]):
        try:
            points,reason=_metric_samples(cw,alarm)
            incident['metric_samples']=points
            incident['metric_status']=reason or ('samples_collected' if points else 'no_samples_returned')
        except Exception as exc:
            incident['metric_samples']=[]
            incident['metric_status']='metric_read_unavailable'
            if 'CloudWatch metric read unavailable' not in warnings:
                warnings.append('CloudWatch metric read unavailable; check cloudwatch:GetMetricStatistics permission.')
    # EC2 is limited to resources explicitly named signalroot-lab*.
    try:
        instances=_ec2_records(session,opts,region)
        for i, instance in enumerate(instances):
            timestamp=instance['observed_at']
            state=instance['state']
            record={'id':f'aws-ec2-{i+1}','kind':'EC2 status','observed_at':timestamp,
               'summary':f'EC2 instance state: {state}', 'resource':instance['name'],
               'signals':[{'timestamp':timestamp,'source':'ec2','name':'EC2 instance state',
                           'value':state,'note':'Snapshot status only; no root cause inferred.'}]}
            snapshot['incidents'].append(_diagnose_record(diagnose_fn,record))
        snapshot['counts']['ec2_instances']=len(instances)
    except Exception:
        snapshot['counts']['ec2_instances']=0
        warnings.append('EC2 status read unavailable; check ec2:DescribeInstances permission.')
    snapshot['counts']['incidents']=len(snapshot['incidents'])
    snapshot['correlation_windows']=correlate_observations(snapshot['incidents'])
    snapshot['collection_notes']=warnings
    snapshot['metric_window_minutes']=45
    snapshot['rds_event_window_minutes']=EVENT_WINDOW_MINUTES
    snapshot['warning']=('Observed states, numeric metric samples, and time proximity are not confirmed root causes. '
                         'Raw RDS messages, alarm descriptions, application logs, and secrets are not collected.')
    return snapshot
