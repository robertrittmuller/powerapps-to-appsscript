# Acceptance sample provenance

## Microsoft business templates

Selected from [Microsoft's Teams Power Apps templates](https://github.com/microsoft/teams-powerapps-app-templates):

| Template | Retained canvas exports | Acceptance focus |
|---|---|---|
| Milestones | Milestones | Projects, tasks, assignment, status, relational records and editable galleries |
| Employee Ideas | Ideas; Manage ideas | Campaigns, submissions, voting, validation, media and manager/user workflows |
| Inspection | Inspection; Manage inspections; Review inspections | Checklists, conditional responses, area management, result filtering and dashboards |

These are three business templates containing six apps, not six unrelated
examples. Keep their Dataverse and Teams dependencies visible: converting a
canvas export alone does not migrate its solution tables, identities, security,
calculated fields, flows or Planner actions.

Pinned package: [release 44](https://github.com/microsoft/teams-powerapps-app-templates/releases/tag/44),
`AppPackages.zip`; SHA-256
`40cea1a23ee4e72e06886951514bc71071b933d5066038aa99c873679f2540c7`.
The checksum is recorded from the retrieved artifact, not a Microsoft signature.
`scripts/fetch_microsoft_samples.py` verifies it on downloads and cache hits,
then reads explicitly named CAB/ZIP members. It preserves the original `.msapp`
bytes. Full source paths and per-export hashes are retained in
`.artifacts/microsoft/provenance.json`; exports live in gitignored
`samples/microsoft/`. Nothing is installed in a Microsoft tenant.

Upstream code is [MIT licensed, copyright Microsoft Corporation](https://github.com/microsoft/teams-powerapps-app-templates/blob/main/LICENSE).
Microsoft's README separately documents trademark restrictions. We link to and
fetch the upstream packages; no sample binary is redistributed in this repo.
Keep the upstream license with any separately redistributed sample package.
Two complete source formulas are retained in
`tests/fixtures/microsoft-formulas.json`, with input/formula hashes and original
screen/control names, under `tests/fixtures/MICROSOFT-LICENSE.txt`. The generated
`fixtureSourceFormulas.msapp` wraps those unchanged formulas in test controls and
sample collections. It is a regression fixture, not a real acceptance app.

Reproduce with Docker:

```bash
./pfx2gas build
./pfx2gas build browser
./pfx2gas browser scripts/assess_microsoft_samples.py
```

The September 9 assessment exits **1**: all six generate syntactically valid
projects; three fail startup. Employee Ideas, Inspection and Milestones pass
the short startup check and leave loading in Chromium. Their first-action
probes fail on clipped controls or delayed connector calls; these failures are
attached to the combined scorecard with matching source/converter hashes.
All six remain below usability acceptance. See `GAP_ASSESSMENT.md` for the fix
sequence. This is a separate acceptance baseline, not a hidden allowance in
the existing passing regression corpus.

## Existing modern regression corpus

Five exports from
[sunilshetty07/Microsoft-PowerApps-Canvas](https://github.com/sunilshetty07/Microsoft-PowerApps-Canvas/tree/3e60c764a51d63061064e2902e247e6daeaa8468)
are pinned to commit `3e60c764a51d63061064e2902e247e6daeaa8468` with per-file SHA-256
values in `scripts/fetch_samples.py`. A clean-container download was verified.
Cached mismatches fail without overwriting local exports. These files are
downloaded for testing, not redistributed; their redistribution license has not
been established by this assessment. Editable Grid lacks its Student Tracker
metadata and initialization, so it is not the sole persistent CRUD target.

`benchmark/apps.json.requiredApps` names those five reproducible CI inputs.
Five additional local exports (including HelpDesk) remain optional and their
absence stays visible in scorecards. They are not yet a reproducible CI corpus.

## Evidence boundaries

- Soak scorecards record input hashes and the exact converter source fingerprint.
- Chromium artifacts exercise generated client code plus generated `Code.gs`
  against a persistent in-memory Sheets test double. Reload is a real browser
  reload, but neither Google authorization nor real Sheets persistence is proven.
- Converted-output screenshots are regression evidence, not original-app visual
  baselines. Original captures at matching data, state and viewport are still needed.
