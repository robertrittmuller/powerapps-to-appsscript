"""Boot a synthesized project in Node against a minimal browser/Apps Script shim.

This is runtime evidence, not a string assertion: the generated runtime and
App.js are evaluated, DOMContentLoaded fires, async server calls resolve, and
the expected start screen must become the only visible screen.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path


SIM_TEMPLATE = r"""
const elements = {};
const consoleErrors = [];
function makeEl(tag, attrs) {
  return {
    tag, tagName: String(tag).toUpperCase(), attrs, style: {}, children: [], listeners: {},
    textContent: '', innerHTML: '', value: '', selectedOptions: [],
    getAttribute(k) { return attrs[k] !== undefined ? attrs[k] : null; },
    setAttribute(k, v) { attrs[k] = String(v); },
    removeAttribute(k) { delete attrs[k]; },
    addEventListener(ev, fn) { (this.listeners[ev] = this.listeners[ev] || []).push(fn); },
    click() { (this.listeners.click || []).forEach(fn => fn()); },
    change() { (this.listeners.change || []).forEach(fn => fn()); },
    appendChild(c) { this.insertBefore(c, null); },
    insertBefore(c, before) {
      if (c.parentNode) c.remove();
      const index = before ? this.children.indexOf(before) : this.children.length;
      this.children.splice(index, 0, c); c.parentNode = this;
    },
    remove() {
      if (this.parentNode) {
        const children = this.parentNode.children;
        children.splice(children.indexOf(this), 1); this.parentNode = null;
      }
    },
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
  createElement(t) {
    const el = makeEl(t, {});
    Object.defineProperty(el, 'innerHTML', {
      get() { return this.__html || ''; },
      set(value) {
        this.__html = String(value || '');
        this.firstElementChild = this.__html.includes('class="fx-row"') ? makeRow(this.__html) : null;
      },
    });
    return el;
  },
  body: makeEl('body', {}),
  getElementById: id => id === 'fx-storage-context'
    ? {textContent: JSON.stringify({appId: 'simulated-script', user: 'simulated-user'})} : null,
};
global.window = global;
// Functional browser-storage test double; a new simulator process starts with
// a clean profile. Cross-page reload persistence is covered by Chromium.
const savedCache = new Map();
global.localStorage = {
  get length() {return savedCache.size;}, key: i => [...savedCache.keys()][i] ?? null,
  getItem: key => savedCache.has(key) ? savedCache.get(key) : null,
  setItem: (key, value) => savedCache.set(key, String(value)),
  removeItem: key => savedCache.delete(key),
};
global.console.error = (...a) => { consoleErrors.push(a.map(String).join(' ').slice(0, 240)); };
global.console.warn = () => {};
// Stable randomness makes startup evidence repeatable. Apps still exercise the
// same Rand/RandBetween code path, but select the first eligible sample row.
Math.random = () => 0;
const serverData = __SERVER_DATA__;
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
        if (String(prop) === 'api') {
          const ds = args[0], op = args[1], payload = args[2] || {};
          const rows = serverData[ds] || (serverData[ds] = []);
          if (op === 'list') { if (ok) ok(JSON.parse(JSON.stringify(rows))); return; }
          if (op === 'create') {
            const saved = Object.assign({}, payload.record || {});
            if (rows.some(row => Object.prototype.hasOwnProperty.call(row, 'id'))
                && (saved.id === undefined || saved.id === null || saved.id === '')) {
              saved.id = 'sim-created-' + (rows.length + 1);
            }
            rows.push(saved); if (ok) ok(JSON.parse(JSON.stringify(saved))); return;
          }
          if (op === 'patch') {
            const base = payload.base || {}, record = payload.record || {};
            const found = rows.find(row => base.id != null && String(row.id) === String(base.id));
            const saved = found ? Object.assign(found, record) : Object.assign({}, base, record);
            if (!found) rows.push(saved);
            if (ok) ok(JSON.parse(JSON.stringify(saved))); return;
          }
          if (op === 'remove') {
            const id = payload.record && payload.record.id;
            const index = rows.findIndex(row => id != null && String(row.id) === String(id));
            if (index >= 0) rows.splice(index, 1);
            if (ok) ok({ok: index >= 0}); return;
          }
          if (op === 'removeIf') {
            const ids = (payload.ids || []).map(String);
            for (let i = rows.length - 1; i >= 0; i--) {
              if (ids.includes(String(rows[i].id))) rows.splice(i, 1);
            }
            if (ok) ok({ok: true}); return;
          }
        }
        if (ok) ok([]);
      }, 0);
    };
  },
});
global.google = { script: { run: runner } };

