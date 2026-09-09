"""Stage 1: unpack a .msapp file (a ZIP of pa.yaml sources + metadata).

Real .msapp archives vary: entry names may use backslashes, the source folder
may be ``src`` or ``Src``, the manifest may be ``CanvasManifest.json`` (packed
form) or ``Header.json``/``Properties.json`` (Studio download form), and
auxiliary files like ``_EditorState.pa.yaml`` live alongside real screens.
This module normalizes all of that.
"""
from __future__ import annotations

import base64
import json
import math
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml


class UnpackError(Exception):
    pass


@dataclass
class UnpackedApp:
    app_name: str
    layout: dict = field(default_factory=dict)
    app_yaml: dict = field(default_factory=dict)
    screens: dict[str, dict] = field(default_factory=dict)  # name -> yaml dict
    data_sources: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    media_resources: dict[str, str] = field(default_factory=dict)
    # Screen names in the app's own order (first one is the start screen).
    # Legacy: TopParent.Index; modern: archive entry order / ScreenOrder.
    screen_order: list[str] = field(default_factory=list)


_IMAGE_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}
_MAX_EMBEDDED_IMAGE_BYTES = 1_500_000


def _extract_media_resources(
    text_entries: dict[str, str], raw_entries: dict[str, bytes], warnings: list[str]
) -> dict[str, str]:
    """Return safe local image resources as data URIs.

    Legacy exports often carry an already-expired ``RootPath`` URL alongside
    the real file under ``Assets/Images``.  Resolve the packaged path instead.
    SVG is deliberately not embedded here because arbitrary SVG can contain
    active content; dynamic SVG formulas continue through the existing image
    binding and sanitizer path.
    """
    lookup = {name.lower(): name for name in text_entries}
    refs_name = lookup.get("references/resources.json")
    if not refs_name:
        return {}
    try:
        resources = json.loads(text_entries[refs_name]).get("Resources", [])
    except (json.JSONDecodeError, AttributeError):
        warnings.append("unparseable media resource manifest: References/Resources.json")
        return {}

    raw_lookup = {name.lower(): name for name in raw_entries}
    out: dict[str, str] = {}
    for resource in resources:
        if not isinstance(resource, dict) or resource.get("ResourceKind") != "LocalFile":
            continue
        name = str(resource.get("Name") or "")
        resource_path = str(resource.get("Path") or resource.get("FileName") or "")
        normalized = resource_path.replace("\\", "/").lstrip("/")
        actual = raw_lookup.get(normalized.lower())
        if not actual and resource.get("FileName"):
            filename = str(resource["FileName"]).replace("\\", "/").rsplit("/", 1)[-1]
            matches = [entry for key, entry in raw_lookup.items() if key.endswith("/" + filename.lower())]
            actual = matches[0] if len(matches) == 1 else None
        suffix = Path(normalized).suffix.lower()
        mime = _IMAGE_MIME_TYPES.get(suffix)
        if not name or not actual or not mime:
            warnings.append(f"packaged media resource not embedded: {name or resource_path}")
            continue
        payload = raw_entries[actual]
        if len(payload) > _MAX_EMBEDDED_IMAGE_BYTES:
            warnings.append(
                f"packaged media resource exceeds {_MAX_EMBEDDED_IMAGE_BYTES} bytes: {name}"
            )
            continue
        encoded = base64.b64encode(payload).decode("ascii")
        out[name] = f"data:{mime};base64,{encoded}"
    return out


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
            raw_entries: dict[str, bytes] = {}
            for name in zf.namelist():
                norm = name.replace("\\", "/")
                if norm.endswith("/"):
                    continue
                try:
                    payload = zf.read(name)
                    raw_entries[norm] = payload
                    entries[norm] = payload.decode("utf-8", errors="replace")
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

    # Preserve only layout metadata; connection/author identifiers are not
    # needed by the generated page. Both source formats use these settings.
    layout = {}
    layout_keys = {
        "DocumentLayoutWidth": "designWidth", "DocumentLayoutHeight": "designHeight",
        "DocumentLayoutScaleToFit": "scaleToFit",
        "DocumentLayoutMaintainAspectRatio": "lockAspectRatio",
        "DocumentLayoutLockOrientation": "lockOrientation",
        "DocumentLayoutOrientation": "orientation",
    }
    for metadata_name in ("CanvasManifest.json", "Properties.json"):
        try:
            metadata = json.loads(read(metadata_name) or "{}")
            if not isinstance(metadata, dict):
                continue
            for original, key in layout_keys.items():
                if original in metadata:
                    value = metadata[original]
                    if key in {"designWidth", "designHeight"}:
                        valid = type(value) in {int, float} and math.isfinite(value) and value > 0
                    elif key == "orientation":
                        valid = isinstance(value, str) and value.lower() in {"portrait", "landscape"}
                    else:
                        valid = isinstance(value, bool)
                    if not valid:
                        raise UnpackError(f"invalid canvas layout setting: {original}")
                    layout[key] = value
        except (json.JSONDecodeError, TypeError):
            pass

    # --- source files: any .pa.yaml under a src/ folder (any casing) ---
    def is_src(n: str) -> bool:
        parts = n.lower().split("/")
        return "src" in parts and n.lower().endswith(".pa.yaml")

    src_files = sorted(n for n in entries if is_src(n))
    # Archive entry order = screen creation order (Power Apps shows the first
    # screen); used when no explicit ScreenOrder metadata exists.
    archive_screen_order = [
        n.rsplit("/", 1)[-1].removesuffix(".pa.yaml")
        for n in entries if is_src(n)
    ]
    if not src_files:
        has_legacy = any(n.lower().replace("\\", "/").startswith("controls/")
                         and n.lower().endswith(".json") for n in entries)
        if has_legacy:
            from .legacy import convert_legacy_msapp
            try:
                legacy = convert_legacy_msapp(path)
            except ValueError as exc:
                raise UnpackError(f"legacy .msapp unreadable: {exc}") from exc
            legacy["media_resources"] = _extract_media_resources(
                entries, raw_entries, legacy["warnings"]
            )
            legacy["layout"] = layout
            return UnpackedApp(**legacy)
        if any(n.lower().endswith(".fx.yaml") for n in entries):
            raise UnpackError(
                "this .msapp only contains retired *.fx.yaml sources. "
                "Open it in Power Apps Studio, save, and download a fresh copy to upgrade to pa.yaml."
            )
        raise UnpackError("no src/*.pa.yaml files found in the .msapp archive")

    out = UnpackedApp(app_name=str(app_name), layout=layout)
    out.media_resources = _extract_media_resources(entries, raw_entries, out.warnings)
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

    # Screen order: explicit CanvasManifest.ScreenOrder wins; else archive order.
    order: list[str] = []
    manifest_raw = read("CanvasManifest.json")
    if manifest_raw:
        try:
            so = json.loads(manifest_raw).get("ScreenOrder")
            if isinstance(so, list):
                order = [str(s) for s in so]
        except json.JSONDecodeError:
            pass
    if not order:
        order = archive_screen_order
    out.screen_order = [s for s in order if s in out.screens]
    return out
