"""One case per family (4 calls total), with explicit paid opt-in."""
import argparse,json,tempfile,hashlib
from pathlib import Path
from run import run,HERE

def main():
  p=argparse.ArgumentParser()
  p.add_argument('--engine',choices=['baseline','ai'],default='baseline')
  p.add_argument('--confirm-paid',action='store_true')
  args=p.parse_args()
  # Use same exact cases and unchanged label provenance. Pilot has its own fingerprint.
  cases=json.loads((HERE/'cases.json').read_text(encoding='utf-8'))
  wanted=('deployment regression','database degradation','upstream dependency degradation','insufficient or conflicting evidence')
  selected=[next(c for c in cases if c['scenario_family']==kind) for kind in wanted]
  # The full 100-case runner has a dataset freeze and expects n=100; pilot intentionally runs four directly.
  import sys
  sys.path.insert(0,str(HERE.parent))
  from app import Incident,diagnose
  from ai_engine import analyze_ai,ProviderError
  if args.engine=='ai' and not args.confirm_paid:
    p.error('Live model requests require --confirm-paid (4 potential billable calls).')
  for c in selected:
    incident=Incident(incident_id=c['id'], summary=c['summary'], signals=c['signals'])
    try:
      result=(analyze_ai(incident) if args.engine=='ai' else diagnose(incident))
      print(c['id'], '|',c['scenario_family'],'| expected:',c['expected'],'| predicted:',result['diagnosis'])
    except ProviderError as exc:
      print(c['id'],'| AI provider failed:',type(exc).__name__,'(not counted as abstention)')
      raise SystemExit(1)
if __name__=='__main__':main()
