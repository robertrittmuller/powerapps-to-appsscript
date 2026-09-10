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

The Dataverse slice decodes native TableDefinition metadata and distinguishes
tables, collections, option sets, views and services. Generated storage keeps
source primary keys and logical/display field aliases; choices retain labels
and typed codes. Row writes validate all changed cells before mutation, including
invalid choices and conflicting aliases. Lookup snapshots and multi-select
values persist in structured cells; source dates cross google.script.run as ISO
text. A seventh Chromium fixture executes save/failure/create/delete/reload.
Every real-app soak now executes generated setup and table/choice reads against
the Sheets test double, in addition to syntax and client startup checks.

The time/validation slice adds TimeValue, localized date/time Text formats,
constant canvas regex matching, correct Find arguments and deferred
IsBlankOrError. Two complete Microsoft source formulas are retained with hashes
and their MIT license; executed formula tests and an eighth generated Chromium
fixture cover timestamps, localization and every URL-validation outcome.

The canvas slice preserves source design/scaling settings and App/screen
dimension formulas, including hidden-screen references, startup reads, minimum
sizes, custom breakpoints and fill. Viewport resize reevaluates bindings without
replacing edited inputs. Checkbox/toggle Value is boolean, correcting unintended
mobile routing and contrast themes in the real exports. Manual layout takes
precedence over dormant LayoutDirection settings; nested container and DataCard
children use local coordinates. Two additional Chromium fixtures cover manual
and automatic layouts, narrow/minimum widths, scaled interactions and retained
draft text/caret. AutoHeight dependency ordering and device orientation locking
still need implementation or verification.
Screen OnHidden is now wired and awaited before destination OnVisible. This
restores Employee Ideas' source initialization of mobile width, padding and
other values when leaving loading; its mobile first-action probe now passes.

Navigation now preserves literal context records and separates screen-local
variables from globals. A generated edit/save/reload journey proves the selected
second record is retained, an awaited handler updates its defining screen after
navigation, and hidden-screen references, Blank shadowing, zero/false and
case-insensitive names behave correctly. Milestones' first-run dialog now
appears because its source Navigate context survives. Arbitrary context-record
expressions remain unsupported; dynamic destination declarations are deferred
until first navigation and warned. Transition animations remain missing.

One live OpenRouter request verified the configured connection but failed
behavioral equivalence: its accepted timezone formula reversed the offset sign
at 0.98 model confidence, failing three of four timezone journeys. Offline
regressions retain that failure. The v3 static gate also rejects behavior
helpers and known mutating methods in value formulas; it is not an equivalence
proof or a JavaScript sandbox. Fallback receives screen/local metadata and now
includes App and screen properties, with unverified equivalence ledgered.

Saved-view filters now come from companion solution FetchXML, with source hashes
in each assessment. Supported nested filters and explicit ordering execute
against migrated tables; unsupported or missing queries fail even on empty
tables. Current-user views require exactly one migrated systemuser record
matching the actual Google session email. Startup awaits User() before running
source initialization. Template-stored legacy gallery actions now survive row
flattening. A native Chromium fixture verifies filtering/search, saved changes,
reload and selection through the original template action.
Relative day filters now support exported UserLocal columns for last-seven-days,
positive last-x-days, today, yesterday and tomorrow. They use the browser clock
and timezone; this migration assumption and recent-range boundary equivalence
remain ledgered. DateOnly/TimeZoneIndependent, missing subtype metadata and other
relative operators fail explicitly. Boundary tests include both DST changes;
the generated browser fixture checks save/reload and membership at the next
midnight. `TimeUnit` constants now retain the intended DateAdd unit instead of
silently reading an unset variable and defaulting to days.

