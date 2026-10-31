"""Explicit, cost-capped research evaluation: no live API calls without consent."""
import argparse,collections,hashlib,json,sys,time,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import Incident, diagnose
from ai_engine import analyze_ai,ProviderError
HERE=Path(__file__).resolve().parent
LABELS=('Deployment regression','Dependency or database degradation','Insufficient evidence')

def run(dataset,engine='baseline',limit=0,confirm=False,delay=0.0,results=None):
  manifest=json.loads((HERE/'manifest.json').read_text(encoding='utf-8'))
  if hashlib.sha256(dataset.read_bytes()).hexdigest()!=manifest['sha256_cases_json']:
    raise ValueError('Dataset differs from frozen manifest. Re-label and re-freeze before use.')
  cases=json.loads(dataset.read_text(encoding='utf-8'))
  if len(cases)!=100 or len({c['id'] for c in cases})!=100:
    raise ValueError('Expected 100 unique scenarios.')
  if engine=='ai' and (not confirm or not 1<=limit<=100):
    raise ValueError('AI evaluation requires --confirm-paid and --max-calls 1..100.')
  selected=cases if engine=='baseline' else cases[:limit]
  rows=[]
  for c in selected:
    inc=Incident(incident_id=c['id'], summary=c['summary'], signals=c['signals'])
    started=time.perf_counter()
    try:
      answer=diagnose(inc) if engine=='baseline' else analyze_ai(inc)
      predicted=answer['diagnosis']
      status='ok'
      cited=answer.get('supporting_evidence_ids',[])+answer.get('counterevidence_ids',[])
      valid_refs=all(ref in {f'S{i+1}' for i in range(len(c['signals']))} for ref in cited)
      explanation=answer.get('explanation','')
    except (ProviderError,ValueError) as exc:
      predicted=None;status='provider_or_validation_error';valid_refs=False;explanation=f'{type(exc).__name__} (details omitted)';cited=[]
    rows.append({'id':c['id'],'family':c['scenario_family'],'expected':c['expected'],
                 'predicted':predicted,'correct':predicted==c['expected'],'status':status,
                 'evidence_ids_valid':valid_refs,'cited_evidence_ids':cited,
                 'explanation':explanation[:1200], 'elapsed_seconds':round(time.perf_counter()-started,3)})
    if engine=='ai' and delay>0 and len(rows)<len(selected):time.sleep(delay)
  n=len(rows); errors=sum(r['status']!='ok' for r in rows)
  successful=[r for r in rows if r['status']=='ok']
  confusion={expected:{pred:sum(r['expected']==expected and r['predicted']==pred for r in successful) for pred in LABELS} for expected in LABELS}
  metrics={'mode':engine,'total_cases':n,'completed_calls':len(successful),'error_count':errors,
       'correct':sum(r['correct'] for r in rows),
       'accuracy_all_cases':sum(r['correct'] for r in rows)/n if n else None,
       'accuracy_successful_only':sum(r['correct'] for r in successful)/len(successful) if successful else None,
       'abstention_rate':sum(r['predicted']=='Insufficient evidence' for r in rows)/n if n else None,
       'coverage':sum(r['predicted'] in LABELS[:2] for r in rows)/n if n else None,
       'by_expected_label':{k:{'count':sum(r['expected']==k for r in rows),'correct':sum(r['expected']==k and r['correct'] for r in rows)} for k in LABELS},
       'confusion_matrix':confusion,
       'citation_id_integrity':all(r['evidence_ids_valid'] for r in successful),
       'interpretation':'Developer-authored synthetic template stress test; NOT independent validation or real-world accuracy.',
       'note':'Provider and validation errors count as incorrect for accuracy_all_cases; do not equate valid IDs with semantically valid evidence.',
       'rows':rows}
  target=results or HERE/f'report_{engine}.json'
  target.write_text(json.dumps(metrics,indent=2)+'\n',encoding='utf-8')
  print(f"Engine: {engine} | cases: {n} | correct: {metrics['correct']} | accuracy: {metrics['accuracy_all_cases']:.3f} | errors: {errors} | coverage: {metrics['coverage']:.3f}")
  print('By expected label:',metrics['by_expected_label'])
  print('Saved:',target)
  return metrics

def main():
  p=argparse.ArgumentParser(description='Synthetic evaluation, NOT independent validation')
  p.add_argument('--engine',choices=['baseline','ai'],default='baseline')
  p.add_argument('--confirm-paid',action='store_true',help='Required for any live model calls')
  p.add_argument('--max-calls',type=int,default=0,help='Maximum paid requests (1-100)')
  p.add_argument('--delay',type=float,default=0.5,help='Seconds between AI calls')
  args=p.parse_args()
  run(HERE/'cases.json',args.engine,args.max_calls,args.confirm_paid,args.delay)
if __name__=='__main__':main()
