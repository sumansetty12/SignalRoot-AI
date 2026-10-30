"""v0.7.0 bounded AWS investigation helpers; no AWS writes, no raw logs in results."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import os
import re

MAX_LOG_GROUPS = 3
MAX_LOG_EVENTS = 50
MAX_RDS_MESSAGES = 40

# Match safe categories only; never forward RDS Message or log text.
RDS_PATTERNS = (
    ('failover', re.compile(r'failover|fail.over|promot(?:ed|ion)|switchover', re.I)),
    ('restart', re.compile(r'restart|reboot', re.I)),
    ('connectivity', re.compile(r'connect(?:ion|ivity)|unreachable|cannot reach', re.I)),
    ('storage', re.compile(r'storage|disk|space', re.I)),
    ('maintenance', re.compile(r'maintenance|patch|upgrade', re.I)),
    ('recovery', re.compile(r'recover(?:ed|y|ing)|available|completed', re.I)),
)
LOG_PATTERNS = (
    ('timeout', re.compile(r'timeout|timed out',re.I)),
    ('connection_error', re.compile(r'connection refused|connection reset|cannot connect|connection failed',re.I)),
    ('server_error', re.compile(r'\b5\d\d\b|internal server error',re.I)),
    ('exception', re.compile(r'exception|traceback',re.I)),
)

def sanitize_rds_event(event:dict) -> dict:
    """Transform free text to category flags; no message content or arbitrary identifiers."""
    msg = str(event.get('Message') or '')[:4000]
    flags = [label for label,pattern in RDS_PATTERNS if pattern.search(msg)]
    return {'categories_detected':flags[:6], 'message_examined':bool(msg),
            'note':'Keyword indicators only; not proof of cause or current database state.'}

def sanitized_rds_signal(event:dict) -> dict | None:
    fields = sanitize_rds_event(event)
    # Prefer lack of evidence to overstating a database outage.
    if not fields['categories_detected']:
        return None
    event_date = event.get('Date')
    timestamp = event_date.astimezone(timezone.utc).isoformat() if isinstance(event_date,datetime) else 'unknown'
    return {'timestamp':timestamp,'source':'rds', 'name':'Database event indicators',
            'value':', '.join(fields['categories_detected']),
            'note':'Sanitized AWS message classification; verify in AWS console.'}

def summarize_log_events(events:list[dict]) -> dict:
    """Only pattern counts; no raw messages, event IDs, IPs or user data returned."""
    counts={label:0 for label,_ in LOG_PATTERNS}
    for event in events[:MAX_LOG_EVENTS]:
        msg=str(event.get('message') or '')[:4000]
        for label, pattern in LOG_PATTERNS:
            if pattern.search(msg):counts[label]+=1
    return {'events_examined':min(len(events),MAX_LOG_EVENTS),
            'pattern_counts':counts,
            'note':'Keyword counts only, not evidence that the application or database caused the incident.'}

def read_logs(session, opts, now=None):
    """Opt-in allowlisted CloudWatch log groups; bounded queries and redacted output."""
    raw=os.getenv('SIGNALROOT_LOG_GROUPS','')
    groups=[g.strip() for g in raw.split(',') if g.strip()]
    if not groups:
        return {'enabled':False,'groups_scanned':0,'summaries':[], 'note':'No log groups allowlisted.'}
    if len(groups)>MAX_LOG_GROUPS or any(not g.startswith('/signalroot-lab/') or len(g)>128 for g in groups):
        raise ValueError('Only up to 3 /signalroot-lab/ log groups may be allowlisted.')
    now=now or datetime.now(timezone.utc)
    client=session.client('logs',config=opts)
    summaries=[]
    for group in groups:
        response=client.filter_log_events(logGroupName=group,
            startTime=int((now-timedelta(minutes=45)).timestamp()*1000),
            endTime=int(now.timestamp()*1000),limit=MAX_LOG_EVENTS)
        summary=summarize_log_events(response.get('events',[]))
        summary['log_group']='signalroot-lab (allowlisted)'
        summaries.append(summary)
    return {'enabled':True,'groups_scanned':len(groups),'summaries':summaries,
            'note':'Log content is examined locally for predefined patterns; raw lines are never stored or returned.'}

def ec2_instance_health(session,opts,instances):
    """Describe status checks only for lab-tagged instances already identified by describe_instances."""
    if not instances:return []
    ec2=session.client('ec2',config=opts)
    ids=[x['instance_id'] for x in instances if x.get('instance_id')][:20]
    if not ids:return []
    res=ec2.describe_instance_status(InstanceIds=ids,IncludeAllInstances=True)
    output=[]
    for status in res.get('InstanceStatuses',[]):
        output.append({'instance_status':status.get('InstanceStatus',{}).get('Status','unknown'),
                       'system_status':status.get('SystemStatus',{}).get('Status','unknown'),
                       'observed_at':datetime.now(timezone.utc).isoformat()})
    return output

def analyze_window(window:dict,incidents:list[dict]) -> dict:
    by_id={r['id']:r for r in incidents}
    selected=[by_id[e['id']] for e in window.get('events',[]) if e['id'] in by_id]
    kinds={r.get('kind') for r in selected}
    classifications=[f for r in selected for f in r.get('rds_indicators',{}).get('categories_detected',[])]
    observed=[]
    if 'RDS event' in kinds:observed.append('RDS events occurred in this time window')
    if 'CloudWatch alarm' in kinds:observed.append('CloudWatch alarm(s) were active in this time window')
    if 'EC2 status' in kinds:observed.append('EC2 state was sampled in this time window')
    possible=[]
    if any(c in ('failover','restart') for c in classifications):
        possible.append('An RDS event message included a restart/failover indicator; confirm the event in the RDS console.')
    if 'RDS event' in kinds and 'CloudWatch alarm' in kinds:
        possible.append('Database and alarm observations are temporally adjacent, but causation is unproven.')
    return {'window_id':window.get('id'), 'observation_count':len(selected),
            'observed_facts':observed,'possible_connections':possible,
            'root_cause_confirmed':False,'confidence':'unverified',
            'missing_evidence':['Application-side dependency traces or database connectivity checks',
                                'Comparison against a pre-incident baseline'],
            'safety_note':'Temporal correlation and keyword flags are not proof of root cause.'}

def build_ai_input(incidents:list[dict], window:dict) -> dict:
    """Build limited evidence input from an already-sanitized snapshot; no raw AWS payloads."""
    by_id={r['id']:r for r in incidents}
    signals=[]
    for event in window.get('events',[])[:20]:
        r=by_id.get(event.get('id'))
        if not r:continue
        for signal in r.get('signals',[])[:2]:
            signals.append({k:signal.get(k,'') for k in ('timestamp','source','name','value','note')})
    return {'incident_id':f"aws-{window.get('id','window')}",
            'summary':'AWS observed events in a time window; causal relationship is not established.',
            'signals':signals[:40]}
