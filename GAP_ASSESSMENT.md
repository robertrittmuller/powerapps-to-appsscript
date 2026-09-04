# pfx2gas — Gap Assessment & Roadmap (updated 2026-09-04)

Forward-looking view: what to work on next. Historical findings and the P0
fixes they produced are at the bottom. Everything here was re-verified against
the code and the real-app corpus (10 apps, 23,746 formulas) on this date.

## Where we stand (verified)

| Check | Result |
|---|---|
| Python suite (`./pfx2gas test`) | 104 passed |
| JS runtime suite (`./pfx2gas test`) | 47 passed, 0 fail |
| Formula translation on 10-app corpus | 23,724 / 23,746 translated (99.9%) |
| Runtime wiring on 10-app corpus | 15,267 / 23,746 emitted (64.3%); 276 approximated |
| Ignored/unsupported property formulas | 8,203 / 23,746 (34.5%; conservative emission ledger) |
| Real-app soak (`./pfx2gas soak`) | **10/10 convert + validate + generated-app boot cleanly**; exact start screen, zero reference errors |
| Emitter↔runtime consistency (`scripts/check_runtime_consistency.py`) | pass |
| Generated server code syntax | all `.gs` node --check clean (validated every soak app) |
| Data layer | external sources → typed, sample-seeded Sheet tabs; collections → client-side state |
| Deployed a converted app via clasp | **redeployed and inspected 2026-09-04** — HelpDesk @12 uses the current component/runtime/visual output and authenticated-user defaults (see §1) |
| CI | green — pytest + JS + consistency + soak + container job + wrapper smoke |

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
   placeholders. Until data-card collection, validation, create/update, and
   success/failure events exist, ledger `SubmitForm` as unsupported rather than
   a successful no-op. Acceptance: Reset restores the generated default and
   every unimplemented form action is visible in the report.
5. **✅ Secure deployment defaults.** Require an authenticated user by default,
   make anonymous/deployer execution explicit, whitelist generated data
   sources, validate API payloads, and remove unneeded scopes. Acceptance: a
   default conversion cannot expose deployer-owned Sheet mutation anonymously.

With these gates green, the next pass has started: every real generated app is
now booted by the soak gate, and legacy component definitions are expanded into
their actual child controls. Continue with interaction assertions over real
apps, visual/deployed comparison, a modern app with real external data,
data-layer scaling/correctness, control/chart/CSS parity, identity enrichment,
and finally full-app LLM review.

---

## Next up, in recommended order

### 1. ⏳ M4 — first deployment complete; second app still required

HelpDesk-2021.msapp → converted in the container → pushed to the existing Apps
Script project → deployed @12 on 2026-09-04 with component expansion, HtmlText
interiors, dynamic MENU navigation, and the current runtime. A live Chrome pass
verified HOME rendering and HOME → NEW navigation, including a record-valued
Category dropdown displaying `IT` rather than `[object Object]`. The manifest now
requires a signed-in user and executes as that user (`ANYONE` /
`USER_ACCESSING`) with only the Sheets scope. Runs at:
`https://script.google.com/macros/s/AKfycbwbyTp89b-J_KEQ9N9wAf0OdJ8faH3k5gwAj_K1ToUFjaDPf8X35VBEnFQvfu5f2OJH/exec`

The earlier @3 anonymous/deployer-owned deployment is retained only as
historical evidence and should not be used for current testing. The second
representative-app deployment remains the open part of M4.

