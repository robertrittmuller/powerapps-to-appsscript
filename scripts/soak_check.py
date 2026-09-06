"""Convert, validate, boot, and score every real sample app.

The generated JSON/Markdown scorecards distinguish structural startup evidence
from critical-journey and visual evidence. Missing higher-tier evidence is
reported as unassessed, never silently promoted to a pass.
"""
from __future__ import annotations

import os
import hashlib
import shutil
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from pfx2gas.analyze import analyze
from pfx2gas.benchmark import (FAIL, PASS, UNASSESSED, build_scorecard,
                               load_catalog, metadata_for, write_scorecard)
from pfx2gas.fidelity import iter_expressions
from pfx2gas.parse import parse
from pfx2gas.startup_sim import simulate_project
from pfx2gas.synth.build import synthesize
from pfx2gas.unpack import unpack
from pfx2gas.validate import validate_project

SAMPLES_DIR = Path(os.environ.get("PFX2GAS_SAMPLES_DIR", REPO / "samples" / "real"))
OUT = Path(os.environ.get("PFX2GAS_SOAK_OUT", REPO / ".artifacts" / "benchmark"))
CATALOG_PATH = Path(
    os.environ.get("PFX2GAS_BENCHMARK_CATALOG", REPO / "benchmark" / "apps.json")
)


def _pending_journeys(metadata: dict[str, Any], reason: str) -> list[dict[str, Any]]:
    return [
        {
            "id": journey["id"],
            "description": journey.get("description", ""),
            "required": journey.get("required", True),
            "status": UNASSESSED,
            "error": reason,
        }
        for journey in metadata.get("criticalJourneys", [])
    ]


def _journey_evidence(
    metadata: dict[str, Any], verdict: dict[str, Any] | None
) -> list[dict[str, Any]]:
    executed = {
        result["id"]: result for result in (verdict or {}).get("journeyResults", [])
    }
    evidence = []
    for journey in metadata.get("criticalJourneys", []):
        result = executed.get(journey["id"])
        item = {
            "id": journey["id"],
            "description": journey.get("description", ""),
            "required": journey.get("required", True),
        }
        if result:
            item.update(result)
        else:
            item.update({
                "status": UNASSESSED,
                "error": "journey has no automated steps",
            })
        evidence.append(item)
    return evidence


def _formula_fidelity(ir: Any) -> dict[str, Any]:
    expressions = list(iter_expressions(ir))
    gaps = [
        (prop, expr)
        for _screen, _control, prop, expr in expressions
        if expr.emission_status in {"ignored", "unsupported"}
    ]
    top_gaps = [
        {"property": prop, "count": count}
        for prop, count in Counter(prop for prop, _expr in gaps).most_common(15)
    ]
    return {
        "total": len(expressions),
        "translated": sum(
            expr.translation_status in {"rule", "llm"}
            for _screen, _control, _prop, expr in expressions
        ),
        "emitted": sum(
            expr.emission_status == "emitted"
            for _screen, _control, _prop, expr in expressions
        ),
        "approximated": sum(
            expr.emission_status == "approximated"
            for _screen, _control, _prop, expr in expressions
        ),
        "gaps": len(gaps),
        "topGaps": top_gaps,
    }


