"""Retain source-backed startup/content evidence for the pinned Modern Card app.

Run: ./pfx2gas browser scripts/assess_modern_card_workflow.py
The export is missing MyFiles. Do not inject invented document records or routes
to make its card workflow pass; retain source and renderer failures separately.
"""
import hashlib
import json
from zipfile import ZipFile

from browser_check import OUT, REPO, control, run_case
from playwright.sync_api import expect, sync_playwright
from pfx2gas.parse import parse
from pfx2gas.unpack import unpack

NAME = 'public-modern-card'
SOURCE_SHA256 = '91c3699c11e065fbaea989563213b3f21a02fb7720b3cb5c0d22aa0feabb08f0'


def source_contract(source):
    ir = parse(unpack(source))
    checker = []
    with ZipFile(source) as archive:
        for name in archive.namelist():
            if name.endswith('AppCheckerResult.sarif'):
                for run in json.loads(archive.read(name)).get('runs', []):
                    for result in run.get('results', []):
                        checker.append({key: result[key] for key in ('ruleId', 'message', 'locations') if key in result})
    controls = {ctrl.name: ctrl for screen in ir.screens for ctrl in screen.walk_controls()}
    return {
        'inputSha256': hashlib.sha256(source.read_bytes()).hexdigest(),
        'screenOrder': [screen.name for screen in ir.screens],
        'startScreenFormula': ir.properties['StartScreen'].raw,
        'onStart': ir.on_start.raw if ir.on_start else None,
        'namedFormulas': {name: expr.raw for name, expr in ir.named_formulas.items()},
        'dataSources': [{'name': ds.name, 'origin': ds.origin, 'fields': [field.name for field in ds.fields]} for ds in ir.data_sources],
        'controls': {name: {'type': controls[name].type,
                           'properties': {key: expr.raw for key, expr in controls[name].properties.items()}}
                     for name in ['Header1', 'Gallery1', 'Card1', 'Card2']},
        'exportedSourceChecker': checker,
    }


def main():
    source = REPO / 'samples/real/modern-card.msapp'
    assert hashlib.sha256(source.read_bytes()).hexdigest() == SOURCE_SHA256
    facts = source_contract(source)
    assert facts['screenOrder'] == ['Screen1', 'HomeScreen']
    assert facts['startScreenFormula'] == 'HomeScreen'
    steps = []

    def check(name, action):
        try:
            action()
            steps.append({'id': name, 'status': 'pass'})
        except Exception as error:
            steps.append({'id': name, 'status': 'fail', 'error': str(error) or type(error).__name__})

    def journey(page, _backend):
        check('authored-start-screen-visible', lambda: expect(page.locator('[data-screen="HomeScreen"]')).to_be_visible())
        check('screen-order-fallback-not-visible', lambda: expect(page.locator('[data-screen="Screen1"]')).to_be_hidden())
        check('source-documents-header-renders', lambda: expect(control(page, 'Header1')).to_contain_text('Documents', timeout=1500))
        # The missing data contract is a source failure. No successful empty
        # gallery can establish that document cards or their Launch actions work.
        def document_contract():
            assert any(ds['name'] == 'MyFiles' for ds in facts['dataSources']), (
                'Source export has no MyFiles data source or initialization; its embedded '
                'AppCheckerResult.sarif also reports MyFiles and required file fields as invalid names.')
        check('document-workflow-has-exported-data-contract', document_contract)
        page.reload()
        check('reload-preserves-authored-start-screen', lambda: expect(page.locator('[data-screen="HomeScreen"]')).to_be_visible())
        (OUT / NAME / 'source-contract.json').write_text(json.dumps(facts, indent=2) + '\n')

    with sync_playwright() as p:
        browser = p.chromium.launch()
        result = run_case(browser, NAME, source, journey)
        browser.close()
    if len(steps) != 5 or any(step['status'] != 'pass' for step in steps):
        result.update(status='fail', error='Incomplete source document contract or rendered content; see steps and source-contract.json')
    result.update(sourceAppId='modern-card', steps=steps, completeUsability='unassessed',
        assessmentScope='source-defined initial screen and header content, exported document contract and reload',
        assessmentScriptSha256=hashlib.sha256((REPO / 'scripts/assess_modern_card_workflow.py').read_bytes()).hexdigest(),
        sourceContract=facts,
        sourceLimitations=[
            'MyFiles and the file-name, author, created, thumbnail and link fields are absent; source AppChecker reports them as invalid names.',
            'There is no source navigation from HomeScreen to Screen1. The standalone Card1 content/action is not exercised.',
        ],
        remainingWorkflowChecks=['Render document cards from a complete source contract and execute their original Launch actions.',
                                 'Verify card text/images, keyboard actions and responsive geometry.'])
    (OUT / NAME / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'steps': steps}, indent=2))
    return int(result['status'] != 'pass')


if __name__ == '__main__':
    raise SystemExit(main())
