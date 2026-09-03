"""Power Apps icon names -> Unicode glyph characters (Segoe MDL2/Fluent).

Power Apps stores Material/Fluent icon *names* in Image/Icon properties
(``'customer-service'``, ``Icon.EmojiSmile``, ...). Browsers cannot resolve a
bare name as an image URL (404 noise, missing icon). The converter renders
known names as their Unicode glyph character (styled via font-family Segoe
MDL2 Assets, which ships with Windows and is commonly available; unknown
names keep the legacy behavior and are reported).
"""
from __future__ import annotations

import re

# name (lowercase, hyphens/scores stripped) -> Unicode codepoint
_ICON_GLYPHS = {
    "customerservice": 0xE778,
    "settings": 0xE713,
    "gear": 0xE713,
    "filter": 0xE71C,
    "smile": 0xE76E,
    "emojismile": 0xE76E,
    "search": 0xE721,
    "home": 0xE80F,
    "add": 0xE710,
    "plus": 0xE710,
    "delete": 0xE74D,
    "trash": 0xE74D,
    "edit": 0xE70F,
    "pencil": 0xE70F,
    "save": 0xE74E,
    "back": 0xE72B,
    "arrowback": 0xE72B,
    "chevronright": 0xE76C,
    "chevronleft": 0xE76B,
    "chevronup": 0xE70E,
    "chevrondown": 0xE70D,
    "nextarrow": 0xE76C,
    "close": 0xE711,
    "cancel": 0xE711,
    "x": 0xE711,
    "checkmark": 0xE73E,
    "check": 0xE73E,
    "refresh": 0xE72C,
    "sync": 0xE895,
    "mail": 0xE715,
    "email": 0xE715,
    "person": 0xE77B,
    "contact": 0xE77B,
    "heart": 0xEB51,
    "starred": 0xE735,
    "document": 0xE8A5,
    "file": 0xE8A5,
    "folder": 0xE8B7,
    "download": 0xE896,
    "info": 0xE946,
    "warning": 0xE7BA,
    "error": 0xE783,
    "calendar": 0xE787,
    "clock": 0xE823,
    "location": 0xE81D,
    "pin": 0xE718,
    "phone": 0xE717,
    "list": 0xE8FD,
    "lightbulb": 0xEA61,
    "lock": 0xE72E,
    "unlock": 0xE72F,
    "flag": 0xE7C1,
    "play": 0xE768,
    "pause": 0xE769,
    "attach": 0xE723,
    "share": 0xE72D,
    "help": 0xE897,
    "question": 0xE897,
    "comment": 0xE90A,
    "tag": 0xE8EC,
    "print": 0xE749,
    "camera": 0xE722,
    "zoomin": 0xE8A3,
    "zoomout": 0xE71F,
}


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.strip().lower())


def icon_glyph(name: str) -> str | None:
    """Unicode glyph character for a Power Apps icon name, or None if unknown.

    Accepts bare names (``customer-service``), enum forms (``Icon.Filter``),
    and display forms (``EmojiSmile``).
    """
    if not name:
        return None
    n = _normalize(name)
    if n.startswith("icon"):
        n = n[4:]
    cp = _ICON_GLYPHS.get(n)
    return chr(cp) if cp is not None else None


def is_icon_name(value: str) -> bool:
    """True when a static Image/Icon value is an icon name rather than a URL,
    data URI, or path. Names are lowercase kebab-case words without dots,
    slashes, or extensions."""
    if not value or len(value) > 40:
        return False
    if value.startswith(("http://", "https://", "data:", "/", "blob:")):
        return False
    if "." in value:  # has an extension like .png/.svg
        return False
    return icon_glyph(value) is not None
