"""First-action probes for real Microsoft exports, retaining workflow failures.

These are partial workflow checks, not whole-app usability acceptance. They
execute source initialization, timers and button formulas without overriding
state, navigating directly or substituting successful connector responses.
Run with ./pfx2gas browser scripts/assess_microsoft_workflows.py.
"""
import json

from browser_check import OUT, REPO, control, run_case
from playwright.sync_api import expect, sync_playwright

# These destinations/actions are taken from the release-44 source formulas.
# Milestones defaults to desktop. Employee Ideas also defaults to desktop;
# its mobile entry is explicitly selected by the source's Teams launch parameter.
CASES = [
    ('milestones', 'Projects Screen', 'btnNewProject', 'Add Project Screen'),
    ('employee-ideas', 'Mobile Landing Screen', 'btnMobileBrowseCampaigns', 'Mobile Campaign Summary Screen'),
    ('inspection', 'Welcome Screen', 'btnInspect', 'Items Screen'),
]


def main():
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for app, loaded_screen, primary, destination in CASES:
            name = 'microsoft-first-action-' + app
            steps = []
            def check(step, action):
                try:
                    action()
                    steps.append({'id': step, 'status': 'pass'})
                except Exception as error:
                    steps.append({'id': step, 'status': 'fail', 'error': str(error)})

            def journey(page, _backend):
                if app == 'employee-ideas':
                    check('source-desktop-loading-transition', lambda: expect(
                        page.locator('[data-screen="Campaign Summary Screen"]')).to_be_visible(timeout=10000))
                    check('source-unchecked-mobile-toggle', lambda: expect(control(page, 'tglAdmin_Mobile')).not_to_be_checked())
                    check('desktop-screenshot', lambda: page.screenshot(
                        path=str(OUT / name / 'desktop-loaded.png'), full_page=True, timeout=10000))
                    page.set_viewport_size({'width': 390, 'height': 844})
                    page.goto('https://converted.test/?hostClientType=ios')
                check('source-loading-transition', lambda: expect(
                    page.locator(f'[data-screen="{loaded_screen}"]')).to_be_visible(timeout=10000))
                # Retain capture failures while still exercising the remaining
                # source actions; a diagnostic screenshot must not skip them.
                check('loaded-screenshot', lambda: page.screenshot(
                    path=str(OUT / name / 'loaded.png'), full_page=True, timeout=10000))
                if app == 'milestones':
                    # Loading.Navigate passes locShowFirstRun to Projects.
                    # Preserve and exercise this onboarding instead of clicking
                    # through its modal overlay or injecting a dismissed state.
                    check('source-first-run-welcome', lambda: expect(control(page, 'conDialogFirstRun')).to_be_visible())
                    check('source-first-run-continue', lambda: control(page, 'btnCustomize_Continue').click(timeout=5000))
                    check('source-platform-introduction', lambda: expect(control(page, 'conDialogSplash_PowerApps')).to_be_visible())
                    check('source-platform-introduction-dismiss', lambda: control(page, 'btnSplashPowerApps_Proceed').click(timeout=5000))
                    check('source-first-run-dismissed', lambda: expect(control(page, 'conDialogWelcome')).to_be_hidden())
                button = control(page, primary)
                def readable():
                    expect(button).to_be_visible()
                    geometry = button.evaluate('''el => ({width:el.clientWidth,height:el.clientHeight,
                      textWidth:el.scrollWidth,textHeight:el.scrollHeight,text:el.textContent})''')
                    assert geometry['textWidth'] <= geometry['width'] and geometry['textHeight'] <= geometry['height'], geometry
                check('primary-action-readable', readable)
                check('primary-action-click', lambda: button.click(timeout=5000))
                check('source-action-destination', lambda: expect(
                    page.locator(f'[data-screen="{destination}"]')).to_be_visible(timeout=5000))
                # Allow already dispatched async connector failures to surface.
                page.wait_for_timeout(200)
                failed = [step['id'] for step in steps if step['status'] == 'fail']
                assert not failed, failed

            template = {'milestones': 'Milestones', 'employee-ideas': 'EmployeeIdeas', 'inspection': 'Inspection'}[app]
            result = run_case(browser, name, REPO / 'samples/microsoft' / (app + '.msapp'), journey,
                              solution=REPO / 'samples/microsoft' / (template + '.solution.zip'))
            result.update(sourceAppId=app, assessmentScope='source loading and first action only',
                          completeUsability='unassessed', steps=steps)
            (OUT / name / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
            results.append(result)
        browser.close()
    destination = REPO / '.artifacts/microsoft/first-actions.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(results, indent=2) + '\n')
    return int(any(result['status'] != 'pass' for result in results))


if __name__ == '__main__':
    raise SystemExit(main())
