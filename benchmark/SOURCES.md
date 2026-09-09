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
The fetcher also retains the three companion `*.solution.zip` files and their
hashes. Their `customizations.xml` supplies saved-view FetchXML omitted from
the canvas exports. Conversion and browser evidence record the solution hash;
evidence from different solution metadata cannot be merged.

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

The solution-aware September 9 assessment exits **1**: all six generate valid
code and pass generated-server setup/read checks, but only Employee Ideas passes
the short startup check. Previously silent view filters now expose missing
migrated identities and unsupported relative-date queries. All three default
first-action probes fail. The separate populated Employee Ideas probe supplies
one authored user, four campaigns and three questions through generated Code.gs:
29 checks pass for active filtering/order/search, campaign selection, mobile
fields and labels, required-title validation, single/multiline custom responses,
submission, persistence, reload, reopening and per-campaign idea counts. The unrelated campaign question
is excluded. The source warning path handles the unsupported Teams post.
The optional `--voting` probe persists a count of one and executes Relate/Unrelate,
but fails its membership assertion. The source Concurrent contains an
unconditional Unrelate branch that removes the voting-user link in this run;
the ordering risk is ledgered and retained for source review.
Ratings, attachments, manager workflows and complete usability remain
unassessed. Source app and solution bytes stay unchanged.
The combined scorecard retains failures with matching source/converter/solution
hashes. Authored record contents and a data hash accompany the populated probe.
All six remain below complete usability acceptance. See `GAP_ASSESSMENT.md` for the fix
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
