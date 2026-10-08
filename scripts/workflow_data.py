"""Explicitly authored migration snapshots shared by browser assessments."""
import hashlib
import json

from browser_check import REPO


def user_records(*identities):
    fixture = json.loads((REPO/'tests/fixtures/business-users.json').read_text())
    records = [{**fixture['common'], **user} for user in fixture['users']
               if user['systemuserid'] in identities]
    assert {record['systemuserid'] for record in records} == set(identities)
    return records


def import_rows(backend, source, records):
    result = backend({'fn':'__importRows', 'args':[source,records]})
    assert result == {'result':{'ok':True, 'source':source, 'rows':len(records)}}, result


def migration_evidence(records):
    return {'kind':'synthetic-migration-records', 'records':records,
            'sha256':hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest(),
            'limitations':['Authored test snapshots, not source tenant data; native computed values, licensing and security roles remain unverified.']}
