"""Compare baseline with optional AI provider on a labeled JSON dataset.

IMPORTANT: Included development cases are NOT an independent external evaluation.
"""
import argparse
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import Incident, diagnose
from ai_engine import analyze_ai, ProviderError


def run(path:Path, use_ai=False):
    data=json.loads(path.read_text(encoding='utf-8'))
    rows=[]
    for case in data:
        incident=Incident(incident_id=case['id'],summary=case['summary'],signals=case['signals'])
        try:
            prediction=(analyze_ai(incident) if use_ai else diagnose(incident))['diagnosis']
        except ProviderError as exc:
            raise RuntimeError('AI provider failed; do not count this as an abstention.') from exc
        rows.append({'id':case['id'],'expected':case['expected'], 'predicted':prediction,
                     'correct':prediction==case['expected'],
                     'abstained':prediction=='Insufficient evidence'})
    count=len(rows)
    return {'mode':'ai' if use_ai else 'baseline','dataset':str(path.name),
            'warning':'Developer-authored synthetic cases; not independently labeled and not a real-world estimate.',
            'n':count,'accuracy':sum(x['correct'] for x in rows)/count if count else None,
            'abstention_rate':sum(x['abstained'] for x in rows)/count if count else None,
            'rows':rows}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dataset',default=str(Path(__file__).with_name('development_cases.json')))
    p.add_argument('--engine',choices=['baseline','ai'],default='baseline')
    args=p.parse_args()
    report=run(Path(args.dataset),args.engine=='ai')
    print(json.dumps(report,indent=2))
    out=Path(__file__).parent/f'evaluation_{args.engine}.json'
    out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('Saved:',out)
if __name__=='__main__': main()