Native FluidGrid and Form cards now interpret X/Y as order/row coordinates,
wrap minimum widths, expand WidthFit cards and use row heights. A generated
fixture verifies resize/hidden-card reflow, scrolling and retained input
nodes/text/focus/caret. Gallery template dimensions exist before first-row
binding. Exported Hidden/Scroll text overflow is preserved. Explicit table
lineage carries logical/display aliases into local collections, including
cache restoration; UpdateIf preserves inner-row scope and applies only the
first matching change. Conflicting aliases fail before mutation. Deferred
IsError restores the original source warning/recovery path around a failed post.
Top-level gallery TemplateSize formulas now resolve lazily before dependent
layout reads and update with state or viewport changes. A generated Chromium
fixture covers empty/populated cards, vertical and horizontal resizing, row
selection and retained edits. The unchanged Milestones settings card now measures
316 pixels; its 33 non-finite layout errors are gone, leaving the two explicit
user/directory migration failures. Dynamic orientation/padding/WrapCount and
nested gallery layouts remain open.
External UpdateIf, asynchronous predicates/change records, complete error-value
propagation and nested-gallery card layouts remain unsupported or unverified.

Lookup snapshots now use exported target-table metadata to expose logical,
canonical and display aliases recursively. Key-only references retain identity
without inventing names; ambiguous polymorphic references and conflicting or
invalid nested values fail before writes. Snapshots do not resolve current
related-table values or enforce relationships. Employee Ideas' question filter
now finds the correct campaign questions. Gallery updates use their own direct
template even when mounted rows contain nested templates. Conditional TextMode
retains single-line/multiline/password behavior and edits, focus, caret and
listeners across mode changes. Browser checks save and reload multiline answers.

Concurrent now starts deferred branches and waits for all results, preserving
each branch's action chain. Other branches finish even after one fails, and the
first error in source argument order propagates; success returns true. Executed
formula tests control response order, while Chromium verifies independent saves,
failure recovery and persistence after reload. Source error-management settings,
branch dependency validation and external side-effect ordering remain ledgered
review items. The LLM v6 gate rejects Concurrent, keyed-write and relationship-write helper references
in value proposals.

Two-argument Patch now updates by an explicit exported source primary key and
creates only when no stored row has that key. Validation or service failures never
fall through to creation; missing metadata/keys and ambiguous duplicate keys
fail explicitly. The generated native UI verifies save failure/retry, correct-row
updates, creation, repeated-key updates and reload. Keyless, inferred/composite
keys and table arguments remain unsupported. All generated API mutations now
hold a script lock across their reads and writes, flush before releasing, and
release after failures. The server test double enforces those invariants and
exercises lock timeouts, write failures and uncertain flush failures. This is
per-request serialization; client calculations and whole workflows are not
atomic, and live Google contention still needs verification.

Exported one-to-many and many-to-many relationships now use their actual
navigation aliases and source keys. A separate Sheets join table persists many-to-many membership;
Relate/Unrelate refreshes the first source's links and related-record snapshots,
while reverse reads wait for their own Refresh. Native Node startup and Chromium
journeys cover bidirectional membership, multiple parents/members, write-failure
recovery, repeat operations and page reload. Refreshing one source also sees
new related names without replacing the other source's cache. Conflicting schema
endpoints, ambiguous records, missing metadata/keys and orphaning deletes fail.
One-to-many reads use exported lookup keys, restore real campaign idea counts,
and support reassignment/unlinking with read-only/system-required field guards.
Retries are explicitly idempotent and unmatched Unrelate is a no-op. Alternate keys, cascades,
permissions, initial membership migration and live Google concurrency remain
open. Missing or unsupported navigation contracts raise an error rather than
silently returning an empty table. Opposing relationship writes in different
Concurrent branches receive a per-formula source-ordering warning.

The browser gate now drains dispatched server calls and includes console errors
observed during capture. A voting run exposed the old gate returning pass with
a nonempty error list. Deliberate pending-callback and late-capture errors now
fail their regression probes, alongside the existing screenshot-failure gate.

