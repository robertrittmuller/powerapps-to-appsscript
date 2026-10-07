"""Compare independently captured source/target observations and reject weak evidence."""
from __future__ import annotations

import math

CONTEXT_KEYS = ('locale','timezone','viewport','dataSnapshotSha256','launchParameters','roles')


def equivalent(expected, actual, tolerance=0):
    if type(tolerance) not in (int,float) or not math.isfinite(tolerance) or tolerance < 0:
        return False
    if type(expected) is not type(actual) and not (type(expected) in (int,float) and type(actual) in (int,float)):
        return False
    if type(expected) in (int,float):
        return math.isfinite(expected) and math.isfinite(actual) and abs(expected-actual) <= tolerance
    if isinstance(expected,dict):
        return expected.keys() == actual.keys() and all(equivalent(value,actual[key],tolerance) for key,value in expected.items())
    if isinstance(expected,list):
        return len(expected) == len(actual) and all(equivalent(a,b,tolerance) for a,b in zip(expected,actual))
    return expected == actual


def compare_captures(source: dict, target: dict) -> dict:
    errors = []
    for key in ('inputSha256','capturePlanSha256'):
        if not source.get(key) or source[key] != target.get(key):
            errors.append(f'Mismatched or missing {key}')
    for key in CONTEXT_KEYS:
        if key not in source.get('context',{}) or source['context'][key] != target.get('context',{}).get(key):
            errors.append(f'Source and target contexts differ: {key}')
    if not source.get('url') or not target.get('url') or source['url']==target['url']:
        errors.append('Distinct source and target URLs are required')
    if source.get('side') != 'source' or target.get('side') != 'target':
        errors.append('Comparison requires independent source and target captures')
    if source.get('status') != 'pass' or target.get('status') != 'pass':
        errors.append('A source or target assertion failed')
    if source.get('errors') or target.get('errors'):
        errors.append('Source or target browser errors were recorded')
    source_rows = source.get('observations',[])
    target_rows = target.get('observations',[])
    if not source_rows or not target_rows:
        errors.append('Observable assertions are missing')
    source_ids = [row['id'] for row in source_rows]
    target_ids = [row['id'] for row in target_rows]
    if source_ids != target_ids or len(set(source_ids)) != len(source_ids):
        errors.append('Observation IDs are missing, reordered or duplicated')
    for a,b in zip(source_rows,target_rows):
        tolerance = a.get('tolerance',0)
        if not isinstance(tolerance,(int,float)) or not math.isfinite(tolerance) or tolerance < 0 or b.get('tolerance',0) != tolerance:
            errors.append(f'Invalid tolerance: {a.get("id")}')
        elif (a.get('status') != 'pass' or b.get('status') != 'pass' or 'expected' not in a or 'expected' not in b
              or a.get('journey') != b.get('journey') or not a.get('journey')
              or not equivalent(a['expected'],a.get('value'),tolerance)
              or not equivalent(b['expected'],b.get('value'),tolerance)
              or not equivalent(a['expected'],b['expected'],tolerance)
              or not equivalent(a.get('value'),b.get('value'),tolerance)):
            errors.append(f'Observation differs: {a.get("id")}')
    return {'schemaVersion':1,'kind':'source-target','status':'fail' if errors else 'pass','errors':errors,
            'scope':'declared workflow observations and UI assertions; screenshots retained for visual review',
            'inputSha256':target.get('inputSha256'),'converterSourceSha256':target.get('converterSourceSha256'),
            'capturePlanSha256':target.get('capturePlanSha256'),'source':source,'target':target,
            'journeys':target.get('journeys',[])}


def validate_comparison_evidence(proof, input_hash, converter_hash, *, live=False, required_journeys=(), required_live_checks=None, solution_hash=None):
    if proof.get('schemaVersion') != 1 or proof.get('inputSha256') != input_hash or proof.get('converterSourceSha256') != converter_hash:
        raise ValueError('Source/converter fingerprint is missing or stale')
    if proof.get('kind') != ('live-google' if live else 'source-target') or proof.get('status') != 'pass':
        raise ValueError('Required evidence did not pass')
    if solution_hash and any(proof.get(side,{}).get('solutionSha256') != solution_hash for side in (['target'] if live else ['source','target'])):
        raise ValueError('Solution metadata is missing or stale')
    if not live:
        fresh = compare_captures(proof['source'],proof['target'])
        if fresh['status'] != 'pass' or fresh['inputSha256'] != input_hash or fresh['converterSourceSha256'] != converter_hash or proof.get('journeys') != fresh['journeys']:
            raise ValueError('Independent source/target observations did not match')
    else:
        from urllib.parse import urlparse
        target = proof['target']
        url = urlparse(target.get('url',''))
        if url.scheme != 'https' or url.hostname != 'script.google.com' or not url.path.endswith('/exec'):
            raise ValueError('A deployed Apps Script URL is required')
        if not proof.get('deploymentVersion') or proof.get('usesMocks') is not False:
            raise ValueError('Live deployment version and non-mocked service evidence are required')
        required_live_checks = required_live_checks if required_live_checks is not None else ('authorization','persistence','failureRecovery','concurrentEdits')
        if {'authorization','concurrentEdits'} & set(required_live_checks) and len(set(target.get('context',{}).get('roles',[]))) < 2:
            raise ValueError('Live authorization requires at least two declared user roles')
        if target.get('inputSha256') != input_hash or target.get('converterSourceSha256') != converter_hash:
            raise ValueError('Live capture belongs to a different source/converter')
        checks = {row['id']:row for row in target.get('observations',[])}
        if len(checks) != len(target.get('observations',[])):
            raise ValueError('Duplicate live observations')
        for check in required_live_checks:
            row = checks.get(check,{})
            if row.get('status') != 'pass' or 'expected' not in row or not equivalent(row['expected'],row.get('value'),row.get('tolerance',0)):
                raise ValueError('Missing live assertion: ' + check)
        if (target.get('status') != 'pass' or target.get('errors') or proof.get('journeys') != target.get('journeys')
                or any(row.get('status') != 'pass' or 'expected' not in row
                       or not equivalent(row['expected'], row.get('value'),row.get('tolerance',0)) for row in checks.values())):
            raise ValueError('Live browser capture failed')
    observed = proof.get('journeys',[])
    if not observed or len(set(observed)) != len(observed) or not set(required_journeys) <= set(observed):
        raise ValueError('Required critical journeys were not captured')
    if not set(required_journeys) <= {row.get('journey') for row in proof['target'].get('observations',[])}:
        raise ValueError('Critical journeys have no observed assertions')
