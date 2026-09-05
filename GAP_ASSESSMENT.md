# pfx2gas — Gap Assessment & Roadmap (updated 2026-09-05)

The latest pass fixed the missing HelpDesk gallery text, packaged logo, chart
families, legends, font fallback, and chart-label contrast. HelpDesk @14 was
browser-checked, but the converter has not yet demonstrated complete usability
or visual equivalence across the benchmark. The next round should close the
regression-gate gaps, exercise actual browser behavior, and prove one complete
persistent data workflow.

This update reviews code through `ef0860c`, the latest saved local scorecard,
and the previously recorded @14 browser inspection. Test results below are
from the completed 2026-09-05 verification run (122 Python / 55 JS); this
documentation review did not rerun the suite or deploy new code.

## Current evidence and its limits

| Evidence | Latest result | What remains unproven |
|---|---|---|
| Unit/runtime tests | 122 Python, 55 JS; emitter/runtime consistency passes | Browser layout and complete deployed workflows |
| Local real-app soak | 10/10 Bootable; 23,746 formulas | All 10 are still unassessed for Usable and High fidelity |
| Formula translation | 23,724 / 23,746 (99.9%) | Translation does not establish runtime behavior |
| Runtime wiring | 15,300 emitted (64.4%), 330 approximated, 8,116 ignored/unsupported | Impact varies by property and critical workflow |
| HelpDesk generated-app journeys | HOME → NEW → HOME; dashboard row text, logo URI, pie and legend output pass | All-screen interactions, image decoding/layout in CI, persistence |
| HelpDesk @14 live browser | Ticket cards, decoded 64×64 logos, pie/bar/legend SVGs, readable fonts/labels, HOME → NEW → HOME | Same-state original comparison, user name/avatar, complete workflow coverage |
| Form/DataCard implementation | Generated synthetic app proves create/edit, required validation, reset, callbacks and LastSubmit using a simulated backend | Real Google Sheets writes surviving reload and another user/session |
| CI configuration | Tests, consistency, soak and scorecard artifacts exist | Fetches only five public modern apps; does not reproduce the full local ten-app corpus |

Local scorecard: `.artifacts/benchmark/benchmark-scorecard.json` and its
Markdown companion, generated at `2026-09-05T12:38:26Z`. The scorecard's
“Gaps” column counts ignored/unsupported formulas only; conversion-report
totals also include approximations. For HelpDesk this is **1,858 + 181 =
2,039 gaps**, with 4,517 of 6,556 formulas emitted.

Historical milestone notes conflict: `AGENTS.md` calls M1–M4 complete, while
the previous roadmap kept M4 open. For the current acceptance bar, a second
representative deployed app with recorded workflow evidence remains an open
deliverable; historical milestone labels do not substitute for that evidence.

## Completed in the latest passes

| Change | Evidence / boundary |
|---|---|
| Compatibility catalog and separate Bootable / Usable / High fidelity grades | `fa7a6d2`; higher tiers remain unassessed when evidence is missing |
| Form/DataCard submit and reset; record-valued selectors; visible unsupported capture controls | `9e23de3`; generated-runtime form journey passes, live persistence still pending |
| Legacy chart-family preservation, single-slice pies, chart-derived legends | `1447ed6`; HelpDesk live charts now render; full chart semantics remain approximate |
| Gallery template rendering, row text and geometry, structural template flattening | `1447ed6`; populated HelpDesk cards verified in generated runtime and Chrome |
| Safe packaged raster assets and reactive sanitized HtmlText | `1447ed6`; HelpDesk logo decodes correctly; broader media remains unsupported |
| Platform-safe font stacks and chart foreground colors | `a674df2`; HelpDesk @14 browser inspection confirms fonts and white labels on blue |
| Updated live deployment evidence | `ef0860c`; same HelpDesk URL, version 14 |

Earlier fixes remain in place: truthful emission ledger, reactive state updates,
async startup error reporting, safe external mutations, real Reset behavior,
authenticated deployment defaults, and component-definition expansion. MENU,
TILES and progress-bar definitions are no longer universally empty fallbacks;
their complete visual and interaction behavior still needs browser evidence.

## HelpDesk: distinguish source limitations from converter defects

