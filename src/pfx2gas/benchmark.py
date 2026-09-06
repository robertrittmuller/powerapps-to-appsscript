"""Compatibility benchmark scorecards and evidence-based quality grades.

The benchmark deliberately keeps three outcomes separate.  A clean startup is
runtime evidence for ``bootable``; it is not evidence that a business journey
works or that the rendered app matches the source visually.
"""
from __future__ import annotations

import json
import hashlib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PASS = "pass"
FAIL = "fail"
UNASSESSED = "unassessed"
GRADE_STATUSES = {PASS, FAIL, UNASSESSED}
COVERAGE_STATUSES = {"none", "partial", "complete"}


def converter_fingerprint() -> str:
    """Identify exact converter sources, including uncommitted local changes."""
    root = Path(__file__).resolve().parents[2]
    digest = hashlib.sha256()
    for directory, suffix in ((root / "src", ".py"), (root / "static", ".js")):
        for path in sorted(directory.rglob("*" + suffix)):
            digest.update(str(path.relative_to(root)).encode())
            digest.update(b"\0")
            digest.update(path.read_bytes())
    return digest.hexdigest()


def load_catalog(path: str | Path) -> dict[str, Any]:
    """Load and minimally validate the versioned app/archetype catalog."""
    catalog_path = Path(path)
    data = json.loads(catalog_path.read_text())
    if data.get("schemaVersion") != 1:
        raise ValueError("benchmark catalog schemaVersion must be 1")
    apps = data.get("apps")
    if not isinstance(apps, dict):
        raise ValueError("benchmark catalog apps must be an object")
    required_apps = data.get("requiredApps", list(apps))
    if (not isinstance(required_apps, list) or not required_apps
            or any(not isinstance(name, str) or name not in apps for name in required_apps)
            or len(set(required_apps)) != len(required_apps)):
        raise ValueError("benchmark requiredApps must name unique catalog apps")
    for app_id, app in apps.items():
        if not isinstance(app, dict):
            raise ValueError(f"benchmark app {app_id!r} must be an object")
        for key in ("journeyCoverage", "visualCoverage"):
            if app.get(key, "none") not in COVERAGE_STATUSES:
                raise ValueError(
                    f"benchmark app {app_id!r} has invalid {key}: {app.get(key)!r}"
                )
        journeys = app.get("criticalJourneys", [])
        if not isinstance(journeys, list):
            raise ValueError(
                f"benchmark app {app_id!r} criticalJourneys must be an array"
            )
        if any(not isinstance(journey, dict) for journey in journeys):
            raise ValueError(
                f"benchmark app {app_id!r} critical journeys must be objects"
            )
        ids = [journey.get("id") for journey in journeys]
        if len(ids) != len(set(ids)) or any(not item for item in ids):
            raise ValueError(
                f"benchmark app {app_id!r} critical journey ids must be unique"
            )
    return data


def metadata_for(catalog: dict[str, Any], app_id: str) -> dict[str, Any]:
    """Return catalog metadata, with conservative defaults for ad-hoc apps."""
    configured = catalog.get("apps", {}).get(app_id, {})
    return {
        "displayName": configured.get("displayName", app_id),
        "archetypes": list(configured.get("archetypes", ["unclassified"])),
        "source": configured.get("source"),
        "journeyCoverage": configured.get("journeyCoverage", "none"),
        "visualCoverage": configured.get("visualCoverage", "none"),
        "criticalJourneys": list(configured.get("criticalJourneys", [])),
        "sourceLimitations": list(configured.get("sourceLimitations", [])),
    }


