"""Execute generated setup and reads against the scalar-only Sheets double."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess


def simulate_server(out_dir: str | Path) -> dict:
    out = Path(out_dir)
    sources = json.loads((out / "data-contract.json").read_text())["sources"]
    tables = [ds for ds in sources if ds["origin"] not in {"service", "view", "option_set", "collection"} and ds["fields"]]
    calls = []
    for ds in tables:
        calls.append({"fn": "api", "args": [ds["name"], "list", {}]})
        calls.extend({"fn": "apiChoices", "args": [ds["name"], field["logical_name"] or field["name"]]}
                     for field in ds["fields"] if field["choices"])
    result = {"status": "pass", "evidenceType": "generated-server-with-sheets-test-double",
              "tables": len(tables), "choiceFields": len(calls) - len(tables), "errors": []}
    try:
        backend = Path(__file__).resolve().parents[2] / "tests/browser/gas-server.cjs"
        execution = subprocess.run(["node", str(backend), str(out)],
            input="".join(json.dumps(call) + "\n" for call in calls), capture_output=True, text=True, timeout=30)
        if execution.returncode:
            raise RuntimeError(execution.stderr[-1500:])
        lines = execution.stdout.splitlines()
        if len(lines) != len(calls):
            raise RuntimeError("generated server did not return every requested result")
        for call, line in zip(calls, lines):
            response = json.loads(line)
            if "error" in response:
                result["errors"].append(f"{call['fn']} {call['args'][0]}: {response['error']}")
            elif not isinstance(response.get("result"), list):
                result["errors"].append(f"{call['fn']} {call['args'][0]} did not return a table")
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        result["errors"].append(str(exc))
    if result["errors"]:
        result["status"] = "fail"
    return result
