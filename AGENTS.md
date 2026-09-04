# AGENTS.md — guidance for AI agents working on pfx2gas

pfx2gas converts Microsoft Power Apps canvas apps (`.msapp`) into runnable
Google Apps Script web apps (HtmlService UI + `google.script.run` API +
Sheets data layer) with an honest per-formula fidelity ledger.

- Read `README.md` for architecture and CLI usage.
- Read `GAP_ASSESSMENT.md` for the current roadmap and known gaps before
  planning work — it is kept current.
- The plan of record is `~/.hermes/plans/2026-09-01_132008-powerapps-to-appsscript-agent.md`
  (M1–M4 all complete; v0.1.0/v0.1.1 tagged).

## Hard rules

1. **Never let the LLM write generated code.** The deterministic pipeline is
   the source of truth. LLM seams are review-only (behavioral equivalence,
   QA scenarios) or a fallback for single formulas whose output is
   `node --check`-gated and ledgered. Do not weaken these guardrails.
2. **Every "converted" claim needs runtime evidence.** The user's acceptance
   bar is *behavioral fidelity*, not function coverage. String assertions on
   generated files are not proof. Boot the generated app (see
   `tests/test_startup_sim.py`) or deploy it before claiming something works.
3. **Bugs found in production get a regression test in the same commit** —
   ideally a gate that makes the whole bug class impossible (see
   `scripts/check_runtime_consistency.py`, the manifest-JSON validator rule),
   not just a pinpoint test.
4. **Container-first.** The user runs nothing locally except Docker and a
   browser. Do not suggest host installs; all commands go through
   `./pfx2gas` (see below).

## Commands

```bash
./pfx2gas build      # rebuild image — REQUIRED after changing src/ or static/
./pfx2gas test       # pytest + node --test + consistency gate (mounted repo)
./pfx2gas soak       # fetch real samples + convert/validate all
./pfx2gas validate output/HelpDesk
./pfx2gas convert samples/real/helpdesk.msapp -o output/HelpDesk --no-llm
```

- `./pfx2gas` works from any cwd and maps host paths into the container
  (repo paths → `/workspace`, outside paths bind-mounted). Bare
  `docker compose …` only works from the repo root.
- The wrapper runs containers as your uid (`PFX2GAS_UID/GID`); on Linux CI
  export `PFX2GAS_UID=$(id -u)`. Files written to `/workspace` must be
  host-owned.
- CI (`.github/workflows/ci.yml`) runs the same suite plus a container job
  and wrapper smoke; keep it green. Pushing workflow-file changes requires
  the PAT to keep the `workflow` scope (fine-grained: Workflows read/write).

## Architecture in one screen

```
.msapp ─▶ unpack ─▶ parse ─▶ analyze ─▶ synthesize ─▶ validate ─▶ report
```

- `src/pfx2gas/legacy.py` adapts binary (pre-pa.yaml) exports; modern apps
  go through `src/*.pa.yaml`. Both feed the same IR (`ir/models.py`).
- `static/gas-runtime.js` + `static/fx-stdlib.js` (+ `fx-charts.js`) ship
  into every generated app. `src/pfx2gas/synth/*` writes `Code.gs`,
  `DataInit.gs`, `Index.html`, `Screens.html`, `App.js.html`,
  `appsscript.json` per app.
- Data model: **collections are client-side state** (never Sheet tabs);
  external sources become seeded Sheet tabs with **snake_case headers**
  (`fx/naming.py` — must match the emitter's record-key casing exactly).

## Regression traps (all previously shipped as bugs — do not re-create)

These are the *classes* that bit us; each has a guardian (noted):

- **Emitter ↔ runtime contract drift.** Generated code calls helpers as
  bare globals (`bind(…)`, `powerapps_*(state, 'Name', …)`). Any helper the
  emitter emits must exist in the runtime's `global.*` export surface, and
  parameter order must match the emitted call shape. Guardians:
  `scripts/check_runtime_consistency.py` (export surface + signatures) and
  `tests/js/test-gas-runtime.js` (signature pinning). Add to both when
  adding a helper.
- **Row-scoped children registered at top level.** Children of Gallery /
  DataTable templates only exist per-row with `item` bound. Registering
  their handlers/evaluators at top level → "control not found" spam and
  `item is not defined` crashes. `synth/client.py` skips them; the
  `FXRuntime.gallery(...)` block handles rows. Guardian:
  `tests/test_startup_sim.py`.
- **Format-template bugs.** Template strings with `{{ }}` MUST have
  `.format()` called — `render_manifest` once shipped invalid JSON
  (doubled braces) that silently dropped the webapp config + oauth scopes.
  Guardian: validator parses `appsscript.json` as JSON.
- **Every screen starts `display:none`.** The start screen (first in the
  app's screen order: legacy `TopParent.Index`, modern archive order /
  `CanvasManifest.ScreenOrder`) must be revealed by the `APP_MAIN`
  bootstrap via `go(start)`, and the runtime reveals the first screen even
  if `APP_MAIN` throws. Never leave a generated app with no visible screen.
- **`.gs` files are JS.** `node --check` them (validator does). Never
  concatenate template fragments with stray characters — an em-dash
  template bug once shipped broken `DataInit.gs` everywhere.
- **Mac bash 3.2.** Repo wrapper scripts must run on it: no `set -u` with
  array expansion, no mutating arrays inside `$( )` subshells.

## Verification ladder (use in order)

1. `./pfx2gas test` — unit level (88 Python + 35 JS at time of writing).
2. `./pfx2gas soak` — real-app conversion + strict validation (10/10).
3. `tests/test_startup_sim.py` — boots generated apps in Node with a stub
   DOM; asserts zero `is not defined` errors and exactly the start screen
   visible. Extend it when touching generation or the runtime.
4. Deploy smoke (needs the user): convert → `./pfx2gas clasp create` →
   **re-copy the regenerated `appsscript.json`** (clasp create clones a
   default manifest over it) → `clasp push --force` → user runs `setup()`
   once in the Apps Script editor (creates workbook; `clasp run` needs a
   standard GCP project and does NOT work with default clasp projects) →
   `clasp deploy` → fetch the `/exec` URL and decode the payload.

## Repo facts

- Samples (`samples/real/`) are gitignored; CI fetches them from the public
  `sunilshetty07/Microsoft-PowerApps-Canvas` repo via
  `scripts/fetch_samples.py` (zip-integrity-checked, cached,
  `PFX2GAS_SAMPLES_DIR` overridable). Legacy-format apps are covered by
  committed synthetic fixtures (`tests/fixtures/build.py`).
- Clasp credentials live in gitignored `.clasp-home/` (mounted at
  `/home/pfx` in the clasp service).
- `.env` (gitignored) carries optional OpenRouter LLM config; real env vars
  override. Never commit keys or paste them into memory/files.
- Console noise that is NOT ours (do not chase): `csp.withgoogle.com`
  blocked by the user's ad-blocker; `Permissions-Policy
  'attribution-reporting'` and iframe-sandbox warnings from Google's
  wrapper; `Net state changed` chatter.
- Icon names (`'customer-service'`, `Icon.Filter`) render as Unicode glyphs
  via `src/pfx2gas/icons.py`; unknown names keep legacy behavior and are
  ledgered. Extend the map when a corpus app uses a new name.
