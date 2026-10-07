"""Run with ./pfx2gas browser scripts/acceptance_check.py [--run]."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from pfx2gas.acceptance import assess_manifest, load_manifest

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',default='benchmark/acceptance.json')
    parser.add_argument('--run',action='store_true',help='Fetch pinned sources and execute all declared assessments')
    parser.add_argument('--require-source-comparison',action='store_true')
    parser.add_argument('--require-live-google',action='store_true')
    args = parser.parse_args(argv)
    path = ROOT/args.manifest
    manifest = load_manifest(path)
    executions = []
    if args.run:
        commands = [(command,False,None) for command in manifest.get('setupCommands',[]) + manifest.get('baselineCommands',[])]
        commands += [(app['runner'],True,app['result']) for app in manifest['apps'] if app.get('runner')]
        for command,required,result in commands:
            if result:
                (ROOT/result).unlink(missing_ok=True)  # Never reuse old evidence after a crashed runner.
            try:
                status = subprocess.run([sys.executable,*command],cwd=ROOT,timeout=1800).returncode
                executions.append({'command':command,'exitCode':status,'required':required})
            except (OSError,subprocess.TimeoutExpired) as exc:
                executions.append({'command':command,'exitCode':1,'required':required,'error':str(exc)})
    result = assess_manifest(ROOT,path,require_source=args.require_source_comparison,require_live=args.require_live_google)
    result['executions'] = executions
    if any(execution['required'] and execution['exitCode'] for execution in executions):
        result['status'] = 'fail'
    output = ROOT/'.artifacts/acceptance'
    output.mkdir(parents=True,exist_ok=True)
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    for app in result['apps']:
        print(app['id'] + ': ' + app['status'] + (' — ' + '; '.join(app['errors']) if app['errors'] else ''))
    return int(result['status'] != 'pass')


if __name__ == '__main__':
    raise SystemExit(main())
