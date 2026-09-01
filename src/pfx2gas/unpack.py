"""Stage 1: unpack a .msapp file (a ZIP of pa.yaml sources + metadata)."""
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
    data = yaml.safe_load(text)
    return data if isinstance(data, dict) else {}


def unpack(msapp_path: str | Path) -> UnpackedApp:
    path = Path(msapp_path)
    if not path.exists():
        raise UnpackError(f"file not found: {path}")
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()

            def read(n: str) -> str:
                return zf.read(n).decode("utf-8")

            manifest: dict = {}
            if "CanvasManifest.json" in names:
                try:
                    manifest = json.loads(read("CanvasManifest.json"))
                except json.JSONDecodeError:
                    pass
            app_name = manifest.get("Name") or path.stem

            src_files = [n for n in names if n.startswith("src/") and n.endswith(".pa.yaml")]
            if not src_files:
                legacy = [n for n in names if n.endswith(".fx.yaml")]
                if legacy:
                    raise UnpackError(
                        "this .msapp only contains retired *.fx.yaml sources. "
                        "Open it in Power Apps Studio, save, and download a fresh copy to upgrade to pa.yaml."
                    )
                raise UnpackError("no src/*.pa.yaml files found in the .msapp archive")

            out = UnpackedApp(app_name=str(app_name))
            for name in src_files:
                rel = name[len("src/"):]
                data = _load_yaml(read(name))
                if rel == "App.pa.yaml":
                    out.app_yaml = data
                else:
                    screen_name = rel.removesuffix(".pa.yaml")
                    out.screens[screen_name] = data

            for name in names:
                if name.startswith("DataSources/") and name.endswith(".json"):
                    try:
                        ds = json.loads(read(name))
                        if isinstance(ds, dict) and ds.get("Name"):
                            out.data_sources.append(ds)
                    except json.JSONDecodeError:
                        out.warnings.append(f"unparseable data source file: {name}")
    except zipfile.BadZipFile as exc:
        raise UnpackError(f"{path.name} is not a valid .msapp (ZIP) archive") from exc

    if any(n.startswith("Connections/") for n in names):
        out.warnings.append("connection metadata present; data source credentials are NOT migrated")
    return out