Deploy-hardening bugs found and fixed along the way (all with regression
tests): `render_manifest` shipped invalid JSON (doubled braces) so clasp lost
the webapp config + oauth scopes; `Index.html` called an `include()` helper
that never existed in `Code.gs`; includes used bare names instead of the full
`.js.html` filenames. Also documented: `clasp run` needs a standard GCP
project (default clasp projects can't use it) — one-time `setup()` runs in the
editor instead.

Visual bugs found by inspecting the deployed app and fixed in the deterministic
renderer (all regression-gated): RGBA alpha was discarded, making transparent
fills solid black; content-box sizing inflated positioned controls; body padding
shifted the canvas; `LineHeight` was emitted as pixels; Power Apps font sizes
were emitted as CSS pixels rather than points; `BorderColor` was never written
and `BorderStyle.None` was not recognized; bare legacy alignment/weight enums
were ignored; `User().Image` was not bound to image `src`; Windows private-use
icon glyphs rendered as boxes on macOS; and record-valued dropdown choices
rendered as `[object Object]`. The current deployed HOME audit found 49 visible
controls, zero private-use icon glyphs, and only the intended search-input
border. Browser logs contained no generated-app warning/error.

### 2. ✅ CI workflow (done 2026-09-02, run #1 green)

`.github/workflows/ci.yml` runs on every push to main and every PR: Python
suite, JS runtime suite, emitter↔runtime consistency gate, then the real-app
soak against 5 modern-format samples fetched fresh from the public source repo
(`scripts/fetch_samples.py` — zip-integrity-checked, cached, retried). Legacy
apps stay covered by the committed synthetic fixtures.

Regression-class bugs (like the emitter↔runtime drift) now fail CI instead of
surfacing in a converted app.

### 3. ⏳ Component-template emulation (in progress)

The 37 first-party component instances in the corpus no longer render as empty
divs. The legacy adapter reads `ComponentsMetadata.json` and `Components/*.json`,
inlines each definition's child tree under its instance, namespaces child
controls, and binds component inputs plus `Self`/`Parent`/control references.
Static HtmlText markup now renders after executable markup is removed, so the
HelpDesk MENU, TILES1/TILES2, and BUSCADOR visuals have real interiors; Clean
UI's horizontal/vertical progress bars have reactive child geometry, fill, and
text. Menu screen-valued inputs and `App.ActiveScreen` now generate working
dynamic navigation instead of invalid dotted screen-name strings.

Remaining actions: turn the live HOME → NEW smoke into an automated real-sample
click assertion for every HelpDesk menu target and add numeric/style assertions
for Clean UI progress bars; compare rendered screens side-by-side with the
originals; then cover component output properties and modern pa.yaml component
definitions. Acceptance: interaction assertions and visual comparison pass for
HelpDesk navigation/tiles and Clean UI progress bars. One deployed smoke on the
regenerated output now passes.

### 4. Modern pa.yaml app with real external data (corpus gap)

All data-bearing corpus apps are legacy binary format. The Sheet-backed data
layer for modern Studio exports (the most common real-world case: pa.yaml +
SharePoint list) is exercised only by synthetic fixtures.

Next actions: export one of your own apps backed by a real SharePoint list /
Excel table into `samples/real/`; run the soak + deploy flow on it.
Acceptance: CRUD against the real list works through the Sheet layer; report
fields match the list columns.

### 5. User() enrichment (small, in progress)

`whoami()` now derives a display name from the email local part when Apps Script
exposes the active user's email, and a neutral avatar placeholder replaces the
broken image state. `pictureUrl` remains unavailable, and the current deployed
environment returned a blank active-user email, so its header name is still
empty.

Next actions: optionally use the Directory API on Workspace accounts and
document both domain-policy and consumer-account limitations. Acceptance:
header shows a sensible name for the deployed app when identity is available.

### 6. LLM review seams at scale (medium, needs configured `.env`)

Behavioral-equivalence review and QA-scenario authoring have run 16 times ever.
They're the project's answer to "the transpiler says converted, is it *right*?"
and have never been exercised on a full real app.

Next actions: full `pfx2gas convert samples/real/helpdesk.msapp` (no
`--no-llm`) with the OpenRouter config; triage the review findings; feed
confirmed issues back into the function map / emitter.
Acceptance: review table populated for a real app; every high-risk finding
either fixed or documented.

### 7. Parity tail (P2, opportunistic)

Known, documented, lower stakes — pick up as user demand appears:
- Ignored props: `LayoutMode` x81, form semantics (`DataField`/`Update`/
  `Required`/`DisplayName` x11 each), chart series styling (`barMaxValue`,
  `ItemColorSet`, `Explode`), `TemplateSize`, `WrapCount`, `Transition`.
- App theme/typography (clean system stylesheet instead), responsive reflow.
- Delegation: server-side filtering for tabs > ~5k rows.
- Power Automate flows: still out of scope, flagged only.

---

## Suggested sequence

| Step | Item | Effort | Depends on |
|---|---|---|---|
| 1 | Correctness gates 1–5 above | medium | — |
| 2 | ✅ Generated-app boot matrix + strict-fidelity CI fixture; expand interaction coverage | medium | 1 |
| 3 | ⏳ Legacy component expansion landed; finish interaction + visual/deploy evidence | large | 1–2 |
| 4 | Real modern data app into soak + second deployment (#4/M4) | medium + your export | 1–2, you |
| 5 | Data scaling, control/chart/CSS parity | ongoing | 2 |
| 6 | User() enrichment, then LLM review at scale | small / medium | authenticated deployment, .env |

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
