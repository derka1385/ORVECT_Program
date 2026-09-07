"""Create a synthetic demo through the frontend proxy and verify a real Gemini run.

Run with --follow-up to also test reassessment after a new informative observation.
No credentials, VINs or real customer data are sent by this script.
"""
import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--api', default='http://127.0.0.1:3000/backend-api')
    parser.add_argument('--follow-up', action='store_true')
    parser.add_argument('--single-code', action='store_true', help='Also exercise the fast Gemini model with P0301 alone')
    args = parser.parse_args()
    def call(path, payload=None):
        request = Request(args.api + path, data=json.dumps(payload).encode() if payload is not None else None,
                          headers={'Content-Type': 'application/json'})
        with urlopen(request, timeout=240) as response:
            return json.load(response)
    fixture = json.loads((ROOT / 'frontend/public/demo/golf-misfire.json').read_text())
    if args.single_code:
        fixture['fault_codes'] = fixture['fault_codes'][:1]
    preview = call('/diagnostics/dtc-preview', {key:fixture[key] for key in ('vehicle_id','fault_codes')})
    assert all(item['documented'] for item in preview['items']), preview
    case = call('/diagnostics', {key:fixture[key] for key in ('vehicle_id','mileage','symptoms','circumstances')})
    path = '/diagnostics/' + case['id']
    print(json.dumps({'created_case':case['id'], 'url':'http://127.0.0.1:3000/diagnostics/ai/' + case['id']}), flush=True)
    call(path + '/fault-codes', {'fault_codes':fixture['fault_codes']})
    for measurement in fixture['measurements']:
        call(path + '/measurements', measurement)
    analysis = call(path + '/analyze', {})
    detail = call(path)
    assert detail['case']['ai_model'].startswith('gemini-'), detail['case']['ai_model']
    assert analysis['hypotheses'], 'Gemini returned no hypothesis for the documented demonstration'
    assert analysis['nextChecks'], 'No guided check returned'
    assert analysis['safetyAssessment']['decisionSource'] == 'safety_engine'
    print(json.dumps({'phase':'initial','model':detail['case']['ai_model'], 'hypotheses':[h['label'] for h in analysis['hypotheses']], 'next_check':analysis['nextChecks'][0]['title']}, ensure_ascii=False), flush=True)
    if args.follow_up:
        current = next(step for step in detail['steps'] if step['status']=='current')
        call(path + '/steps/' + current['id'] + '/result', {'state':'unavailable','outcome':'Contrôle indisponible dans cette démonstration','comment':'Simulation'})
        unchanged = call(path + '/reanalyze', {})
        assert unchanged == analysis, 'An unavailable test must not change the analysis'
        print('PASS: unavailable test preserves hypotheses', flush=True)
        # An added measurement is independent of the LLM-selected current check.
        call(path + '/measurements', {'name':'Inspection visuelle connecteur bobine cylindre 1', 'value':'SIMULATION : verrou cassé, connecteur partiellement débranché ; aucun remplacement effectué', 'unit':None, 'conditions':'Observation synthétique contact coupé, moteur refroidi', 'source':'manual'})
        updated = call(path + '/reanalyze', {})
        assert updated['hypotheses'] and updated['nextChecks']
        assert updated != analysis, 'New evidence did not change the analysis'
        print(json.dumps({'phase':'follow_up','hypotheses':[h['label'] for h in updated['hypotheses']], 'next_check':updated['nextChecks'][0]['title']}, ensure_ascii=False), flush=True)
    print('PASS: real Gemini, catalogue, persistence and frontend proxy', flush=True)

if __name__ == '__main__':
    main()
