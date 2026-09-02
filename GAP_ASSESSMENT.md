# pfx2gas — Gap Assessment (2026-09-02)

What stands between the current converter and "fully converts a Power Apps canvas
app to a working Apps Script web app." Every claim below was verified against the
code and the real-app corpus (`samples/real/`, 10 apps, ~22k formulas) on this date.

## Current state (verified)

| Check | Result |
|---|---|
| Python suite (`uv run pytest -q`) | 90 passed |
| JS runtime suite (`node --test tests/js/*.js`) | 18 passed, 0 fail |
| Formula coverage on 10-app corpus | **21,905 / 21,940 rule-transpiled (99.8%)** |
| Distinct unmapped functions in corpus | 2 (`Environment.cr4d6_sumofnaturalnumber`, `ShowHostInfo` — both host/Dataverse-bound, fine as stubs) |
| Ignored properties | 538 / 21,955 (2.5%) |
| E2E convert (helpdesk.msapp, 6 screens, 5,535 formulas) | exits 0, validator PASS |
| Deployed a converted app via clasp | **never done** (clasp not installed; plan milestone M4 open) |
| CI | none (no `.github/`) |

Plan milestones: M1–M3 done. M4 ("two real apps converted, deployed via clasp,
report reviewed, v0.1.0 tag") **not achieved** — no tag, no deploy.

The headline 99.8% is formula *transpilation* coverage, not app fidelity. The gaps
below are why a "100% converted" app can still be non-functional.

---

## P0 — Correctness of what "converted" means

### 1. Every conversion ships a broken `DataInit.gs` (verified bug)
`src/pfx2gas/synth/server.py:147` emits `SpreadsheetApp.create({app_name!r} — data);`
— a literal em-dash inside a JS statement. `node --check` on the generated file:
`SyntaxError: missing ) after argument list`. The intended code was presumably
`SpreadsheetApp.create('<name> — data')` with the em-dash inside the string literal.
One-line template fix.

### 2. The validator never syntax-checks `.gs` files (verified blind spot)
`src/pfx2gas/validate.py` runs `node --check` only on `*.js.html` (it strips
`<script>` wrappers first). `Code.gs` / `DataInit.gs` are checked for structure
only (`function doGet()` present), so bug #1 sailed through as "validator PASS".
Fix: copy each `.gs` to a temp `.js` and run the same `js_syntax_ok()` check.

### 3. Legacy `.msapp`: every TextInput becomes a Label (verified)
The legacy template map (`src/pfx2gas/legacy.py`) maps template name `text` →
`Label` unconditionally. In legacy apps the `text` template is a **TextInput**
whenever it has `Mode` / `Default` / `HintText` properties (verified in
helpdesk.msapp: `TextInputTitle_2`, template `text`, has all three → rendered as
a `<span>` you cannot type into). Every form input in the 3 legacy corpus apps
(helpdesk, clean-ui, and any other binary-format app) is affected. Fix: map
`text` → `TextInput` when those properties are present, else `Label`.

### 4. Data layer is skeletal: zero inferred fields on every real app
- helpdesk.msapp: 12 data sources, **0 inferred fields on all 12** → generated
  `DataInit.gs` creates a workbook with **no tabs** (`specs = []`), and every
  `api(ds, …)` call throws `no sheet named …` at runtime.
- wordle / tic-tac-toe: all `col*` collections also land as 0-field "data sources".
- The authoritative schema is present and unused: legacy
  `References\DataSources.json` carries `Schema: *[Field:type]`,
  `OrderedColumnNames`, and embedded sample `Data` per source. Modern pa.yaml
  apps' `Collect`/`ClearCollect` shapes are likewise not turned into field defs.
- Also missing: the **collection vs external source distinction**. `col*`
  collections are client-side state arrays and should NOT become Sheet tabs;
  external sources (SharePoint/Excel/static sample tables) should.

### 5. No real modern (pa.yaml) app with external data in the corpus
All three data-bearing real samples are legacy binary format. The data layer is
only exercised by synthetic fixtures. Acceptance bar ("works the same way as the
original") is unproven for the most common real-world case: a modern app backed
by a SharePoint list. Add such a sample (or convert one of the user's own) to the
soak set.

## P1 — Behavior & delivery

### 6. First-party component templates render as empty divs (37 instances)
ProgressBar-horiz/vert, MENU, TILES1, TILES2, BUSCADOR (helpdesk, clean-ui).
Their custom properties transpile as "converted" but mean nothing without
component rendering — the helpdesk nav menu and tile dashboards are blank boxes.
Needed: a component-template emulation layer driven by `ComponentsMetadata.json`
+ `References\Templates.json` (each template is a small control tree with custom
properties), or at minimum report-level surfacing of exactly what each component
did.

### 7. Deploy path (M4) never exercised end-to-end
Nothing verifies the generated project actually deploys and serves: clasp
create/push/deploy, HtmlService include names, `appsscript.json` webapp config,
oauth scopes vs what `setup()` needs, `setup()` actually creating the workbook.
This is the single biggest unknown between "validator PASS" and "works".

### 8. User() fidelity
`Code.gs whoami()` returns `email` only; `fullName` / `pictureUrl` are always
empty, so helpdesk's header shows a blank user name and missing avatar. Fix:
derive a display name from the email local part at minimum; optionally Directory
API (Workspace) for real names/avatars, documented as consumer-account-limited.

### 9. No CI
Both suites are green locally but run nowhere automatically. A GitHub Actions
workflow (pytest + node --test on push/PR) is cheap and protects the ledger.

## P2 — Parity polish (known, documented, lower stakes)

- **Ignored props, top offenders:** `LayoutMode` x81, `Format` x20, `Mode` x19,
  `DataField`/`DisplayName`/`Required`/`Update` x11 each (form semantics),
  chart-series props (`barMaxValue`, `ItemColorSet`, `Explode`…), `TemplateSize`,
  `WrapCount`, `Transition`, `LoadingSpinner`.
- **Theme/typography parity:** clean system stylesheet instead of app theme.
- **Responsive reflow** not reproduced (absolute positioning only).
- **Chart interiors** now render (Pie/Bar/Line via fx-charts.js) but series
  styling props ignored.
- **Delegation:** whole-tab reads, ~5k-row guidance — fine for the corpus, needs
  server-side filtering for bigger data.
- **Power Automate flows** inside apps: out of scope, flagged only.
- **LLM review seams barely exercised:** 16 logged LLM calls ever; behavioral-
  equivalence review + QA scenarios have not run against a real app at scale
  (needs a configured `.env` + full convert without `--no-llm`).

---

## Recommended order of attack

| # | Item | Effort | Impact |
|---|---|---|---|
| 1 | Fix em-dash `DataInit.gs` template bug (#1) | minutes | unbreaks every deployment |
| 2 | Add `.gs` node --check to validator (#2) | small | closes the blind spot permanently |
| 3 | Legacy `text`+Mode → TextInput disambiguation (#3) | small | legacy forms usable |
| 4 | Field inference from `References\DataSources.json` Schema + collection field inference; collection-vs-source distinction (#4) | medium | data layer actually works |
| 5 | Clasp deploy smoke test on helpdesk (#7) | small–medium | closes M4; first live app |
| 6 | Component-template emulation for MENU/TILES/ProgressBar (#6) | large | restores real UI on 2 corpus apps |
| 7 | CI workflow (#9), User() enrichment (#8) | small | protects + polishes |
| 8 | Modern data-app sample, LLM review at scale, remaining props (#5, P2) | ongoing | raises the bar toward pixel/behavior parity |

Items 1–4 turn "99.8% formulas transpiled" into "the converted app actually
runs with data", which is the user's stated acceptance bar. Items 5–7 make that
true for the corpus's two most business-like apps.