[HelpDesk @14](https://script.google.com/a/macros/rittmuller.com/s/AKfycbwbyTp89b-J_KEQ9N9wAf0OdJ8faH3k5gwAj_K1ToUFjaDPf8X35VBEnFQvfu5f2OJH/exec)
is the current visual reference for the converted output. Its @12 failures
showed why a clean startup and console cannot establish visual correctness.
The @14 inspection demonstrates improvement, not an original-app fidelity
baseline.

The exported app also contains prototype behavior that a faithful conversion
must preserve and disclose:

- `NEW.btnSave.OnSelect` is only
  `Navigate(HOME,ScreenTransition.Fade)`; it does not create a record.
- `Records`, `RecordsAssignedtome` and the dashboard aggregates are client
  collections seeded by source formulas. They are not persistent ticket tables.
- `NextArrow3.OnSelect` is `Select(Parent)`, and its gallery has no
  navigation action. Staying on HOME is not evidence of a lost Navigate.
- The HOME column chart uses `TotalRecords` even though the surrounding title
  refers to priority. Chart data correctness must be checked against the source
  binding and source data, not inferred from a label.

The catalog currently requests a persistent `create-ticket` journey for this
export. That is a benchmark/source mismatch requiring correction and a
replacement CRUD acceptance app, not permission to invent a Save mutation.
Record source limitations separately from missing converter support and missing
verification. Any functional enhancement to the original app is a distinct
scope decision.

## Next round: five ordered work packages

### R1 — P0: make regression evidence enforceable and reproducible

**Confirmed code gaps:** `scripts/soak_check.py` exits nonzero for no apps or
Bootable failures only; a failed required journey can appear in the scorecard
while the command succeeds. `scripts/fetch_samples.py` downloads five modern
apps; the five additional local samples, including HelpDesk, are not reproduced
by that fetch. Missing catalog apps are reported but do not fail the run.
`benchmark.evaluate_grades` can also award High fidelity from complete visual
evidence without requiring Usable to pass.

Implement:

- Fail CI for any executed required journey failure. Distinguish unassessed
  evidence from failure, and define the required app/journey set explicitly.
- Require the declared CI corpus to be present; pin retrievable sample versions
  and hashes, record provenance/licensing, and include redistributable legacy
  fixtures when a real export cannot be distributed.
- Correct HelpDesk's source-incompatible create journey, recording the source
  limitation and retaining persistent CRUD as a separate required acceptance
  target. Do not obtain a higher grade merely by deleting an unmet requirement.
- Require both usable-workflow and visual evidence before awarding High fidelity;
  retain independent component results for diagnosis.
- Align report terminology for approximated versus ignored/unsupported counts.
  Store converter revision, input hash and evidence type alongside results.

**Done when:** a deliberately failing journey makes the command and CI fail;
a missing required app fails explicitly; the full declared corpus is
reproducible in a clean container; no visual pass masks a broken workflow.

Primary files: `scripts/soak_check.py`, `scripts/fetch_samples.py`,
`src/pfx2gas/benchmark.py`, `benchmark/apps.json`,
`.github/workflows/ci.yml`, `tests/test_benchmark.py`.

### R2 — P0: automate real-browser content and layout checks

The simulator checks generated runtime behavior with a stub DOM. It does not
perform browser text measurement, image decoding, hit testing, real event
bubbling, font layout, or viewport reflow. The @14 manual review must become a
repeatable test with retained screenshots and DOM measurements.

Implement a Docker-based browser runner for generated output with deterministic
data and a controlled Apps Script API bridge. Cover HelpDesk HOME, NEW, LIST and
REPORTS plus source-supported paths to VIEW/EDIT; Clean UI components; and a
modern app. Test empty, single-record and multiple-record states. Inspect:

- visible text, decoded images, chart geometry and legends;
- bounding boxes, text clipping, overlap, scroll access and keyboard focus;
- menu destinations, input/reset behavior, search/filter and selection;
- source-sized and narrow viewports with reproducible fonts and data.

Keep converted-output regression screenshots separate from original-versus-
converted fidelity evidence. Obtain original app captures at the same viewport,
data and interaction state; record baseline provenance and explicit tolerances.
Missing originals block the High fidelity claim, but not browser regression work.

**Done when:** recreating blank gallery children, broken images, hidden charts or
clipped primary controls fails automated browser checks; failure artifacts
identify the control and state; at least one critical screen has an original
comparison. Every remaining mismatch is classified and reproducible.

Primary files: new browser harness/tests and container service,
`src/pfx2gas/startup_sim.py`, `benchmark/apps.json`, CI artifact configuration.

### R3 — P0: chart data and display semantics

Chart rendering now exists, but code inspection identifies concrete remaining
gaps in `static/fx-charts.js` and `synth/client.py`:

- `ShowLabels` is serialized but never read by the renderer.
- Column inference chooses the first eligible fields; one category/value pair
  is supported, with no full multi-series mapping.
- Bars clamp negative heights to a positive minimum, so negative values cannot
  be represented correctly relative to zero.
- Series/legend metadata and hard-coded palettes are approximations;
  `ItemColorSet` expressions are not consumed.
- Chart width/height and foreground config are captured statically; changing a
  control's outer dimensions does not establish correctly resized SVG content.
- Zero-total pies can produce empty SVG content without an explicit empty state.

First implement explicit field/series binding where source metadata exists,
label visibility, consistent chart/legend colors, negative/zero/empty states,
and reactive sizing. Add multi-series support next, with explicit reporting for
unsupported variants. Review source formulas before changing dashboard totals.

**Done when:** generated-app and browser fixtures prove exact categories,
values, label visibility, colors and geometry for empty/one/many rows,
negative/zero values and multiple series. HelpDesk remains visually stable;
a distinct multi-series fixture demonstrates broader compatibility.

Primary files: `src/pfx2gas/legacy.py`, `src/pfx2gas/synth/client.py`,
`static/fx-charts.js`, `static/gas-runtime.js`, chart and browser tests.

### R4 — P0: gallery input, row context and responsive behavior

The current gallery path rebuilds all row DOM on each binding update, uses
global `val(name)` lookup for row control references, and emits child OnSelect
handlers but not row OnChange/input bindings. Row properties cover text and a
limited style set; images, selectors, input defaults and disabled states need
equivalent row support. These are confirmed implementation limits; wrong-row
reads, focus loss and lost edits are risks to reproduce with multi-row tests.

Implement stable row identity and row-scoped control lookup, child input/change
events, selected-record behavior, and bindings for row media/defaults/disabled
states. Test async child actions and `Select(Parent)` with a real parent
handler for correct ordering and exactly-once execution. Revisit horizontal
galleries, WrapCount/template width and padding with browser geometry evidence.
Add viewport resize invalidation and test AutoHeight/dependent positions in
nested containers; current runtime has no resize listener.

**Done when:** editing row two updates only row two; typing, focus and selection
survive unrelated state updates; async actions refresh the correct row;
nested/wrapped layouts reflow without clipped primary controls at supported
viewports. A source-app action must determine navigation behavior.

Primary files: `static/gas-runtime.js`, `src/pfx2gas/synth/client.py`,
gallery/form fixtures, generated-runtime and browser journeys.

### R5 — P0: prove persistent CRUD and finish visible identity/media states

Use an actual data-backed app with source create/edit/delete behavior. Inspect
Editable Grid's source for suitability; obtain another licensed modern export
if it lacks persistent mutations. Keep the existing synthetic Form/DataCard
journey as a regression test, but add a browser and deployed Google Sheets
journey: create → read → edit → validate → delete → reload.

Exercise stable IDs, choice/lookup/person/date values, loading and server error
states, duplicate-submit prevention, and the selected execution identity.
Start with the Sheets contract and only add adapters required by the chosen app.
Give DataTable and searchable ComboBox behavior concrete fixtures rather than
treating their generic/native-select renderers as complete.

Address the visible blank identity state: use a deterministic no-photo/no-name
fallback and report identity availability; add optional Workspace enrichment
only with an explicit adapter and permission contract. Distinguish intentionally
absent images from failed resources. Keep unsupported attachments visible until
a Drive storage/access contract and upload/download journey are implemented.

**Done when:** a second deployed app completes its declared CRUD journey,
changes survive reload against real Sheets, server failures produce useful
feedback, and identity/media controls have meaningful fallback states.
Record the deployment version, data setup, steps and results.

Primary files: `src/pfx2gas/synth/server.py`, `src/pfx2gas/synth/client.py`,
`static/gas-runtime.js`, form/data tests and benchmark catalog.

## Execution order and release criteria

Start R1, then build R2's browser harness before broad UI changes. Use that
harness for R3 and R4; select the R5 data app early so its source/schema informs
the work. Original captures and a suitable CRUD export are evidence inputs,
not reasons to delay the independent test and runtime work.

Each production defect needs a pinpoint regression plus a check for that class
of failure in the same code change. Run `./pfx2gas test`, the required corpus
soak and affected browser journeys; rebuild after source/runtime changes.
Regenerate from the source export and verify the deployed result after each
release tranche. Avoid app-specific patches to generated output.

The next release should require:

- no failed required startup, workflow or browser-content checks;
- reproducible declared corpus coverage in CI;
- HelpDesk's verified content/navigation plus explicit source limitations;
- chart and gallery cases passing the new browser gates;
- one real persistent CRUD workflow with recorded Google deployment evidence.

Call an app **Bootable** after startup checks, **Usable** after all applicable
critical workflows, and **High fidelity** only after those workflows and
original-app visual/interaction comparisons meet documented tolerances.
Unassessed remains an explicit outcome.

## Later work, after this round

- Expand the benchmark to 25–30 licensed, versioned apps across CRUD, dashboards,
  responsive containers, reusable components, collections, media and workflows.
  Prioritize gaps by affected critical journeys, then frequency.
- Introduce typed Google adapters for lookup/person/choice/date/attachment
  semantics; add Drive and other Workspace services as demonstrated apps need
  them. Report connector-specific losses.
- Add filtering/pagination, concurrency/version checks, batching and retry UX;
  whole-tab reads and collections are not delegation or persistence guarantees.
- Run LLM equivalence review and gap triage at corpus scale. Strengthen opt-in
  single-formula fallback with symbol allowlists, typed context, isolated
  execution tests, caching and provenance.
- Extend active/large media, themes, transitions and less common controls by
  measured need. Power Automate migration requires a separately designed target
  and remains an explicit unsupported dependency.

---

## Architecture decision: expand LLM use, but not whole-app code generation

The LLM should do more work, but it should not become the generator. Formula
translation is already 23,724 / 23,746 (99.9%); the larger gap is that only
15,300 formulas (64.4%) are wired into a runtime behavior or visual property.
Asking a model to translate the remaining 22 formulas cannot solve missing
forms, controls, connector semantics, media, responsive layout, or component
behavior. Whole-app model-generated JavaScript would also make conversions
non-reproducible and much harder to secure or regression-test.

Use a deterministic-core / LLM-assurance design:

| LLM role | May affect generated app? | Required gate |
|---|---:|---|
| Translate one otherwise unsupported formula | Yes, opt-in and ledgered `partial` | syntax check today; add symbol allowlist, context/type checks, isolated runtime test, and generated-app boot |
| Review original Power Fx vs emitted JavaScript | No; report only | structured verdict with evidence and a concrete test suggestion |
| Classify unsupported controls/properties and cluster corpus gaps | No; engineering artifact only | aggregate against the machine-readable fidelity ledger |
| Compare original and converted screenshots/interactions | No; QA report only | deterministic screenshots, DOM/style facts, and reproducible steps accompany every finding |
| Propose a new deterministic mapping and regression test | No direct write to converted output | developer-reviewed rule/runtime/test change must pass the full corpus |
| Generate an entire replacement app or freely rewrite generated files | **No** | prohibited; deterministic synthesis remains the source of truth |

The coverage flywheel is: cluster real corpus gaps → have the LLM explain the
Power Apps semantics and suggest tests → implement a deterministic mapping →
run unit, startup, interaction, visual, and deployed gates → permanently reduce
the gap for every future app. A conversion must remain reproducible with
`--no-llm`; LLM fallback is an explicit enhancement, never the only path to a
usable baseline.

---

## Historical: the September 2026 assessment & what it produced

Original findings, all fixed in `6bc7e7b` + `89ddd58`:

1. ✅ `DataInit.gs` emitted invalid JS (literal em-dash) — fixed; `.gs` now
   syntax-checked by the validator (was a blind spot).
2. ✅ Legacy `text` template → every TextInput rendered as a Label — fixed with
   input-property disambiguation (24 corpus inputs, 0 false positives).
3. ✅ Zero inferred fields on every real app — fixed via
   `References\DataSources.json` schema parsing + snake_case headers (matching
   transpiled records) + embedded sample-data seeding.
4. ✅ Collections treated as Sheet tables — now client-side state with
   Power Apps Patch/Remove subset-matching semantics.
5. ✅ Emitter↔runtime signature drift (found during the post-fix state check) —
   fixed + consistency gate added.
