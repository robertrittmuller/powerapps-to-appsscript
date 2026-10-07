# Fidelity and release acceptance

The converter distinguishes valid generated files, verified startup, complete
business workflows, source equivalence and live Google behavior. Passing an
earlier stage never promotes the later stages. All commands below use Docker.

## The seven enhancements

1. **Evidence-backed conversion.** Each generated project contains the full
   formula/control inventory, a capability census and a schema-2 ledger.
   Validation recomputes the census and checks the source contract. Conversion
   boots generated client/server code and writes fingerprinted `verification.json`.
   `--strict-fidelity` requires startup and zero gaps; `--require-stage bootable`
   requires startup while allowing explicitly reported fidelity gaps. Dynamic
   StartScreen formulas need authored launch expectations and stay unassessed
   in the generic verifier. Simulation uses service doubles, not Google.
2. **Semantic conformance.** `tests/fixtures/powerfx-conformance.json` records
   independently documented expectations. Tests execute emitted formulas in
   UTC, New York, Berlin and Kolkata and check generated label values. They
   cover the review's eight failures plus boundary and blank-date cases. This is a
   growing reference corpus, not exhaustive Power Fx equivalence.
3. **Supported signatures.** Arity checks prevent silently discarded optional
   arguments. Scalar-only mappings reject table/record overloads; dynamic
   objects fail visibly; table-projector mappings also reject scalar/record
   inputs. Special data mappings reject extra record arguments they cannot
   preserve. Unsupported overloads become formula gaps. Value uses
   locale decimal/group separators, exponent/percent syntax and common locale
   currencies; non-Latin digits and all regional currency formats are not yet
   covered by reference tests. JavaScript numbers remain binary floating point.
4. **Data constraints.** Dataverse SystemRequired fields, create/update flags,
   calculated flags and exported literal defaults reach generated server code.
   Read-only writes are ignored; keys cannot be changed; required failures are
   atomic. ApplicationRequired remains an application rule. Calculated/rollup
   evaluation, audit defaults, Dataverse privileges, live lookup cascades and
   non-UserLocal date semantics need adapters and remain preflight gaps.
5. **One release manifest.** `acceptance.json` names ten required apps, source
   exports, solution metadata, setup prerequisites, journeys and runners. An
   absent runner, unassessed full usability, missing steps or stale fingerprint
   fails release acceptance. Five apps currently have no complete executable
   journey runner; existing partial runners also cannot certify their apps.
6. **Preflight and matched captures.** Preflight exposes missing exports,
   converter gaps and migrations. `compare_workflow.py` runs an authored plan
   against the original and converted apps under matched conditions. It stores
   assertions, screenshots and separate actor contexts. Google authorization,
   persistence, recovery and concurrent-user assertions require a live deployment.
7. **Risk-ranked review.** Optional LLM review considers all emitted startup,
   screen and control/value formulas, prioritizes mutations and risky semantics,
   and reports reviewed/unreviewed contexts. Its default budget is 40 formulas.
   Invalid/missing/duplicate verdicts cannot inflate coverage. Proposed QA
   scenarios must become source-verified deterministic tests before acceptance.

## Reproduce the checks

```bash
./pfx2gas build
./pfx2gas test
./pfx2gas soak
./pfx2gas build browser
./pfx2gas browser
./pfx2gas browser scripts/check_comparison_capture.py
./pfx2gas preflight samples/real/expandable-nav.msapp -o .artifacts/preflight.json
./pfx2gas convert tests/fixtures/fixtureB.msapp -o output/FixtureB --no-llm --require-stage bootable
./pfx2gas validate output/FixtureB --require-stage bootable
```

The comparison self-test uses local fixture pages and verifies isolation,
nested frames, persistence, screenshots and assertion failure handling. It is
not evidence for an original Power App or a live Google deployment.

```bash
# Fetch sources, execute all declared assessments, then require complete workflows.
./pfx2gas browser scripts/acceptance_check.py --run

# Full release requirement, including previously captured external evidence.
./pfx2gas browser scripts/acceptance_check.py --run --require-source-comparison --require-live-google
```

The command writes `.artifacts/acceptance/result.json` and exits nonzero on any
required gap. Source fetch and baseline assessments are diagnostic; per-app
workflow results and original/live comparisons determine acceptance. A failed
runner cannot reuse its previous result. Source export, converter source and
assessment-script hashes bind workflow evidence to the assessed revision.

The `Release acceptance` Actions workflow runs on version tags or manual
dispatch. It optionally downloads `source-live-evidence` from a supplied Actions
run ID; that artifact must contain `<app-id>/sourceComparison.json` and
`<app-id>/liveGoogle.json` for the exact source/converter revision. The workflow
fails when evidence is missing. This is a release check, not an automatic
publishing action; release procedures must require its success.

## Capture original and deployed behavior

Start from `capture-plan.example.json` and save the completed plan under
gitignored `.artifacts/`. Supply actual URLs, exported source path, reviewed
data snapshot hash, application parameters, roles, expectations and selectors.
For apps with solution metadata, also set `solutionExport` to that ZIP/XML path;
its fingerprint is required by release acceptance.
Restore equivalent initial records separately before each side runs. The
runner records the declared snapshot; it does not import data or prove two
tenants contain identical records. Use disposable test data for mutation plans.

Each actor can specify separate Playwright `storage_state` files under
`sessions.source` and `sessions.target`. These files contain authentication
material and must stay out of commits and uploaded evidence. The tool does not
log in for you. Apps Script selectors can declare nested iframe selectors.

```bash
./pfx2gas browser scripts/compare_workflow.py --plan .artifacts/my-capture-plan.json --output .artifacts/acceptance/APP-ID --allow-writes --live-google
```

`--allow-writes` is required for authored click/fill/select/press steps because
they may change both apps. Supported actions also include navigate, reload,
screenshot and observe. Observations read text, value, count, attributes or
geometry. Each must name a required journey and an expected value; geometry
can use an explicit nonnegative tolerance. Text/values/counts use retrying
Playwright assertions. Add screenshot steps at meaningful intermediate states.
Review images for visual differences not captured by declared DOM assertions;
the tool does not perform perceptual screenshot matching.

Source and target must agree on every observed value and the declared context.
Live evidence additionally requires a Google `/exec` URL, an operator-supplied
deployment version, no mocks, passed live assertions, and at least two roles
when permission or concurrent-user checks apply. Apps in the release manifest
declare applicable checks; data-backed apps default to `authorization`,
`persistence`, `failureRecovery` and `concurrentEdits`. Author real actions and
assertions that exercise each behavior; naming an assertion does not prove its
business adequacy. Deployment version and test-data provenance require review.
The evidence format is auditable, not cryptographically attested.

Unavailable original sessions, incomplete source exports, missing migrations
or missing Google deployments leave these stages unassessed and block release
acceptance. They do not justify marking an app high fidelity.

The stricter server checks also expose incomplete synthetic user migration
records in the existing Employee Ideas and Milestones workflow runners. For
example, `Users.user__license__type` is SystemRequired and has no exported
default. These runs now fail during setup. Complete imported source records
and an explicit migration policy are needed; inventing defaults or disabling
validation would hide this gap. Narrow generated fixtures still exercise
required fields, read-only writes, defaults and failed-save atomicity.
