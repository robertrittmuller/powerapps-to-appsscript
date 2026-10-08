"""Fail-closed release acceptance, independent of the development regression gate."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .benchmark import converter_fingerprint


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_manifest(path: Path) -> dict:
    manifest = json.loads(path.read_text())
    apps = manifest.get('apps')
    if manifest.get('schemaVersion') != 1 or not isinstance(apps,list) or not apps:
        raise ValueError('Acceptance manifest requires schemaVersion 1 and apps')
    def validate_files(files):
        if (not isinstance(files,list) or any(not isinstance(file,str) or not file for file in files)
                or len(set(files)) != len(files)):
            raise ValueError('Assessment dependencies must be unique file paths')
    validate_files(manifest.get('harnessFiles', []))
    ids = set()
    for app in apps:
        if not isinstance(app,dict) or not app.get('id') or app['id'] in ids:
            raise ValueError('Acceptance app IDs must be unique')
        ids.add(app['id'])
        validate_files(app.get('dependencies', []))
        if not app.get('source') or not app.get('dataSetup') or not app.get('journeys') or len(set(app['journeys'])) != len(app['journeys']):
            raise ValueError('Every acceptance app requires source, setup and unique required journeys')
        if app.get('runner') is not None and (not isinstance(app['runner'],list) or not app['runner'] or not all(isinstance(arg,str) for arg in app['runner']) or not app.get('result')):
            raise ValueError('Runner arguments and result path must be declared together')
        if 'liveChecks' in app and (not isinstance(app['liveChecks'],list) or not app['liveChecks']
                or any(not isinstance(check,str) or not check for check in app['liveChecks'])
                or len(set(app['liveChecks'])) != len(app['liveChecks'])):
            raise ValueError('Live checks must name nonempty unique assertions')
    return manifest


def assess_manifest(root: Path, manifest_path: Path, *, require_source=False, require_live=False) -> dict:
    manifest = load_manifest(manifest_path)
    fingerprint = converter_fingerprint()
    apps = []
    for spec in manifest['apps']:
        errors = []
        source = root / spec['source']
        source_hash = sha256(source) if source.is_file() else None
        if source_hash is None:
            errors.append('Required source export is missing')
        if spec.get('solution') and not (root/spec['solution']).is_file():
            errors.append('Required solution metadata is missing')
        evidence = {}
        try:
            if not spec.get('runner') or not spec.get('result'):
                raise ValueError('Required critical workflow has no executable runner')
            evidence = json.loads((root/spec['result']).read_text())
            if evidence.get('sourceAppId') != spec['id'] or evidence.get('inputSha256') != source_hash:
                errors.append('Evidence belongs to a different source export')
            if evidence.get('converterSourceSha256') != fingerprint:
                errors.append('Evidence was produced by a different converter revision')
            if evidence.get('assessmentScriptSha256') != sha256(root/spec['runner'][0]):
                errors.append('Assessment-script fingerprint is missing or stale')
            for file in [*manifest.get('harnessFiles', []), *spec.get('dependencies', [])]:
                if evidence.get('assessmentDependencySha256', {}).get(file) != sha256(root/file):
                    errors.append('Assessment dependency fingerprint is missing or stale: ' + file)
            if spec.get('solution') and (root/spec['solution']).is_file() and evidence.get('solutionSha256') != sha256(root/spec['solution']):
                errors.append('Solution-metadata fingerprint is missing or stale')
            if evidence.get('status') != 'pass' or evidence.get('consoleErrors'):
                errors.append('Executed workflow/UI checks failed')
            if evidence.get('completeUsability') != 'pass' or evidence.get('criticalJourneyCoverage') != 'complete':
                errors.append('Complete critical workflow/UI evidence is missing')
            journeys = evidence.get('criticalJourneys', [])
            if (not isinstance(journeys,list) or any(not isinstance(j,dict) or not isinstance(j.get('id'),str) for j in journeys)
                    or len({j['id'] for j in journeys}) != len(journeys)):
                raise ValueError('Critical journey evidence is malformed or duplicated')
            by_id = {j['id']: j for j in journeys}
            for journey in spec['journeys']:
                if by_id.get(journey,{}).get('status') != 'pass':
                    errors.append('Required journey did not pass: ' + journey)
            if (not isinstance(evidence.get('steps'),list) or not evidence['steps']
                    or any(not isinstance(step,dict) or step.get('status') != 'pass' for step in evidence['steps'])):
                errors.append('Individual workflow assertions are absent or failed')
        except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            errors.append(str(exc))
        for stage, required in [('sourceComparison',require_source),('liveGoogle',require_live)]:
            if required:
                try:
                    from .comparison import validate_comparison_evidence
                    proof = json.loads((root/'.artifacts/acceptance'/spec['id']/(stage+'.json')).read_text())
                    solution = root/spec['solution'] if spec.get('solution') else None
                    validate_comparison_evidence(proof, source_hash, fingerprint, live=(stage=='liveGoogle'),
                        required_journeys=spec['journeys'], required_live_checks=spec.get('liveChecks'),
                        solution_hash=sha256(solution) if solution and solution.is_file() else None)
                except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                    errors.append(f'{stage}: {exc}')
        apps.append({'id':spec['id'],'status':'fail' if errors else 'pass','errors':errors,
                     'inputSha256':source_hash,'dataSetup':spec['dataSetup']})
    return {'schemaVersion':1,'manifestSha256':sha256(manifest_path),'converterSourceSha256':fingerprint,
            'requirements':{'sourceComparison':require_source,'liveGoogle':require_live},
            'status':'pass' if all(app['status']=='pass' for app in apps) else 'fail', 'apps':apps}
