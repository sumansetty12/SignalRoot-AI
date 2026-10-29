"""Evaluate baseline and optionally live AI on the separate synthetic challenge set.

No live calls unless --allow-live-ai is explicitly passed. Provider failures are
accounted as errors (not abstentions and not correct predictions).
"""
from __future__ import annotations
import argparse, collections, hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import Incident, diagnose
from ai_engine import analyze_ai, ProviderError, LABELS

DATASET = Path(__file__).with_name('challenge_cases.json')
MANIFEST = Path(__file__).with_name('challenge_manifest.json')


def validate_dataset(path: Path, manifest_path: Path | None = None):
    raw = path.read_bytes()
    cases = json.loads(raw)
    if not isinstance(cases, list) or not cases:
        raise ValueError('Dataset must be a nonempty list.')
    ids = set()
    for case in cases:
        if case['id'] in ids:
            raise ValueError(f"Duplicate case ID: {case['id']}")
        ids.add(case['id'])
        if case['expected'] not in LABELS:
            raise ValueError(f"Invalid expected label: {case['id']}")
        if not isinstance(case['signals'], list) or not case.get('label_rationale'):
            raise ValueError(f"Missing signals or labeling rationale: {case['id']}")
    digest = hashlib.sha256(raw).hexdigest()
    if manifest_path is not None:
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest['sha256'] != digest or manifest['cases'] != len(cases):
            raise ValueError('Challenge cases differ from the manifest; revalidate labels and version the benchmark.')
    return cases, digest


def metrics(rows):
    """Coverage and selective accuracy expose unsafe confident misdiagnoses."""
    n = len(rows)
    successes = [x for x in rows if x['status'] != 'provider_error']
    answered = [x for x in successes if not x['abstained']]
    expected_known = [x for x in successes if x['expected'] != 'Insufficient evidence']
    unknown = [x for x in successes if x['expected'] == 'Insufficient evidence']
    labels = list(LABELS)
    def ratio(a, b):
        return round(a / b, 4) if b else None
    return {
        'total': n,
        'provider_errors': n - len(successes),
        'evaluated': len(successes),
        'accuracy': ratio(sum(r['correct'] for r in successes), len(successes)),
        'overall_accuracy_treating_errors_as_wrong': ratio(sum(r['correct'] for r in successes), n),
        'coverage': ratio(len(answered), len(successes)),
        'selective_accuracy': ratio(sum(r['correct'] for r in answered), len(answered)),
        'abstention_rate': ratio(sum(r['abstained'] for r in successes), len(successes)),
        'correct_abstention_rate_on_unknown': ratio(sum(r['abstained'] for r in unknown), len(unknown)),
        'incorrect_abstentions_on_known': sum(r['abstained'] for r in expected_known),
        'wrong_non_abstaining_diagnoses': sum(not r['correct'] for r in answered),
        'per_label': {label: {'n': sum(r['expected'] == label for r in successes),
                               'accuracy': ratio(sum(r['correct'] for r in successes if r['expected'] == label),
                                                 sum(r['expected'] == label for r in successes))} for label in labels},
        'confusion_matrix': {label: {pred: sum(r['expected']==label and r['predicted']==pred for r in successes)
                                      for pred in labels} for label in labels},
    }


def evaluate(cases, engine='baseline', provider=None, max_ai_calls=10):
    if engine not in ('baseline', 'ai'):
        raise ValueError('Unknown engine')
    if engine == 'ai' and len([case for case in cases if case['signals']]) > max_ai_calls:
        raise ValueError(f'Live AI call cap exceeded: dataset would require more than {max_ai_calls} calls. Raise --max-ai-calls explicitly.')
    rows = []
    for case in cases:
        incident = Incident(incident_id=case['id'], summary=case['summary'], signals=case['signals'])
        try:
            prediction = diagnose(incident) if engine == 'baseline' else analyze_ai(incident, provider)
            label = prediction['diagnosis']
            row = {'id': case['id'], 'expected': case['expected'], 'predicted': label,
                   'status': 'ok', 'correct': label == case['expected'],
                   'abstained': label == 'Insufficient evidence'}
            if engine == 'ai':
                row['evidence_ids'] = prediction.get('supporting_evidence_ids', [])
                row['validation_abstained'] = str(prediction.get('explanation','')).startswith('Model output rejected:')
        except ProviderError:
            row = {'id': case['id'], 'expected': case['expected'], 'predicted': None,
                   'status': 'provider_error', 'correct': False, 'abstained': False}
        rows.append(row)
    return {'engine': engine, 'metrics': metrics(rows), 'rows': rows,
            'warning': 'Developer-authored synthetic challenge data; this is NOT independent evaluation or real-world accuracy.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine', choices=['baseline','ai','compare'], default='baseline')
    p.add_argument('--allow-live-ai', action='store_true', help='Explicit consent for external, billable API calls using synthetic data')
    p.add_argument('--max-ai-calls', type=int, default=10)
    p.add_argument('--dataset', type=Path, default=DATASET)
    p.add_argument('--output', type=Path, default=None)
    args = p.parse_args()
    if args.max_ai_calls < 0:
        p.error('--max-ai-calls must be nonnegative')
    if args.engine in ('ai','compare') and not args.allow_live_ai:
        p.error('Live AI evaluation requires --allow-live-ai; baseline runs offline.')
    manifest = MANIFEST if args.dataset.resolve() == DATASET.resolve() else None
    cases, digest = validate_dataset(args.dataset, manifest)
    results = {}
    for engine in (('baseline','ai') if args.engine == 'compare' else (args.engine,)):
        results[engine] = evaluate(cases, engine, max_ai_calls=args.max_ai_calls)
    report = {'dataset': args.dataset.name, 'dataset_sha256': digest,
              'dataset_provenance': 'developer-authored synthetic challenge cases, not externally validated',
              'results': results}
    out = args.output or Path(__file__).with_name(f'challenge_report_{args.engine}.json')
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'dataset':report['dataset'], 'dataset_sha256':digest,
                      'metrics': {k:v['metrics'] for k,v in results.items()}},indent=2))
    print(f'Saved: {out}')
    if any(v['metrics']['provider_errors'] for v in results.values()):
        print('WARNING: Provider errors occurred. They are NOT abstentions or correct predictions.')
        return 2
    return 0

if __name__=='__main__':
    raise SystemExit(main())
