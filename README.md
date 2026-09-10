# pfx2gas — Power Apps → Google Apps Script converter

`pfx2gas` converts a Microsoft Power Apps **canvas app** (`.msapp` file) into a
runnable **Google Apps Script web app**: an HtmlService single-page UI, a
`google.script.run` server API, and a Google Sheets data layer — plus an
honest, per-formula **conversion report** of what was converted, what was
approximated, and what needs human attention.

Microsoft service dependencies should migrate to Google services where possible.
For capabilities without a faithful native equivalent, preserve their behavior
through an Apps Script adapter and record the differences. The
[Google service mapping](benchmark/GOOGLE_SERVICE_MAPPING.md) tracks this work;
unimplemented adapters remain explicit conversion gaps.

The Planner adapter maps eight exported operations to a shared Sheets task board.
Apps declaring Planner include `PlannerMigration.gs` and `planner-migration.md`:
run `setup()`, supply reviewed source records and Google-user mappings, then run
the private migration function in the Apps Script editor. Missing migration is
an error. Membership, dates, assignments, creation and description updates have
generated-server and Chromium evidence; live Google deployment remains unverified.

Office365Users and Microsoft365Users search, profile and photo calls now use the
native Google People directory. Generated projects include `DirectoryMigration.gs`
and `directory-migration.md` for mapping source user IDs to Google accounts.
The manifest enables People v1 and directory access; the app must execute as the
identified accessing user with domain directory sharing enabled. A Chromium
journey covers search, profile/photo selection and persisted task assignment
using explicit native API response fixtures. Live directory permissions and
photo visibility remain deployment checks.

Dataverse user/team-owned rows now default to the migrated Google caller when
the source formula omits Owner. Import the source Users records with their
original keys and Google emails in `internalemailaddress`; this is separate
from the Office365Users directory mapping. Explicit user/team assignments are
retained and Owning User/Team follows the owner. Missing or ambiguous identities
fail before writing. Ownership is stored record data; Dataverse security roles,
business units, audit timestamps and other defaults remain separate gaps.

Dataverse state and status reason fields use their exported option relationships
and per-state defaults. The standard Active/Inactive model creates active rows;
other models need an exported initial state. State changes choose the matching
default reason, explicit reasons must belong to the selected state, and source
read-only flags are honored. Missing metadata and custom transition rules fail
explicitly. Both the ledger and data contract retain the adapter. Existing rows
are not backfilled, and audit timestamps, plugins and other column defaults
remain unsupported.

MicrosoftTeams team/channel selectors and notifications now use native Google
Chat. `ChatMigration.gs` and `chat-migration.md` map original IDs to named Google
spaces, with an anchor space representing each logical team. The accessing user
must belong to the mapped spaces. Supported source HTML becomes escaped Chat
Markdown; unsupported content fails before posting. Generated-server and Chromium
tests use explicit API fixtures. Live authorization and native rendering remain
unverified; tests send no real messages.

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
  fields from mutations, references, and Form DataCards, and transpiles every formula
  with a coverage ledger of what succeeded.
- **Synthesize** — emits the Apps Script project (see layout below).
- **Validate** — `node --check` every generated script, structural checks,
  count of unsupported-function stubs.
- **Report** — `conversion-report.md`: per-formula status table, data mapping,
  manual follow-ups, capacity notes.

## Requirements

Docker is the only host requirement. Python 3.11, Node 20, uv, and clasp are
provided by the project image. The
`./pfx2gas` wrapper works from any directory and maps host paths into the
container automatically:

```bash
./pfx2gas build    # re-run this after changing converter source (code is baked into the image)
./pfx2gas convert ~/Apps/YourApp.msapp -o ~/Apps/output/YourApp  # any paths
./pfx2gas test                                                   # full suite
./pfx2gas soak                                                   # real-app benchmark + scorecard
./pfx2gas build browser                                          # optional Chromium test image
./pfx2gas browser                                                # generated client + server journeys

# deployment (credentials persist in .clasp-home/):
./pfx2gas clasp login --no-localhost                             # once
./pfx2gas clasp -w /abs/path/output/YourApp create --title YourApp --type webapp
./pfx2gas clasp -w /abs/path/output/YourApp push --force
./pfx2gas clasp -w /abs/path/output/YourApp deploy
```

## Install

```bash
git clone <this repo>
cd powerapps-to-appsscript
./pfx2gas build
./pfx2gas test
```

## Quick start

Export your app from Power Apps Studio (**Save As → This computer**) to get
`YourApp.msapp`, then:

