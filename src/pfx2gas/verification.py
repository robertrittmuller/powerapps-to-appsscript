"""Generated-server/startup evidence, kept separate from workflow acceptance."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def project_fingerprint(directory: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(directory.iterdir()):
        if file.suffix in {'.gs', '.html'} or file.name in {'appsscript.json', 'source-inventory.json', 'data-contract.json'}:
            digest.update(file.name.encode() + b'\0' + file.read_bytes())
    return digest.hexdigest()


def verify_startup(directory: str | Path) -> dict:
    from .ir import AppIR
    from .fx import lexer as lx
    from .server_sim import simulate_server
    from .startup_sim import simulate_project
    out = Path(directory)
    evidence = {'schemaVersion': 1, 'evidenceType': 'generated-runtime-simulator',
                'projectSha256': project_fingerprint(out), 'startup': 'unassessed',
                'workflows': 'unassessed', 'sourceComparison': 'unassessed', 'liveGoogle': 'unassessed'}
    try:
        ir = AppIR.model_validate_json((out / 'source-inventory.json').read_text())
        expected = ir.start_screen or (ir.screens[0].name if ir.screens else None)
        start = ir.properties.get('StartScreen')
        if start and start.raw:
            roots = lx.parse_formula(start.raw)
            node = roots[0] if len(roots) == 1 else None
            if node and node.kind == 'ident' and node.value in {s.name for s in ir.screens}:
                expected = node.value
            elif not (node and ((node.kind == 'call' and node.value == 'Blank') or (node.kind == 'str' and not node.value))):
                expected = None
        server = simulate_server(out)
        runtime = simulate_project(out)
        evidence.update(server=server, runtime=runtime, expectedScreen=expected)
        errors = list(server.get('errors', [])) + runtime.get('allConsoleErrors', runtime.get('consoleErrors', [])) + runtime.get('refErrors', [])
        if expected and runtime['visible'] != [expected]:
            errors.append(f'Expected start screen {expected}; visible {runtime["visible"]}')
        evidence['errors'] = errors
        evidence['startup'] = 'fail' if errors else ('pass' if expected else 'unassessed')
        if expected is None:
            evidence['reason'] = 'Dynamic StartScreen requires source-backed launch/user/data expectations'
    except Exception as exc:
        evidence.update(startup='fail', errors=[str(exc)])
    (out / 'verification.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return evidence
