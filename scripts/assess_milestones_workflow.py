"""Unchanged Microsoft Milestones onboarding with authored Google user migration.

Runs generated Code.gs and UI with explicit People API fixtures. This records
partial workflow evidence, not live Google authorization or complete usability.
Run: ./pfx2gas browser scripts/assess_milestones_workflow.py
"""
import hashlib
import json
import time

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


def main(project=False,workitem=False,settings=False,filters=False):
    settings=settings or filters
    workitem=workitem or settings
    project=project or workitem
    name=NAME+('-filters' if filters else '-settings' if settings else '-workitem' if workitem else '-project' if project else '')
    steps=[]
    def check(name,action):
        try:
            action();steps.append({'id':name,'status':'pass'})
        except Exception as error:
            steps.append({'id':name,'status':'fail','error':str(error)});raise
    def journey(page,backend):
        page.set_default_timeout(5000)
        def snapshot():
            sources=['Project User Settings','Projects','Project Team Members','Project Milestones']
            if workitem:
                sources+=['Project Work Items','Project Work Item Statuses','Project Work Item Categories','Project Work Item Priorities']
            records={source:backend({'fn':'api','args':[source,'list',{}]}) for source in sources}
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
            if settings:
                check('open-global-settings',lambda:control(page,'imgProjectsGlobalSettings').click())
                check('global-settings-screen',lambda:expect(page.locator('[data-screen="Global Settings Screen"]')).to_be_visible())
                settings_save=control(page,'btnSave_GlobalSettings')
                check('unchanged-settings-disable-save',lambda:expect(settings_save).to_be_disabled())
                specs=[('Category','Categories',['Facilities']),('Priority','Priorities',['High']),
                       ('Status','Statuses',['Done','Not started','In progress'])]
                for kind,plural,names in specs:
                    for label in names:
                        check('add-'+kind.lower()+'-'+label,lambda kind=kind:control(page,'btnAdd'+kind).click())
                        check('blank-'+kind.lower()+'-'+label+'-disables-save',lambda:expect(settings_save).to_be_disabled())
                        inputs=control(page,'gal'+plural).locator('[data-control="txt'+kind+'Name"]')
                        inputs.last.fill(label)
                        inputs.last.press('Tab')
                        check('enter-'+kind.lower()+'-'+label,lambda inputs=inputs,label=label:expect(inputs.last).to_have_value(label))
                check('valid-settings-enable-save',lambda:expect(settings_save).to_be_enabled())
                check('source-status-titles',lambda:expect(control(page,'galStatuses').locator('[data-control="lblStatusTitle"]')).to_have_text(
                    ['Completion status','Optional status 1','Optional status 2']))
                page.screenshot(path=str(OUT/name/'settings-draft.png'),full_page=True)
                check('save-global-settings',lambda:settings_save.click())
                check('settings-callbacks-settle',lambda:page.wait_for_function('async()=>await window.__waitForGasIdle()',timeout=10000))
                def settings_records():
                    records={}
                    for _kind,plural,names in specs:
                        source='Project Work Item '+plural
                        rows=backend({'fn':'api','args':[source,'list',{}]})['result']
                        records[source]=rows
                        assert [row['msft_name'] for row in rows]==names,{'source':source,'names':[row['msft_name'] for row in rows]}
                        assert all(row['statecode']==0 and row['statuscode']==1 for row in rows)
                        if plural=='Statuses':
                            # The unchanged Save formula supplies no Sequence.
                            assert all(row['msft_sequence'] is None for row in rows)
                    (OUT/name/'configured-settings.json').write_text(json.dumps(records,indent=2)+'\n')
                check('configured-settings-persist',settings_records)
                check('return-after-settings',lambda:control(page,'btnCancel_GlobalSettings').click())
                expect(page.locator('[data-screen="Projects Screen"]')).to_be_visible()
                page.reload()
                expect(page.locator('[data-screen="Projects Screen"]')).to_be_visible(timeout=10000)
                check('reopen-global-settings',lambda:control(page,'imgProjectsGlobalSettings').click())
                expect(page.locator('[data-screen="Global Settings Screen"]')).to_be_visible()
                for kind,plural,names in specs:
                    def restored_settings(kind=kind,plural=plural,names=names):
                        inputs=control(page,'gal'+plural).locator('[data-control="txt'+kind+'Name"]')
                        expect(inputs).to_have_count(len(names))
                        # Active Project Work Item Statuses orders by Name in
                        # the exported savedquery b478c817-ce45-459c-85a7-5da2bdbc9c5a.
                        # OnVisible's subsequent Sort(Sequence) ties because Save
                        # never writes that field. Input order was not a source
                        # contract; do not invent sequence values to retain it.
                        restored_names=sorted(names) if kind=='Status' else names
                        for index,label in enumerate(restored_names):
                            expect(inputs.nth(index)).to_have_value(label)
                    check('restored-'+plural.lower(),restored_settings)
                page.screenshot(path=str(OUT/name/'settings-reloaded.png'),full_page=True)
                control(page,'btnCancel_GlobalSettings').click()
                expect(page.locator('[data-screen="Projects Screen"]')).to_be_visible()
            if project:
                ada=DIRECTORY['people'][0]
                response={'method':'get','args':['people/100',{'personFields':'metadata,names,emailAddresses,organizations,phoneNumbers,locations,photos',
                          'sources':['READ_SOURCE_TYPE_PROFILE']}],'result':ada}
                backend({'fn':'__peopleResponses','args':[[response,response]]})
                check('new-project-action',lambda:control(page,'btnNewProject').click())
                check('new-project-screen',lambda:expect(page.locator('[data-screen="Add Project Screen"]')).to_be_visible())
                check('empty-name-cannot-continue',lambda:expect(control(page,'btnNextNewProjectMilestones')).to_be_disabled())
                check('three-default-milestones',lambda:expect(control(page,'txtAddMilestoneName')).to_have_count(3))
                def default_dates():
                    dates=control(page,'datMilestoneTargetDate')
                    expect(dates).to_have_count(3)
                    for index,value in enumerate(['2026-03-01','2026-03-08','2026-03-15']):
                        expect(dates.nth(index)).to_be_visible()
                        expect(dates.nth(index)).to_have_value(value)
                check('weekly-default-date-inputs',default_dates)
                def edit_dates():
                    dates=control(page,'datMilestoneTargetDate')
                    dates.nth(1).fill('2026-03-10')
                    dates.nth(2).fill('2026-03-20')
                check('edit-independent-milestone-dates',edit_dates)
                def default_colors():
                    selected=page.evaluate("""() => [...document.querySelector('[data-control="galAddMilestones"]').querySelector(':scope > .fx-rows').children]
                        .map(row => FXRuntime.rowValue(row, 'galMilestoneColorPicker').selected.color)""")
                    assert selected==['#5AC6CC','#C5E9EA','#F0F9FA'],selected
                check('source-default-color-selections',default_colors)
                check('open-second-color-picker',lambda:control(page,'btnMilestoneColor').nth(1).click())
                picker=control(page,'galMilestoneColorPicker').nth(1)
                check('second-color-picker-visible',lambda:expect(picker).to_be_visible())
                def choose_color():
                    button=picker.locator('[data-control="btnColorPreview"]').filter(has_text='#F4B9B9')
                    picker.evaluate('''host=>{window.__colorClicks=[];host.addEventListener('click',event=>{
                        const row=event.target.closest('.fx-row');
                        const record={target:event.target.dataset.control,item:row&&row.__fxItem,before:host.__fxValues.selected,
                            x:event.clientX,y:event.clientY,scroll:host.scrollLeft,rect:event.target.getBoundingClientRect().toJSON()};
                        window.__colorClicks.push(record);
                    },true);}''')
                    evidence={'before':button.evaluate('el=>({text:el.textContent,item:el.closest(".fx-row").__fxItem,rect:el.getBoundingClientRect().toJSON()})')}
                    evidence['geometry']=picker.evaluate('el=>({scroll:el.scrollLeft,host:el.getBoundingClientRect().toJSON(),buttons:[...el.querySelectorAll("button")].map(btn=>({text:btn.textContent,rect:btn.getBoundingClientRect().toJSON(),width:getComputedStyle(btn).width,minWidth:getComputedStyle(btn).minWidth,padding:getComputedStyle(btn).padding,position:getComputedStyle(btn).position}))})')
                    button.click()
                    evidence['after']=picker.evaluate('el=>({selected:el.__fxValues.selected,rows:[...el.querySelector(":scope > .fx-rows").children].map(row=>({item:row.__fxItem,text:row.querySelector("button").textContent}))})')
                    evidence['clicks']=page.evaluate('window.__colorClicks')
                    (OUT/name/'color-selection.json').write_text(json.dumps(evidence,indent=2)+'\n')
                check('choose-second-milestone-color',choose_color)
                check('color-picker-closes-after-selection',lambda:expect(picker).to_be_hidden())
                def color_preview():
                    colors=control(page,'btnMilestoneColor').evaluate_all('els => els.map(el=>getComputedStyle(el).backgroundColor)')
                    assert colors==['rgb(90, 198, 204)','rgb(244, 185, 185)','rgb(240, 249, 250)'],colors
                check('independent-edited-color-preview',color_preview)
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
                def milestone_dates():
                    milestones=backend({'fn':'api','args':['Project Milestones','list',{}]})['result']
                    assert [row['msft_milestonedate'] for row in milestones]==[
                        '2026-03-01T05:00:00.000Z','2026-03-10T04:00:00.000Z','2026-03-20T04:00:00.000Z'],{
                        'milestoneDates':[row['msft_milestonedate'] for row in milestones]}
                check('milestone-edited-dates-persist',milestone_dates)
                def milestone_colors():
                    milestones=backend({'fn':'api','args':['Project Milestones','list',{}]})['result']
                    assert [row['msft_color'] for row in milestones]==['#5AC6CC','#F4B9B9','#F0F9FA'],{
                        'milestoneColors':[row['msft_color'] for row in milestones]}
                check('independent-milestone-colors-persist',milestone_colors)
                if workitem:
                    backend({'fn':'__peopleResponses','args':[[response,response]]})
                    page.reload()
                    check('project-screen-after-reload',lambda:expect(page.locator('[data-screen="Projects Screen"]')).to_be_visible(timeout=10000))
                    projects=control(page,'galProjects')
                    check('saved-project-listed-after-reload',lambda:expect(projects.locator('[data-control="lblProjects_ProjectName"]')).to_have_text(['Facilities renewal']))
                    check('select-saved-project',lambda:projects.locator('[data-control="btnProjects_Foreground"]').first.click())
                    check('saved-project-header',lambda:expect(control(page,'lblProjectName')).to_have_text('Facilities renewal'))
                    def open_work_item():
                        started=time.monotonic()
                        try:
                            control(page,'btnNewWorkItem').click()
                        finally:
                            elapsed=time.monotonic()-started
                            (OUT/name/'work-item-click-timing.json').write_text(json.dumps({'seconds':elapsed})+'\n')
                    check('new-work-item-action',open_work_item)
                    check('new-work-item-screen',lambda:expect(page.locator('[data-screen="Add/Edit Work Item"]')).to_be_visible())
                    save=control(page,'btnCreateWorkItem')
                    check('empty-work-item-name-disables-create',lambda:expect(save).to_be_disabled())
                    selectors=['cmbAddWorkItemTeamMember','cmbAddWorkItemMilestone','cmbAddWorkItemStatus','cmbAddWorkItemCategory','cmbAddWorkItemPriority']
                    options={selector:control(page,selector).locator('option').all_text_contents() for selector in selectors}
                    (OUT/name/'work-item-options.json').write_text(json.dumps(options,indent=2)+'\n')
                    check('migrated-project-member-option',lambda:expect(control(page,selectors[0]).locator('option')).to_contain_text(['Ada Lovelace']))
                    check('persisted-milestone-options',lambda:expect(control(page,selectors[1]).locator('option')).to_contain_text(['Survey site','Replace equipment','Review handover']))
                    check('assign-work-item-google-user',lambda:control(page,selectors[0]).select_option(label='Ada Lovelace'))
                    check('assign-work-item-milestone',lambda:control(page,selectors[1]).select_option(label='Replace equipment'))
                    if settings:
                        for selector,label in [(selectors[2],'In progress'),(selectors[3],'Facilities'),(selectors[4],'High')]:
                            check('select-work-item-'+label,lambda selector=selector,label=label:control(page,selector).select_option(label=label))
                    control(page,'txtAddWorkItemName').fill('Survey the north entrance')
                    control(page,'txtAddWorkItemDesc').fill('Measure access clearance.\nRecord photos in the project notes.')
                    control(page,'datAddWorkItemTargetDate').fill('2026-03-09')
                    check('work-item-name-enables-create',lambda:expect(save).to_be_enabled())
                    page.screenshot(path=str(OUT/name/'work-item-draft.png'),full_page=True)
                    check('create-work-item',lambda:save.click())
                    check('return-from-work-item',lambda:expect(page.locator('[data-screen="Projects Screen"]')).to_be_visible())
                    check('work-item-callbacks-settle',lambda:page.wait_for_function('async()=>await window.__waitForGasIdle()',timeout=10000))
                    def work_item_record():
                        records=backend({'fn':'api','args':['Project Work Items','list',{}]})['result']
                        assert len(records)==1,{'count':len(records)}
                        record=records[0]
                        assert record['msft_name']=='Survey the north entrance',record['msft_name']
                        assert record['msft_description']=='Measure access clearance.\nRecord photos in the project notes.',record['msft_description']
                        assert record['msft_etadate']=='2026-03-09T04:00:00.000Z',record['msft_etadate']
                    check('saved-work-item-text-and-date',work_item_record)
                    created=backend({'fn':'api','args':['Project Work Items','list',{}]})['result'][0]
                    observed={'created':created}
                    def retain_work_item_evidence():
                        (OUT/name/'work-item-records.json').write_text(json.dumps(observed,indent=2)+'\n')
                    retain_work_item_evidence()
                    def linked_records():
                        for field,source,title in [('msft_project_id','Projects','Facilities renewal'),
                                ('msft_milestone_id','Project Milestones','Replace equipment'),
                                ('msft_teammember_id','Project Team Members','Ada Lovelace')]:
                            targets=backend({'fn':'api','args':[source,'list',{}]})['result']
                            target=next(record for record in targets if record['msft_name']==title)
                            assert created[field]['id']==target['id'],{'field':field,'actual':created[field].get('id'),'expected':target['id']}
                        assert created['msft_teammember_id']['msft_userid']=='business.tester@example.test'
                    check('saved-work-item-links-and-google-assignee',linked_records)
                    if settings:
                        def configured_links(record):
                            for field,label in [('msft_workitemstatus_id','In progress'),('msft_category_id','Facilities'),('msft_priority_id','High')]:
                                assert record[field] and record[field]['msft_name']==label,{'field':field,'recordId':record['id']}
                        check('work-item-retains-configured-settings',lambda:configured_links(created))
                    items=control(page,'galWorkItems')
                    title=items.locator('[data-control="lblWorkItemTitle"]')
                    check('saved-work-item-visible',lambda:expect(title).to_have_text(['Survey the north entrance']))
                    check('saved-work-item-milestone-label',lambda:expect(items.locator('[data-control="lblWorkItemMilestone"]')).to_have_text(['Replace equipment']))
                    check('saved-work-item-assignee-label',lambda:expect(items.locator('[data-control="lblWorkItemAssignedTo"]')).to_have_text(['Ada Lovelace']))
                    def reference_data():
                        counts={source:len(backend({'fn':'api','args':[source,'list',{}]})['result'])
                                for source in ['staticIcons','staticLocalizations','staticCharWidths']}
                        assert counts=={'staticIcons':129,'staticLocalizations':573,'staticCharWidths':194},counts
                    check('complete-exported-reference-tables',reference_data)
                    def milestone_width():
                        metrics=page.evaluate('''() => {
                          const value=val('lblWorkItemMilestone'),gallery=val('galWorkItems');
                          const chars=Array.from(value.text).map(char=>{
                            const match=state.colCharsWidth.find(row=>row.char===char && row.char_font===value.font && row.char_weight===value.font_weight);
                            return {char,size:match?Number(match.size):null};
                          });
                          const expected=Math.min(chars.reduce((sum,char)=>sum+(char.size||0),0)*value.size+value.padding_left+value.padding_right+2,
                            Math.max(gallery.width/10,90));
                          return {font:value.font,weight:value.font_weight,characters:chars,width:value.width,expected,
                            family:value.el.style.fontFamily};
                        }''')
                        (OUT/name/'milestone-label-metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
                        assert metrics['font']=="'Segoe UI', 'Open Sans', sans-serif"
                        assert metrics['weight']=='normal'
                        assert all(char['size'] is not None for char in metrics['characters']),metrics
                        assert metrics['expected']>=90,metrics
                        assert abs(metrics['width']-metrics['expected'])<0.1,metrics
                        assert metrics['family']=='"Segoe UI", "Open Sans", sans-serif',metrics
                    check('milestone-label-uses-source-character-widths',milestone_width)
                    backend({'fn':'__peopleResponses','args':[[response,response]]})
                    page.reload()
                    expect(page.locator('[data-screen="Projects Screen"]')).to_be_visible(timeout=10000)
                    projects.locator('[data-control="btnProjects_Foreground"]').first.click()
                    check('work-item-visible-after-reload',lambda:expect(title).to_have_text(['Survey the north entrance']))
                    check('reopen-work-item',lambda:items.locator('[data-control="btnWorkItemsForeground"]').first.click())
                    check('edit-work-item-screen',lambda:expect(page.locator('[data-screen="Add/Edit Work Item"]')).to_be_visible())
                    def restored_editor():
                        expect(control(page,'txtAddWorkItemName')).to_have_value('Survey the north entrance')
                        expect(control(page,'txtAddWorkItemDesc')).to_have_value('Measure access clearance.\nRecord photos in the project notes.')
                        expect(control(page,'datAddWorkItemTargetDate')).to_have_value('2026-03-09')
                        expect(control(page,selectors[0]).locator('option:checked')).to_have_text(['Ada Lovelace'])
                        expect(control(page,selectors[1]).locator('option:checked')).to_have_text(['Replace equipment'])
                        if settings:
                            for selector,label in [(selectors[2],'In progress'),(selectors[3],'Facilities'),(selectors[4],'High')]:
                                expect(control(page,selector).locator('option:checked')).to_have_text([label])
                    check('work-item-editor-restores-values-and-links',restored_editor)
                    control(page,'txtAddWorkItemName').fill('Confirm north entrance clearance')
                    control(page,'datAddWorkItemTargetDate').fill('2026-03-11')
                    check('save-work-item-edits',lambda:save.click())
                    expect(page.locator('[data-screen="Projects Screen"]')).to_be_visible()
                    page.wait_for_function('async()=>await window.__waitForGasIdle()',timeout=10000)
                    def edited_record():
                        records=backend({'fn':'api','args':['Project Work Items','list',{}]})['result']
                        assert len(records)==1,{'count':len(records)}
                        record=records[0]
                        observed['edited']=record;retain_work_item_evidence()
                        assert record['id']==created['id']
                        assert record['msft_name']=='Confirm north entrance clearance'
                        assert record['msft_etadate']=='2026-03-11T04:00:00.000Z'
                        assert record['msft_teammember_id']['id']==created['msft_teammember_id']['id']
                        assert record['msft_milestone_id']['id']==created['msft_milestone_id']['id']
                        if settings:
                            configured_links(record)
                            for field in ['msft_workitemstatus_id','msft_category_id','msft_priority_id']:
                                assert record[field]['id']==created[field]['id']
                    check('work-item-edit-retains-record-and-linked-identities',edited_record)
                    check('edited-work-item-listed-once',lambda:expect(title).to_have_text(['Confirm north entrance clearance']))
                    backend({'fn':'__peopleResponses','args':[[response,response]]})
                    page.reload()
                    expect(page.locator('[data-screen="Projects Screen"]')).to_be_visible(timeout=10000)
                    projects.locator('[data-control="btnProjects_Foreground"]').first.click()
                    check('edited-work-item-survives-reload',lambda:expect(title).to_have_text(['Confirm north entrance clearance']))
                    page.screenshot(path=str(OUT/name/'work-item-reloaded.png'),full_page=True)
                    if filters:
                        check('open-work-item-search',lambda:control(page,'imgSearchWorkItems').click())
                        search=control(page,'txtFindWorkItems')
                        check('search-field-visible',lambda:expect(search).to_be_visible())
                        search.fill('north entrance')
                        check('search-matches-persisted-work-item',lambda:expect(title).to_have_text(['Confirm north entrance clearance']))
                        search.fill('not a matching work item')
                        check('search-excludes-unmatched-work-item',lambda:expect(title).to_have_count(0))
                        check('close-and-reset-work-item-search',lambda:control(page,'imgCloseSearchWorkItems').click())
                        check('reset-search-restores-work-item',lambda:expect(title).to_have_text(['Confirm north entrance clearance']))
                        check('search-reset-to-blank',lambda:expect(search).to_have_value(''))
                        primary_name='Confirm north entrance clearance'
                        contrast_name='Order handover signs'
                        def expect_items(names):
                            expect(title).to_have_count(len(names))
                            for text in names:
                                expect(title.filter(has_text=text)).to_have_text([text])
                        check('create-contrasting-work-item',lambda:control(page,'btnNewWorkItem').click())
                        expect(page.locator('[data-screen="Add/Edit Work Item"]')).to_be_visible()
                        control(page,'txtAddWorkItemName').fill(contrast_name)
                        control(page,'txtAddWorkItemDesc').fill('Prepare signs before project handover.')
                        control(page,'datAddWorkItemTargetDate').fill('2026-04-01')
                        for selector,label in zip(selectors,['Ada Lovelace','Review handover','Not started','Facilities','High']):
                            control(page,selector).select_option(label=label)
                        check('save-contrasting-work-item',lambda:save.click())
                        expect(page.locator('[data-screen="Projects Screen"]')).to_be_visible()
                        page.wait_for_function('async()=>await window.__waitForGasIdle()',timeout=10000)
                        def contrasting_record():
                            records=backend({'fn':'api','args':['Project Work Items','list',{}]})['result']
                            assert len(records)==2
                            contrast=next(row for row in records if row['msft_name']==contrast_name)
                            observed['contrast']=contrast;retain_work_item_evidence()
                            assert contrast['id']!=created['id']
                            assert contrast['msft_milestone_id']['msft_name']=='Review handover'
                            assert contrast['msft_workitemstatus_id']['msft_name']=='Not started'
                            assert contrast['msft_etadate']=='2026-04-01T04:00:00.000Z'
                        check('contrasting-work-item-persists-with-distinct-links',contrasting_record)
                        check('both-work-items-visible',lambda:expect_items([primary_name,contrast_name]))
                        check('open-work-item-filter-dialog',lambda:control(page,'imgFilterWorkItems').click())
                        check('filter-dialog-visible',lambda:expect(control(page,'conFilterWorkItems')).to_be_visible())
                        filter_controls=['cmbMilestones','cmbCategories','cmbPriorities','cmbTeamMembers','cmbStatuses']
                        for selector,label in zip(filter_controls,['Select milestones','Select categories','Select priorities','Select team members','Select statuses']):
                            check('filter-accessible-'+selector,lambda selector=selector,label=label:expect(control(page,selector)).to_have_accessible_name(label))
                            check('filter-multiple-'+selector,lambda selector=selector:expect(control(page,selector)).to_have_attribute('multiple',''))
                        def filter_defaults():
                            selected={name:control(page,name).locator('option:checked').all_text_contents() for name in filter_controls}
                            (OUT/name/'filter-defaults.json').write_text(json.dumps(selected,indent=2)+'\n')
                            assert all(values==[] for values in selected.values()),selected
                        check('filter-defaults-are-blank',filter_defaults)
                        check('apply-empty-filters',lambda:control(page,'btnApplyFilter').click())
                        check('empty-filters-retain-both-work-items',lambda:expect_items([primary_name,contrast_name]))
                        announce=control(page,'lblAnnounce_Projects')
                        def filter_items(tag,criteria,expected):
                            check(tag+'-open',lambda:control(page,'imgFilterWorkItems').click())
                            for selector,labels in criteria.items():
                                check(tag+'-'+selector,lambda selector=selector,labels=labels:control(page,selector).select_option(label=labels))
                            check(tag+'-apply',lambda:control(page,'btnApplyFilter').click())
                            check(tag+'-matches',lambda:expect_items(expected))
                            check(tag+'-announcement',lambda:expect(announce).to_have_text('Filters applied to work items list'))
                        def clear_filters(tag):
                            check(tag+'-open',lambda:control(page,'imgFilterWorkItems').click())
                            check(tag+'-clear',lambda:control(page,'btnClearFilter').click())
                            check(tag+'-restores-both-items',lambda:expect_items([primary_name,contrast_name]))
                            check(tag+'-announcement',lambda:expect(announce).to_have_text('Work item filters cleared and filter dialog closed'))
                            for selector in filter_controls:
                                check(tag+'-blank-'+selector,lambda selector=selector:expect(control(page,selector).locator('option:checked')).to_have_count(0))
                        filter_items('unmatched-milestone',{'cmbMilestones':['Survey site']},[])
                        clear_filters('clear-unmatched')
                        filter_items('single-milestone',{'cmbMilestones':['Replace equipment']},[primary_name])
                        filter_items('multiple-milestones',{'cmbMilestones':['Replace equipment','Review handover']},[primary_name,contrast_name])
                        filter_items('milestones-and-status',{'cmbStatuses':['Not started']},[contrast_name])
                        page.screenshot(path=str(OUT/name/'combined-filters.png'),full_page=True)
                        clear_filters('clear-combined')
                        filter_items('shared-category-priority-assignee',{'cmbCategories':['Facilities'],'cmbPriorities':['High'],'cmbTeamMembers':['Ada Lovelace']},[primary_name,contrast_name])
                        filter_items('shared-fields-and-unmatched-status',{'cmbStatuses':['Done']},[])
                        clear_filters('clear-shared')
                        control(page,'imgSearchWorkItems').click();search.fill('HANDOVER')
                        check('search-matches-second-item-case-insensitively',lambda:expect_items([contrast_name]))
                        search.fill('north')
                        check('search-switches-to-first-item',lambda:expect_items([primary_name]))
                        control(page,'imgCloseSearchWorkItems').click()
                        check('clear-search-restores-two-items',lambda:expect_items([primary_name,contrast_name]))
                        filter_items('reopen-filtered-item',{'cmbMilestones':['Replace equipment']},[primary_name])
                        check('open-filtered-work-item',lambda:items.locator('[data-control="btnWorkItemsForeground"]').click())
                        check('filtered-item-editor-retains-name',lambda:expect(control(page,'txtAddWorkItemName')).to_have_value(primary_name))
                        check('filtered-item-editor-retains-date',lambda:expect(control(page,'datAddWorkItemTargetDate')).to_have_value('2026-03-11'))
                        check('return-from-filtered-item',lambda:control(page,'btnCancelWorkItem').click())
                        expect(page.locator('[data-screen="Projects Screen"]')).to_be_visible()
                        clear_filters('clear-before-selection')
                        for width,height in [(1440,900),(1000,700),(520,700)]:
                            viewport_id=str(width)+'x'+str(height)
                            page.set_viewport_size({'width':width,'height':height})
                            check('filter-keyboard-open-'+viewport_id,lambda:control(page,'imgFilterWorkItems').click())
                            def keyboard_filter():
                                picker=control(page,'cmbMilestones')
                                picker.scroll_into_view_if_needed()
                                expect(picker).to_be_in_viewport(ratio=0.95)
                                expect(picker).to_be_enabled()
                                box=picker.bounding_box()
                                assert box['width']>=200 and box['height']>=28,box
                                panel=control(page,'lblFilterContainer').bounding_box()
                                for selector in filter_controls:
                                    bounds=control(page,selector).bounding_box()
                                    assert bounds['x']>=panel['x'] and bounds['x']+bounds['width']<=panel['x']+panel['width'],{'panel':panel,'selector':selector,'bounds':bounds}
                                picker.focus();picker.press('Home');picker.press('ArrowDown');picker.press('Shift+ArrowDown')
                                expect(picker.locator('option:checked')).to_have_text(['Replace equipment','Review handover'])
                                expect(picker).to_be_focused()
                                page.screenshot(path=str(OUT/name/('filter-dialog-'+viewport_id+'.png')),full_page=True)
                            check('filter-keyboard-multiple-selection-'+viewport_id,keyboard_filter)
                            def keyboard_apply():
                                apply=control(page,'btnApplyFilter')
                                apply.scroll_into_view_if_needed()
                                expect(apply).to_be_in_viewport(ratio=0.95)
                                apply.focus();apply.press('Enter')
                                expect_items([primary_name,contrast_name])
                            check('filter-keyboard-apply-'+viewport_id,keyboard_apply)
                            clear_filters('filter-keyboard-clear-'+viewport_id)
                        page.set_viewport_size({'width':1440,'height':900})
                    select_all=control(page,'chkSelectAllWorkItems')
                    announcement=control(page,'lblAnnounce_Projects')
                    check('select-all-work-items',lambda:select_all.check())
                    check('select-all-checks-loaded-row',lambda:expect(items.locator('[data-control="chkSelectWorkItem"]').first).to_be_checked())
                    if filters:
                        check('select-all-checks-second-loaded-row',lambda:expect(items.locator('[data-control="chkSelectWorkItem"]').nth(1)).to_be_checked())
                    check('select-all-announcement',lambda:expect(announcement).to_have_text('All work items selected'))
                    check('selection-announcement-is-live',lambda:expect(announcement).to_have_attribute('aria-live','assertive'))
                    check('deselect-all-work-items',lambda:select_all.uncheck())
                    check('deselect-all-clears-loaded-row',lambda:expect(items.locator('[data-control="chkSelectWorkItem"]').first).not_to_be_checked())
                    if filters:
                        check('deselect-all-clears-second-loaded-row',lambda:expect(items.locator('[data-control="chkSelectWorkItem"]').nth(1)).not_to_be_checked())
                    check('deselect-all-announcement',lambda:expect(announcement).to_have_text('All work items deselected'))
                    deletion_row=items.locator(':scope > .fx-rows > .fx-row').filter(has=page.locator('[data-control="lblWorkItemTitle"]').filter(has_text='Confirm north entrance clearance'))
                    check('select-work-item-for-deletion',lambda:deletion_row.locator('[data-control="chkSelectWorkItem"]').check())
                    check('selection-stays-on-project-screen',lambda:expect(page.locator('[data-screen="Projects Screen"]')).to_be_visible())
                    check('open-work-item-deletion-dialog',lambda:control(page,'imgDeleteWorkItems').click())
                    check('deletion-requires-confirmation',lambda:expect(control(page,'btnDeleteWarning')).to_be_disabled())
                    check('confirm-work-item-deletion',lambda:control(page,'chkConfirmDelete').check())
                    check('delete-selected-work-item',lambda:control(page,'btnDeleteWarning').click())
                    page.wait_for_function('async()=>await window.__waitForGasIdle()',timeout=10000)
                    def removed_record():
                        observed['afterDelete']=backend({'fn':'api','args':['Project Work Items','list',{}]})['result']
                        retain_work_item_evidence()
                        assert [row['id'] for row in observed['afterDelete']]==([observed['contrast']['id']] if filters else [])
                        assert len(backend({'fn':'api','args':['Projects','list',{}]})['result'])==1
                        assert len(backend({'fn':'api','args':['Project Milestones','list',{}]})['result'])==3
                    check('work-item-deletion-preserves-project-and-milestones',removed_record)
                    check('deleted-work-item-disappears',lambda:expect(title).to_have_text([contrast_name]) if filters else expect(title).to_have_count(0))
        finally:
            snapshot()
            (OUT/name/'runtime-state.json').write_text(json.dumps(page.evaluate("""() => ({
                now: new Date().toISOString(), loaded: state.gblAppLoaded,
                timer: {value: val('tmrLoadingDelay').value, running: val('tmrLoadingDelay').running},
                screens: [...document.querySelectorAll('[data-screen]')].filter(el => el.style.display !== 'none').map(el => el.dataset.screen)
            })"""),indent=2)+'\n')
            if project:
                trace={key:backend({'fn':fn,'args':[]}) for key,fn in
                       [('peopleRequests','__peopleRequests'),('connectorRequests','__connectorRequests')]}
                (OUT/name/'native-directory-evidence.json').write_text(json.dumps(trace,indent=2)+'\n')
    with sync_playwright() as p:
        browser=p.chromium.launch()
        result=run_case(browser,name,REPO/'samples/microsoft/milestones.msapp',journey,
            solution=REPO/'samples/microsoft/Milestones.solution.zip',setup_backend=seed,
            timezone_id='America/New_York',running_time='2026-03-01T16:00:00+00:00')
        browser.close()
    result.update(sourceAppId='milestones',steps=steps,assessmentScope='first-run onboarding and persisted settings across two simulated Google users'+('; source global category/priority/status setup and reload' if settings else '')+('; project creation probe' if project else '')+('; work-item create/edit/delete and preserved assignment/milestone links' if workitem else '')+('; two persisted work items, search, combined multi-select filters, filtered editing and targeted deletion' if filters else ''),
                  completeUsability='unassessed',assessmentScriptSha256=hashlib.sha256((REPO/'scripts/assess_milestones_workflow.py').read_bytes()).hexdigest())
    if filters:
        result['filterUIAssessment']={'status':result['status'],'viewports':[[1440,900],[1000,700],[520,700]],
            'checks':'accessible source labels; empty/multiple selections; actual keyboard selection/apply; controls visible after scrolling; source clear action',
            'limits':'source control dimensions and canvas minimum are retained; native select appearance and searchable ComboBox popup are not reproduced'}
    if settings:
        result['sourceSettingsLimitations']=['The exported Save formula omits Sequence; blank status sequences retain the Active view Name ordering on reload, not entry order. Arbitrary completion-status positioning and tenant-side sequence population remain unverified.',
            'Audit timestamps and other server defaults are not populated by this adapter.']
    (OUT/name/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'status':result['status'],'steps':steps},indent=2))
    return int(result['status']!='pass')


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',action='store_true',help='Continue through the original project creation workflow')
    parser.add_argument('--workitem',action='store_true',help='Continue project creation through the original work-item workflow')
    parser.add_argument('--settings',action='store_true',help='Configure source categories/priorities/statuses before the project and work-item lifecycle')
    parser.add_argument('--filters',action='store_true',help='Continue settings/work-item lifecycle through search and filter controls')
    args=parser.parse_args()
    raise SystemExit(main(project=args.project,workitem=args.workitem,settings=args.settings,filters=args.filters))
