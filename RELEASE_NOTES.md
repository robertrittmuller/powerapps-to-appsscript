# v0.2.0-rc.1 — tested development checkpoint

Date: September 10, 2026. This release candidate freezes the implementation at
`ce727cc`. Release preparation changes version metadata and documentation only.
Python represents the version as `0.2.0rc1`; the Git tag and npm metadata use
`0.2.0-rc.1`.

The converter has a reproducible, tested baseline for further development.
**The production acceptance goal is not complete: 1 of the 10 pinned apps has
complete declared workflow/UI evidence.** Required corpus failures remain failures;
the full CI acceptance gate is not green. This checkpoint does not certify
arbitrary Power Apps exports or live Google deployments.

## Included behavior

- Modern and legacy canvas exports feed one deterministic pipeline with a
  per-formula fidelity ledger, generated Apps Script server and Sheets data layer.
- Microsoft Planner operations map to a shared Sheets task board; user-directory
  operations use Google People; selected Microsoft Teams operations use Google
  Chat. Each adapter requires explicit source-ID/user/resource migration.
- Dataverse records preserve exported keys, relationships, choices and supported
  ownership/state/status defaults. Unimplemented semantics remain explicit gaps.
- Authored startup screens, reactive named formulas, components, forms, selectors,
  gallery row scope, source layouts, icons and SVG controls have runtime coverage.
- Modern Header/Card controls render source text/images with keyboard actions and
  disabled states. Wrapped galleries use cell widths and reactive spacing, with
  a ledgered one-column minimum while width-dependent startup values settle.
- Optional LLM fallback stays within the existing single-formula validation
  boundary. Release verification runs without LLM assistance.

## Verification at the implementation checkpoint

| Check | Result |
|---|---|
| Python | 614 passed, 3 skipped |
| JavaScript | 119 passed |
| Emitter/runtime consistency | Pass; 25 emitted bare calls resolve, helper signatures checked |
| Chromium regression fixtures | 43 passed; three deliberate failure probes correctly retain failed verdicts |
| Expandable Navigation | 75 checks passed; complete declared workflow/UI evidence |
| Milestones | 260 checks passed; broader app usability unassessed |
| Employee Ideas with Google Chat fixtures | 31 checks passed; broader app usability unassessed |
| SVG reachable workflow | 41 checks passed; broader app usability unassessed |
| Modern Card | 7 startup/header/reload checks passed; missing document contract fails |
| Public corpus | 5/5 code/server validation; 3/5 unconfigured startup |
| Microsoft business corpus | 6/6 code/server validation; 2/6 unconfigured startup |

The complete implementation-source fingerprint is
`f691416266f1339bc45e42bb7784a2cebec91a748805dce3c8bc91dfbd4c1109`.
The release version changes `src/pfx2gas/__init__.py`, so the release fingerprint
differs; the earlier results are explicitly attributed to `ce727cc`, not relabeled.
Packaged conversion and generated-app actions also passed for modern and legacy
Header/Card fixtures and the pinned Modern Card source.

Google API responses and Sheets storage in automated journeys are explicit test
fixtures. These checks do not establish real OAuth permissions, directory/photo
visibility, Google Chat rendering or production data persistence.

## Release package verification

The rebuilt release package passed the full 614-Python/119-JavaScript suite,
emitter/runtime consistency and all 43 Chromium fixtures. The three deliberate
failure probes still report failures. Installed Python/npm versions and lockfile
metadata agree. Packaged modern/legacy conversions produce byte-identical
client/server code to the implementation checkpoint and pass generated-app
selection and disabled-action checks. Chromium separately verifies persisted
row updates.

Release source fingerprint:
`c08d64e9aa12085eadd86050eddbcd6a8b86718271fb5000e228c3102acec053`.
Normalizing only the version string reproduces the earlier implementation
fingerprint, confirming that the real-app results above remain applicable to the
same converter behavior. Their original evidence hashes are preserved.

## Known release blockers

- Nine target apps still lack complete critical-workflow/UI evidence. See
  [the acceptance matrix](benchmark/ACCEPTANCE.md) and
  [the gap assessment](GAP_ASSESSMENT.md).
- Modern Card references an absent `MyFiles` list and fields; its embedded source
  checker reports invalid names. A complete export is unavailable. No schema,
  documents or extra navigation are invented to make this app pass.
- Editable Grid references the unexported Student Tracker choice source.
  The unconfigured Navigation and Microsoft baselines also retain missing
  migration, source-loading and first-action failures.
- Full native Fluent presentation, searchable selector popups, attachments,
  remaining connectors and broader layout/component semantics are incomplete.
- Live deployment validation and original-app visual comparisons remain open.
  Existing Apps Script quota, whole-tab read and authorization limitations apply.

## Reproduce using Docker

```bash
./pfx2gas build
./pfx2gas test
./pfx2gas build browser
./pfx2gas browser
./pfx2gas browser scripts/assess_public_workflows.py
./pfx2gas browser scripts/assess_milestones_workflow.py --filters
./pfx2gas browser scripts/assess_employee_workflow.py --chat
./pfx2gas browser scripts/assess_svg_workflow.py
```

Run the following independently; they intentionally remain nonzero while the
documented acceptance failures exist:

```bash
./pfx2gas soak
./pfx2gas browser scripts/assess_microsoft_samples.py
./pfx2gas browser scripts/assess_modern_card_workflow.py
```

Review the generated `.artifacts/benchmark`, `.artifacts/microsoft` and
`.artifacts/browser` reports, including source hashes, console errors and failed
steps. Each converted project's `conversion-report.md` remains the contract for
manual work. Configure and verify service migrations before using real data.

The Git tag identifies this checkpoint. To return to it, use a separate checkout
at `v0.2.0-rc.1` and rebuild the containers. Keep app exports, Google data and
credentials outside any source rollback; a code checkout does not undo data writes.
