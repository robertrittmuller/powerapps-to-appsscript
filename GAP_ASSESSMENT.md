# pfx2gas — Gap Assessment & Roadmap (updated 2026-09-04)

Forward-looking view: what to work on next. Historical findings and the P0
fixes they produced are at the bottom. Everything here was re-verified against
the code and the real-app corpus (10 apps, 23,746 formulas) on this date.

## Where we stand (verified)

| Check | Result |
|---|---|
| Python suite (`./pfx2gas test`) | 118 passed |
| JS runtime suite (`./pfx2gas test`) | 50 passed, 0 fail |
| Formula translation on 10-app corpus | 23,724 / 23,746 translated (99.9%) |
| Runtime wiring on 10-app corpus | 15,292 / 23,746 emitted (64.4%); 287 approximated |
| Ignored/unsupported property formulas | 8,167 / 23,746 (34.4%; conservative emission ledger) |
| Real-app soak (`./pfx2gas soak`) | **10/10 Bootable**; exact start screen, zero startup runtime errors |
| Compatibility benchmark | versioned 10-app archetype/journey catalog; per-app JSON + Markdown Bootable/Usable/High-fidelity scorecards |
| Emitter↔runtime consistency (`scripts/check_runtime_consistency.py`) | pass |
| Generated server code syntax | all `.gs` node --check clean (validated every soak app) |
| Data layer | external sources → typed, sample-seeded Sheet tabs; collections → client-side state |
| Deployed a converted app via clasp | **redeployed and inspected 2026-09-04** — HelpDesk @12 contains the component/runtime/visual pass and authenticated-user defaults; the newer benchmark/nullable-field pass is locally verified but not redeployed |
| CI | workflow covers pytest + JS + consistency + soak + container/wrapper smoke; benchmark JSON/Markdown are now upload artifacts |

