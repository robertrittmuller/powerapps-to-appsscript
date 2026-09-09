"""Stage 5: validate a synthesized project (syntax, structure, stub census)."""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

REQUIRED_FILES = ["Code.gs", "DataInit.gs", "appsscript.json", "Index.html",
                  "Screens.html", "App.js.html", "conversion-ledger.json", "data-contract.json"]


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
    if contract_path.exists():
        try:
            from .ir import AppIR, DataSource
            from .synth.server import data_contracts
            contract = json.loads(contract_path.read_text())
            if contract.get("version") != 1 or not isinstance(contract.get("sources"), list):
                raise ValueError("unsupported contract shape")
            sources = [DataSource.model_validate(ds) for ds in contract["sources"]]
            expected = data_contracts(AppIR(name="validation", data_sources=sources))
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
    ledger_path = out / "conversion-ledger.json"
    if ledger_path.exists():
        try:
            ledger = json.loads(ledger_path.read_text())
            rows = ledger.get("formulas", [])
            if not isinstance(rows, list):
                raise ValueError("formulas must be a list")
            fidelity_gap_count = sum(
                1 for row in rows if row.get("emission") != "emitted"
            )
        except (json.JSONDecodeError, ValueError, AttributeError) as exc:
            problems.append(f"conversion-ledger.json is invalid: {exc}")

    return {"ok": not problems, "problems": problems, "stub_count": stub_count,
            "fidelity_gap_count": fidelity_gap_count}
