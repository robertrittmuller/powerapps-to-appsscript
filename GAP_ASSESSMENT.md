# pfx2gas — Gap Assessment & Roadmap (updated 2026-09-02, after fix batch)

Forward-looking view: what to work on next. Historical findings and the P0
fixes they produced are at the bottom. Everything here was re-verified against
the code and the real-app corpus (10 apps, ~22k formulas) on this date.

## Where we stand (verified)

| Check | Result |
|---|---|
| Python suite (`uv run pytest -q`) | 80 passed |
| JS runtime suite (`node --test tests/js/*.js`) | 35 passed, 0 fail |
| Formula coverage on 10-app corpus | 21,905 / 21,940 rule-transpiled (99.8%) |
| Ignored properties | 538 / 21,955 (2.5%) |
| Real-app soak (`scripts/soak_check.py`) | **10/10 convert + validate** under the strict validator |
| Emitter↔runtime consistency (`scripts/check_runtime_consistency.py`) | pass |
| Generated server code syntax | all `.gs` node --check clean (validated every soak app) |
| Data layer | external sources → typed, sample-seeded Sheet tabs; collections → client-side state |
| Deployed a converted app via clasp | **never done** (M4 open, clasp not installed) |
| CI | **green** — [run #1](https://github.com/robertrittmuller/powerapps-to-appsscript/actions/runs/33702273235) (2026-09-02): all steps pass on ubuntu-latest |

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

## Next up, in recommended order

### 1. M4 — deploy a converted app end-to-end (highest value, needs you)

Everything upstream of deployment is now verified; deployment is the single
biggest untested boundary. "Validator PASS" has never been shown to equal
"works in a browser". clasp runs **inside the project container** (no local
install needed); its credentials persist in `.clasp-home/`.

Next actions (you + me):
1. `docker compose run --rm clasp login --no-localhost` — open the printed
   Google URL in your browser, authorize, paste the code back into the container.
2. I convert helpdesk into `output/HelpDesk` (in-container), then
   `clasp create` → `push --force` in the container.
3. You run `setup()` once in the Apps Script editor (creates the workbook:
   6 tabs + 44 seeded rows), I `clasp deploy` and we verify the web app URL:
   navigation, galleries, the 56 text inputs, collection-backed screens.

Acceptance: helpdesk usable in a browser from the deployed URL; gaps found
during the smoke test filed as the next fix list. This unlocks the v0.1.0 tag.

### 2. ✅ CI workflow (done 2026-09-02, run #1 green)

`.github/workflows/ci.yml` runs on every push to main and every PR: Python
suite, JS runtime suite, emitter↔runtime consistency gate, then the real-app
soak against 5 modern-format samples fetched fresh from the public source repo
(`scripts/fetch_samples.py` — zip-integrity-checked, cached, retried). Legacy
apps stay covered by the committed synthetic fixtures.

Regression-class bugs (like the emitter↔runtime drift) now fail CI instead of
surfacing in a converted app.

### 3. Component-template emulation (large, biggest remaining fidelity gap)

37 first-party component instances render as empty divs: MENU, TILES1/TILES2,
BUSCADOR (helpdesk), ProgressBar horiz/vert (clean-ui). Their custom properties
transpile fine but mean nothing without the component's inner control tree —
helpdesk's nav and tile dashboards are blank.

Next actions: read `ComponentsMetadata.json` + `References\Templates.json`
(each template is a small control tree with custom properties, already in the
archive); synthesize component instances by inlining the template tree with
instance properties bound. Start with ProgressBar (simplest visual), then MENU.
Acceptance: helpdesk nav renders and navigates; progress bars render in clean-ui.

### 4. Modern pa.yaml app with real external data (corpus gap)

All data-bearing corpus apps are legacy binary format. The Sheet-backed data
layer for modern Studio exports (the most common real-world case: pa.yaml +
SharePoint list) is exercised only by synthetic fixtures.

Next actions: export one of your own apps backed by a real SharePoint list /
Excel table into `samples/real/`; run the soak + deploy flow on it.
Acceptance: CRUD against the real list works through the Sheet layer; report
fields match the list columns.

### 5. User() enrichment (small)

`whoami()` returns email only; `fullName`/`pictureUrl` are always blank, so
helpdesk's header user name/avatar are empty.

Next actions: derive display name from the email local part at minimum;
optionally Directory API on Workspace accounts (document the consumer-account
limitation). Acceptance: header shows a sensible name for the deployed app.

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
| 1 | ~~CI workflow~~ | ✅ done | — |
| 2 | clasp install + login (you), then deploy smoke test (#1) | small–medium | you (5 min) |
| 3 | v0.1.0 tag | minutes | 2 green |
| 4 | Component-template emulation (#3) | large | — |
| 5 | Real modern data app into soak (#4) | small + your export | you |
| 6 | User() enrichment (#5), LLM review at scale (#6) | small / medium | .env present |
| 7 | Parity tail (#7) | ongoing | demand |

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
