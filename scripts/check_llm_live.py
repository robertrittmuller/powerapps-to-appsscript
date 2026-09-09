"""Opt-in, one-call live LLM check; never run as part of the normal test suite.

Run with ./pfx2gas test '/app/.venv/bin/python scripts/check_llm_live.py'.
Uses the configured provider/model, checks the existing formula acceptance gate,
and executes the accepted proposal in a generated app across dates/timezones.
"""
import json
import os
from pathlib import Path

from pfx2gas.analyze import analyze
from pfx2gas.cli import _llm_fallback
from pfx2gas.ir import AppIR, ControlNode, FxExpr, ScreenNode
from pfx2gas.llm import LlmClient
from pfx2gas.startup_sim import simulate_project
from pfx2gas.synth.build import synthesize
from pfx2gas.validate import validate_project

OUT = Path('.artifacts/llm-live')


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    client = LlmClient(log_dir=OUT)
    if not client.available:
        print('LLM is not configured: set PFX2GAS_LLM_BASE_URL, PFX2GAS_LLM_API_KEY and PFX2GAS_LLM_MODEL.')
        return 1
    # One provider request, no automatic retries or long default network waits.
    client._client = client._get_client().with_options(timeout=30, max_retries=0)
    formula = 'TimeZoneOffset(Date(2026, monthNumber, 15))'
    expr = FxExpr(raw=formula)
    ir = analyze(AppIR(name='LiveLlmTimezone', start_screen='Timezone',
        on_start=FxExpr(raw='Set(monthNumber, 1)', kind='behavior'),
        screens=[ScreenNode(name='Timezone', controls=[
            ControlNode(name='Offset', type='Label', properties={'Text': expr}),
            ControlNode(name='Summer', type='Button', properties={
                'OnSelect': FxExpr(raw='Set(monthNumber, 7)', kind='behavior')})])]))
    _llm_fallback(ir, client)
    expr = ir.screens[0].controls[0].properties['Text']
    result = {'model': client.model, 'formula': formula, 'requestLimit': 1,
              'accepted': expr.translation_status == 'llm', 'cases': []}
    if result['accepted']:
        project = synthesize(ir, OUT / 'project')
        result['validation'] = validate_project(project)
        for zone, winter, summer in [('UTC', 0, 0), ('America/New_York', 300, 240),
                                     ('Europe/Berlin', -60, -120), ('Asia/Kolkata', -330, -330)]:
            os.environ['TZ'] = zone
            probe = simulate_project(project, [{'id': zone, 'steps': [
                {'action': 'expectText', 'control': 'Offset', 'equals': str(winter)},
                {'action': 'click', 'control': 'Summer'},
                {'action': 'expectText', 'control': 'Offset', 'equals': str(summer)},
            ]}])
            result['cases'].append({'timezone': zone, 'consoleErrors': probe['allConsoleErrors'],
                                    'journeys': probe['journeyResults']})
    result['status'] = 'pass' if (result['accepted'] and result['validation']['ok'] and
        all(not case['consoleErrors'] and case['journeys'][0]['status'] == 'pass' for case in result['cases'])) else 'fail'
    (OUT / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'accepted': result['accepted'], 'timezoneCases': len(result['cases'])}))
    return int(result['status'] != 'pass')


if __name__ == '__main__':
    raise SystemExit(main())
