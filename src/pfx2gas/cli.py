"""pfx2gas CLI — convert a Power Apps .msapp to a Google Apps Script project."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rich.console import Console

err = Console(stderr=True, style="bold red")
out = Console()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pfx2gas",
        description="Convert a Power Apps canvas app (.msapp) to a Google Apps Script web app.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    conv = sub.add_parser("convert", help="convert an .msapp to an Apps Script project")
    conv.add_argument("msapp", help="path to the .msapp file")
    conv.add_argument("-o", "--output", default=None,
                      help="output directory (default: ./output/<app-name>)")
    conv.add_argument("--report-only", action="store_true",
                      help="produce the conversion report without synthesizing the project")
    conv.add_argument("--no-llm", action="store_true",
                      help="disable the LLM fallback (stubbed formulas stay stubs)")

    validate_p = sub.add_parser("validate", help="validate a synthesized project directory")
    validate_p.add_argument("project_dir")

    args = parser.parse_args(argv)

    if args.command == "validate":
        from .validate import validate_project
        result = validate_project(args.project_dir)
        if result["ok"]:
            out.print(f"[green]OK[/green] — {result['stub_count']} stub call sites")
            return 0
        for p in result["problems"]:
            err.print(p)
        return 1

    # convert
    from .unpack import unpack, UnpackError
    from .parse import parse
    from .analyze import analyze
    from .report import render_report
    from .validate import validate_project

    msapp = Path(args.msapp)
    if not msapp.exists():
        err.print(f"file not found: {msapp}")
        return 1

    try:
        unpacked = unpack(msapp)
    except UnpackError as exc:
        err.print(str(exc))
        return 1

    for warning in unpacked.warnings:
        out.print(f"[yellow]warn:[/yellow] {warning}")

    out.print(f"[bold]{unpacked.app_name}[/bold]: {len(unpacked.screens)} screens, "
              f"{len(unpacked.data_sources)} data sources")
    ir = analyze(parse(unpacked))

    # LLM fallback for unmapped formulas (opt-in via env, --no-llm to force off)
    if not args.no_llm:
        from .llm import LlmClient
        client = LlmClient()
        if client.available:
            _llm_fallback(ir, client)
        else:
            out.print("[dim]LLM fallback not configured "
                      "(set PFX2GAS_LLM_BASE_URL / PFX2GAS_LLM_API_KEY); "
                      "unmapped formulas stay stubbed[/dim]")

    out_dir = Path(args.output) if args.output else Path("output") / ir.name
    out.print(f"support matrix: {len(ir.support_matrix)} entries "
              f"({sum(1 for e in ir.support_matrix if e.status == 'full')} full)")

    if args.report_only:
        report = render_report(ir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "conversion-report.md").write_text(report)
        out.print(f"[green]report written:[/green] {out_dir / 'conversion-report.md'}")
        return 0

    from .synth.build import synthesize
    synthesize(ir, out_dir)
    validation = validate_project(out_dir)
    (out_dir / "conversion-report.md").write_text(render_report(ir, validation))

    if validation["ok"]:
        out.print(f"[green]converted:[/green] {out_dir}")
        out.print(f"  validator: PASS, {validation['stub_count']} stub call sites")
        out.print("  next steps:")
        out.print("    1. npx @google/clasp create --title <name> --type webapp (or reuse a scriptId)")
        out.print("    2. copy the project files, then npx @google/clasp push --force")
        out.print("    3. in the Apps Script editor run setup() once (DataInit.gs)")
        out.print("    4. npx @google/clasp deploy")
        out.print(f"  review {out_dir / 'conversion-report.md'} for manual follow-ups")
        return 0
    for problem in validation["problems"]:
        err.print(problem)
    return 1


def _llm_fallback(ir, client) -> None:
    """Give the LLM one shot at every stubbed formula, in place."""
    from .fx import transpile  # noqa: F401  (context import)

    def try_fix(expr, context: str) -> None:
        if expr.js is not None and "FX.unsupported" not in expr.js:
            return
        result = client.translate_formula(expr.raw, context)
        if result and result["js"]:
            expr.js = result["js"]
            from .ir import SupportEntry
            ir.support_matrix.append(SupportEntry(
                subject=expr.raw[:80], status="partial",
                detail=f"LLM-translated (confidence {result['confidence']:.2f}): {result['notes'][:80]}",
            ))

    if ir.on_start:
        try_fix(ir.on_start, "App.OnStart")
    for screen in ir.screens:
        if screen.on_visible:
            try_fix(screen.on_visible, f"{screen.name}.OnVisible")
        for ctrl in screen.walk_controls():
            for pname, expr in ctrl.properties.items():
                try_fix(expr, f"{screen.name}.{ctrl.name}.{pname}")
