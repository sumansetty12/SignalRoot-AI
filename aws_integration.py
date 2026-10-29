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
                        'No service metrics, log contents, or alarm descriptions are collected in this version.'),
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
    return _snapshot(alarms,events,diagnose_fn,mode='synthetic_demo',region='us-east-1')

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
        resp = rds.describe_events(SourceType='db-instance',Duration=60,MaxRecords=MAX_EVENTS)
        events=resp.get('Events',[])[:MAX_EVENTS]
        return _snapshot(alarms,events,diagnose_fn,mode='aws_read_only_snapshot',region=region)
    except Exception as exc:
        raise AWSIntegrationError(f'AWS read failed ({type(exc).__name__}). Check CloudWatch/RDS read permissions and AWS region.') from None