def evaluate_grades(app: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Calculate evidence-based grades without promoting missing evidence.

    Higher grades fail when their prerequisite cannot boot, but remain
    unassessed when journey or visual coverage is incomplete.  This distinction
    prevents a green syntax/startup check from being reported as usability.
    """
    stages = app.get("stages", {})
    startup = app.get("evidence", {}).get("startup", {})
    expected_screen = startup.get("expectedScreen")
    visible_screens = startup.get("visibleScreens", [])
    boot_checks = (
        stages.get("convert") == PASS,
        stages.get("validate") == PASS,
        stages.get("boot") == PASS,
        expected_screen is not None and visible_screens == [expected_screen],
        not startup.get("referenceErrors"),
        not startup.get("consoleErrors"),
    )
    if all(boot_checks):
        bootable = {"status": PASS, "reason": "clean generated-app startup"}
    else:
        bootable = {
            "status": FAIL,
            "reason": "conversion, validation, or generated-app startup failed",
        }

    metadata = app.get("metadata", {})
    journey_results = app.get("evidence", {}).get("journeys", [])
    required = [item for item in journey_results if item.get("required", True)]
    declared = [item for item in metadata.get("criticalJourneys", [])
                if item.get("required", True)]
    reported_ids = {item.get("id") for item in required}
    missing_journeys = [item for item in declared if item.get("id") not in reported_ids]
    if bootable["status"] == FAIL:
        usable = {"status": FAIL, "reason": "app is not bootable"}
    elif any(item.get("status") == FAIL for item in required):
        usable = {"status": FAIL, "reason": "a required critical journey failed"}
    elif (
        metadata.get("journeyCoverage") == "complete"
        and not missing_journeys
        and required
        and all(item.get("status") == PASS for item in required)
    ):
        usable = {"status": PASS, "reason": "all required critical journeys passed"}
    else:
        usable = {
            "status": UNASSESSED,
            "reason": "complete automated critical-journey evidence is not available",
        }

    visual = app.get("evidence", {}).get("visual", {})
    if usable["status"] == FAIL:
        high_fidelity = {"status": FAIL, "reason": "a prerequisite business workflow failed"}
    elif visual.get("status") == FAIL:
        high_fidelity = {
            "status": FAIL,
            "reason": "visual or interaction comparison exceeded its tolerance",
        }
    elif (
        metadata.get("visualCoverage") == "complete"
        and visual.get("status") == PASS
        and usable["status"] == PASS
    ):
        high_fidelity = {
            "status": PASS,
            "reason": "all required visual comparisons passed",
        }
    else:
        high_fidelity = {
            "status": UNASSESSED,
            "reason": "complete deterministic visual evidence is not available",
        }

    return {
        "bootable": bootable,
        "usable": usable,
        "highFidelity": high_fidelity,
    }


def build_scorecard(
    apps: list[dict[str, Any]],
    *,
    catalog_path: str | Path,
    sample_dir: str | Path,
    catalog_app_ids: list[str] | None = None,
    required_app_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Attach grades and aggregate only status counts (never one vanity score)."""
    for app in apps:
        app["grades"] = evaluate_grades(app)
    grades: dict[str, dict[str, int]] = {}
    for grade_name in ("bootable", "usable", "highFidelity"):
        counts = Counter(app["grades"][grade_name]["status"] for app in apps)
        grades[grade_name] = {
            status: counts.get(status, 0) for status in (PASS, FAIL, UNASSESSED)
        }
    exercised = {app["id"] for app in apps}
    catalog_ids = set(catalog_app_ids or [])
    scorecard = {
        "schemaVersion": 1,
        "converterSourceSha256": converter_fingerprint(),
        "evidenceType": "generated-runtime-simulator",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "catalog": str(catalog_path),
        "sampleDirectory": str(sample_dir),
        "appCount": len(apps),
        "catalogCoverage": {
            "catalogAppCount": len(catalog_ids),
            "exercisedCatalogApps": sorted(exercised & catalog_ids),
            "missingCatalogApps": sorted(catalog_ids - exercised),
            "uncatalogedApps": sorted(exercised - catalog_ids),
            "missingRequiredApps": sorted(set(required_app_ids if required_app_ids is not None
                                              else catalog_ids) - exercised),
        },
        "summary": {"grades": grades},
        "apps": apps,
    }
    scorecard["gateErrors"] = gate_errors(scorecard)
    return scorecard


def gate_errors(scorecard: dict[str, Any]) -> list[str]:
    """Release gate: absent evidence stays unassessed; executed failures never pass."""
    errors = []
    if not scorecard.get("apps"):
        errors.append("no benchmark apps were exercised")
    for name in scorecard.get("catalogCoverage", {}).get("missingRequiredApps", []):
        errors.append(f"required benchmark app missing: {name}")
    for app in scorecard.get("apps", []):
        for grade, result in app["grades"].items():
            if result["status"] == FAIL:
                errors.append(f"{app['id']}: {grade}: {result['reason']}")
        # Executable required journeys cannot quietly become unassessed if the
        # runner omits one. Intentionally planned journeys have no steps yet.
        results = {j["id"]: j for j in app.get("evidence", {}).get("journeys", [])}
        for journey in app.get("metadata", {}).get("criticalJourneys", []):
            if journey.get("required", True) and journey.get("steps"):
                result = results.get(journey["id"], {})
                if result.get("status") != PASS:
                    errors.append(f"{app['id']}: required journey did not pass: {journey['id']}")
    return errors


def _md(value: Any) -> str:
    return str(value if value is not None else "—").replace("|", "\\|")


def _rate(numerator: int, denominator: int) -> str:
    if not denominator:
        return "—"
    return f"{100 * numerator / denominator:.1f}%"


def render_scorecard_markdown(scorecard: dict[str, Any]) -> str:
    """Render a reviewable companion to the machine-readable JSON artifact."""
    summary = scorecard["summary"]["grades"]
    lines = [
        "# pfx2gas compatibility benchmark",
        "",
        f"Generated: `{scorecard['generatedAt']}`  ",
        f"Apps exercised: **{scorecard['appCount']}**",
        "",
        "## Quality tiers",
        "",
        "| Tier | Pass | Fail | Unassessed |",
        "|---|---:|---:|---:|",
    ]
    coverage = scorecard.get("catalogCoverage", {})
    missing = coverage.get("missingCatalogApps", [])
    if missing:
        lines.insert(4, f"Catalog apps not present in this run: `{', '.join(missing)}`  ")
    for key, label in (
        ("bootable", "Bootable"),
        ("usable", "Usable"),
        ("highFidelity", "High fidelity"),
    ):
        counts = summary[key]
        lines.append(
            f"| {label} | {counts[PASS]} | {counts[FAIL]} | "
            f"{counts[UNASSESSED]} |"
        )

    lines.extend([
        "",
        "> Unassessed is intentional: startup evidence alone never proves a "
        "critical journey or visual match.",
        "",
        "## Per-app scorecard",
        "",
        "| App | Format | Archetypes | Bootable | Usable | High fidelity | "
        "Screens | Controls | Emitted | Ignored/unsupported |",
        "|---|---|---|---|---|---|---:|---:|---:|---:|",
    ])
    for app in scorecard["apps"]:
        observed = app.get("observed", {})
        fidelity = app.get("formulaFidelity", {})
        grades = app["grades"]
        lines.append(
            "| {name} | {format} | {archetypes} | {boot} | {usable} | {visual} | "
            "{screens} | {controls} | {emitted} | {gaps} |".format(
                name=_md(app.get("name", app["id"])),
                format=_md(observed.get("sourceFormat")),
                archetypes=_md(", ".join(app["metadata"].get("archetypes", []))),
                boot=grades["bootable"]["status"],
                usable=grades["usable"]["status"],
                visual=grades["highFidelity"]["status"],
                screens=observed.get("screenCount", 0),
                controls=observed.get("controlCount", 0),
                emitted=(
                    f"{fidelity.get('emitted', 0)}/{fidelity.get('total', 0)} "
                    f"({_rate(fidelity.get('emitted', 0), fidelity.get('total', 0))})"
                ),
                gaps=fidelity.get("gaps", 0),
            )
        )

    lines.extend(["", "## Evidence and blockers", ""])
    for app in scorecard["apps"]:
        lines.extend([f"### {_md(app.get('name', app['id']))}", ""])
        for grade_name, label in (
            ("bootable", "Bootable"),
            ("usable", "Usable"),
            ("highFidelity", "High fidelity"),
        ):
            grade = app["grades"][grade_name]
            lines.append(f"- {label}: **{grade['status']}** — {grade['reason']}")
        problems = app.get("problems", [])
        for limitation in app["metadata"].get("sourceLimitations", []):
            lines.append(f"- Source limitation: {_md(limitation)}")
        if problems:
            lines.append(f"- Problems: {_md('; '.join(problems[:5]))}")
        top_gaps = app.get("formulaFidelity", {}).get("topGaps", [])
        if top_gaps:
            rendered = ", ".join(
                f"{item['property']} ×{item['count']}" for item in top_gaps
            )
            lines.append(f"- Top fidelity gaps: {_md(rendered)}")
        lines.append("- Critical journeys:")
        journeys = app.get("evidence", {}).get("journeys", [])
        if not journeys:
            lines.append("  - none declared")
        for journey in journeys:
            lines.append(
                f"  - `{_md(journey.get('id'))}`: **{journey.get('status')}** — "
                f"{_md(journey.get('description', ''))}"
            )
            if journey.get("error"):
                lines.append(f"    - {_md(journey['error'])}")
        lines.append("")
    lines.extend(["## Release gate", ""])
    errors = scorecard.get("gateErrors", [])
    lines.extend([f"- {error}" for error in errors] or ["Pass: no required regression checks failed."])
    return "\n".join(lines).rstrip() + "\n"


def write_scorecard(scorecard: dict[str, Any], output_dir: str | Path) -> tuple[Path, Path]:
    """Write stable JSON and Markdown benchmark artifacts."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "benchmark-scorecard.json"
    md_path = out / "benchmark-scorecard.md"
    json_path.write_text(json.dumps(scorecard, indent=2, sort_keys=True) + "\n")
    md_path.write_text(render_scorecard_markdown(scorecard))
    return json_path, md_path
