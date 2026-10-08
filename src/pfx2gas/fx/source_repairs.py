"""Explicit, fingerprinted repairs of defects in retained upstream formulas.

These are behavioral deviations, never proof of source equivalence. Original
formula bytes stay in the IR/ledger; only the parsed emission tree is changed.
"""
from __future__ import annotations

import hashlib

from . import lexer as lx


EMPLOYEE_VOTE_HASHES = frozenset({
    # Release 44: desktop/mobile gallery icon, gallery button, detail controls.
    '637297bc86d6dd71d6671d3be5ec9201e748dcdb7413d8f26d0e2f636e646541',
    '6ff27d6d1b26d7263b1eb778fb930774267be29e7bd3e6bdd3b92e571a4fc8bd',
    '4fb28ebf2df2bb4d5511b91deaeb9716230c5bcfb1156ba7b5c1ff49e6caf145',
})
VOTE_REPAIR_ID = 'microsoft-employee-ideas-release44-voting'
VOTE_REPAIR_NOTE = (
    'Intentional source repair: Microsoft Employee Ideas release 44 votes now '
    'Relate or Unrelate exclusively according to the updated local vote state; '
    'the original Concurrent unconditionally removed voter membership. '
    'Original formula retained; voting-count concurrency and cross-user '
    'lost-update risks remain unverified'
)


def repair_metadata(raw: str) -> list[dict]:
    digest = hashlib.sha256(raw.encode()).hexdigest()
    if digest not in EMPLOYEE_VOTE_HASHES:
        return []
    return [{
        'id': VOTE_REPAIR_ID,
        'sourceFormulaSha256': digest,
        'source': 'https://github.com/microsoft/teams-powerapps-app-templates/releases/tag/44',
        'deviation': VOTE_REPAIR_NOTE,
    }]


def apply_source_repairs(raw: str, statements: list[lx.Node], behavior: bool) -> list[dict]:
    repairs = repair_metadata(raw)
    if not repairs:
        return []
    # The exact source hash authorizes this one repair. Also guard the parser
    # shape: parser drift must fail visibly rather than change a different node.
    candidates = [node for node in statements if node.kind == 'call' and node.value == 'Concurrent']
    if not behavior or len(candidates) != 1 or len(candidates[0].children) != 3:
        raise lx.FxSyntaxError('Known voting source repair no longer matches the parsed behavior')
    concurrent = candidates[0]
    branch, unlink, count = concurrent.children
    if (branch.kind != 'call' or branch.value != 'If' or len(branch.children) != 2
            or unlink.kind != 'call' or unlink.value != 'Unrelate' or len(unlink.children) != 2
            or branch.children[1].kind != 'call' or branch.children[1].value != 'Relate'
            or branch.children[1].children != unlink.children
            or count.kind != 'call' or count.value not in {'Patch', 'With'}):
        raise lx.FxSyntaxError('Known voting source repair no longer matches the relationship branches')
    branch.children.append(unlink)
    concurrent.children.pop(1)
    return repairs


def validate_source_repairs(raw: str, repairs: list[dict]) -> None:
    """Bug-class gate: a source deviation cannot be erased from both artifacts."""
    if repairs != repair_metadata(raw):
        raise ValueError('source repair metadata differs from the original formula fingerprint')