def _run_app(path: Path, output_dir: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    t0 = time.time()
    app: dict[str, Any] = {
        "id": path.stem,
        "name": metadata["displayName"],
        "file": path.name,
        "inputSha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "metadata": metadata,
        "stages": {"convert": FAIL, "validate": FAIL, "boot": FAIL},
        "observed": {},
        "formulaFidelity": {
            "total": 0,
            "translated": 0,
            "emitted": 0,
            "approximated": 0,
            "gaps": 0,
            "topGaps": [],
        },
        "evidence": {
            "startup": {
                "expectedScreen": None,
                "visibleScreens": [],
                "referenceErrors": [],
                "consoleErrors": [],
            },
            "journeys": _pending_journeys(metadata, "app was not exercised"),
            "visual": {
                "status": UNASSESSED,
                "reason": "no deterministic visual baseline was exercised",
            },
        },
        "problems": [],
    }
    shutil.rmtree(output_dir, ignore_errors=True)
    try:
        unpacked = unpack(path)
        ir = analyze(parse(unpacked))
        synthesize(ir, output_dir)
        app["stages"]["convert"] = PASS
        app["name"] = ir.name or metadata["displayName"]
        controls = [ctrl for screen in ir.screens for ctrl in screen.walk_controls()]
        app["observed"] = {
            "sourceFormat": (
                "legacy-binary-json"
                if any("legacy binary-JSON" in warning for warning in ir.warnings)
                else "modern-pa-yaml"
            ),
            "startScreen": ir.start_screen,
            "screenCount": len(ir.screens),
            "controlCount": len(controls),
            "controlTypes": dict(sorted(Counter(ctrl.type for ctrl in controls).items())),
            "dataSourceCount": len(ir.data_sources),
            "dataSourceOrigins": dict(
                sorted(Counter(source.origin for source in ir.data_sources).items())
            ),
            "warnings": list(ir.warnings),
        }
        app["formulaFidelity"] = _formula_fidelity(ir)

        validation = validate_project(output_dir)
        app["stages"]["validate"] = PASS if validation["ok"] else FAIL
        app["problems"].extend(validation["problems"])
        if validation["ok"]:
            automated = [
                {"id": journey["id"], "steps": journey["steps"]}
                for journey in metadata.get("criticalJourneys", [])
                if journey.get("steps")
            ]
            verdict = simulate_project(output_dir, automated)
            startup = {
                "expectedScreen": ir.start_screen,
                "visibleScreens": verdict.get("visible", []),
                "referenceErrors": verdict.get("refErrors", []),
                "consoleErrors": verdict.get("consoleErrors", []),
            }
            app["evidence"]["startup"] = startup
            app["evidence"]["journeys"] = _journey_evidence(metadata, verdict)
            boot_ok = (
                startup["visibleScreens"] == [ir.start_screen]
                and not startup["referenceErrors"]
                and not startup["consoleErrors"]
            )
            app["stages"]["boot"] = PASS if boot_ok else FAIL
            if not boot_ok:
                app["problems"].append(
                    "startup: expected={expected!r}, visible={visible!r}, errors={errors!r}".format(
                        expected=ir.start_screen,
                        visible=startup["visibleScreens"],
                        errors=startup["consoleErrors"],
                    )
                )
        else:
            app["evidence"]["journeys"] = _pending_journeys(
                metadata, "generated project did not validate"
            )
    except Exception as exc:  # noqa: BLE001
        app["problems"].append(str(exc)[:400])
        app["evidence"]["journeys"] = _pending_journeys(
            metadata, "conversion or startup simulation failed"
        )
    app["durationSeconds"] = round(time.time() - t0, 3)
    return app


def main() -> int:
    catalog = load_catalog(CATALOG_PATH)
    OUT.mkdir(parents=True, exist_ok=True)
    apps_dir = OUT / "apps"
    apps = sorted(SAMPLES_DIR.glob("*.msapp"))
    print(f"{'app':35s} convert  validate  boot     (time)")
    results = []
    for path in apps:
        result = _run_app(path, apps_dir / path.stem, metadata_for(catalog, path.stem))
        results.append(result)
        stages = result["stages"]
        print(
            f"{path.stem:35s} {stages['convert'].upper():7s} "
            f"{stages['validate'].upper():8s} {stages['boot'].upper():8s} "
            f"({result['durationSeconds']:.1f}s) {result['problems'][:2]}"
        )

    scorecard = build_scorecard(
        results,
        catalog_path=CATALOG_PATH,
        sample_dir=SAMPLES_DIR,
        catalog_app_ids=list(catalog["apps"]),
        required_app_ids=catalog.get("requiredApps", list(catalog["apps"])),
    )
    json_path, md_path = write_scorecard(scorecard, OUT)
    boot_counts = scorecard["summary"]["grades"]["bootable"]
    fidelity = Counter()
    for result in results:
        for key in ("total", "translated", "emitted", "approximated", "gaps"):
            fidelity[key] += result["formulaFidelity"][key]
    print(
        f"\n{boot_counts[PASS]}/{len(apps)} apps are bootable; "
        f"{boot_counts[FAIL]} failed"
    )
    print(
        f"fidelity: {fidelity['translated']}/{fidelity['total']} translated; "
        f"{fidelity['emitted']} emitted; {fidelity['approximated']} approximated; "
        f"{fidelity['gaps']} ignored/unsupported"
    )
    print(f"scorecards: {json_path} and {md_path}")
    for error in scorecard["gateErrors"]:
        print(f"GATE FAIL: {error}")
    return 1 if scorecard["gateErrors"] else 0


if __name__ == "__main__":
    sys.exit(main())
