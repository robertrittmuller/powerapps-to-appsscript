from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
import subprocess
import sys

import pytest

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


def test_first_action_failure_is_attached_without_promoting_partial_success(monkeypatch):
    monkeypatch.syspath_prepend(str(REPO / 'scripts'))
    from assess_microsoft_samples import merge_first_actions
    app = _app()
    app['inputSha256'] = 'source-hash'
    scorecard = build_scorecard([app], catalog_path='catalog', sample_dir='samples')
    probe = {'sourceAppId': 'sample', 'app': 'microsoft-first-action-sample',
             'inputSha256': 'source-hash', 'converterSourceSha256': scorecard['converterSourceSha256'],
             'status': FAIL, 'steps': [], 'assessmentScope': 'first action only',
             'evidenceType': 'chromium-generated-client-and-server'}
    merged = merge_first_actions(scorecard, [probe])
    assert merged['summary']['grades']['usable'][FAIL] == 1
    assert merged['gateErrors']
    probe['status'] = PASS
    merged = merge_first_actions(scorecard, [probe])
    assert merged['summary']['grades']['usable'][UNASSESSED] == 1
    assert len(app['evidence']['journeys']) == 2
    probe['consoleErrors'] = ['delayed connector error']
    assert merge_first_actions(scorecard, [probe])['summary']['grades']['usable'][FAIL] == 1


@pytest.mark.parametrize('mismatch', ['inputSha256', 'converterSourceSha256', 'sourceMetadata'])
def test_first_action_evidence_rejects_stale_source_or_converter(monkeypatch, mismatch):
    monkeypatch.syspath_prepend(str(REPO / 'scripts'))
    from assess_microsoft_samples import merge_first_actions
    app = _app()
    app['inputSha256'] = 'source-hash'
    scorecard = build_scorecard([app], catalog_path='catalog', sample_dir='samples')
    probe = {'sourceAppId': 'sample', 'inputSha256': 'source-hash',
             'converterSourceSha256': scorecard['converterSourceSha256']}
    probe[mismatch] = 'stale'
    with pytest.raises(ValueError, match='does not match'):
        merge_first_actions(scorecard, [probe])


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


@pytest.mark.parametrize("journey_status,coverage,expected", [
    (FAIL, "complete", FAIL), (PASS, "partial", UNASSESSED), (PASS, "complete", PASS),
])
def test_visual_evidence_requires_complete_passing_business_journeys(journey_status, coverage, expected):
    app = _app(journey_coverage=coverage, journey_status=journey_status)
    app["metadata"]["visualCoverage"] = "complete"
    app["evidence"]["visual"] = {"status": PASS}
    assert evaluate_grades(app)["highFidelity"]["status"] == expected


def test_missing_declared_journey_cannot_promote_app():
    app = _app(journey_coverage="complete")
    app["metadata"]["criticalJourneys"] = [
        {"id": "create-record"}, {"id": "reload-record", "steps": [{"action": "reload"}]},
    ]
    scorecard = build_scorecard([app], catalog_path="catalog", sample_dir="samples")
    assert app["grades"]["usable"]["status"] == UNASSESSED
    assert any("reload-record" in error for error in scorecard["gateErrors"])


@pytest.mark.parametrize("failure", ["journey", "missing-app"])
def test_soak_command_exits_nonzero_for_required_regressions(tmp_path, failure):
    samples = tmp_path / "samples"
    samples.mkdir()
    shutil.copyfile(REPO / "tests/fixtures/fixtureA.msapp", samples / "fixture.msapp")
    apps = {"fixture": {"criticalJourneys": [{
        "id": "visible-screen", "required": True,
        "steps": [{"action": "expectScreen", "screen": "wrong-screen"}]
        if failure == "journey" else [],
    }]}}
    if failure == "missing-app":
        apps["required-but-missing"] = {}
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"schemaVersion": 1, "apps": apps}))
    output = tmp_path / "scorecard"
    result = subprocess.run([sys.executable, str(REPO / "scripts/soak_check.py")],
        env={**os.environ, "PFX2GAS_SAMPLES_DIR": str(samples),
             "PFX2GAS_BENCHMARK_CATALOG": str(catalog), "PFX2GAS_SOAK_OUT": str(output)},
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 1, result.stdout + result.stderr
    scorecard = json.loads((output / "benchmark-scorecard.json").read_text())
    assert scorecard["apps"][0]["grades"]["bootable"]["status"] == PASS
    assert scorecard["gateErrors"]
    assert "GATE FAIL" in result.stdout


def test_explicit_required_corpus_does_not_hide_optional_missing_apps():
    scorecard = build_scorecard([_app()], catalog_path="catalog", sample_dir="samples",
        catalog_app_ids=["sample", "optional"], required_app_ids=["sample"])
    assert scorecard["catalogCoverage"]["missingCatalogApps"] == ["optional"]
    assert scorecard["catalogCoverage"]["missingRequiredApps"] == []
    assert scorecard["gateErrors"] == []
