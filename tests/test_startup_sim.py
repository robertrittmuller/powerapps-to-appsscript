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

setTimeout(() => {
  const visible = Object.values(elements)
    .filter(e => e.attrs['data-screen'] && (!e.style.display || e.style.display === ''))
    .map(e => e.attrs['data-screen']);
  const refErrors = consoleErrors.filter(e => e.includes('is not defined'));
  console.log(JSON.stringify({ visible, refErrors, totalConsoleErrors: consoleErrors.length }));
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


def test_fixture_b_startup_clean():
    """Data app with a gallery: row-scoped children must not leak to top level."""
    verdict = _simulate(FIXTURES / "fixtureB.msapp")
    assert verdict["refErrors"] == [], f"ReferenceErrors at startup: {verdict['refErrors']}"
    assert verdict["visible"] == ["Screen1"], verdict
    assert verdict["totalConsoleErrors"] == 0, verdict