const screensSrc = __SCREENS__;
function decodeAttr(value) {
  return String(value).replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
}
function parseAttrs(source) {
  const attrs = {};
  const attrRe = /([:\w-]+)="([^"]*)"/g;
  let match;
  while ((match = attrRe.exec(source)) !== null) attrs[match[1]] = decodeAttr(match[2]);
  return attrs;
}
function hydrateInlineStyle(el) {
  String(el.attrs.style || '').split(';').forEach(function (declaration) {
    const split = declaration.indexOf(':');
    if (split < 0) return;
    const rawName = declaration.slice(0, split).trim();
    const value = declaration.slice(split + 1).trim();
    const name = rawName.replace(/-([a-z])/g, (_m, letter) => letter.toUpperCase());
    if (name) el.style[name] = value;
  });
  return el;
}
const screenRe = /<section data-screen="([^"]+)" style="display:none">/g;
let sm;
while ((sm = screenRe.exec(screensSrc)) !== null) {
  elements['screen:' + sm[1]] = makeEl('section', { 'data-screen': sm[1] });
}
const ctrlRe = /<([a-z]+)([^>]*data-control="([^"]+)"[^>]*)>/g;
let cm; const seen = new Set();
while ((cm = ctrlRe.exec(screensSrc)) !== null) {
  if (!seen.has(cm[3])) {
    seen.add(cm[3]);
    elements['ctrl:' + cm[3]] = hydrateInlineStyle(makeEl(cm[1], parseAttrs(cm[2])));
  }
}

function makeRow(markup) {
  const row = makeEl('div', { class: 'fx-row' });
  row.__controls = {};
  const matcher = /<([a-z]+)([^>]*data-control="([^"]+)"[^>]*)>/g;
  let match;
  while ((match = matcher.exec(markup)) !== null) {
    const child = hydrateInlineStyle(makeEl(match[1], parseAttrs(match[2])));
    child.type = child.attrs.type || '';
    row.__controls[match[3]] = child;
  }
  row.querySelector = function (selector) {
    const match = selector.match(/^\[data-control="([^"]+)"\]/);
    return match ? this.__controls[match[1]] || null : null;
  };
  row.querySelectorAll = function (selector) {
    if (selector === 'input, textarea, select') return Object.values(this.__controls)
      .filter(el => ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName));
    return [];
  };
  return row;
}

