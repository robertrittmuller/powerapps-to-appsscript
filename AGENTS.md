# AGENTS.md — guidance for AI agents working on pfx2gas

pfx2gas converts Microsoft Power Apps canvas apps (`.msapp`) into runnable
Google Apps Script web apps (HtmlService UI + `google.script.run` API +
Sheets data layer) with an honest per-formula fidelity ledger.

- Read `README.md` for architecture and CLI usage, `GAP_ASSESSMENT.md` for
  the current roadmap/known gaps (kept current) before planning work.
- Plan of record: `~/.hermes/plans/2026-09-01_132008-powerapps-to-appsscript-agent.md`
  (M1–M4 complete; tags `v0.1.0`, `v0.1.1`).
- Test counts cited below drift; check `./pfx2gas test` output rather than
  trusting this file.

## Hard rules

1. **Never let the LLM write generated code.** The deterministic pipeline is
   the source of truth. LLM seams are review-only (behavioral equivalence,
   QA scenarios) or a fallback for single formulas whose output is
   `node --check`-gated and ledgered. Do not weaken these guardrails.
2. **Every "converted" claim needs runtime evidence.** The user's acceptance
   bar is *behavioral fidelity*, not function coverage. String assertions on
   generated files are not proof — boot the generated app
   (`tests/test_startup_sim.py`) and/or deploy before claiming it works.