Eleven pinned source exports are available here: five public regression apps
and six Microsoft business apps. **All eleven generate valid code; six pass
the short startup check. None has complete usability acceptance evidence.**
Inspection's recent-date views now pass startup; its primary action reaches
Items Screen. Its Planner calls now use an explicit Google Sheets task-board
adapter; all five first-action checks pass with an authored imported board and
zero runtime errors. Missing migration still fails. Editable Grid's unexported
Student Tracker choice source is now correctly rejected by the startup simulator,
which previously returned an empty success for unknown RPCs. Missing
identity mappings, layout errors and connector dependencies leave four Microsoft
apps failing short startup, and all three default first-action probes still fail.
With one explicitly authored
user, four campaigns and three questions, Employee Ideas now passes 29 checks covering active
filtering/order/search, selected detail, mobile field geometry/labels,
required-title validation, single/multiline responses, submission, persistence,
reload, reopening and actual per-campaign idea counts. One unrelated campaign question is correctly excluded.
The source's failed Teams-post warning executes without aborting the save.
With an explicitly active migrated settings record and reviewed Chat space
mappings, a separate 31-check scenario executes the unchanged source notification
through native Google Chat API fixtures and reloads without reposting. No live
message is sent; native Google authorization and formatting remain unverified.
Its title remains deliberately truncated under source Wrap=false/Overflow.Hidden.
The optional voting probe now persists a count of one and executes relationship
operations, but fails its membership assertion: the exported Concurrent's
unconditional Unrelate leaves no voting-user link in this run. This is a source
race risk requiring original-app review; the converter does not rewrite it.
Ratings, attachments, manager workflows and
complete usability remain unassessed.
Milestones also exposes a nonfinite dtcSettings.Height dependency during startup;
the new card layout gate surfaces it instead of silently accepting NaN geometry.
Twenty generated-fixture Chromium journeys pass. Fixtures are regression
evidence, not additional real acceptance apps. The last recorded Google
deployment remains HelpDesk @14.

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
| Unit/runtime tests | 447 Python pass, 3 skip; 96 JS pass; bare globals, FX, FXRuntime and FX.collections emitter/runtime consistency passes | Complete deployed workflows and broader control semantics |
| Current real-app soak | 5/5 valid code and generated-server initialization; 4/5 Bootable; 1,145 formulas | Editable Grid requests choices from unexported Student Tracker; the former empty-success simulator hid this dependency. Usability unassessed; five historical local exports are absent |
| Current regression translation/wiring | 1,140 translated; 970 emitted, 14 approximated, 161 ignored/unsupported | Translation does not establish runtime behavior |
| Historical ten-app corpus | Previously 10/10 Bootable; 23,746 formulas | Not reproduced in this workspace; those results did not establish usability |
| HelpDesk generated-app journeys | HOME → NEW → HOME; dashboard row text, logo URI, pie and legend output pass | All-screen interactions, image decoding/layout in CI, persistence |
| HelpDesk @14 live browser | Ticket cards, decoded 64×64 logos, pie/bar/legend SVGs, readable fonts/labels, HOME → NEW → HOME | Same-state original comparison, user name/avatar, complete workflow coverage |
| Chromium: business form | Actual generated client + Code.gs: edit/create, required validation, write failure, delete and page reload pass against a persistent Sheets test double | Real Google authorization/Sheets writes and another user/session |
| Chromium regression suite | 21/21 fixtures pass, including responsive gallery template sizes and empty cards, native Chat selectors/notifications, stable horizontal gallery geometry/wrapping, native Google directory search/profile/photo assignment, imported Planner tasks, persisted relationships and relative-date view save/reload; three intentional failure gates preserve failed verdicts | Real Google services, real-app critical workflows and original visual comparisons; HelpDesk is absent here |
| Planner to Google adapter | Eight operations use generated Code.gs and a reserved Sheets task-board store. Chromium lists plans/buckets/tasks, creates and assigns, writes descriptions, selects/updates, reloads and recovers from failed writes. Labels and geometry pass. Missing migration, unknown/unmapped identity, denied membership, invalid dates and oversized records fail explicitly | Native Tasks UI, Planner roles/audit metadata, ordering hints, categories, notifications, aliases/additional operations and complete real-app workflows. Workbook editors bypass API membership checks; live identity and storage access require deployment verification |
| Office365Users/Microsoft365Users to Google | SearchUser, UserProfileV2 and UserPhotoV2 use native Google People with explicit source-ID/account mappings and manifest scopes. Chromium searches, selects the correct profile/photo, excludes the assigned person, creates a task with the preserved source ID, reloads, and recovers from API/write failures | Native API responses and images are authored fixtures. Live directory access/photo visibility, unsupported Microsoft fields, exact search semantics and complete real-app assignment flows remain unverified. Owner-delegated access is denied |
| MicrosoftTeams to Google Chat | Four exported operations preserve source team/channel IDs through explicit named-space mappings. Native joined-space checks, deterministic supported HTML-to-Markdown posts, byte limits and API failures execute in generated-server tests. Chromium selectors, labels, posting/reload and error recovery pass. The unchanged Employee Ideas notification scenario passes 31 checks | Explicit native API fixtures, no live messages. Google Cloud/OAuth setup, native rendering, richer HTML, attachments, Teams roles/settings, connector aliases and complete workflows remain open; the hierarchy exists in the converted UI rather than native Chat |
| Dropdown displayed column | Source Dropdown.Value now selects readable labels in standalone and gallery-row controls while preserving selected source records. A pinpoint runtime check and the Chat Chromium fixture cover both generation paths | Modern ItemDisplayText and full native picker/search behavior remain separate gaps |
| Formula-created gallery records | Equal unkeyed records from literal/computed tables reuse their controls across reevaluation. Existing object identities are reserved before matching fresh records by typed values; native IDs remain preferred. Chromium retains the selected channel and exact DOM node through edits and posting; runtime tests cover duplicate equal records, ordering and date/text distinctions | Identical unkeyed clones use prior occurrence order; unsupported/cyclic data cannot be matched by value. Broader computed-table and nested-gallery semantics remain unverified |
| Gallery template dimensions | Static orientation and reactive TemplateSize determine template dimensions before row mounting. Chromium verifies the original loading formula stays 224 × 88, wrapping/selection, responsive 72/84-pixel vertical rows and 48/64-pixel horizontal rows, empty-card heights and retained input nodes/text. The unchanged Milestones settings card is 316 pixels without layout errors | Dynamic orientation/padding/WrapCount, nested galleries, exact native cross-axis sizing and original visual comparison remain gaps |
| Dataverse ownership | Exported Owner fields default to a migrated Google caller on create; explicit user/team assignments update derived ownership columns while ordinary edits retain ownership. Generated-server tests cover source keys/aliases, two users, team assignment, ambiguous/missing identities and failure without partial writes. Validation checks source/ledger ownership contracts | Ownership is record data; source row security, privileges, cascading assignment, business units, audit/status defaults and live Google execution remain open |
| Milestones populated onboarding | 19 checks pass across two simulated Google users: source first-run dialog, dismissal, reload, separate settings and returning-user behavior, with zero runtime errors | Project probe passes 28 checks but repeats the first edited milestone name in all three saved rows; dates are blank and colors fall back to gray. Complete project/work-item functionality and UI remain unproven |
| Microsoft generated-server initialization | Six exports: setup and reads across 124 tables and 302 choice fields pass in the Sheets test double | Tenant data migration, real Google writes, source defaults, calculations, relationships and permissions |
| Microsoft business baseline | 6/6 convert and validate; 2/6 pass short startup (Employee Ideas, Inspection) | Migrated identities and Teams/Planner dependencies still fail prerequisites |
| Microsoft first actions | All three default probes fail. A separate Inspection probe with an authored imported Google task board passes all five checks and has zero runtime errors; it cannot overwrite the default missing-migration failure. Populated Employee Ideas passes 29 checks through mobile submission and reload. Optional voting persists its count but source Concurrent removes the voter link | Complete inspection/task creation, voting ordering, ratings, attachments, real Google persistence, identities and UI parity; partial success never promotes an app to Usable |
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
| 2. Preserve initialization and data contracts (R5) — next | `Param`, browser `Language()`, Timer lifecycle and explicit initialization failures are implemented. Native Dataverse schemas, aliases, source keys, choices and common relationships now feed generated storage. Next implement remaining relationship semantics, defaults/calculations, typed date/choice behavior and explicit Google connector adapters. Do not fake connector success or navigate past unexecuted initialization. |
| 3. Make record editing reliable (R4/R5) | Stable gallery rows, scoped handlers, defaults/DisplayMode, focus retention and correct-row save/reload pass in generated fixtures. Extend to source business apps, nested layouts and real Google Sheets. |
| 4. Close visible UI differences (R2/R3/R4) | Use those same workflows for text/media/disabled/validation states, chart series/axes and responsive layout. Extend Chromium to source-sized and narrow viewports and compare matching original screenshots. |