// Give gallery controls enough DOM behavior to execute their generated row
// templates. This catches the production class where an app boots cleanly but
// every data card is visually empty.
const galleryRows = {};
const galleryRe = /<div data-control="([^"]+)"([^>]*)class="fx-gallery">/g;
let gm;
while ((gm = galleryRe.exec(screensSrc)) !== null) {
  const name = gm[1];
  const host = elements['ctrl:' + name];
  if (!host || galleryRows[name]) continue;
  const templateStart = screensSrc.indexOf('<template>', galleryRe.lastIndex);
  const templateEnd = screensSrc.indexOf('</template>', templateStart);
  if (templateStart < 0 || templateEnd < 0) continue;
  const rowMarkup = screensSrc.slice(templateStart + '<template>'.length, templateEnd).trim();
  const template = { innerHTML: rowMarkup };
  const rowsEl = makeEl('div', { class: 'fx-rows' });
  host.querySelector = (selector) => selector === 'template' ? template
    : selector === '.fx-rows' ? rowsEl : null;
  host.attrs = Object.assign(host.attrs, parseAttrs(gm[2]));
  host.__fxRows = rowsEl;
  galleryRows[name] = rowsEl;
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
function pause(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

async function runJourneys(journeys) {
  const results = [];
  for (const journey of journeys) {
    const result = { id: journey.id, status: 'pass', steps: [] };
    const errorsBefore = consoleErrors.length;
    try {
      for (const step of journey.steps || []) {
        const target = step.gallery
          ? ((galleryRows[step.gallery] || {}).children || [])[Number(step.row || 0)]?.__controls[step.control]
          : elements['ctrl:' + step.control];
        if (step.action === 'wait') {
          const milliseconds = Number(step.milliseconds);
          if (!Number.isFinite(milliseconds) || milliseconds < 0 || milliseconds > 10000)
            throw new Error('journey wait must be between 0 and 10000 ms');
          await pause(milliseconds);
        } else if (step.action === 'click' || step.action === 'change') {
          const el = target;
          if (!el) throw new Error('control not found: ' + step.control);
          el[step.action]();
          await pause(50);
        } else if (step.action === 'setValue') {
          const el = target;
          if (!el) throw new Error('control not found: ' + step.control);
          if (typeof step.value === 'boolean') el.checked = step.value;
          else el.value = step.value == null ? '' : String(step.value);
          el.change();
          await pause(10);
        } else if (step.action === 'expectValue') {
          const el = target;
          const actual = el ? (typeof step.equals === 'boolean' ? !!el.checked : String(el.value)) : null;
          const expected = typeof step.equals === 'boolean' ? step.equals : String(step.equals);
          if (actual !== expected) {
            throw new Error('expected ' + step.control + ' value ' + JSON.stringify(expected)
              + ', got ' + JSON.stringify(actual));
          }
        } else if (step.action === 'expectScreen') {
          const actual = visibleScreens();
          if (actual.length !== 1 || actual[0] !== step.screen) {
            throw new Error('expected screen ' + step.screen + ', got ' + JSON.stringify(actual));
          }
        } else if (step.action === 'expectText') {
          const el = target;
          const actual = el ? String(el.textContent) : null;
          if (actual !== String(step.equals)) {
            throw new Error('expected ' + step.control + ' text ' + JSON.stringify(step.equals)
              + ', got ' + JSON.stringify(actual));
          }
        } else if (step.action === 'expectGalleryRows') {
          const rowsEl = galleryRows[step.control];
          const count = rowsEl ? rowsEl.children.length : 0;
          if (count < Number(step.min || 1)) {
            throw new Error('expected at least ' + (step.min || 1) + ' rows in '
              + step.control + ', got ' + count);
          }
          if (step.contains) {
            const text = rowsEl.children.map(row => Object.values(row.__controls || {})
              .map(el => String(el.textContent || '')).join(' ')).join(' ');
            if (!text.includes(String(step.contains))) {
              throw new Error('expected ' + step.control + ' rows to contain '
                + JSON.stringify(step.contains) + ', got ' + JSON.stringify(text));
            }
          }
        } else if (step.action === 'expectGalleryControlStyle') {
          const rowsEl = galleryRows[step.gallery];
          const row = rowsEl && rowsEl.children[Number(step.row || 0)];
          const el = row && row.__controls && row.__controls[step.control];
          const actual = el && el.style ? String(el.style[step.property] || '') : null;
          if (actual !== String(step.equals)) {
            throw new Error('expected ' + step.gallery + '[' + (step.row || 0) + '].'
              + step.control + ' style.' + step.property + '=' + JSON.stringify(step.equals)
              + ', got ' + JSON.stringify(actual));
          }
        } else if (step.action === 'expectChart') {
          const el = elements['ctrl:' + step.control];
          const cfg = el ? JSON.parse(el.getAttribute('data-chart') || '{}') : {};
          if (!el) throw new Error('chart control not found: ' + step.control);
          if (step.type && cfg.type !== step.type) {
            throw new Error('expected ' + step.control + ' chart type ' + step.type
              + ', got ' + cfg.type);
          }
          if (step.contains && !String(el.innerHTML || '').includes(String(step.contains))) {
            throw new Error('expected ' + step.control + ' chart output to contain '
              + JSON.stringify(step.contains));
          }
          if (String(el.innerHTML || '').includes('No data')) {
            throw new Error(step.control + ' rendered No data');
          }
        } else if (step.action === 'expectImageSource') {
          const el = elements['ctrl:' + step.control];
          const source = el && el.getAttribute('src') || '';
          if (!source.startsWith(String(step.startsWith || ''))) {
            throw new Error('expected ' + step.control + ' source to start with '
              + JSON.stringify(step.startsWith) + ', got ' + JSON.stringify(source.slice(0, 60)));
          }
        } else if (step.action === 'expectState') {
          const actual = FXRuntime.state[step.key];
          if (JSON.stringify(actual) !== JSON.stringify(step.equals)) {
            throw new Error('expected state.' + step.key + '=' + JSON.stringify(step.equals)
              + ', got ' + JSON.stringify(actual));
          }
        } else if (step.action === 'expectDataRow') {
          const rows = FXRuntime.state[step.source] || [];
          const wanted = step.where || {};
          const found = rows.some(row => Object.keys(wanted).every(
            key => JSON.stringify(row && row[key]) === JSON.stringify(wanted[key])));
          if (!found) {
            throw new Error('expected row in ' + step.source + ' matching '
              + JSON.stringify(wanted) + ', got ' + JSON.stringify(rows));
          }
        } else {
          throw new Error('unsupported journey action: ' + step.action);
        }
        result.steps.push({ action: step.action, status: 'pass' });
      }
      if (consoleErrors.length > errorsBefore) {
        throw new Error('runtime errors: ' + consoleErrors.slice(errorsBefore).join('; '));
      }
    } catch (err) {
      result.status = 'fail';
      result.error = String(err && err.message ? err.message : err);
    }
    results.push(result);
  }
  return results;
}

setTimeout(async () => {
  const startupVisible = visibleScreens();
  const startupConsoleErrors = consoleErrors.slice();
  const journeyResults = await runJourneys(__JOURNEYS__);
  const visible = Object.values(elements)
    .filter(e => e.attrs['data-screen'] && (!e.style.display || e.style.display === ''))
    .map(e => e.attrs['data-screen']);
  const refErrors = startupConsoleErrors.filter(e => e.includes('is not defined'));
  console.log(JSON.stringify({
    visible: startupVisible,
    finalVisible: visible,
    refErrors,
    consoleErrors: startupConsoleErrors,
    allConsoleErrors: consoleErrors,
    journeyResults,
  }));
  process.exit(0);
}, 120);
"""


def _script_body(path: Path) -> str:
    text = path.read_text()
    if text.startswith("<script>\n") and text.endswith("\n</script>"):
        return text[len("<script>\n"):-len("\n</script>")]
    return text


def _seeded_server_data(out: Path) -> dict[str, list[dict]]:
    """Read the rows setup() would create, for a faithful server API shim."""
    source = (out / "DataInit.gs").read_text()
    match = re.search(r"\bvar specs = (.*?);\n\s*specs\.forEach", source, re.DOTALL)
    if not match:
        return {}
    specs = json.loads(match.group(1))
    seeded: dict[str, list[dict]] = {}
    for spec in specs:
        headers = [field[0] for field in spec.get("fields", [])]
        seeded[spec["name"]] = [
            {
                header: row[index] if index < len(row) else ""
                for index, header in enumerate(headers)
            }
            for row in spec.get("rows", [])
        ]
        for index, row in enumerate(seeded[spec["name"]], start=1):
            if "id" in row and row["id"] in {"", None}:
                row["id"] = f"sim-seeded-{index}"
    return seeded


def simulate_project(
    out_dir: str | Path, journeys: list[dict] | None = None
) -> dict:
    """Execute generated code and optionally exercise declarative journeys.

    Supported journey actions include ``click``, ``change``, ``setValue``,
    ``expectScreen``, ``expectText``, ``expectValue``, ``expectState``,
    ``expectDataRow``, ``expectGalleryRows``, ``expectGalleryControlStyle``,
    ``expectChart``, and ``expectImageSource``. The returned ``visible`` and
    ``consoleErrors`` fields
    are startup snapshots, so later interaction failures do not get
    misreported as a failure to boot.
    """
    out = Path(out_dir)
    sim = (SIM_TEMPLATE
           .replace("__SCREENS__", json.dumps((out / "Screens.html").read_text()))
           .replace("__FX__", json.dumps(_script_body(out / "fx-stdlib.js.html")))
           .replace("__CHARTS__", json.dumps(_script_body(out / "fx-charts.js.html")))
           .replace("__RT__", json.dumps(_script_body(out / "gas-runtime.js.html")))
           .replace("__APP__", json.dumps(_script_body(out / "App.js.html")))
           .replace("__SERVER_DATA__", json.dumps(_seeded_server_data(out)))
           .replace("__JOURNEYS__", json.dumps(journeys or [])))
    sim_path = Path(tempfile.mkdtemp()) / "startup-sim.js"
    sim_path.write_text(sim)
    result = subprocess.run(
        ["node", str(sim_path)], capture_output=True, text=True, timeout=120
    )
    if result.returncode != 0:
        raise RuntimeError(f"startup simulator crashed: {result.stderr[:400]}")
    return json.loads(result.stdout)
