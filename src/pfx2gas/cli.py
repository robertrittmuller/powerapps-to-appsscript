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
    conv.add_argument("--solution", help="exported solution ZIP or customizations.xml supplying Dataverse saved-view filters")
    conv.add_argument("-o", "--output", default=None,
                      help="output directory (default: ./output/<app-name>)")
    conv.add_argument("--report-only", action="store_true",
                      help="produce the conversion report without synthesizing the project")
    conv.add_argument("--no-llm", action="store_true",
                      help="disable the LLM fallback (stubbed formulas stay stubs)")
    conv.add_argument("--no-review", action="store_true",
                      help="disable the LLM behavioral-equivalence review + QA scenarios")
    conv.add_argument(
        "--webapp-access",
        choices=("MYSELF", "DOMAIN", "ANYONE", "ANYONE_ANONYMOUS"),
        default="ANYONE",
        help="deployment audience (default: signed-in users; anonymous is explicit)",
    )
    conv.add_argument(
        "--execute-as",
        choices=("USER_ACCESSING", "USER_DEPLOYING"),
        default="USER_ACCESSING",
        help="Apps Script execution identity (default: the signed-in user)",
    )
    conv.add_argument("--strict-fidelity", action="store_true",
                      help="exit non-zero when the generated fidelity ledger has gaps")

    validate_p = sub.add_parser("validate", help="validate a synthesized project directory")
    validate_p.add_argument("project_dir")
    validate_p.add_argument("--strict-fidelity", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "validate":
        from .validate import validate_project
        result = validate_project(args.project_dir)
        if result["ok"] and (not args.strict_fidelity or not result["fidelity_gap_count"]):
            out.print(f"[green]OK[/green] — {result['stub_count']} stub call sites, "
                      f"{result['fidelity_gap_count']} fidelity gaps")
            return 0
        if result["ok"]:
            err.print(f"strict fidelity failed: {result['fidelity_gap_count']} ledgered gaps")
            return 1
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
    try:
        ir = analyze(parse(unpacked), solution=args.solution)
    except (OSError, ValueError) as exc:
        err.print(f"source metadata could not be loaded: {exc}")
        return 1
    ir.webapp_access = args.webapp_access
    ir.webapp_execute_as = args.execute_as

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
        from .synth.build import assess_fidelity
        assess_fidelity(ir)
        report = render_report(ir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "conversion-report.md").write_text(report)
        out.print(f"[green]report written:[/green] {out_dir / 'conversion-report.md'}")
        return 0

    from .synth.build import synthesize
    synthesize(ir, out_dir)
    validation = validate_project(out_dir)

    # LLM review seams (review-only; never modify generated code)
    review_rows: list[dict] = []
    qa_scenarios: list[dict] = []
    if not args.no_llm and not args.no_review:
        from .llm import LlmClient
        from .review import author_qa_scenarios, review_behavioral_equivalence
        review_client = LlmClient()
        if review_client.available:
            out.print("[dim]LLM review: checking behavioral equivalence...[/dim]")
            review_rows = review_behavioral_equivalence(ir, review_client)
            qa_scenarios = author_qa_scenarios(ir, review_client)
            highs = sum(1 for r in review_rows if r["risk"] == "high")
            out.print(f"  review: {len(review_rows)} formulas reviewed, {highs} high-risk")

    (out_dir / "conversion-report.md").write_text(
        render_report(ir, validation, review_rows=review_rows, qa_scenarios=qa_scenarios))

    if validation["ok"] and (not args.strict_fidelity or not validation["fidelity_gap_count"]):
        out.print(f"[green]converted:[/green] {out_dir}")
        out.print(f"  validator: PASS, {validation['stub_count']} stub call sites, "
                  f"{validation['fidelity_gap_count']} fidelity gaps")
        out.print("  next steps:")
        out.print(f"    1. ./pfx2gas clasp -w {out_dir.resolve()} create "
                  "--title <name> --type webapp (or reuse a scriptId)")
        out.print("    2. re-run convert to restore appsscript.json, then "
                  f"./pfx2gas clasp -w {out_dir.resolve()} push --force")
        out.print("    3. in the Apps Script editor run setup() once (DataInit.gs)")
        out.print(f"    4. ./pfx2gas clasp -w {out_dir.resolve()} deploy")
        out.print(f"  review {out_dir / 'conversion-report.md'} for manual follow-ups")
        return 0
    if validation["ok"]:
        err.print(f"strict fidelity failed: {validation['fidelity_gap_count']} ledgered gaps")
        return 1
    for problem in validation["problems"]:
        err.print(problem)
    return 1


def _llm_fallback(ir, client) -> None:
    """Give the LLM one shot at every stubbed formula, in place."""
    from .fidelity import iter_expressions
    import json

    def try_fix(expr, context: str) -> None:
        if expr.blocked_dependencies:
            return  # A model must not guess missing saved-query contracts.
        if not expr.raw:
            return
        if expr.js is not None and "FX.unsupported" not in expr.js:
            return
        result = client.translate_formula(expr.raw, context,
                                          behavior=(expr.kind == "behavior"))
        if result and result["js"]:
            expr.js = result["js"]
            expr.translation_status = "llm"
            expr.fidelity_note = "LLM proposal passed syntax/structural checks; behavioral equivalence remains unverified"
            from .ir import SupportEntry
            ir.support_matrix.append(SupportEntry(
                subject=expr.raw[:80], status="partial",
                detail=f"LLM-translated (confidence {result['confidence']:.2f}): {result['notes'][:80]}",
            ))

    screens = {screen.name: screen for screen in ir.screens}
    for screen_name, control, property_name, expr in iter_expressions(ir):
        screen = screens.get(screen_name)
        scope = {"definingScreen": screen.name if screen else None,
                 "localVariables": screen.context_vars if screen else [],
                 "globalVariables": ir.global_vars}
        try_fix(expr, f"{screen_name}.{control}.{property_name}\nScope: {json.dumps(scope)}")
