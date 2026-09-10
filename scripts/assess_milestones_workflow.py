"""Unchanged Microsoft Milestones onboarding with authored Google user migration.

Runs generated Code.gs and UI with explicit People API fixtures. This records
partial workflow evidence, not live Google authorization or complete usability.
Run: ./pfx2gas browser scripts/assess_milestones_workflow.py
"""
import hashlib
import json

from browser_check import OUT, REPO, control, run_case
from playwright.sync_api import expect, sync_playwright

NAME='milestones-populated'
DIRECTORY=json.loads((REPO/'tests/fixtures/google-directory.json').read_text())
USERS=[{'systemuserid':mapping['id'],'internalemailaddress':mapping['google_email'],
        'fullname':person['names'][0]['displayName']}
       for mapping,person in zip(DIRECTORY['migration']['users'],DIRECTORY['people'])]


def seed(backend):
    for record in USERS:
        result=backend({'fn':'api','args':['Users','create',{'record':record}]})
        assert 'error' not in result,result
    result=backend({'fn':'__importDirectory','args':[DIRECTORY['migration']]})
    assert result=={'result':{'ok':True,'users':2}},result
    return {'kind':'authored-example-records','records':{'Users':USERS},
            'directoryMigration':DIRECTORY['migration'],
            'sha256':hashlib.sha256(json.dumps([USERS,DIRECTORY],sort_keys=True).encode()).hexdigest(),
            'googlePeople':'explicit native API fixtures; no live Google authorization'}


