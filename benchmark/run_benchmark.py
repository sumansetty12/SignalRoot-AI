"""Evaluate the read-only heuristic baseline on labelled synthetic scenarios."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app import Incident, diagnose  # noqa: E402


def main():
    path = Path(__file__).with_name('scenarios.json')
    scenarios = json.loads(path.read_text(encoding='utf-8'))
    results = []
    for entry in scenarios:
        incident = Incident(incident_id=entry['id'], summary=entry['summary'], signals=entry['signals'])
        result = diagnose(incident)
        predicted = result['diagnosis']
        results.append({'id': entry['id'], 'expected': entry['expected'],
                        'predicted': predicted, 'correct': predicted == entry['expected'],
                        'confidence': result['confidence'], 'status': result['status']})

    correct = sum(r['correct'] for r in results)
    total = len(results)
    abstentions = sum(r['predicted'] == 'Insufficient evidence' for r in results)
    labels = ['Deployment regression', 'Dependency or database degradation', 'Insufficient evidence']
    per_label = {label: {'total': sum(r['expected'] == label for r in results),
                         'correct': sum(r['expected'] == label and r['correct'] for r in results)} for label in labels}
    report = {
        'benchmark_version': '0.3.0',
        'limitations': 'Small synthetic set written by the project developer. Not a real-world performance estimate. Rule design and test-set creation are not independent.',
        'total': total, 'correct': correct, 'top1_accuracy': round(correct / total, 4) if total else None,
        'abstentions': abstentions, 'abstention_rate': round(abstentions / total, 4) if total else None,
        'per_expected_label': per_label, 'cases': results,
    }
    output = Path(__file__).with_name('results.json')
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f'Scenarios evaluated: {total}')
    print(f'Correct top-1 diagnoses: {correct}/{total}')
    print(f'Top-1 accuracy: {report["top1_accuracy"]:.4f}')
    print(f'Abstentions: {abstentions}/{total}')
    print()
    for r in results:
        print(f'{"PASS" if r["correct"] else "MISS"} | {r["id"]:<21} | expected={r["expected"]:<36} | predicted={r["predicted"]}')
    print(f'\nReport saved to: {output}')


if __name__ == '__main__':
    main()
