"""Source-action browser checks for the pinned public canvas app corpus.

These are real app workflows, not complete usability or original-UI comparisons.
Run: ./pfx2gas browser scripts/assess_public_workflows.py
"""
import json

from playwright.sync_api import sync_playwright, expect
from browser_check import OUT, REPO, control, run_case


def main():
    name = 'public-expandable-nav'
    steps = []

    def check(step_id, action):
        try:
            action()
            steps.append({'id': step_id, 'status': 'pass'})
        except Exception as error:
            steps.append({'id': step_id, 'status': 'fail', 'error': str(error)})
            raise

    def journey(page, _backend):
        check('source-home-screen', lambda: expect(page.locator('[data-screen="HomeScreen"]')).to_be_visible())

        def named_menu_data():
            page.wait_for_function('state.NavStructure && state.NavStructure.length === 4')
            assert page.evaluate('state.NavStructure.map(row => row.title)') == ['Home', 'Work', 'Admin', 'Logout']

        check('source-named-menu-data', named_menu_data)
        check('source-menu-visible', lambda: expect(control(page, 'NavComponent_1__ButtonCanvas1'))
              .to_have_text(['Home', 'Work', 'Admin', 'Logout']))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        result = run_case(browser, name, REPO/'samples/real/expandable-nav.msapp', journey)
        browser.close()
    result.update(sourceAppId='expandable-nav', steps=steps, completeUsability='unassessed',
                  assessmentScope='source navigation component menu and destinations')
    (OUT/name/'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'steps': steps}, indent=2))
    return int(result['status'] != 'pass')


if __name__ == '__main__':
    raise SystemExit(main())
