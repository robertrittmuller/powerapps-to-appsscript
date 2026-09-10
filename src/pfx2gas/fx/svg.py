"""Recognize literal control text in an otherwise static SVG EncodeUrl argument.

This is a ledgered repair, not general XML/URL sanitization. Dynamic markup,
attributes, CDATA and unknown expressions retain their original semantics.
"""
from __future__ import annotations

from collections.abc import Callable
from xml.parsers import expat

from .lexer import Node


def literal_text_fragments(node: Node, is_control_text: Callable[[Node], bool]):
    fragments = []

    def flatten(part):
        if part.kind == 'binary' and part.value == '&':
            for child in part.children:
                flatten(child)
        else:
            fragments.append(part)

    flatten(node)
    if not any(part.kind != 'str' for part in fragments):
        return None
    if any(part.kind != 'str' and not is_control_text(part) for part in fragments):
        return None
    literals = ''.join(str(part.value) for part in fragments if part.kind == 'str')
    # Do not process a DTD or expand entities from an exported formula.
    if '<!DOCTYPE' in literals.upper():
        return None
    prefix = '__pfx_svg_text_'
    while prefix in literals:
        prefix += '_'
    tokens = {i: f'{prefix}{i}__' for i, part in enumerate(fragments) if part.kind != 'str'}
    scaffold = ''.join(str(part.value) if part.kind == 'str' else tokens[i]
                       for i, part in enumerate(fragments))
    parser = expat.ParserCreate(namespace_separator='}')
    stack, text, escaped = [], [], set()
    svg = 'http://www.w3.org/2000/svg}'
    cdata = False
    root = None

    def flush():
        if stack and stack[-1] in {svg + 'text', svg + 'tspan'} and not cdata:
            content = ''.join(text)
            escaped.update(i for i, token in tokens.items() if token in content)
        text.clear()

    def start(name, _attrs):
        nonlocal root
        flush()
        if root is None:
            root = name
        stack.append(name)

    def end(_name):
        flush()
        stack.pop()

    def start_cdata():
        nonlocal cdata
        flush()
        cdata = True

    def end_cdata():
        nonlocal cdata
        flush()
        cdata = False

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = text.append
    parser.StartCdataSectionHandler = start_cdata
    parser.EndCdataSectionHandler = end_cdata
    try:
        parser.Parse(scaffold, True)
    except expat.ExpatError:
        return None
    return (fragments, escaped) if root == svg + 'svg' and escaped else None
