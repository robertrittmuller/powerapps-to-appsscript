"""Reproduce the Microsoft acceptance baseline, retaining failures as failures.

Run: ./pfx2gas browser scripts/assess_microsoft_samples.py
This is deliberately separate from the established regression corpus until its
blocking startup/connector gaps are fixed; it does not imply usable conversion.
"""
import os
import subprocess
import sys

from fetch_microsoft_samples import REPO, main as fetch_samples


if __name__ == "__main__":
    fetch_samples()
    raise SystemExit(subprocess.run(
        [sys.executable, str(REPO / "scripts/soak_check.py")],
        env={**os.environ, "PFX2GAS_SAMPLES_DIR": str(REPO / "samples/microsoft"),
             "PFX2GAS_SOAK_OUT": str(REPO / ".artifacts/microsoft/benchmark"),
             "PFX2GAS_BENCHMARK_CATALOG": str(REPO / "benchmark/microsoft-apps.json")},
    ).returncode)
