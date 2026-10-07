"""Capture one authored journey against both real apps in Docker Chromium.

Uses explicit source/target locators and assertions; does not invent app actions.
Sessions and captures belong in gitignored .artifacts, never in the manifest.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import sync_playwright, expect
from pfx2gas.benchmark import converter_fingerprint
from pfx2gas.comparison import compare_captures, equivalent, validate_comparison_evidence


def capture(browser, plan, side, output):
    contexts, pages = {}, {}
    observed, errors, steps, screenshots = [], [], [], []
    shared = plan['context']
    for actor in plan['actors']:
        options = dict(viewport=shared['viewport'],locale=shared['locale'],timezone_id=shared['timezone'])
        if actor.get('sessions',{}).get(side):
            options['storage_state'] = actor['sessions'][side]
        contexts[actor['id']] = browser.new_context(**options)
        contexts[actor['id']].set_default_timeout(plan.get('timeoutMs',15000))
        pages[actor['id']] = contexts[actor['id']].new_page()
        pages[actor['id']].on('pageerror',lambda error: errors.append(str(error)))
        pages[actor['id']].goto(plan[side+'Url'],wait_until='domcontentloaded')
    try:
        for step in plan['steps']:
            page = pages[step['actor']]
            try:
                action = step['action']
                locator = None
                if 'locators' in step:
                    spec = step['locators'][side]
                    frame = page
                    if isinstance(spec,dict):
                        for selector in spec.get('frames',[]): frame = frame.frame_locator(selector)
                        spec = spec['selector']
                    locator = frame.locator(spec)
                if action == 'navigate':
                    page.goto(urljoin(plan[side+'Url'],step['path']),wait_until='domcontentloaded')
                elif action == 'reload': page.reload(wait_until='domcontentloaded')
                elif action == 'click': locator.click()
                elif action == 'fill': locator.fill(step['value'])
                elif action == 'press': locator.press(step['key'])
                elif action == 'select': locator.select_option(label=step['value'])
                elif action == 'screenshot':
                    file = output/(side+'-'+step['id']+'.png')
                    page.screenshot(path=str(file),full_page=True)
                    screenshots.append({'step':step['id'],'file':str(file),'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
                elif action == 'observe':
                    kind = step.get('read','text')
                    if kind != 'count': locator.first.wait_for(state='visible')
                    if kind == 'text':
                        expect(locator).to_have_text(step['expected']); value = locator.inner_text()
                    elif kind == 'value':
                        expect(locator).to_have_value(step['expected']); value = locator.input_value()
                    elif kind == 'count':
                        expect(locator).to_have_count(step['expected']); value = locator.count()
                    elif kind == 'attribute':
                        expect(locator).to_have_attribute(step['attribute'],step['expected']); value = locator.get_attribute(step['attribute'])
                    elif kind == 'geometry': value = locator.bounding_box()
                    else: raise ValueError('Unsupported observation type: ' + kind)
                    expected = step['expected']
                    tolerance = step.get('tolerance',0)
                    passed = equivalent(expected,value,tolerance)
                    observed.append({'id':step['id'],'journey':step['journey'],'value':value,'expected':expected,
                                     'tolerance':tolerance,'status':'pass' if passed else 'fail'})
                    if not passed: errors.append('Expected observation failed: ' + step['id'])
                else: raise ValueError('Unsupported action: ' + action)
                steps.append({'id':step['id'],'actor':step['actor'],'action':action,'status':'pass'})
            except Exception as exc:
                errors.append(step['id'] + ': ' + str(exc))
                steps.append({'id':step['id'],'actor':step['actor'],'action':step['action'],'status':'fail'})
                break
        for actor,page in pages.items():
            file = output/(side+'-'+actor+'.png')
            page.screenshot(path=str(file),full_page=True)
            screenshots.append({'file':str(file),'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
        return {'side':side,'status':'fail' if errors else 'pass','errors':errors,'url':plan[side+'Url'],
                'inputSha256':plan['inputSha256'],'solutionSha256':plan.get('solutionSha256'),'converterSourceSha256':converter_fingerprint(),
                'capturePlanSha256':plan['capturePlanSha256'],'context':shared,
                'journeys':list(dict.fromkeys(row['journey'] for row in observed)),
                'steps':steps,'observations':observed,'screenshots':screenshots,'browserVersion':browser.version}
    finally:
        for context in contexts.values(): context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--allow-writes',action='store_true',help='Authorize authored interactions that may mutate the source and target apps')
    parser.add_argument('--live-google',action='store_true',help='Also require live persistence, permissions, failures and concurrent-user checks')
    args = parser.parse_args()
    raw = Path(args.plan).read_bytes()
    plan = json.loads(raw)
    if plan.get('schemaVersion') != 1 or not plan.get('steps') or not plan.get('actors'):
        raise ValueError('A versioned capture plan, actors and steps are required')
    if any(step['action'] not in {'navigate','reload','observe','screenshot'} for step in plan['steps']) and not args.allow_writes:
        raise ValueError('Interactive actions require --allow-writes; they can mutate both real apps')
    ids = [step['id'] for step in plan['steps']]
    if len(ids) != len(set(ids)): raise ValueError('Step IDs must be unique')
    actor_ids = [actor['id'] for actor in plan['actors']]
    if len(actor_ids) != len(set(actor_ids)) or any(step['actor'] not in actor_ids for step in plan['steps']):
        raise ValueError('Unique actors and valid step actors are required')
    import re
    if any(not re.fullmatch(r'[A-Za-z0-9_-]+',key) for key in ids+actor_ids):
        raise ValueError('Step and actor IDs must use letters, numbers, hyphens or underscores')
    source = Path(plan['sourceExport'])
    plan['inputSha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    if plan.get('solutionExport'):
        plan['solutionSha256'] = hashlib.sha256(Path(plan['solutionExport']).read_bytes()).hexdigest()
    plan['capturePlanSha256'] = hashlib.sha256(raw).hexdigest()
    plan['context']['roles'] = [actor['role'] for actor in plan['actors']]
    output = Path(args.output)
    output.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            source_capture = capture(browser,plan,'source',output)
            target_capture = capture(browser,plan,'target',output)
        finally: browser.close()
    for side,data in [('source',source_capture),('target',target_capture)]:
        (output/(side+'-capture.json')).write_text(json.dumps(data,indent=2)+'\n')
    proof = compare_captures(source_capture,target_capture)
    try:
        validate_comparison_evidence(proof,plan['inputSha256'],converter_fingerprint(),required_journeys=plan['journeys'])
    except ValueError as exc:
        proof['status'] = 'fail'
        proof['errors'].append(str(exc))
    (output/'sourceComparison.json').write_text(json.dumps(proof,indent=2)+'\n')
    failed = proof['status'] != 'pass'
    if args.live_google:
        live = {'schemaVersion':1,'kind':'live-google','status':target_capture['status'],'target':target_capture,
                'inputSha256':plan['inputSha256'],'converterSourceSha256':converter_fingerprint(),
                'journeys':target_capture['journeys'],'deploymentVersion':plan.get('deploymentVersion'),
                'usesMocks':False}
        try:
            validate_comparison_evidence(live,plan['inputSha256'],converter_fingerprint(),live=True,required_journeys=plan['journeys'],required_live_checks=plan.get('liveChecks'))
        except ValueError as exc:
            live.update(status='fail',errors=[str(exc)])
            failed = True
        (output/'liveGoogle.json').write_text(json.dumps(live,indent=2)+'\n')
    print(json.dumps({'status':'fail' if failed else 'pass','errors':proof['errors'],'output':str(output)},indent=2))
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
