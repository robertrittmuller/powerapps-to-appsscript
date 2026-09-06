"""Fetch the pinned Microsoft business-app release for conversion assessment.

Packages stay in gitignored .artifacts; the published checksum is verified even
on cache hits. No Microsoft environment is provisioned or modified.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import subprocess
import urllib.request
import zipfile

REPO = Path(__file__).resolve().parent.parent
URL = "https://github.com/microsoft/teams-powerapps-app-templates/releases/download/44/AppPackages.zip"
SHA256 = "40cea1a23ee4e72e06886951514bc71071b933d5066038aa99c873679f2540c7"
APPS = {
    "Milestones": ("MSFT_Milestones_managed.zip", {
        "msft_milestones_5daaa": "milestones",
    }),
    "EmployeeIdeas": ("MSFT_EmployeeIdeas_managed.zip", {
        "msft_employeeideas_955d7": "employee-ideas",
        "msft_employeeideasmanager_f172c": "employee-ideas-manager",
    }),
    "Inspection": ("MSFT_AreaInspection_managed.zip", {
        "msft_areainspection_9036a": "inspection",
        "msft_areainspectionmanager_a6427": "inspection-manager",
        "msft_reviewinspections_1dd45": "review-inspections",
    }),
}


def main() -> int:
    output = REPO / ".artifacts/microsoft"
    output.mkdir(parents=True, exist_ok=True)
    cached = output / "AppPackages-44.zip"
    if cached.exists():
        payload = cached.read_bytes()
    else:
        with urllib.request.urlopen(URL, timeout=60) as response:
            payload = response.read(50 * 1024 * 1024 + 1)
    if hashlib.sha256(payload).hexdigest() != SHA256:
        raise ValueError("Microsoft release checksum mismatch")
    archive = zipfile.ZipFile(io.BytesIO(payload))
    if archive.testzip():
        raise ValueError("corrupt Microsoft release archive")
    if not cached.exists():
        cached.write_bytes(payload)
    samples = REPO / "samples/microsoft"
    samples.mkdir(parents=True, exist_ok=True)
    manifest = {"url": URL, "releaseSha256": SHA256, "apps": []}
    for app, (member, canvases) in APPS.items():
        package = archive.read(f"AppPackages/{app}/DataverseSolution.cab")
        target = output / f"{app}.cab"
        # Always derive from verified release bytes, not a possibly stale CAB.
        target.write_bytes(package)
        extracted = subprocess.run(
            ["cabextract", "-p", "-F", member, str(target)],
            check=True, capture_output=True, timeout=60,
        ).stdout
        solution = zipfile.ZipFile(io.BytesIO(extracted))
        if solution.testzip():
            raise ValueError(f"corrupt {app} solution")
        # Read named entries only; never extract archive-controlled filesystem paths.
        for canvas, name in canvases.items():
            source_member = f"CanvasApps/{canvas}_DocumentUri.msapp"
            source = solution.read(source_member)
            with zipfile.ZipFile(io.BytesIO(source)) as msapp:
                if msapp.testzip():
                    raise ValueError(f"corrupt canvas export: {name}")
            (samples / f"{name}.msapp").write_bytes(source)
            record = {"id": name, "template": app, "file": f"{name}.msapp",
                      "member": source_member, "sha256": hashlib.sha256(source).hexdigest()}
            manifest["apps"].append(record)
            print(name, record["sha256"], flush=True)
    (output / "provenance.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
