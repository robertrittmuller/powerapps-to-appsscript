from __future__ import annotations

from pathlib import Path

from pfx2gas.benchmark import (FAIL, PASS, UNASSESSED, build_scorecard,
                               evaluate_grades, load_catalog,
                               render_scorecard_markdown)

REPO = Path(__file__).parent.parent


def _app(*, journey_coverage="partial", journey_status=PASS, console_errors=None):
    return {
        "id": "sample",
        "name": "Sample",
        "metadata": {
            "archetypes": ["crud"],
            "journeyCoverage": journey_coverage,
            "visualCoverage": "none",
        },
        "stages": {"convert": PASS, "validate": PASS, "boot": PASS},
        "observed": {
            "sourceFormat": "modern-pa-yaml",
            "screenCount": 1,
            "controlCount": 2,
        },
        "formulaFidelity": {"total": 4, "emitted": 3, "gaps": 1},
        "evidence": {
            "startup": {
                "expectedScreen": "Home",
                "visibleScreens": ["Home"],
                "consoleErrors": console_errors or [],
            },
            "journeys": [
                {
                    "id": "create-record",
                    "description": "Create a record",
                    "required": True,
                    "status": journey_status,
                }
            ],
            "visual": {"status": UNASSESSED},
        },
        "problems": [],
    }


def test_catalog_is_versioned_and_declares_all_current_samples():
    catalog = load_catalog(REPO / "benchmark" / "apps.json")
    assert catalog["schemaVersion"] == 1
    assert set(catalog["apps"]) == {
        "clean-ui",
        "containers-guide",
        "editable-grid",
        "expandable-nav",
        "helpdesk",
        "modern-card",
        "sentiment-feedback",
        "svg-app",
        "tic-tac-toe",
        "wordle",
    }


def test_startup_does_not_get_promoted_to_usability_or_visual_fidelity():
    grades = evaluate_grades(_app())
    assert grades["bootable"]["status"] == PASS
    assert grades["usable"]["status"] == UNASSESSED
    assert grades["highFidelity"]["status"] == UNASSESSED


def test_complete_journey_coverage_can_prove_usable():
    grades = evaluate_grades(_app(journey_coverage="complete"))
    assert grades["usable"]["status"] == PASS


def test_failed_required_journey_fails_usable_grade():
    grades = evaluate_grades(
        _app(journey_coverage="complete", journey_status=FAIL)
    )
    assert grades["bootable"]["status"] == PASS
    assert grades["usable"]["status"] == FAIL


def test_any_startup_console_error_fails_bootable_and_dependent_tiers():
    grades = evaluate_grades(_app(console_errors=["binding error: boom"]))
    assert grades["bootable"]["status"] == FAIL
    assert grades["usable"]["status"] == FAIL
    assert grades["highFidelity"]["status"] == FAIL


def test_scorecard_reports_catalog_coverage_and_each_app_separately():
    scorecard = build_scorecard(
        [_app()],
        catalog_path="benchmark/apps.json",
        sample_dir="samples/real",
        catalog_app_ids=["sample", "missing"],
    )
    assert scorecard["catalogCoverage"]["missingCatalogApps"] == ["missing"]
    markdown = render_scorecard_markdown(scorecard)
    assert "Catalog apps not present in this run: `missing`" in markdown
    assert "| Sample | modern-pa-yaml | crud | pass | unassessed | unassessed |" in markdown
