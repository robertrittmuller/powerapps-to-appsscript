"""Reproduce the Microsoft acceptance baseline, retaining failures as failures.

Run: ./pfx2gas browser scripts/assess_microsoft_samples.py
This is deliberately separate from the established regression corpus until its
blocking startup/connector gaps are fixed; it does not imply usable conversion.
"""
import os
import json
from collections import Counter
import subprocess
import sys

from fetch_microsoft_samples import REPO, main as fetch_samples
from pfx2gas.benchmark import evaluate_grades, gate_errors, write_scorecard


def merge_first_actions(scorecard, probes):
    """A failed first action fails usability; a pass cannot prove full coverage."""
    by_id = {app['id']: app for app in scorecard['apps']}
    for probe in probes:
        app = by_id[probe['sourceAppId']]
        if (probe['inputSha256'] != app['inputSha256'] or
                probe['converterSourceSha256'] != scorecard['converterSourceSha256']):
            raise ValueError('browser evidence does not match the source/converter hashes')
        if probe['status'] not in {'pass', 'fail'}:
            raise ValueError('browser probe must report pass or fail')
        journeys = app['evidence'].setdefault('journeys', [])
        journeys[:] = [journey for journey in journeys if journey['id'] != 'browser-first-action']
        journeys.append({
            'id': 'browser-first-action', 'description': probe['assessmentScope'],
            'required': True, 'status': 'fail' if probe.get('consoleErrors') else probe['status'],
            'error': probe.get('error'), 'steps': probe['steps'],
            'consoleErrors': probe.get('consoleErrors', []),
            'evidenceType': probe['evidenceType'],
            'inputSha256': probe['inputSha256'],
            'converterSourceSha256': probe['converterSourceSha256'],
            'artifact': '.artifacts/browser/' + probe['app'] + '/result.json',
        })
    for app in scorecard['apps']:
        app['grades'] = evaluate_grades(app)
    for grade in ('bootable', 'usable', 'highFidelity'):
        counts = Counter(app['grades'][grade]['status'] for app in scorecard['apps'])
        scorecard['summary']['grades'][grade] = {status: counts[status] for status in ('pass', 'fail', 'unassessed')}
    scorecard['evidenceType'] = 'generated-runtime-simulator-and-chromium-first-actions'
    scorecard['gateErrors'] = gate_errors(scorecard)
    return scorecard


if __name__ == "__main__":
    fetch_samples()
    baseline = subprocess.run(
        [sys.executable, str(REPO / "scripts/soak_check.py")],
        env={**os.environ, "PFX2GAS_SAMPLES_DIR": str(REPO / "samples/microsoft"),
             "PFX2GAS_SOAK_OUT": str(REPO / ".artifacts/microsoft/benchmark"),
             "PFX2GAS_BENCHMARK_CATALOG": str(REPO / "benchmark/microsoft-apps.json")},
    ).returncode
    probes_path = REPO / '.artifacts/microsoft/first-actions.json'
    probes_path.unlink(missing_ok=True)
    workflows = subprocess.run(
        [sys.executable, str(REPO / 'scripts/assess_microsoft_workflows.py')],
    ).returncode
    scorecard_dir = REPO / '.artifacts/microsoft/benchmark'
    probes = json.loads(probes_path.read_text())
    if {probe['sourceAppId'] for probe in probes} != {'milestones', 'employee-ideas', 'inspection'} or len(probes) != 3:
        raise ValueError('Microsoft first-action assessment did not report every required probe')
    scorecard = merge_first_actions(json.loads((scorecard_dir / 'benchmark-scorecard.json').read_text()), probes)
    write_scorecard(scorecard, scorecard_dir)
    raise SystemExit(int(bool(baseline or workflows)))
