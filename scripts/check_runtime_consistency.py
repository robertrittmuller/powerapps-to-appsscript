"""Consistency gate between the code emitter and the static runtime.

1. Collection-helper signatures match the emitter's call shape.
2. Every bare function the emitter writes into generated App.js must exist in
   the runtime's global export surface (global.<name> =) or fx-stdlib —
   catches drift like bind() being defined but never exported, which only
   surfaced as a blank screen in the deployed app.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tests" / "fixtures"))

STATIC = REPO / "static"

# (name, expected first params in the runtime definition, min arg count)
EXPECTED = {
    "powerapps_collect": (["st", "ds"], 2),
    "powerapps_clearCollect": (["st", "ds"], 2),
    "powerapps_remove": (["st", "ds", "record"], 2),
    "powerapps_removeIf": (["st", "ds", "pred"], 2),
}

# Bare calls that are JS builtins/keywords or namespaced by construction.
ALLOWED = {
    # language / builtins
    "if", "for", "while", "switch", "catch", "return", "function", "typeof",
    "new", "async", "await", "Promise", "Object", "Array", "String", "Number", "Boolean",
    "Date", "JSON", "parseInt", "parseFloat", "isNaN", "Error", "Set", "Map",
    "encodeURIComponent", "decodeURIComponent",
    "console",
    # namespaced calls
    "FX", "FXRuntime", "FXCollections",
    # server-API + collection helpers (checked separately above / exported)
}

KEYWORDS = ALLOWED | {
    "if", "for", "while", "switch", "catch", "return", "function", "typeof",
    "new",
}


def runtime_exports(src: str) -> set[str]:
    return set(re.findall(r"global\.(\w+)\s*=", src))


def fx_exports() -> set[str]:
    src = (STATIC / "fx-stdlib.js").read_text()
    names = set(re.findall(r"^\s{4}(\w+):\s*function", src, re.M))
    return {"FX"} | names


def generated_fixture_bare_calls() -> tuple[list[str], Path, set[str], set[str]]:
    """Convert navigation and form fixtures and collect generated bare calls."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "fixture_build", REPO / "tests" / "fixtures" / "build.py")
    fixture_build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture_build)

    from pfx2gas.analyze import analyze
    from pfx2gas.parse import parse
    from pfx2gas.synth.build import synthesize
    from pfx2gas.unpack import unpack

    tmp = Path(tempfile.mkdtemp())
    apps = []
    out = tmp / "FixtureA"
    fixture_build.build_fixtures()
    for fixture_name in ("fixtureA.msapp", "fixtureForm.msapp", "fixtureCharts.msapp", "fixtureScopes.msapp", "fixtureGallery.msapp", "fixtureTimer.msapp", "fixtureStorage.msapp"):
        ir = analyze(parse(unpack(fixture_build.FIXTURE_DIR / fixture_name)))
        out = synthesize(ir, tmp / fixture_name.removesuffix(".msapp"))
        apps.append((out / "App.js.html").read_text())
    app = "\n".join(apps).replace("<script>\n", "").replace("\n</script>", "")
    # strip comments so prose like "// OnStart (transpiled...)" isn't a call
    app = re.sub(r"//[^\n]*", "", app)
    app = re.sub(r"/\*.*?\*/", "", app, flags=re.S)
    calls = set(re.findall(r"(?<![\w.$])([a-zA-Z_]\w*)\s*\(", app))
    runtime_calls = set(re.findall(r"\bFXRuntime\.(\w+)\s*\(", app))
    fx_calls = set(re.findall(r"\bFX\.(\w+)\s*\(", app))
    return sorted(calls), out, runtime_calls, fx_calls


def main() -> int:
    problems: list[str] = []
    src = (STATIC / "gas-runtime.js").read_text()
    exports = runtime_exports(src)

    # 1. collection-helper signatures
    for name, (params, min_args) in EXPECTED.items():
        m = re.search(rf"{name}\s*=\s*function\s*\(([^)]*)\)", src)
        if not m:
            problems.append(f"{name}: not defined in gas-runtime.js")
            continue
        got = [p.strip() for p in m.group(1).split(",") if p.strip()]
        if got[: len(params)] != params:
            problems.append(
                f"{name}: runtime signature ({', '.join(got)}) does not start with "
                f"({', '.join(params)}); emitter writes {name}(state, '<Name>', ...)")
        if len(got) < min_args:
            problems.append(f"{name}: takes {len(got)} args, emitter needs >= {min_args}")

    # 2. emitter <-> runtime export surface (real fixture conversion)
    calls, _out, runtime_calls, fx_calls = generated_fixture_bare_calls()
    fx = fx_exports()
    for call in calls:
        if call in KEYWORDS or call in fx:
            continue
        if call not in exports:
            problems.append(
                f"emitter generates {call}(...) but gas-runtime.js never exports "
                f"global.{call} — ReferenceError at app startup")

    # Namespaced helpers are just as critical as bare globals. Check their
    # actual callable surface in Node, including row-scoped handler helpers.
    run = subprocess.run(["node", "-e", "global.document={getElementById:()=>null,addEventListener:()=>{}};"
        "require('./static/gas-runtime.js');"
        "const FX=require('./static/fx-stdlib.js');"
        "const functions=o=>Object.keys(o).filter(k=>typeof o[k]==='function');"
        "process.stdout.write(JSON.stringify({runtime:functions(FXRuntime),fx:functions(FX)}));"],
        cwd=REPO, text=True, capture_output=True, check=True)
    surfaces = json.loads(run.stdout)
    available = set(surfaces["runtime"])
    for call in sorted(runtime_calls - available):
        problems.append(f"emitter generates FXRuntime.{call}(...) but runtime has no callable helper")
    # Cover both actual generation (special emitter rewrites) and ordinary
    # function-map templates, even before a fixture uses a newly added map.
    from pfx2gas.fx.function_map import FUNCTION_MAP
    for spec in FUNCTION_MAP.values():
        if "special-cased" not in spec.note:
            fx_calls.update(re.findall(r"\bFX\.(\w+)\s*\(", spec.js))
    for call in sorted(fx_calls - set(surfaces["fx"])):
        problems.append(f"emitter generates FX.{call}(...) but stdlib has no callable helper")

    if problems:
        print("RUNTIME-EMITTER DRIFT DETECTED:")
        for p in problems:
            print(" -", p)
        return 1
    print(f"OK: signatures match; {len(calls)} bare calls from generated code "
          f"all resolve against the runtime export surface")
    return 0


if __name__ == "__main__":
    sys.exit(main())
