"""Stage 4 orchestrator: IR -> complete Apps Script project on disk."""
from __future__ import annotations

from pathlib import Path

from ..ir import AppIR
from .client import render_app_js, render_index_html, render_screens_html
from .server import render_code_gs, render_data_init, render_manifest

STATIC_DIR = Path(__file__).resolve().parents[3] / "static"


def synthesize(ir: AppIR, out_dir: str | Path) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    (out / "Code.gs").write_text(render_code_gs(ir))
    (out / "DataInit.gs").write_text(render_data_init(ir))
    (out / "appsscript.json").write_text(render_manifest(ir))
    (out / "Index.html").write_text(render_index_html(ir, render_screens_html(ir)))
    (out / "Screens.html").write_text(render_screens_html(ir))
    (out / "App.js.html").write_text("<script>\n" + render_app_js(ir) + "\n</script>")
    for static_name in ("gas-runtime.js", "fx-stdlib.js"):
        src = STATIC_DIR / static_name
        if src.exists():
            (out / static_name.replace(".js", ".js.html")).write_text(
                "<script>\n" + src.read_text() + "\n</script>"
            )
    return out
