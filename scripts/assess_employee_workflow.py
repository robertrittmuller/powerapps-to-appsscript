"""Populated Microsoft Employee Ideas campaign-to-submission probe.

Uses the unmodified release-44 app and its saved views, with explicitly
authored migration records written through generated Code.gs before startup.
This is partial workflow evidence, never whole-app usability acceptance.
Run: ./pfx2gas browser scripts/assess_employee_workflow.py
"""
import hashlib
import json

from browser_check import OUT, REPO, control, run_case
from playwright.sync_api import expect, sync_playwright

NAME = 'employee-populated'
RECORDS = {'Users': [{'systemuserid':'test-source-user',
    'internalemailaddress':'business.tester@example.test', 'fullname':'Business Tester'}],
    'Employee Idea Campaigns': [
        {'msft_employeeidea_campaignid':f'campaign-{index}', 'msft_name':title,
         'msft_description':title + ' description', 'msft_calc_employeeidea_campaignstatuscode':status,
         'msft_campaignstartdate':'2026-09-01T00:00:00Z', 'msft_campaignenddate':'2026-10-01T00:00:00Z',
         'createdon':f'2026-09-0{index + 1}T00:00:00Z'}
        for index, (title, status) in enumerate([
            ('Better meetings',299600000), ('Energy savings',299600000),
            ('Expired campaign',299600001), ('Future campaign',299600002)])]}


def seed(backend):
    for source, records in RECORDS.items():
        for record in records:
            result = backend({'fn':'api','args':[source,'create',{'record':record}]})
            assert 'error' not in result, result
    return {'kind':'authored-example-records', 'records':RECORDS,
            'sha256':hashlib.sha256(json.dumps(RECORDS, sort_keys=True).encode()).hexdigest()}


def main():
    steps = []
    def check(name, action):
        try:
            action()
            steps.append({'id':name,'status':'pass'})
        except Exception as error:
            steps.append({'id':name,'status':'fail','error':str(error)})
            raise

    def journey(page, _backend):
        page.set_default_timeout(5000)
        check('source-mobile-startup', lambda: expect(page.locator(
            '[data-screen="Mobile Landing Screen"]')).to_be_visible(timeout=10000))
        check('browse-campaigns', lambda: control(page,'btnMobileBrowseCampaigns').click())
        gallery = control(page,'galMobileCampaignSummary')
        titles = gallery.locator('[data-control="lblMobileCampaignSummary_Title"]')
        check('active-view-filter-and-order', lambda: expect(titles).to_have_text(['Energy savings','Better meetings']))
        search = control(page, 'txtMobileCampaignSummary_Search')
        search.fill('meetings')
        check('campaign-search', lambda: expect(titles).to_have_text(['Better meetings']))
        search.fill('')
        expect(titles).to_have_count(2)
        page.screenshot(path=str(OUT / NAME / 'active-campaigns.png'), full_page=True, timeout=10000)
        check('select-template-row', lambda: gallery.locator('[data-control="btnMobileCampaignSummary_SelectBorder"]').first.click())
        check('selected-campaign-detail', lambda: expect(control(page,'lblMobileCampaignDetail_Title')).to_have_text('Energy savings'))
        check('new-idea-action', lambda: control(page,'btnMobileCampaignIdea_Submit').click())
        check('new-idea-screen', lambda: expect(page.locator('[data-screen="Mobile Idea Screen"]')).to_be_visible())
        def usable_fields():
            fields = control(page, 'galMobileIdeaResponses').locator('[data-control="txtMobileResponseText"]')
            expect(fields).to_have_count(2)
            width = page.viewport_size['width']
            for field in fields.all():
                box = field.bounding_box()
                assert box and 0 <= box['x'] and box['x'] + box['width'] <= width, {
                    'failure':'idea field extends outside the mobile viewport', 'field':box, 'viewportWidth':width}
                expect(field).to_be_editable()
        check('idea-fields-fit-mobile-viewport', usable_fields)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        result = run_case(browser, NAME, REPO / 'samples/microsoft/employee-ideas.msapp', journey,
            launch_parameters={'hostClientType':'ios'}, viewport={'width':390,'height':844},
            solution=REPO / 'samples/microsoft/EmployeeIdeas.solution.zip', setup_backend=seed)
        browser.close()
    result.update(sourceAppId='employee-ideas', steps=steps,
        assessmentScope='populated campaign browsing, selection and new-idea form access',
        completeUsability='unassessed', mutationAndSubmission='unassessed')
    (OUT / NAME / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status':result['status'], 'steps':steps}, indent=2))
    return int(result['status'] != 'pass')


if __name__ == '__main__':
    raise SystemExit(main())
