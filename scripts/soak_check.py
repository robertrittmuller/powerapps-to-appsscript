"""Soak: convert every sample app in-process and validate the output."""
import os
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from pfx2gas.analyze import analyze
from pfx2gas.parse import parse
from pfx2gas.synth.build import synthesize
from pfx2gas.unpack import unpack
from pfx2gas.validate import validate_project

SAMPLES_DIR = Path(os.environ.get("PFX2GAS_SAMPLES_DIR", REPO / "samples" / "real"))
OUT = Path(os.environ.get("PFX2GAS_SOAK_OUT", "/tmp/gap-regression"))
OUT.mkdir(parents=True, exist_ok=True)

apps = sorted(SAMPLES_DIR.glob("*.msapp"))
print(f"{'app':35s} convert  validate  (time)")
fails = 0
for f in apps:
    name = f.stem
    out = OUT / name
    t0 = time.time()
    shutil.rmtree(out, ignore_errors=True)
    try:
        ir = analyze(parse(unpack(f)))
        synthesize(ir, out)
        res = validate_project(out)
        ok = res["ok"]
        probs = res["problems"][:2]
    except Exception as e:  # noqa: BLE001
        ok, probs = False, [str(e)[:110]]
    if not ok:
        fails += 1
    print(f"{name:35s} {'OK' if ok else 'FAIL':7s} {'OK' if ok else 'FAIL':8s} "
          f"({time.time() - t0:.1f}s) {probs}")
print(f"\n{len(apps) - fails}/{len(apps)} apps convert + validate cleanly")
sys.exit(1 if fails else 0)
