"""Power Apps icon names -> portable Unicode glyph characters.

Power Apps stores Material/Fluent icon *names* in Image/Icon properties
(``'customer-service'``, ``Icon.EmojiSmile``, ...). Browsers cannot resolve a
bare name as an image URL (404 noise, missing icon). The converter renders
known names as standard Unicode symbols that render on Windows, macOS, and
Linux; unknown names keep the legacy behavior and are reported).
"""
from __future__ import annotations

import re

# name (lowercase, hyphens/scores stripped) -> Unicode codepoint
_ICON_GLYPHS = {
    "customerservice": 0x260E,       # ☎
    "settings": 0x2699,              # ⚙
    "gear": 0x2699,                  # ⚙
    "filter": 0x25BD,                # ▽
    "smile": 0x263A,                 # ☺
    "emojismile": 0x263A,            # ☺
    "search": 0x2315,                # ⌕
    "home": 0x2302,                  # ⌂
    "add": 0xFF0B,                   # ＋
    "plus": 0xFF0B,                  # ＋
    "delete": 0x2715,                # ✕
    "trash": 0x2715,                 # ✕
    "edit": 0x270E,                  # ✎
    "pencil": 0x270E,                # ✎
    "save": 0x2713,                  # ✓
    "back": 0x2190,                  # ←
    "arrowback": 0x2190,             # ←
    "chevronright": 0x276F,          # ❯
    "chevronleft": 0x276E,           # ❮
    "chevronup": 0x2303,             # ⌃
    "chevrondown": 0x2304,           # ⌄
    "nextarrow": 0x276F,             # ❯
    "close": 0x00D7,                 # ×
    "cancel": 0x00D7,                # ×
    "x": 0x00D7,                     # ×
    "checkmark": 0x2713,             # ✓
    "check": 0x2713,                 # ✓
    "refresh": 0x21BB,               # ↻
    "sync": 0x21BA,                  # ↺
    "mail": 0x2709,                  # ✉
    "email": 0x2709,                 # ✉
    "person": 0x25C9,                # ◉
    "contact": 0x25C9,               # ◉
    "heart": 0x2665,                 # ♥
    "starred": 0x2605,               # ★
    "document": 0x25A4,              # ▤
    "file": 0x25A4,                  # ▤
    "adddocument": 0xFF0B,          # ＋
    "documentwithcontent": 0x25A4, # ▤
    "detaillist": 0x2637,           # ☷
    "trending": 0x2197,             # ↗
    "sort": 0x21C5,                 # ⇅
    "reload": 0x21BB,               # ↻
    "cancelbadge": 0x2297,          # ⊗
    "folder": 0x25F0,                # ◰
    "download": 0x21E9,              # ⇩
    "info": 0x24D8,                  # ⓘ
    "warning": 0x26A0,               # ⚠
    "error": 0x2298,                 # ⊘
    "calendar": 0x25A3,              # ▣
    "clock": 0x25F7,                 # ◷
    "location": 0x2316,              # ⌖
    "pin": 0x2316,                   # ⌖
    "phone": 0x260E,                 # ☎
    "list": 0x2637,                  # ☷
    "lightbulb": 0x2600,             # ☀
    "lock": 0x2299,                  # ⊙
    "unlock": 0x25CB,                # ○
    "flag": 0x2691,                  # ⚑
    "play": 0x25B6,                  # ▶
    "pause": 0x2016,                 # ‖
    "attach": 0x26D3,                # ⛓
    "share": 0x2197,                 # ↗
    "help": 0x003F,                  # ?
    "question": 0x003F,              # ?
    "comment": 0x25CC,               # ◌
    "tag": 0x25C6,                   # ◆
    "print": 0x25A3,                 # ▣
    "camera": 0x25C9,                # ◉
    "zoomin": 0x2295,                # ⊕
    "zoomout": 0x2296,               # ⊖
    "griddots": 0x25A6,              # ▦
    "appslist": 0x2637,              # ☷
    "history": 0x21BA,               # ↺
    "arrowexit": 0x21AA,             # ↪
    "globe": 0x1F310,               # 🌐
}


def _normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.strip().lower())


def icon_map() -> dict[str,str]:
    """Share the deterministic portable glyph map with dynamic button bindings."""
    return {name:chr(codepoint) for name,codepoint in _ICON_GLYPHS.items()}


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
