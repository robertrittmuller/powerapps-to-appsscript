"""Stage 5: validate a synthesized project (syntax, structure, stub census)."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

REQUIRED_FILES = ["Code.gs", "DataInit.gs", "appsscript.json", "Index.html",
                  "Screens.html", "App.js.html"]


def js_syntax_ok(js: str) -> tuple[bool, str]:
    """node --check a JS snippet; returns (ok, stderr)."""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js)
        path = f.name
    try:
        result = subprocess.run(["node", "--check", path], capture_output=True, text=True, timeout=30)
        return result.returncode == 0, result.stderr.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    finally:
        Path(path).unlink(missing_ok=True)


def validate_project(out_dir: str | Path) -> dict:
    out = Path(out_dir)
    problems: list[str] = []
    missing = [n for n in REQUIRED_FILES if not (out / n).exists()]
    if missing:
        problems.append(f"missing files: {', '.join(missing)}")

    stub_count = 0
    for js_html in out.glob("*.js.html"):
        body = js_html.read_text().replace("<script>\n", "").replace("\n</script>", "")
        ok, err = js_syntax_ok(body)
        if not ok:
            problems.append(f"{js_html.name} fails node --check: {err.splitlines()[0] if err else 'unknown'}")
        stub_count += body.count("FX.unsupported(")

    # Server-side .gs files are plain JS (V8); syntax-check them like the client.
    for gs_file in sorted(out.glob("*.gs")):
        ok, err = js_syntax_ok(gs_file.read_text())
        if not ok:
            problems.append(f"{gs_file.name} fails node --check: {err.splitlines()[0] if err else 'unknown'}")

    index = (out / "Index.html").read_text() if (out / "Index.html").exists() else ""
    if index and "data-screen" not in index and "include('Screens')" not in index:
        problems.append("Index.html does not reference Screens")

    gs = (out / "Code.gs").read_text() if (out / "Code.gs").exists() else ""
    if gs and "function doGet()" not in gs:
        problems.append("Code.gs has no doGet()")

    return {"ok": not problems, "problems": problems, "stub_count": stub_count}
