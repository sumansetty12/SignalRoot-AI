"""Audit an existing 100-case AI report without calling any provider.

This cannot tell true model abstentions from validator-fallback abstentions because
v0.9.1 did not preserve the original output and disposition separately.
"""
import argparse, collections, json
from pathlib import Path
from research.run import LABELS

def audit(path: Path):
    report=json.loads(path.read_text(encoding='utf-8'))
    rows=report.get('rows', [])
    expected_counts=collections.Counter(r.get('expected') for r in rows)
    predicted_counts=collections.Counter(r.get('predicted') for r in rows)
    wrong_abstentions=[r for r in rows if r.get('predicted')=='Insufficient evidence' and r.get('expected')!='Insufficient evidence']
    failed=[r for r in rows if r.get('status')!='ok']
    validator_visible=[r for r in rows if (r.get('explanation') or '').startswith('Model output rejected:')]
    out={
        'source_report':str(path), 'total':len(rows),
        'expected_counts':dict(expected_counts),'predicted_counts':dict(predicted_counts),
        'incorrect_abstentions':len(wrong_abstentions),
        'incorrect_abstention_ids':[r.get('id') for r in wrong_abstentions],
        'provider_or_validation_errors':len(failed),
        'explicit_validator_fallbacks_in_saved_explanations':len(validator_visible),
        'warning':('The previous runner used a combined abstention output. Original model choices '
                   'and validation rejections cannot always be recovered from this report. '
                   'Do not equate all abstentions with model decisions.'),
        'next_step':'Collect separately logged raw choice, parser outcome, evidence validation and final decision on new synthetic cases.'
    }
    return out

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, default=Path('research/report_ai.json'))
    parser.add_argument('--output',type=Path,default=Path('research/audit_summary.json'))
    args=parser.parse_args()
    if not args.report.exists():
        parser.error(f'Report not found: {args.report}; copy the original report from your v0.9.1 folder.')
    result=audit(args.report)
    args.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