Milestones supplies the first project/task lifecycle target; Employee Ideas and
Inspection verify that fixes generalize. The Microsoft baseline still exits 1
with three startup failures; first-action failures keep the other three below Usable/High fidelity,
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

| Microsoft export | Latest observed blocker | Additional source dependencies to preserve |
|---|---|---|
| Employee Ideas | Default first action stops on an unmigrated current user. Populated data passes 29 checks; native Chat fixture variant passes 31. Voting membership still fails on the source's opposing relationship writes | Ratings, attachments, complete manager workflows, live target services and original visual comparison |
| Employee Ideas Manager | GetAllTeams requires explicit Chat migration and native authorization | Complete team/channel setup, campaign editing and notifications with migrated data |
| Inspection | Leaves Landing for Welcome/Items; all five first-action checks pass with an explicitly imported Sheets task board. Unmigrated Planner fails | Local drafts, shared tasks and native Google directory assignment pass in fixtures; full real inspection/task submission, migrated identities and Teams-to-Chat posting remain |
| Inspection Manager | Current-user identity and required Chat/Planner migrations | Plan/bucket/task/group-plan setup and complete inspection management; URL validation formula has executed evidence |
| Milestones | Nonfinite dtcSettings.Height, unmigrated current user and Google directory mappings | Complete project/task creation, assignment, relational data and readable onboarding/layout |
| Review Inspections | Current-user identity; Planner migration is also required | Complete review workflow, inspection data, task associations and live authorization |

