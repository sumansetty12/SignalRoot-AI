"""Diagnostic comparison on a newly authored *development* dataset.

Raw provider responses are written only for synthetic cases after explicit opt-in.
Never use this tracing workflow on real customer telemetry.
"""
import argparse, hashlib, json, os, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import Incident, diagnose
from ai_engine import (build_evidence,build_messages,openai_chat,_validate,
                       MAX_SIGNALS,MAX_PAYLOAD_BYTES,ProviderError)
HERE=Path(__file__).resolve().parent

def evaluate_case(case, provider, variant):
    os.environ['SIGNALROOT_PROMPT_VARIANT']=variant
    incident=Incident(incident_id=case['id'],summary=case['summary'],signals=case['signals'])
    baseline=diagnose(incident)
    evidence=build_evidence(incident)
    item={'id':case['id'],'expected':case['expected'],'baseline_prediction':baseline['diagnosis'],
          'variant':variant,'raw_model_diagnosis':None,'validated_diagnosis':None,
          'decision':'not_called','error_type':None,'raw_response':None,
          'cited_evidence_ids':[]}
    if not evidence:
        item.update(decision='empty_input_abstain',validated_diagnosis='Insufficient evidence')
        return item
    if len(evidence)>MAX_SIGNALS:
        item.update(decision='input_rejected',error_type='TooManySignals')
        return item
    messages=build_messages(incident,evidence,baseline)
    if len(json.dumps(messages,default=str).encode())>MAX_PAYLOAD_BYTES:
        item.update(decision='input_rejected',error_type='PayloadTooLarge')
        return item
    try:
        raw=provider(messages)
        # Synthetic data only. Save short model response to debug validation effects.
        item['raw_response']=raw[:4000] if isinstance(raw,str) else None
        try:
            parsed=json.loads(raw)
            if isinstance(parsed,dict):
                item['raw_model_diagnosis']=parsed.get('diagnosis')
        except (ValueError,TypeError):pass
        try:
            valid=_validate(raw,evidence)
            item.update(decision='validated_model_output',validated_diagnosis=valid['diagnosis'],
                        cited_evidence_ids=valid['supporting_evidence_ids']+valid['counterevidence_ids'])
        except ValueError as exc:
            item.update(decision='validator_rejected_abstain',
                        validated_diagnosis='Insufficient evidence',error_type=str(exc))
    except ProviderError as exc:
        item.update(decision='provider_error',error_type=type(exc).__name__)
    return item

def run(variant='hypothesis', engine='baseline',max_calls=0,confirm=False,provider=None,output=None):
    cases_path=HERE/'calibration_dev.json'
    manifest=json.loads((HERE/'calibration_manifest.json').read_text(encoding='utf-8'))
    if hashlib.sha256(cases_path.read_bytes()).hexdigest()!=manifest['sha256']:
        raise ValueError('Calibration dataset fingerprint mismatch.')
    cases=json.loads(cases_path.read_text(encoding='utf-8'))
    if engine=='ai' and (not confirm or not 1<=max_calls<=len(cases)):
        raise ValueError('Live AI requires --confirm-paid and --max-calls 1..18')
    if variant not in ('conservative','hypothesis'):
        raise ValueError('Unknown prompt variant')
    source=provider or openai_chat
    rows=[]; called=0
    for case in cases:
        if engine=='baseline':
            inc=Incident(incident_id=case['id'],summary=case['summary'],signals=case['signals'])
            pred=diagnose(inc)['diagnosis']
            item={'id':case['id'],'expected':case['expected'],'validated_diagnosis':pred,
                  'decision':'baseline','raw_model_diagnosis':None,'raw_response':None}
        else:
            # Explicit maximum of paid provider calls, not number of cases.
            if case['signals'] and called>=max_calls:continue
            if case['signals']:called+=1
            item=evaluate_case(case,source,variant)
        item['correct']=item['validated_diagnosis']==case['expected']
        rows.append(item)
    out={'dataset':'developer-authored calibration development only; NOT independent test',
         'engine':engine,'variant':variant,'provider_calls_attempted':called,
         'cases_evaluated':len(rows),'correct':sum(r['correct'] for r in rows),
         'accuracy':sum(r['correct'] for r in rows)/len(rows) if rows else None,
         'model_abstentions':sum(r.get('raw_model_diagnosis')=='Insufficient evidence' and r['decision']=='validated_model_output' for r in rows),
         'validator_fallback_abstentions':sum(r['decision']=='validator_rejected_abstain' for r in rows),
         'missing_diagnosis_after_provider_error':sum(r['decision']=='provider_error' for r in rows),
         'rows':rows,'warning':'Raw model responses are recorded for synthetic cases only; do not provide real customer telemetry.'}
    target=output or HERE/f'calibration_{engine}_{variant}.json'
    target.write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
    print(f"{engine}/{variant}: {out['correct']}/{out['cases_evaluated']} correct; "
          f"calls={called}, model abstentions={out['model_abstentions']}, validator fallbacks={out['validator_fallback_abstentions']}")
    print('Saved:',target)
    return out

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--engine',choices=['baseline','ai'],default='baseline')
    parser.add_argument('--variant',choices=['conservative','hypothesis'],default='hypothesis')
    parser.add_argument('--max-calls',type=int,default=0)
    parser.add_argument('--confirm-paid',action='store_true')
    args=parser.parse_args()
    run(args.variant,args.engine,args.max_calls,args.confirm_paid)
if __name__=='__main__':main()
