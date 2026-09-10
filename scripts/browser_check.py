"""Real Chromium regression journeys using generated client AND server code.

Run with ./pfx2gas browser. Screenshots are converted-output evidence, not
original-app visual baselines. The spreadsheet service is a test double.
"""
from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlsplit, parse_qs, urlencode

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
from playwright.sync_api import sync_playwright, expect
from pfx2gas.analyze import analyze
from pfx2gas.benchmark import converter_fingerprint
from pfx2gas.parse import parse
from pfx2gas.synth.build import synthesize
from pfx2gas.unpack import unpack
from pfx2gas.validate import validate_project

OUT = REPO / ".artifacts/browser"


def control(page, name):
    return page.locator(f'[data-control="{name}"]')


def check_form(page, backend):
    expect(control(page, "InputFirst")).to_have_value("Ada")
    control(page, "InputFirst").fill("Augusta")
    control(page, "ButtonSubmit").click()
    expect(control(page, "InputFirst")).to_have_value("Augusta")
    page.wait_for_function("state.savedName === 'Lovelace'")
    page.reload()
    expect(control(page, "InputFirst")).to_have_value("Augusta")
    control(page, "ButtonNew").click()
    control(page, "InputFirst").fill("Grace")
    control(page, "ButtonSubmit").click()
    expect(control(page, "InputLast")).to_have_attribute("aria-invalid", "true")
    control(page, "InputLast").fill("Hopper")
    backend({"fn": "__failNextMutation", "args": []})
    control(page, "ButtonSubmit").click()
    page.wait_for_function("String(state.saveError).includes('Simulated Sheets')")
    control(page, "ButtonSubmit").click()
    page.wait_for_function("state.savedName === 'Hopper'")
    rows = backend({"fn": "api", "args": ["Contacts", "list", {}]})["result"]
    assert len(rows) == 2 and rows[1]["first_name"] == "Grace", rows
    page.reload()
    page.wait_for_function("state.Contacts && state.Contacts.length === 2")
    control(page, "ButtonDeleteLast").click()
    page.wait_for_function("state.Contacts.length === 1")
    page.reload()
    expect(control(page, "InputFirst")).to_have_value("Augusta")
    assert len(backend({"fn": "api", "args": ["Contacts", "list", {}]})["result"]) == 1


def check_helpdesk(page, _backend):
    expect(page.locator('[data-screen="HOME"]')).to_be_visible()
    # Source OnStart declares eight personal tickets and four aggregate rows.
    expect(control(page, "MyTicket").locator('.fx-row')).to_have_count(8)
    page.wait_for_function("state.Records.length === 8 && state.RecordsAssignedtome.length === 3")
    expect(control(page, "MyTicket")).to_contain_text("OPEN")
    page.wait_for_function("document.querySelector('[data-control=iconApp]').naturalWidth === 64")
    expect(control(page, "PieChart2").locator("svg path")).to_have_count(4)
    assert page.evaluate("state.TotalRecords.map(row => row.num)") == [5, 2, 4, 8]
    expect(control(page, "Legend1")).to_contain_text("OPEN")
    last_row = control(page, "MyTicket").locator('.fx-row').last
    last_row.scroll_into_view_if_needed()
    assert control(page, "MyTicket").evaluate("el => el.scrollTop > 0")
    expect(last_row).to_contain_text("CANCELLED")
    control(page, "MyTicket").locator('.fx-row').first.scroll_into_view_if_needed()
    control(page, "MENU_1__link2").click()
    expect(page.locator('[data-screen="NEW"]')).to_be_visible()
    control(page, "TextInputTitle").fill("Temporary title")
    control(page, "TextInputCommentary").fill("Temporary notes")
    control(page, "btnSave_1").click()
    expect(control(page, "TextInputTitle")).to_have_value("")
    expect(control(page, "TextInputCommentary")).to_have_value("")
    control(page, "btnBack").click()
    expect(page.locator('[data-screen="HOME"]')).to_be_visible()


def check_charts(page, _backend):
    chart = control(page, "BusinessChart")
    expect(chart.locator("svg rect")).to_have_count(3)
    expect(chart.locator("svg text")).to_have_count(0)
    expect(chart.locator("svg")).to_have_attribute("width", "320")
    expect(chart.locator("svg rect").nth(0)).to_have_attribute("fill", "rgba(49,130,93,1)")
    expect(control(page, "BusinessLegend")).to_contain_text("Gain")
    expect(control(page, "BusinessLegend").locator("rect").nth(1)).to_have_attribute("fill", "rgba(212,96,104,1)")
    zero = float(chart.locator("[data-zero-axis]").get_attribute("y1"))
    negative = chart.locator('[data-value="-5"]')
    assert float(negative.get_attribute("y")) == zero
    assert float(negative.get_attribute("height")) > 50
    assert float(chart.locator('[data-value="0"]').get_attribute("height")) == 0
    expect(control(page, "BusinessPie").locator("svg circle")).to_have_count(1)
    expect(control(page, "BusinessPie").locator("svg text")).to_have_count(0)
    page.screenshot(path=str(OUT / "business-charts/negative-and-zero.png"))
    control(page, "ToggleChart").click()
    expect(chart.locator("svg")).to_have_attribute("width", "600")
    expect(chart).to_contain_text("Loss")
    assert chart.bounding_box()["width"] == 600
    page.screenshot(path=str(OUT / "business-charts/labels-and-resize.png"))
    control(page, "ClearChart").click()
    expect(chart).to_contain_text("No data")
    expect(control(page, "BusinessPie")).to_contain_text("No data")


def check_scopes(page, backend):
    expect(control(page, "ScopeTotal")).to_have_text("12")
    expect(control(page, "ScopeGallery").locator('.fx-row')).to_have_count(2)
    expect(control(page, "ScopeGallery").locator('[data-control="ScopeRow"]')).to_have_text(["7", "10"])
    expect(control(page, "GroupedScopeTotal")).to_have_text("low:2,high:13")
    control(page, "RemoveScopeRows").click()
    expect(control(page, "ScopeGallery").locator('[data-control="ScopeRow"]')).to_have_text(["10"])
    expect(control(page, "GroupedScopeTotal")).to_have_text("low:2,high:8")
    page.wait_for_function("document.querySelector('[data-control=ScopeImage]').naturalWidth === 32")
    assert "fill='blue'" in control(page, "ScopeImage").get_attribute("src")
    control(page, "ClearScopeImage").click()
    page.wait_for_function("document.querySelector('[data-control=ScopeImage]').complete && document.querySelector('[data-control=ScopeImage]').naturalWidth === 32")
    assert "fill='red'" in control(page, "ScopeImage").get_attribute("src")
    backend({"fn": "__failNextMutation", "args": []})
    control(page, "ScopeSave").click()
    expect(control(page, "ScopeSaveStatus")).to_have_text("failed")
    assert backend({"fn": "api", "args": ["Contacts", "list", {}]})["result"][0]["first_name"] == "Ada"
    control(page, "ScopeSave").click()
    expect(control(page, "ScopeSaveStatus")).to_have_text("Updated")
    page.reload()
    rows = backend({"fn": "api", "args": ["Contacts", "list", {}]})["result"]
    assert len(rows) == 1 and rows[0]["first_name"] == "Updated", rows
    assert rows[0]["last_name"] == "Lovelace" and rows[0]["id"], rows
    # Exercise real generated doGet/event templating, including script-ending
    # input. Parameters are decoded text, never executable or trusted identity.
    payload = '</script><script>window.__injected=true</script> & + café'
    page.goto("https://converted.test/?" + urlencode({"recordId": payload}))
    expect(control(page, "LaunchValue")).to_have_text(payload)
    expect(control(page, "LaunchCase")).to_have_text("case-sensitive")
    expect(control(page, "LaunchLanguage")).to_have_text("en-US")
    assert page.evaluate("window.__injected === undefined")
    page.goto("https://converted.test/?recordId=42")
    expect(control(page, "LaunchValue")).to_have_text("42")
    assert page.evaluate("FXRuntime.param('recordId') === '42' && FXRuntime.param('missing') === null")
    control(page,'ConcurrentSave').click()
    expect(control(page,'ConcurrentStatus')).to_have_text('complete')
    rows = backend({'fn':'api','args':['Contacts','list',{}]})['result']
    assert [(row['first_name'],row['last_name']) for row in rows] == [('Concurrent','Finished')], rows
    control(page,'ConcurrentFailure').click()
    expect(control(page,'ConcurrentStatus')).to_have_text('recovered')
    assert page.evaluate('state.afterConcurrent === true && state.leftDone === false')
    rows = backend({'fn':'api','args':['Contacts','list',{}]})['result']
    assert [(row['first_name'],row['last_name']) for row in rows] == [('Concurrent','Survivor')], rows
    page.screenshot(path=str(OUT / 'record-scopes/concurrent-recovery.png'))
    page.reload()
    assert backend({'fn':'api','args':['Contacts','list',{}]})['result'] == rows


