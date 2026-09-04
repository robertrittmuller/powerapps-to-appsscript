"""Boot a synthesized project in Node against a minimal browser/Apps Script shim.

This is runtime evidence, not a string assertion: the generated runtime and
App.js are evaluated, DOMContentLoaded fires, async server calls resolve, and
the expected start screen must become the only visible screen.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


SIM_TEMPLATE = r"""
const elements = {};
const consoleErrors = [];
function makeEl(tag, attrs) {
  return {
    tag, tagName: String(tag).toUpperCase(), attrs, style: {}, children: [], listeners: {},
    textContent: '', value: '', selectedOptions: [],
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
global.console.error = (...a) => { consoleErrors.push(a.map(String).join(' ').slice(0, 240)); };
global.console.warn = () => {};
let handlers = {};
const runner = new Proxy({}, {
  get(_t, prop) {
    if (prop === 'withSuccessHandler') return (cb) => { handlers.ok = cb; return runner; };
    if (prop === 'withFailureHandler') return (cb) => { handlers.err = cb; return runner; };
    return (...args) => {
      const ok = handlers.ok;
      handlers = {};
      setTimeout(() => {
        if (String(prop) === 'whoami') {
          if (ok) ok({ email: '', fullName: '', pictureUrl: '' });
          return;
        }
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
const ctrlRe = /<([a-z]+)[^>]*data-control="([^"]+)"/g;
let cm; const seen = new Set();
while ((cm = ctrlRe.exec(screensSrc)) !== null) {
  if (!seen.has(cm[2])) {
    seen.add(cm[2]);
    elements['ctrl:' + cm[2]] = makeEl(cm[1], { 'data-control': cm[2] });
  }
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
  console.log(JSON.stringify({ visible, refErrors, consoleErrors }));
  process.exit(0);
}, 120);
"""


def _script_body(path: Path) -> str:
    text = path.read_text()
    if text.startswith("<script>\n") and text.endswith("\n</script>"):
        return text[len("<script>\n"):-len("\n</script>")]
    return text


def simulate_project(out_dir: str | Path) -> dict:
    """Execute one generated project and return its observed startup state."""
    out = Path(out_dir)
    sim = (SIM_TEMPLATE
           .replace("__SCREENS__", json.dumps((out / "Screens.html").read_text()))
           .replace("__FX__", json.dumps(_script_body(out / "fx-stdlib.js.html")))
           .replace("__CHARTS__", json.dumps(_script_body(out / "fx-charts.js.html")))
           .replace("__RT__", json.dumps(_script_body(out / "gas-runtime.js.html")))
           .replace("__APP__", json.dumps(_script_body(out / "App.js.html"))))
    sim_path = Path(tempfile.mkdtemp()) / "startup-sim.js"
    sim_path.write_text(sim)
    result = subprocess.run(
        ["node", str(sim_path)], capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"startup simulator crashed: {result.stderr[:400]}")
    return json.loads(result.stdout)
