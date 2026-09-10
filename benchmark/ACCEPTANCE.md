# Ten-app acceptance scope

The current user goal requires ten example apps to preserve **critical app
functionality**, retain a functional UI, and pass code and usability tests.
Exact visual reproduction and complete support for every Power Fx feature are
separate fidelity goals. A documented gap does not excuse a broken critical
workflow or an unusable control.

Use these ten pinned source exports as the acceptance set. Their source hashes
and licenses remain in the existing corpus manifests and `SOURCES.md`. Editable
Grid remains a regression input, but its missing Student Tracker schema and
uninitialized source filter make it unsuitable as an acceptance example without
a complete export. Do not invent its missing source behavior.

| Source app | Required critical workflow |
|---|---|
| Expandable Navigation | Expand/collapse menus, navigate to every declared destination and return; usable controls and profile state at supported viewport sizes |
| Modern Card Control | Render source card content and execute every visible card action |
| SVG App | Exercise each declared image state and verify usable selectors and decoded image output |
| Sentiment Analysis Feedback | Submit feedback and show its classification/result through a Google service adapter; preserve source-defined save and failure behavior |
| Microsoft Milestones | Create a project and milestone; create, assign, edit, filter and reopen a persisted work item |
| Microsoft Employee Ideas | Open a campaign, submit an idea, vote and verify both the idea and vote after reload |
| Microsoft Employee Ideas Manager | Create/edit a campaign with required fields, dates and status; retain persistence and role-dependent actions |
| Microsoft Inspection | Choose an area/checklist, enter and submit responses; reopen saved answers and recover from failed saves |
| Microsoft Inspection Manager | Create/edit areas, checklists and checklist steps consumed by Inspection |
| Microsoft Review Inspections | Filter results, verify chart totals, drill into saved responses and execute source follow-up actions |

For each app, retain its input hash, converter fingerprint, source-to-Google
service/data setup, generated project and code-validation results. Exercise the
unchanged source actions in the generated UI using the generated server. Record
asserted outcomes, reload/error behavior, console errors, screenshots and UI
geometry/accessibility evidence. An unsupported-connector placeholder cannot
pass a workflow whose critical purpose depends on that connector.

Native service response fixtures establish repeatable adapter behavior; label
them explicitly and report live Google authorization/deployment separately.
Synthetic fixtures remain regression tests, not additional source apps in this
ten-app set. A short startup check or a passing first action cannot stand in for
the declared workflow and UI tests.

The existing `Usable` grade is the critical-journey gate. `High fidelity` adds
original-app visual comparisons and is reported separately. Neither a lower
formula-gap count nor pixel parity substitutes for a functional UI. Current
per-app evidence and remaining failures are recorded in `GAP_ASSESSMENT.md` and
the generated scorecards; this scope document does not grant a passing grade.

Current complete browser evidence: **Expandable Navigation** passes 75 checks
covering its declared critical workflow and UI at 1440×900, 1000×700 and 520×700.
Its generated server uses explicit Google directory mappings/response fixtures;
source canvas minimum sizes, the no-photo avatar fallback and browser Exit
feedback are recorded in the result. Run `./pfx2gas browser
scripts/assess_public_workflows.py` to reproduce it. The identity-free soak
simulator remains a separate unmigrated baseline. The other nine target apps
still require complete critical-workflow and UI evidence.

Modern Card's source declares `HomeScreen` as `App.StartScreen`; it is not the
first screen in archive order. Its separate `assess_modern_card_workflow.py`
assessment retains startup/reload evidence and content failures. The export has
no `MyFiles` data contract or initialization, and its embedded source checker
flags the list and file fields as invalid names. A complete export is not
currently available to the user. The missing source contract and missing modern
Header/Card rendering keep the document-card workflow unassessed. Do not infer
a schema, add sample documents or introduce a route to the unreachable standalone
card to award acceptance.

Milestones has expanded partial evidence: `./pfx2gas browser
scripts/assess_milestones_workflow.py --filters` passes 260 checks through project,
milestone and settings creation, assigned work-item create/edit/reload, search,
combined filters, filtered reopening and targeted deletion. Keyboard filter
controls and dialog containment are checked at three viewport sizes. The result
retains its source and assessment-script hashes, source-default provenance,
Google migration fixtures and screenshots. Complete app usability remains
unassessed; searchable native selectors, broader task variants and source column
clipping are still open. This does not increase the complete-app count.

SVG has a separate partial assessment: `./pfx2gas browser
scripts/assess_svg_workflow.py` checks its reachable text/slider/rating/timer SVG
states, decoded and painted output, source image fitting/transparency, reload
and keyboard/geometry at two landscape sizes. Its result retains the source
hash, converter fingerprint and property provenance. Literal SVG text repair is
ledgered. Unnamed source inputs and unreachable exported screens still require
assessment before a complete usability claim; it is not a second accepted app.
