"""Shared Power Fx identifier normalization.

The emitter rewrites Power Fx field names to JS-safe snake_case
(``Status`` -> ``status``, ``Sample Heading`` -> ``sample_heading``). Every
layer that reads or writes those fields (data-source schemas, Sheet headers,
collection records) must use the same convention, so it lives here.
"""
from __future__ import annotations


def snake(name: str) -> str:
    """Sanitize a Power Fx field name for JS property access:
    'File name with extension' -> file_name_with_extension, FullName -> full_name."""
    out: list[str] = []
    prev_upper = False
    for i, ch in enumerate(name):
        if ch.isupper() and i > 0 and not prev_upper:
            out.append("_")
        if ch.isalnum():
            out.append(ch.lower())
        elif out and out[-1] != "_":
            out.append("_")
        prev_upper = ch.isupper()
    return "".join(out).strip("_") or "field"


def component_symbol(owner: str, name: str) -> str:
    """An instance-local variable/collection key, independent of letter case."""
    return f'__pfx_component_{len(owner)}_{owner}_{name.casefold()}'