Plan milestones: M1–M3 done. M4 ("two real apps converted, deployed via clasp,
report reviewed") is the only open milestone.

State-checking before this rewrite caught one more real bug: the runtime
collection helpers were defined with a different parameter order than the
emitter emits (`function (ds)` vs emitted `powerapps_collect(state, 'Name', …)`
) — invisible to syntax checks and to tests that exercise each side in
isolation. Fixed in `89ddd58`, with signature-pinning tests plus
`scripts/check_runtime_consistency.py` as a permanent gate. Lesson: generated
code ↔ static runtime contracts need a cross-check in CI, not just unit tests.

---

## Corrective roadmap (2026-09-04 review)

The green syntax/soak baseline is necessary but is not behavioral-fidelity
evidence. The 2026-09-04 review found five release-blocking correctness gaps.
The first corrective pass is now implemented and regression-gated:

1. **✅ Truthful fidelity ledger.** Track translation separately from generated
   runtime wiring. Report ignored properties, generic component fallbacks,
   approximations, unpack warnings, and unsupported behavior; never call a
   formula converted merely because it produced syntactically valid JS.
   Acceptance: HelpDesk reports its empty components and unsupported form
   semantics instead of "no follow-ups."
2. **✅ Reactive and async runtime correctness.** Route `Set`/`UpdateContext` and
   `Clear` through the state update API, refresh bindings after handlers, wait
   for initial data loads, and surface rejected `APP_MAIN`/evaluator promises.
   Acceptance: a click-driven `Set` immediately changes dependent text,
   visibility, styles, and gallery items without navigation or a server call.
3. **✅ Fail-safe external mutations.** Never send executable predicates to Apps
   Script and never interpret a missing predicate as "match all." Evaluate the
   supported `RemoveIf` subset deterministically and send explicit record IDs;
   reject unsupported/malformed requests. Acceptance: only matching rows are
   removed and an empty match performs no mutation.
4. **✅ Reset and form honesty.** Implement real `Reset` plus input defaults and
   placeholders; never ship an unimplemented form action as a successful no-op.
   The Priority 2 pass now also implements deterministic Form/DataCard submit
   behavior and keeps unsupported capture inputs visible in the UI and report.
5. **✅ Secure deployment defaults.** Require an authenticated user by default,
   make anonymous/deployer execution explicit, whitelist generated data
   sources, validate API payloads, and remove unneeded scopes. Acceptance: a
   default conversion cannot expose deployer-owned Sheet mutation anonymously.

With these gates green, every real generated app is booted by the soak gate and
legacy component definitions are expanded into their actual child controls.
The project now moves from "can generate an app" to "can reliably produce a
usable app across representative Power Apps archetypes."

---

## Architecture decision: expand LLM use, but not whole-app code generation

The LLM should do more work, but it should not become the generator. Formula
translation is already 23,724 / 23,746 (99.9%); the larger gap is that only
15,292 formulas (64.4%) are wired into a runtime behavior or visual property.
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

## Current deployment evidence

HelpDesk-2021.msapp is deployed as @12 with component expansion, HtmlText
interiors, dynamic MENU navigation, and the visual/runtime pass that preceded
the new benchmark work:
`https://script.google.com/macros/s/AKfycbwbyTp89b-J_KEQ9N9wAf0OdJ8faH3k5gwAj_K1ToUFjaDPf8X35VBEnFQvfu5f2OJH/exec`

A live Chrome pass verified HOME rendering, HOME → NEW → HOME navigation, and a
record-valued Category dropdown displaying `IT` rather than `[object Object]`.
The HOME audit found 49 visible controls, zero private-use icon glyphs, only the
intended search-input border, and no generated-app warning/error. The manifest
requires a signed-in user and executes as that user (`ANYONE` /
`USER_ACCESSING`) with only the Sheets scope. A second representative deployment
is still required to close M4.

The deployed review produced regression gates for RGBA alpha, content-box
sizing, canvas offset, line-height, point-based font sizes, border color/style,
legacy alignment/weight enums, dynamic image sources, cross-platform icons, and
record-valued dropdown labels. Deployment plumbing is also gated: valid
manifest JSON, the server `include()` helper, full `.js.html` include names, and
generated `.gs` syntax.

---

## Next up, in recommended order

### 1. P0 — compatibility benchmark and quality tiers (foundation complete)

Implemented in the first priority pass: `benchmark/apps.json` now classifies
all 10 current apps by archetype and declares a critical journey for each;
`./pfx2gas soak` publishes machine-readable and reviewable scorecards under
`.artifacts/benchmark/`; CI uploads both artifacts. The generated-app simulator
now uses the data that `setup()` would seed, treats every startup console error
as a Bootable failure, and can run declarative click/change/screen/text/state
journeys. HelpDesk HOME → NEW → HOME is the first passing automated real-app
journey. The current honest result is **10 Bootable, 0 Usable, 0 High fidelity**:
all 10 higher-tier results remain `unassessed` until their complete journey and
visual evidence exists.

The stricter gate exposed two previously hidden blank-record crashes in SVG App
and Wordle. Nullable Power Fx field reads now compile through a deterministic
`FX.field` helper (Blank instead of a JavaScript exception), with unit and full
corpus regression coverage.

Expand the corpus from 10 examples to a versioned benchmark of at least 25–30
apps spanning: CRUD/forms, dashboards/charts, galleries/search/filter, approval
workflows, media/attachments, responsive containers, reusable components,
role-based experiences, and offline/collection-heavy apps. Include both modern
`pa.yaml` and legacy exports, simple and complex apps, and different source
connectors.

For every app, record three separate outcomes instead of one "converted" flag:

- **Bootable:** validates, starts on the correct screen, and has no startup
  runtime errors.
- **Usable:** all declared critical user journeys complete against the Google
  data layer without unsupported behavior.
- **High fidelity:** visual/interaction comparisons stay within explicit
  tolerances and every difference is ledgered.

Remaining acceptance work: expand to 25–30 representative licensed exports,
automate every required journey, add deterministic visual baselines/tolerances,
and persist cross-run regression history. No aggregate percentage may hide a
broken critical workflow.

### 2. P0 — usable-app primitives: forms, records, tables, and media

Implement the features most likely to turn a bootable conversion into a usable
business app:

- **✅ First tranche:** `SubmitForm` now performs DataCard value collection,
  required validation, stable-ID create vs update, `ResetForm`, `OnSuccess`,
  `OnFailure`, `Error`/`Valid`, and `LastSubmit`. A generated-app journey boots
  the output and proves edit, validation failure, reset, create, callback, and
  refreshed data behavior. The real Containers Guide form registers all 11
  cards and infers its Contacts Sheet schema.
- **✅ Selection foundation:** Dropdown/ComboBox/ListBox preserve record-valued
  `Selected`/`SelectedItems`, honor display fields/default selection and native
  multi-select; Gallery exposes `Selected`/`SelectedItems`/`AllItems`. Nested
  selection and `LastSubmit` field reads are blank-safe.
- **✅ Honest blockers:** camera, PenInput/signature, barcode, microphone,
  attachments, and AddMediaButton render visible unsupported placeholders and
  are enumerated in the conversion report instead of appearing as empty UI.
- editable DataTable and gallery patterns, validation messages, and error state;
- packaged media/resource extraction, attachments backed by Drive, and image
  fallbacks that distinguish "no image" from a failed asset;
- complete DataTable selection/display/search behavior and searchable ComboBox
  interaction beyond the native select approximation.

Acceptance: benchmark apps can create, view, edit, validate, and delete records;
reload preserves data; attachment/media paths work; the report identifies any
control that prevents a critical journey.

### 3. P0 — Google-native data and connector adapters

Separate formula/control conversion from source migration through a typed
adapter contract. Keep Sheets as the default table store, then add Drive for
files/attachments and optional Workspace adapters for Gmail, Calendar, and
Directory. Define explicit mappings for SharePoint/Dataverse/Excel concepts:
choice, lookup, person, attachment, calculated, date/time, permissions, and
row identity. Do not silently flatten unsupported types.

Add a real modern `pa.yaml` app backed by SharePoint or Excel to the benchmark,
convert it to the appropriate Google adapters, and make it the second deployed
app required by M4.

Acceptance: schema/choice/lookup metadata round-trips, CRUD works after reload,
permissions follow the selected execution identity, and connector-specific
losses appear in the fidelity report.

### 4. P1 — visual, component, and responsive equivalence lab

Turn the HelpDesk inspection process into repeatable tooling:

- capture the original and converted app at the same viewport, screen, data,
  and interaction state;
- compare bounding boxes, typography, colors, borders, visibility, images,
  scroll regions, and screenshots;
- automate all HelpDesk menu targets and Clean UI progress-bar geometry/styles;
- finish component outputs and modern `pa.yaml` component definitions;
- implement theme tokens, responsive/reflow formulas, nested containers, chart
  series/legends, gallery template size/padding/wrap, and transitions by measured
  corpus impact.

An LLM vision review may prioritize and describe mismatches, but the evidence is
the deterministic screenshot/DOM/style diff and the fix remains a generator or
runtime rule.

Acceptance: every benchmark critical screen has a reproducible visual baseline;
pixel/geometry thresholds fail CI; intended approximations are allowlisted and
ledgered rather than hidden.

### 5. P1 — guarded LLM coverage and review at scale

Run behavioral-equivalence review and QA-scenario generation on full real apps,
starting with HelpDesk. Improve the single-formula fallback before expanding
its use: provide typed control/data/source context, reject symbols outside the
generated capability surface, distinguish pure value expressions from mutation
handlers, execute isolated test cases, cache by prompt/model/source hash, and
record full provenance and confidence.

Add an LLM gap-triage report that clusters the fidelity ledger by business
impact and proposes deterministic rule/test work. Never let model confidence
change a fidelity status to `emitted` or `full`; only runtime wiring and passing
evidence can do that.

Acceptance: every high-risk LLM review finding is fixed, converted into a
regression test, or explicitly accepted; every LLM formula fallback is
allowlist-clean, syntax-clean, boot-tested, provenance-recorded, and still
reported as partial until its relevant journey passes.

### 6. P1 — scale, security, and identity

Add server-side filtering/sorting/pagination for data beyond the current ~5k-row
whole-tab guidance, optimistic concurrency/version checks, batched writes,
quota telemetry, and retry/error UX. Validate least-privilege scopes per
adapter. Complete `User()` with documented Workspace Directory support when
the deployment/domain exposes identity; retain safe name/avatar fallbacks when
it does not.

Acceptance: large-table benchmark journeys stay within Apps Script quotas,
concurrent edits do not silently overwrite data, and generated scopes/identity
behavior match the report.

### 7. P2 — measured compatibility tail

Prioritize the remaining controls, properties, Power Fx functions, delegation
patterns, and Power Automate replacements by frequency × critical-journey
impact in the expanded benchmark. Power Automate flows remain out of scope
until a workflow target and migration contract are explicitly designed; they
must continue to be flagged rather than dropped.

---

## Suggested sequence

| Step | Item | Effort | Depends on |
|---|---|---|---|
| 0 | ✅ Correctness, secure defaults, startup/consistency gates, first deployed visual smoke | complete | — |
| 1 | ⏳ Compatibility benchmark and three-tier scorecard foundation complete; corpus/journey/visual/history expansion remains | medium | representative app exports |
| 2 | Forms/DataCards, selected records, tables, media, and attachments | large | 1 |
| 3 | Typed Google adapter layer + modern real-data app + second deployment/M4 | large | 1–2, representative data app |
| 4 | Automated interaction and visual-equivalence lab; component/responsive/chart parity | large/ongoing | 1 |
| 5 | Guarded LLM review/fallback and gap-to-deterministic-rule flywheel | medium/ongoing | 1 and the existing safety gates |
| 6 | Pagination/concurrency/quota hardening, least privilege, and identity enrichment | medium/large | 3 |

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
