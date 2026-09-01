# pfx2gas — Power Apps → Google Apps Script converter

`pfx2gas` converts a Microsoft Power Apps **canvas app** (`.msapp` file) into a
runnable **Google Apps Script web app**: an HtmlService single-page UI, a
`google.script.run` server API, and a Google Sheets data layer — plus an
honest, per-formula **conversion report** of what was converted, what was
approximated, and what needs human attention.

It is a deterministic transpiler pipeline (unpack → parse → analyze →
synthesize → validate) with an optional LLM fallback for formulas the rule
engine can't map. The LLM never writes files; it can only propose a
replacement for a single formula, which is syntax-checked before acceptance.

## How it works

```
app.msapp ──▶ unpack ──▶ parse ──▶ analyze ──▶ synthesize ──▶ validate ──▶ output/<App>/
            (ZIP of    (pa.yaml  (IR + global   (Code.gs,      (node --check,
             pa.yaml)   → IR)     vars, data     Screens.html,   structure,
                                  sources)       App.js, ...)    stub census)
```

- **Unpack** — a `.msapp` is a ZIP archive; `src/*.pa.yaml` files are the app's
  source (per Microsoft's canvas-app YAML format).
- **Parse** — controls, properties, and Power Fx expressions become a typed IR.
- **Analyze** — discovers global variables (`Set`/`Collect`), infers data-source
  fields from `Patch`/`Collect`/dotted references, and transpiles every formula
  with a coverage ledger of what succeeded.
- **Synthesize** — emits the Apps Script project (see layout below).
- **Validate** — `node --check` every generated script, structural checks,
  count of unsupported-function stubs.
- **Report** — `conversion-report.md`: per-formula status table, data mapping,
  manual follow-ups, capacity notes.

## Requirements

- Python 3.11+ and [uv](https://docs.astral.sh/uv/)
- Node.js ≥ 18 (generated JS is syntax-checked with `node --check`)
- For deployment only: [clasp](https://github.com/google/clasp)
  (`npm install -g @google/clasp`) and a one-time `clasp login`

## Install

```bash
git clone <this repo>
cd powerapps-to-appsscript
uv sync          # creates .venv and installs dependencies
uv run pytest -q # verify: 46 tests pass
node --test tests/js/test-fx-stdlib.js tests/js/test-gas-runtime.js  # 18 more
```

## Quick start

Export your app from Power Apps Studio (**Save As → This computer**) to get
`YourApp.msapp`, then:

```bash
uv run pfx2gas convert YourApp.msapp -o output/YourApp
```

This prints a summary, writes the converted project to `output/YourApp/`, and
exits non-zero if the validator finds problems. Review
`output/YourApp/conversion-report.md` next — it is the contract for the
remaining manual work.

Deploy with clasp:

```bash
cd output/YourApp
clasp login                                  # once, opens a browser
clasp create --title "YourApp" --type webapp # or reuse an existing scriptId
clasp push --force                           # uploads Code.gs, *.html, etc.
clasp open-script                            # run setup() once in the editor
                                             # (creates the data workbook)
clasp deploy                                 # prints the web app URL
```

The first `setup()` run creates one Google Sheet workbook with a tab per data
source and stores its ID in script properties; the API layer reads/writes it.

## CLI reference

```
pfx2gas convert <file.msapp> [-o DIR] [--report-only] [--no-llm]
pfx2gas validate <project_dir>
```

| Option | Meaning |
|---|---|
| `-o, --output DIR` | Output directory (default `./output/<AppName>`) |
| `--report-only` | Produce only `conversion-report.md`, no project files |
| `--no-llm` | Disable the LLM fallback; unmapped formulas stay stubs |
| `validate <dir>` | Re-run structural/syntax checks on a converted project |

Exit codes: `0` success (validator PASS), `1` validation failure or bad input.

## What the converter produces

```
output/<App>/
├── appsscript.json       # manifest: webapp config + Sheets scopes
├── Code.gs               # doGet() + api(ds, op, payload) dispatcher + CRUD
├── DataInit.gs           # setup(): creates the data workbook + tabs once
├── Index.html            # shell page (HtmlService template includes)
├── Screens.html          # one <section data-screen> per screen, controls
├── App.js.html           # transpiled formulas: bindings, evaluators, handlers
├── gas-runtime.js.html   # static runtime: promise shim, router, state, toasts
├── fx-stdlib.js.html     # static FX.* Power Fx helper library
└── conversion-report.md  # fidelity ledger — read this before shipping
```

Static files (`gas-runtime`, `fx-stdlib`) are shared runtime, not generated
per-app; everything else is derived from your app.

## The conversion report

Every formula lands in exactly one bucket:

- **converted** — rule-transpiled to JS calling the `FX.*` stdlib.
- **partial** — transpiled with the LLM fallback (confidence + notes included).
- **stubbed** — emitted as `FX.unsupported('<Function>')`, which throws a clear
  runtime error instead of silently misbehaving, and is listed under
  *Manual follow-ups*.

The report also contains the data mapping (original source → Sheet tab +
inferred fields) and Apps Script capacity notes (6-min executions, 30
concurrent, 30-s web-app response budget — read whole-tab data sizes
accordingly).

## LLM fallback (optional)

Unmapped formulas can be translated by any OpenAI-compatible chat API.
Configure via environment variables, then run without `--no-llm`:

```bash
export PFX2GAS_LLM_BASE_URL="https://openrouter.ai/api/v1"  # or api.openai.com/v1
export PFX2GAS_LLM_API_KEY="sk-or-..."                      # provider key
export PFX2GAS_LLM_MODEL="openai/gpt-5.6-luna"              # any chat model

uv run pfx2gas convert YourApp.msapp
```

Guarantees: the model receives the function-coverage table (single source of
truth with the transpiler) plus the generated app's real globals (`state`,
data-layer `api*` calls, `val()`, navigation, `toast`), returns one JSON object
per formula, and its JS is accepted only if it passes `node --check` (value
formulas must be single expressions; behavior formulas may be statements).
It may refuse when translation is genuinely impossible — the formula then
stays a documented stub. All calls are logged to `.runs/llm-calls.jsonl`
with confidence and notes; LLM-touched formulas appear in the report as
*partial* with their confidence so you know what to review first.

## Supported Power Fx surface (v1)

Rule-transpiled today (~70 functions via the `FX.*` stdlib):

- **Logic** `If`, `Switch`, `IfError`, `IsBlank`, `IsEmpty`, `Coalesce`, `With`
- **Tables** `Filter`, `ForAll`, `LookUp`, `CountRows`, `CountIf`, `Concat`,
  `First`, `Last`, `Sort`, `SortByColumns`, `Distinct`, `Sum`, `Average`,
  `AddColumns`, `Sequence`, `Split`
- **Text** `Concatenate`, `Upper`, `Lower`, `Trim`, `Left`, `Right`, `Mid`,
  `Len`, `Find`, `Substitute`, `Replace`, `Text` (number/date formats),
  `Proper`, `Char`, `GUID`, `EncodeUrl`, `PlainText`
- **Math** `Abs`, `Int`, `Round`/`RoundUp`/`RoundDown`, `Mod`, `Sqrt`, `Power`,
  `Min`, `Max`, `Value`, `Rand`
- **Dates** `Today`, `Now`, `Year`, `Month`, `Day`, `Hour`, `Minute`,
  `Weekday`, `DateAdd`, `DateDiff`, `Date`, `Time`
- **Colors** `RGBA`, `ColorFade`; **enums** (`Color.X`, `Font.X`,
  `Font.'Open Sans'`, …) emitted as literals
- **Behavior** `Set`, `UpdateContext`, `Navigate`, `Back`, `Notify`,
  `Patch`, `Remove`, `RemoveIf`, `Collect`, `ClearCollect`, `Refresh`,
  `SubmitForm`, `Select` (as data-layer/control calls), `Launch`
  (opens a new tab)

Anything not in the map (e.g. `Choices()`, custom `Environment.*` functions,
`ShowHostInfo`) becomes a documented stub via the coverage ledger — never
silently wrong. Adding functions is one entry in
`src/pfx2gas/fx/function_map.py` plus a JS helper in `static/fx-stdlib.js`.

**Controls:** Label, Button, TextInput, TextArea, Dropdown, CheckBox,
DatePicker, Gallery (row template), Image, Icon, HtmlText, Form.

## Out of scope (flagged, not silently dropped)

- Model-driven apps and apps whose source is only the retired `*.fx.yaml`
  format (re-save the app in Studio to upgrade it)
- Power Automate flows, Dataverse-specific features, custom components with
  complex property sets
- Delegation semantics: data is read whole-tab (client-side filtering);
  keep Sheets under ~5,000 rows or extend `Code.gs` with server-side filters
- Media assets beyond basic images

## Development

```bash
uv run pytest -q                    # Python suite (61 tests)
node --test tests/js/*.js           # JS runtime suite (18 tests)
uv run pytest tests/test_e2e.py -q  # end-to-end CLI runs on synthetic fixtures
```

The test fixtures are synthetic `.msapp` files built by
`tests/fixtures/build.py` (A: navigation/state, B: data sources + gallery,
C: exotic functions for the stub path, D: a real Studio-export shape —
`Properties.json` manifest, `Src\` paths, `Screens:` wrapper, `_EditorState`
auxiliary file, versioned control types like `Classic/Icon@2.5.0`). The Power
Fx transpiler is table-driven — add cases to `tests/test_fx_transpiler.py`.

**Real-app samples:** `samples/real/` (gitignored) holds real `.msapp` files
for soak testing, fetched from the public
[sunilshetty07/Microsoft-PowerApps-Canvas](https://github.com/sunilshetty07/Microsoft-PowerApps-Canvas)
repo (editable-grid, expandable-nav, modern-card, svg-app, sentiment-feedback —
1,100+ formulas total, 97%+ rule-transpiled). Download any `.msapp` into that
folder to test against it.

Layout:

```
src/pfx2gas/
├── unpack.py        # stage 1: .msapp ZIP → pa.yaml sources
├── parse.py         # stage 2: pa.yaml → AppIR
├── analyze.py       # stage 3: globals, data sources, transpile + ledger
├── fx/              # lexer.py, emitter.py, function_map.py (coverage map)
├── synth/           # server.py (Code.gs), client.py (UI/JS), build.py
├── validate.py      # stage 5
├── report.py        # stage 6: conversion-report.md
├── llm.py           # optional fallback seam
└── cli.py           # argparse CLI
static/              # shared runtime shipped into every converted app
tests/               # pytest + node --test suites, fixtures
```

## Status

v0.1.0 — the pipeline end-to-end on canvas apps in the supported subset.
Fidelity on real apps grows with the function map; the report tells you
exactly where you stand for any given app.
