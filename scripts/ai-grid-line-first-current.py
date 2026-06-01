#!/usr/bin/env python3
"""Run the current AI grid recipe as a live line-first policy.

This is a speed/operations probe. It spends one image-generation call on the
white-line mask, parses that mask as an observed grid graph, and only launches
dots-only retry waves when the line graph is not accepted or report-trusted.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
AI_GRID_PATH = ROOT / "scripts" / "ai-grid-experiment.py"
AI_ARBITER_PATH = ROOT / "scripts" / "ai-evidence-arbiter.py"
AI_DOT_FIT_PATH = ROOT / "scripts" / "ai-dot-lattice-fit.py"
AI_LINE_GRAPH_PATH = ROOT / "scripts" / "ai-line-graph-lattice.py"
AI_LINE_SKELETON_PATH = ROOT / "scripts" / "ai-line-skeleton-junction-probe.py"
AI_PARALLEL_PATH = ROOT / "scripts" / "ai-grid-parallel-current.py"
DEFAULT_OUT_DIR = ROOT / "test-results" / "ai-grid-line-first-current"

LINE_PROMPT_ID = "white-grid-exact-copy-no-marks-v1"
DOT_PROMPT_ID = "white-intersection-dots-no-lines-v1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-id", default="real-map-home-IMG_9719.jpg")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--provider", default="grok-image")
    parser.add_argument("--line-prompt-id", default=LINE_PROMPT_ID)
    parser.add_argument("--dot-prompt-id", default=DOT_PROMPT_ID)
    parser.add_argument("--line-samples", type=int, default=1, help="Parallel line-mask samples to try before dot fallback.")
    parser.add_argument("--waves", default="4,2", help="Comma-separated dot fallback wave sizes.")
    parser.add_argument("--line-settings", default="64:3:1,64:3:2,64:5:2")
    parser.add_argument("--selection-policy", choices=["confidence", "guarded-mesh-density", "guarded-risk-aware"], default="guarded-risk-aware")
    parser.add_argument("--require-safe-accept", action="store_true")
    parser.add_argument("--require-fullspan-accept", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--max-width", type=int, default=1024)
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args()

    ai_grid = load_module("ai_grid_experiment", AI_GRID_PATH)
    ai_arbiter = load_module("ai_evidence_arbiter", AI_ARBITER_PATH)
    dot_fit = load_module("ai_dot_lattice_fit", AI_DOT_FIT_PATH)
    line_graph = load_module("ai_line_graph_lattice", AI_LINE_GRAPH_PATH)
    line_skeleton = load_module("ai_line_skeleton_junction_probe", AI_LINE_SKELETON_PATH)
    parallel = load_module("ai_grid_parallel_current", AI_PARALLEL_PATH)
    ai_grid.load_project_env()

    label = ai_grid.load_label(args.source_id)
    out_dir = Path(args.out_dir)
    run_dir = out_dir / slugify(Path(args.source_id).stem) / policy_id(args)
    if args.run_id:
        run_dir = run_dir / slugify(args.run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    input_path = ROOT / label["sourceUrl"].removeprefix("/")
    input_image = ai_grid.load_display_image(input_path)
    input_work_path = ai_grid.write_working_input(input_image, run_dir, args.max_width, args.source_id)

    started = time.perf_counter()
    line_prompt = prompt_by_id(ai_grid, args.line_prompt_id)
    line_reports, line_wall_ms = run_line_jobs(ai_grid, args.provider, input_work_path, label, run_dir, line_prompt, args.line_samples)
    line_selected = analyze_line_graph(
        line_graph,
        line_skeleton,
        ai_grid,
        ai_arbiter,
        label,
        line_reports,
        args.line_prompt_id,
        args.line_settings,
        run_dir / "line-graph",
        write_visuals=not args.summary_only,
    )
    selected_line_report = selected_report_for_line(line_reports, line_selected)
    if line_graph_usable(line_selected):
        report = build_line_report(args, run_dir, started, line_wall_ms, line_reports, line_selected)
        write_report(report, run_dir)
        print(render_console(report))
        return

    dot_prompt = prompt_by_id(ai_grid, args.dot_prompt_id)
    fallback = run_dot_fallback(
        parallel,
        dot_fit,
        ai_grid,
        ai_arbiter,
        args,
        input_work_path,
        label,
        run_dir,
        selected_line_report,
        dot_prompt,
    )
    report = build_dot_report(args, run_dir, started, line_wall_ms, line_reports, line_selected, fallback)
    write_report(report, run_dir)
    print(render_console(report))


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def prompt_by_id(ai_grid: Any, prompt_id: str) -> Any:
    for prompt in ai_grid.IMAGE_PROMPTS:
        if prompt.prompt_id == prompt_id:
            return prompt
    raise RuntimeError(f"Prompt not found: {prompt_id}")


def parse_wave_sizes(value: str) -> list[int]:
    sizes = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not sizes or any(size <= 0 for size in sizes):
        raise ValueError("--waves must contain one or more positive integers")
    return sizes


def policy_id(args: argparse.Namespace) -> str:
    chunks = [f"line_first_l{args.line_samples}_wave{'_then'.join(str(size) for size in parse_wave_sizes(args.waves))}"]
    if args.selection_policy != "confidence":
        chunks.append(args.selection_policy.replace("-", "_"))
    if args.require_fullspan_accept:
        chunks.append("require_fullspan")
    elif args.require_safe_accept:
        chunks.append("require_safe")
    if args.line_prompt_id != LINE_PROMPT_ID:
        chunks.append(f"line_{slugify(args.line_prompt_id)}")
    return "_".join(chunks)


def run_line_jobs(
    ai_grid: Any,
    provider: str,
    input_work_path: Path,
    label: dict[str, Any],
    run_dir: Path,
    prompt: Any,
    line_samples: int,
) -> tuple[list[dict[str, Any]], float]:
    if line_samples <= 0:
        raise ValueError("--line-samples must be positive")
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=line_samples) as executor:
        futures = [
            executor.submit(run_one_line_job, ai_grid, provider, input_work_path, label, run_dir, prompt, index, line_samples)
            for index in range(1, line_samples + 1)
        ]
        reports = [future.result() for future in concurrent.futures.as_completed(futures)]
    return sorted(reports, key=lambda report: report["_jobIndex"]), elapsed_ms(started)


def run_one_line_job(
    ai_grid: Any,
    provider: str,
    input_work_path: Path,
    label: dict[str, Any],
    run_dir: Path,
    prompt: Any,
    index: int,
    line_samples: int,
) -> dict[str, Any]:
    line_dir = run_dir / ("line" if line_samples == 1 else f"line-{index:02d}")
    line_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    result = ai_grid.run_image_experiment(provider, prompt, input_work_path, label, line_dir)
    result["lineSampleIndex"] = index
    result["lineSampleWallMs"] = round_metric(elapsed_ms(started))
    report = {
        "sourceId": label["sourceId"],
        "sourceUrl": label["sourceUrl"],
        "inputWorkingImage": str(input_work_path),
        "results": [result],
    }
    report_path = line_dir / "report.json"
    report_path.write_text(f"{json.dumps(report, indent=2)}\n")
    report["_reportPath"] = str(report_path)
    report["_jobKind"] = "line"
    report["_jobIndex"] = index
    return report


def analyze_line_graph(
    line_graph: Any,
    line_skeleton: Any,
    ai_grid: Any,
    ai_arbiter: Any,
    label: dict[str, Any],
    line_reports: list[dict[str, Any]],
    line_prompt_id: str,
    settings_value: str,
    out_dir: Path,
    write_visuals: bool,
) -> dict[str, Any]:
    overlays_dir = out_dir / "overlays"
    if write_visuals:
        overlays_dir.mkdir(parents=True, exist_ok=True)
    candidates = []
    for line_report in line_reports:
        for setting in line_graph.parse_settings(settings_value):
            candidate = line_graph.analyze_report(
                ai_grid,
                ai_arbiter,
                line_skeleton,
                label,
                line_report,
                line_prompt_id,
                setting,
                overlays_dir,
                write_visuals=write_visuals,
            )
            if candidate is not None:
                candidates.append(candidate)
    if not candidates:
        return {"decision": "refuse", "reasons": ["line graph produced no candidates"]}
    selected = line_graph.select_candidate(candidates)
    return line_graph.candidate_to_json(selected)


def line_graph_usable(line_selected: dict[str, Any]) -> bool:
    return line_selected.get("decision") == "accepted-observed-grid-graph" or bool(line_selected.get("trustedGrownExtent"))


def selected_report_for_line(line_reports: list[dict[str, Any]], line_selected: dict[str, Any]) -> dict[str, Any]:
    selected_path = line_selected.get("reportPath")
    for report in line_reports:
        if report.get("_reportPath") == selected_path:
            return report
    return line_reports[0]


def run_dot_fallback(
    parallel: Any,
    dot_fit: Any,
    ai_grid: Any,
    ai_arbiter: Any,
    args: argparse.Namespace,
    input_work_path: Path,
    label: dict[str, Any],
    run_dir: Path,
    line_report: dict[str, Any],
    dot_prompt: Any,
) -> dict[str, Any]:
    wave_sizes = parse_wave_sizes(args.waves)
    scorer = parallel.DotReportScorer(
        dot_fit,
        ai_grid,
        ai_arbiter,
        args.source_id,
        line_report,
        label,
        write_visuals=not args.summary_only,
        selection_policy=args.selection_policy,
    )
    dot_reports = []
    wave_events = []
    selected = None
    next_dot_index = 1
    fallback_started = time.perf_counter()
    for wave_index, wave_size in enumerate(wave_sizes):
        jobs = [("dot", index, dot_prompt) for index in range(next_dot_index, next_dot_index + wave_size)]
        next_dot_index += wave_size
        wave_started = time.perf_counter()
        reports = parallel.run_jobs(ai_grid, args.provider, input_work_path, label, run_dir, jobs)
        wave_events.append({
            "wave": parallel.wave_name(wave_index),
            "jobs": len(jobs),
            "wallMs": round_metric(elapsed_ms(wave_started)),
        })
        dot_reports.extend(report for report in reports if report["_jobKind"] == "dot")
        raw_selected = scorer.evaluate(parallel.ordered_dot_reports(dot_reports), run_dir / f"score-wave-{wave_index + 1}")
        selected = parallel.choose_wave_selection(
            raw_selected,
            None,
            require_safe_accept=args.require_safe_accept,
            require_fullspan_accept=args.require_fullspan_accept,
        )
        if parallel.should_stop_after_wave(selected, args.require_safe_accept, args.require_fullspan_accept):
            break
    if selected is None:
        raise RuntimeError("Dot fallback produced no selection")
    return {
        "fallbackWallMs": round_metric(elapsed_ms(fallback_started)),
        "waves": wave_events,
        "dotReportsUsed": [item["_reportPath"] for item in parallel.ordered_dot_reports(dot_reports)],
        "selected": parallel.summarize_selection(selected),
        "selectedDetail": selected,
    }


def build_line_report(
    args: argparse.Namespace,
    run_dir: Path,
    started: float,
    line_wall_ms: float,
    line_reports: list[dict[str, Any]],
    line_selected: dict[str, Any],
) -> dict[str, Any]:
    return {
        "sourceId": args.source_id,
        "outDir": str(run_dir),
        "policy": policy_id(args),
        "linePromptId": args.line_prompt_id,
        "dotPromptId": args.dot_prompt_id,
        "selectionPolicy": args.selection_policy,
        "requireSafeAccept": args.require_safe_accept,
        "requireFullspanAccept": args.require_fullspan_accept,
        "summaryOnly": args.summary_only,
        "totalWallMs": round_metric(elapsed_ms(started)),
        "lineWallMs": round_metric(line_wall_ms),
        "lineSampleCount": len(line_reports),
        "lineReports": [report["_reportPath"] for report in line_reports],
        "selectedLineReport": line_selected.get("reportPath"),
        "lineGraphSelected": line_selected,
        "fallbackUsed": False,
        "selectedEvidence": "line-graph",
        "selected": line_graph_summary(line_selected),
    }


def build_dot_report(
    args: argparse.Namespace,
    run_dir: Path,
    started: float,
    line_wall_ms: float,
    line_reports: list[dict[str, Any]],
    line_selected: dict[str, Any],
    fallback: dict[str, Any],
) -> dict[str, Any]:
    return {
        "sourceId": args.source_id,
        "outDir": str(run_dir),
        "policy": policy_id(args),
        "linePromptId": args.line_prompt_id,
        "dotPromptId": args.dot_prompt_id,
        "selectionPolicy": args.selection_policy,
        "requireSafeAccept": args.require_safe_accept,
        "requireFullspanAccept": args.require_fullspan_accept,
        "summaryOnly": args.summary_only,
        "totalWallMs": round_metric(elapsed_ms(started)),
        "lineWallMs": round_metric(line_wall_ms),
        "lineSampleCount": len(line_reports),
        "lineReports": [report["_reportPath"] for report in line_reports],
        "selectedLineReport": line_selected.get("reportPath"),
        "lineGraphSelected": line_selected,
        "fallbackUsed": True,
        "selectedEvidence": "dot-consensus-fallback",
        "dotFallback": fallback,
        "selected": fallback["selected"],
    }


def line_graph_summary(line_selected: dict[str, Any]) -> dict[str, Any]:
    return {
        "evidenceSource": "line-graph",
        "decision": line_selected.get("decision"),
        "lineGraphTrustedGrownExtent": line_selected.get("trustedGrownExtent", False),
        "lineGraphTrustedGrownReason": line_selected.get("trustedGrownReason"),
        "spanI": line_selected.get("spanI"),
        "spanJ": line_selected.get("spanJ"),
        "grownSpanI": line_selected.get("grownSpanI"),
        "grownSpanJ": line_selected.get("grownSpanJ"),
        "meshWithin0_15Pct": line_selected.get("meshWithin0_15Pct"),
        "selectedLineWithin0_15Pct": line_selected.get("selectedLineWithin0_15Pct"),
        "reasons": line_selected.get("reasons"),
    }


def write_report(report: dict[str, Any], run_dir: Path) -> None:
    (run_dir / "line-first-report.json").write_text(f"{json.dumps(report, indent=2)}\n")
    (run_dir / "line-first-report.md").write_text(render_markdown(report))


def render_markdown(report: dict[str, Any]) -> str:
    selected = report["selected"]
    lines = [
        "# Line-First AI Grid Current Recipe",
        "",
        f"- Source: `{report['sourceId']}`",
        f"- Policy: `{report['policy']}`",
        f"- Selection policy: `{report['selectionPolicy']}`",
        f"- Require safe accept: `{report['requireSafeAccept']}`",
        f"- Require full-span accept: `{report['requireFullspanAccept']}`",
        f"- Total wall time: `{round_metric(report['totalWallMs'] / 1000)}s`",
        f"- Line wall time: `{round_metric(report['lineWallMs'] / 1000)}s`",
        f"- Line samples: `{report['lineSampleCount']}`",
        f"- Fallback used: `{report['fallbackUsed']}`",
        f"- Selected evidence: `{report['selectedEvidence']}`",
        f"- Final decision: `{selected.get('decision')}`",
    ]
    if report["fallbackUsed"]:
        lines.extend([
            f"- Dot samples used: `{selected.get('dotVariantCount')}`",
            f"- Homography line <=.15: `{selected.get('truthLineSamplesWithin0_15SquaresPct')}`",
            f"- Mesh line <=.15: `{selected.get('truthMeshSamplesWithin0_15SquaresPct')}`",
            "",
            "| Wave | Jobs | Wall Time |",
            "| --- | ---: | ---: |",
        ])
        for wave in report["dotFallback"]["waves"]:
            lines.append(f"| `{wave['wave']}` | {wave['jobs']} | {round_metric(wave['wallMs'] / 1000)}s |")
    else:
        lines.extend([
            f"- Line selected <=.15: `{selected.get('selectedLineWithin0_15Pct')}`",
            f"- Line mesh <=.15: `{selected.get('meshWithin0_15Pct')}`",
            f"- Trusted grown extent: `{selected.get('lineGraphTrustedGrownExtent')}`",
        ])
    lines.append("")
    return "\n".join(lines)


def render_console(report: dict[str, Any]) -> str:
    selected = report["selected"]
    lines = [
        f"Line-first AI grid current: {selected.get('decision')} for {report['sourceId']}",
        f"- evidence: {report['selectedEvidence']}",
        f"- total wall: {round_metric(report['totalWallMs'] / 1000)}s",
        f"- line wall: {round_metric(report['lineWallMs'] / 1000)}s",
        f"- line samples: {report['lineSampleCount']}",
        f"- fallback used: {report['fallbackUsed']}",
    ]
    if report["fallbackUsed"]:
        lines.extend([
            f"- dot samples used: {selected.get('dotVariantCount')}",
            f"- truth line <=.15: {selected.get('truthLineSamplesWithin0_15SquaresPct')}",
            f"- mesh <=.15: {selected.get('truthMeshSamplesWithin0_15SquaresPct')}",
        ])
    else:
        lines.extend([
            f"- selected line <=.15: {selected.get('selectedLineWithin0_15Pct')}",
            f"- mesh <=.15: {selected.get('meshWithin0_15Pct')}",
            f"- trusted grown extent: {selected.get('lineGraphTrustedGrownExtent')}",
        ])
    lines.append(f"Artifacts: {report['outDir']}/line-first-report.md")
    return "\n".join(lines)


def elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def slugify(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "-" for char in value).strip("-")


def round_metric(value: float) -> float:
    return round(float(value), 3)


if __name__ == "__main__":
    main()
