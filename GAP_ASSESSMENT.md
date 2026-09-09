# pfx2gas — Gap Assessment & Roadmap (updated 2026-09-09)

The product goal is to convert common business Power Apps canvas apps into
Google-hosted apps that work correctly and preserve as much of the original UI
and interaction behavior as reasonably possible, with minimal manual repair.
Success means people can complete the original business tasks using a familiar
interface, with correct data and explicit evidence of fidelity.

The September 9 pass adds stable editable gallery rows with per-row control
references, focus/selection retention through sorting, persisted row saves,
queued parent selection, and timer lifecycle/focus support. It also fixes block
comments, word-form logical operators, nested behavior chains and sorting.
Untranslatable behavior now fails visibly instead of disappearing. The LLM
single-formula seam has structural parsing, helper-name and response-schema
checks, while remaining explicitly partial until behavior is tested.

The next slice adds nested `As` record aliases, gallery aliases across async
saves, table/global disambiguation, single-column projections and membership,
plus GroupBy/Ungroup. Generated Chromium tests exercise reactive grouped totals,
targeted row removal, and persisted edits through aliased gallery records.
Multi-condition If now retains all branches and its fallback; Switch evaluates
its subject once. Both preserve selected async action order.

The local-draft slice implements SaveData/LoadData/ClearData with typed browser
storage, append-on-load semantics, scoped clearing and explicit quota/corruption
failures. Chromium exposed a separate missing dynamic-input-default binding;
standalone input defaults now populate after reload and preserve unsaved edits
through unrelated updates. Native input/button DisplayMode formulas reevaluate
while typing. Form/DataCard record application continues to own form field
defaults. Storage is browser-local, plaintext, and limited to 1 MB
per encoded entry; it does not make the remote Apps Script app available offline.

Eleven pinned source exports are available here: five public regression apps
and six Microsoft business apps. **All eleven generate valid code; the five
regression apps, Employee Ideas and Inspection currently pass startup. None has
complete usability acceptance evidence.** The previous two clean Microsoft startup results hid
initialization formulas that were never emitted; restoring those formulas now
exposes TimeValue, IsMatch and connector dependencies. GroupBy and LoadData no longer
block Employee Ideas and Inspection, but their loading-to-business workflows
remain unassessed. Six generated-fixture Chromium journeys pass. These fixtures
are regression evidence, not additional
real acceptance apps. The last recorded Google deployment remains HelpDesk @14.

## Acceptance goal: faithful business-app conversion

**Functional fidelity:** preserve source business rules, calculations,
validation, navigation, search/filter/sort, record selection, form modes,
create/edit/delete, persisted data, roles and error handling. Test the complete
workflow in the Google environment, including reload and failure paths. A
visible unsupported placeholder documents a gap; it does not satisfy a
workflow that depends on that feature.

**UI fidelity:** preserve screen structure, control placement and dimensions,
text and wrapping, typography, colors, icons, images, charts, forms, galleries,
component styling, visibility and interaction states. Preserve the source's
fixed-layout, scaling or responsive behavior at its supported viewports.
Google services provide the target runtime and data layer; visual styling
continues to follow the source app. Generic controls and replacement glyphs
remain approximations until their appearance and behavior are checked.

**Reasonable differences:** small browser/font rendering differences may be
accepted within documented tolerances when readability and interaction remain
equivalent. Missing text/media, incorrect charts, clipped essential controls,
lost edits, incorrect records or broken actions are blocking defects. Record
each material platform limitation, affected workflow, available adaptation and
remaining manual work. Source bugs and incomplete prototypes remain separately
identified so they do not become invented converter behavior.

**Repeatability:** implement fixes in the reusable parser, generator or runtime
and regenerate from the export. Each fix should be exercised in an independent
representative app or fixture as well as the app that exposed it. Measure
complete workflow passes, original-versus-converted visual differences, and
remaining manual interventions per app; formula counts are diagnostic evidence.

Prioritize representative business patterns in the acceptance corpus:

