"""Soak: convert, validate, and boot every real sample app."""
import os
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from pfx2gas.analyze import analyze
from pfx2gas.fidelity import iter_expressions
from pfx2gas.parse import parse
from pfx2gas.synth.build import synthesize
from pfx2gas.startup_sim import simulate_project
from pfx2gas.unpack import unpack
from pfx2gas.validate import validate_project

SAMPLES_DIR = Path(os.environ.get("PFX2GAS_SAMPLES_DIR", REPO / "samples" / "real"))
OUT = Path(os.environ.get("PFX2GAS_SOAK_OUT", "/tmp/gap-regression"))
OUT.mkdir(parents=True, exist_ok=True)

apps = sorted(SAMPLES_DIR.glob("*.msapp"))
print(f"{'app':35s} convert  validate  boot     (time)")
fails = 0
formula_total = 0
formula_translated = 0
formula_emitted = 0
formula_approximated = 0
formula_gaps = 0
for f in apps:
    name = f.stem
    out = OUT / name
    t0 = time.time()
    shutil.rmtree(out, ignore_errors=True)
    valid_ok = False
    boot_ok = False
    try:
        ir = analyze(parse(unpack(f)))
        synthesize(ir, out)
        expressions = [expr for _screen, _control, _prop, expr in iter_expressions(ir)]
        formula_total += len(expressions)
        formula_translated += sum(
            expr.translation_status in {"rule", "llm"} for expr in expressions
        )
        formula_emitted += sum(expr.emission_status == "emitted" for expr in expressions)
        formula_approximated += sum(
            expr.emission_status == "approximated" for expr in expressions
        )
        formula_gaps += sum(
            expr.emission_status in {"ignored", "unsupported"} for expr in expressions
        )
        res = validate_project(out)
        valid_ok = res["ok"]
        verdict = simulate_project(out) if valid_ok else {}
        boot_ok = (verdict.get("visible") == [ir.start_screen]
                   and verdict.get("refErrors") == [])
        ok = valid_ok and boot_ok
        probs = res["problems"][:2]
        if valid_ok and not boot_ok:
            probs = [f"startup: visible={verdict.get('visible')} "
                     f"refErrors={verdict.get('refErrors')}"]
    except Exception as e:  # noqa: BLE001
        ok, probs = False, [str(e)[:110]]
    if not ok:
        fails += 1
    print(f"{name:35s} {'OK' if ok else 'FAIL':7s} "
          f"{'OK' if valid_ok else 'FAIL':8s} {'OK' if boot_ok else 'FAIL':8s} "
          f"({time.time() - t0:.1f}s) {probs}")
print(f"\n{len(apps) - fails}/{len(apps)} apps convert + validate + boot cleanly")
print(
    f"fidelity: {formula_translated}/{formula_total} translated; "
    f"{formula_emitted} emitted; {formula_approximated} approximated; "
    f"{formula_gaps} ignored/unsupported"
)
sys.exit(1 if fails else 0)