def check_gallery(page, backend):
    rows = control(page, "ContactRows").locator('.fx-row')
    expect(rows).to_have_count(2)
    first = rows.nth(0).locator('[data-control="RowFirst"]')
    second = rows.nth(1).locator('[data-control="RowFirst"]')
    last = rows.nth(1).locator('[data-control="RowLast"]')
    expect(first).to_have_value("Ada")
    expect(second).to_have_value("Grace")
    expect(last).to_have_value("Hopper")
    expect(rows.nth(1).locator('[data-control="RowPreview"]')).to_have_text("Grace Hopper")
    page.wait_for_function("Array.from(document.querySelectorAll('[data-control=RowImage]')).every(el => el.naturalWidth === 32)")
    # Keep a live reference to the input; replacing or moving it during typing
    # used to erase the edit and focus on every binding update.
    last.focus()
    last.press("End")
    last.press_sequentially(" edited")
    last.evaluate("el => { window.__editedInput = el; el.setSelectionRange(2, 5); }")
    page.evaluate("FXRuntime.setState({counter: 10})")
    assert last.evaluate("el => el === window.__editedInput && document.activeElement === el && el.selectionStart === 2 && el.selectionEnd === 5")
    expect(last).to_have_value("Hopper edited")
    expect(rows.nth(1).locator('[data-control="RowPreview"]')).to_have_text("Grace Hopper edited")
    page.evaluate("FXRuntime.setState({reverseRows: true})")
    expect(rows.nth(0).locator('[data-control="RowFirst"]')).to_have_value("Grace")
    assert page.evaluate("document.activeElement === window.__editedInput && window.__editedInput.selectionStart === 2 && window.__editedInput.selectionEnd === 5")
    page.evaluate("FXRuntime.setState({reverseRows: false})")
    expect(last).to_have_value("Hopper edited")
    rows.nth(1).locator('[data-control="RowReset"]').click()
    expect(last).to_have_value("Hopper")
    second.fill("Amazing Grace")
    second.press("Tab")
    page.wait_for_function("state.savedRow === 'Amazing Grace'")
    expect(first).to_have_value("Ada")
    last.fill("Admiral")
    rows.nth(1).locator('[data-control="RowSave"]').click()
    page.wait_for_function("state.parentCalls === 1 && state.parentSawFinished === true")
    assert page.evaluate("state.selectedName") == "Amazing Grace"
    saved = backend({"fn": "api", "args": ["Contacts", "list", {}]})["result"]
    assert [(r["first_name"], r["last_name"]) for r in saved] == [("Ada", "Lovelace"), ("Amazing Grace", "Admiral")], saved
    # A row's selector retains records and reacts through its own OnChange.
    rows.nth(1).locator('[data-control="RowChoice"]').select_option(index=0)
    page.wait_for_function("state.chosenName === 'Ada'")
    control(page, "LockRows").click()
    expect(last).to_be_disabled()
    control(page, "LockRows").click()
    expect(last).to_be_enabled()
    page.screenshot(path=str(OUT / "editable-gallery/two-row-edit.png"))
    page.reload()
    expect(first).to_have_value("Ada")
    expect(second).to_have_value("Amazing Grace")
    expect(last).to_have_value("Admiral")


def check_timers(page, _backend):
    expect(page.locator('[data-screen="LoadingScreen"]')).to_be_visible()
    page.wait_for_function("state.timerStarted === true")
    page.clock.run_for(260)
    expect(page.locator('[data-screen="ReadyScreen"]')).to_be_visible()
    expect(control(page, "ReadyMessage")).to_have_text("Ready")
    page.clock.run_for(60)
    expect(control(page, "FocusInput")).to_be_focused()
    control(page, "StartRepeat").click()
    page.clock.run_for(50)
    assert page.evaluate("val('RepeatTimer').value") == 50
    control(page, "GoOther").click()
    page.clock.run_for(500)
    assert page.evaluate("state.cycles") == 0
    control(page, "ReturnReady").click()
    page.clock.run_for(260)
    assert page.evaluate("state.cycles") == 3
    page.clock.run_for(500)
    assert page.evaluate("state.cycles") == 3
    control(page, "ResetRepeat").click()
    assert page.evaluate("val('RepeatTimer').value") == 0
    control(page, "StartRepeat").click()
    page.clock.run_for(310)
    assert page.evaluate("state.cycles") == 3
    page.screenshot(path=str(OUT / "timer-lifecycle/ready.png"))


