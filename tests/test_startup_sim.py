"""Startup simulation: run the generated app's JS against a stub DOM in Node.

Catches the "blank screen in production" bug class that string assertions
cannot see: missing runtime exports (bind), row-scoped controls registered at
top level ("item is not defined"), evaluator crashes at bootstrap.

The sim builds the static DOM from Screens.html, loads fx-stdlib + fx-charts +
gas-runtime + App.js exactly like the deployed page does, fires
DOMContentLoaded with a faithful async google.script.run mock, then asserts:
  - no "is not defined" errors on the console
  - exactly the start screen is visible
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

SIM_TEMPLATE = """
const elements = {};
const consoleErrors = [];
function makeEl(tag, attrs) {
  return {
    tag, attrs, style: {}, children: [], listeners: {}, textContent: '',
    getAttribute(k) { return attrs[k] !== undefined ? attrs[k] : null; },
    setAttribute(k, v) { attrs[k] = String(v); },
    removeAttribute(k) { delete attrs[k]; },
    addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); },
    appendChild(c) { this.children.push(c); },
    querySelector() { return null; },
    querySelectorAll(sel) {
      if (sel === '[data-screen]') return Object.values(elements).filter(e => e.attrs['data-screen']);
      if (sel.startsWith('[data-control=')) {
        const name = sel.match(/"([^"]+)"/)[1];
        const hit = Object.values(elements).find(e => e.attrs['data-control'] === name);
        return hit ? [hit] : [];
      }
      return [];
    },
    classList: { add(){}, remove(){} },
    click() { (this.listeners.click || []).forEach(f => f()); },
  };
}
global.document = {
  addEventListener(ev, fn) { global.__domReady = fn; },
  querySelector(sel) {
    if (sel === '[data-screen]') return Object.values(elements).find(e => e.attrs['data-screen']) || null;
    if (sel.startsWith('[data-control=')) {
      const name = sel.match(/"([^"]+)"/)[1];
      return Object.values(elements).find(e => e.attrs['data-control'] === name) || null;
    }
    return null;
  },
  querySelectorAll(sel) {
    if (sel === '[data-screen]') return Object.values(elements).filter(e => e.attrs['data-screen']);
    return [];
  },
  createElement: (t) => makeEl(t, {}),
  body: makeEl('body', {}),
  getElementById: () => null,
};
global.window = global;
global.console.error = (...a) => { consoleErrors.push(a.map(String).join(' ').slice(0, 140)); };
global.console.warn = () => {};
let handlers = {};
const runner = new Proxy({}, {
  get(_t, prop) {
    if (prop === 'withSuccessHandler') return (cb) => { handlers.ok = cb; return runner; };
    if (prop === 'withFailureHandler') return (cb) => { handlers.err = cb; return runner; };
    return (...args) => {
      const ok = handlers.ok, err = handlers.err;
      handlers = {};
      setTimeout(() => {
        if (String(prop) === 'whoami') { if (ok) ok({ email: '', fullName: '', pictureUrl: '' }); return; }
        if (ok) ok([]);
      }, 0);
    };
  },
});
global.google = { script: { run: runner } };

const screensSrc = __SCREENS__;
const screenRe = /<section data-screen="([^"]+)" style="display:none">/g;
let sm;
while ((sm = screenRe.exec(screensSrc)) !== null) {
  elements['screen:' + sm[1]] = makeEl('section', { 'data-screen': sm[1] });
}
const ctrlRe = /data-control="([^"]+)"/g;
let cm; const seen = new Set();
while ((cm = ctrlRe.exec(screensSrc)) !== null) {
  if (!seen.has(cm[1])) { seen.add(cm[1]); elements['ctrl:' + cm[1]] = makeEl('div', { 'data-control': cm[1] }); }
}

(0, eval)(__FX__);
(0, eval)(__CHARTS__);
(0, eval)(__RT__);
(0, eval)(__APP__);
global.__domReady();

function visibleScreens() {
  return Object.values(elements)
    .filter(e => e.attrs['data-screen'] && (!e.style.display || e.style.display === ''))
    .map(e => e.attrs['data-screen']);
}

