"""Stage 5: validate a synthesized project (syntax, structure, stub census)."""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

REQUIRED_FILES = ["Code.gs", "DataInit.gs", "appsscript.json", "Index.html",
                  "Screens.html", "App.js.html", "conversion-ledger.json", "data-contract.json",
                  "gas-runtime.js.html", "fx-stdlib.js.html", "fx-charts.js.html",
                  "source-inventory.json", "preflight.json"]


def js_syntax_ok(js: str) -> tuple[bool, str]:
    """node --check a JS snippet; returns (ok, stderr)."""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js)
        path = f.name
    try:
        result = subprocess.run(["node", "--check", path], capture_output=True, text=True, timeout=30)
        return result.returncode == 0, result.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    finally:
        Path(path).unlink(missing_ok=True)


def validate_project(out_dir: str | Path) -> dict:
    out = Path(out_dir)
    problems: list[str] = []
    missing = [n for n in REQUIRED_FILES if not (out / n).exists()]
    if missing:
        problems.append(f"missing files: {', '.join(missing)}")

    stub_count = 0
    for js_html in out.glob("*.js.html"):
        body = js_html.read_text().replace("<script>\n", "").replace("\n</script>", "")
        ok, err = js_syntax_ok(body)
        if not ok:
            problems.append(f"{js_html.name} fails node --check: {err.splitlines()[0] if err else 'unknown'}")
        stub_count += body.count("FX.unsupported(")

    # Server-side .gs files are plain JS (V8); syntax-check them like the client.
    for gs_file in sorted(out.glob("*.gs")):
        ok, err = js_syntax_ok(gs_file.read_text())
        if not ok:
            problems.append(f"{gs_file.name} fails node --check: {err.splitlines()[0] if err else 'unknown'}")

    index = (out / "Index.html").read_text() if (out / "Index.html").exists() else ""
    if index and "data-screen" not in index and "include('Screens')" not in index:
        problems.append("Index.html does not reference Screens")

    gs = (out / "Code.gs").read_text() if (out / "Code.gs").exists() else ""
    if gs and not re.search(r"\bfunction\s+doGet\s*\([^)]*\)\s*\{", gs):
        problems.append("Code.gs has no doGet()")
    if gs and "function include(name)" not in gs:
        problems.append("Code.gs has no include() helper (Index.html templating needs it)")

    # The manifest is JSON and must actually parse — the Apps Script web-app
    # config and oauth scopes live here, and clasp silently tolerates junk.
    import json

    manifest_path = out / "appsscript.json"
    if manifest_path.exists():
        try:
            json.loads(manifest_path.read_text())
        except json.JSONDecodeError as exc:
            problems.append(f"appsscript.json is not valid JSON: {exc}")

    # Guard the whole class of source-schema / stored-column drift. Valid JS
    # cannot prove that aliases, primary keys or non-table kinds survived.
    contract_path = out / "data-contract.json"
    expected_ownership = None
    expected_states = None
    if contract_path.exists():
        try:
            from .ir import AppIR, DataSource
            from .synth.server import data_contracts
            contract = json.loads(contract_path.read_text())
            if contract.get("version") != 1 or not isinstance(contract.get("sources"), list):
                raise ValueError("unsupported contract shape")
            sources = [DataSource.model_validate(ds) for ds in contract["sources"]]
            expected = data_contracts(AppIR(name="validation", data_sources=sources))
            expected_ownership = {name:spec['ownership'] for name,spec in expected.items() if 'ownership' in spec}
            if contract.get('dataverseOwnership', {}) != expected_ownership:
                raise ValueError('ownership adapter differs from exported source contract')
            expected_states = {name:spec['stateModel'] for name,spec in expected.items() if 'stateModel' in spec}
            if contract.get('dataverseStateModels', {}) != expected_states:
                raise ValueError('state adapter differs from exported source contract')
            declaration = re.search(r"var DATA_CONTRACTS = (.*?);\n", gs)
            if not declaration or json.loads(declaration.group(1)) != expected:
                raise ValueError("Code.gs contract differs from exported source contract")
            init = (out / "DataInit.gs").read_text()
            declaration = re.search(r"var specs = (.*?);\n", init)
            specs = json.loads(declaration.group(1)) if declaration else []
            if {spec["name"]: [field[0] for field in spec["fields"]] for spec in specs} != {
                    name: list(spec["fields"]) for name, spec in expected.items()}:
                raise ValueError("DataInit.gs tables or columns differ from source contract")
        except (ValueError, TypeError, AttributeError, KeyError, OSError) as exc:
            problems.append(f"data-contract.json is invalid or inconsistent: {exc}")

    fidelity_gap_count = 0
    formula_gap_count = capability_gap_count = 0
    ledger_path = out / "conversion-ledger.json"
    if ledger_path.exists():
        try:
            ledger = json.loads(ledger_path.read_text())
            import hashlib
            from .preflight import assess
            from .fidelity import ledger_rows, iter_expressions
            from .fx.source_repairs import validate_source_repairs
            from .ir import AppIR
            inventory_text = (out / 'source-inventory.json').read_text()
            inventory = AppIR.model_validate_json(inventory_text)
            for _screen, _control, _property, expr in iter_expressions(inventory):
                validate_source_repairs(expr.raw, expr.source_repairs)
                if expr.source_repairs and (expr.emission_status == 'emitted' or any(
                        repair['deviation'] not in expr.approximations for repair in expr.source_repairs)):
                    raise ValueError('source repair cannot be reported as unchanged source equivalence')
            if json.loads(contract_path.read_text()).get('sources') != [ds.model_dump() for ds in inventory.data_sources]:
                raise ValueError('data contract differs from source inventory')
            if ledger.get('schemaVersion') != 2:
                raise ValueError('unsupported ledger schema; regenerate this project')
            if ledger.get('sourceInventorySha256') != hashlib.sha256(inventory_text.encode()).hexdigest():
                raise ValueError('source inventory fingerprint differs')
            expected_preflight = assess(inventory)
            if ledger.get('capabilities') != expected_preflight['capabilities']:
                raise ValueError('capability inventory is incomplete or differs from source')
            if json.loads((out / 'preflight.json').read_text()) != expected_preflight:
                raise ValueError('preflight differs from source inventory')
            if expected_ownership is not None and ledger.get('dataverseOwnership', {}) != expected_ownership:
                raise ValueError('ownership adapter differs from exported source contract')
            if expected_states is not None and ledger.get('dataverseStateModels', {}) != expected_states:
                raise ValueError('state adapter differs from exported source contract')
            rows = ledger.get("formulas", [])
            if not isinstance(rows, list):
                raise ValueError("formulas must be a list")
            if rows != ledger_rows(inventory):
                raise ValueError('formula census differs from source inventory')
            formula_gap_count = sum(1 for row in rows if row.get('emission') != 'emitted' or row.get('translation') != 'rule')
            capability_gap_count = len(expected_preflight['issues'])
            fidelity_gap_count = formula_gap_count + capability_gap_count
        except (ValueError, AttributeError, TypeError, KeyError, OSError) as exc:
            problems.append(f"conversion-ledger.json is invalid: {exc}")

    return {"ok": not problems, "problems": problems, "stub_count": stub_count,
            "fidelity_gap_count": fidelity_gap_count,
            "formula_gap_count": formula_gap_count, "capability_gap_count": capability_gap_count}
