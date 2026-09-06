"""Fetch the public real-app sample corpus into samples/real/ (gitignored).

CI uses this to soak-test against real .msapp exports; locally it is a no-op
when the files already exist. Sources are the public
sunilshetty07/Microsoft-PowerApps-Canvas repo (as documented in the README).
"""
from __future__ import annotations

import io
import hashlib
import os
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
# Overridable so containers can cache the corpus on a mounted volume.
DEST = Path(os.environ.get("PFX2GAS_SAMPLES_DIR", REPO / "samples" / "real"))

SOURCE_REPO = "sunilshetty07/Microsoft-PowerApps-Canvas"
REVISION = "3e60c764a51d63061064e2902e247e6daeaa8468"

# destination name -> path inside the source repo (URL-encoded by caller)
SAMPLES = {
    "editable-grid.msapp": "Editable Grid/Nc09c71dd-b017-4760-8195-3e4303fa2491-document.msapp",
    "expandable-nav.msapp": "Expandable Navigation/N74ca92fc-4b80-4299-b15e-8daa9b7cbae5-document.msapp",
    "modern-card.msapp": "Modern Card Control/Ndee67cf0-ddcf-4927-aded-708146a2ab70-document.msapp",
    "svg-app.msapp": "SVG App/N9a128de4-fbfc-416e-9fb2-77c0c7693bb9-document.msapp",
    "sentiment-feedback.msapp": "Sentiment Analysis-Feedback form/Nd1df79ff-c17a-43af-8ab6-4e481f90ac72-document.msapp",
}

SHA256 = {
    "editable-grid.msapp": "5a0b9889b6293e9f7c17477d4f69f56f850576af071d0506ff44b8a3e1d467c2",
    "expandable-nav.msapp": "44c9357ea01288a3a7ec927a159d27c116526d996c9e4141cc44d5184b272dd7",
    "modern-card.msapp": "91c3699c11e065fbaea989563213b3f21a02fb7720b3cb5c0d22aa0feabb08f0",
    "sentiment-feedback.msapp": "4a8d4ed9d9d5cefe64cc6d5e2846e0ff293d3a09642d881a66a17cce8b07acb0",
    "svg-app.msapp": "3a424b2a81c2afe0a079cad007cfa88f7686b3256ab34dd8d33fe09b79b5f4f0",
}


def fetch(dest: Path, repo_path: str, retries: int = 3) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        matches = hashlib.sha256(dest.read_bytes()).hexdigest() == SHA256[dest.name]
        print(f"  {'=' if matches else '!'} {dest.name} (cached checksum {'verified' if matches else 'MISMATCH'})")
        return matches
    url = (f"https://raw.githubusercontent.com/{SOURCE_REPO}/{REVISION}/"
           + urllib.parse.quote(repo_path))
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "pfx2gas-ci"})
            with urllib.request.urlopen(req, timeout=60) as r:
                payload = r.read()
            if hashlib.sha256(payload).hexdigest() != SHA256[dest.name]:
                raise ValueError(f"checksum mismatch: {dest.name}")
            # a truncated HTML error page must never land in the corpus
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:  # raises if not a zip
                bad = zf.testzip()
                if bad:
                    raise ValueError(f"corrupt zip entry: {bad}")
            dest.write_bytes(payload)
            print(f"  + {dest.name} ({len(payload) // 1024} KB)")
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"  ! attempt {attempt}/{retries} failed: {exc}")
            if attempt < retries:
                time.sleep(2 * attempt)
    return False


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    failures = []
    for name, repo_path in SAMPLES.items():
        if not fetch(DEST / name, repo_path):
            failures.append(name)
    if failures:
        print(f"FAILED to fetch: {', '.join(failures)}", file=sys.stderr)
        return 1
    print(f"sample corpus ready: {len(SAMPLES)} apps in {DEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
