"""Consistency gate: signatures emitted into generated JS must exist in the
static runtime libraries with matching arity.

Catches drift like the powerapps_*(state, name, ...) helpers being defined
with a different parameter order than the emitter writes into App.js — a
bug class syntax checks and unit tests on either side alone cannot see.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
STATIC = REPO / "static"

# (name, expected first params in the runtime definition, min arg count
#  the emitter passes). Emitted shape: fn(state, 'Name', ...)
EXPECTED = {
    "powerapps_collect": (["st", "ds"], 2),
    "powerapps_clearCollect": (["st", "ds"], 2),
    "powerapps_remove": (["st", "ds", "record"], 2),
    "powerapps_removeIf": (["st", "ds", "pred"], 2),
}


def runtime_js() -> str:
    return (STATIC / "gas-runtime.js").read_text()


def main() -> int:
    src = runtime_js()
    problems = []
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

    # The emitter must actually reference each helper with (state, ...) shape.
    emitter = (REPO / "src" / "pfx2gas" / "fx" / "emitter.py").read_text()
    for name in EXPECTED:
        if f"{name}(state" not in emitter and name not in emitter:
            problems.append(f"emitter no longer emits {name}(...)")

    if problems:
        print("RUNTIME-EMITTER DRIFT DETECTED:")
        for p in problems:
            print(" -", p)
        return 1
    print(f"OK: {len(EXPECTED)} collection helpers match the emitter's call shape")
    return 0


if __name__ == "__main__":
    sys.exit(main())
