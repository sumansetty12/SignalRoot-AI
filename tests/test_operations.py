import json
from datetime import datetime, timezone
from fastapi.testclient import TestClient
import app
import operations as ops


def sample():
    return {'region':'us-east-2','incidents':[
        {'id':'aws-rds-1','kind':'RDS event','summary':'RDS availability observed','observed_at':'2026-10-29T23:15:42+00:00',
         'resource':'lab-db','signals':[{'timestamp':'2026-10-29T23:15:42+00:00','source':'rds','name':'RDS event','value':'restart detected'}],
         'prediction':{'diagnosis':'Insufficient evidence'}}]}


def test_history_dedup(tmp_path,monkeypatch):
    monkeypatch.setenv('SIGNALROOT_DB_PATH',str(tmp_path/'db.sqlite3'))
    x=ops.persist_snapshot(sample()); y=ops.persist_snapshot(sample())
    assert x['new']==1 and y['new']==0
    rows=ops.history()
    assert len(rows)==1 and rows[0]['seen_count']==2
    assert ops.detail(rows[0]['fingerprint'])['payload']['kind']=='RDS event'
    assert ops.acknowledge(rows[0]['fingerprint']) is True
    assert ops.history(unacknowledged_only=True)==[]


def test_ops_dashboard_and_endpoints(tmp_path,monkeypatch):
    monkeypatch.setenv('SIGNALROOT_DB_PATH',str(tmp_path/'test.sqlite3'))
    c=TestClient(app.app)
    assert c.get('/dashboard').status_code==200
    assert 'Monitoring &amp; History' in c.get('/dashboard').text
    assert c.get('/api/ops/status').status_code==200
    assert c.get('/api/ops/history').json()['items']==[]
    assert c.get('/api/ops/history/nonexistent').status_code==404


def test_no_automatic_ai_or_notifications_by_default(tmp_path,monkeypatch):
    monkeypatch.setenv('SIGNALROOT_DB_PATH',str(tmp_path/'db.sqlite3'))
    monkeypatch.delenv('SIGNALROOT_WEBHOOK_URL',raising=False)
    monkeypatch.delenv('SIGNALROOT_AUTO_AI_ENABLED',raising=False)
    assert ops.config()['auto_ai_enabled'] is False
    assert ops.persist_snapshot(sample())['new']==1
    assert ops.summary()['ai_attempts_today']==0


def test_disabled_aws_scan_cannot_run(monkeypatch):
    monkeypatch.setenv('SIGNALROOT_AWS_ENABLED','0')
    try:
        ops.scan_once()
        assert False, 'scan should be denied'
    except RuntimeError as exc:
        assert 'SIGNALROOT_AWS_ENABLED' in str(exc)


def test_poll_interval_limits(monkeypatch):
    monkeypatch.setenv('SIGNALROOT_POLL_SECONDS','10')
    try:
        ops.config()
        assert False
    except ValueError:
        pass


def test_notification_rejects_http(monkeypatch):
    monkeypatch.setenv('SIGNALROOT_WEBHOOK_URL','http://localhost:9000/unsafe')
    # No network request permitted for non-HTTPS URLs.
    ops._notify({'kind':'RDS event'})
