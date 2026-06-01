#!/usr/bin/env python3
"""Run the current AI grid recipe with parallel dot retries.

This script is a speed/operations probe for the current optional remote AI
path. It launches the white-line mask and first dot samples in parallel, scores
the returned artifacts with the deterministic fitter, and launches a second dot
wave only when the first wave has no accepted visible-lattice geometry.
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
LABELS_PATH = ROOT / "input" / "map-grid-labels.json"
DEFAULT_OUT_DIR = ROOT / "test-results" / "ai-grid-parallel-current"

LINE_PROMPT_ID = "white-grid-exact-copy-no-marks-v1"
DOT_PROMPT_ID = "white-intersection-dots-no-lines-v1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-id", default="real-map-home-IMG_9719.jpg")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--provider", default="grok-image")
    parser.add_argument("--line-prompt-id", default=LINE_PROMPT_ID)
    parser.add_argument("--dot-prompt-id", default=DOT_PROMPT_ID)
    parser.add_argument("--first-wave", type=int, default=3)
    parser.add_argument("--second-wave", type=int, default=2)
    parser.add_argument("--waves", default=None, help="Comma-separated dot retry wave sizes. Overrides --first-wave/--second-wave.")
    parser.add_argument("--line-skeleton", action="store_true", help="Allow the skeletonized white-line parser to accept after the first wave when dot consensus has not accepted.")
    parser.add_argument("--line-skeleton-thresholds", default="64,96,128")
    parser.add_argument("--line-graph", action="store_true", help="Allow the observed-grid graph parser to accept after each wave when dot consensus has not accepted.")
    parser.add_argument("--line-graph-settings", default="64:3:1,64:3:2,64:5:2")
    parser.add_argument("--measure-early-accept", action="store_true", help="Score completed dot reports as they arrive and record the first accepted geometry time without cancelling launched jobs.")
    parser.add_argument("--require-safe-accept", action="store_true", help="Continue to the next wave unless the selected accepted geometry also passes the early-return safety floor.")
    parser.add_argument("--require-fullspan-accept", action="store_true", help="Continue to the next wave unless the selected accepted geometry is no-label full-span projection-ready.")
    parser.add_argument("--summary-only", action="store_true", help="Skip lattice overlay image generation during scoring and write metric reports only.")
    parser.add_argument(
        "--selection-policy",
        choices=["confidence", "guarded-mesh-density", "guarded-risk-aware"],
        default="confidence",
        help="Dot-variant selection policy used by the deterministic scorer.",
    )
    parser.add_argument("--max-width", type=int, default=1024)
    parser.add_argument("--run-id", default=None, help="Optional run folder suffix for preserving repeated live measurements of the same source and policy.")
    args = parser.parse_args()
    wave_sizes = parse_wave_sizes(args.waves) if args.waves else [size for size in [args.first_wave, args.second_wave] if size > 0]
    policy_id = policy_name(wave_sizes)
    if args.line_skeleton:
        policy_id = f"{policy_id}_line_skeleton"
    if args.line_graph:
        policy_id = f"{policy_id}_line_graph"
    if args.selection_policy != "confidence":
        policy_id = f"{policy_id}_{args.selection_policy.replace('-', '_')}"
    if args.line_prompt_id != LINE_PROMPT_ID:
        policy_id = f"{policy_id}_line_{slugify(args.line_prompt_id)}"
    if args.dot_prompt_id != DOT_PROMPT_ID:
        policy_id = f"{policy_id}_dot_{slugify(args.dot_prompt_id)}"
    if args.require_fullspan_accept:
        policy_id = f"{policy_id}_require_fullspan"
    elif args.require_safe_accept:
        policy_id = f"{policy_id}_require_safe"
    line_skeleton_thresholds = parse_thresholds(args.line_skeleton_thresholds)

    ai_grid = load_module("ai_grid_experiment", AI_GRID_PATH)
    ai_arbiter = load_module("ai_evidence_arbiter", AI_ARBITER_PATH)
    dot_fit = load_module("ai_dot_lattice_fit", AI_DOT_FIT_PATH)
    line_skeleton = load_module("ai_line_skeleton_junction_probe", AI_LINE_SKELETON_PATH) if args.line_skeleton or args.line_graph else None
    line_graph = load_module("ai_line_graph_lattice", AI_LINE_GRAPH_PATH) if args.line_graph else None
    ai_grid.load_project_env()

    label = ai_grid.load_label(args.source_id)
    out_dir = Path(args.out_dir)
    run_dir = out_dir / slugify(Path(args.source_id).stem) / policy_id
    if args.run_id:
        run_dir = run_dir / slugify(args.run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    input_path = ROOT / label["sourceUrl"].removeprefix("/")
    input_image = ai_grid.load_display_image(input_path)
    input_work_path = ai_grid.write_working_input(input_image, run_dir, args.max_width, args.source_id)
    line_prompt = prompt_by_id(ai_grid, args.line_prompt_id)
    dot_prompt = prompt_by_id(ai_grid, args.dot_prompt_id)

    started = time.perf_counter()
    wave_events: list[dict[str, Any]] = []

    line_report: dict[str, Any] | None = None
    dot_reports: list[dict[str, Any]] = []
    first_score: dict[str, Any] | None = None
    selected: dict[str, Any] | None = None
    line_skeleton_selection: dict[str, Any] | None = None
    line_graph_selection: dict[str, Any] | None = None
    early_accept: dict[str, Any] | None = None
    safe_early_accept: dict[str, Any] | None = None
    fullspan_early_accept: dict[str, Any] | None = None
    early_scores: list[dict[str, Any]] = []
    scorer: DotReportScorer | None = None
    next_dot_index = 1
    for wave_index, wave_size in enumerate(wave_sizes):
        jobs = []
        if wave_index == 0:
            jobs.append(("line", 0, line_prompt))
        jobs.extend(("dot", index, dot_prompt) for index in range(next_dot_index, next_dot_index + wave_size))
        next_dot_index += wave_size

        wave_started = time.perf_counter()
        def on_report(report: dict[str, Any]) -> None:
            nonlocal line_report, early_accept, safe_early_accept, fullspan_early_accept, scorer
            if report["_jobKind"] == "line":
                line_report = report
                scorer = DotReportScorer(
                    dot_fit,
                    ai_grid,
                    ai_arbiter,
                    args.source_id,
                    line_report,
                    label,
                    write_visuals=not args.summary_only,
                    selection_policy=args.selection_policy,
                )
            elif report["_jobKind"] == "dot":
                dot_reports.append(report)
            if not args.measure_early_accept or line_report is None or not dot_reports:
                return
            score_dir = run_dir / f"score-wave-{wave_index + 1}-after-{len(dot_reports)}-completed"
            early_selected = evaluate_with_scorer(
                scorer,
                dot_fit,
                ai_grid,
                ai_arbiter,
                args.source_id,
                line_report,
                ordered_dot_reports(dot_reports),
                label,
                score_dir,
                write_visuals=not args.summary_only,
            )
            early_summary = summarize_selection(early_selected)
            early_summary["elapsedMs"] = round_metric(elapsed_ms(started))
            early_summary["wave"] = wave_name(wave_index)
            early_summary["completedDotReports"] = len(dot_reports)
            early_scores.append(early_summary)
            if early_accept is None and early_summary["decision"] == "accepted-visible-lattice-geometry":
                early_accept = dict(early_summary)
            early_safe_selection = choose_wave_selection(early_selected, None, None, require_safe_accept=True)
            early_safe_summary = summarize_selection(early_safe_selection)
            early_safe_summary["elapsedMs"] = early_summary["elapsedMs"]
            early_safe_summary["wave"] = early_summary["wave"]
            early_safe_summary["completedDotReports"] = early_summary["completedDotReports"]
            if safe_early_accept is None and early_safe_summary.get("earlyReturnSafe"):
                safe_early_accept = dict(early_safe_summary)
            early_fullspan_selection = choose_wave_selection(early_selected, None, None, require_fullspan_accept=True)
            early_fullspan_summary = summarize_selection(early_fullspan_selection)
            early_fullspan_summary["elapsedMs"] = early_summary["elapsedMs"]
            early_fullspan_summary["wave"] = early_summary["wave"]
            early_fullspan_summary["completedDotReports"] = early_summary["completedDotReports"]
            if fullspan_early_accept is None and early_fullspan_summary.get("noLabelFullSpanAutoProject"):
                fullspan_early_accept = dict(early_fullspan_summary)

        reports = run_jobs(
            ai_grid,
            args.provider,
            input_work_path,
            label,
            run_dir,
            jobs,
            on_report=on_report if args.measure_early_accept else None,
        )
        wave_wall_ms = elapsed_ms(wave_started)
        wave_events.append({"wave": wave_name(wave_index), "jobs": len(jobs), "wallMs": round_metric(wave_wall_ms)})

        if not args.measure_early_accept and line_report is None:
            line_report = report_for(reports, "line", 0)
        if scorer is None:
            scorer = DotReportScorer(
                dot_fit,
                ai_grid,
                ai_arbiter,
                args.source_id,
                line_report,
                label,
                write_visuals=not args.summary_only,
                selection_policy=args.selection_policy,
            )
        if not args.measure_early_accept:
            dot_reports.extend(report for report in reports if report["_jobKind"] == "dot")
        score_dir = run_dir / ("score-final" if wave_index == len(wave_sizes) - 1 else f"score-wave-{wave_index + 1}")
        selected = evaluate_with_scorer(
            scorer,
            dot_fit,
            ai_grid,
            ai_arbiter,
            args.source_id,
            line_report,
            ordered_dot_reports(dot_reports),
            label,
            score_dir,
            write_visuals=not args.summary_only,
        )
        if args.line_skeleton and line_skeleton_selection is None and line_skeleton is not None:
            line_skeleton_selection = evaluate_line_skeleton(
                line_skeleton,
                ai_grid,
                ai_arbiter,
                dot_fit,
                args.source_id,
                line_report,
                label,
                score_dir / "line-skeleton",
                line_skeleton_thresholds,
                len(dot_reports),
        )
        if args.line_graph and line_graph_selection is None and line_graph is not None and line_skeleton is not None:
            line_graph_selection = evaluate_line_graph(
                line_graph,
                line_skeleton,
                ai_grid,
                ai_arbiter,
                args.source_id,
                line_report,
                label,
                score_dir / "line-graph",
                args.line_prompt_id,
                args.line_graph_settings,
                write_visuals=not args.summary_only,
            )
        if wave_index == 0:
            first_score = choose_wave_selection(
                selected,
                line_skeleton_selection,
                line_graph_selection,
                require_safe_accept=args.require_safe_accept,
                require_fullspan_accept=args.require_fullspan_accept,
            )
        selected = choose_wave_selection(
            selected,
            line_skeleton_selection,
            line_graph_selection,
            require_safe_accept=args.require_safe_accept,
            require_fullspan_accept=args.require_fullspan_accept,
        )
        if should_stop_after_wave(selected, args.require_safe_accept, args.require_fullspan_accept):
            break

    if line_report is None or selected is None or first_score is None:
        raise RuntimeError("No wave reports were produced")

    total_wall_ms = elapsed_ms(started)
    report = {
        "sourceId": args.source_id,
        "outDir": str(run_dir),
        "provider": args.provider,
        "policy": policy_id,
        "runId": args.run_id,
        "linePromptId": LINE_PROMPT_ID,
        "dotPromptId": DOT_PROMPT_ID,
        "firstWave": args.first_wave,
        "secondWave": args.second_wave,
        "waveSizes": wave_sizes,
        "lineSkeletonEnabled": args.line_skeleton,
        "lineSkeletonThresholds": line_skeleton_thresholds,
        "lineGraphEnabled": args.line_graph,
        "lineGraphSettings": args.line_graph_settings,
        "earlyAcceptMeasurementEnabled": args.measure_early_accept,
        "requireSafeAccept": args.require_safe_accept,
        "requireFullspanAccept": args.require_fullspan_accept,
        "selectionPolicy": args.selection_policy,
        "summaryOnly": args.summary_only,
        "earlyAccept": early_accept,
        "safeEarlyAccept": safe_early_accept,
        "fullspanEarlyAccept": fullspan_early_accept,
        "earlyScores": early_scores,
        "waves": wave_events,
        "totalWallMs": round_metric(total_wall_ms),
        "dotReportsUsed": [item["_reportPath"] for item in ordered_dot_reports(dot_reports)],
        "lineReport": line_report["_reportPath"],
        "lineSkeletonSelection": None if line_skeleton_selection is None else summarize_selection(line_skeleton_selection),
        "lineGraphSelection": None if line_graph_selection is None else summarize_selection(line_graph_selection),
        "firstWaveDecision": summarize_selection(first_score),
        "selected": summarize_selection(selected),
        "selectedDetail": selected,
    }
    (run_dir / "parallel-report.json").write_text(f"{json.dumps(report, indent=2)}\n")
    (run_dir / "parallel-report.md").write_text(render_markdown(report))
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


def parse_thresholds(value: str) -> list[int]:
    thresholds = [int(item.strip()) for item in value.split(",") if item.strip()]
    if not thresholds or any(threshold <= 0 for threshold in thresholds):
        raise ValueError("--line-skeleton-thresholds must contain one or more positive integers")
    return thresholds


def policy_name(wave_sizes: list[int]) -> str:
    return f"parallel_wave{'_then'.join(str(size) for size in wave_sizes)}"


def wave_name(index: int) -> str:
    names = ["first", "second", "third", "fourth", "fifth"]
    return names[index] if index < len(names) else f"wave-{index + 1}"


def run_jobs(
    ai_grid: Any,
    provider: str,
    input_work_path: Path,
    label: dict[str, Any],
    run_dir: Path,
    jobs: list[tuple[str, int, Any]],
    on_report: Any | None = None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(jobs)) as executor:
        futures = [
            executor.submit(run_one_job, ai_grid, provider, input_work_path, label, run_dir, kind, index, prompt)
            for kind, index, prompt in jobs
        ]
        for future in concurrent.futures.as_completed(futures):
            report = future.result()
            results.append(report)
            if on_report is not None:
                on_report(report)
    return sorted(results, key=lambda item: (item["_jobKind"], item["_jobIndex"]))


def run_one_job(
    ai_grid: Any,
    provider: str,
    input_work_path: Path,
    label: dict[str, Any],
    run_dir: Path,
    kind: str,
    index: int,
    prompt: Any,
) -> dict[str, Any]:
    job_dir = run_dir / ("line" if kind == "line" else f"dot-{index:02d}")
    job_dir.mkdir(parents=True, exist_ok=True)
    result = ai_grid.run_image_experiment(provider, prompt, input_work_path, label, job_dir)
    report = {
        "sourceId": label["sourceId"],
        "sourceUrl": label["sourceUrl"],
        "inputWorkingImage": str(input_work_path),
        "results": [result],
    }
    report_path = job_dir / "report.json"
    report_path.write_text(f"{json.dumps(report, indent=2)}\n")
    report["_reportPath"] = str(report_path)
    report["_jobKind"] = kind
    report["_jobIndex"] = index
    return report


def report_for(reports: list[dict[str, Any]], kind: str, index: int) -> dict[str, Any]:
    for report in reports:
        if report["_jobKind"] == kind and report["_jobIndex"] == index:
            return report
    raise RuntimeError(f"Missing report for {kind} {index}")


def ordered_dot_reports(dot_reports: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(dot_reports, key=lambda item: item["_jobIndex"])


class DotReportScorer:
    def __init__(
        self,
        dot_fit: Any,
        ai_grid: Any,
        ai_arbiter: Any,
        source_id: str,
        line_report: dict[str, Any],
        label: dict[str, Any],
        write_visuals: bool = True,
        selection_policy: str = "confidence",
    ) -> None:
        self.dot_fit = dot_fit
        self.ai_grid = ai_grid
        self.ai_arbiter = ai_arbiter
        self.source_id = source_id
        self.line_report = line_report
        self.label = label
        self.write_visuals = write_visuals
        self.selection_policy = selection_policy
        self.line_context = dot_fit.prepare_line_context(ai_grid, ai_arbiter, line_report)
        self.variant_cache: dict[str, dict[str, Any]] = {}

    def evaluate(self, dot_reports: list[dict[str, Any]], out_dir: Path) -> dict[str, Any]:
        overlays_dir = out_dir / "overlays"
        if self.write_visuals:
            overlays_dir.mkdir(parents=True, exist_ok=True)
        variants = []
        for order_index, dot_report in enumerate(dot_reports, start=1):
            cache_key = dot_report.get("_reportPath") or f"dot-{dot_report.get('_jobIndex', order_index)}"
            variant = self.variant_cache.get(cache_key)
            if variant is None:
                variant_index = int(dot_report.get("_jobIndex", order_index))
                variant = self.dot_fit.analyze_fixture(
                    self.ai_grid,
                    self.ai_arbiter,
                    self.source_id,
                    self.line_report,
                    dot_report,
                    self.label,
                    overlays_dir,
                    variant_index,
                    line_context=self.line_context,
                    write_visuals=self.write_visuals,
                )
                self.variant_cache[cache_key] = variant
            variants.append(variant)
        return select_from_variants(self.dot_fit, variants, self.selection_policy)


def evaluate(
    dot_fit: Any,
    ai_grid: Any,
    ai_arbiter: Any,
    source_id: str,
    line_report: dict[str, Any],
    dot_reports: list[dict[str, Any]],
    label: dict[str, Any],
    out_dir: Path,
    write_visuals: bool = True,
    selection_policy: str = "confidence",
) -> dict[str, Any]:
    scorer = DotReportScorer(
        dot_fit,
        ai_grid,
        ai_arbiter,
        source_id,
        line_report,
        label,
        write_visuals=write_visuals,
        selection_policy=selection_policy,
    )
    return scorer.evaluate(dot_reports, out_dir)


def evaluate_with_scorer(
    scorer: DotReportScorer | None,
    dot_fit: Any,
    ai_grid: Any,
    ai_arbiter: Any,
    source_id: str,
    line_report: dict[str, Any],
    dot_reports: list[dict[str, Any]],
    label: dict[str, Any],
    out_dir: Path,
    write_visuals: bool = True,
    selection_policy: str = "confidence",
) -> dict[str, Any]:
    if scorer is None:
        scorer = DotReportScorer(
            dot_fit,
            ai_grid,
            ai_arbiter,
            source_id,
            line_report,
            label,
            write_visuals=write_visuals,
            selection_policy=selection_policy,
        )
    return scorer.evaluate(dot_reports, out_dir)


def select_from_variants(dot_fit: Any, variants: list[dict[str, Any]], selection_policy: str = "confidence") -> dict[str, Any]:
    selected = dot_fit.select_best_variant(variants, policy=selection_policy)
    return decorate_dot_selection(dot_fit, selected, variants, selection_policy, include_safe_alternative=True)


def decorate_dot_selection(
    dot_fit: Any,
    selected: dict[str, Any],
    variants: list[dict[str, Any]],
    selection_policy: str,
    include_safe_alternative: bool,
) -> dict[str, Any]:
    manual_seed = dot_fit.select_best_manual_seed_variant(variants)
    selected = dict(selected)
    selected["dotVariantCount"] = len(variants)
    selected["manualSeedVariant"] = dot_fit.variant_summary(manual_seed)
    selected["manualSeedDetail"] = dot_fit.seed_detail(manual_seed)
    selected["manualSeedRecommendation"] = dot_fit.manual_seed_recommendation(selected, manual_seed)
    selected["manualSeedDiffers"] = manual_seed["dotVariantId"] != selected["dotVariantId"]
    selected["earlyReturnSafety"] = dot_fit.early_return_safety(selected)
    selected["selectionPolicy"] = selection_policy
    selected["selectionPolicyTrace"] = dot_fit.selection_policy_trace(variants, selection_policy)
    selected["selectionDiagnostics"] = dot_fit.selection_diagnostics(selected, variants)
    selected["benchmarkOracleDiagnostics"] = dot_fit.benchmark_oracle_diagnostics(selected, variants)
    selected["noLabelRiskDiagnostics"] = dot_fit.no_label_risk_diagnostics(selected, variants)
    dot_fit.attach_no_label_projection_readiness(selected)
    selected["dotVariantsByOrder"] = [dot_fit.variant_summary(variant) for variant in variants]
    selected["dotVariants"] = [dot_fit.variant_summary(variant) for variant in sorted(variants, key=lambda item: item["selectionScore"], reverse=True)]
    if include_safe_alternative:
        safe_selected = select_safe_accepted_variant(dot_fit, variants, selection_policy)
        selected["safeAcceptedAlternative"] = None if safe_selected is None else dot_fit.variant_summary(safe_selected)
        if safe_selected is not None and safe_selected["dotVariantId"] != selected["dotVariantId"]:
            selected["_safeAcceptedSelection"] = decorate_dot_selection(
                dot_fit,
                safe_selected,
                variants,
                selection_policy,
                include_safe_alternative=False,
            )
        fullspan_selected = select_no_label_fullspan_variant(dot_fit, variants, selection_policy)
        selected["fullspanAcceptedAlternative"] = None if fullspan_selected is None else dot_fit.variant_summary(fullspan_selected)
        if fullspan_selected is not None and fullspan_selected["dotVariantId"] != selected["dotVariantId"]:
            selected["_fullspanAcceptedSelection"] = decorate_dot_selection(
                dot_fit,
                fullspan_selected,
                variants,
                selection_policy,
                include_safe_alternative=False,
            )
    return selected


def select_safe_accepted_variant(dot_fit: Any, variants: list[dict[str, Any]], selection_policy: str) -> dict[str, Any] | None:
    safe = [
        variant
        for variant in variants
        if variant["decision"] == "accepted-visible-lattice-geometry" and dot_fit.early_return_safety(variant)["safe"]
    ]
    if not safe:
        return None
    return dot_fit.select_best_variant(safe, policy=selection_policy)


def select_no_label_fullspan_variant(dot_fit: Any, variants: list[dict[str, Any]], selection_policy: str) -> dict[str, Any] | None:
    ready = []
    for variant in variants:
        if variant["decision"] != "accepted-visible-lattice-geometry":
            continue
        decorated = dot_fit.decorate_variant_for_no_label_readiness(variant, variants)
        if decorated.get("projectionModelComparison", {}).get("noLabelProjectionReadiness", {}).get("fullSpanAutoProject"):
            ready.append(decorated)
    if not ready:
        return None
    return dot_fit.select_best_variant(ready, policy=selection_policy)


def evaluate_line_skeleton(
    line_skeleton: Any,
    ai_grid: Any,
    ai_arbiter: Any,
    dot_fit: Any,
    source_id: str,
    line_report: dict[str, Any],
    label: dict[str, Any],
    out_dir: Path,
    thresholds: list[int],
    dot_reports_launched: int,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    line_experiment = line_skeleton.first_image_result(line_report)
    line_path = Path(line_experiment["outputImage"])
    if not line_path.is_absolute():
        line_path = ROOT / line_path
    line_rgb = line_skeleton.load_rgb(line_path)
    line_mask = ai_arbiter.extract_line_mask(ai_grid, line_rgb, line_experiment)
    variants = [
        line_skeleton.analyze_threshold(ai_grid, dot_fit, source_id, label, line_mask, out_dir, threshold)
        for threshold in thresholds
    ]
    selected = dict(max(variants, key=lambda variant: variant["selectionScore"]))
    selected["evidenceSource"] = "line-skeleton"
    selected["dotVariantId"] = f"line-skeleton-t{selected['threshold']}"
    selected["dotVariantCount"] = dot_reports_launched
    selected["lineSkeletonVariants"] = variants
    return selected


def evaluate_line_graph(
    line_graph: Any,
    line_skeleton: Any,
    ai_grid: Any,
    ai_arbiter: Any,
    source_id: str,
    line_report: dict[str, Any],
    label: dict[str, Any],
    out_dir: Path,
    line_prompt_id: str,
    settings_value: str,
    write_visuals: bool = True,
) -> dict[str, Any]:
    overlays_dir = out_dir / "overlays"
    if write_visuals:
        overlays_dir.mkdir(parents=True, exist_ok=True)
    candidates = []
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
        return {
            "evidenceSource": "line-graph",
            "decision": "refuse",
            "dotVariantId": "line-graph",
            "dotVariantCount": None,
            "reasons": ["line graph produced no candidates"],
        }
    selected = line_graph.candidate_to_json(line_graph.select_candidate(candidates))
    return line_graph_to_selection(selected, source_id)


def line_graph_to_selection(selected: dict[str, Any], source_id: str) -> dict[str, Any]:
    usable = line_graph_usable(selected)
    reasons = list(selected.get("reasons") or [])
    if selected.get("trustedGrownExtent") and selected.get("trustedGrownReason") not in reasons:
        reasons.append(selected.get("trustedGrownReason"))
    decision = "accepted-observed-grid-graph" if usable else selected.get("decision", "refuse")
    return {
        **selected,
        "sourceId": source_id,
        "evidenceSource": "line-graph",
        "decision": decision,
        "originalLineGraphDecision": selected.get("decision"),
        "dotVariantId": "line-graph",
        "dotVariantCount": None,
        "reasons": reasons,
        "earlyReturnSafety": {
            "safe": usable,
            "reasons": ["line graph accepted/trusted observed-grid seed"] if usable else ["line graph is not accepted/trusted"],
        },
    }


def line_graph_usable(selection: dict[str, Any] | None) -> bool:
    if not selection:
        return False
    return selection.get("decision") == "accepted-observed-grid-graph" or bool(selection.get("trustedGrownExtent"))


def choose_wave_selection(
    dot_selection: dict[str, Any],
    line_skeleton_selection: dict[str, Any] | None,
    line_graph_selection: dict[str, Any] | None = None,
    require_safe_accept: bool = False,
    require_fullspan_accept: bool = False,
) -> dict[str, Any]:
    if dot_selection["decision"] == "accepted-visible-lattice-geometry":
        if require_fullspan_accept and not is_no_label_fullspan_ready(dot_selection):
            fullspan_selection = dot_selection.get("_fullspanAcceptedSelection")
            if fullspan_selection is not None:
                fullspan_selection = dict(fullspan_selection)
                fullspan_selection.setdefault("evidenceSource", "dot-consensus-fullspan-alternative")
                fullspan_selection["fullspanSelectionApplied"] = True
                return fullspan_selection
            return downgrade_unready_fullspan_accept(dot_selection, "dot-consensus")
        if require_safe_accept and not dot_selection.get("earlyReturnSafety", {}).get("safe"):
            safe_selection = dot_selection.get("_safeAcceptedSelection")
            if safe_selection is not None:
                safe_selection = dict(safe_selection)
                safe_selection.setdefault("evidenceSource", "dot-consensus-safe-alternative")
                safe_selection["safeSelectionApplied"] = True
                return safe_selection
            if line_graph_usable(line_graph_selection):
                return dict(line_graph_selection)
            return downgrade_unsafe_accept(dot_selection, "dot-consensus")
        dot_selection = dict(dot_selection)
        dot_selection.setdefault("evidenceSource", "dot-consensus")
        return dot_selection
    if line_graph_usable(line_graph_selection) and not require_fullspan_accept:
        return dict(line_graph_selection)
    if line_skeleton_selection and line_skeleton_selection["decision"] == "accepted-visible-lattice-geometry":
        if require_fullspan_accept and not is_no_label_fullspan_ready(line_skeleton_selection):
            return downgrade_unready_fullspan_accept(line_skeleton_selection, "line-skeleton")
        if require_safe_accept and not line_skeleton_selection.get("earlyReturnSafety", {}).get("safe"):
            return downgrade_unsafe_accept(line_skeleton_selection, "line-skeleton")
        return line_skeleton_selection
    dot_selection = dict(dot_selection)
    dot_selection.setdefault("evidenceSource", "dot-consensus")
    return dot_selection


def is_no_label_fullspan_ready(selection: dict[str, Any]) -> bool:
    readiness = selection.get("projectionModelComparison", {}).get("noLabelProjectionReadiness", {})
    return bool(readiness.get("fullSpanAutoProject"))


def downgrade_unready_fullspan_accept(selection: dict[str, Any], evidence_source: str) -> dict[str, Any]:
    downgraded = dict(selection)
    downgraded["decision"] = "candidate-visible-lattice-geometry"
    downgraded["evidenceSource"] = f"{selection.get('evidenceSource', evidence_source)}-unready-fullspan"
    reasons = list(selection.get("reasons") or [])
    reason = "require-fullspan-accept was set and this accepted geometry is not no-label full-span projection-ready"
    if reason not in reasons:
        reasons.append(reason)
    downgraded["reasons"] = reasons
    downgraded["unreadyFullspanAcceptedSelection"] = summarize_selection(selection)
    return downgraded


def downgrade_unsafe_accept(selection: dict[str, Any], evidence_source: str) -> dict[str, Any]:
    downgraded = dict(selection)
    downgraded["decision"] = "candidate-visible-lattice-geometry"
    downgraded["evidenceSource"] = f"{selection.get('evidenceSource', evidence_source)}-unsafe-require-safe"
    reasons = list(selection.get("reasons") or [])
    reason = "require-safe-accept was set and this accepted geometry did not pass the early-return safety floor"
    if reason not in reasons:
        reasons.append(reason)
    downgraded["reasons"] = reasons
    downgraded["unsafeAcceptedSelection"] = summarize_selection(selection)
    return downgraded


def should_stop_after_wave(selection: dict[str, Any], require_safe_accept: bool, require_fullspan_accept: bool = False) -> bool:
    if selection["decision"] not in {"accepted-visible-lattice-geometry", "accepted-observed-grid-graph"}:
        return False
    if require_fullspan_accept:
        return is_no_label_fullspan_ready(selection)
    if not require_safe_accept:
        return True
    return bool(selection.get("earlyReturnSafety", {}).get("safe"))


def summarize_selection(selection: dict[str, Any]) -> dict[str, Any]:
    if selection.get("evidenceSource") == "line-graph":
        safety = selection.get("earlyReturnSafety", {})
        return {
            "evidenceSource": "line-graph",
            "decision": selection["decision"],
            "dotVariantId": selection.get("dotVariantId"),
            "dotVariantCount": selection.get("dotVariantCount"),
            "manualSeedVariantId": None,
            "manualSeedMode": None,
            "manualSeedSpan": None,
            "selectionScore": selection.get("graphScore"),
            "homographyInliers": None,
            "spanI": selection.get("spanI"),
            "spanJ": selection.get("spanJ"),
            "truthLineSamplesWithin0_15SquaresPct": selection.get("selectedLineWithin0_15Pct"),
            "observedEdgeHomographyLineWithin0_15Pct": None,
            "truthMeshSamplesWithin0_15SquaresPct": selection.get("meshWithin0_15Pct"),
            "truthMeshVsHomographyGainPct": None,
            "projectionConfidenceLevel": "observed-grid-graph",
            "projectionConfidenceRecommendation": "observed-grid-graph-candidate",
            "observedEdgeVsFullSpanGapPct": None,
            "visibleMeshCellDensity": selection.get("completeCellDensityPct"),
            "projectionReadinessMode": "observed-grid-graph-only",
            "fullSpanAutoProject": False,
            "requiresManualExtentConfirmation": not bool(selection.get("trustedGrownExtent")),
            "observedRegionOnly": True,
            "noLabelProjectionReadinessMode": "no-label-observed-region-candidate",
            "noLabelFullSpanAutoProject": False,
            "noLabelRequiresManualExtentConfirmation": True,
            "noLabelObservedRegionOnly": True,
            "earlyReturnSafe": safety.get("safe", False),
            "earlyReturnSafetyReasons": safety.get("reasons"),
            "reasons": selection.get("reasons"),
            "originalLineGraphDecision": selection.get("originalLineGraphDecision"),
            "lineGraphTrustedGrownExtent": selection.get("trustedGrownExtent"),
            "lineGraphTrustedGrownReason": selection.get("trustedGrownReason"),
            "lineGraphSelectedLineWithin0_15Pct": selection.get("selectedLineWithin0_15Pct"),
            "lineGraphMeshWithin0_15Pct": selection.get("meshWithin0_15Pct"),
        }
    fit = selection.get("fit", {})
    bench = selection.get("benchmark", {})
    manual = selection.get("manualSeedRecommendation", {})
    safety = selection.get("earlyReturnSafety", {})
    projection = selection.get("projectionModelComparison", {})
    confidence = projection.get("fullSpanProjectionConfidence", {})
    readiness = projection.get("projectionReadiness", {})
    no_label_readiness = projection.get("noLabelProjectionReadiness", {})
    return {
        "evidenceSource": selection.get("evidenceSource", "dot-consensus"),
        "decision": selection["decision"],
        "dotVariantId": selection.get("dotVariantId"),
        "dotVariantCount": selection.get("dotVariantCount"),
        "manualSeedVariantId": manual.get("recommendedVariantId"),
        "manualSeedMode": manual.get("mode"),
        "manualSeedSpan": manual.get("recommendedSpan"),
        "selectionScore": selection.get("selectionScore"),
        "homographyInliers": fit.get("homographyInliers"),
        "spanI": fit.get("spanI"),
        "spanJ": fit.get("spanJ"),
        "truthLineSamplesWithin0_15SquaresPct": bench.get("truthLineSamplesWithin0_15SquaresPct"),
        "observedEdgeHomographyLineWithin0_15Pct": projection.get("observedEdgeHomographyLineWithin0_15Pct"),
        "truthMeshSamplesWithin0_15SquaresPct": bench.get("truthMeshSamplesWithin0_15SquaresPct"),
        "truthMeshVsHomographyGainPct": bench.get("truthMeshVsHomographyGainPct"),
        "projectionConfidenceLevel": confidence.get("level"),
        "projectionConfidenceRecommendation": confidence.get("recommendation"),
        "observedEdgeVsFullSpanGapPct": confidence.get("observedEdgeVsFullSpanGapPct"),
        "visibleMeshCellDensity": projection.get("visibleMeshCellDensity"),
        "projectionReadinessMode": readiness.get("mode"),
        "fullSpanAutoProject": readiness.get("fullSpanAutoProject"),
        "requiresManualExtentConfirmation": readiness.get("requiresManualExtentConfirmation"),
        "observedRegionOnly": readiness.get("observedRegionOnly"),
        "noLabelProjectionReadinessMode": no_label_readiness.get("mode"),
        "noLabelFullSpanAutoProject": no_label_readiness.get("fullSpanAutoProject"),
        "noLabelRequiresManualExtentConfirmation": no_label_readiness.get("requiresManualExtentConfirmation"),
        "noLabelObservedRegionOnly": no_label_readiness.get("observedRegionOnly"),
        "earlyReturnSafe": safety.get("safe", False),
        "earlyReturnSafetyReasons": safety.get("reasons"),
        "reasons": selection.get("reasons"),
    }


def render_markdown(report: dict[str, Any]) -> str:
    selected = report["selected"]
    first = report["firstWaveDecision"]
    lines = [
        "# Parallel AI Grid Current Recipe",
        "",
        f"- Source: `{report['sourceId']}`",
        f"- Policy: `{report['policy']}`",
        f"- Selection policy: `{report['selectionPolicy']}`",
        f"- Line skeleton enabled: `{report['lineSkeletonEnabled']}`",
        f"- Line graph enabled: `{report['lineGraphEnabled']}`",
        f"- Require safe accept: `{report['requireSafeAccept']}`",
        f"- Require full-span accept: `{report['requireFullspanAccept']}`",
        f"- Summary only: `{report['summaryOnly']}`",
        f"- Total wall time: `{round_metric(report['totalWallMs'] / 1000)}s`",
        f"- First wave: `{round_metric(report['waves'][0]['wallMs'] / 1000)}s`, `{first['decision']}` via `{first['evidenceSource']}`",
        f"- Final decision: `{selected['decision']}`",
        f"- Final evidence: `{selected['evidenceSource']}`",
        f"- Dot samples used: `{selected['dotVariantCount']}`",
        f"- Manual correction seed: `{selected.get('manualSeedVariantId')}` `{selected.get('manualSeedSpan')}` `{selected.get('manualSeedMode')}`",
        f"- Homography line <=.15: `{selected['truthLineSamplesWithin0_15SquaresPct']}`",
        f"- Observed-edge homography <=.15: `{selected.get('observedEdgeHomographyLineWithin0_15Pct')}`",
        f"- Mesh line <=.15: `{selected['truthMeshSamplesWithin0_15SquaresPct']}`",
        f"- Projection confidence: `{selected.get('projectionConfidenceLevel')}` `{selected.get('projectionConfidenceRecommendation')}`",
        f"- Projection readiness: `{selected.get('projectionReadinessMode')}` auto-full-span=`{selected.get('fullSpanAutoProject')}` manual-extent=`{selected.get('requiresManualExtentConfirmation')}` observed-only=`{selected.get('observedRegionOnly')}`",
        f"- No-label projection readiness: `{selected.get('noLabelProjectionReadinessMode')}` auto-full-span=`{selected.get('noLabelFullSpanAutoProject')}` manual-extent=`{selected.get('noLabelRequiresManualExtentConfirmation')}` observed-only=`{selected.get('noLabelObservedRegionOnly')}`",
        "",
        "| Wave | Jobs | Wall Time |",
        "| --- | ---: | ---: |",
    ]
    for wave in report["waves"]:
        lines.append(f"| `{wave['wave']}` | {wave['jobs']} | {round_metric(wave['wallMs'] / 1000)}s |")
    if report.get("earlyAcceptMeasurementEnabled"):
        early = report.get("earlyAccept")
        safe_early = report.get("safeEarlyAccept")
        fullspan_early = report.get("fullspanEarlyAccept")
        lines.extend(["", "## Early Accept Measurement", ""])
        if early:
            lines.append(
                f"First accepted geometry appeared after `{round_metric(early['elapsedMs'] / 1000)}s` "
                f"with `{early['completedDotReports']}` completed dot reports; the command still drained launched jobs."
            )
        else:
            lines.append("No accepted geometry appeared before the launched jobs finished.")
        if safe_early:
            lines.append(
                f"First early-return-safe geometry appeared after `{round_metric(safe_early['elapsedMs'] / 1000)}s` "
                f"with `{safe_early['completedDotReports']}` completed dot reports."
            )
        else:
            lines.append("No early-return-safe geometry appeared before the launched jobs finished.")
        if fullspan_early:
            lines.append(
                f"First no-label full-span projection-ready geometry appeared after `{round_metric(fullspan_early['elapsedMs'] / 1000)}s` "
                f"with `{fullspan_early['completedDotReports']}` completed dot reports."
            )
        else:
            lines.append("No no-label full-span projection-ready geometry appeared before the launched jobs finished.")
    lines.append("")
    return "\n".join(lines)


def render_console(report: dict[str, Any]) -> str:
    selected = report["selected"]
    first = report["firstWaveDecision"]
    return "\n".join(
        [
            f"Parallel AI grid current: {selected['decision']} for {report['sourceId']}",
            f"- evidence: {selected['evidenceSource']}",
            f"- selection policy: {report['selectionPolicy']}",
            f"- line graph enabled: {report['lineGraphEnabled']}",
            f"- require safe accept: {report['requireSafeAccept']}",
            f"- require full-span accept: {report['requireFullspanAccept']}",
            f"- summary only: {report['summaryOnly']}",
            f"- total wall: {round_metric(report['totalWallMs'] / 1000)}s",
            f"- first wave: {round_metric(report['waves'][0]['wallMs'] / 1000)}s -> {first['decision']} via {first['evidenceSource']}",
            f"- dot samples used: {selected['dotVariantCount']}",
            f"- manual seed: {selected.get('manualSeedVariantId')} {selected.get('manualSeedSpan')} {selected.get('manualSeedMode')}",
            f"- truth line <=.15: {selected['truthLineSamplesWithin0_15SquaresPct']}",
            f"- observed-edge <=.15: {selected.get('observedEdgeHomographyLineWithin0_15Pct')}",
            f"- mesh <=.15: {selected.get('truthMeshSamplesWithin0_15SquaresPct')}",
            f"- projection confidence: {selected.get('projectionConfidenceLevel')} {selected.get('projectionConfidenceRecommendation')}",
            f"- projection readiness: {selected.get('projectionReadinessMode')} auto-full-span={selected.get('fullSpanAutoProject')} manual-extent={selected.get('requiresManualExtentConfirmation')} observed-only={selected.get('observedRegionOnly')}",
            f"- no-label projection readiness: {selected.get('noLabelProjectionReadinessMode')} auto-full-span={selected.get('noLabelFullSpanAutoProject')} manual-extent={selected.get('noLabelRequiresManualExtentConfirmation')} observed-only={selected.get('noLabelObservedRegionOnly')}",
            *early_console_lines(report),
            f"Artifacts: {report['outDir']}/parallel-report.md",
        ]
    )


def elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def early_console_lines(report: dict[str, Any]) -> list[str]:
    if not report.get("earlyAcceptMeasurementEnabled"):
        return []
    early = report.get("earlyAccept")
    safe_early = report.get("safeEarlyAccept")
    fullspan_early = report.get("fullspanEarlyAccept")
    lines = []
    if not early:
        lines.append("- early accept: none before drain")
    else:
        lines.append(f"- early accept: {round_metric(early['elapsedMs'] / 1000)}s after {early['completedDotReports']} completed dots")
    if not safe_early:
        lines.append("- safe early accept: none before drain")
    else:
        lines.append(
            f"- safe early accept: {round_metric(safe_early['elapsedMs'] / 1000)}s after {safe_early['completedDotReports']} completed dots"
        )
    if not fullspan_early:
        lines.append("- full-span early accept: none before drain")
    else:
        lines.append(
            f"- full-span early accept: {round_metric(fullspan_early['elapsedMs'] / 1000)}s after {fullspan_early['completedDotReports']} completed dots"
        )
    return lines


def slugify(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "-" for char in value).strip("-")


def round_metric(value: float) -> float:
    return round(float(value), 3)


if __name__ == "__main__":
    main()