def run_case(browser, name, source, journey, clock=False, launch_parameters=None, viewport=None, solution=None, setup_backend=None, timezone_id=None, fixed_time=None):
    ir = analyze(parse(unpack(source)), solution=solution)
    project = synthesize(ir, OUT / name / "project")
    validation = validate_project(project)
    assert validation["ok"], validation["problems"]
    server = subprocess.Popen(["node", str(REPO / "tests/browser/gas-server.cjs"), str(project)],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    def backend(request):
        server.stdin.write(json.dumps(request) + "\n")
        server.stdin.flush()
        line = server.stdout.readline()
        if not line:
            raise RuntimeError("generated server test process stopped")
        return json.loads(line)
    context = browser.new_context(viewport=viewport or {"width": 1440, "height": 900}, locale="en-US", timezone_id=timezone_id)
    context.expose_function("__gasCall", backend)
    context.add_init_script(path=str(REPO / "tests/browser/bridge.js"))
    # No app-generated external requests are permitted in this local test.
    def route_app(route):
        url = urlsplit(route.request.url)
        if url.netloc != "converted.test" or url.path != "/":
            return route.abort()
        parameters = {key: values[0] for key, values in parse_qs(url.query, keep_blank_values=True).items()}
        response = backend({"fn": "doGet", "args": [{"parameter": parameters}]})
        if "error" in response:
            raise RuntimeError(response["error"])
        route.fulfill(content_type="text/html", body=response["result"])
    context.route("**/*", route_app)
    page = context.new_page()
    if clock:
        page.clock.install(time=0)
        page.clock.pause_at(1)
    if fixed_time:
        page.clock.set_fixed_time(datetime.fromisoformat(fixed_time))
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    result = {"app": name, "status": "pass", "backend": "generated Code.gs + Sheets test double",
              "originalVisualComparison": "unassessed", "evidenceType": "chromium-generated-client-and-server",
              "inputSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "sourceMetadata": ir.source_metadata,
              "converterSourceSha256": converter_fingerprint(), "browserVersion": browser.version}
    if fixed_time or timezone_id:
        result['dateContext'] = {'now':fixed_time,'timeZone':timezone_id}
    try:
        if setup_backend:
            result['dataSetup'] = setup_backend(backend)
        page.goto("https://converted.test/?" + urlencode(launch_parameters or {}))
        journey(page, backend)
    except Exception as error:
        result.update(status="fail", error=str(error) or type(error).__name__)
    finally:
        try:
            page.wait_for_function('async () => await window.__waitForGasIdle()', timeout=10000)
            result['serverCallDrain'] = {'status':'pass'}
        except Exception as error:
            result['status'] = 'fail'
            result['serverCallDrain'] = {'status':'fail','error':str(error)}
        try:
            page.screenshot(path=str(OUT / name / "result.png"), full_page=True, timeout=10000)
            result['screenshot'] = {'status':'pass'}
        except Exception as error:
            result['status'] = 'fail'
            result['screenshot'] = {'status':'fail', 'error':str(error)}
        try:
            result["controls"] = page.locator('[data-screen]:visible [data-control]').evaluate_all(
                "els => els.map(el => {const r=el.getBoundingClientRect(); return {name:el.dataset.control,"
                "text:el.innerText, x:r.x,y:r.y,width:r.width,height:r.height,"
                "font:getComputedStyle(el).fontFamily};})")
        except Exception as error:
            result['status'] = 'fail'
            result['measurementError'] = str(error)
        # RPC callbacks and captures can surface errors after the journey
        # returns. Finalize the verdict only after those observations finish.
        result['consoleErrors'] = list(errors)
        if errors:
            result['status'] = 'fail'
            result.setdefault('error','runtime errors: ' + '; '.join(errors))
        (OUT / name / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        context.close()
        server.terminate()
        server.wait(timeout=5)
    print(name, result["status"], result.get("error", ""), flush=True)
    return result


def check_storage(page, backend):
    note, status, count = (control(page, name) for name in ("DraftNote", "CacheStatus", "DraftCount"))
    expect(status).to_have_text("ready")
    expect(count).to_have_text("0")
    expect(control(page, "SaveDraft")).to_be_disabled()
    identity = page.evaluate("JSON.parse(document.getElementById('fx-storage-context').textContent)")
    note.fill("Inspect north entrance")
    expect(control(page, "SaveDraft")).to_be_enabled()
    control(page, "SaveDraft").click()
    expect(status).to_have_text("saved")
    page.reload()
    expect(note).to_have_value("Inspect north entrance")
    expect(count).to_have_text("1")
    expect(control(page, "DraftDate")).to_have_value("2026-09-09")
    expect(control(page, "DraftDone")).not_to_be_checked()
    assert page.evaluate("state.Drafts[0].logged_at instanceof Date && state.Drafts[0].done === false && state.Drafts[0].count === 0 && state.Drafts[0].detail.code === 'inspection'")
    note.fill("Unsaved note")
    note.focus()
    page.evaluate("document.querySelector('[data-control=DraftNote]').setSelectionRange(2, 6)")
    # Keyboard activation changes unrelated state without moving input focus.
    page.evaluate("document.querySelector('[data-control=DraftUnrelated]').click()")
    expect(status).to_have_text("editing")
    expect(note).to_have_value("Unsaved note")
    assert page.evaluate("document.activeElement.dataset.control === 'DraftNote' && document.activeElement.selectionStart === 2 && document.activeElement.selectionEnd === 6")
    control(page, "DraftReset").click()
    expect(note).to_have_value("Inspect north entrance")
    page.screenshot(path=str(OUT / "local-draft-storage/saved-and-reloaded.png"))
    control(page, "AppendDraft").click()
    expect(count).to_have_text("2")
    control(page, "SaveBackup").click()
    expect(status).to_have_text("backup saved")

    # A browser quota failure is handled by the source's IfError and leaves
    # the existing persistent draft available after a reload.
    page.evaluate("() => { Storage.prototype.setItem = function(){throw new DOMException('quota full', 'QuotaExceededError')}; }")
    note.fill("Must not replace saved draft")
    control(page, "SaveDraft").click()
    expect(status).to_have_text("save failed")
    page.reload()
    expect(note).to_have_value("Inspect north entrance")
    expect(count).to_have_text("1")

    page.evaluate("localStorage.setItem(Object.keys(localStorage).find(k => k.endsWith(':inspection-draft')), '{corrupt')")
    page.reload()
    expect(status).to_have_text("load failed")
    expect(count).to_have_text("0")
    control(page, "ClearDraft").click()
    expect(status).to_have_text("draft cleared")
    assert page.evaluate("Object.keys(localStorage).some(k => k.endsWith(':backup'))")
    note.fill("Restored draft")
    control(page, "SaveDraft").click()
    expect(status).to_have_text("saved")

    backend({"fn": "__setStorageIdentity", "args": ["another-script", identity["user"]]})
    page.reload()
    expect(note).to_have_value("")
    note.fill("Other app draft")
    control(page, "SaveDraft").click()
    expect(status).to_have_text("saved")
    backend({"fn": "__setStorageIdentity", "args": [identity["appId"], "another-user@example.test"]})
    page.reload()
    expect(note).to_have_value("")
    note.fill("Other user draft")
    control(page, "SaveDraft").click()
    expect(status).to_have_text("saved")
    backend({"fn": "__setStorageIdentity", "args": [identity["appId"], identity["user"]]})
    page.goto("https://converted.test/?appId=another-script&user=another-user@example.test")
    expect(note).to_have_value("Restored draft")
    page.evaluate("localStorage.setItem('unrelated-app-storage', 'keep')")
    control(page, "ClearAppCache").click()
    expect(status).to_have_text("cache cleared")
    assert page.evaluate("localStorage.length === 3 && localStorage.getItem('unrelated-app-storage') === 'keep'")
    page.reload()
    expect(note).to_have_value("")
    expect(count).to_have_text("0")


def check_dataverse(page, backend):
    name, status, count = (control(page, key) for key in ("ContractName", "ContractResult", "ContractCount"))
    expect(name).to_have_value("Second project")
    expect(count).to_have_text("2")
    expect(control(page, "ContractChoice").locator("option")).to_have_text(["Open", "Closed"])
    assert page.evaluate("state['Project Active'].no === false && state['Project Status'].open === 0")
    assert page.evaluate("() => { try { google.script.run.api('Projects', 'create', {record:{msft_start:new Date()}}); return false; } catch(e) { return /cannot transport/.test(e.message); } }")
    name.fill("Second project edited")
    control(page, "ContractChoice").select_option(index=0)
    control(page, "ContractSave").click()
    expect(status).to_have_text("saved")
    saved = backend({"fn": "api", "args": ["Projects", "list", {}]})["result"]
    assert [(r["id"], r["name"]) for r in saved] == [("project-one", "First project"), ("project-two", "Second project edited")]
    assert saved[1]["status"] == 0 and saved[1]["active"] is False
    control(page, "ContractInvalid").click()
    expect(status).to_have_text("invalid choice")
    assert backend({"fn": "api", "args": ["Projects", "list", {}]})["result"] == saved
    page.reload()
    expect(name).to_have_value("Second project edited")
    expect(control(page, "ContractChoice")).to_have_value("0")
    control(page, "ContractNew").click()
    expect(status).to_have_text("created")
    expect(count).to_have_text("3")
    new = backend({"fn": "api", "args": ["Projects", "list", {}]})["result"][-1]
    assert new["id"] == new["project"] == new["msft_projectid"]
    assert new["active"] is True and new["budget"] == 0 and new["status"] == 0
    assert new["msft_start"] == "2026-09-09T00:00:00.000Z"
    assert new["owner"] == {"user_id": "user-1", "full_name": "Grace"} and new["tags"] == [0, 1]
    page.reload()
    expect(name).to_have_value("New project")
    page.screenshot(path=str(OUT / "dataverse-contract/persisted-project.png"))
    control(page, "ContractDelete").click()
    expect(status).to_have_text("deleted")
    expect(count).to_have_text("2")
    page.reload()
    expect(name).to_have_value("Second project edited")
    expect(count).to_have_text("2")

    before = backend({'fn':'api','args':['Projects','list',{}]})['result']
    name.fill('Updated through the source key')
    backend({'fn':'__failNextMutation','args':[]})
    control(page,'ContractKeySave').click()
    expect(status).to_have_text('key save failed')
    assert backend({'fn':'api','args':['Projects','list',{}]})['result'] == before
    control(page,'ContractKeySave').click()
    expect(status).to_have_text('key saved')
    expect(count).to_have_text('2')
    saved = backend({'fn':'api','args':['Projects','list',{}]})['result']
    assert saved[0] == before[0] and saved[1]['project'] == 'project-two'
    assert saved[1]['name'] == 'Updated through the source key' and saved[1]['budget'] == 0 and saved[1]['active'] is False
    name.fill('Created using a fixed key')
    control(page,'ContractKeyUpsert').click()
    expect(status).to_have_text('key upserted')
    expect(count).to_have_text('3')
    name.fill('Retry updates the same row')
    control(page,'ContractKeyUpsert').click()
    page.wait_for_function("state.selectedProject.name === 'Retry updates the same row'")
    expect(count).to_have_text('3')
    saved = backend({'fn':'api','args':['Projects','list',{}]})['result']
    assert saved[-1]['project'] == 'fixed-new-key' and saved[-1]['name'] == 'Retry updates the same row'
    control(page,'ContractKeyInvalid').click()
    expect(status).to_have_text('key required')
    assert backend({'fn':'api','args':['Projects','list',{}]})['result'] == saved
    page.reload()
    expect(name).to_have_value('Retry updates the same row')
    expect(count).to_have_text('3')
    page.screenshot(path=str(OUT / 'dataverse-contract/keyed-patch-reloaded.png'))
    control(page,'ContractDelete').click()
    expect(count).to_have_text('2')


def check_source_formulas(page, _backend):
    url, error = (control(page, key) for key in ("txtSetupSharePoint_URL", "lblSetupSharePoint_ErrorURL"))
    expect(error).to_have_text("")
    for text, message in [
        ("not a URL", "Please enter a valid URL"),
        ("https://contoso.sharepoint.com/sites/Team/extra", "URL must have exactly 4 forward slashes"),
        ("https://contoso.example.com/sites/Team", "URL must include .sharepoint.com/sites/"),
        ("https://contoso.sharepoint.com/sites/Ab", "URL must include at least a three character site name"),
        ("https://contoso.sharepoint.com/sites/Team", ""),
        ("", ""),
    ]:
        url.fill(text)
        if message:
            expect(error).to_contain_text(message)
        else:
            expect(error).to_have_text("")
    label = control(page, "lblEditWorkItemCreatedOn")
    expect(label).to_have_text("Created on 09 Sep")
    control(page, "FormulaFrench").click()
    expect(label).to_have_text("Créé le 09 sept.")
    control(page, "FormulaJapanese").click()
    expect(label).to_have_text("Created on 09 9月")
    control(page, "FormulaToday").click()
    expect(label).to_have_text(re.compile(r"Created at \d{2}:\d{2} (AM|PM)"))
    assert label.evaluate("el => el.scrollWidth <= el.clientWidth")
    page.screenshot(path=str(OUT / "source-formulas/validated-formulas.png"))


def check_canvas(page, _backend):
    expect(control(page, "CanvasTitle")).to_have_text("1440 / 5")
    assert page.evaluate("state.initialWidth === 1440 && state.initialToggle === false")
    expect(control(page, "ThemeCaption")).to_have_text("Light theme")
    assert page.evaluate("val('Details Screen').width === 1440")
    draft, button = control(page, 'Draft'), control(page, 'OpenDetails')
    panel = control(page, 'ManualPanel')
    def geometry():
        a, b, c = panel.bounding_box(), draft.bounding_box(), button.bounding_box()
        assert b['x'] == a['x'] + 20 and b['y'] == a['y'] + 20, (a, b)
        assert c['y'] == a['y'] + 100 and b['width'] == a['width'] - 40, (a, b, c)
        assert c['y'] >= b['y'] + b['height'], (b, c)
        assert button.evaluate('el => el.scrollWidth <= el.clientWidth && el.scrollHeight <= el.clientHeight')
        first, second = control(page, 'AutoFirst').bounding_box(), control(page, 'AutoSecond').bounding_box()
        assert second['x'] == first['x'] + first['width'] + 8 and first['y'] == second['y'], (first, second)
    geometry()
    draft.fill('Unsaved mobile draft')
    draft.focus()
    draft.evaluate('el => { window.__draft = el; el.setSelectionRange(2, 5); }')
    for width, logical, size in [(900, 900, 2), (390, 390, 1), (280, 320, 1), (1201, 1201, 4)]:
        page.set_viewport_size({'width': width, 'height': 700})
        expect(control(page, 'CanvasTitle')).to_have_text(f'{logical} / {size}')
        geometry()
        expect(draft).to_have_value('Unsaved mobile draft')
        assert draft.evaluate('el => el === window.__draft && document.activeElement === el && el.selectionStart === 2 && el.selectionEnd === 5')
    page.set_viewport_size({'width': 390, 'height': 700})
    expect(control(page, 'CanvasTitle')).to_have_text('390 / 1')
    page.screenshot(path=str(OUT / 'responsive-canvas/narrow.png'))
    button.click()
    expect(control(page, 'DetailsTitle')).to_have_text('Light details')
    page.wait_for_function("state.exitCount === 1 && state.enteredAfterExit === true")
    assert page.evaluate("state.exitScreenWidth === 390 && state.exitDraft === 'Unsaved mobile draft'")
    control(page, 'ReturnCanvas').click()
    control(page, 'ThemeToggle').check()
    expect(control(page, 'ThemeCaption')).to_have_text('Blue theme')
    expect(page.locator('[data-screen="Responsive Screen"]')).to_have_css('background-color', 'rgb(221, 238, 255)')
    button.click()
    expect(control(page, 'DetailsTitle')).to_have_text('Blue details')
    page.wait_for_function('state.exitCount === 2')
    control(page, 'ReturnCanvas').click()
    expect(draft).to_have_value('Unsaved mobile draft')
    expect(control(page, 'CaptionReference')).to_have_text('Open details: Unsaved mobile draft')


def check_scaled_canvas(page, _backend):
    expect(control(page, 'CanvasTitle')).to_have_text('1200 / 3')
    assert page.evaluate("state.initialWidth === 1200 && state.initialToggle === false")
    for width, height in [(600, 500), (1500, 400)]:
        page.set_viewport_size({'width': width, 'height': height})
        scale = min(width / 1200, height / 800)
        expect(page.locator('[data-screen="Responsive Screen"]')).to_have_css('transform', f'matrix({scale}, 0, 0, {scale}, 0, 0)')
        assert page.evaluate("val('App').width === 1200 && val('App').height === 800")
        rect = control(page, 'ManualPanel').bounding_box()
        assert abs(rect['width'] - 1160 * scale) < 1, rect
        control(page, 'OpenDetails').click()
        expect(control(page, 'DetailsTitle')).to_have_text('Light details')
        control(page, 'ReturnCanvas').click()
    page.screenshot(path=str(OUT / 'scaled-canvas/letterboxed.png'))


def check_navigation(page, backend):
    expect(control(page, 'BrowseScope')).to_have_text('browse:blank:global')
    contacts = control(page, 'NavigationRows').locator('[data-control="OpenContact"]')
    expect(contacts).to_have_text(['Ada Lovelace', 'Grace Hopper'])
    contacts.nth(1).click()
    expect(control(page, 'DetailFirst')).to_have_value('Grace')
    expect(control(page, 'DetailStatus')).to_have_text('detail:0:disabled:quoted')
    expect(control(page, 'DetailScope')).to_have_text('selected:global:1')
    assert page.evaluate('state.enteredName') == 'Grace'
    control(page, 'DetailFirst').fill('Amazing Grace')
    control(page, 'SaveContact').click()
    expect(control(page, 'OtherScope')).to_have_text('other:global')
    expect(control(page, 'HiddenDetail')).to_have_text('saved:0:disabled:quoted')
    saved = backend({'fn': 'api', 'args': ['Contacts', 'list', {}]})['result']
    assert [(r['id'], r['first_name']) for r in saved] == [('one', 'Ada'), ('two', 'Amazing Grace')], saved
    control(page, 'ReturnDetail').click()
    expect(control(page, 'DetailTitle')).to_have_text('Amazing Grace Hopper')
    expect(control(page, 'DetailScope')).to_have_text('selected:global:2')
    control(page, 'ClearDetail').click()
    expect(control(page, 'DetailScope')).to_have_text('blank:global:2')
    control(page, 'BrowseAgain').click()
    expect(control(page, 'BrowseScope')).to_have_text('browse:blank:global')
    contacts.nth(0).click()
    expect(control(page, 'DetailTitle')).to_have_text('Ada Lovelace')
    expect(control(page, 'DetailFirst')).to_have_value('Ada')
    page.reload()
    expect(contacts).to_have_text(['Ada Lovelace', 'Amazing Grace Hopper'])
    contacts.nth(1).click()
    expect(control(page, 'DetailTitle')).to_have_text('Amazing Grace Hopper')
    expect(control(page, 'DetailScope')).to_have_text('selected:global:1')
    page.screenshot(path=str(OUT / 'navigation-context/persisted-contact.png'))


def check_collection_aliases(page, backend):
    rows = control(page,'DraftRows').locator('[data-control="DraftName"]')
    expect(rows).to_have_count(2)
    expect(rows.nth(0)).to_have_value('Draft one')
    expect(rows.nth(1)).to_have_value('Draft two')
    expect(control(page,'DraftRows').locator('[data-control="DraftOwner"]')).to_have_text(['Ada','Grace'])
    expect(control(page,'StandaloneModeDraft')).to_have_js_property('tagName','INPUT')
    expect(control(page,'MaskedExample')).to_have_attribute('type','password')
    expect(control(page,'DraftSummary')).to_have_text('Draft one:0, Draft two:0')
    rows.nth(1).fill('Edited second draft')
    rows.nth(1).press('Tab')
    expect(control(page,'DraftSummary')).to_have_text('Draft one:0, Edited second draft:0')
    control(page,'BumpDrafts').click()
    expect(control(page,'DraftSummary')).to_have_text('Draft one:1, Edited second draft:1')
    control(page,'DraftRows').locator('[data-control="SaveDraftRow"]').nth(1).click()
    expect(control(page,'DraftStatus')).to_have_text('saved')
    records = backend({'fn':'api','args':['Projects','list',{}]})['result']
    assert records[0]['name'] == 'First project' and records[1]['name'] == 'Edited second draft'
    page.reload()
    expect(control(page,'DraftSummary')).to_have_text('Draft one:0, Draft two:0')
    control(page,'RestoreDrafts').click()
    expect(control(page,'DraftSummary')).to_have_text('Draft one:1, Edited second draft:1')
    expect(rows.nth(0)).to_have_value('Draft one')
    expect(rows.nth(1)).to_have_value('Edited second draft')
    control(page,'ConflictingDraft').click()
    expect(control(page,'DraftStatus')).to_have_text('conflict retained draft')
    expect(control(page,'DraftSummary')).to_have_text('Draft one:1, Edited second draft:1')
    page.screenshot(path=str(OUT / 'collection-aliases/restored-and-validated.png'))
    rows.nth(1).focus()
    rows.nth(1).evaluate('el=>el.setSelectionRange(2,7)')
    control(page,'ToggleDraftMode').evaluate('el=>el.click()')
    expect(rows.nth(1)).to_have_js_property('tagName','TEXTAREA')
    assert rows.nth(1).evaluate('el=>document.activeElement===el && el.selectionStart===2 && el.selectionEnd===7')
    expect(control(page,'StandaloneModeDraft')).to_have_js_property('tagName','TEXTAREA')
    expect(control(page,'StandaloneModeDraft')).to_have_value('Standalone draft')
    control(page,'StandaloneModeDraft').fill('Standalone\nsecond line')
    control(page,'StandaloneModeDraft').press('Tab')
    expect(control(page,'ModeChanged')).to_have_text('Standalone\nsecond line')
    rows.nth(1).fill('Multiline draft\nSecond line')
    rows.nth(1).press('Tab')
    control(page,'DraftRows').locator('[data-control="SaveDraftRow"]').nth(1).click()
    expect(control(page,'DraftStatus')).to_have_text('saved')
    records = backend({'fn':'api','args':['Projects','list',{}]})['result']
    assert records[1]['name'] == 'Multiline draft\nSecond line', records
    control(page,'AppendDraft').click()
    expect(rows).to_have_count(3)
    expect(rows.nth(2)).to_have_value('Third draft')
    expect(rows.nth(1)).to_have_value('Multiline draft\nSecond line')
    page.screenshot(path=str(OUT / 'collection-aliases/appended-multiline-draft.png'))


def check_card_layout(page, _backend):
    page.set_viewport_size({'width':640,'height':400})
    first, wide = control(page,'FirstCard'), control(page,'WideCard')
    draft = control(page,'WideDraft')
    def box(name):
        return control(page,name).bounding_box()
    expect(draft).to_have_value('Retain this draft')
    assert first.bounding_box()['x'] == 0 and wide.bounding_box()['x'] == 120
    assert wide.bounding_box()['width'] == 520
    assert first.bounding_box()['height'] == wide.bounding_box()['height'] == 100
    assert box('FullCard')['y'] == 160
    assert box('HiddenCard')['width'] == box('LastCard')['width'] == 320
    draft.fill('Draft survives resizing')
    draft.focus()
    draft.evaluate('el => {window.__cardInput=el; el.setSelectionRange(2,7)}')
    page.set_viewport_size({'width':280,'height':400})
    expect(wide).to_have_css('width','160px')
    assert box('LastCard')['y'] == box('HiddenCard')['y'] + box('HiddenCard')['height']
    assert draft.evaluate('el => el===window.__cardInput && document.activeElement===el && el.selectionStart===2 && el.selectionEnd===7')
    control(page,'ToggleCard').click()
    expect(control(page,'HiddenCard')).to_be_hidden()
    assert box('LastCard')['y'] == 220 and box('LastCard')['width'] == 280
    assert box('FooterCard')['y'] == 360
    control(page,'FooterAction').click()
    expect(control(page,'CapturedDraft')).to_have_text('Draft survives resizing')
    assert control(page,'CardCanvas').evaluate('el => el.scrollTop > 0 && el.scrollWidth === el.clientWidth')
    expect(draft).to_have_value('Draft survives resizing')
    expect(control(page,'BoundedTitle')).to_have_css('overflow','hidden')
    expect(control(page,'BoundedTitle')).to_have_css('white-space','nowrap')
    scrollable = control(page,'ScrollableText')
    expect(scrollable).to_have_css('overflow','auto')
    assert scrollable.evaluate('el => {el.scrollTop=el.scrollHeight; return el.scrollTop > 0}')
    page.screenshot(path=str(OUT / 'card-layout/scrolled-form.png'))


def check_views(page, backend):
    expect(control(page, 'SelectedProject')).to_have_text('')
    expect(control(page, 'ViewRows')).to_have_text('Third project, First project')
    expect(control(page, 'ViewCount')).to_have_text('1')
    control(page, 'ViewSearch').fill('FIRST')
    expect(control(page, 'ViewRows')).to_have_text('First project')
    control(page, 'ViewSearch').fill('absent')
    expect(control(page, 'ViewRows')).to_have_text('')
    control(page, 'ViewSearch').fill('')
    control(page, 'OpenSecond').click()
    expect(control(page, 'ViewRows')).to_have_text('Second project, Third project, First project')
    expect(control(page, 'ViewCount')).to_have_text('2')
    buttons = control(page, 'ProjectGallery').locator('[data-control="SelectProject"]')
    expect(buttons).to_have_text(['Second project', 'Third project', 'First project'])
    buttons.nth(1).click()
    expect(control(page, 'SelectedProject')).to_have_text('Third project')
    page.reload()
    expect(control(page, 'ViewRows')).to_have_text('Second project, Third project, First project')
    expect(control(page, 'SelectedProject')).to_have_text('')
    rows = backend({'fn':'api','args':['Projects','list',{}]})['result']
    assert rows[1]['status'] == 0 and rows[1]['active'] is False
    page.screenshot(path=str(OUT / 'saved-views/filtered-and-reloaded.png'))


def check_relative_views(page, backend):
    names = control(page,'ViewRows')
    expect(names).to_have_text('Third project, Second project')
    control(page,'ViewSearch').fill('SECOND')
    expect(names).to_have_text('Second project')
    control(page,'ViewSearch').fill('')
    buttons = control(page,'ProjectGallery').locator('[data-control="SelectProject"]')
    expect(buttons).to_have_text(['Third project','Second project'])
    buttons.nth(1).click()
    expect(control(page,'SelectedProject')).to_have_text('Second project')
    control(page,'OpenSecond').click()
    expect(names).to_have_text('First project, Third project, Second project')
    rows = backend({'fn':'api','args':['Projects','list',{}]})['result']
    assert next(row for row in rows if row['project']=='project-one')['start__date']=='2026-03-08T15:59:00.000Z'
    page.reload()
    expect(names).to_have_text('First project, Third project, Second project')
    expect(buttons).to_have_text(['First project','Third project','Second project'])
    page.screenshot(path=str(OUT/'relative-saved-views/saved-and-reloaded.png'))
    # At the next local midnight, the oldest row leaves the seven-day range
    # and the formerly future row enters. Persisted dates remain unchanged.
    page.clock.set_fixed_time(datetime.fromisoformat('2026-03-09T04:00:00+00:00'))
    page.reload()
    expect(names).to_have_text('Future project, First project, Third project')
    expect(buttons).to_have_text(['Future project','First project','Third project'])
    assert backend({'fn':'api','args':['Projects','list',{}]})['result']==rows


def check_relationships(page, backend):
    names, count, reverse, status = [control(page,name) for name in ['RelatedNames','RelatedCount','InverseCount','RelatedStatus']]
    expect(control(page,'RelatedProject')).to_have_text('Second project')
    expect(control(page,'RelatedUser')).to_have_text('Grace')
    expect(count).to_have_text('0')
    expect(reverse).to_have_text('0')
    before = {ds:backend({'fn':'api','args':[ds,'list',{}]})['result'] for ds in ['Projects','Users']}
    backend({'fn':'__failNextMutation','args':[]})
    control(page,'AddMember').click()
    expect(status).to_have_text('link failed')
    expect(count).to_have_text('0')
    control(page,'AddMember').click()
    expect(status).to_have_text('linked')
    expect(names).to_have_text('Grace')
    expect(reverse).to_have_text('0')
    control(page,'RefreshUsers').click()
    expect(reverse).to_have_text('1')
    control(page,'ChooseFirstProject').click()
    expect(count).to_have_text('0')
    control(page,'AddMember').click()
    expect(count).to_have_text('1')
    control(page,'ChooseFirstUser').click()
    control(page,'AddMember').click()
    expect(count).to_have_text('2')
    expect(names).to_have_text('Grace, Ada')
    control(page,'AddMember').click()
    page.wait_for_function('async () => await window.__waitForGasIdle()')
    expect(count).to_have_text('2')
    page.reload()
    expect(names).to_have_text('Grace')
    expect(reverse).to_have_text('2')
    backend({'fn':'__failNextMutation','args':[]})
    control(page,'RemoveMember').click()
    expect(status).to_have_text('unlink failed')
    expect(count).to_have_text('1')
    control(page,'RemoveMember').click()
    expect(status).to_have_text('unlinked')
    expect(count).to_have_text('0')
    expect(reverse).to_have_text('2')
    control(page,'RefreshUsers').click()
    expect(reverse).to_have_text('1')
    control(page,'AddReverse').click()
    expect(status).to_have_text('reverse linked')
    expect(reverse).to_have_text('2')
    expect(count).to_have_text('0')
    control(page,'RefreshProjects').click()
    expect(count).to_have_text('1')
    control(page,'RemoveReverse').click()
    expect(status).to_have_text('reverse unlinked')
    expect(reverse).to_have_text('1')
    page.reload()
    expect(count).to_have_text('0')
    expect(reverse).to_have_text('1')
    control(page,'ChooseFirstProject').click()
    expect(names).to_have_text('Grace, Ada')
    for ds in before:
        assert backend({'fn':'api','args':[ds,'list',{}]})['result'] == before[ds]
    links = backend({'fn':'api','args':['Projects','links',{}]})['result']
    assert len(links) == 2 and all(link[1] == 'project-one' for link in links), links
    response = backend({'fn':'api','args':['Users','patch',{'base':{'id':'user-two'},'record':{'fullname':'Grace Hopper'}}]})
    assert 'error' not in response, response
    expect(names).to_have_text('Grace, Ada')
    control(page,'RefreshProjects').click()
    expect(names).to_have_text('Grace Hopper, Ada')
    assert page.evaluate("state.Users.find(row=>row.id==='user-two').fullname") == 'Grace'
    assigned = control(page,'AssignedCount')
    expect(assigned).to_have_text('0')
    control(page,'AssignProject').click()
    expect(status).to_have_text('assigned')
    expect(assigned).to_have_text('1')
    assert page.evaluate('state.Projects[0].owner') is None
    control(page,'ChooseFirstUser').click()
    expect(assigned).to_have_text('0')
    control(page,'AssignProject').click()
    expect(assigned).to_have_text('1')
    control(page,'ChooseSecondUser').click()
    expect(assigned).to_have_text('0')
    control(page,'UnassignProject').click()
    expect(status).to_have_text('unassigned')
    rows = backend({'fn':'api','args':['Projects','list',{}]})['result']
    assert rows[0]['owner']['user'] == 'user-one' and rows[1]['owner'] is None
    control(page,'ChooseFirstUser').click()
    backend({'fn':'__failNextMutation','args':[]})
    control(page,'UnassignProject').click()
    expect(status).to_have_text('unassignment failed')
    expect(assigned).to_have_text('1')
    control(page,'UnassignProject').click()
    expect(status).to_have_text('unassigned')
    expect(assigned).to_have_text('0')
    page.reload()
    expect(assigned).to_have_text('0')
    rows = backend({'fn':'api','args':['Projects','list',{}]})['result']
    assert all(row['owner'] is None for row in rows), rows
    page.screenshot(path=str(OUT / 'many-to-many-relationships/reloaded-memberships.png'))


def setup_planner(backend):
    migration=json.loads((REPO/'tests/fixtures/planner-board.json').read_text())
    result=backend({'fn':'__importPlanner','args':[migration]})
    assert result.get('result')=={'ok':True,'plans':2,'tasks':2}, result
    return {'source':'authored Planner migration fixture','plans':2,'tasks':2}


def check_planner(page, backend):
    for name,label in [('BoardTitle','Task title'),('BoardAssignee','Assignee email'),('BoardDescription','Task description')]:
        expect(control(page,name)).to_have_attribute('aria-label',label)
    for name in ['BoardTitle','BoardAssignee','BoardDescription','BoardCreate','BoardUpdate','BoardTasks']:
        expect(control(page,name)).to_be_visible()
        geometry=control(page,name).bounding_box()
        assert geometry['x'] >= 0 and geometry['x']+geometry['width'] <= page.viewport_size['width'],geometry
    for name in ['BoardCreate','BoardUpdate']:
        assert control(page,name).evaluate('el => el.scrollWidth <= el.clientWidth && el.scrollHeight <= el.clientHeight')
    expect(control(page,'BoardPlans')).to_have_text('Shared inspections')
    expect(control(page,'BoardGroup')).to_have_text('Shared inspections')
    expect(control(page,'BoardBuckets')).to_have_text('Repairs')
    expect(control(page,'BoardCount')).to_have_text('1')
    expect(control(page,'BoardAssigned')).to_have_text('1')
    rows=control(page,'BoardTasks').locator('[data-control="BoardSelect"]')
    expect(rows).to_have_text(['Repair door / 50% / 2 assigned'])
    control(page,'BoardTitle').fill('Repair window')
    control(page,'BoardDescription').fill('Inspection notes\nReplace damaged hinge')
    backend({'fn':'__failNextMutation','args':[]})
    control(page,'BoardCreate').click()
    expect(control(page,'BoardStatus')).to_have_text('create failed')
    expect(control(page,'BoardCount')).to_have_text('1')
    control(page,'BoardCreate').click()
    expect(control(page,'BoardStatus')).to_have_text('created')
    expect(rows).to_have_text(['Repair door / 50% / 2 assigned','Repair window / 0% / 1 assigned'])
    expect(control(page,'BoardCount')).to_have_text('2')
    expect(control(page,'BoardAssigned')).to_have_text('1')
    saved=backend({'fn':'__plannerSnapshot','args':[]})['result']['tasks'][-1]
    assert saved['title']=='Repair window' and saved['assignees']==['user-b']
    assert saved['bucket_id']=='bucket-a' and saved['due_date_time']=='2026-09-12T00:00:00.000Z'
    assert saved['description']=='Inspection notes\nReplace damaged hinge'
    page.reload()
    expect(rows).to_have_count(2)
    rows.nth(1).click()
    control(page,'BoardDescription').fill('Revised details')
    backend({'fn':'__failNextMutation','args':[]})
    control(page,'BoardUpdate').click()
    expect(control(page,'BoardStatus')).to_have_text('update failed')
    assert backend({'fn':'__plannerSnapshot','args':[]})['result']['tasks'][-1]==saved
    control(page,'BoardUpdate').click()
    expect(control(page,'BoardStatus')).to_have_text('updated')
    control(page,'BoardAssignee').fill('outside@example.test')
    control(page,'BoardCreate').click()
    expect(control(page,'BoardStatus')).to_have_text('create failed')
    expect(rows).to_have_count(2)
    page.reload()
    expect(rows).to_have_count(2)
    final=backend({'fn':'__plannerSnapshot','args':[]})['result']['tasks']
    assert len(final)==3 and final[-1]=={**saved,'description':'Revised details'}
    assert final[0]['description']=='Existing notes' and final[1]['title']=='Private task'
    page.screenshot(path=str(OUT/'google-planner/persisted-board.png'))


def setup_directory(backend):
    setup_planner(backend)
    data=json.loads((REPO/'tests/fixtures/google-directory.json').read_text())
    assert backend({'fn':'__importDirectory','args':[data['migration']]})=={'result':{'ok':True,'users':2}}
    return {'source':'authored directory identity mappings and Planner board',
            'googlePeople':'explicit native API response fixtures; no live Google authorization',
            'users':2,'plans':2,'tasks':2}


def check_directory(page,backend):
    data=json.loads((REPO/'tests/fixtures/google-directory.json').read_text())
    people=data['people'];grace=people[1]
    def responses(*items):
        backend({'fn':'__peopleResponses','args':[list(items)]})
    def requests():
        return backend({'fn':'__peopleRequests','args':[]})['result']
    # Authored image returned at the fixture API's photo URL; no network download.
    page.route('https://lh3.googleusercontent.com/test-grace',lambda route:route.fulfill(
        content_type='image/svg+xml',body='<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32"><circle cx="16" cy="16" r="16" fill="teal"/></svg>'))
    expect(control(page,'DirectoryStatus')).to_have_text('ready')
    expect(control(page,'DirectorySearch')).to_have_attribute('aria-label','Search people')
    responses({'method':'listDirectoryPeople','result':{'people':people}})
    control(page,'DirectoryFind').click()
    expect(control(page,'DirectoryStatus')).to_have_text('search complete')
    rows=control(page,'DirectorySelect')
    expect(rows).to_have_text(['Ada Lovelace / business.tester@example.test','Grace Hopper / second@example.test'])
    assert requests()[0]['method']=='listDirectoryPeople'
    responses({'error':'403 Directory permission revoked'})
    control(page,'DirectorySearch').fill('Grace')
    control(page,'DirectoryFind').click()
    expect(control(page,'DirectoryStatus')).to_have_text('search failed')
    expect(rows).to_have_count(2)
    responses({'method':'searchDirectoryPeople','result':{'people':[grace]}})
    control(page,'DirectoryFind').focus()
    page.keyboard.press('Enter')
    expect(control(page,'DirectoryStatus')).to_have_text('search complete')
    expect(rows).to_have_text(['Grace Hopper / second@example.test'])
    assert requests()[0]['args'][0]['query']=='Grace'
    responses({'method':'get','result':grace},{'error':'403 Photo access denied'})
    rows.click()
    expect(control(page,'DirectoryStatus')).to_have_text('assignment failed')
    assert page.evaluate('(state.colTaskAssignments || []).length')==0
    expect(rows).to_have_count(1)
    responses({'method':'get','result':grace},{'method':'get','result':grace})
    rows.click()
    expect(control(page,'DirectoryStatus')).to_have_text('assigned')
    expect(control(page,'DirectoryAssigned')).to_have_text('Grace Hopper')
    expect(rows).to_have_count(0)
    page.wait_for_function('document.querySelector("[data-control=DirectoryPhoto]").naturalWidth === 32')
    assert page.evaluate('state.colUserProfiles[0]')=={
        'app_ref':'user-b','app_email':'second@example.test','app_img':grace['photos'][0]['url'],'app_display_name':'Grace Hopper'}
    assert [request['args'][0] for request in requests()]==['people/200','people/200']
    for name in ['DirectorySearch','DirectoryFind','DirectoryCreate','DirectoryPhoto']:
        expect(control(page,name)).to_be_visible()
        box=control(page,name).bounding_box()
        assert box['width']>0 and box['height']>0 and box['x']>=0 and box['x']+box['width']<=page.viewport_size['width'],box
    backend({'fn':'__failNextMutation','args':[]})
    control(page,'DirectoryCreate').click()
    expect(control(page,'DirectoryStatus')).to_have_text('task failed')
    expect(control(page,'DirectoryTaskCount')).to_have_text('1')
    control(page,'DirectoryCreate').click()
    expect(control(page,'DirectoryStatus')).to_have_text('task created')
    expect(control(page,'DirectoryTaskCount')).to_have_text('2')
    task=backend({'fn':'__plannerSnapshot','args':[]})['result']['tasks'][-1]
    assert task['title']=='Directory assigned repair' and task['assignees']==['user-b']
    page.screenshot(path=str(OUT/'google-directory/assigned-google-person.png'))
    page.reload()
    expect(control(page,'DirectoryTaskCount')).to_have_text('2')
    assert backend({'fn':'__plannerSnapshot','args':[]})['result']['tasks'][-1]==task


def setup_chat(backend):
    data=json.loads((REPO/'tests/fixtures/google-chat.json').read_text())
    assert backend({'fn':'__importChat','args':[data['migration']]})=={'result':{'ok':True,'teams':2,'channels':3}}
    return {'source':'authored source-ID to Google space mappings',
            'googleChat':'explicit native API response fixtures; no real messages or live authorization'}


def check_chat(page,backend):
    data=json.loads((REPO/'tests/fixtures/google-chat.json').read_text())
    spaces={'method':'list','result':{'spaces':data['spaces']}}
    created={'method':'create','result':{'name':'spaces/REPAIRS/messages/idea.1'}}
    def responses(*items):
        backend({'fn':'__chatResponses','args':[list(items)]})
    def requests():
        return backend({'fn':'__chatRequests','args':[]})['result']
    def messages():
        return backend({'fn':'__chatMessages','args':[]})['result']
    expect(control(page,'ChatStatus')).to_have_text('ready')
    for name,label in [('ChatTeam','Choose team'),('ChatChannel','Choose channel'),
                       ('ChatSubject','Notification subject'),('ChatDescription','Idea description')]:
        expect(control(page,name)).to_have_attribute('aria-label',label)
    responses({'method':'list','error':'403 Chat is disabled'})
    control(page,'ChatLoadTeams').click()
    expect(control(page,'ChatStatus')).to_have_text('teams failed')
    responses(spaces)
    control(page,'ChatLoadTeams').click()
    expect(control(page,'ChatStatus')).to_have_text('teams ready')
    expect(control(page,'ChatTeam').locator('option')).to_have_text(['Facilities','Operations'])
    control(page,'ChatTeam').select_option(index=0)
    responses(spaces,spaces)
    control(page,'ChatLoadChannels').click()
    expect(control(page,'ChatStatus')).to_have_text('channels ready')
    expect(control(page,'ChatTeamName')).to_have_text('Facilities')
    expect(control(page,'ChatChannel').locator('option')).to_have_text(['Facilities','Repairs'])
    expect(control(page,'ChatRowChannel').locator('option')).to_have_text(['Facilities','Repairs'])
    control(page,'ChatRowChannel').select_option(index=1)
    expect(control(page,'ChatPreviewId')).to_have_text('repairs')
    expect(control(page,'ChatRowChannel')).to_have_value('repairs')
    page.evaluate('window.__chatRow=document.querySelector("[data-control=ChatRowChannel]")')
    control(page,'ChatChannel').select_option(index=1)
    assert page.evaluate('val("ChatTeam").selected.id')=='team-a'
    assert page.evaluate('val("ChatChannel").selected.id')=='repairs'
    control(page,'ChatSubject').fill('Repair door')
    control(page,'ChatDescription').fill('Replace hinge & tighten bolts')
    responses(spaces,{'method':'create','error':'403 Posting permission revoked'})
    control(page,'ChatPost').click()
    expect(control(page,'ChatStatus')).to_have_text('send failed')
    assert messages()==[] and [r['method'] for r in requests()]==['list','create']
    responses(spaces,created)
    control(page,'ChatPost').focus();page.keyboard.press('Enter')
    expect(control(page,'ChatStatus')).to_have_text('sent')
    expect(control(page,'ChatMessageId')).to_have_text('spaces/REPAIRS/messages/idea.1')
    expect(control(page,'ChatRowChannel')).to_have_value('repairs')
    assert page.evaluate('window.__chatRow===document.querySelector("[data-control=ChatRowChannel]")')
    saved=messages();assert len(saved)==1
    message,parent,options=saved[0]['request']
    assert parent=='spaces/REPAIRS' and set(options)=={'requestId'}
    assert message=={'text':'**Repair door**\n\nA new employee idea has been created\\!  \n  \n**Description**  \nReplace hinge \\& tighten bolts',
                     'markupSyntax':'MARKUP_SYNTAX_MARKDOWN'}
    page.screenshot(path=str(OUT/'google-chat/native-notification.png'))
    responses()
    control(page,'ChatDescription').fill('<at>Everyone</at>')
    control(page,'ChatPost').click()
    expect(control(page,'ChatStatus')).to_have_text('send failed')
    assert requests()==[] and messages()==saved
    for name in ['ChatTeam','ChatChannel','ChatPost','ChatMessageId']:
        expect(control(page,name)).to_be_visible()
        box=control(page,name).bounding_box()
        assert box['width']>0 and box['height']>0 and box['x']>=0 and box['x']+box['width']<=page.viewport_size['width'],box
    page.reload()
    expect(control(page,'ChatStatus')).to_have_text('ready')
    assert messages()==saved


def check_horizontal_gallery(page,_backend):
    for name,wrap,count in [('LoadingLogos',1,3),('WrappedLogos',2,6)]:
        gallery=control(page,name)
        expect(gallery).to_have_attribute('data-gallery-layout','horizontal')
        expected_height=(48+20)*wrap+20
        page.wait_for_function('([name,height]) => {const r=document.querySelector(`[data-control="${name}"]`).getBoundingClientRect(); return r.width===224 && r.height===height;}',arg=[name,expected_height])
        buttons=control(page,name+'Select');expect(buttons).to_have_count(count)
        host=gallery.bounding_box()
        for index in range(count):
            row=buttons.nth(index);expect(row).to_be_visible();bounds=row.bounding_box()
            assert bounds['width']==bounds['height']==48,bounds
            assert bounds['x']==host['x']+20+(index//wrap)*68,bounds
            assert bounds['y']==host['y']+20+(index%wrap)*68,bounds
        buttons.last.click()
        expect(control(page,'SelectedLogo')).to_have_text('ABCDEF'[count-1])
    for _ in range(10): control(page,'LayoutTick').click()
    page.wait_for_timeout(500)
    assert control(page,'LoadingLogos').bounding_box()['width']==224
    assert page.evaluate('document.documentElement.scrollWidth')<=page.viewport_size['width']
    assert page.evaluate('document.documentElement.scrollHeight')<=page.viewport_size['height']
    page.screenshot(path=str(OUT/'horizontal-gallery/stable-template-geometry.png'),full_page=True)


def main():
    subprocess.run([sys.executable, str(REPO / "tests/fixtures/build.py")], check=True, capture_output=True)
    cases = [("business-form", REPO / "tests/fixtures/fixtureForm.msapp", check_form),
             ("business-charts", REPO / "tests/fixtures/fixtureCharts.msapp", check_charts),
             ("record-scopes", REPO / "tests/fixtures/fixtureScopes.msapp", check_scopes)]
    cases.append(("editable-gallery", REPO / "tests/fixtures/fixtureGallery.msapp", check_gallery))
    cases.append(("timer-lifecycle", REPO / "tests/fixtures/fixtureTimer.msapp", check_timers, True))
    cases.append(("local-draft-storage", REPO / "tests/fixtures/fixtureStorage.msapp", check_storage))
    cases.append(("dataverse-contract", REPO / "tests/fixtures/fixtureDataverse.msapp", check_dataverse))
    cases.append(('many-to-many-relationships', REPO / 'tests/fixtures/fixtureRelationships.msapp', check_relationships))
    cases.append(("source-formulas", REPO / "tests/fixtures/fixtureSourceFormulas.msapp", check_source_formulas))
    cases.append(("responsive-canvas", REPO / "tests/fixtures/fixtureCanvas.msapp", check_canvas))
    cases.append(("scaled-canvas", REPO / "tests/fixtures/fixtureScaledCanvas.msapp", check_scaled_canvas))
    cases.append(("navigation-context", REPO / "tests/fixtures/fixtureNavigation.msapp", check_navigation))
    cases.append(('card-layout', REPO / 'tests/fixtures/fixtureCardLayout.msapp', check_card_layout))
    cases.append(('collection-aliases', REPO / 'tests/fixtures/fixtureCollectionAliases.msapp', check_collection_aliases))
    cases.append(('google-planner', REPO/'tests/fixtures/fixturePlanner.msapp', check_planner,
                  False,None,None,None,setup_planner,'UTC'))
    cases.append(('google-directory', REPO/'tests/fixtures/fixtureDirectory.msapp', check_directory,
                  False,None,None,None,setup_directory,'UTC'))
    cases.append(('google-chat', REPO/'tests/fixtures/fixtureChat.msapp', check_chat,
                  False,None,None,None,setup_chat,'UTC'))
    cases.append(('horizontal-gallery',REPO/'tests/fixtures/fixtureHorizontalGallery.msapp',check_horizontal_gallery))
    cases.append(("saved-views", REPO / "tests/fixtures/fixtureViews.msapp", check_views,
                  False, None, None, REPO / 'tests/fixtures/fixtureViews.solution.zip'))
    cases.append(('relative-saved-views', REPO/'tests/fixtures/fixtureRelativeViews.msapp', check_relative_views,
                  False, None, None, REPO/'tests/fixtures/fixtureRelativeViews.solution.zip', None,
                  'America/New_York', '2026-03-08T16:00:00+00:00'))
    helpdesk = REPO / "samples/real/helpdesk.msapp"
    if helpdesk.exists():
        cases.append(("helpdesk", helpdesk, check_helpdesk))
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        results = [run_case(browser, *case) for case in cases]
        def fail_capture(page, _backend):
            def fail_screenshot(**_kwargs):
                raise RuntimeError('deliberate screenshot failure')
            page.screenshot = fail_screenshot
            raise RuntimeError('deliberate journey failure')
        failed = run_case(browser, 'evidence-failure-gate', REPO / 'tests/fixtures/fixtureA.msapp', fail_capture)
        assert failed['status'] == 'fail' and failed['error'] == 'deliberate journey failure'
        assert failed['screenshot'] == {'status':'fail','error':'deliberate screenshot failure'}
        assert (OUT / 'evidence-failure-gate/result.json').exists()
        def late_console_error(page, _backend):
            screenshot = page.screenshot
            def capture(**kwargs):
                page.evaluate("console.error('deliberate late capture error')")
                return screenshot(**kwargs)
            page.screenshot = capture
        late = run_case(browser,'late-runtime-error-gate',REPO / 'tests/fixtures/fixtureA.msapp',late_console_error)
        assert late['status'] == 'fail' and 'deliberate late capture error' in late['consoleErrors']
        def pending_callback_error(page, _backend):
            page.evaluate("google.script.run.withSuccessHandler(() => console.error('deliberate pending callback error')).whoami(); void 0")
        pending = run_case(browser,'pending-runtime-error-gate',REPO / 'tests/fixtures/fixtureA.msapp',pending_callback_error)
        assert pending['status'] == 'fail' and 'deliberate pending callback error' in pending['consoleErrors']
        assert pending['serverCallDrain']['status'] == 'pass'
        browser.close()
    (OUT / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    return int(any(result["status"] != "pass" for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
