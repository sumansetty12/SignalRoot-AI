'''Single-process opt-in pilot scheduler and SQLite incident ledger.
No AWS writes, no remediation; snapshots contain only redacted outputs of aws_integration.
'''
from __future__ import annotations
import hashlib
import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

_lock = threading.RLock()
_stop = threading.Event()
_worker = None
_last_error = None
_last_scan = None


def config():
    interval = int(os.getenv('SIGNALROOT_POLL_SECONDS', '300'))
    if not 60 <= interval <= 86400:
        raise ValueError('SIGNALROOT_POLL_SECONDS must be between 60 and 86400')
    return {
        'auto_enabled': os.getenv('SIGNALROOT_AUTO_MONITOR') == '1',
        'aws_enabled': os.getenv('SIGNALROOT_AWS_ENABLED') == '1',
        'interval_seconds': interval,
        'auto_ai_enabled': os.getenv('SIGNALROOT_AUTO_AI_ENABLED') == '1',
        'daily_ai_limit': max(0, min(int(os.getenv('SIGNALROOT_DAILY_AI_LIMIT', '0')), 20)),
        'notifications_enabled': bool(os.getenv('SIGNALROOT_WEBHOOK_URL')),
    }


def db_path():
    return Path(os.getenv('SIGNALROOT_DB_PATH', str(Path(__file__).resolve().parent / 'data' / 'incidents.sqlite3'))).resolve()


def connect():
    dest=db_path()
    dest.parent.mkdir(parents=True,exist_ok=True)
    con=sqlite3.connect(str(dest),timeout=15)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA busy_timeout=15000')
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('''CREATE TABLE IF NOT EXISTS observations (
      fingerprint TEXT PRIMARY KEY, first_seen TEXT NOT NULL,
      last_seen TEXT NOT NULL, seen_count INTEGER NOT NULL,
      kind TEXT NOT NULL, summary TEXT NOT NULL, observed_at TEXT NOT NULL,
      region TEXT NOT NULL, diagnosis TEXT NOT NULL, status TEXT NOT NULL,
      acknowledged INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL)''')
    con.execute('''CREATE TABLE IF NOT EXISTS scans (
      id INTEGER PRIMARY KEY AUTOINCREMENT, scanned_at TEXT NOT NULL,
      event_count INTEGER NOT NULL, new_count INTEGER NOT NULL, region TEXT NOT NULL)''')
    con.execute('''CREATE TABLE IF NOT EXISTS ai_usage (
      id INTEGER PRIMARY KEY AUTOINCREMENT, requested_at TEXT NOT NULL,
      event_fingerprint TEXT NOT NULL, result TEXT NOT NULL)''')
    con.commit()
    return con