Typed toggle values, source canvas dimensions, OnHidden initialization and
editable-gallery focus/selection now have regression evidence. Extend the
implemented Google connector subsets through complete data-backed journeys,
resolve remaining source geometry dependencies, and compare original/converted
UI in the same data state. Missing migrations and failed workflows must retain
failed verdicts; do not bypass initialization or substitute empty success.

The decoder now retains `NativeCDSDataSourceInfo.TableDefinition` attributes,
keys, choices, relationships, views and logical/display-name mappings in
`data-contract.json`. OptionSetInfo constants initialize typed client values;
services remain explicit adapter dependencies. Saved views now accept companion
solution FetchXML for a bounded deterministic subset. Other relative dates, joins,
aggregates, paging/limits and localized choice-label ordering fail explicitly;
numeric choice ordering requires exported `useraworderby="true"`. Tenant text
collation and implicit primary-key ordering are ledgered approximations.
Missing metadata cannot use LLM fallback. Lookup records are
stored snapshots, not live relationships. Source defaults/calculated fields,
permissions, implicit localized choice-to-text conversion and complete typed
date comparisons remain unimplemented or unverified. These are converter gaps,
not missing export evidence. Source inspection artifacts are under `.artifacts/`.
Inspection also uses legacy bare `Minutes` in DateDiff. Contextual bare-unit
resolution and DateDiff's whole-unit boundaries need follow-up; the current
duration helper still returns fractions for subday units and has incomplete
millisecond/quarter semantics. The new explicit TimeUnit enum mapping does not
establish complete date-arithmetic parity.

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
Viewport resize invalidation, manual nested-container positioning and native
form/card grids now have browser gates. Extend these to AutoHeight,
forward-dependent positions, nested galleries and more real workflows. Preserve the source
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