setTimeout(async () => {
  const behavior = {};
  const next = elements['ctrl:Button1'];
  const back = elements['ctrl:ButtonBack'];
  if (next && back) {
    behavior.initialText = elements['ctrl:Label1'].textContent;
    behavior.initialCounter = FXRuntime.state.counter;
    next.click();
    await new Promise(resolve => setTimeout(resolve, 20));
    behavior.afterNextCounter = FXRuntime.state.counter;
    behavior.afterNextVisible = visibleScreens();
    back.click();
    await new Promise(resolve => setTimeout(resolve, 20));
    behavior.afterBackVisible = visibleScreens();
  }
  const visible = visibleScreens();
  const refErrors = consoleErrors.filter(e => e.includes('is not defined'));
  console.log(JSON.stringify({ visible, refErrors, totalConsoleErrors: consoleErrors.length, behavior }));
  process.exit(0);
}, 80);
"""


def _strip_script_wrapper(path: Path) -> str:
    return path.read_text().replace("<script>\n", "").replace("\n</script>", "")


@pytest.fixture(scope="module", autouse=True)
def _build_fixtures():
    subprocess.run([sys.executable, str(FIXTURES / "build.py")], check=True)


def _simulate(msapp: Path) -> dict:
    from pfx2gas.analyze import analyze
    from pfx2gas.parse import parse
    from pfx2gas.synth.build import synthesize
    from pfx2gas.unpack import unpack

    static = Path(__file__).parent.parent / "static"
    out = synthesize(analyze(parse(unpack(msapp))), Path(tempfile.mkdtemp()) / "Sim")
    sim = (SIM_TEMPLATE
           .replace("__SCREENS__", json.dumps((out / "Screens.html").read_text()))
           .replace("__FX__", json.dumps((static / "fx-stdlib.js").read_text()))
           .replace("__CHARTS__", json.dumps((static / "fx-charts.js").read_text()))
           .replace("__RT__", json.dumps((static / "gas-runtime.js").read_text()))
           .replace("__APP__", json.dumps(_strip_script_wrapper(out / "App.js.html"))))
    sim_path = Path(tempfile.mkdtemp()) / "startup-sim.js"
    sim_path.write_text(sim)
    result = subprocess.run(["node", str(sim_path)], capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, f"sim crashed: {result.stderr[:400]}"
    return json.loads(result.stdout)


def test_fixture_a_startup_clean(ir_a=None):
    verdict = _simulate(FIXTURES / "fixtureA.msapp")
    assert verdict["refErrors"] == [], f"ReferenceErrors at startup: {verdict['refErrors']}"
    assert verdict["visible"] == ["Screen1"], verdict
    assert verdict["totalConsoleErrors"] == 0, verdict
    assert verdict["behavior"] == {
        "initialText": "Hello",
        "initialCounter": 1,
        "afterNextCounter": 2,
        "afterNextVisible": ["Screen2"],
        "afterBackVisible": ["Screen1"],
    }


def test_fixture_b_startup_clean():
    """Data app with a gallery: row-scoped children must not leak to top level."""
    verdict = _simulate(FIXTURES / "fixtureB.msapp")
    assert verdict["refErrors"] == [], f"ReferenceErrors at startup: {verdict['refErrors']}"
    assert verdict["visible"] == ["Screen1"], verdict
    assert verdict["totalConsoleErrors"] == 0, verdict


def test_generated_business_charts_startup_clean():
    verdict = _simulate(FIXTURES / "fixtureCharts.msapp")
    assert verdict["refErrors"] == [], verdict
    assert verdict["visible"] == ["Charts"], verdict
    assert verdict["totalConsoleErrors"] == 0, verdict


def test_generated_record_scopes_startup_clean():
    verdict = _simulate(FIXTURES / "fixtureScopes.msapp")
    assert verdict["refErrors"] == [], verdict
    assert verdict["visible"] == ["Scopes"], verdict
    assert verdict["totalConsoleErrors"] == 0, verdict


def test_generated_local_draft_cache_loads_missing_cache_without_errors():
    verdict = _simulate(FIXTURES / "fixtureStorage.msapp")
    assert verdict["refErrors"] == [], verdict
    assert verdict["visible"] == ["DraftScreen"], verdict
    assert verdict["totalConsoleErrors"] == 0, verdict


def test_generated_gallery_edits_second_row_and_queues_parent_once(tmp_path):
    from pfx2gas.analyze import analyze
    from pfx2gas.parse import parse
    from pfx2gas.startup_sim import simulate_project
    from pfx2gas.synth.build import synthesize
    from pfx2gas.unpack import unpack

    ir = analyze(parse(unpack(FIXTURES / "fixtureGallery.msapp")))
    project = synthesize(ir, tmp_path / "Gallery")
    row = {"gallery": "ContactRows", "row": 1}
    verdict = simulate_project(project, [{"id": "edit-second-row", "steps": [
        {"action": "expectValue", "control": "RowFirst", "equals": "Grace", **row},
        {"action": "setValue", "control": "RowFirst", "value": "Amazing Grace", **row},
        {"action": "expectDataRow", "source": "Contacts", "where": {"id": "two", "first_name": "Amazing Grace"}},
        {"action": "expectDataRow", "source": "Contacts", "where": {"id": "one", "first_name": "Ada"}},
        {"action": "setValue", "control": "RowLast", "value": "Admiral", **row},
        {"action": "click", "control": "UnrelatedUpdate"},
        {"action": "expectValue", "control": "RowLast", "equals": "Admiral", **row},
        {"action": "click", "control": "RowSave", **row},
        {"action": "expectState", "key": "parentCalls", "equals": 1},
        {"action": "expectState", "key": "parentSawFinished", "equals": True},
        {"action": "expectState", "key": "selectedName", "equals": "Amazing Grace"},
        {"action": "expectDataRow", "source": "Contacts", "where": {"id": "two", "last_name": "Admiral"}},
    ]}])
    assert verdict["consoleErrors"] == [], verdict
    assert verdict["journeyResults"][0]["status"] == "pass", verdict
    controls = {c.name: c for s in ir.screens for c in s.walk_controls()}
    for name, property_name in [("RowFirst", "Default"), ("RowFirst", "OnChange"),
                                ("RowSave", "OnSelect"), ("RowLast", "DisplayMode")]:
        assert controls[name].properties[property_name].emission_status == "emitted"


def test_generated_timers_initialize_data_and_leave_loading_screen(tmp_path):
    from pfx2gas.analyze import analyze
    from pfx2gas.parse import parse
    from pfx2gas.startup_sim import simulate_project
    from pfx2gas.synth.build import synthesize
    from pfx2gas.unpack import unpack

    ir = analyze(parse(unpack(FIXTURES / "fixtureTimer.msapp")))
    assert {"timerStarted", "timerEnded"}.issubset(ir.global_vars)
    assert next(ds for ds in ir.data_sources if ds.name == "TimerRows").origin == "collection"
    verdict = simulate_project(synthesize(ir, tmp_path / "Timer"), [{"id": "loading-flow", "steps": [
        {"action": "expectScreen", "screen": "LoadingScreen"},
        {"action": "expectState", "key": "timerStarted", "equals": True},
        {"action": "wait", "milliseconds": 350},
        {"action": "expectScreen", "screen": "ReadyScreen"},
        {"action": "expectText", "control": "ReadyMessage", "equals": "Ready"},
        {"action": "expectState", "key": "timerEnded", "equals": True},
        {"action": "click", "control": "StartRepeat"},
        {"action": "wait", "milliseconds": 400},
        {"action": "expectState", "key": "cycles", "equals": 3},
        {"action": "click", "control": "ResetRepeat"},
        {"action": "expectState", "key": "cycles", "equals": 0},
    ]}])
    assert verdict["consoleErrors"] == [], verdict
    assert verdict["journeyResults"][0]["status"] == "pass", verdict


@pytest.mark.parametrize("target", ["startup", "screen", "hidden", "button", "timer"])
def test_untranslatable_behavior_cannot_silently_pass_runtime_checks(tmp_path, target):
    from pfx2gas.analyze import analyze
    from pfx2gas.ir import AppIR, ControlNode, ScreenNode, FxExpr
    from pfx2gas.startup_sim import simulate_project
    from pfx2gas.synth.build import synthesize

    broken = FxExpr(raw="Set(x, @broken)", kind="behavior")
    screen = ScreenNode(name="Main")
    ir = AppIR(name="BrokenBehavior", screens=[screen], start_screen="Main")
    steps = []
    if target == "startup":
        ir.on_start = broken
    elif target == "screen":
        screen.on_visible = broken
    elif target == "hidden":
        screen.properties['OnHidden'] = broken
        ir.screens.append(ScreenNode(name='Other'))
        screen.controls = [ControlNode(name='LeaveScreen', type='Button', properties={
            'OnSelect': FxExpr(raw='Navigate(Other)', kind='behavior')})]
        steps = [{'action': 'click', 'control': 'LeaveScreen'}]
    elif target == "button":
        screen.controls = [ControlNode(name="BrokenButton", type="Button", properties={"OnSelect": broken})]
        steps = [{"action": "click", "control": "BrokenButton"}]
    else:
        screen.controls = [ControlNode(name="BrokenTimer", type="Timer", properties={
            "OnTimerEnd": broken, "Duration": FxExpr(raw="150"), "AutoStart": FxExpr(raw="true")})]
        steps = [{"action": "wait", "milliseconds": 250}]
    verdict = simulate_project(synthesize(analyze(ir), tmp_path / "Broken"), [{"id": "observe-failure", "steps": steps}])
    assert any("formula could not be translated" in error for error in verdict["allConsoleErrors"]), verdict
    if target in {"button", "timer", "hidden"}:
        assert verdict["journeyResults"][0]["status"] == "fail", verdict


def test_shared_simulator_runs_declarative_critical_journey(tmp_path):
    """The soak runner uses the same generated-app interaction evidence."""
    from pfx2gas.analyze import analyze
    from pfx2gas.parse import parse
    from pfx2gas.startup_sim import simulate_project
    from pfx2gas.synth.build import synthesize
    from pfx2gas.unpack import unpack

    out = synthesize(
        analyze(parse(unpack(FIXTURES / "fixtureA.msapp"))), tmp_path / "Sim"
    )
    verdict = simulate_project(out, [{
        "id": "next-and-back",
        "steps": [
            {"action": "expectScreen", "screen": "Screen1"},
            {"action": "expectText", "control": "Label1", "equals": "Hello"},
            {"action": "click", "control": "Button1"},
            {"action": "expectState", "key": "counter", "equals": 2},
            {"action": "expectScreen", "screen": "Screen2"},
            {"action": "click", "control": "ButtonBack"},
            {"action": "expectScreen", "screen": "Screen1"},
        ],
    }])
    assert verdict["visible"] == ["Screen1"]
    assert verdict["consoleErrors"] == []
    assert verdict["journeyResults"] == [{
        "id": "next-and-back",
        "status": "pass",
        "steps": [
            {"action": "expectScreen", "status": "pass"},
            {"action": "expectText", "status": "pass"},
            {"action": "click", "status": "pass"},
            {"action": "expectState", "status": "pass"},
            {"action": "expectScreen", "status": "pass"},
            {"action": "click", "status": "pass"},
            {"action": "expectScreen", "status": "pass"},
        ],
    }]


def test_generated_form_create_validate_reset_and_last_submit(tmp_path):
    """Boot and exercise the generated Form/DataCard path end to end."""
    from pfx2gas.analyze import analyze
    from pfx2gas.parse import parse
    from pfx2gas.startup_sim import simulate_project
    from pfx2gas.synth.build import synthesize
    from pfx2gas.unpack import unpack

    ir = analyze(parse(unpack(FIXTURES / "fixtureForm.msapp")))
    contacts = next(ds for ds in ir.data_sources if ds.name == "Contacts")
    assert [(field.name, field.type) for field in contacts.fields] == [
        ("id", "text"), ("FirstName", "text"), ("LastName", "text")
    ]
    out = synthesize(ir, tmp_path / "FixtureForm")
    verdict = simulate_project(out, [{
        "id": "create-contact",
        "steps": [
            {"action": "expectValue", "control": "InputFirst", "equals": "Ada"},
            {"action": "expectValue", "control": "InputLast", "equals": "Lovelace"},
            {"action": "setValue", "control": "InputFirst", "value": "Augusta"},
            {"action": "click", "control": "ButtonSubmit"},
            {"action": "expectDataRow", "source": "Contacts",
             "where": {"id": "sim-seeded-1", "first_name": "Augusta",
                       "last_name": "Lovelace"}},
            {"action": "click", "control": "ButtonNew"},
            {"action": "setValue", "control": "InputFirst", "value": "Grace"},
            {"action": "click", "control": "ButtonSubmit"},
            {"action": "expectState", "key": "saveError",
             "equals": "Last Name is required."},
            {"action": "setValue", "control": "InputLast", "value": "temporary"},
            {"action": "click", "control": "ButtonResetForm"},
            {"action": "expectValue", "control": "InputFirst", "equals": ""},
            {"action": "expectValue", "control": "InputLast", "equals": ""},
            {"action": "setValue", "control": "InputFirst", "value": "Grace"},
            {"action": "setValue", "control": "InputLast", "value": "Hopper"},
            {"action": "click", "control": "ButtonSubmit"},
            {"action": "expectState", "key": "savedName", "equals": "Hopper"},
            {"action": "expectDataRow", "source": "Contacts",
             "where": {"first_name": "Grace", "last_name": "Hopper"}},
        ],
    }])
    assert verdict["consoleErrors"] == []
    assert verdict["journeyResults"][0]["status"] == "pass", verdict

    app_js = (out / "App.js.html").read_text()
    assert "FXRuntime.registerForm('Form1'" in app_js
    assert "await submitForm('Form1')" in app_js
    assert "FX.field(val('Form1').last_submit, 'last_name')" in app_js
    assert "var displayFields = ['FirstName']" in app_js
    assert "FXRuntime.applyDefaultSelection" in app_js
    assert re.search(r'<select data-control="ComboPeople"[^>]*\bmultiple',
                     (out / "Screens.html").read_text())
