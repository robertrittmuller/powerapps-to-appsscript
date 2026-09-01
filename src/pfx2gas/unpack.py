"""Stage 1: unpack a .msapp file (a ZIP of pa.yaml sources + metadata).

Real .msapp archives vary: entry names may use backslashes, the source folder
may be ``src`` or ``Src``, the manifest may be ``CanvasManifest.json`` (packed
form) or ``Header.json``/``Properties.json`` (Studio download form), and
auxiliary files like ``_EditorState.pa.yaml`` live alongside real screens.
This module normalizes all of that.
"""
from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class UnpackError(Exception):
    pass


@dataclass
class UnpackedApp:
    app_name: str
    app_yaml: dict = field(default_factory=dict)
    screens: dict[str, dict] = field(default_factory=dict)  # name -> yaml dict
    data_sources: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _load_yaml(text: str) -> dict:
    """Parse pa.yaml tolerantly.

    Real Studio exports contain bare ``=`` scalars (empty formulas), which
    YAML 1.1 treats as the special ``value`` tag; map it to the literal string.
    """
    class PaYamlLoader(yaml.SafeLoader):
        pass

    PaYamlLoader.add_constructor("tag:yaml.org,2002:value", lambda loader, node: "=")
    try:
        data = yaml.load(text, Loader=PaYamlLoader)
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def unpack(msapp_path: str | Path) -> UnpackedApp:
    path = Path(msapp_path)
    if not path.exists():
        raise UnpackError(f"file not found: {path}")
    try:
        with zipfile.ZipFile(path) as zf:
            # Normalize: forward slashes, drop directory entries.
            entries: dict[str, str] = {}
            for name in zf.namelist():
                norm = name.replace("\\", "/")
                if norm.endswith("/"):
                    continue
                try:
                    entries[norm] = zf.read(name).decode("utf-8", errors="replace")
                except (KeyError, zipfile.BadZipFile):
                    continue
    except zipfile.BadZipFile as exc:
        raise UnpackError(f"{path.name} is not a valid .msapp (ZIP) archive") from exc

    lower_map = {n.lower(): n for n in entries}

    def read(name: str) -> str | None:
        actual = lower_map.get(name.lower())
        return entries[actual] if actual else None

    # --- app name: CanvasManifest.json (packed) or Properties.json (Studio) ---
    app_name: str | None = None
    for manifest_name in ("CanvasManifest.json", "Properties.json"):
        raw = read(manifest_name)
        if raw:
            try:
                app_name = json.loads(raw).get("Name")
            except (json.JSONDecodeError, AttributeError):
                pass
            if app_name:
                break
    app_name = app_name or path.stem

    # --- source files: any .pa.yaml under a src/ folder (any casing) ---
    def is_src(n: str) -> bool:
        parts = n.lower().split("/")
        return "src" in parts and n.lower().endswith(".pa.yaml")

    src_files = sorted(n for n in entries if is_src(n))
    if not src_files:
        has_legacy = any(n.lower().replace("\\", "/").startswith("controls/")
                         and n.lower().endswith(".json") for n in entries)
        if has_legacy:
            from .legacy import convert_legacy_msapp
            try:
                legacy = convert_legacy_msapp(path)
            except ValueError as exc:
                raise UnpackError(f"legacy .msapp unreadable: {exc}") from exc
            legacy["warnings"].extend(
                [f"skipped auxiliary source file: {w}" for w in []])
            return UnpackedApp(**legacy)
        if any(n.lower().endswith(".fx.yaml") for n in entries):
            raise UnpackError(
                "this .msapp only contains retired *.fx.yaml sources. "
                "Open it in Power Apps Studio, save, and download a fresh copy to upgrade to pa.yaml."
            )
        raise UnpackError("no src/*.pa.yaml files found in the .msapp archive")

    out = UnpackedApp(app_name=str(app_name))
    for name in src_files:
        base = name.rsplit("/", 1)[-1]
        if base.startswith("_"):  # _EditorState.pa.yaml etc. are auxiliary
            out.warnings.append(f"skipped auxiliary source file: {name}")
            continue
        data = _load_yaml(entries[name])
        if base.lower() == "app.pa.yaml":
            out.app_yaml = data
        else:
            out.screens[base.removesuffix(".pa.yaml")] = data

    # --- data sources + connection warnings ---
    for name, content in entries.items():
        parts = name.lower().split("/")
        if len(parts) >= 2 and parts[-2] == "datasources" and parts[-1].endswith(".json"):
            try:
                ds = json.loads(content)
                if isinstance(ds, dict) and ds.get("Name"):
                    out.data_sources.append(ds)
            except json.JSONDecodeError:
                out.warnings.append(f"unparseable data source file: {name}")

    if any("connections/" in f"/{n.lower()}" for n in entries):
        out.warnings.append("connection metadata present; data source credentials are NOT migrated")

    if not out.screens and not out.app_yaml:
        raise UnpackError("pa.yaml sources found but none contained parseable app/screen definitions")
    return out