| Business pattern | Required workflow evidence | Required UI evidence |
|---|---|---|
| Service requests / ticket tracking | Search, select, create, assign/update, validate and reopen a persisted record | List/detail/form consistency, statuses, navigation and dashboard |
| Inventory / asset / customer records | Filter/sort, edit the correct row, maintain lookups and save changes | Dense galleries/tables, selectors, forms and images |
| Requests / approvals / expense forms | Submit, validate, transition status and enforce the source's role-dependent actions | Conditional fields, disabled states, validation feedback and attachments where used |
| Operational dashboards | Accurate aggregations and filter-dependent results | Original chart type, labels, series, colors, legends and resizing |

These are coverage targets, not current support claims. Select exports whose
source workflows are complete, covering modern and legacy controls and
representative data sources. An external flow or connector dependency remains
a blocker until its target behavior is implemented and verified. Retain games
and component demos for regression coverage, while business-app failures drive
the implementation order.

## Current evidence and its limits

| Evidence | Latest result | What remains unproven |
|---|---|---|
| Unit/runtime tests | 194 Python pass, 3 skip; 71 JS pass; bare globals, FX and FXRuntime emitter/runtime consistency passes | Complete deployed workflows and broader control semantics |
| Current real-app soak | 5/5 Bootable; 1,120 formulas | Usability unassessed; the other five historical local exports are absent |
| Current regression translation/wiring | 1,114 translated; 969 emitted, 13 approximated, 138 ignored/unsupported | Translation does not establish runtime behavior |
| Historical ten-app corpus | Previously 10/10 Bootable; 23,746 formulas | Not reproduced in this workspace; those results did not establish usability |
| HelpDesk generated-app journeys | HOME → NEW → HOME; dashboard row text, logo URI, pie and legend output pass | All-screen interactions, image decoding/layout in CI, persistence |
| HelpDesk @14 live browser | Ticket cards, decoded 64×64 logos, pie/bar/legend SVGs, readable fonts/labels, HOME → NEW → HOME | Same-state original comparison, user name/avatar, complete workflow coverage |
| Chromium: business form | Actual generated client + Code.gs: edit/create, required validation, write failure, delete and page reload pass against a persistent Sheets test double | Real Google authorization/Sheets writes and another user/session |
| Chromium regression suite | 6/6 fixtures pass: form, charts, record scopes/launch parameters, editable gallery, timer lifecycle, local draft persistence; generated client and server code | Real Google services, real-app critical workflows and original visual comparisons; HelpDesk is absent here |
| Microsoft business baseline | 6/6 convert and validate; 2/6 pass startup (Employee Ideas, Inspection) | Startup alone does not prove leaving loading or completing business actions; all business workflows remain unverified |
| CI configuration | Existing tests plus required-app/journey gates and new Chromium artifact job | Browser job configured and locally tested, not yet verified in remote CI; local HelpDesk remains optional |

Evidence: `.artifacts/benchmark/benchmark-scorecard.json`,
`.artifacts/microsoft/benchmark/benchmark-scorecard.json`, and
`.artifacts/browser/`. Scorecards now label ignored/unsupported separately from
approximations and retain input hashes and a converter source fingerprint.
Browser screenshots are converted-output regression evidence, not originals.

Historical milestone notes conflict: `AGENTS.md` calls M1–M4 complete, while
the previous roadmap kept M4 open. For the current acceptance bar, a second
representative deployed app with recorded workflow evidence remains an open
deliverable; historical milestone labels do not substitute for that evidence.

## Completed in the latest passes

| Change | Evidence / boundary |
|---|---|
| Formula-created collection discovery and multi-argument Collect/ClearCollect | Source-backed HelpDesk counts and independent chart fixture pass in Chromium; declared external tables retain server routing |
| Source chart colors/label visibility, signed bars, zero-total pie state and reactive dimensions | JS semantic tests plus generated chart startup/browser journey; full multi-series and axis semantics still open |
| Enforced benchmark gates and pinned modern sample hashes | Deliberate failed-journey/missing-app subprocess tests fail correctly; clean-container five-export download verified |
| Chromium with generated Code.gs and DataInit.gs | Synthetic form create/edit/validate/fail/delete/reload and charts pass; HelpDesk content/navigation passes locally; no live Google persistence claim |
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