def fingerprint(record,region):
    # Stable within repeated overlapping scans. No account identifiers included.
    canonical=json.dumps([region,record.get('kind'),record.get('summary'),
                          record.get('resource'),record.get('observed_at')],
                          sort_keys=True,default=str)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def persist_snapshot(snapshot, *, notify=False, ai=False):
    now=datetime.now(timezone.utc).isoformat()
    region=snapshot.get('region','unknown')
    additions=[]
    with _lock:
        with connect() as db:
            for event in snapshot.get('incidents',[])[:120]:
                key=fingerprint(event,region)
                prediction=event.get('prediction',{})
                # Store bounded normalized evidence, not original AWS raw messages.
                payload=json.dumps(event,default=str)[:20000]
                result=db.execute('''INSERT OR IGNORE INTO observations
                (fingerprint,first_seen,last_seen,seen_count,kind,summary,observed_at,region,diagnosis,status,payload)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (key,now,now,1,str(event.get('kind',''))[:100],str(event.get('summary',''))[:250],
                 str(event.get('observed_at','unknown'))[:100],region,
                 str(prediction.get('diagnosis','Insufficient evidence'))[:150],
                 'open',payload))
                if result.rowcount:
                    additions.append({'fingerprint':key,'summary':str(event.get('summary',''))[:250],
                                      'kind':event.get('kind',''), 'observed_at':event.get('observed_at','')})
                else:
                    db.execute('UPDATE observations SET last_seen=?, seen_count=seen_count+1 WHERE fingerprint=?', (now,key))
            db.execute('INSERT INTO scans(scanned_at,event_count,new_count,region) VALUES(?,?,?,?)',
                       (now,len(snapshot.get('incidents',[])),len(additions),region))
    if notify:
        for item in additions[:5]:
            _notify(item)
    if ai:
        for item in additions[:5]:
            _auto_ai(item,snapshot)
    return {'observed':len(snapshot.get('incidents',[])),'new':len(additions),'region':region,'new_items':additions}


def _notify(item):
    url=os.getenv('SIGNALROOT_WEBHOOK_URL','')
    if not url:
        return
    parsed=urlparse(url)
    # Only explicitly configured HTTPS webhook. No arbitrary endpoints from UI.
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
        return
    # No detailed evidence, secrets or account identifiers sent to webhook.
    body=json.dumps({'text':'SignalRoot AI: new AWS observation (pilot). Review the local dashboard. Type: '+str(item['kind'])[:60]}).encode()
    try:
        with urlopen(Request(url,data=body,headers={'Content-Type':'application/json'},method='POST'),timeout=5) as r:
            r.read(128)
    except Exception:
        pass  # Notifications are best-effort and never interrupt collection.


def _auto_ai(item,snapshot):
    cfg=config()
    if not (cfg['auto_ai_enabled'] and cfg['daily_ai_limit'] and os.getenv('SIGNALROOT_AWS_AI_ENABLED')=='1'):
        return
    if not os.getenv('OPENAI_API_KEY'):
        return
    day=datetime.now(timezone.utc).date().isoformat()
    with _lock:
        with connect() as db:
            count=db.execute('SELECT COUNT(*) FROM ai_usage WHERE requested_at >= ?', (day,)).fetchone()[0]
            if count >= cfg['daily_ai_limit']:
                return
            # Reserve quota before contacting provider. Failed attempts count.
            db.execute('INSERT INTO ai_usage(requested_at,event_fingerprint,result) VALUES(?,?,?)',
                       (datetime.now(timezone.utc).isoformat(),item['fingerprint'],'reserved'))
    source=next((x for x in snapshot.get('incidents',[]) if fingerprint(x,snapshot['region'])==item['fingerprint']),None)
    if not source:
        return
    # Only sanitized source signals; no raw logs are sent.
    try:
        from app import Incident, Signal
        from ai_engine import analyze_ai
        inc=Incident(incident_id='auto-'+item['fingerprint'][:12],summary='AWS observation; cause unconfirmed',
                     signals=[Signal(**s) for s in source.get('signals',[])[:10]
                              if s.get('source') in ('rds','cloudwatch','ec2','metrics')])
        result=analyze_ai(inc)
        value=str(result.get('diagnosis','unknown'))[:180]
    except Exception:
        value='failed'
    with _lock:
        with connect() as db:
            db.execute('UPDATE ai_usage SET result=? WHERE id=(SELECT MAX(id) FROM ai_usage WHERE event_fingerprint=?)',
                       (value,item['fingerprint']))


def history(limit=50,unacknowledged_only=False):
    limit=max(1,min(int(limit),200))
    with _lock:
        with connect() as db:
            rows=db.execute('SELECT fingerprint,first_seen,last_seen,seen_count,kind,summary,observed_at,region,diagnosis,status,acknowledged FROM observations '+
                            ('WHERE acknowledged=0 ' if unacknowledged_only else '')+
                            'ORDER BY first_seen DESC LIMIT ?', (limit,)).fetchall()
            return [dict(row) for row in rows]


def acknowledge(key):
    with _lock:
        with connect() as db:
            cur=db.execute('UPDATE observations SET acknowledged=1 WHERE fingerprint=?',(key,))
            return bool(cur.rowcount)


def detail(key):
    with _lock:
        with connect() as db:
            row=db.execute('SELECT * FROM observations WHERE fingerprint=?',(key,)).fetchone()
            if not row: return None
            d=dict(row); d['payload']=json.loads(d['payload']); return d


def summary():
    global _last_error,_last_scan
    with _lock:
        with connect() as db:
            total=db.execute('SELECT COUNT(*) FROM observations').fetchone()[0]
            open_=db.execute('SELECT COUNT(*) FROM observations WHERE acknowledged=0').fetchone()[0]
            scans=db.execute('SELECT COUNT(*) FROM scans').fetchone()[0]
            today=datetime.now(timezone.utc).date().isoformat()
            ai_used=db.execute('SELECT COUNT(*) FROM ai_usage WHERE requested_at >= ?', (today,)).fetchone()[0]
    return {**config(),'total_observations':total,'unacknowledged':open_,
            'scan_count':scans,'ai_attempts_today':ai_used,'last_scan':_last_scan,
            'last_error':_last_error,'worker_running':bool(_worker and _worker.is_alive()),
            'scope':'single-account localhost pilot; not a multi-tenant SaaS'}


def scan_once(*,send_notifications=False,auto_ai=False):
    global _last_scan,_last_error
    if not config()['aws_enabled']:
        raise RuntimeError('SIGNALROOT_AWS_ENABLED must be 1')
    from aws_integration import collect_aws_snapshot
    from app import diagnose
    try:
        snap=collect_aws_snapshot(diagnose)
        result=persist_snapshot(snap,notify=send_notifications,ai=auto_ai)
        _last_scan=datetime.now(timezone.utc).isoformat()
        _last_error=None
        return result
    except Exception as exc:
        _last_error=str(exc)[:250]
        raise


def _loop():
    # Delay first scan so the API is available to inspect the state and disable safely.
    while not _stop.wait(config()['interval_seconds']):
        try:
            scan_once(send_notifications=True,auto_ai=True)
        except Exception:
            pass


def start():
    global _worker
    cfg=config()
    if not (cfg['auto_enabled'] and cfg['aws_enabled']):
        return False
    with _lock:
        if _worker and _worker.is_alive(): return True
        _stop.clear()
        _worker=threading.Thread(target=_loop,name='signalroot-pilot-poller',daemon=True)
        _worker.start()
        return True


def stop():
    _stop.set()
    if _worker and _worker.is_alive(): _worker.join(timeout=2)