def main(project=False):
    name=NAME+('-project' if project else '')
    steps=[]
    def check(name,action):
        try:
            action();steps.append({'id':name,'status':'pass'})
        except Exception as error:
            steps.append({'id':name,'status':'fail','error':str(error)});raise
    def journey(page,backend):
        page.set_default_timeout(5000)
        def snapshot():
            records={source:backend({'fn':'api','args':[source,'list',{}]})
                     for source in ['Project User Settings','Projects','Project Team Members','Project Milestones']}
            (OUT/name/'saved-records.json').write_text(json.dumps(records,indent=2)+'\n')
        try:
            check('source-loading-transition',lambda:expect(page.locator('[data-screen="Projects Screen"]')).to_be_visible(timeout=10000))
            check('first-run-welcome',lambda:expect(control(page,'conDialogFirstRun')).to_be_visible())
            page.screenshot(path=str(OUT/name/'first-run.png'),full_page=True)
            check('continue-onboarding',lambda:control(page,'btnCustomize_Continue').click())
            check('platform-introduction',lambda:expect(control(page,'conDialogSplash_PowerApps')).to_be_visible())
            check('remember-dismissal',lambda:control(page,'chkSplashPowerApps_DoNotShowAgain').check())
            check('dismiss-introduction',lambda:control(page,'btnSplashPowerApps_Proceed').click())
            check('onboarding-dismissed',lambda:expect(control(page,'conDialogWelcome')).to_be_hidden())
            snapshot()
            page.reload()
            check('reload-projects',lambda:expect(page.locator('[data-screen="Projects Screen"]')).to_be_visible(timeout=10000))
            check('welcome-stays-dismissed',lambda:expect(control(page,'conDialogWelcome')).to_be_hidden())
            def single_settings():
                records=backend({'fn':'api','args':['Project User Settings','list',{}]})['result']
                assert len(records)==1,records
                assert records[0]['owner']['systemuserid']=='user-a',records
                assert records[0]['owninguser']['systemuserid']=='user-a',records
                assert records[0]['msft_isdisplaysplashpowerapps'] is False,records
            check('one-settings-record-after-reload',single_settings)
            backend({'fn':'__setStorageIdentity','args':['milestones-test-app','second@example.test']})
            page.reload()
            check('second-user-projects',lambda:expect(page.locator('[data-screen="Projects Screen"]')).to_be_visible(timeout=10000))
            check('second-user-first-run',lambda:expect(control(page,'conDialogFirstRun')).to_be_visible())
            check('second-user-continue',lambda:control(page,'btnCustomize_Continue').click())
            check('second-user-remember-dismissal',lambda:control(page,'chkSplashPowerApps_DoNotShowAgain').check())
            check('second-user-dismiss',lambda:control(page,'btnSplashPowerApps_Proceed').click())
            check('second-user-onboarding-dismissed',lambda:expect(control(page,'conDialogWelcome')).to_be_hidden())
            backend({'fn':'__setStorageIdentity','args':['milestones-test-app','business.tester@example.test']})
            page.reload()
            check('first-user-returns',lambda:expect(page.locator('[data-screen="Projects Screen"]')).to_be_visible(timeout=10000))
            check('first-user-dismissal-retained',lambda:expect(control(page,'conDialogWelcome')).to_be_hidden())
            def separate_settings():
                records=backend({'fn':'api','args':['Project User Settings','list',{}]})['result']
                assert len(records)==2,records
                assert [record['owner']['systemuserid'] for record in records]==['user-a','user-b'],records
                assert all(record['msft_isdisplaysplashpowerapps'] is False for record in records),records
            check('separate-persisted-user-settings',separate_settings)
            page.screenshot(path=str(OUT/name/'returning-user.png'),full_page=True)
            if project:
                ada=DIRECTORY['people'][0]
                response={'method':'get','args':['people/100',{'personFields':'metadata,names,emailAddresses,organizations,phoneNumbers,locations,photos',
                          'sources':['READ_SOURCE_TYPE_PROFILE']}],'result':ada}
                backend({'fn':'__peopleResponses','args':[[response,response]]})
                check('new-project-action',lambda:control(page,'btnNewProject').click())
                check('new-project-screen',lambda:expect(page.locator('[data-screen="Add Project Screen"]')).to_be_visible())
                check('empty-name-cannot-continue',lambda:expect(control(page,'btnNextNewProjectMilestones')).to_be_disabled())
                check('three-default-milestones',lambda:expect(control(page,'txtAddMilestoneName')).to_have_count(3))
                control(page,'txtNewProjectName').fill('Facilities renewal')
                for index,title in enumerate(['Survey site','Replace equipment','Review handover']):
                    control(page,'txtAddMilestoneName').nth(index).fill(title)
                page.screenshot(path=str(OUT/name/'project-draft.png'),full_page=True)
                check('next-to-team-assignment',lambda:control(page,'btnNextNewProjectMilestones').click())
                check('create-action-visible',lambda:expect(control(page,'btnCreateProject')).to_be_visible())
                backend({'fn':'__peopleResponses','args':[[response]]})
                check('create-project',lambda:control(page,'btnCreateProject').click())
                check('return-to-projects',lambda:expect(page.locator('[data-screen="Projects Screen"]')).to_be_visible())
                check('project-callbacks-settle',lambda:page.wait_for_function('async()=>await window.__waitForGasIdle()',timeout=10000))
                def project_records():
                    projects=backend({'fn':'api','args':['Projects','list',{}]})['result']
                    milestones=backend({'fn':'api','args':['Project Milestones','list',{}]})['result']
                    members=backend({'fn':'api','args':['Project Team Members','list',{}]})['result']
                    assert len(projects)==1 and projects[0]['msft_name']=='Facilities renewal',[(r['id'],r['msft_name']) for r in projects]
                    assert len(members)==1 and members[0]['msft_name']=='Ada Lovelace',[(r['id'],r['msft_name']) for r in members]
                    assert [row['msft_name'] for row in milestones]==['Survey site','Replace equipment','Review handover'],{
                        'milestones':[{'id':r['id'],'name':r['msft_name'],'date':r['msft_milestonedate'],'color':r['msft_color']} for r in milestones]}
                check('distinct-milestone-edits-persist',project_records)
        finally:
            snapshot()
            if project:
                trace={key:backend({'fn':fn,'args':[]}) for key,fn in
                       [('peopleRequests','__peopleRequests'),('connectorRequests','__connectorRequests')]}
                (OUT/name/'native-directory-evidence.json').write_text(json.dumps(trace,indent=2)+'\n')
    with sync_playwright() as p:
        browser=p.chromium.launch()
        result=run_case(browser,name,REPO/'samples/microsoft/milestones.msapp',journey,
            solution=REPO/'samples/microsoft/Milestones.solution.zip',setup_backend=seed)
        browser.close()
    result.update(sourceAppId='milestones',steps=steps,assessmentScope='first-run onboarding and persisted settings across two simulated Google users'+('; project creation probe' if project else ''),
                  completeUsability='unassessed')
    (OUT/name/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'steps':steps},indent=2))
    return int(result['status']!='pass')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',action='store_true',help='Continue through the original project creation workflow')
    raise SystemExit(main(project=parser.parse_args().project))
