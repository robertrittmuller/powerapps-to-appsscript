"""Real Chromium regression journeys using generated client AND server code.

Run with ./pfx2gas browser. Screenshots are converted-output evidence, not
original-app visual baselines. The spreadsheet service is a test double.
"""
from __future__ import annotations

import json
import hashlib
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


def run_case(browser, name, source, journey):
    project = synthesize(analyze(parse(unpack(source))), OUT / name / "project")
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
    context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="en-US")
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
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    result = {"app": name, "status": "pass", "backend": "generated Code.gs + Sheets test double",
              "originalVisualComparison": "unassessed", "evidenceType": "chromium-generated-client-and-server",
              "inputSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "converterSourceSha256": converter_fingerprint(), "browserVersion": browser.version}
    try:
        page.goto("https://converted.test/")
        journey(page, backend)
        assert not errors, errors
    except Exception as error:
        result.update(status="fail", error=str(error) or type(error).__name__)
    finally:
        result["consoleErrors"] = errors
        page.screenshot(path=str(OUT / name / "result.png"), full_page=True)
        result["controls"] = page.locator('[data-screen]:visible [data-control]').evaluate_all(
            "els => els.map(el => {const r=el.getBoundingClientRect(); return {name:el.dataset.control,"
            "text:el.innerText, x:r.x,y:r.y,width:r.width,height:r.height,"
            "font:getComputedStyle(el).fontFamily};})")
        (OUT / name / "result.json").write_text(json.dumps(result, indent=2) + "\n")
        context.close()
        server.terminate()
        server.wait(timeout=5)
    print(name, result["status"], result.get("error", ""), flush=True)
    return result


def main():
    subprocess.run([sys.executable, str(REPO / "tests/fixtures/build.py")], check=True, capture_output=True)
    cases = [("business-form", REPO / "tests/fixtures/fixtureForm.msapp", check_form),
             ("business-charts", REPO / "tests/fixtures/fixtureCharts.msapp", check_charts),
             ("record-scopes", REPO / "tests/fixtures/fixtureScopes.msapp", check_scopes)]
    helpdesk = REPO / "samples/real/helpdesk.msapp"
    if helpdesk.exists():
        cases.append(("helpdesk", helpdesk, check_helpdesk))
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        results = [run_case(browser, *case) for case in cases]
        browser.close()
    (OUT / "results.json").write_text(json.dumps(results, indent=2) + "\n")
    return int(any(result["status"] != "pass" for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