The catalog now records source-supported form/list interactions instead of a
persistent `create-ticket` journey. Persistent CRUD remains a required acceptance
target in the Microsoft business catalog, and HelpDesk is not promoted to Usable.
The eight tickets and dashboard's `[5, 2, 4, 8]` values are literal source data;
the dashboard is not a derived count of those eight records.
Record source limitations separately from missing converter support and missing
verification. Any functional enhancement to the original app is a distinct
scope decision.

## Next round: five ordered work packages

R1–R5 are stable work-package identifiers. Execute them in the business-outcome
sequence below: begin the regression checks alongside a real business app,
then fix the functional and UI defects found in its workflows. Test harness
completion alone is not completion of this round.

### Selected Microsoft acceptance targets and immediate fix order

The user requested two or three Microsoft examples with broad feature coverage.
Selected **Milestones, Employee Ideas and Inspection**, including their manager
and review variants: six untouched legacy canvas exports, complemented by the
five existing modern regression exports. See [sample provenance](benchmark/SOURCES.md)
and [the business catalog](benchmark/microsoft-apps.json). Release 44 and all
export bytes are pinned; extraction and the failing baseline are reproducible
with `./pfx2gas browser scripts/assess_microsoft_samples.py`.

| Next priority | Observed blocker and outcome required |
|---|---|
| 1. Correct record and formula scopes (R4/R5) | Implemented: blank-safe fields, nested `With`, row/global fallback, `ThisItem`/`ThisRecord`, LookUp/AddColumns, `As` aliases in functions/galleries, table/global disambiguation, column projection, membership, grouping and multi-branch If/Switch. Remaining: variadic/error-handling and async semantics, source workflow coverage and complete table value semantics. |
| 2. Preserve initialization and data contracts (R5) — next | `Param`, browser `Language()`, Timer lifecycle and explicit initialization failures are implemented. Next preserve Dataverse solution schemas/choices/lookups and define explicit Google connector adapters. Do not fake connector success or navigate past unexecuted initialization. |
| 3. Make record editing reliable (R4/R5) | Stable gallery rows, scoped handlers, defaults/DisplayMode, focus retention and correct-row save/reload pass in generated fixtures. Extend to source business apps, nested layouts and real Google Sheets. |
| 4. Close visible UI differences (R2/R3/R4) | Use those same workflows for text/media/disabled/validation states, chart series/axes and responsive layout. Extend Chromium to source-sized and narrow viewports and compare matching original screenshots. |

Milestones supplies the first project/task lifecycle target; Employee Ideas and
Inspection verify that fixes generalize. The Microsoft baseline still exits 1
with four startup failures; Employee Ideas and Inspection are Usable/High fidelity unassessed,
not passing business apps. None of R1–R5 is fully complete under its original
acceptance criteria.

### September 6 completed slice and the next blocking dependencies

- Quoted source/global names retain their identity, including spaces and
  escaped apostrophes; nested image fields are no longer flattened into a
  nonexistent row variable. Local fields shadow outer fields even when Blank.
- `With` and two-argument `IfError` propagate asynchronous saves and failures
  before subsequent behavior. Unsupported asynchronous table predicates remain
  explicit translation gaps, not syntax-invalid synchronous callbacks.
- Nested mutation schema discovery includes App.OnStart and nested behaviors.
  External mutation-backed tables get stable generated IDs when absent, and
  embedded fields survive partial updates. Existing deployed workbooks without
  those headers still need an explicit migration; this does not migrate @14.
- `doGet(event)` supplies case-sensitive, decoded, text-valued `Param` data;
  missing parameters return Blank. Embedded request JSON escapes `<` to prevent
  a script-ending payload from executing. Parameters never establish identity
  or permissions. `Language()` uses the browser locale, not a Microsoft profile.