```bash
./pfx2gas convert YourApp.msapp -o output/YourApp
```

This prints a summary, writes the converted project to `output/YourApp/`, and
exits non-zero if the validator finds problems. Review
`output/YourApp/conversion-report.md` next — it is the contract for the
remaining manual work.

Deploy with clasp:

```bash
./pfx2gas clasp login --no-localhost                                    # once
./pfx2gas clasp -w /abs/path/output/YourApp create --title YourApp --type webapp
# clasp create replaces appsscript.json; restore the converter-generated manifest.
./pfx2gas convert YourApp.msapp -o /abs/path/output/YourApp --no-llm
./pfx2gas clasp -w /abs/path/output/YourApp push --force
./pfx2gas clasp -w /abs/path/output/YourApp open-script                 # run setup() once
./pfx2gas clasp -w /abs/path/output/YourApp deploy
```

The first `setup()` run creates one Google Sheet workbook with a tab per
external data source (seeded with the app's embedded sample data when the
export carries it) and stores its ID in script properties; the API layer
reads/writes it. Power Apps **collections** (`Collect`/`ClearCollect`) are
client-side state, not external tables: they become in-memory arrays in the
converted app and never hit the Sheet.

## CLI reference

```
./pfx2gas convert <file.msapp> [-o DIR] [--report-only] [--no-llm]
./pfx2gas validate <project_dir> [--strict-fidelity]
```

