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
            ('Expired campaign',299600001), ('Future campaign',299600002)])],
    'Employee Idea Questions': [
        {'msft_employeeidea_questionid':f'question-{index}', 'msft_name':title,
         'msft_sequence':index, 'msft_employeeidea_responsetypecode':kind,
         'msft_employeeidea_campaignid':{'msft_employeeidea_campaignid':campaign}}
        for index, (title, kind, campaign) in enumerate([
            ('Who will benefit?',299600001,'campaign-1'),
            ('How would you measure success?',299600002,'campaign-1'),
            ('Question from another campaign',299600001,'campaign-0')])]}


def seed(backend):
    for source, records in RECORDS.items():
        for record in records:
            result = backend({'fn':'api','args':[source,'create',{'record':record}]})
            assert 'error' not in result, result
    return {'kind':'authored-example-records', 'records':RECORDS,
            'sha256':hashlib.sha256(json.dumps(RECORDS, sort_keys=True).encode()).hexdigest()}


def main(voting=False):
    name = NAME + ('-voting' if voting else '')
    steps = []
    def check(name, action):
        try:
            action()
            steps.append({'id':name,'status':'pass'})
        except Exception as error:
            steps.append({'id':name,'status':'fail','error':str(error)})
            raise

    def journey(page, backend):
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
        page.screenshot(path=str(OUT / name / 'active-campaigns.png'), full_page=True, timeout=10000)
        check('select-template-row', lambda: gallery.locator('[data-control="btnMobileCampaignSummary_SelectBorder"]').first.click())
        check('selected-campaign-detail', lambda: expect(control(page,'lblMobileCampaignDetail_Title')).to_have_text('Energy savings'))
        check('new-idea-action', lambda: control(page,'btnMobileCampaignIdea_Submit').click())
        check('new-idea-screen', lambda: expect(page.locator('[data-screen="Mobile Idea Screen"]')).to_be_visible())
        def usable_fields():
            fields = control(page, 'galMobileIdeaResponses').locator('[data-control="txtMobileResponseText"]')
            expect(fields).to_have_count(4)
            width = page.viewport_size['width']
            for field in fields.all():
                box = field.bounding_box()
                assert box and 0 <= box['x'] and box['x'] + box['width'] <= width, {
                    'failure':'idea field extends outside the mobile viewport', 'field':box, 'viewportWidth':width}
                expect(field).to_be_editable()
        check('idea-fields-fit-mobile-viewport', usable_fields)
        responses = control(page, 'galMobileIdeaResponses')
        check('source-field-labels', lambda: expect(responses.locator(
            '[data-control="lblMobileIdeaResponseRating_Instructions"]')).to_have_text([
                'Title','Description','Who will benefit?','How would you measure success?']))
        submit = control(page, 'btnMobileCampaignIdeaControls_Submit')
        check('empty-title-disables-submit', lambda: expect(submit).to_be_disabled())
        fields = responses.locator('[data-control="txtMobileResponseText"]')
        def field_modes():
            modes = fields.evaluate_all('els=>els.map(el=>el.tagName)')
            assert modes == ['INPUT','TEXTAREA','INPUT','TEXTAREA'], modes
        check('source-single-and-multiline-field-modes', field_modes)
        fields.nth(0).fill('Shorter meetings with written decisions')
        fields.nth(0).press('Tab')
        fields.nth(1).fill('Share an agenda, time-box discussion, and retain the decision notes.')
        fields.nth(1).press('Tab')
        fields.nth(2).fill('All meeting participants')
        fields.nth(2).press('Tab')
        fields.nth(3).fill('Track meeting hours.\nCount decisions recorded each week.')
        fields.nth(3).press('Tab')
        page.screenshot(path=str(OUT / name / 'custom-responses-entered.png'), timeout=10000)
        check('valid-title-enables-submit', lambda: expect(submit).to_be_enabled())
        check('submit-idea', lambda: submit.click())
        check('submission-success-screen', lambda: expect(page.locator('[data-screen="Mobile Success Screen"]')).to_be_visible())
        def saved_idea():
            result = backend({'fn':'api','args':['Employee Ideas','list',{}]})
            assert 'error' not in result, result
            rows = result['result']
            assert len(rows) == 1 and rows[0]['title'] == 'Shorter meetings with written decisions', rows
            assert rows[0]['description'] == 'Share an agenda, time-box discussion, and retain the decision notes.', rows
        check('generated-server-saved-idea', saved_idea)
        def saved_responses():
            result = backend({'fn':'api','args':['Employee Idea Responses','list',{}]})
            assert 'error' not in result, result
            rows = sorted(result['result'],key=lambda row:row['sequence'])
            assert len(rows) == 2, rows
            assert [row['instructions'] for row in rows] == ['Who will benefit?','How would you measure success?'], rows
            assert [row['response__text'] for row in rows] == [
                'All meeting participants','Track meeting hours.\nCount decisions recorded each week.'], rows
            assert [row['question']['employee__idea__question'] for row in rows] == ['question-0','question-1'], rows
            ideas = backend({'fn':'api','args':['Employee Ideas','list',{}]})['result']
            assert all(row['idea']['employee__idea'] == ideas[0]['employee__idea'] for row in rows), rows
        check('generated-server-saved-custom-responses', saved_responses)
        check('source-posting-failure-warning', lambda: expect(page.locator('#fx-toast')).to_contain_text('Message was not posted'))
        check('return-to-campaign', lambda: control(page,'btnMobileCampaignIdeaControls_Return').click())
        ideas = control(page,'galMobileCampaignDetailsIdeas')
        check('saved-idea-listed', lambda: expect(ideas).to_contain_text('Shorter meetings with written decisions'))
        page.reload()
        expect(page.locator('[data-screen="Mobile Landing Screen"]')).to_be_visible(timeout=10000)
        control(page,'btnMobileBrowseCampaigns').click()
        control(page,'galMobileCampaignSummary').locator('[data-control="btnMobileCampaignSummary_SelectBorder"]').first.click()
        check('saved-idea-listed-after-reload', lambda: expect(ideas).to_contain_text('Shorter meetings with written decisions'))
        check('reopen-saved-idea', lambda: ideas.locator('[data-control="btnMobileCampaignDetailIdeas_Select"]').first.click())
        check('saved-idea-detail', lambda: expect(control(page,'lblMobileCampaignIdeaCard_Title')).to_have_text('Shorter meetings with written decisions'))
        # The source deliberately exports Wrap=false and Overflow.Hidden.
        # Retain that bounded title behavior; do not credit it as full-title visibility.
        check('source-title-overflow-boundary', lambda: expect(control(page,'lblMobileCampaignIdeaCard_Title')).to_have_css('overflow','hidden'))
        check('server-record-retained-after-reload', saved_idea)
        check('custom-responses-retained-after-reload', saved_responses)
        def reopened_responses():
            expect(responses.locator('[data-control="lblMobileIdeaResponseRating_Instructions"]')).to_have_text([
                'Who will benefit?','How would you measure success?'])
            expect(fields.nth(0)).to_have_value('All meeting participants')
            expect(fields.nth(1)).to_have_value('Track meeting hours.\nCount decisions recorded each week.')
        check('reopened-custom-response-fields', reopened_responses)
        if voting:
            check('return-from-idea-to-vote', lambda: control(page,'comMobileHeader_IdeaSubmission__btnMobileHeader').click())
            vote = ideas.locator('[data-control="btnMobileCampaignDetailsIdeas_Votes"]').first
            check('initial-vote-count', lambda: expect(vote).to_have_text('0 votes'))
            try:
                check('cast-vote', lambda: vote.click())
                check('optimistic-vote-count-displayed', lambda: expect(vote).to_have_text('1 vote'))
                check('vote-server-callbacks-settle', lambda: page.wait_for_function(
                    'async () => await window.__waitForGasIdle()', timeout=10000))
                def persisted_vote():
                    records = backend({'fn':'api','args':['Employee Ideas','list',{}]})['result']
                    assert len(records) == 1, records
                    assert records[0]['vote__count'] == 1, records[0]['vote__count']
                check('vote-persisted-in-generated-server', persisted_vote)
            finally:
                (OUT / name / 'vote-records.json').write_text(json.dumps(
                    backend({'fn':'api','args':['Employee Ideas','list',{}]}), indent=2))

    with sync_playwright() as p:
        browser = p.chromium.launch()
        result = run_case(browser, name, REPO / 'samples/microsoft/employee-ideas.msapp', journey,
            launch_parameters={'hostClientType':'ios'}, viewport={'width':390,'height':844},
            solution=REPO / 'samples/microsoft/EmployeeIdeas.solution.zip', setup_backend=seed)
        browser.close()
    result.update(sourceAppId='employee-ideas', steps=steps,
        assessmentScope='populated campaign browsing, custom text questions, idea submission, reload and reopening' + ('; voting probe' if voting else ''),
        completeUsability='unassessed', mutationAndSubmission='assessed by individual steps',
        externalPosting='unsupported; source warning/recovery path is exercised')
    (OUT / name / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status':result['status'], 'steps':steps}, indent=2))
    return int(result['status'] != 'pass')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--voting', action='store_true', help='Continue into the currently unsupported voting workflow')
    raise SystemExit(main(voting=parser.parse_args().voting))
