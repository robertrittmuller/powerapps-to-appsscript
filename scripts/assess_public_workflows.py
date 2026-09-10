"""Source-action browser checks for the pinned public canvas app corpus.

Real-app critical workflows and UI checks; original-UI comparisons stay separate.
Run: ./pfx2gas browser scripts/assess_public_workflows.py
"""
import json
import re
import hashlib
from pathlib import Path

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

    def journey(page, backend):
        check('source-home-screen', lambda: expect(page.locator('[data-screen="HomeScreen"]')).to_be_visible())

        def named_menu_data():
            page.wait_for_function('state.NavStructure && state.NavStructure.length === 4')
            assert page.evaluate('state.NavStructure.map(row => row.title)') == ['Home', 'Work', 'Admin', 'Logout']

        check('source-named-menu-data', named_menu_data)
        check('source-menu-content', lambda: expect(control(page, 'NavComponent_1__ButtonCanvas1'))
              .to_have_text(['Home', 'Work', 'Admin', 'Logout']))
        check('source-profile-email', lambda: expect(control(page, 'NavComponent_1__TextCanvas2'))
              .to_have_text('business.tester@example.test'))
        check('source-work-action', lambda: control(page, 'NavComponent_1__ButtonCanvas1').nth(1).click(timeout=5000))
        check('source-work-destination', lambda: expect(page.locator('[data-screen="TaskScreen"]')).to_be_visible())
        check('source-home-action', lambda: control(page, 'NavComponent_2__ButtonCanvas1').nth(0).click(timeout=5000))
        check('source-home-return', lambda: expect(page.locator('[data-screen="HomeScreen"]')).to_be_visible())
        expander=control(page,'NavComponent_1__ButtonCanvas3').first
        check('source-expander-has-accessible-name',lambda:expect(expander).to_have_accessible_name(re.compile(r'\S')))
        check('source-expand-home',lambda:expander.click(timeout=5000))
        check('source-dashboard-action',lambda:control(page,'NavComponent_1__ButtonCanvas2').filter(has_text='Dashboard').click(timeout=5000))
        check('source-dashboard-destination',lambda:expect(page.locator('[data-screen="DashboardScreen"]')).to_be_visible())
        def active_controls(suffix):
            return page.locator('[data-screen]:visible [data-control$="__'+suffix+'"]')

        def home():
            active_controls('ButtonCanvas1').filter(has_text=re.compile('^Home$')).click(timeout=5000)
            expect(page.locator('[data-screen="HomeScreen"]')).to_be_visible()

        check('source-dashboard-return',home)
        destinations=[
            ('Home','Dashboard','DashboardScreen'),
            ('Home','Quick Actions','QuickActionsScreen'),
            ('Work',None,'TaskScreen'),
            ('Work','Completed Tasks','CompletedTaskScreen'),
            ('Work','Approvals','ApprovalsScreen'),
            ('Work','Recent Activitiy','WorkActivityScreen'),
            ('Admin',None,'AdminScreen'),
            ('Admin','User','UserScreen'),
            ('Admin','Settings','SettingsScreen'),
        ]
        def collapse():
            expander=active_controls('ButtonCanvas3').first
            expander.focus();expander.press('Enter')
            expect(active_controls('GalSubmenu').first).to_be_visible()
            expander.press('Space')
            expect(active_controls('GalSubmenu').first).to_be_hidden()
            expect(expander).to_be_focused()
        def menu_ui():
            buttons=active_controls('ButtonCanvas1')
            expect(buttons).to_have_text(['Home','Work','Admin','Logout'])
            heights=active_controls('GalMenu').locator(':scope > .fx-rows > .fx-row').evaluate_all(
                'els=>els.map(el=>el.offsetHeight)')
            assert heights==[39,39,39,39],{'closedRowHeights':heights}
            for index,label in enumerate(['Home','Work','Admin','Logout']):
                button=buttons.nth(index)
                expect(button).to_have_accessible_name(label)
                expect(button.locator('[data-fx-button-symbol]')).to_be_visible()
                box=button.bounding_box()
                assert box['width']>=40 and box['height']>=30,box
                assert box['y']>=0 and box['y']+box['height']<=page.viewport_size['height'],box
                # Preserve the source's narrow-menu formula, including a label
                # for every icon when its visual caption is hidden.
                caption=button.locator('[data-fx-button-caption]')
                if box['width']<200:
                    expect(caption).to_be_hidden()
                else:
                    expect(caption).to_be_visible()
            image=active_controls('Image1')
            image_state=image.evaluate('el=>({complete:el.complete,naturalWidth:el.naturalWidth,src:el.getAttribute("src"),background:getComputedStyle(el).backgroundImage})')
            # The generated-server identity fixture intentionally has no photo.
            # Verify the visible CSS avatar fallback, not an invented image URL.
            expect(image).to_be_visible()
            assert image_state['src'] is None and image_state['background'].count('radial-gradient(')==2,image_state
            assert image.bounding_box()['width']==image.bounding_box()['height']==60
            email=active_controls('TextCanvas2')
            expect(email).to_have_text('business.tester@example.test')
            if buttons.first.bounding_box()['width']>200:
                expect(email).to_be_visible()
            else:
                expect(email).to_be_hidden()

        for width,height in [(1440,900),(1000,700),(520,700)]:
            viewport_id=str(width)+'x'+str(height)
            page.set_viewport_size({'width':width,'height':height});page.wait_for_timeout(100)
            check('source-menu-ui-'+viewport_id,menu_ui)
            for group, caption, screen in destinations:
                def navigate(group=group,caption=caption,screen=screen):
                    root_button=active_controls('ButtonCanvas1').filter(has_text=re.compile('^'+group+'$'))
                    if caption:
                        row=root_button.locator('..')
                        expander=row.locator('[data-control$="__ButtonCanvas3"]')
                        expect(expander).to_have_accessible_name(re.compile(r'\S'))
                        expander.click(timeout=5000)
                        active_controls('ButtonCanvas2').filter(has_text=re.compile('^'+caption+'$')).click(timeout=5000)
                    else:
                        root_button.click(timeout=5000)
                    expect(page.locator('[data-screen="'+screen+'"]')).to_be_visible()
                check('source-destination-'+screen+'-'+viewport_id,navigate)
                check('source-return-from-'+screen+'-'+viewport_id,home)
            check('source-keyboard-expand-collapse-'+viewport_id,collapse)
            page.screenshot(path=str(OUT/name/('menu-'+viewport_id+'.png')),full_page=True)
        def reload_profile():
            data=json.loads((REPO/'tests/fixtures/google-directory.json').read_text())
            backend({'fn':'__peopleResponses','args':[[{'method':'get','result':data['people'][0]}]]})
            page.reload();expect(page.locator('[data-screen="HomeScreen"]')).to_be_visible()
            expect(control(page,'NavComponent_1__TextCanvas2')).to_have_text('business.tester@example.test')
        check('source-reload-profile',reload_profile)
        def exit_feedback():
            active_controls('ButtonCanvas1').filter(has_text=re.compile('^Logout$')).click(timeout=5000)
            expect(page.locator('#fx-toast')).to_have_text('You may now close this window.')
        check('source-exit-browser-feedback',exit_feedback)

    def setup_directory(backend):
        data = json.loads((REPO/'tests/fixtures/google-directory.json').read_text())
        assert backend({'fn':'__importDirectory','args':[data['migration']]}) == {'result':{'ok':True,'users':2}}
        backend({'fn':'__peopleResponses','args':[[{'method':'get','result':data['people'][0]}]]})
        return {'source':'authored source-ID/Google identity mappings',
                'googlePeople':'explicit native response fixture; no live Google authorization'}

    with sync_playwright() as p:
        browser = p.chromium.launch()
        result = run_case(browser, name, REPO/'samples/real/expandable-nav.msapp', journey, setup_backend=setup_directory)
        browser.close()
    if result['status']=='pass' and (len(steps)!=75 or any(step['status']!='pass' for step in steps)):
        result.update(status='fail',error='Incomplete required navigation/UI checks')
    result.update(sourceAppId='expandable-nav', steps=steps, completeUsability=result['status'],
                  criticalJourneyCoverage='complete',
                  criticalJourneys=[{'id':'expand-and-navigate','required':True,'status':result['status']}],
                  uiAssessment={'status':result['status'],'viewports':[[1440,900],[1000,700],[520,700]],
                                'sourceSizing':'source canvas minimum dimensions retained; smaller windows can scroll',
                                'profilePhoto':'no-photo CSS avatar fallback',
                                'exit':'browser close-window feedback; no Google sign-out'},
                  assessmentScriptSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  assessmentScope='all source navigation destinations/returns, expansion/collapse, profile and action usability')
    (OUT/name/'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'steps': steps}, indent=2))
    return int(result['status'] != 'pass')


if __name__ == '__main__':
    raise SystemExit(main())
