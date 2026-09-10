"""Stage 4 orchestrator: IR -> complete Apps Script project on disk."""
from __future__ import annotations

from pathlib import Path

from ..fidelity import finalize_fidelity, ledger_rows
from ..ir import AppIR
from .client import render_app_js, render_index_html, render_screens_html
from .server import render_code_gs, render_data_init, render_manifest

STATIC_DIR = Path(__file__).resolve().parents[3] / "static"


def assess_fidelity(ir: AppIR) -> AppIR:
    """Run synthesis in memory so report-only mode still gets emission truth."""
    render_screens_html(ir)
    render_app_js(ir)
    finalize_fidelity(ir)
    return ir


def synthesize(ir: AppIR, out_dir: str | Path) -> Path:
    import json
    from ..relationships import relationship_contracts
    from ..services import service_contracts

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    screens_html = render_screens_html(ir)
    app_js = render_app_js(ir)
    finalize_fidelity(ir)
    (out / "Code.gs").write_text(render_code_gs(ir))
    (out / "DataInit.gs").write_text(render_data_init(ir))
    if 'Planner' in service_contracts(ir):
        from .planner import MIGRATION_TEMPLATE, MIGRATION_GUIDE
        # This is an operator-edited import entry point; keep reviewed data
        # across a repeated conversion to the same output directory.
        migration = out / 'PlannerMigration.gs'
        if not migration.exists():
            migration.write_text(MIGRATION_TEMPLATE)
        (out / 'planner-migration.md').write_text(MIGRATION_GUIDE)
    if any(contract['target'] == 'google-people-directory' for contract in service_contracts(ir).values()):
        from .directory import MIGRATION_TEMPLATE, MIGRATION_GUIDE
        migration = out / 'DirectoryMigration.gs'
        if not migration.exists():
            migration.write_text(MIGRATION_TEMPLATE)
        (out / 'directory-migration.md').write_text(MIGRATION_GUIDE)
    (out / "appsscript.json").write_text(render_manifest(ir))
    (out / "Index.html").write_text(render_index_html(ir, screens_html))
    (out / "Screens.html").write_text(screens_html)
    (out / "App.js.html").write_text("<script>\n" + app_js + "\n</script>")
    (out / "conversion-ledger.json").write_text(
        json.dumps({
            "app": ir.name,
            "sourceLayout": ir.layout,
            "sourceMetadata": ir.source_metadata,
            "savedViews": ir.view_sets,
            "googleServiceAdapters": service_contracts(ir),
            "deployment": {
                "access": ir.webapp_access,
                "executeAs": ir.webapp_execute_as,
            },
            "warnings": ir.warnings,
            "formulas": ledger_rows(ir),
        }, indent=2) + "\n"
    )
    (out / "data-contract.json").write_text(json.dumps({
        "version": 1, "sources": [ds.model_dump() for ds in ir.data_sources],
        "relationshipNavigation": relationship_contracts(ir),
        "googleServiceAdapters": service_contracts(ir),
        "limitations": ["Exported one-to-many lookups and many-to-many links refresh related records on the first source only. Many-to-many links use __pfx2gas_links; retries are idempotent and unmatched Unrelate is a no-op. Cascade deletes, alternate-key relationships and permissions require adapters.",
                        "Lookup fields remain stored snapshots; source defaults, calculated fields and unsupported saved views require adapters.",
                        "Choice codes and boolean values are retained; implicit localized choice-to-text coercion is not yet implemented."],
    }, indent=2) + "\n")
    for static_name in ("gas-runtime.js", "fx-stdlib.js", "fx-charts.js"):
        src = STATIC_DIR / static_name
        if src.exists():
            (out / static_name.replace(".js", ".js.html")).write_text(
                "<script>\n" + src.read_text() + "\n</script>"
            )
    return out