3. **Production bugs get a bug-class gate in the same commit** (see
   `scripts/check_runtime_consistency.py`, validator's manifest-JSON rule),
   plus a pinpoint regression test.
4. **Container-first.** The user runs nothing locally except Docker and a
   browser. All commands go through `./pfx2gas`; never suggest host installs.

## Runtime environment (verified 2026-09-03)

- **Containers are the canonical runtime.** Image `pfx2gas:latest`:
  `python:3.11-slim` + Node 20 binaries (from `node:20-slim`) + uv + clasp.
  Host Node (26.x) / Python (3.12) differ — do not assume host versions.
- **clasp is NOT version-pinned** (`npm install -g @google/clasp` at build;
  3.4.1 as of writing) — expect minor behavior drift across builds.
- CI (`.github/workflows/ci.yml`): `ubuntu-latest`, Python 3.11, Node 20,
  `astral-sh/setup-uv`, two jobs — `test` (suites + consistency + soak) and
  `container` (image build + in-container suite + CLI/wrapper smoke, with
  `PFX2GAS_UID/GID=1001` for the runner user).
- Pushing changes under `.github/workflows/` requires the stored PAT to keep
  the `workflow` scope (fine-grained: Workflows read/write); reading run
  status requires Actions:read.

## Commands

```bash
./pfx2gas build      # rebuild image — REQUIRED after changing src/ or static/
./pfx2gas test       # pytest + node --test + consistency gate (mounted repo)
./pfx2gas soak       # fetch real samples + convert/validate all
./pfx2gas validate output/HelpDesk
./pfx2gas convert samples/real/helpdesk.msapp -o output/HelpDesk --no-llm
```

- `./pfx2gas` works from any cwd and maps host paths into the container
  (repo paths → `/workspace`; outside paths bind-mounted at the same
  absolute path). Bare `docker compose …` only works from the repo root.
- Containers run as your uid (`PFX2GAS_UID/GID`, default 1000; Linux CI
  exports 1001). Files written to `/workspace` must stay host-owned.

## Architecture

Pipeline (deterministic; `pfx2gas convert` = all stages):

```
.msapp ─▶ unpack ─▶ parse ─▶ analyze ─▶ synthesize ─▶ validate ─▶ report
```

- **Input formats.** Modern apps carry `Src/*.pa.yaml`; legacy binary
  exports (`Controls\*.json`) go through `legacy.py`'s adapter. Both feed
  the same pydantic IR (`ir/models.py`). Screen order (= start screen):
  legacy `TopParent.Index`, modern archive entry order or
  `CanvasManifest.ScreenOrder`.
- **Generated project** (per app, in `output/<App>/`): `Code.gs` (doGet +
  `api(ds, op, payload)` dispatcher: `list|patch|create|remove|removeIf`,
  plus `apiChoices`, `whoami`, and the `include(name)` templating helper),
  `DataInit.gs` (`setup()` creates the workbook, preserves every exported seed row,
  and expands sheet rows/columns before writes),
  `appsscript.json` (webapp config + Sheets scopes), `Index.html`,
  `Screens.html`, `App.js.html`, and the static `gas-runtime/fx-stdlib/
  fx-charts.js.html` copies + `conversion-report.md`.
- **Templating contract.** `Index.html` contains server-side scriptlets
  `<?!= include('App.js.html') ?>` etc. — names are FULL filenames, and
  `include()` (defined in `Code.gs`) strips the `<script>` wrappers from
  `.js.html` files so they nest inside Index's own `<script>` block.
- **Runtime export surface** (`gas-runtime.js`, 24 globals): `state`, `go`,
  `goBack`, `toast`, `val`, `bind`, `refreshData`, `submitForm`,
  `selectControl`, `esc`, `exitApp`, `FXUser`, `FXRuntime`, `selfRef`,
  `apiPatch/apiCreate/apiRemove/apiRemoveIf/apiClearCollect`,
  `powerapps_collect/clearCollect/remove/removeIf`. Generated code calls
  these bare. fx-stdlib exports `FX` (74 functions) + `FX.collections`;
  fx-charts exports `FXCharts`.
- **Data model.** Collections (`CollectionDataSourceInfo`) are client-side
  state arrays — never Sheet tabs; `Collect/ClearCollect/Patch/Remove/
  RemoveIf/Refresh` against them compile to local `powerapps_*` /
  `FX.collections.*` calls. External sources become seeded Sheet tabs with
  **snake_case headers** (`fx/naming.py`) that MUST match the emitter's
  record-key casing.
- **Row-scoped children.** Gallery/DataTable template children are rendered
  per-row by `FXRuntime.gallery(name, itemsFn, rowFn, handlers)` with `item`
  bound; they must never be registered at top level.
- **Icons.** Power Apps icon *names* (`'customer-service'`, `Icon.Filter`)
  map to Segoe MDL2 Unicode glyphs (`icons.py`, 64 entries); known names
  render as `.fx-icon` spans (color/size preserved), unknown keep legacy
  behavior and are ledgered.

## Regression traps (all previously shipped as bugs — do not re-create)

- **Emitter ↔ runtime contract drift.** Any helper the emitter emits must
  exist in the runtime's `global.*` export surface with matching parameter
  order. Guardians: `scripts/check_runtime_consistency.py` (converts a
  fixture, strips comments, checks every bare call + collection-helper
  signatures) and `tests/js/test-gas-runtime.js` (signature pinning).
  Update both when adding a helper.
- **Row-scoped children at top level** → "control not found" spam +
  `item is not defined` crashes. See Architecture; guardian:
  `tests/test_startup_sim.py`.
- **Format-template bugs.** Template strings with `{{ }}` MUST get
  `.format()` — `render_manifest` once shipped invalid JSON (doubled
  braces) that silently dropped the webapp config + oauth scopes.
  Guardian: validator parses `appsscript.json`.
- **No visible screen.** Every screen section starts `display:none`; the
  `APP_MAIN` bootstrap must end with `go(startScreen)` and the runtime
  reveals the first screen even if `APP_MAIN` throws.
- **`.gs` files are JS.** The validator `node --check`s them; keep it that
  way (an em-dash template bug once shipped broken `DataInit.gs`
  everywhere, and the old validator passed it).
- **Mac bash 3.2.** Wrapper scripts must run on it: no `set -u` with array
  expansion, no mutating arrays inside `$( )` subshells.

## Verification ladder (use in order)

1. `./pfx2gas test` — unit level.
2. `./pfx2gas soak` — real-app conversion + strict validation (10/10).
3. `tests/test_startup_sim.py` — boots the *generated* app in Node with a
   stub DOM, full stdlib/charts/runtime, indirect eval, and a faithful
   async `google.script.run` proxy mock; asserts zero `is not defined`
   errors and exactly the start screen visible. Extend it when touching
   generation or the runtime.
4. Deploy smoke (needs the user): convert → `./pfx2gas clasp create` →
   **re-copy the regenerated `appsscript.json`** (clasp create clones a
   default manifest over it) → `clasp push --force` → user runs `setup()`
   once in the Apps Script editor (creates the workbook; `clasp run` needs
   a standard GCP project and does NOT work with default clasp projects) →
   `clasp deploy` → fetch the `/exec` URL (curl sees Google's sandbox
   wrapper; decode embedded payload for assertions).

## Repo facts

- Samples (`samples/real/`) are gitignored; CI fetches the 5 public
  modern-format apps via `scripts/fetch_samples.py` (zip-integrity-checked,
  cached, `PFX2GAS_SAMPLES_DIR` overridable). Legacy-format apps are covered
  by committed synthetic fixtures (`tests/fixtures/build.py`).
- Clasp credentials persist in gitignored `.clasp-home/` (mounted at
  `/home/pfx` in the clasp service).
- `.env` (gitignored) carries optional OpenRouter LLM config; real env vars
  override. Never commit keys or paste them into memory/files.
- Console noise that is NOT ours (do not chase): `csp.withgoogle.com`
  blocked by the user's ad-blocker; `Permissions-Policy
  'attribution-reporting'` and iframe-sandbox warnings from Google's
  wrapper; `Net state changed` chatter.
- Known documented gaps (see `GAP_ASSESSMENT.md`): component-template
  emulation (MENU/TILES/ProgressBar render empty), `User()` returns email
  only (blank name/avatar), delegation (whole-tab reads ~5k-row guidance).