- The generated-browser scope fixture, startup test, formula value tests and
  emitter/runtime gate prevent these bug classes recurring. Source semantics:
  [Power Fx With](https://learn.microsoft.com/en-us/power-platform/power-fx/reference/function-with),
  [Param](https://learn.microsoft.com/en-us/power-platform/power-fx/reference/function-param),
  [Apps Script request events](https://developers.google.com/apps-script/guides/web).

Timer lifecycle events now have deterministic runtime wiring. Their source
initialization also needs complete data, connector and remaining formula
support. Block comments, nested action chains and capitalized logical operators
previously prevented entire startup formulas from being emitted; those cases
now translate. Immediate errors are only the first reachable failures, not the
full dependency list:

| Microsoft export | Current startup blocker | Additional source dependencies to preserve |
|---|---|---|
| Employee Ideas | No error in the startup window; leaving Loading Screen remains unverified | Teams channel posting and Dataverse campaign/idea data |
| Employee Ideas Manager | `MicrosoftTeams.GetAllTeams` | Loading/focus timers; team/channel lookup and posting |
| Inspection | No error in the startup window; leaving Landing Screen remains unverified | Browser draft persistence implemented and tested independently; full inspection submission, Planner tasks, Office365 identity and Teams posting remain |
| Inspection Manager | Teams lookup, `Planner.ListMyPlansV2`, `IsMatch` | Loading/focus timers; plan/bucket/task/group-plan lookups and settings validation |
| Milestones | `TimeValue` | Loading/focus timers; Office365 user/profile/photo and relational project/task data |
| Review Inspections | `Planner.ListMyPlansV2` | Loading/focus timers and inspection data |

Next acceptance evidence must demonstrate leaving the loading state through
the source-defined flow, with real mapped data, then completing a business
journey. Follow that immediately with editable-gallery focus/selection tests
and original-versus-converted UI comparisons in the same data state.

The exports already contain detailed `NativeCDSDataSourceInfo.TableDefinition`
metadata: entity attributes and primary keys, relationships, views and option
sets, plus logical/display-name mappings. The legacy adapter currently ignores
this data while reading only the older `Schema` string. Decode these embedded
contracts next; missing target schemas are a converter gap, not missing export
evidence. Also retain `OptionSetInfo` constants rather than treating them as
empty external tables. Source inspection artifacts are under `.artifacts/`.

### R1 — P0: make regression evidence enforceable and reproducible

**Implemented:** failed required journeys and missing required apps cause a
nonzero exit; High fidelity requires Usable; the HelpDesk source mismatch is
corrected; modern exports are revision/hash pinned; scorecards retain source
fingerprints and input hashes. Container tests now explicitly import the mounted
source tree instead of accidentally testing an older baked package.

**Remaining:** reproduce the five additional local exports (including HelpDesk)
or licensed equivalents in CI, promote the Microsoft corpus into regression
gating once its startup failures are fixed, and attach complete workflow/original
visual evidence. The full historical ten-app corpus is not yet reproducible.

Checklist (retain completed items as acceptance requirements):

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

**Implemented, partial:** `./pfx2gas browser` runs Chromium in Docker against
generated HTML/JS plus actual generated server code with a Sheets test double.
Forms, chart semantics and local HelpDesk HOME/NEW interactions pass; screenshots,
console errors, DOM geometry, browser version and source hashes are retained.
CI runs the redistributable synthetic form/chart cases. HelpDesk runs when present.

The simulator checks generated runtime behavior with a stub DOM. It does not
perform browser text measurement, image decoding, hit testing, real event
bubbling, font layout, or viewport reflow. The @14 manual review must become a
repeatable test with retained screenshots and DOM measurements.

Implement a Docker-based browser runner for generated output with deterministic
data and a controlled Apps Script API bridge. Cover HelpDesk HOME, NEW, LIST and
REPORTS plus source-supported paths to VIEW/EDIT; Clean UI components; and a
modern data-backed business app selected for R5. Test empty, single-record and
multiple-record states, plus loading, validation failure and disabled states.
Inspect:

- visible text, decoded images, chart geometry and legends;
- bounding boxes, text clipping, overlap, scroll access and keyboard focus;
- menu destinations, input/reset behavior, search/filter and selection;
- source-sized and narrow viewports with reproducible fonts and data, preserving
  the source's fixed/scaled/responsive layout contract.

Keep converted-output regression screenshots separate from original-versus-
converted fidelity evidence. Obtain original app captures at the same viewport,
data and interaction state; record baseline provenance and explicit tolerances.
Missing originals block the High fidelity claim, but not browser regression work.

**Done when:** recreating blank gallery children, broken images, hidden charts or
clipped primary controls fails automated browser checks; failure artifacts
identify the control and state; at least one critical screen has an original
comparison. Every remaining mismatch is classified and reproducible.
Pair the checks with fixes to the source-to-output differences they expose;
retain before/after evidence and verify another app or fixture for each fix.

Primary files: new browser harness/tests and container service,
`src/pfx2gas/startup_sim.py`, `benchmark/apps.json`, CI artifact configuration.

### R3 — P0: chart data and display semantics

**Implemented:** `ShowLabels` and `ItemColorSet` expressions, matching legend
colors, explicit field-name normalization, signed bar geometry, zero-total pie
empty state and reactive source Width/Height/foreground. Independent generated
startup and browser chart fixtures verify these; HelpDesk retains its four
literal source totals. General chart rendering remains approximate.

Remaining gaps in `static/fx-charts.js` and `synth/client.py`:

- Column inference chooses the first eligible fields; one category/value pair
  is supported, with no full multi-series mapping.
- Axis ranges/ticks/formatting, source label placement and series metadata remain
  approximate. Negative pie values are omitted; exact source parity is unverified.
- Source-formula size changes update SVG, but viewport-driven layout invalidation
  and all flex/container-resize paths remain unverified.

Implement multi-series binding where source metadata exists, source axis and
label formatting, and viewport/layout resizing next, with explicit reporting for
unsupported variants. Review source formulas before changing dashboard totals.

**Done when:** generated-app and browser fixtures prove exact categories,
values, label visibility, colors and geometry for empty/one/many rows,
negative/zero values and multiple series. HelpDesk remains visually stable;
a distinct multi-series fixture demonstrates broader compatibility. Compare
the dashboard's totals, chart appearance and filter behavior with the original.

Primary files: `src/pfx2gas/legacy.py`, `src/pfx2gas/synth/client.py`,
`static/fx-charts.js`, `static/gas-runtime.js`, chart and browser tests.

### R4 — P0: gallery input, row context and responsive behavior

**Implemented, partial:** rows with stable IDs retain DOM identity, edits,
focus and selection through unrelated updates and sorting. Row references and
OnChange/OnSelect handlers use lexical row context across awaited saves.
Defaults, selectors, images, disabled states and Reset are wired per row.
Select(Parent) invokes the source handler once after the child action. Generated
runtime and Chromium fixtures verify editing only the second persisted record,
reset, sort, selection and reload. ID-less replacement records, nested galleries,
full reactive row styling and broad responsive layout remain unverified.

Extend this evidence to real business apps and concurrent row actions. Revisit horizontal
galleries, WrapCount/template width and padding with browser geometry evidence.
Add viewport resize invalidation and test AutoHeight/dependent positions in
nested containers; current runtime has no resize listener. Preserve the source
layout mode: a fixed canvas may scale or scroll, while a responsive source must
reflow according to its formulas.

**Done when:** editing row two updates only row two; typing, focus and selection
survive unrelated state updates; async actions refresh the correct row;
nested/wrapped layouts follow the original's scaling/reflow behavior without
clipped primary controls at supported viewports. A source-app action must
determine navigation behavior. Form/gallery appearance and validation states
must also match the original within the recorded tolerances.

Primary files: `static/gas-runtime.js`, `src/pfx2gas/synth/client.py`,
gallery/form fixtures, generated-runtime and browser journeys.

### R5 — P0: prove persistent CRUD and finish visible identity/media states

Use the selected Microsoft business templates with source create/edit/delete
behavior. Editable Grid has persistent formulas but lacks its Student Tracker
metadata and initialization; it remains a limited regression input. The six
Microsoft exports now establish the business acceptance targets throughout R1–R5.
Keep the existing synthetic Form/DataCard
journey as a regression test, but add a browser and deployed Google Sheets
journey: create → read → edit → validate → delete → reload.

Exercise stable IDs, choice/lookup/person/date values, loading and server error
states, duplicate-submit prevention, and the selected execution identity.
Start with the Sheets contract and only add adapters required by the chosen app.
Give DataTable and searchable ComboBox behavior concrete fixtures rather than
treating their generic/native-select renderers as complete.

The current server already derives a display-name fallback from the email local
part and the generated image fallback renders without a profile photo. Verify
anonymous/unavailable identity states and report that these are fallbacks, not
directory identity. Add optional Workspace enrichment only with an explicit
adapter and permission contract. Distinguish intentionally
absent images from failed resources. Keep unsupported attachments visible until
a Drive storage/access contract and upload/download journey are implemented.

**Done when:** a second deployed app completes its declared CRUD journey,
changes survive reload against real Sheets, server failures produce useful
feedback, and identity/media controls have meaningful fallback states. Its
list/detail/form screens and supported interaction states have original-app
comparisons, with all blocking functional and visual differences resolved.
Record the deployment version, data setup, steps and results.

Primary files: `src/pfx2gas/synth/server.py`, `src/pfx2gas/synth/client.py`,
`static/gas-runtime.js`, form/data tests and benchmark catalog.

## Execution order and release criteria

1. With the three R5 business templates selected and baselined, record their
   complete solution data contracts, layout modes and original reference states. Keep HelpDesk
   as an additional dashboard/component regression target.
2. Implement the R1 checks that prevent false passes and the R2 browser checks
   needed to exercise those two apps. Expand the harness as actual workflows
   require it.
3. Fix blocking business behavior first: correct record selection/editing,
   reactive inputs, validation, save/reload and navigation (R4/R5). In the same
   app states, restore missing or incorrect text, media, layout and control
   appearance (R2/R4). Verify complete workflows and their visible results.
4. Correct dashboard data, chart presentation and responsive/scaled behavior
   (R3/R4), ordered by impact on the selected business workflows. A chart defect
   that misrepresents a business result is a functional blocker.
5. Regenerate, deploy and compare both apps; retain the source/output evidence,
   remaining differences and the regression fixtures for subsequent conversions.

Rank work by blocked business tasks and incorrect data first, then missing or
misleading UI and visual similarity, then prevalence across common business
apps. Source captures and a complete data-backed export are required evidence
inputs; independent regression and runtime work can proceed while they are
being obtained.

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
- a complete real business-app workflow with persistent CRUD and recorded
  Google deployment evidence, including validation and error behavior;
- original-versus-converted comparisons for the business app's critical
  list/detail/form screens and the dashboard reference, with no missing
  essential content, misleading visualization or unusable control;
- a per-app list of remaining differences and manual repairs. An unresolved
  critical business feature keeps that app below the acceptance goal even if
  the limitation is accurately reported.

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
- Run LLM equivalence review and gap triage at corpus scale. Extend the new
  single-expression/handler boundary, helper checks and logged provenance with
  full symbol/type analysis, isolated behavioral tests and caching.
- Extend active/large media, themes, transitions and less common controls by
  measured need. Power Automate migration requires a separately designed target
  and remains an explicit unsupported dependency.

---

## Architecture decision: expand LLM use, but not whole-app code generation

The LLM should do more work, but it should not become the generator. In the
historical ten-app assessment, formula translation reached 23,724 / 23,746
(99.9%), while only 15,300 formulas (64.4%) were wired into runtime behavior or
visual properties.
Asking a model to translate the remaining 22 formulas cannot solve missing
forms, controls, connector semantics, media, responsive layout, or component
behavior. Whole-app model-generated JavaScript would also make conversions
non-reproducible and much harder to secure or regression-test.

Use a deterministic-core / LLM-assurance design:

| LLM role | May affect generated app? | Required gate |
|---|---:|---|
| Translate one otherwise unsupported formula | Yes, opt-in and ledgered `partial` | Node syntax + AST boundary/helper checks and strict response schema; full symbol/type checks, isolated runtime tests and generated-app boot remain needed |
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