| Option | Meaning |
|---|---|
| `-o, --output DIR` | Output directory (default `./output/<AppName>`) |
| `--report-only` | Produce only `conversion-report.md`, no project files |
| `--no-llm` | Disable the LLM fallback; unmapped formulas stay stubs |
| `--no-review` | Disable the LLM behavioral-equivalence review + QA scenarios |
| `--solution ZIP_OR_XML` | Load saved-view FetchXML from an exported solution ZIP or `customizations.xml` |
| `--webapp-access` | `ANYONE` (signed-in default), `MYSELF`, `DOMAIN`, or explicit `ANYONE_ANONYMOUS` |
| `--execute-as` | `USER_ACCESSING` (default) or explicit `USER_DEPLOYING` |
| `--strict-fidelity` | Exit non-zero when the generated fidelity ledger contains gaps |
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
├── conversion-ledger.json # machine-readable translation/runtime-wiring ledger
├── data-contract.json    # source fields, keys, aliases, choices and retained metadata
└── conversion-report.md  # fidelity ledger — read this before shipping
```

Static files (`gas-runtime`, `fx-stdlib`) are shared runtime, not generated
per-app; everything else is derived from your app.

## Business-app acceptance testing

The acceptance targets are Microsoft's **Milestones, Employee Ideas and
Inspection** templates (six canvas exports including their manager/review apps).
Their pinned source packages, feature distribution and evidence limitations are
documented in [benchmark/SOURCES.md](benchmark/SOURCES.md).

```bash
./pfx2gas browser scripts/assess_microsoft_samples.py
```

This separate baseline currently fails. It also exercises source loading and
first actions for Milestones, Employee Ideas and Inspection in Chromium,
retaining delayed connector errors and unreadable primary controls as failures.
These are partial workflow checks; complete usability remains unproven.
`./pfx2gas browser scripts/assess_employee_workflow.py` adds explicitly authored
campaign/user/question records through generated Code.gs before startup. Its 29 checks
pass: campaign filtering/order/search/selection, mobile field layout and labels,
required-title validation, single/multiline custom responses, campaign idea counts, submission,
persistence, reload and reopening. The unmigrated Teams post follows the source
warning/recovery path. Adding `--voting` persists a count of one, but fails the
membership assertion: the exported Concurrent runs both Relate and an
unconditional Unrelate, leaving no voter link in this run. That source ordering
risk is ledgered; the converter preserves the source actions.
Adding `--chat` imports reviewed example space mappings and an explicitly active
notification settings record. Its 31 checks include the unchanged source's native
Chat request, preserved team/channel IDs, successful submission and reload without
reposting. Google API responses are fixtures; this is partial workflow evidence.
The browser gate waits for dispatched server calls and includes errors that
arrive during capture before assigning a verdict.
Ratings, attachments, manager workflows and complete app usability remain unassessed.
`./pfx2gas browser scripts/assess_milestones_workflow.py` verifies original
Milestones onboarding and persisted settings across two simulated Google users.
All 19 checks pass. Its `--project` probe reaches project/member creation through
native Google People fixtures and saves three distinct edited milestone names and dates.
All 39 checks pass, including dates across the daylight-saving change, opening
the second nested color picker, selecting a different color, and preserving each
milestone's name/date/color in storage. Adding `--workitem` passes 77 checks through
project creation, work-item creation, Google-user assignment, milestone linkage,
reload, reopening with typed defaults, edit and confirmed deletion. It retains
the same work-item ID and linked identities through edits, and deletion preserves
the project and its milestones. These use generated Code.gs and native Google
API fixtures. Its complete icon/localization/character-width tables now survive
conversion, and the milestone label measures the source formula's 115 pixels.
Adding `--settings` tests original category/priority/status creation before the
work-item lifecycle. Empty names now disable Save using the source control's
exported primary output, and status captions preserve arithmetic precedence.
All 109 checks now pass: five settings remain active after reload, and the
work-item lifecycle retains the selected status/category/priority identities.
The unchanged Save formula omits status Sequence; reload follows the exported
Active view's name ordering. Arbitrary completion-status positioning and
tenant-side sequence population remain unverified.
Broader workflows, source-imposed column clipping and
complete app usability remain open. Source/data hashes,
records and screenshots are in `.artifacts/browser/`.
The normal `./pfx2gas soak` enforces the existing
required regression corpus, including failed required journeys and missing apps.
It currently fails Editable Grid because its choice formulas reference the
unexported Student Tracker source. The startup simulator now retains that
dependency failure instead of returning an empty successful response.

`./pfx2gas browser` tests generated forms, charts, record scopes, editable
galleries, timer lifecycles, launch parameters, local drafts, Dataverse record
contracts and state/status defaults with activation/deactivation and reload,
complete source timestamp/URL-validation formulas, responsive and
scaled canvases, card grids, responsive gallery template sizes and horizontal wrapping, the migrated Planner task board,
native Google directory assignments, Chat selectors/notifications, record-valued
selector defaults/reset in both standalone and row controls, independent nested
property reads, checkbox editing without accidental gallery navigation, Fluent date entry/reset/bulk save,
typed collection aliases and conditional draft
updates in Chromium, plus HelpDesk
when its local export is present. It runs
generated `doGet`/client/server code against a Sheets test double to check save,
validation, failure, delete and reload behavior, including safe request templating.
Screenshots and DOM measurements are saved under `.artifacts/browser/` and
uploaded by CI. Real Google deployment and original-versus-converted visual
comparison remain separate acceptance steps.

The real-app soak also executes generated `setup()`, table reads and exported
choice reads against the Sheets test double. A server initialization failure
fails the app's startup gate even when all files pass syntax validation.

## The conversion report

Translation and generated runtime wiring are reported separately. A formula
can translate successfully while its control/property is still ignored by the
synthesizer. Runtime-wiring statuses are:

- **emitted** — deterministic synthesis wires the formula into the app; this
  is not, by itself, deployed behavioral proof.
- **partial** — an approximation or LLM translation that needs QA.
- **ignored** — translation exists but the property/control has no runtime wiring.
- **unsupported** — emitted as an explicit `FX.unsupported(...)` failure.

The report also contains the data mapping (original source → Sheet tab +
inferred fields) and Apps Script capacity notes (6-min executions, 30
concurrent, 30-s web-app response budget — read whole-tab data sizes
accordingly).

## UI parity

Converted apps aim to match the original visually and behaviorally:

- **Layout** — static `X/Y/Width/Height/ZIndex` become absolutely-positioned
  inline styles; reactive ones (e.g. `X: =Parent.Width/2 - 40`) become
  `styleControl` evaluators re-applied on state changes and viewport resize.
  Manual containers and DataCard children retain their local coordinates;
  an exported `LayoutMode.Manual` takes precedence over a dormant direction.
- **Canvas dimensions** — exported design size, scaling and aspect settings
  are retained. App/screen width, height, minimum size, breakpoints, orientation
  and screen fill formulas are available during startup and on hidden screens.
  Browser tests cover minimum-width scrolling, uniform scaling, breakpoint
  boundaries and unsaved input/focus retention on resize. Device orientation
  locking and full AutoHeight dependency handling remain
  unverified; retaining an exported setting is not proof of complete support.
- **Card layouts** — Form and native FluidGrid cards use source row/order
  coordinates, minimum widths, wrapping, WidthFit expansion and row heights.
  Hidden cards leave the flow; children read the resulting card dimensions.
  Narrow-screen tests retain input nodes, text, focus and caret while wrapping
  and scrolling. Nested gallery card layouts remain unverified. Source
  Overflow.Hidden and Overflow.Scroll retain clipping and scroll access.
- **Screen lifecycle** — navigation runs the departing screen's `OnHidden`
  before the destination's `OnVisible`, with each screen's own `Self` reference.
  Failed exit behavior is surfaced, and superseded navigation cannot run a
  delayed entry handler for an obsolete destination.
- **Navigation context** — `Navigate` passes a literal context record before
  destination bindings and `OnVisible` execute. `UpdateContext` updates only its
  defining screen, including after an awaited save or navigation. Context names
  are case-insensitive and preserve Blank, zero, false and selected records;
  locals shadow globals, `[@name]` reads the global, and `Set` writes the global.
  A generated browser journey verifies second-record edit/save/reload, retained
  locals, and hidden-screen references. Arbitrary context-record expressions
  remain unsupported; dynamic destinations defer local declarations until the
  first navigation and are warned. Transition animations remain unimplemented.
- **Auto-layout** — modern containers render as CSS flexbox: `LayoutDirection`,
  `LayoutAlignItems`, `LayoutJustifyContent`, `LayoutWrap`, `LayoutGap`,
  `FillPortions` (flex), `LayoutMinWidth/Height`, `LayoutOverflowX/Y`.
- **Typography & text** — `Font`, `Size`, `FontColor`, `FontWeight`,
  `Italic`, `Underline`, `Strikethrough`, `LineHeight`, `Align`,
  `VerticalAlign`, `Wrap`; requested faces retain cross-platform serif,
  sans-serif, or monospace fallbacks.
- **Text input modes** — literal and conditional `TextMode.SingleLine`,
  `MultiLine` and `Password` select the corresponding native input. Mode changes
  retain edits, event handlers, focus and caret; unrelated updates retain the
  node. Generated browser checks cover standalone and per-row controls, newline
  persistence and adding rows whose templates contain another gallery.
- **Borders & effects** — `BorderStyle` (solid/dashed/dotted/double),
  thickness, color, radius per corner, `DropShadow`, `HoverFill/Color/BorderColor`,
  `PressedFill/Color/BorderColor`, `DisabledFill/Color/BorderColor`,
  `FocusedBorderColor/Fill` (as CSS `:hover/:active/:disabled/:focus-visible` rules).
- **Images and packaged media** — `Image` src, `ImagePosition` (object-fit),
  `ImageRotation`; safe local PNG/JPEG/GIF/WebP resources are embedded as data
  URIs so old docserver URLs and asset-name/icon-name collisions cannot break
  the generated app.
- **Accessibility & input semantics** — `Role` (ARIA roles), `AccessibleLabel`/
  `Tooltip` (aria-label), `Live` (aria-live), `TabIndex`, `DisplayMode: Disabled`
  (disabled/readonly attributes), `MaxLength`, `VirtualKeyboardMode` (inputmode),
  `DelayOutput`.
- **Galleries** — the row template renders per item with `ThisItem` bound to
  the row; template size/padding and absolute child geometry are retained;
  top-level TemplateSize formulas update with state and viewport changes.
  TemplateWidth/TemplateHeight exist before rows mount, including empty
  galleries whose surrounding cards depend on their height. Circular or
  non-finite template formulas fail explicitly. Orientation, padding and
  WrapCount currently require static values; broader nested layouts still need review.
  Child handlers receive the item, preserving per-row actions. Row clicks
  expose record-valued `Selected` and `SelectedItems`. `AllItems` includes loaded
  records and each row's controls; `AllItemsCount` counts the loaded rows.
  Bulk formulas retain per-row edits through aliases, sorting, nested record
  scopes and awaited saves. Control records omit DOM nodes from JSON transport.
  Stable IDs
  retain row inputs, focus and text selection across state updates and sorting;
  row references, defaults, selectors, images, disabled states, Reset and
  OnChange use that row's controls. Child `Select(Parent)` actions are queued
  after the child handler, avoiding duplicate parent actions from DOM bubbling.
  ID-less records use object identity, then typed equality for fresh equivalent
  records. Identical clones follow prior occurrence order.
- **Selectors** — Dropdown, ComboBox, and ListBox options preserve their source
  records for `Selected`/`SelectedItems`; `DisplayFields`, default selections,
  and multi-select are wired into native selects.
- **Exported reference data** — initialization preserves all exported seed rows,
  including static lookup tables beyond row 100. Sheet rows and columns expand
  before initialization and API writes. This preserves the export's snapshots;
  tenant data migration and existing-workbook backfills remain separate work.
- **Font values** — Segoe UI retains its source CSS fallback stack, and Normal,
  Semibold, Bold and Lighter retain their CSS weight values for formula comparisons.
  Static font stacks preserve separate faces. Source-shaped character-width lookups
  and rendered row dimensions pass; font availability and other enum mappings
  still require review.
- **Nested galleries** — each outer row owns an independent child gallery,
  with its own Default/Selected, ThisItem.IsSelected, current control values and
  parent event routing. Node and Chromium check empty/repopulated items, pointer
  and keyboard selection, nested edits retained through resize/sort, Reset
  without recursively resetting children, and correct-row bulk saves/reload.
  Button labels stay inside their source-sized rectangles, preventing transparent
  text from intercepting neighboring color clicks. Loading remains eager;
  cross-level record aliases, additional control types and full layout parity
  still require review.
- **Fluent date inputs** — Teams' `Microsoft_CoreControls_DatePicker` becomes a
  native date input. Its Value is a local-midnight Date; classic SelectedDate
  follows the same date contract. Defaults, independent gallery edits, Blank,
  Reset, OnChange, DisplayMode, focus eligibility and accessible labels have
  generated runtime and Chromium coverage, including persisted bulk saves/reload.
  Date plus/minus days preserves civil dates across DST, Date subtraction returns
  days, and DateAdd no longer mutates its input. Browser calendar appearance,
  source timezone settings, typed Time arithmetic and persisted ISO operand
  typing remain review items; this does not establish complete date parity.
- **Self sizing dependencies** — consumed semantic properties such as Size and
  Padding resolve forward references, with cycle checks and caching within each
  control snapshot. Legacy bare screen-size Switch cases retain declared variable
  shadowing. Split exposes Value plus a legacy Result alias through AddColumns;
  that alias is not preserved through JSON or all table-copy operations, as ledgered.
- **Input defaults and disabled states** — standalone text, date, checkbox and
  slider defaults react to loaded records while preserving edits through
  unrelated state updates. Reset restores the current default. Native inputs
  and buttons reevaluate source DisplayMode formulas as the user types.
  Toggle/checkbox `Value` is boolean; slider `Value` is numeric and button
  `Text` reads its visible caption.
- **Legacy canvas components** — definitions in `Components/*.json` are inlined
  per instance with namespaced children and reactive custom inputs. This covers
  the corpus's MENU, TILES/BUSCADOR, and progress-bar components; static
  `HtmlText` interiors are preserved with executable markup removed.
- **Charts** — legacy pie/bar/line families render as SVG, including visible
  single-value pies; generated series labels/color sets feed separate Legend
  controls instead of rendering `No data`.
- **Forms** — `NewForm`/`EditForm`/`ViewForm`, `ResetForm`, and `SubmitForm` use
  DataCard metadata to load and collect values, validate required fields,
  create or update a stable Sheet row, expose `Error`/`Valid`/`LastSubmit`, and
  run `OnSuccess`/`OnFailure`.
- **Record formulas** — nested/quoted fields are blank-safe; nested `With` and
  table predicates preserve row/global scope and the enclosing gallery's
  `ThisItem`. LookUp projections and AddColumns field pairs are retained.
  `As` aliases work in nested record functions and gallery templates;
  `Table[@Field]` resolves the active table record and `[@Name]` bypasses it.
  Column projections preserve a single-column table; `in`/`exactin` support
  membership with the corresponding case rules. GroupBy/Ungroup retain local
  nested rows for aggregation and filtering, including nested ForAll results.
  Two-argument `IfError` can recover from an awaited save; nested saves expose
  fields for the generated Sheet schema and receive stable row IDs when absent.
- **Typed local collections** — explicit Collect/ClearCollect lineage from an
  exported table carries its logical/display aliases into local records.
  Collect, Patch, Remove, UpdateIf and cache restoration preserve those aliases;
  conflicting alias values fail before changing records. UpdateIf applies the
  first matching condition/change pair with the correct row scope. External
  UpdateIf and asynchronous conditions/change records remain unsupported.
  IsError defers synchronous/async failures so source warning paths can recover;
  complete Power Fx error-value propagation remains unimplemented.
- **Dataverse data contracts** — native exports retain their field types,
  logical/display aliases, primary keys, choice codes/labels and relationship
  metadata. Option sets initialize client constants; services and views do not
  become Sheet tabs. Updates preserve source keys and validate changed cells
  before writing a row. Choices use exported labels and typed values; zero and
  false remain distinct from Blank. Dates cross the Apps Script bridge as ISO
  text. Lookup record snapshots and multi-select values persist as structured
  cells. Source defaults/calculations/permissions and
  implicit localized choice-to-text coercion still need target adapters.
- **Relationships** — exported navigation names, schema names and
  source keys drive related-table reads and `Relate`/`Unrelate`. Many-to-many links persist in
  a separate `__pfx2gas_links` tab. Refreshing the first source fetches its links
  and current related records; the reverse source retains its snapshot until
  explicitly refreshed. Missing/ambiguous keys, conflicting metadata and write
  failures raise errors. Retried link operations are idempotent in this target
  adapter; unmatched Unrelate is a no-op. One-to-many relationships use the
  exported lookup field, support reassignment/unlinking, and honor read-only and
  system-required lookup flags. Delete requires explicit unlinking first;
  alternate-key relationships, cascades, Dataverse permissions and live Google contention remain unsupported
  or unverified. Existing deployments must rerun `setup()` to add join storage;
  existing source memberships still require data migration. The export alone
  does not contain those membership rows.
- **Dataverse saved views** — supply `--solution path/to/export.zip` when the
  canvas export carries view IDs but omits their FetchXML. Supported direct
  `Filter(Table, 'Table Views'.'View name')` arguments preserve nested AND/OR,
  typed comparisons, membership/null tests and explicit multi-column ordering.
  Current-user filters match the Google session email to exactly one migrated
  `systemuser` record; missing/ambiguous mappings fail. Startup loads `User()`
  before source initialization can capture its email. This is a functional
  identity mapping, not Dataverse authorization. `last-seven-days`, `last-x-days`
  (positive 32-bit day count), `today`, `yesterday` and `tomorrow` work on columns
  with explicitly exported `UserLocal` date behavior. They use the browser clock
  and timezone, with calendar boundaries across daylight saving changes.
  Recent-day ranges start at local midnight N days ago and exclude the query
  instant and future timestamps. These ranges remain ledgered approximations:
  source-tenant boundary equivalence, server clock and per-user timezone settings
  are unverified. Migrated timestamps must include an explicit timezone.
  Missing date behavior, `DateOnly`/`TimeZoneIndependent` relative filters, other
  relative operators, joins, aggregates, paging/limits and localized choice ordering remain unsupported;
  choice ordering is numeric only when FetchXML explicitly requests
  `useraworderby="true"`. Tenant text collation and implicit primary-key order
  are ledgered approximations. Missing queries fail even on empty tables and
  cannot be invented by the LLM. The ledger records solution hashes and queries.
- **Behavior syntax** — block/line comments, `And`/`Or`/`Not`, and nested
  semicolon-separated actions retain branch-local execution order.
  Multi-condition `If` retains every branch and its optional fallback;
  `Switch` evaluates its subject once. Selected async results are awaited.
  Sort/SortByColumns preserve normalized column names, ascending/descending
  directions and multiple column/order pairs.
  `Concurrent` starts deferred branches, waits for all of them and returns true
  on success or propagates the first error in source argument order. A branch
  failure does not stop its siblings. Generated browser tests verify independent
  saves, recovery and reload. Source error-management settings, dependency
  validation and external side-effect ordering remain ledgered review items.
- **Keyed Patch and write locking** — `Patch(Source, Record)` updates by the
  explicit exported source primary key, or creates when no stored row has that key.
  Logical/display aliases, unchanged fields and typed zero/false values survive.
  Validation and service failures never trigger an automatic create. Keyless
  records, inferred or composite keys and table arguments remain unsupported;
  unkeyed collections cannot use this overload. Generated API mutations wait up
  to 30 seconds for a script lock, flush Sheets and release it even on failure.
  This protects each server read/modify/write operation, not an entire business
  workflow or calculations performed earlier in the client. Live multi-user
  Google contention is still unverified.
- **Local drafts** — SaveData/LoadData/ClearData use browser storage for local
  collections. LoadData appends saved rows; its optional flag suppresses only
  missing entries. Nested records/tables, dates, blanks, zero and false survive
  reloads. Cache names are scoped to the deployed script and identified user.
  When Google supplies no user identity, sessions share that app's cache in
  the browser profile. Storage is plaintext, limited to 1 MB per encoded entry,
  and can be unavailable or removed by browser settings. This does not make
  the Apps Script page or remote data services available offline.
- **Time and validation formulas** — TimeValue handles clock text, fractional
  seconds, localized day periods and ISO timestamps. Text distinguishes minutes
  from months and retains its output-language argument for date/time labels.
  IsMatch/Match/MatchAll support constant JavaScript-compatible canvas patterns,
  boundaries, case options and capture records. Find uses one-based positions
  and returns Blank when absent; IsBlankOrError catches deferred synchronous or
  awaited failures. The complete Milestones timestamp and Inspection Manager
  URL formulas have executed regressions. Full locale/format coverage and the
  newer Unicode Power Fx regex dialect remain unverified; unsupported Match
  enums are rejected explicitly.
- **Timers** — Duration, Start, AutoStart, AutoPause, Repeat, Reset,
  OnTimerStart and OnTimerEnd are wired to browser scheduling, with elapsed
  Value and SetFocus support. Browser timer precision is approximate; timers
  inside gallery templates are still unsupported. Untranslatable startup,
  screen and control actions surface explicit runtime errors.
- **Launch context** — `Param("name")` reads case-sensitive request parameters
  as text (missing values are Blank); the server safely embeds them without
  interpreting markup. `Language()` uses the browser locale. Query parameters
  are untrusted data, never user identity or authorization.
- **Unsupported capture inputs** — camera, signature/PenInput, barcode,
  microphone, attachments, and AddMediaButton render a visible blocker and are
  called out in the report until browser/Drive adapters exist.

What is *not* reproduced pixel-perfect: app themes/typography (a clean system
stylesheet is used), responsive reflow behavior, full multi-series/chart-style
semantics, active or oversized packaged media, and exotic container nesting
(these are the first things to check in QA).

## Review seams (how the LLM helps without touching code)

When the LLM is configured (`.env` or env vars) and review is enabled, two
review-only passes run after synthesis — they can **never modify generated
code**:

1. **Behavioral-equivalence review** — for every transpiled *behavior*
   formula, the model receives the (original formula, generated JS) pair and
   judges whether behavior is preserved (blank handling, number coercion,
   Patch merge semantics, Set vs UpdateContext scope, stale bindings...).
   Findings land in the report's *Behavioral-equivalence review* table sorted
   by risk, each with a concrete verification suggestion.
2. **QA scenario authoring** — the model reads the app's screens, controls,
   and formulas and writes 6–12 manual test scenarios (referencing actual
   control names) for the report's *Manual QA scenarios* section: run the same
   steps in the original app and the converted app and compare.

Use `--no-review` to skip both.

## LLM fallback (optional)

Unmapped formulas can be translated by any OpenAI-compatible chat API.
Configure via environment variables **or a `.env` file** in the repo root
(see `.env.example`; `.env` is gitignored and never committed; real
environment variables take precedence):

```bash
cp .env.example .env
# then edit .env:
#   PFX2GAS_LLM_BASE_URL=https://openrouter.ai/api/v1
#   PFX2GAS_LLM_API_KEY=sk-or-...
#   PFX2GAS_LLM_MODEL=openai/gpt-5.6-luna

./pfx2gas convert YourApp.msapp
```

Guarantees: the model receives the function-coverage table (single source of
truth with the transpiler) plus the generated app's real globals (`state`,
data-layer `api*` calls, `val()`, navigation, `toast`), returns one JSON object
per formula, and its JS is accepted only if it passes `node --check` (value
formulas must be single expressions; behavior formulas may be statements).
The response schema is checked without coercion and confidence must be finite
and between zero and one. A pinned JavaScript parser also verifies the
single-expression/event-handler boundary, rejects explicit mutations, behavior
helpers and known mutating methods in value formulas, and checks FX/FXRuntime
helper names. Scope metadata includes the formula's defining screen and its
declared locals; App and screen properties participate in fallback as well as
control properties. It rejects dynamic evaluation,
imports and selected direct-network/prototype operations without executing the
proposal. These static checks do not prove behavioral equivalence or constitute
a general JavaScript security sandbox; fallback formulas remain partial and
require runtime QA. Model, formula hash, gate version and rejection reasons are
retained in the call log.
Gate v6 rejects behavior-only Concurrent, keyed-write and relationship-write helper references in value proposals.

It may refuse when translation is genuinely impossible — the formula then
stays a documented stub. All calls are logged to `.runs/llm-calls.jsonl`
with confidence and notes; LLM-touched formulas appear in the report as
*partial* with their confidence so you know what to review first.

An opt-in live smoke test makes one provider request, with a 30-second timeout
and no retries, then boots the generated candidate app for winter/summer dates
in four timezones:

```bash
./pfx2gas test '/app/.venv/bin/python scripts/check_llm_live.py'
```

The September 9 OpenRouter check connected successfully, but the proposal
reversed TimeZoneOffset's sign at 0.98 model confidence. It passed the static
gate and failed three timezone journeys. The failure is retained in
`.artifacts/llm-live/`; offline regressions reproduce the semantic failure
without credentials or provider calls. A successful API request is not a
successful conversion, and ordinary tests never invoke the provider.

## Supported Power Fx surface (v1)

The deterministic function map includes:

- **Logic** `If`, `Switch`, `IfError`, `IsBlank`, `IsBlankOrError`, `IsEmpty`, `Coalesce`, `With`
- **Tables** `Filter`, `ForAll`, `LookUp`, `CountRows`, `CountIf`, `Concat`,
  `First`, `Last`, `Sort`, `SortByColumns`, `Distinct`, `Sum`, `Average`,
  `AddColumns`, `Sequence`, `Split`
- **Text** `Concatenate`, `Upper`, `Lower`, `Trim`, `Left`, `Right`, `Mid`,
  `Len`, `Find`, `Substitute`, `Replace`, `Text` (number/date formats),
  `IsMatch`, `Match`, `MatchAll`, `Proper`, `Char`, `GUID`, `EncodeUrl`, `PlainText`
- **Math** `Abs`, `Int`, `Round`/`RoundUp`/`RoundDown`, `Mod`, `Sqrt`, `Power`,
  `Min`, `Max`, `Value`, `Rand`
- **Dates** `Today`, `Now`, `Year`, `Month`, `Day`, `Hour`, `Minute`,
  `Weekday`, `DateAdd`, `DateDiff`, `Date`, `Time`, `TimeValue`
- **Colors** `RGBA`, `ColorFade`; **enums** (`Color.X`, `Font.X`,
  `Font.'Open Sans'`, …) emitted as literals
- **Behavior** `Set`, `UpdateContext`, `Navigate`, `Back`, `Notify`,
  `Patch`, `Remove`, `RemoveIf`, `Collect`, `ClearCollect`, `Refresh`,
  `Reset`, `Select` (as data-layer/control calls), `Launch`
  (opens a new tab)

`Choices('Source'.Field)` uses retained native choice metadata when available,
with the generated `__Choices` tab as a fallback;
anything else not in the map (for example custom `Environment.*` functions or
`ShowHostInfo`) becomes documented unsupported
operations via the coverage ledger — never silently wrong. Adding functions is one entry in
`src/pfx2gas/fx/function_map.py` plus a JS helper in `static/fx-stdlib.js`.

**Controls:** Label, Button, TextInput, TextArea, Dropdown/ComboBox/ListBox, CheckBox,
DatePicker, FluentDatePicker, Gallery (row template, per-item handlers), Image, Icon, HtmlText,
Form, GroupContainer/auto-layout containers (flexbox: direction, align,
justify, gap, wrap, FillPortions, min sizes), Rectangle, Header, Timer, Slider,
Chart/Legend, InfoButton, Form/DataCard, DataTable (generic), Badge;
legacy binary-`.msapp` format via adapter.

## Out of scope (flagged, not silently dropped)

- Model-driven apps and apps whose source is only the retired `*.fx.yaml`
  format (re-save the app in Studio to upgrade it)
- Power Automate flows, Dataverse-specific features, custom components with
  complex property sets
- Delegation semantics: data is read whole-tab (client-side filtering);
  keep Sheets under ~5,000 rows or extend `Code.gs` with server-side filters
- Active/oversized media, audio/video resources, and Drive-backed attachments

## Development

```bash
./pfx2gas build  # required after src/ or static/ changes
./pfx2gas test   # Python + JS + runtime consistency
./pfx2gas soak   # convert, validate, boot, exercise journeys, write scorecards
```

The soak run writes `.artifacts/benchmark/benchmark-scorecard.json` and
`.artifacts/benchmark/benchmark-scorecard.md`. It reports three independent
quality tiers per app:

- **Bootable** requires a valid generated project, the exact start screen, and
  zero startup runtime errors.
- **Usable** requires complete passing evidence for every declared critical
  user journey; otherwise it remains `unassessed`.
- **High fidelity** requires complete deterministic visual comparisons within
  explicit tolerances; otherwise it remains `unassessed`.

The versioned app/archetype and journey catalog is in `benchmark/apps.json`.
CI publishes both scorecards as the `compatibility-benchmark` artifact. A
passing boot check is deliberately never promoted into a usability or visual
claim.

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
