#!/usr/bin/env python3
"""Fit visible lattice geometry from AI-generated dot and line evidence.

This is a discovery/eval script. It does not use fixture labels to fit the
geometry. Labels are used only for the benchmark section of the report.
"""

from __future__ import annotations

import argparse
import copy
import importlib.util
import json
import math
import re
import sys
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[1]
AI_GRID_PATH = ROOT / "scripts" / "ai-grid-experiment.py"
AI_ARBITER_PATH = ROOT / "scripts" / "ai-evidence-arbiter.py"
LABELS_PATH = ROOT / "input" / "map-grid-labels.json"
DEFAULT_OUT_DIR = ROOT / "test-results" / "ai-dot-lattice-fit"


@dataclass(frozen=True)
class Edge:
    left: int
    right: int
    family: int
    delta: tuple[int, int]
    distance: float
    angle: float
    support: float


@dataclass
class FitResult:
    decision: str
    reasons: list[str]
    homography: np.ndarray | None
    coordinates: dict[int, tuple[int, int]]
    inlier_indexes: list[int]
    metrics: dict[str, Any]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--line-reports-glob", default="test-results/ai-grid-experiments-grok-white-v1/*/report.json")
    parser.add_argument(
        "--dot-reports-glob",
        action="append",
        default=None,
        help="Dot report glob. Repeat to evaluate and select among multiple AI dot samples per source image.",
    )
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--summary-only", action="store_true", help="Skip overlay/contact-sheet image generation and write metric reports only.")
    parser.add_argument("--line-prompt-id", default="white-grid-exact-copy-no-marks-v1")
    parser.add_argument("--dot-prompt-id", default="white-intersection-dots-no-lines-v1")
    parser.add_argument(
        "--selection-policy",
        choices=["confidence", "guarded-mesh-density", "guarded-risk-aware"],
        default="confidence",
        help=(
            "Auto-selection policy after all available dot variants are scored. "
            "Guarded challengers use only no-label geometry metrics and remain opt-in."
        ),
    )
    args = parser.parse_args()

    ai_grid = load_module("ai_grid_experiment", AI_GRID_PATH)
    ai_arbiter = load_module("ai_evidence_arbiter", AI_ARBITER_PATH)
    labels = {label["sourceId"]: label for label in json.loads(LABELS_PATH.read_text())["labels"]}
    line_reports = load_reports(args.line_reports_glob, args.line_prompt_id)
    dot_reports = load_report_groups(args.dot_reports_glob or ["test-results/ai-grid-experiments-grok-dots-realhome/*/report.json"], args.dot_prompt_id)

    out_dir = Path(args.out_dir)
    overlays_dir = out_dir / "overlays"
    if not args.summary_only:
        overlays_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for source_id in sorted(set(line_reports) & set(dot_reports)):
        label = labels.get(source_id)
        if not label:
            continue
        line_context = prepare_line_context(ai_grid, ai_arbiter, line_reports[source_id])
        image_context = prepare_original_image_context(ai_grid, label, line_context["mask"].shape)
        variants = [
            analyze_fixture(
                ai_grid,
                ai_arbiter,
                source_id,
                line_reports[source_id],
                dot_report,
                label,
                overlays_dir,
                variant_index,
                line_context=line_context,
                image_context=image_context,
                write_visuals=not args.summary_only,
            )
            for variant_index, dot_report in enumerate(dot_reports[source_id], start=1)
        ]
        selected = select_best_variant(variants, policy=args.selection_policy)
        manual_seed = select_best_manual_seed_variant(variants)
        selected["dotVariantCount"] = len(variants)
        selected["manualSeedVariant"] = variant_summary(manual_seed)
        selected["manualSeedDetail"] = seed_detail(manual_seed)
        selected["manualSeedRecommendation"] = manual_seed_recommendation(selected, manual_seed)
        selected["manualSeedDiffers"] = manual_seed["dotVariantId"] != selected["dotVariantId"]
        selected["earlyReturnSafety"] = early_return_safety(selected)
        selected["selectionPolicyTrace"] = selection_policy_trace(variants, args.selection_policy)
        selected["selectionDiagnostics"] = selection_diagnostics(selected, variants)
        selected["benchmarkOracleDiagnostics"] = benchmark_oracle_diagnostics(selected, variants)
        selected["noLabelRiskDiagnostics"] = no_label_risk_diagnostics(selected, variants)
        attach_no_label_projection_readiness(selected)
        selected["dotVariantsByOrder"] = [variant_summary(variant) for variant in variants]
        selected["dotVariants"] = [variant_summary(variant) for variant in sorted(variants, key=lambda item: item["selectionScore"], reverse=True)]
        selected["retryPolicies"] = retry_policy_summaries(variants, args.selection_policy)
        results.append(selected)

    report = {
        "outDir": str(out_dir),
        "selectionMode": selection_mode_description(args.selection_policy),
        "selectionPolicy": args.selection_policy,
        "summaryOnly": args.summary_only,
        "summary": summarize(results),
        "results": results,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(f"{json.dumps(report, indent=2)}\n")
    (out_dir / "report.md").write_text(render_markdown(report))
    if not args.summary_only:
        write_contact_sheet(results, out_dir)
    print(render_console(report))


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_reports(pattern: str, prompt_id: str | None = None) -> dict[str, dict[str, Any]]:
    reports = {}
    for path in sorted(ROOT.glob(pattern)):
        report = json.loads(path.read_text())
        if prompt_id and not report_has_prompt(report, prompt_id):
            continue
        report["_reportPath"] = str(path)
        reports[report["sourceId"]] = report
    return reports


def load_report_groups(patterns: list[str], prompt_id: str | None = None) -> dict[str, list[dict[str, Any]]]:
    reports: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[Path] = set()
    for pattern in patterns:
        for path in sorted(ROOT.glob(pattern)):
            if path in seen:
                continue
            seen.add(path)
            report = json.loads(path.read_text())
            if prompt_id and not report_has_prompt(report, prompt_id):
                continue
            report["_reportPath"] = str(path)
            reports[report["sourceId"]].append(report)
    return reports


def report_has_prompt(report: dict[str, Any], prompt_id: str) -> bool:
    return any(
        result.get("ok") and result.get("outputImage") and result.get("promptId") == prompt_id
        for result in report.get("results", [])
    )


def analyze_fixture(
    ai_grid: Any,
    ai_arbiter: Any,
    source_id: str,
    line_report: dict[str, Any],
    dot_report: dict[str, Any],
    label: dict[str, Any],
    overlays_dir: Path,
    variant_index: int = 1,
    line_context: dict[str, Any] | None = None,
    image_context: dict[str, Any] | None = None,
    write_visuals: bool = True,
) -> dict[str, Any]:
    line_context = line_context or prepare_line_context(ai_grid, ai_arbiter, line_report)
    image_context = image_context or prepare_original_image_context(ai_grid, label, line_context["mask"].shape)
    line_experiment = line_context["experiment"]
    dot_experiment = first_image_result(dot_report)
    line_path = line_context["path"]
    dot_path = resolve_output_path(dot_experiment["outputImage"])
    dot_rgb = load_rgb(dot_path)
    line_mask = line_context["mask"]
    dot_mask = ai_grid.extract_signal_mask(dot_rgb, "white_mask")
    dots = ai_arbiter.extract_dots(dot_mask)
    points = np.float32([[dot.x, dot.y] for dot in dots])

    fit = fit_visible_lattice(points, line_mask, line_context=line_context)
    fit.metrics.update(original_image_line_contrast(image_context["gray"], fit))
    benchmark = benchmark_fit(ai_grid, label, fit, points, line_mask)
    selection_score = selection_score_for_fit(fit.metrics, fit.decision)
    overlay_path = write_overlay(ai_grid, label, source_id, points, line_mask, fit, overlays_dir, variant_index) if write_visuals else None
    observed_mesh = observed_mesh_geometry(points, fit)

    return {
        "sourceId": source_id,
        "dotVariantId": f"dot-v{variant_index:02d}",
        "dotReportPath": dot_report.get("_reportPath"),
        "lineElapsedMs": line_experiment.get("elapsedMs"),
        "dotElapsedMs": dot_experiment.get("elapsedMs"),
        "selectionScore": round_metric(selection_score),
        "manualSeedScore": round_metric(manual_seed_score_for_fit(fit.metrics, fit.decision)),
        "decision": fit.decision,
        "reasons": fit.reasons,
        "lineImage": str(line_path),
        "dotImage": str(dot_path),
        "overlayImage": None if overlay_path is None else str(overlay_path),
        "fullExtentStatus": "refused-needs-known-dimensions-or-manual-confirmation",
        "fit": fit.metrics,
        "observedMesh": observed_mesh,
        "projectionModelComparison": projection_model_comparison(benchmark, observed_mesh, fit.metrics, fit.decision),
        "benchmark": benchmark,
    }


def prepare_line_context(ai_grid: Any, ai_arbiter: Any, line_report: dict[str, Any]) -> dict[str, Any]:
    line_experiment = first_image_result(line_report)
    line_path = resolve_output_path(line_experiment["outputImage"])
    line_rgb = load_rgb(line_path)
    line_mask = ai_arbiter.extract_line_mask(ai_grid, line_rgb, line_experiment)
    return {
        "experiment": line_experiment,
        "path": line_path,
        "mask": line_mask,
        "lineDistance": line_distance_transform(line_mask),
        "lineMaskDilated": cv2.dilate(line_mask, np.ones((3, 3), np.uint8), iterations=1),
    }


def prepare_original_image_context(ai_grid: Any, label: dict[str, Any], mask_shape: tuple[int, int]) -> dict[str, Any]:
    source_path = ROOT / label["sourceUrl"].removeprefix("/")
    image = ai_grid.load_display_image(source_path)
    height, width = mask_shape[:2]
    if image.size != (width, height):
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    rgb = np.array(image)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32)
    return {"gray": gray}


def original_image_line_contrast(gray: np.ndarray, fit: FitResult) -> dict[str, Any]:
    if fit.homography is None or not fit.coordinates:
        return empty_original_image_line_contrast()
    values = list(fit.coordinates.values())
    min_i, max_i = min(value[0] for value in values), max(value[0] for value in values)
    min_j, max_j = min(value[1] for value in values), max(value[1] for value in values)
    offset = max(2.0, min(5.0, float(fit.metrics.get("medianNearestNeighborPx") or 24.0) * 0.14))
    grid_samples: list[list[float]] = []
    tangent_samples: list[list[float]] = []
    for i in range(min_i, max_i + 1):
        for j in np.linspace(min_j, max_j, 28):
            grid_samples.append([i, float(j)])
            tangent_samples.append([i, float(j) + 0.2])
    for j in range(min_j, max_j + 1):
        for i in np.linspace(min_i, max_i, 28):
            grid_samples.append([float(i), j])
            tangent_samples.append([float(i) + 0.2, j])
    if not grid_samples:
        return empty_original_image_line_contrast()
    points = cv2.perspectiveTransform(np.float32(grid_samples).reshape(1, -1, 2), fit.homography).reshape(-1, 2)
    tangent_points = cv2.perspectiveTransform(np.float32(tangent_samples).reshape(1, -1, 2), fit.homography).reshape(-1, 2)
    tangent = tangent_points - points
    normal = np.stack([-tangent[:, 1], tangent[:, 0]], axis=1)
    magnitude = np.linalg.norm(normal, axis=1)
    valid_normal = magnitude > 1e-4
    normal[valid_normal] = normal[valid_normal] / magnitude[valid_normal, None]
    center, center_inside = sample_gray_nearest(gray, points)
    side_a, side_a_inside = sample_gray_nearest(gray, points + normal * offset)
    side_b, side_b_inside = sample_gray_nearest(gray, points - normal * offset)
    valid = valid_normal & center_inside & side_a_inside & side_b_inside
    if int(valid.sum()) < 20:
        return {
            **empty_original_image_line_contrast(),
            "imageLineContrastSamples": int(valid.sum()),
        }
    contrast = ((side_a[valid] + side_b[valid]) * 0.5) - center[valid]
    return {
        "imageLineContrastSamples": int(valid.sum()),
        "imageLineContrastMedian": round_metric(float(np.median(contrast))),
        "imageLineContrastMean": round_metric(float(np.mean(contrast))),
        "imageLineContrastPositivePct": round_metric(float(np.mean(contrast > 1.5) * 100.0)),
    }


def empty_original_image_line_contrast() -> dict[str, Any]:
    return {
        "imageLineContrastSamples": 0,
        "imageLineContrastMedian": None,
        "imageLineContrastMean": None,
        "imageLineContrastPositivePct": None,
    }


def sample_gray_nearest(gray: np.ndarray, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    height, width = gray.shape[:2]
    xs = np.rint(points[:, 0]).astype(int)
    ys = np.rint(points[:, 1]).astype(int)
    inside = (xs >= 0) & (xs < width) & (ys >= 0) & (ys < height)
    values = np.zeros(len(points), dtype=np.float32)
    values[inside] = gray[ys[inside], xs[inside]]
    return values, inside


def first_image_result(report: dict[str, Any]) -> dict[str, Any]:
    for result in report.get("results", []):
        if result.get("ok") and result.get("outputImage"):
            return result
    raise RuntimeError(f"No successful image result in {report.get('_reportPath')}")


def resolve_output_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.array(ImageOps.exif_transpose(image).convert("RGB"))


def fit_visible_lattice(points: np.ndarray, line_mask: np.ndarray, line_context: dict[str, Any] | None = None) -> FitResult:
    line_context = line_context or {
        "lineDistance": line_distance_transform(line_mask),
        "lineMaskDilated": cv2.dilate(line_mask, np.ones((3, 3), np.uint8), iterations=1),
    }
    if len(points) < 40:
        return refused("too few compact dots", {"dotCount": int(len(points))})
    median_nn = median_nearest_neighbor(points)
    threshold_px = max(4.0, min(7.0, median_nn * 0.10))
    line_distance = line_context["lineDistance"]
    line_close = points_near_line(points, line_distance, threshold_px)
    filtered_points = points[line_close]
    filtered_original_indexes = np.nonzero(line_close)[0]
    if len(filtered_points) < 40:
        return refused(
            "too few dots agree with line mask",
            {"dotCount": int(len(points)), "lineAgreementDots": int(len(filtered_points)), "medianNearestNeighborPx": round_metric(median_nn)},
        )

    median_nn = median_nearest_neighbor(filtered_points)
    candidate_edges = build_candidate_edges(filtered_points, line_context["lineMaskDilated"], median_nn)
    axis_results = []
    dot_axes = dominant_axes(candidate_edges)
    if len(dot_axes) == 2:
        dot_axis_result = fit_with_axis_candidate(
            points,
            filtered_points,
            filtered_original_indexes,
            median_nn,
            candidate_edges,
            dot_axes,
            "dot-neighbor-axes",
            line_mask,
            line_context,
        )
        axis_results.append(dot_axis_result)
    else:
        dot_axis_result = None

    if dot_axis_result is not None and dot_axis_result.decision == "accepted-visible-lattice-geometry":
        best_axis_result = dot_axis_result
        axis_policy = "kept accepted dot-neighbor axis fit"
    else:
        line_axes = cached_line_axis_angles(line_context, line_mask)
        if len(line_axes) == 2:
            axis_results.append(
                fit_with_axis_candidate(
                    points,
                    filtered_points,
                    filtered_original_indexes,
                    median_nn,
                    candidate_edges,
                    line_axes,
                    "line-mask-angle-prior",
                    line_mask,
                    line_context,
                )
            )
        if not axis_results:
            return refused("could not find two dot-neighbor or line-mask axis families", base_metrics(points, filtered_points, median_nn, candidate_edges))
        best_axis_result = max(axis_results, key=lambda item: selection_score_for_fit(item.metrics, item.decision))
        axis_policy = "used best available axis candidate"
    best_axis_result.metrics["axisCandidateCount"] = len(axis_results)
    best_axis_result.metrics["axisCandidateModes"] = [result.metrics.get("axisMode") for result in axis_results]
    best_axis_result.metrics["axisSelectedMode"] = best_axis_result.metrics.get("axisMode")
    best_axis_result.metrics["axisSelectionPolicy"] = axis_policy
    best_axis_result.metrics["axisCandidateScores"] = [
        {
            "mode": result.metrics.get("axisMode"),
            "decision": result.decision,
            "score": round_metric(selection_score_for_fit(result.metrics, result.decision)),
            "spanI": result.metrics.get("spanI"),
            "spanJ": result.metrics.get("spanJ"),
            "homographyInliers": result.metrics.get("homographyInliers"),
        }
        for result in axis_results
    ]
    return best_axis_result


def cached_line_axis_angles(line_context: dict[str, Any], line_mask: np.ndarray) -> list[float]:
    if "lineAxisAngles" not in line_context:
        line_context["lineAxisAngles"] = line_axis_angles_from_mask(line_mask)
    return line_context.get("lineAxisAngles") or []


def fit_with_axis_candidate(
    points: np.ndarray,
    filtered_points: np.ndarray,
    filtered_original_indexes: np.ndarray,
    median_nn: float,
    candidate_edges: list[dict[str, Any]],
    axes: list[float],
    axis_mode: str,
    line_mask: np.ndarray,
    line_context: dict[str, Any],
) -> FitResult:
    family_edges = assign_edge_families(candidate_edges, axes)
    sparse_edges = keep_local_step_edges(family_edges, len(filtered_points), axes)
    components = assign_lattice_coordinates(sparse_edges, len(filtered_points))
    if not components:
        metrics = base_metrics(points, filtered_points, median_nn, sparse_edges, axes)
        metrics["axisMode"] = axis_mode
        return refused("no connected lattice component", metrics)

    ranked_components = sorted(components, key=lambda item: len(item["coordinates"]), reverse=True)
    component_results = [
        fit_lattice_component(points, filtered_points, filtered_original_indexes, median_nn, sparse_edges, axes, axis_mode, line_mask, line_context, component, rank)
        for rank, component in enumerate(ranked_components[:6], start=1)
        if len(component["coordinates"]) >= 40
    ]
    if not component_results:
        largest = ranked_components[0]
        coordinates = largest["coordinates"]
        conflict_rate = largest["conflicts"] / max(1, largest["edgeVisits"])
        result = refused(
            "largest lattice component is too small",
            base_metrics(points, filtered_points, median_nn, sparse_edges, axes, coordinates, conflict_rate),
        )
        result.metrics["axisMode"] = axis_mode
        return result

    best_result = max(component_results, key=lambda item: selection_score_for_fit(item.metrics, item.decision))
    best_result.metrics["componentPoolEvaluated"] = len(component_results)
    best_result.metrics["componentPoolSelectedRank"] = best_result.metrics.get("componentRankBySize")
    best_result.metrics["componentPoolLargestDecision"] = component_results[0].decision
    best_result.metrics["componentPoolLargestScore"] = round_metric(selection_score_for_fit(component_results[0].metrics, component_results[0].decision))
    best_result.metrics["componentPoolSelectedScore"] = round_metric(selection_score_for_fit(best_result.metrics, best_result.decision))
    return best_result


def fit_lattice_component(
    points: np.ndarray,
    filtered_points: np.ndarray,
    filtered_original_indexes: np.ndarray,
    median_nn: float,
    sparse_edges: list[Edge],
    axes: list[float],
    axis_mode: str,
    line_mask: np.ndarray,
    line_context: dict[str, Any],
    component: dict[str, Any],
    rank: int,
) -> FitResult:
    coordinates = component["coordinates"]
    conflict_rate = component["conflicts"] / max(1, component["edgeVisits"])
    src = np.float32([coordinates[index] for index in sorted(coordinates)])
    dst = np.float32([filtered_points[index] for index in sorted(coordinates)])
    reproj_threshold = max(3.0, min(8.0, median_nn * 0.14))
    homography, inlier_mask = cv2.findHomography(src, dst, cv2.RANSAC, reproj_threshold, maxIters=5000, confidence=0.995)
    if homography is None or inlier_mask is None:
        return refused(
            "homography fit failed",
            base_metrics(points, filtered_points, median_nn, sparse_edges, axes, coordinates, conflict_rate),
        )
    inliers = [index for index, keep in zip(sorted(coordinates), inlier_mask.ravel().tolist()) if int(keep) == 1]
    fit_metrics = geometry_metrics(homography, coordinates, filtered_points, inliers, median_nn, line_mask, line_context)
    fit_metrics.update(base_metrics(points, filtered_points, median_nn, sparse_edges, axes, coordinates, conflict_rate))
    fit_metrics["homography"] = [[round_metric(value) for value in row] for row in homography.tolist()]
    fit_metrics["axisMode"] = axis_mode
    fit_metrics["componentRankBySize"] = rank
    fit_metrics["componentSize"] = len(coordinates)

    decision, reasons = decide_fit(fit_metrics)
    original_inliers = [int(filtered_original_indexes[index]) for index in inliers]
    original_coordinates = {int(filtered_original_indexes[index]): value for index, value in coordinates.items()}
    return FitResult(decision, reasons, homography, original_coordinates, original_inliers, fit_metrics)


def refused(reason: str, metrics: dict[str, Any]) -> FitResult:
    return FitResult("refuse", [reason], None, {}, [], metrics)


def selection_mode_description(policy: str) -> str:
    if policy == "guarded-risk-aware":
        return (
            "no-label guarded risk-aware challenger; starts from guarded mesh-density, "
            "then may switch to a fuller same-error accepted variant only when the selected fit has "
            "borderline reprojection error plus high coordinate conflicts, or to a compact high-precision "
            "accepted variant only when the selected fit has weak lower-quartile support plus lower inlier ratio; "
            "labels are used only for benchmark fields"
        )
    if policy == "guarded-mesh-density":
        return (
            "no-label guarded mesh-density challenger; starts from highest-confidence visible geometry, "
            "then may switch to an early-return-safe accepted variant with materially denser observed inlier mesh; "
            "labels are used only for benchmark fields"
        )
    return "no-label highest-confidence visible geometry; labels are used only for benchmark fields"


def select_best_variant(variants: list[dict[str, Any]], policy: str = "confidence") -> dict[str, Any]:
    if not variants:
        raise RuntimeError("No variants to select")
    best = max(variants, key=lambda item: item["selectionScore"])
    if policy in ("guarded-mesh-density", "guarded-risk-aware"):
        accepted = [variant for variant in variants if variant["decision"] == "accepted-visible-lattice-geometry"]
        if accepted:
            best = select_guarded_mesh_density_variant(best, accepted)
            if policy == "guarded-risk-aware":
                best = select_borderline_conflict_fuller_variant(best, accepted) or best
                best = select_precise_subset_challenger(best, accepted) or best
                best = select_high_precision_compact_challenger(best, accepted) or best
    return best


def selection_policy_trace(variants: list[dict[str, Any]], policy: str = "confidence") -> dict[str, Any]:
    if not variants:
        return {"policy": policy, "path": []}
    best = max(variants, key=lambda item: item["selectionScore"])
    path = [selection_trace_step("initial-confidence", best, changed=True)]
    if policy not in ("guarded-mesh-density", "guarded-risk-aware"):
        return {"policy": policy, "path": path, "finalVariantId": best["dotVariantId"]}
    accepted = [variant for variant in variants if variant["decision"] == "accepted-visible-lattice-geometry"]
    if not accepted:
        return {"policy": policy, "path": path, "finalVariantId": best["dotVariantId"]}
    next_best = select_guarded_mesh_density_variant(best, accepted)
    path.append(selection_trace_step("guarded-mesh-density", next_best, next_best["dotVariantId"] != best["dotVariantId"]))
    best = next_best
    if policy == "guarded-risk-aware":
        challenger = select_borderline_conflict_fuller_variant(best, accepted)
        next_best = challenger or best
        path.append(selection_trace_step("borderline-conflict-fuller", next_best, challenger is not None))
        best = next_best
        challenger = select_precise_subset_challenger(best, accepted)
        next_best = challenger or best
        path.append(selection_trace_step("precise-subset", next_best, challenger is not None))
        best = next_best
        challenger = select_high_precision_compact_challenger(best, accepted)
        next_best = challenger or best
        path.append(selection_trace_step("high-precision-compact", next_best, challenger is not None))
        best = next_best
    return {"policy": policy, "path": path, "finalVariantId": best["dotVariantId"]}


def selection_trace_step(stage: str, variant: dict[str, Any], changed: bool) -> dict[str, Any]:
    fit = variant.get("fit", {})
    return {
        "stage": stage,
        "variantId": variant["dotVariantId"],
        "changed": bool(changed),
        "decision": variant["decision"],
        "selectionScore": round_metric(float(variant["selectionScore"])),
        "spanI": fit.get("spanI"),
        "spanJ": fit.get("spanJ"),
        "homographyInlierRatio": fit.get("homographyInlierRatio"),
        "p90ReprojectionErrorCells": fit.get("p90ReprojectionErrorCells"),
        "p25LineSupport": fit.get("p25LineSupport"),
        "coordinateConflictPct": fit.get("coordinateConflictPct"),
        "earlyReturnSafe": early_return_safety(variant)["safe"],
    }


def select_best_manual_seed_variant(variants: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [variant for variant in variants if variant["decision"] != "refuse"]
    if not usable:
        return max(variants, key=lambda item: item["manualSeedScore"])
    return max(usable, key=lambda item: item["manualSeedScore"])


def retry_policy_summaries(variants: list[dict[str, Any]], selection_policy: str = "confidence") -> dict[str, Any]:
    policies: dict[str, Any] = {}
    for count in range(1, 9):
        sampled = variants[: min(count, len(variants))]
        policies[f"fixed{count}"] = retry_policy_choice(select_best_variant(sampled, policy=selection_policy), len(sampled), "fixed sample count", sampled)
    for count in range(1, 7):
        policies[f"parallel_fixed{count}"] = parallel_fixed_retry_policy(variants, count, selection_policy=selection_policy)
        policies[f"stream_fixed{count}"] = streaming_fixed_retry_policy(variants, count, selection_policy=selection_policy)
    policies["adaptive3"] = adaptive_retry_policy(variants, max_samples=3, allow_extra=False, selection_policy=selection_policy)
    policies["adaptive3_plus_candidate4"] = adaptive_retry_policy(variants, max_samples=3, allow_extra=True, selection_policy=selection_policy)
    policies["adaptive8"] = adaptive_retry_policy(variants, max_samples=min(8, len(variants)), allow_extra=False, selection_policy=selection_policy)
    policies["parallel_wave3_then2"] = parallel_wave_retry_policy(variants, first_wave=3, second_wave=2, selection_policy=selection_policy)
    policies["parallel_wave2_then1_then2"] = parallel_wave_sequence_retry_policy(variants, waves=[2, 1, 2], selection_policy=selection_policy)
    policies["stream_wave3_then2"] = streaming_wave_sequence_retry_policy(variants, waves=[3, 2], selection_policy=selection_policy)
    policies["safe_stream_fixed5"] = streaming_fixed_retry_policy(variants, 5, require_early_return_safe=True, selection_policy=selection_policy)
    policies["safe_stream_wave3_then2"] = streaming_wave_sequence_retry_policy(variants, waves=[3, 2], require_early_return_safe=True, selection_policy=selection_policy)
    policies["fullspan_stream_fixed5"] = streaming_fixed_retry_policy(variants, 5, require_no_label_full_span=True, selection_policy=selection_policy)
    policies["fullspan_stream_wave3_then2"] = streaming_wave_sequence_retry_policy(variants, waves=[3, 2], require_no_label_full_span=True, selection_policy=selection_policy)
    return policies


def adaptive_retry_policy(variants: list[dict[str, Any]], max_samples: int, allow_extra: bool, selection_policy: str = "confidence") -> dict[str, Any]:
    sampled: list[dict[str, Any]] = []
    for variant in variants[:max_samples]:
        sampled.append(variant)
        best = select_best_variant(sampled, policy=selection_policy)
        if best["decision"] == "accepted-visible-lattice-geometry":
            return retry_policy_choice(best, len(sampled), "stopped on accepted geometry", sampled)
    if allow_extra and len(variants) > max_samples:
        sampled.append(variants[max_samples])
        best = select_best_variant(sampled, policy=selection_policy)
        return retry_policy_choice(best, len(sampled), "used fourth sample because first three had no accepted geometry", sampled)
    best = select_best_variant(sampled or variants[:1], policy=selection_policy)
    return retry_policy_choice(best, len(sampled), "reached retry cap", sampled or variants[:1])


def retry_policy_choice(
    variant: dict[str, Any],
    samples_used: int,
    reason: str,
    sampled_variants: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    policy_variant = copy.deepcopy(variant)
    if sampled_variants is not None:
        policy_variant = decorate_variant_for_no_label_readiness(policy_variant, sampled_variants)
    fit = policy_variant["fit"]
    bench = policy_variant["benchmark"]
    safety = early_return_safety(policy_variant)
    no_label_readiness = policy_variant.get("projectionModelComparison", {}).get("noLabelProjectionReadiness", {})
    return {
        "dotVariantId": policy_variant["dotVariantId"],
        "samplesUsed": samples_used,
        "decision": policy_variant["decision"],
        "selectionScore": policy_variant["selectionScore"],
        "manualSeedScore": policy_variant["manualSeedScore"],
        "homographyInliers": fit.get("homographyInliers"),
        "spanI": fit.get("spanI"),
        "spanJ": fit.get("spanJ"),
        "coordinateBounds": fit.get("coordinateBounds"),
        "truthLineSamplesWithin0_15SquaresPct": bench.get("truthLineSamplesWithin0_15SquaresPct"),
        "truthMeshSamplesWithin0_15SquaresPct": bench.get("truthMeshSamplesWithin0_15SquaresPct"),
        "truthMeshVsHomographyGainPct": bench.get("truthMeshVsHomographyGainPct"),
        "observedMeshCellDensity": observed_mesh_cell_density(variant),
        "noLabelProjectionReadinessMode": no_label_readiness.get("mode"),
        "noLabelFullSpanAutoProject": no_label_readiness.get("fullSpanAutoProject"),
        "earlyReturnSafe": safety["safe"],
        "earlyReturnSafetyReasons": safety["reasons"],
        "noLabelRequiresManualExtentConfirmation": no_label_readiness.get("requiresManualExtentConfirmation"),
        "noLabelObservedRegionOnly": no_label_readiness.get("observedRegionOnly"),
        "reason": reason,
    }


def parallel_fixed_retry_policy(variants: list[dict[str, Any]], count: int, selection_policy: str = "confidence") -> dict[str, Any]:
    if not variants:
        raise RuntimeError("No variants to select")
    sampled = variants[: min(count, len(variants))]
    best = select_best_variant(sampled, policy=selection_policy)
    line_elapsed = float(sampled[0].get("lineElapsedMs") or 0)
    dot_wall = max([float(variant.get("dotElapsedMs") or 0) for variant in sampled], default=0.0)
    choice = retry_policy_choice(best, len(sampled), "fixed parallel sample count", sampled)
    choice["estimatedParallelWallMs"] = round_metric(max(line_elapsed, dot_wall))
    return choice


def streaming_fixed_retry_policy(
    variants: list[dict[str, Any]],
    count: int,
    require_early_return_safe: bool = False,
    require_no_label_full_span: bool = False,
    selection_policy: str = "confidence",
) -> dict[str, Any]:
    if not variants:
        raise RuntimeError("No variants to select")
    sampled = variants[: min(count, len(variants))]
    line_elapsed = float(sampled[0].get("lineElapsedMs") or 0)
    completion_times = sorted(
        {
            max(line_elapsed, float(variant.get("dotElapsedMs") or 0))
            for variant in sampled
        }
    )
    for completed_time in completion_times:
        completed = [
            variant
            for variant in sampled
            if max(line_elapsed, float(variant.get("dotElapsedMs") or 0)) <= completed_time
        ]
        best = select_best_streaming_variant(
            completed,
            require_early_return_safe,
            selection_policy=selection_policy,
            require_no_label_full_span=require_no_label_full_span,
        )
        if best is not None:
            accept_reason = streaming_accept_reason("streaming fixed parallel", require_early_return_safe, require_no_label_full_span)
            choice = retry_policy_choice(
                best,
                len(sampled),
                accept_reason,
                completed,
            )
            choice["estimatedParallelWallMs"] = round_metric(completed_time)
            choice["completedDotSamples"] = len(completed)
            choice["launchedDotSamples"] = len(sampled)
            choice["unneededCompletedLaterDotSamples"] = len(sampled) - len(completed)
            return choice

    best = (
        select_best_streaming_variant(
            sampled,
            require_early_return_safe,
            selection_policy=selection_policy,
            require_no_label_full_span=require_no_label_full_span,
        )
        or select_best_variant(sampled, policy=selection_policy)
    )
    dot_wall = max([float(variant.get("dotElapsedMs") or 0) for variant in sampled], default=0.0)
    choice = retry_policy_choice(
        best,
        len(sampled),
        streaming_fallback_reason(require_early_return_safe, require_no_label_full_span),
        sampled,
    )
    choice["estimatedParallelWallMs"] = round_metric(max(line_elapsed, dot_wall))
    choice["completedDotSamples"] = len(sampled)
    choice["launchedDotSamples"] = len(sampled)
    choice["unneededCompletedLaterDotSamples"] = 0
    return choice


def parallel_wave_retry_policy(variants: list[dict[str, Any]], first_wave: int, second_wave: int, selection_policy: str = "confidence") -> dict[str, Any]:
    if not variants:
        raise RuntimeError("No variants to select")
    first = variants[: min(first_wave, len(variants))]
    best = select_best_variant(first, policy=selection_policy)
    line_elapsed = float(first[0].get("lineElapsedMs") or 0)
    first_wall = max([line_elapsed, *[float(variant.get("dotElapsedMs") or 0) for variant in first]])
    if best["decision"] == "accepted-visible-lattice-geometry" or len(first) == len(variants):
        choice = retry_policy_choice(best, len(first), "first parallel wave produced accepted geometry", first)
        choice["estimatedParallelWallMs"] = round_metric(first_wall)
        return choice

    second = variants[len(first) : min(len(first) + second_wave, len(variants))]
    sampled = first + second
    best = select_best_variant(sampled, policy=selection_policy)
    second_wall = max([float(variant.get("dotElapsedMs") or 0) for variant in second], default=0.0)
    choice = retry_policy_choice(best, len(sampled), "used second parallel wave because first wave had no accepted geometry", sampled)
    choice["estimatedParallelWallMs"] = round_metric(first_wall + second_wall)
    return choice


def parallel_wave_sequence_retry_policy(variants: list[dict[str, Any]], waves: list[int], selection_policy: str = "confidence") -> dict[str, Any]:
    if not variants:
        raise RuntimeError("No variants to select")
    sampled: list[dict[str, Any]] = []
    offset = 0
    total_wall = 0.0
    line_elapsed = float(variants[0].get("lineElapsedMs") or 0)
    for wave_index, wave_size in enumerate(waves):
        wave = variants[offset : min(offset + wave_size, len(variants))]
        if not wave:
            break
        offset += len(wave)
        dot_wall = max([float(variant.get("dotElapsedMs") or 0) for variant in wave], default=0.0)
        total_wall += max(line_elapsed, dot_wall) if wave_index == 0 else dot_wall
        sampled.extend(wave)
        best = select_best_variant(sampled, policy=selection_policy)
        if best["decision"] == "accepted-visible-lattice-geometry" or len(sampled) == len(variants):
            choice = retry_policy_choice(best, len(sampled), f"accepted after parallel wave sequence {wave_index + 1}", sampled)
            choice["estimatedParallelWallMs"] = round_metric(total_wall)
            return choice

    best = select_best_variant(sampled or variants[:1], policy=selection_policy)
    choice = retry_policy_choice(best, len(sampled), "reached parallel wave sequence cap", sampled or variants[:1])
    choice["estimatedParallelWallMs"] = round_metric(total_wall)
    return choice


def streaming_wave_sequence_retry_policy(
    variants: list[dict[str, Any]],
    waves: list[int],
    require_early_return_safe: bool = False,
    require_no_label_full_span: bool = False,
    selection_policy: str = "confidence",
) -> dict[str, Any]:
    if not variants:
        raise RuntimeError("No variants to select")
    completed: list[dict[str, Any]] = []
    offset = 0
    elapsed_wall = 0.0
    launched_samples = 0
    line_elapsed = float(variants[0].get("lineElapsedMs") or 0)
    for wave_index, wave_size in enumerate(waves):
        wave = variants[offset : min(offset + wave_size, len(variants))]
        if not wave:
            break
        offset += len(wave)
        launched_samples += len(wave)
        completions = sorted({wave_completion_time(variant, wave_index, elapsed_wall, line_elapsed) for variant in wave})
        wave_end = max(completions) if completions else elapsed_wall
        for completed_time in completions:
            current_completed = [
                variant
                for variant in wave
                if wave_completion_time(variant, wave_index, elapsed_wall, line_elapsed) <= completed_time
            ]
            best = select_best_streaming_variant(
                completed + current_completed,
                require_early_return_safe,
                selection_policy=selection_policy,
                require_no_label_full_span=require_no_label_full_span,
            )
            if best is not None:
                current_sample = completed + current_completed
                accept_reason = streaming_accept_reason(
                    f"streaming wave sequence during wave {wave_index + 1}",
                    require_early_return_safe,
                    require_no_label_full_span,
                )
                choice = retry_policy_choice(
                    best,
                    launched_samples,
                    accept_reason,
                    current_sample,
                )
                choice["estimatedParallelWallMs"] = round_metric(completed_time)
                choice["completedDotSamples"] = len(completed) + len(current_completed)
                choice["launchedDotSamples"] = launched_samples
                choice["unneededCompletedLaterDotSamples"] = launched_samples - choice["completedDotSamples"]
                return choice
        completed.extend(wave)
        best = select_best_streaming_variant(
            completed,
            require_early_return_safe,
            selection_policy=selection_policy,
            require_no_label_full_span=require_no_label_full_span,
        )
        if best is not None:
            accept_reason = streaming_accept_reason(
                f"streaming wave sequence after wave {wave_index + 1}",
                require_early_return_safe,
                require_no_label_full_span,
            )
            choice = retry_policy_choice(
                best,
                launched_samples,
                accept_reason,
                completed,
            )
            choice["estimatedParallelWallMs"] = round_metric(wave_end)
            choice["completedDotSamples"] = len(completed)
            choice["launchedDotSamples"] = launched_samples
            choice["unneededCompletedLaterDotSamples"] = launched_samples - len(completed)
            return choice
        elapsed_wall = wave_end

    fallback = completed or variants[:1]
    best = (
        select_best_streaming_variant(
            fallback,
            require_early_return_safe,
            selection_policy=selection_policy,
            require_no_label_full_span=require_no_label_full_span,
        )
        or select_best_variant(fallback, policy=selection_policy)
    )
    choice = retry_policy_choice(
        best,
        launched_samples or 1,
        streaming_wave_fallback_reason(require_early_return_safe, require_no_label_full_span),
        fallback,
    )
    choice["estimatedParallelWallMs"] = round_metric(elapsed_wall)
    choice["completedDotSamples"] = len(completed)
    choice["launchedDotSamples"] = launched_samples
    choice["unneededCompletedLaterDotSamples"] = launched_samples - len(completed)
    return choice


def select_best_streaming_variant(
    variants: list[dict[str, Any]],
    require_early_return_safe: bool,
    selection_policy: str = "confidence",
    require_no_label_full_span: bool = False,
) -> dict[str, Any] | None:
    if require_no_label_full_span:
        ready = []
        for variant in variants:
            if variant["decision"] != "accepted-visible-lattice-geometry":
                continue
            decorated = decorate_variant_for_no_label_readiness(variant, variants)
            if decorated.get("projectionModelComparison", {}).get("noLabelProjectionReadiness", {}).get("fullSpanAutoProject"):
                ready.append(decorated)
        return None if not ready else select_best_variant(ready, policy=selection_policy)
    if not require_early_return_safe:
        best = select_best_variant(variants, policy=selection_policy)
        return best if best["decision"] == "accepted-visible-lattice-geometry" else None
    safe = [
        variant
        for variant in variants
        if variant["decision"] == "accepted-visible-lattice-geometry" and early_return_safety(variant)["safe"]
    ]
    return None if not safe else select_best_variant(safe, policy=selection_policy)


def decorate_variant_for_no_label_readiness(variant: dict[str, Any], variants: list[dict[str, Any]]) -> dict[str, Any]:
    decorated = copy.deepcopy(variant)
    decorated["earlyReturnSafety"] = early_return_safety(decorated)
    decorated["noLabelRiskDiagnostics"] = no_label_risk_diagnostics(decorated, variants)
    attach_no_label_projection_readiness(decorated)
    return decorated


def streaming_accept_reason(prefix: str, require_early_return_safe: bool, require_no_label_full_span: bool) -> str:
    if require_no_label_full_span:
        return f"{prefix} produced no-label full-span projection-ready geometry before all launched jobs completed"
    if require_early_return_safe:
        return f"{prefix} produced early-return-safe geometry before all launched jobs completed"
    return f"{prefix} produced accepted geometry before all launched jobs completed"


def streaming_fallback_reason(require_early_return_safe: bool, require_no_label_full_span: bool) -> str:
    if require_no_label_full_span:
        return "no no-label full-span projection-ready geometry before all launched jobs completed"
    if require_early_return_safe:
        return "no early-return-safe geometry before all launched jobs completed"
    return "no streaming accept before all launched jobs completed"


def streaming_wave_fallback_reason(require_early_return_safe: bool, require_no_label_full_span: bool) -> str:
    if require_no_label_full_span:
        return "reached streaming wave sequence cap without no-label full-span projection-ready geometry"
    if require_early_return_safe:
        return "reached streaming wave sequence cap without early-return-safe geometry"
    return "reached streaming wave sequence cap"


def wave_completion_time(variant: dict[str, Any], wave_index: int, elapsed_wall: float, line_elapsed: float) -> float:
    dot_elapsed = float(variant.get("dotElapsedMs") or 0)
    if wave_index == 0:
        return max(line_elapsed, dot_elapsed)
    return elapsed_wall + dot_elapsed


def variant_summary(variant: dict[str, Any]) -> dict[str, Any]:
    fit = variant["fit"]
    bench = variant["benchmark"]
    mesh = variant.get("observedMesh", {})
    projection = variant.get("projectionModelComparison", {})
    confidence = projection.get("fullSpanProjectionConfidence", {})
    readiness = projection.get("projectionReadiness", {})
    no_label_readiness = projection.get("noLabelProjectionReadiness", {})
    return {
        "dotVariantId": variant["dotVariantId"],
        "dotReportPath": variant["dotReportPath"],
        "selectionScore": variant["selectionScore"],
        "manualSeedScore": variant["manualSeedScore"],
        "lineElapsedMs": variant.get("lineElapsedMs"),
        "dotElapsedMs": variant.get("dotElapsedMs"),
        "decision": variant["decision"],
        "homographyInliers": fit.get("homographyInliers"),
        "homographyInlierRatio": fit.get("homographyInlierRatio"),
        "spanI": fit.get("spanI"),
        "spanJ": fit.get("spanJ"),
        "coordinateBounds": fit.get("coordinateBounds"),
        "p90ReprojectionErrorCells": fit.get("p90ReprojectionErrorCells"),
        "medianLineSupport": fit.get("medianLineSupport"),
        "p25LineSupport": fit.get("p25LineSupport"),
        "imageLineContrastSamples": fit.get("imageLineContrastSamples"),
        "imageLineContrastMedian": fit.get("imageLineContrastMedian"),
        "imageLineContrastMean": fit.get("imageLineContrastMean"),
        "imageLineContrastPositivePct": fit.get("imageLineContrastPositivePct"),
        "coordinateConflictPct": fit.get("coordinateConflictPct"),
        "axisCandidateCount": fit.get("axisCandidateCount"),
        "axisSelectedMode": fit.get("axisSelectedMode"),
        "axisCandidateModes": fit.get("axisCandidateModes"),
        "axisCandidateScores": fit.get("axisCandidateScores"),
        "componentPoolSelectedRank": fit.get("componentPoolSelectedRank"),
        "componentPoolEvaluated": fit.get("componentPoolEvaluated"),
        "truthP90DotErrorSquares": bench.get("truthP90DotErrorSquares"),
        "truthLineSamplesWithin0_15SquaresPct": bench.get("truthLineSamplesWithin0_15SquaresPct"),
        "observedEdgeHomographyLineWithin0_15Pct": projection.get("observedEdgeHomographyLineWithin0_15Pct"),
        "truthMeshSamplesWithin0_15SquaresPct": bench.get("truthMeshSamplesWithin0_15SquaresPct"),
        "truthMeshVsHomographyGainPct": bench.get("truthMeshVsHomographyGainPct"),
        "projectionConfidenceLevel": confidence.get("level"),
        "projectionReadinessMode": readiness.get("mode"),
        "fullSpanAutoProject": readiness.get("fullSpanAutoProject"),
        "observedRegionOnly": readiness.get("observedRegionOnly"),
        "noLabelProjectionReadinessMode": no_label_readiness.get("mode"),
        "noLabelFullSpanAutoProject": no_label_readiness.get("fullSpanAutoProject"),
        "noLabelRequiresManualExtentConfirmation": no_label_readiness.get("requiresManualExtentConfirmation"),
        "noLabelObservedRegionOnly": no_label_readiness.get("observedRegionOnly"),
        "earlyReturnSafety": early_return_safety(variant),
        "observedMeshCellDensity": observed_mesh_cell_density(variant),
        "observedMeshVertices": mesh.get("vertexCount"),
        "observedMeshEdges": mesh.get("edgeCount"),
        "observedMeshCells": mesh.get("cellCount"),
        "overlayImage": variant["overlayImage"],
    }


def seed_detail(variant: dict[str, Any]) -> dict[str, Any]:
    return {
        "dotVariantId": variant["dotVariantId"],
        "decision": variant["decision"],
        "fit": variant["fit"],
        "observedMesh": variant.get("observedMesh"),
        "projectionModelComparison": variant.get("projectionModelComparison"),
        "selectionScore": variant.get("selectionScore"),
        "manualSeedScore": variant.get("manualSeedScore"),
        "lineImage": variant.get("lineImage"),
        "dotImage": variant.get("dotImage"),
    }


def manual_seed_recommendation(auto: dict[str, Any], manual_seed: dict[str, Any]) -> dict[str, Any]:
    auto_fit = auto["fit"]
    manual_fit = manual_seed["fit"]
    auto_area = int(auto_fit.get("spanI") or 0) * int(auto_fit.get("spanJ") or 0)
    manual_area = int(manual_fit.get("spanI") or 0) * int(manual_fit.get("spanJ") or 0)
    reasons = []
    if auto["dotVariantId"] == manual_seed["dotVariantId"]:
        mode = "auto-and-manual-seed-match"
        reasons.append("auto projection geometry is also the best manual correction seed")
    else:
        mode = "separate-manual-correction-seed"
        if manual_area > auto_area:
            reasons.append("manual correction seed covers a wider visible grid")
        if manual_seed["decision"] != "accepted-visible-lattice-geometry":
            reasons.append("seed requires manual confirmation before projection")
        if not reasons:
            reasons.append("manual correction seed scores higher for correction ergonomics")
    return {
        "mode": mode,
        "recommendedVariantId": manual_seed["dotVariantId"],
        "autoVariantId": auto["dotVariantId"],
        "recommendedDecision": manual_seed["decision"],
        "autoDecision": auto["decision"],
        "recommendedSpan": f"{manual_fit.get('spanI')}x{manual_fit.get('spanJ')}",
        "autoSpan": f"{auto_fit.get('spanI')}x{auto_fit.get('spanJ')}",
        "recommendedArea": manual_area,
        "autoArea": auto_area,
        "reasons": reasons,
    }


def early_return_safety(selection: dict[str, Any]) -> dict[str, Any]:
    """Conservative quality floor for returning before a launched wave drains.

    This is stricter than normal acceptance. It is for latency decisions only:
    a fit can remain accepted for normal scoring while not being safe enough to
    stop a live runner early.
    """
    fit = selection.get("fit", {})
    reasons = []
    if selection.get("decision") != "accepted-visible-lattice-geometry":
        reasons.append("selection is not accepted visible geometry")
    homography_inliers = int(metric_value(fit, "homographyInliers", 0))
    homography_inlier_ratio = metric_value(fit, "homographyInlierRatio", 0.0)
    span_i = int(metric_value(fit, "spanI", 0))
    span_j = int(metric_value(fit, "spanJ", 0))
    min_span = min(span_i, span_j)
    span_area = span_i * span_j
    p90_error = metric_value(fit, "p90ReprojectionErrorCells", 99.0)
    line_agreement = metric_value(fit, "lineAgreementPct", 0.0)
    median_line_support = metric_value(fit, "medianLineSupport", 0.0)
    p25_line_support = metric_value(fit, "p25LineSupport", 0.0)
    coordinate_conflict = metric_value(fit, "coordinateConflictPct", 100.0)
    mesh_density = observed_mesh_cell_density(selection)
    strong_slight_conflict_fit = (
        coordinate_conflict <= 12.0
        and homography_inliers >= 160
        and homography_inlier_ratio >= 0.65
        and p90_error <= 0.07
        and line_agreement >= 97
        and median_line_support >= 0.90
        and p25_line_support >= 0.85
        and mesh_density is not None
        and mesh_density >= 0.25
    )
    if homography_inliers < 100:
        reasons.append("too few homography inliers for early return")
    if homography_inlier_ratio < 0.50:
        reasons.append("homography inlier ratio is too low for early return")
    if min_span < 8:
        reasons.append("visible lattice span is too small for early return")
    if p90_error > 0.08:
        reasons.append("p90 reprojection error is too high for early return")
    if span_area >= 650 and homography_inlier_ratio < 0.60 and p90_error >= 0.04:
        reasons.append("large-span fit has low inlier ratio plus elevated reprojection error")
    elif span_area >= 500 and homography_inlier_ratio < 0.55 and p90_error >= 0.04:
        reasons.append("mid-large span fit has low inlier ratio plus elevated reprojection error")
    if line_agreement < 95:
        reasons.append("too few dots agree with the independent line mask for early return")
    if median_line_support < 0.70:
        reasons.append("median fitted-line support is too low for early return")
    if p25_line_support < 0.55:
        reasons.append("lower-quartile fitted-line support is too low for early return")
    if coordinate_conflict > 10 and not strong_slight_conflict_fit:
        reasons.append("lattice coordinate conflicts are too high for early return")
    if mesh_density is None or mesh_density < 0.18:
        reasons.append("observed inlier mesh is too sparse for early return")
    return {
        "safe": not reasons,
        "reasons": reasons or ["accepted fit passes conservative early-return quality floor"],
    }


def metric_value(metrics: dict[str, Any], key: str, default: float) -> float:
    value = metrics.get(key)
    return float(default) if value is None else float(value)


def observed_mesh_cell_density(selection: dict[str, Any]) -> float | None:
    fit = selection.get("fit", {})
    mesh = selection.get("observedMesh", {})
    span_i = metric_value(fit, "spanI", 0.0)
    span_j = metric_value(fit, "spanJ", 0.0)
    if span_i <= 0 or span_j <= 0:
        return None
    return round_metric(float(mesh.get("cellCount") or 0) / (span_i * span_j))


def attach_no_label_projection_readiness(selection: dict[str, Any]) -> dict[str, Any]:
    comparison = selection.get("projectionModelComparison")
    if comparison is None:
        comparison = {}
        selection["projectionModelComparison"] = comparison
    comparison["noLabelProjectionReadiness"] = no_label_projection_readiness(selection)
    return selection


def no_label_projection_readiness(selection: dict[str, Any]) -> dict[str, Any]:
    """Runtime-safe projection readiness from fit/support metrics only.

    This intentionally ignores benchmark labels and truth-derived projection
    percentages. It answers a more conservative product question: whether an
    accepted visible lattice has enough support to auto-project the full fitted
    span without a human confirming the extent.
    """
    fit = selection.get("fit", {})
    mesh = selection.get("observedMesh", {})
    decision = selection.get("decision")
    safety = selection.get("earlyReturnSafety") or early_return_safety(selection)
    risk_flags = list((selection.get("noLabelRiskDiagnostics") or {}).get("riskFlags") or [])
    homography_inliers = int(metric_value(fit, "homographyInliers", 0.0))
    homography_inlier_ratio = metric_value(fit, "homographyInlierRatio", 0.0)
    span_i = int(metric_value(fit, "spanI", 0.0))
    span_j = int(metric_value(fit, "spanJ", 0.0))
    span_area = span_i * span_j
    min_span = min(span_i, span_j)
    p90_error = metric_value(fit, "p90ReprojectionErrorCells", 99.0)
    line_agreement = metric_value(fit, "lineAgreementPct", 0.0)
    median_line_support = metric_value(fit, "medianLineSupport", 0.0)
    p25_line_support = metric_value(fit, "p25LineSupport", 0.0)
    coordinate_conflict = metric_value(fit, "coordinateConflictPct", 100.0)
    mesh_cells = int(mesh.get("cellCount") or 0)
    mesh_vertices = int(mesh.get("vertexCount") or 0)
    mesh_density = observed_mesh_cell_density(selection)
    density = 0.0 if mesh_density is None else mesh_density
    reasons: list[str] = []

    if decision != "accepted-visible-lattice-geometry":
        return no_label_projection_readiness_result(
            "no-label-manual-confirmation-required",
            "manual-confirmation-required",
            False,
            True,
            False,
            bool(mesh_cells >= 50 and mesh_vertices >= 80 and density >= 0.14),
            risk_flags,
            ["geometry decision is not accepted visible lattice"],
        )

    if risk_flags:
        reasons.append("selection has no-label ambiguity flags")
    if not safety.get("safe"):
        reasons.append("selection does not pass the early-return safety floor")

    strict_full_span = (
        bool(safety.get("safe"))
        and homography_inliers >= 100
        and homography_inlier_ratio >= 0.70
        and p90_error <= 0.07
        and line_agreement >= 98.0
        and median_line_support >= 0.85
        and p25_line_support >= 0.65
        and coordinate_conflict <= 6.0
        and density >= 0.35
        and mesh_cells >= 80
        and mesh_vertices >= 120
    )
    small_span_clean = (
        bool(safety.get("safe"))
        and span_area <= 300
        and homography_inlier_ratio >= 0.80
        and p90_error <= 0.06
        and line_agreement >= 95.0
        and median_line_support >= 0.90
        and p25_line_support >= 0.75
        and coordinate_conflict <= 4.0
        and density >= 0.30
        and not risk_flags
    )
    strong_ambiguous_support = (
        bool(safety.get("safe"))
        and homography_inlier_ratio >= 0.70
        and p90_error <= 0.05
        and line_agreement >= 98.0
        and median_line_support >= 0.90
        and p25_line_support >= 0.90
        and coordinate_conflict <= 6.0
        and density >= 0.35
        and mesh_cells >= 80
    )
    if strict_full_span or small_span_clean or strong_ambiguous_support:
        full_reasons = ["no-label support is strong enough for a full-span auto-project candidate"]
        if risk_flags:
            full_reasons.append("ambiguity flags are retained for reporting but outweighed by strong support")
        return no_label_projection_readiness_result(
            "no-label-full-span-candidate",
            "full-span-homography-candidate",
            True,
            False,
            False,
            True,
            risk_flags,
            full_reasons,
        )

    manual_extent_floor = (
        homography_inliers >= 100
        and min_span >= 12
        and homography_inlier_ratio >= 0.50
        and p90_error <= 0.08
        and line_agreement >= 95.0
        and median_line_support >= 0.65
        and p25_line_support >= 0.55
        and coordinate_conflict <= 10.0
        and density >= 0.20
        and mesh_cells >= 50
        and mesh_vertices >= 80
    )
    if manual_extent_floor:
        return no_label_projection_readiness_result(
            "no-label-manual-extent-check",
            "manual-extent-confirmation-required-before-full-span-projection",
            False,
            True,
            False,
            True,
            risk_flags,
            reasons or ["visible lattice support is usable but not strong enough for autonomous full-span projection"],
        )

    observed_region_floor = (
        homography_inliers >= 80
        and min_span >= 10
        and p90_error <= 0.09
        and line_agreement >= 92.0
        and median_line_support >= 0.60
        and p25_line_support >= 0.50
        and coordinate_conflict <= 12.0
        and mesh_cells >= 40
        and mesh_vertices >= 60
        and density >= 0.12
    )
    observed_reasons = reasons[:]
    if homography_inlier_ratio < 0.50:
        observed_reasons.append("homography inlier ratio is too low to extrapolate full span")
    if density < 0.20:
        observed_reasons.append("observed mesh density is too sparse to extrapolate full span")
    if observed_region_floor:
        return no_label_projection_readiness_result(
            "no-label-observed-region-candidate",
            "project-observed-region-only-until-extent-confirmed",
            False,
            True,
            True,
            True,
            risk_flags,
            observed_reasons or ["visible-region evidence exists but full-span extent is not runtime-safe"],
        )

    if homography_inliers < 100:
        reasons.append("too few homography inliers")
    if min_span < 12:
        reasons.append("visible lattice span is too small")
    if p90_error > 0.08:
        reasons.append("p90 reprojection error is too high")
    if line_agreement < 95.0:
        reasons.append("line agreement is too low")
    if density < 0.20:
        reasons.append("observed mesh density is too sparse")
    return no_label_projection_readiness_result(
        "no-label-manual-confirmation-required",
        "manual-confirmation-required",
        False,
        True,
        False,
        bool(mesh_cells >= 50 and mesh_vertices >= 80 and density >= 0.14),
        risk_flags,
        reasons or ["no-label support is insufficient for projection readiness"],
    )


def no_label_projection_readiness_result(
    mode: str,
    recommendation: str,
    full_span_auto_project: bool,
    requires_manual_extent_confirmation: bool,
    observed_region_only: bool,
    has_observed_mesh_support: bool,
    risk_flags: list[str],
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "mode": mode,
        "recommendation": recommendation,
        "fullSpanAutoProject": full_span_auto_project,
        "requiresManualExtentConfirmation": requires_manual_extent_confirmation,
        "observedRegionOnly": observed_region_only,
        "hasObservedMeshSupport": has_observed_mesh_support,
        "riskFlags": risk_flags,
        "reasons": reasons,
        "source": "no-label-fit-and-observed-mesh-metrics",
    }


def selection_diagnostics(auto: dict[str, Any], variants: list[dict[str, Any]]) -> dict[str, Any]:
    accepted = [variant for variant in variants if variant["decision"] == "accepted-visible-lattice-geometry"]
    if not accepted:
        return {"acceptedMeshDensity": None, "guardedMeshDensity": None}
    mesh_density_variant = max(accepted, key=mesh_density_score_for_variant)
    guarded_mesh_density_variant = select_guarded_mesh_density_variant(auto, accepted)
    return {
        "acceptedMeshDensity": selection_diagnostic_entry(
            "highest observed inlier-mesh cell density among accepted variants",
            auto,
            mesh_density_variant,
            mesh_density_score_for_variant,
        ),
        "guardedMeshDensity": selection_diagnostic_entry(
            "guarded observed inlier-mesh density challenger",
            auto,
            guarded_mesh_density_variant,
            mesh_density_score_for_variant,
            reason=(
                "report-only guarded diagnostic: accepted variants must be early-return-safe, "
                "materially denser, and at least 35% of the auto span; it may still prefer "
                "a smaller visible patch over fuller coverage"
            ),
        ),
    }


def selection_diagnostic_entry(
    description: str,
    auto: dict[str, Any],
    candidate: dict[str, Any],
    score_fn: Any,
    reason: str = "diagnostic uses only accepted variants but may prefer smaller dense patches over fuller visible coverage",
) -> dict[str, Any]:
    return {
        "description": description,
        "recommendation": "report-only",
        "reason": reason,
        "autoVariantId": auto["dotVariantId"],
        "candidateVariantId": candidate["dotVariantId"],
        "differs": auto["dotVariantId"] != candidate["dotVariantId"],
        "autoScore": round_metric(score_fn(auto)),
        "candidateScore": round_metric(score_fn(candidate)),
        "candidate": variant_summary(candidate),
        "truthDelta": benchmark_delta(auto.get("benchmark", {}), candidate.get("benchmark", {})),
    }


def no_label_risk_diagnostics(auto: dict[str, Any], variants: list[dict[str, Any]]) -> dict[str, Any]:
    """Report-only probes for accepted-variant ambiguity.

    These diagnostics are intentionally not a selector. The current hard case
    is not that one no-label metric obviously prefers the benchmark-best
    variant; it is that multiple accepted variants trade coverage, support,
    density, and reprojection error in plausible ways.
    """
    accepted = [variant for variant in variants if variant["decision"] == "accepted-visible-lattice-geometry"]
    challengers = [
        accepted_challenger_entry(auto, variant)
        for variant in accepted
        if variant["dotVariantId"] != auto["dotVariantId"]
    ]
    challengers.sort(key=lambda item: (item["scoreGapToSelected"], -abs(item.get("spanAreaRatio") or 1.0)))
    fuller_same_error = select_fuller_same_error_challenger(auto, accepted)
    fuller_entry = None if fuller_same_error is None else accepted_challenger_entry(auto, fuller_same_error)
    borderline_conflict_fuller_entry = fuller_entry if selected_has_borderline_error_high_conflict(auto) and fuller_entry else None
    precise_subset = select_precise_subset_challenger(auto, accepted)
    precise_subset_entry = None if precise_subset is None else accepted_challenger_entry(auto, precise_subset)
    high_precision_compact = select_high_precision_compact_challenger(auto, accepted)
    high_precision_compact_entry = None if high_precision_compact is None else accepted_challenger_entry(auto, high_precision_compact)
    near_score_challengers = [item for item in challengers if item["scoreGapToSelected"] <= 500]
    wider_near_score = [
        item
        for item in challengers
        if item["scoreGapToSelected"] <= 600 and (item.get("spanAreaRatio") or 0) >= 1.08
    ]
    flags = selected_no_label_risk_flags(auto)
    if wider_near_score:
        flags.append("a wider accepted challenger has a similar no-label score")
    if fuller_entry is not None:
        flags.append("fuller same-error accepted challenger exists")
    if precise_subset_entry is not None:
        flags.append("precise accepted subset challenger exists")
    if high_precision_compact_entry is not None:
        flags.append("high-precision compact accepted challenger exists")
    return {
        "recommendation": "report-only; use these probes to design larger-corpus selector tests, not runtime selection",
        "selectedVariantId": auto["dotVariantId"],
        "acceptedVariantCount": len(accepted),
        "acceptedChallengerCount": len(challengers),
        "nearScoreChallengerCount": len(near_score_challengers),
        "widerNearScoreChallengerCount": len(wider_near_score),
        "selectionAmbiguous": bool(flags),
        "riskFlags": flags,
        "riskLevel": "selection-ambiguous" if flags else "low",
        "selected": no_label_variant_metrics(auto),
        "nearestScoreChallengers": challengers[:3],
        "fullerSameErrorChallenger": fuller_entry,
        "borderlineConflictFullerChallenger": borderline_conflict_fuller_entry,
        "preciseSubsetChallenger": precise_subset_entry,
        "highPrecisionCompactChallenger": high_precision_compact_entry,
    }


def selected_no_label_risk_flags(auto: dict[str, Any]) -> list[str]:
    fit = auto.get("fit", {})
    p90 = metric_value(fit, "p90ReprojectionErrorCells", 99.0)
    conflict = metric_value(fit, "coordinateConflictPct", 0.0)
    mesh_density = observed_mesh_cell_density(auto) or 0.0
    p25_support = metric_value(fit, "p25LineSupport", 1.0)
    inlier_ratio = metric_value(fit, "homographyInlierRatio", 1.0)
    flags = []
    if p90 >= 0.05 and conflict >= 7.0:
        flags.append("selected fit has borderline reprojection error plus high coordinate conflicts")
    if p90 >= 0.06 and mesh_density < 0.35:
        flags.append("selected fit has borderline reprojection error plus sparse observed mesh density")
    if p25_support < 0.70 and inlier_ratio < 0.70:
        flags.append("selected fit has low lower-quartile line support plus lower inlier ratio")
    return flags


def selected_has_borderline_error_high_conflict(auto: dict[str, Any]) -> bool:
    fit = auto.get("fit", {})
    return (
        metric_value(fit, "p90ReprojectionErrorCells", 99.0) >= 0.05
        and metric_value(fit, "coordinateConflictPct", 0.0) >= 7.0
    )


def no_label_variant_metrics(variant: dict[str, Any]) -> dict[str, Any]:
    fit = variant.get("fit", {})
    return {
        "dotVariantId": variant["dotVariantId"],
        "decision": variant["decision"],
        "selectionScore": variant["selectionScore"],
        "manualSeedScore": variant["manualSeedScore"],
        "homographyInliers": fit.get("homographyInliers"),
        "homographyInlierRatio": fit.get("homographyInlierRatio"),
        "spanI": fit.get("spanI"),
        "spanJ": fit.get("spanJ"),
        "spanArea": round_metric(span_area_for_variant(variant)),
        "p90ReprojectionErrorCells": fit.get("p90ReprojectionErrorCells"),
        "medianLineSupport": fit.get("medianLineSupport"),
        "p25LineSupport": fit.get("p25LineSupport"),
        "coordinateConflictPct": fit.get("coordinateConflictPct"),
        "observedMeshCellDensity": observed_mesh_cell_density(variant),
        "earlyReturnSafe": early_return_safety(variant)["safe"],
    }


def accepted_challenger_entry(auto: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    auto_area = max(1.0, span_area_for_variant(auto))
    candidate_area = span_area_for_variant(candidate)
    score_delta = float(candidate["selectionScore"]) - float(auto["selectionScore"])
    return {
        **no_label_variant_metrics(candidate),
        "scoreDeltaVsSelected": round_metric(score_delta),
        "scoreGapToSelected": round_metric(abs(score_delta)),
        "spanAreaRatio": round_metric(candidate_area / auto_area),
        "inlierDelta": round_metric(metric_value(candidate.get("fit", {}), "homographyInliers", 0.0) - metric_value(auto.get("fit", {}), "homographyInliers", 0.0)),
        "inlierRatioDelta": round_metric(metric_value(candidate.get("fit", {}), "homographyInlierRatio", 0.0) - metric_value(auto.get("fit", {}), "homographyInlierRatio", 0.0)),
        "p90ErrorDelta": round_metric(metric_value(candidate.get("fit", {}), "p90ReprojectionErrorCells", 99.0) - metric_value(auto.get("fit", {}), "p90ReprojectionErrorCells", 99.0)),
        "p25LineSupportDelta": round_metric(metric_value(candidate.get("fit", {}), "p25LineSupport", 0.0) - metric_value(auto.get("fit", {}), "p25LineSupport", 0.0)),
        "coordinateConflictDelta": round_metric(metric_value(candidate.get("fit", {}), "coordinateConflictPct", 100.0) - metric_value(auto.get("fit", {}), "coordinateConflictPct", 100.0)),
        "meshDensityDelta": round_metric((observed_mesh_cell_density(candidate) or 0.0) - (observed_mesh_cell_density(auto) or 0.0)),
        "latticeAgreementWithSelected": lattice_agreement_between_variants(auto, candidate),
        "scoreContributionDelta": score_contribution_delta(auto, candidate),
        "truthDelta": benchmark_delta(auto.get("benchmark", {}), candidate.get("benchmark", {})),
        "benchmarkCompositeDeltaPct": benchmark_composite_delta(auto, candidate),
    }


def select_fuller_same_error_challenger(auto: dict[str, Any], accepted: list[dict[str, Any]]) -> dict[str, Any] | None:
    auto_area = span_area_for_variant(auto)
    if auto_area <= 0:
        return None
    auto_p90 = metric_value(auto.get("fit", {}), "p90ReprojectionErrorCells", 99.0)
    challengers = []
    for variant in accepted:
        if variant["dotVariantId"] == auto["dotVariantId"]:
            continue
        fit = variant.get("fit", {})
        area_ratio = span_area_for_variant(variant) / auto_area
        if area_ratio < 1.05:
            continue
        if metric_value(fit, "p90ReprojectionErrorCells", 99.0) > auto_p90 + 0.01:
            continue
        if metric_value(fit, "medianLineSupport", 0.0) < 0.90:
            continue
        if metric_value(fit, "p25LineSupport", 0.0) < 0.60:
            continue
        if metric_value(fit, "coordinateConflictPct", 100.0) > 8.0:
            continue
        if min(metric_value(fit, "spanI", 0.0), metric_value(fit, "spanJ", 0.0)) < 12:
            continue
        challengers.append(variant)
    if not challengers:
        return None
    return max(
        challengers,
        key=lambda variant: (
            span_area_for_variant(variant) / auto_area,
            -metric_value(variant.get("fit", {}), "p90ReprojectionErrorCells", 99.0),
            variant["selectionScore"],
        ),
    )


def select_precise_subset_challenger(auto: dict[str, Any], accepted: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find same-lattice, smaller accepted fits with materially cleaner local evidence."""
    auto_area = span_area_for_variant(auto)
    if auto_area <= 0:
        return None
    auto_fit = auto.get("fit", {})
    challengers = []
    for variant in accepted:
        if variant["dotVariantId"] == auto["dotVariantId"]:
            continue
        if not early_return_safety(variant)["safe"]:
            continue
        area_ratio = span_area_for_variant(variant) / auto_area
        if area_ratio < 0.60 or area_ratio >= 1.0:
            continue
        agreement = lattice_agreement_between_variants(auto, variant)
        if not agreement or float(agreement.get("within0_15Pct") or 0.0) < 95.0:
            continue
        fit = variant.get("fit", {})
        if metric_value(fit, "p90ReprojectionErrorCells", 99.0) > metric_value(auto_fit, "p90ReprojectionErrorCells", 99.0) - 0.012:
            continue
        if metric_value(fit, "p25LineSupport", 0.0) < metric_value(auto_fit, "p25LineSupport", 0.0) + 0.05:
            continue
        if metric_value(fit, "coordinateConflictPct", 100.0) > metric_value(auto_fit, "coordinateConflictPct", 100.0) - 1.0:
            continue
        if min(metric_value(fit, "spanI", 0.0), metric_value(fit, "spanJ", 0.0)) < 8:
            continue
        challengers.append((variant, agreement, area_ratio))
    if not challengers:
        return None
    return max(
        challengers,
        key=lambda item: (
            item[1].get("within0_15Pct") or 0.0,
            metric_value(item[0].get("fit", {}), "p25LineSupport", 0.0) - metric_value(auto_fit, "p25LineSupport", 0.0),
            metric_value(auto_fit, "p90ReprojectionErrorCells", 99.0) - metric_value(item[0].get("fit", {}), "p90ReprojectionErrorCells", 99.0),
            item[0]["selectionScore"],
        ),
    )[0]


def selected_has_low_support_lower_ratio(auto: dict[str, Any]) -> bool:
    fit = auto.get("fit", {})
    low_support_lower_ratio = (
        metric_value(fit, "p25LineSupport", 1.0) <= 0.70
        and metric_value(fit, "homographyInlierRatio", 1.0) <= 0.72
        and metric_value(fit, "p90ReprojectionErrorCells", 0.0) >= 0.035
        and span_area_for_variant(auto) >= 650
    )
    sparse_borderline_broad_fit = (
        span_area_for_variant(auto) >= 650
        and metric_value(fit, "p90ReprojectionErrorCells", 0.0) >= 0.060
        and metric_value(fit, "homographyInlierRatio", 1.0) <= 0.75
        and (observed_mesh_cell_density(auto) or 0.0) < 0.35
    )
    return low_support_lower_ratio or sparse_borderline_broad_fit


def select_high_precision_compact_challenger(auto: dict[str, Any], accepted: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find a smaller, very clean accepted fit when the selected fit is broad but weakly supported.

    This intentionally does not require same-lattice agreement: the failure it
    targets is a plausible broad lattice whose local support is uneven, where a
    compact high-support patch may represent the real visible grid better than
    the no-label score's wider coverage preference.
    """
    if not selected_has_low_support_lower_ratio(auto):
        return None
    auto_area = span_area_for_variant(auto)
    if auto_area <= 0:
        return None
    auto_fit = auto.get("fit", {})
    challengers = []
    for variant in accepted:
        if variant["dotVariantId"] == auto["dotVariantId"]:
            continue
        fit = variant.get("fit", {})
        area_ratio = span_area_for_variant(variant) / auto_area
        if area_ratio < 0.30 or area_ratio > 0.65:
            continue
        if abs(float(variant["selectionScore"]) - float(auto["selectionScore"])) > 1800:
            continue
        if metric_value(fit, "homographyInliers", 0.0) < 90:
            continue
        if metric_value(fit, "homographyInlierRatio", 0.0) < 0.70:
            continue
        if min(metric_value(fit, "spanI", 0.0), metric_value(fit, "spanJ", 0.0)) < 15:
            continue
        if metric_value(fit, "p90ReprojectionErrorCells", 99.0) > 0.060:
            continue
        if metric_value(fit, "p90ReprojectionErrorCells", 99.0) > metric_value(auto_fit, "p90ReprojectionErrorCells", 99.0) - 0.010:
            continue
        if metric_value(fit, "p25LineSupport", 0.0) < 0.95:
            continue
        if metric_value(fit, "p25LineSupport", 0.0) < metric_value(auto_fit, "p25LineSupport", 0.0) + 0.25:
            continue
        if metric_value(fit, "medianLineSupport", 0.0) < 0.98:
            continue
        if metric_value(fit, "coordinateConflictPct", 100.0) > 6.5:
            continue
        if metric_value(fit, "coordinateConflictPct", 100.0) > metric_value(auto_fit, "coordinateConflictPct", 0.0) + 2.5:
            continue
        mesh_density = observed_mesh_cell_density(variant) or 0.0
        if mesh_density < 0.20:
            continue
        if int(variant.get("observedMesh", {}).get("cellCount") or 0) < 55:
            continue
        challengers.append((variant, area_ratio, mesh_density))
    if not challengers:
        return None
    return max(
        challengers,
        key=lambda item: (
            metric_value(item[0].get("fit", {}), "p25LineSupport", 0.0),
            metric_value(auto_fit, "p90ReprojectionErrorCells", 99.0) - metric_value(item[0].get("fit", {}), "p90ReprojectionErrorCells", 99.0),
            item[2],
            item[0]["selectionScore"],
        ),
    )[0]


def score_contribution_delta(auto: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    auto_terms = selection_score_terms(auto)
    candidate_terms = selection_score_terms(candidate)
    deltas = {key: round_metric(candidate_terms[key] - auto_terms[key]) for key in auto_terms}
    ranked = sorted(deltas.items(), key=lambda item: abs(float(item[1])), reverse=True)
    return {
        "terms": deltas,
        "topTerms": [{"term": key, "delta": value} for key, value in ranked[:5]],
    }


def selection_score_terms(variant: dict[str, Any]) -> dict[str, float]:
    metrics = variant.get("fit", {})
    decision = variant.get("decision", "refuse")
    rank = {
        "accepted-visible-lattice-geometry": 2.0,
        "candidate-visible-lattice-geometry": 1.0,
        "refuse": 0.0,
    }.get(decision, 0.0)
    inliers = float(metrics.get("homographyInliers") or 0)
    inlier_ratio = float(metrics.get("homographyInlierRatio") or 0)
    span_i = float(metrics.get("spanI") or 0)
    span_j = float(metrics.get("spanJ") or 0)
    p90_error = float(metrics.get("p90ReprojectionErrorCells") if metrics.get("p90ReprojectionErrorCells") is not None else 2.0)
    median_support = float(metrics.get("medianLineSupport") or 0)
    p25_support = float(metrics.get("p25LineSupport") or 0)
    conflict = float(metrics.get("coordinateConflictPct") or 0)
    line_agreement = float(metrics.get("lineAgreementPct") or 0)
    min_span = min(span_i, span_j)
    area_span = math.sqrt(max(0.0, span_i * span_j))
    return {
        "decisionRank": rank * 10000.0,
        "homographyInliers": inliers * 1.8,
        "homographyInlierRatio": inlier_ratio * 900.0,
        "minSpan": min_span * 70.0,
        "areaSpan": area_span * 20.0,
        "medianLineSupport": median_support * 500.0,
        "p25LineSupport": p25_support * 350.0,
        "lineAgreement": line_agreement * 8.0,
        "p90ReprojectionError": -p90_error * 1600.0,
        "coordinateConflict": -conflict * 24.0,
    }


def lattice_agreement_between_variants(auto: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any] | None:
    distances = []
    distances.extend(one_way_lattice_agreement_distances(auto, candidate))
    distances.extend(one_way_lattice_agreement_distances(candidate, auto))
    if not distances:
        return None
    arr = np.array(distances, dtype=np.float32)
    return {
        "samples": int(len(arr)),
        "within0_15Pct": round_metric(float(np.mean(arr <= 0.15) * 100.0)),
        "medianCells": round_metric(float(np.median(arr))),
        "p90Cells": round_metric(float(np.percentile(arr, 90))),
    }


def one_way_lattice_agreement_distances(source: dict[str, Any], target: dict[str, Any]) -> list[float]:
    target_h = homography_matrix_from_variant(target)
    vertices = source.get("observedMesh", {}).get("vertices") or []
    if target_h is None or len(vertices) == 0:
        return []
    try:
        inverse = np.linalg.inv(target_h)
    except np.linalg.LinAlgError:
        return []
    image_points = np.float32([[float(vertex[2]), float(vertex[3])] for vertex in vertices if len(vertex) >= 4])
    if len(image_points) == 0:
        return []
    grid_points = cv2.perspectiveTransform(image_points.reshape(1, -1, 2), inverse).reshape(-1, 2)
    distances = np.sqrt((grid_points[:, 0] - np.rint(grid_points[:, 0])) ** 2 + (grid_points[:, 1] - np.rint(grid_points[:, 1])) ** 2)
    return [float(value) for value in distances if math.isfinite(float(value))]


def homography_matrix_from_variant(variant: dict[str, Any]) -> np.ndarray | None:
    matrix = variant.get("fit", {}).get("homography")
    if not matrix:
        return None
    return np.float32(matrix)


def benchmark_composite_delta(auto: dict[str, Any], candidate: dict[str, Any]) -> float | None:
    if not auto.get("benchmark", {}).get("truthScored") or not candidate.get("benchmark", {}).get("truthScored"):
        return None
    return round_metric(benchmark_composite_score(candidate) - benchmark_composite_score(auto))


def benchmark_oracle_diagnostics(auto: dict[str, Any], variants: list[dict[str, Any]]) -> dict[str, Any]:
    """Label-scored ceiling diagnostics for improving no-label selectors.

    This must never feed runtime selection. It answers a narrower benchmark
    question: did the artifact set contain a more accurate visible geometry
    than the no-label selector chose, and what did that missed candidate look
    like?
    """
    if not auto.get("benchmark", {}).get("truthScored"):
        return {"truthScored": False}
    scored = [variant for variant in variants if variant.get("benchmark", {}).get("truthScored") and variant["decision"] != "refuse"]
    if not scored:
        return {"truthScored": False}
    return {
        "truthScored": True,
        "sourceId": auto["sourceId"],
        "selectedVariantId": auto["dotVariantId"],
        "selectedBenchmark": {
            "truthLineSamplesWithin0_15SquaresPct": auto["benchmark"].get("truthLineSamplesWithin0_15SquaresPct"),
            "truthMeshSamplesWithin0_15SquaresPct": auto["benchmark"].get("truthMeshSamplesWithin0_15SquaresPct"),
        },
        "bestLine": benchmark_oracle_entry(
            "best benchmark homography-line alignment",
            auto,
            max(scored, key=lambda variant: benchmark_metric(variant, "truthLineSamplesWithin0_15SquaresPct")),
        ),
        "bestMesh": benchmark_oracle_entry(
            "best benchmark observed-mesh alignment",
            auto,
            max(scored, key=lambda variant: benchmark_metric(variant, "truthMeshSamplesWithin0_15SquaresPct")),
        ),
        "bestComposite": benchmark_oracle_entry(
            "best benchmark line-plus-mesh alignment",
            auto,
            max(scored, key=benchmark_composite_score),
        ),
        "recommendation": "benchmark-only; labels are not available at runtime",
    }


def benchmark_oracle_entry(description: str, auto: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    candidate_summary = variant_summary(candidate)
    return {
        "description": description,
        "selectedVariantId": auto["dotVariantId"],
        "candidateVariantId": candidate["dotVariantId"],
        "differs": auto["dotVariantId"] != candidate["dotVariantId"],
        "candidate": candidate_summary,
        "truthDelta": {
            **benchmark_delta(auto.get("benchmark", {}), candidate.get("benchmark", {})),
            "compositeLineMeshPct": round_metric(benchmark_composite_score(candidate) - benchmark_composite_score(auto)),
        },
    }


def benchmark_metric(variant: dict[str, Any], key: str) -> float:
    value = variant.get("benchmark", {}).get(key)
    if value is None:
        value = variant.get(key)
    return float("-inf") if value is None else float(value)


def benchmark_composite_score(variant: dict[str, Any]) -> float:
    line = benchmark_metric(variant, "truthLineSamplesWithin0_15SquaresPct")
    mesh = benchmark_metric(variant, "truthMeshSamplesWithin0_15SquaresPct")
    if line == float("-inf") or mesh == float("-inf"):
        return float("-inf")
    return (line + mesh) / 2.0


def mesh_density_score_for_variant(variant: dict[str, Any]) -> float:
    fit = variant.get("fit", {})
    mesh = variant.get("observedMesh", {})
    span_i = float(fit.get("spanI") or variant.get("spanI") or 0)
    span_j = float(fit.get("spanJ") or variant.get("spanJ") or 0)
    cells = float(mesh.get("cellCount") or variant.get("observedMeshCells") or 0)
    return cells / max(1.0, span_i * span_j)


def span_area_for_variant(variant: dict[str, Any]) -> float:
    fit = variant.get("fit", {})
    span_i = float(fit.get("spanI") or variant.get("spanI") or 0)
    span_j = float(fit.get("spanJ") or variant.get("spanJ") or 0)
    return span_i * span_j


def select_guarded_mesh_density_variant(auto: dict[str, Any], accepted: list[dict[str, Any]]) -> dict[str, Any]:
    auto_density = mesh_density_score_for_variant(auto)
    auto_area = span_area_for_variant(auto)
    if auto_area <= 0:
        return auto

    challengers = []
    for variant in accepted:
        if variant["dotVariantId"] == auto["dotVariantId"]:
            continue
        if not early_return_safety(variant)["safe"]:
            continue
        fit = variant.get("fit", {})
        density = mesh_density_score_for_variant(variant)
        area_ratio = span_area_for_variant(variant) / auto_area
        min_span = min(float(fit.get("spanI") or 0), float(fit.get("spanJ") or 0))
        has_material_density_gain = density - auto_density >= 0.08 or density >= auto_density * 1.5
        if density < 0.35:
            continue
        if not has_material_density_gain:
            continue
        if area_ratio < 0.35:
            continue
        if min_span < 8:
            continue
        challengers.append(variant)

    if not challengers:
        return auto
    return max(challengers, key=lambda variant: (mesh_density_score_for_variant(variant), variant["selectionScore"]))


def select_borderline_conflict_fuller_variant(auto: dict[str, Any], accepted: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not selected_has_borderline_error_high_conflict(auto):
        return None
    return select_fuller_same_error_challenger(auto, accepted)


def benchmark_delta(auto: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "truthLineSamplesWithin0_15SquaresPct",
        "truthMeshSamplesWithin0_15SquaresPct",
        "truthMeshVsHomographyGainPct",
    ]
    delta = {}
    for field in fields:
        if auto.get(field) is None or candidate.get(field) is None:
            delta[field] = None
        else:
            delta[field] = round_metric(float(candidate[field]) - float(auto[field]))
    return delta


def selection_score_for_fit(metrics: dict[str, Any], decision: str) -> float:
    rank = {
        "accepted-visible-lattice-geometry": 2.0,
        "candidate-visible-lattice-geometry": 1.0,
        "refuse": 0.0,
    }.get(decision, 0.0)
    inliers = float(metrics.get("homographyInliers") or 0)
    inlier_ratio = float(metrics.get("homographyInlierRatio") or 0)
    span_i = float(metrics.get("spanI") or 0)
    span_j = float(metrics.get("spanJ") or 0)
    p90_error = float(metrics.get("p90ReprojectionErrorCells") if metrics.get("p90ReprojectionErrorCells") is not None else 2.0)
    median_support = float(metrics.get("medianLineSupport") or 0)
    p25_support = float(metrics.get("p25LineSupport") or 0)
    conflict = float(metrics.get("coordinateConflictPct") or 0)
    line_agreement = float(metrics.get("lineAgreementPct") or 0)
    min_span = min(span_i, span_j)
    area_span = math.sqrt(max(0.0, span_i * span_j))

    return (
        rank * 10000.0
        + inliers * 1.8
        + inlier_ratio * 900.0
        + min_span * 70.0
        + area_span * 20.0
        + median_support * 500.0
        + p25_support * 350.0
        + line_agreement * 8.0
        - p90_error * 1600.0
        - conflict * 24.0
    )


def manual_seed_score_for_fit(metrics: dict[str, Any], decision: str) -> float:
    if decision == "refuse":
        rank = -1.0
    else:
        rank = 1.0
    inliers = float(metrics.get("homographyInliers") or 0)
    inlier_ratio = float(metrics.get("homographyInlierRatio") or 0)
    span_i = float(metrics.get("spanI") or 0)
    span_j = float(metrics.get("spanJ") or 0)
    p90_error = float(metrics.get("p90ReprojectionErrorCells") if metrics.get("p90ReprojectionErrorCells") is not None else 2.0)
    median_support = float(metrics.get("medianLineSupport") or 0)
    p25_support = float(metrics.get("p25LineSupport") or 0)
    conflict = float(metrics.get("coordinateConflictPct") or 0)
    line_agreement = float(metrics.get("lineAgreementPct") or 0)
    min_span = min(span_i, span_j)
    area_span = math.sqrt(max(0.0, span_i * span_j))

    # Manual correction wants a wide, coherent seed even if it is not strong
    # enough for auto projection. Refusals stay below usable candidates.
    return (
        rank * 10000.0
        + inliers * 1.2
        + inlier_ratio * 250.0
        + min_span * 105.0
        + area_span * 85.0
        + median_support * 500.0
        + p25_support * 375.0
        + line_agreement * 5.0
        - p90_error * 1200.0
        - conflict * 34.0
    )


def base_metrics(
    points: np.ndarray,
    filtered_points: np.ndarray,
    median_nn: float,
    edges: list[Edge] | list[dict[str, Any]],
    axes: list[float] | None = None,
    coordinates: dict[int, tuple[int, int]] | None = None,
    conflict_rate: float | None = None,
) -> dict[str, Any]:
    metrics = {
        "dotCount": int(len(points)),
        "lineAgreementDots": int(len(filtered_points)),
        "lineAgreementPct": round_metric(float(len(filtered_points) / max(1, len(points)) * 100)),
        "medianNearestNeighborPx": round_metric(median_nn),
        "candidateEdges": int(len(edges)),
        "axisAnglesDeg": [] if axes is None else [round_metric(axis) for axis in axes],
    }
    if coordinates:
        ispan, jspan = coordinate_span(coordinates)
        metrics.update(
            {
                "assignedDots": int(len(coordinates)),
                "spanI": int(ispan),
                "spanJ": int(jspan),
            }
        )
    if conflict_rate is not None:
        metrics["coordinateConflictPct"] = round_metric(conflict_rate * 100)
    return metrics


def median_nearest_neighbor(points: np.ndarray) -> float:
    if len(points) < 2:
        return 0.0
    _, distances = nearest_neighbors(points, k=2)
    nearest = []
    for row in distances:
        positive = [float(value) for value in row if math.isfinite(float(value)) and float(value) > 1e-6]
        if positive:
            nearest.append(min(positive))
    return float(np.median(nearest)) if len(nearest) else 0.0


def nearest_neighbors(points: np.ndarray, k: int) -> tuple[np.ndarray, np.ndarray]:
    if len(points) == 0:
        return np.empty((0, 0), dtype=np.int32), np.empty((0, 0), dtype=np.float32)
    point_rows = np.float32(points)
    effective_k = max(1, min(k, len(point_rows)))
    labels = np.arange(len(point_rows), dtype=np.float32).reshape(-1, 1)
    knn = cv2.ml.KNearest_create()
    knn.train(point_rows, cv2.ml.ROW_SAMPLE, labels)
    _, _, neighbours, squared_distances = knn.findNearest(point_rows, effective_k)
    return np.rint(neighbours).astype(np.int32), np.sqrt(np.maximum(squared_distances, 0.0)).astype(np.float32)


def points_near_line(points: np.ndarray, line_distance: np.ndarray, threshold_px: float) -> np.ndarray:
    height, width = line_distance.shape[:2]
    xs = np.clip(np.rint(points[:, 0]).astype(int), 0, width - 1)
    ys = np.clip(np.rint(points[:, 1]).astype(int), 0, height - 1)
    return line_distance[ys, xs] <= threshold_px


def line_distance_transform(line_mask: np.ndarray) -> np.ndarray:
    return cv2.distanceTransform((line_mask == 0).astype(np.uint8) * 255, cv2.DIST_L2, 3)


def line_axis_angles_from_mask(line_mask: np.ndarray) -> list[float]:
    height, width = line_mask.shape[:2]
    binary = (line_mask > 0).astype(np.uint8) * 255
    lines = cv2.HoughLinesP(
        binary,
        1,
        np.pi / 720,
        threshold=35,
        minLineLength=max(28, int(min(width, height) * 0.035)),
        maxLineGap=max(6, int(min(width, height) * 0.01)),
    )
    if lines is None:
        return []
    angles = []
    weights = []
    for x1, y1, x2, y2 in lines[:, 0, :]:
        dx = float(x2 - x1)
        dy = float(y2 - y1)
        length = float(math.hypot(dx, dy))
        if length < 28:
            continue
        angles.append((math.degrees(math.atan2(dy, dx)) + 180) % 180)
        weights.append(length)
    return dominant_weighted_axes(angles, weights)


def dominant_weighted_axes(angles: list[float], weights: list[float]) -> list[float]:
    if len(angles) < 2:
        return []
    hist, bins = np.histogram(np.array(angles), bins=72, range=(0, 180), weights=np.array(weights))
    peaks = []
    scratch = hist.copy()
    for _ in range(8):
        index = int(np.argmax(scratch))
        if scratch[index] <= 0:
            break
        nearby = [(index + offset) % len(hist) for offset in range(-2, 3)]
        angle_values = []
        weight_values = []
        for item in nearby:
            angle_values.append(float((bins[item] + bins[item + 1]) / 2))
            weight_values.append(float(hist[item]))
        peaks.append((weighted_circular_mean(angle_values, weight_values), float(sum(weight_values))))
        for offset in range(-5, 6):
            scratch[(index + offset) % len(scratch)] = 0

    best_pair: list[float] = []
    best_score = -1.0
    for left_index, left in enumerate(peaks):
        for right in peaks[left_index + 1:]:
            separation = angle_distance(left[0], right[0])
            if separation < 50 or separation > 130:
                continue
            orthogonality = 1.0 - min(1.0, abs(separation - 90.0) / 90.0)
            score = math.sqrt(left[1] * right[1]) * (0.40 + 0.60 * orthogonality)
            if score > best_score:
                best_score = score
                best_pair = sorted([left[0], right[0]])
    return best_pair


def build_candidate_edges(points: np.ndarray, line_mask_dilated: np.ndarray, median_nn: float) -> list[dict[str, Any]]:
    if len(points) < 2:
        return []
    min_edge = max(3.0, median_nn * 0.45)
    max_edge = max(18.0, median_nn * 1.75)
    neighbour_indexes, neighbour_distances = nearest_neighbors(points, k=13)
    candidate_left: list[int] = []
    candidate_right: list[int] = []
    candidate_distances: list[float] = []
    for left in range(len(points)):
        for right, distance in zip(neighbour_indexes[left], neighbour_distances[left]):
            if right <= left:
                continue
            distance = float(distance)
            if not min_edge <= distance <= max_edge:
                continue
            candidate_left.append(left)
            candidate_right.append(int(right))
            candidate_distances.append(distance)
    if not candidate_left:
        return []

    left_indexes = np.array(candidate_left, dtype=np.int32)
    right_indexes = np.array(candidate_right, dtype=np.int32)
    distances = np.array(candidate_distances)
    supports = segment_support_batch(line_mask_dilated, points[left_indexes], points[right_indexes])
    keep = supports >= 0.16
    edges = []
    for left, right, distance, support in zip(left_indexes[keep], right_indexes[keep], distances[keep], supports[keep]):
        vector = points[right] - points[left]
        angle = (math.degrees(math.atan2(float(vector[1]), float(vector[0]))) + 180) % 180
        edges.append({"left": int(left), "right": int(right), "distance": float(distance), "angle": angle, "support": float(support)})
    return edges


def segment_support_batch(mask: np.ndarray, left_points: np.ndarray, right_points: np.ndarray, samples: int = 18) -> np.ndarray:
    height, width = mask.shape[:2]
    amounts = np.linspace(0.08, 0.92, samples)
    points = left_points[:, None, :] * (1.0 - amounts[None, :, None]) + right_points[:, None, :] * amounts[None, :, None]
    xs = np.clip(np.rint(points[:, :, 0]).astype(np.int32), 0, width - 1)
    ys = np.clip(np.rint(points[:, :, 1]).astype(np.int32), 0, height - 1)
    return np.mean(mask[ys, xs] > 0, axis=1)


def segment_support(mask: np.ndarray, left: np.ndarray, right: np.ndarray, samples: int = 18) -> float:
    height, width = mask.shape[:2]
    values = []
    for amount in np.linspace(0.08, 0.92, samples):
        point = left * (1.0 - amount) + right * amount
        x = int(np.clip(round(float(point[0])), 0, width - 1))
        y = int(np.clip(round(float(point[1])), 0, height - 1))
        values.append(mask[y, x] > 0)
    return float(np.mean(values))


def dominant_axes(edges: list[dict[str, Any]]) -> list[float]:
    if not edges:
        return []
    angles = np.array([edge["angle"] for edge in edges])
    weights = np.array([edge["support"] / max(1.0, edge["distance"]) for edge in edges])
    hist, bins = np.histogram(angles, bins=72, range=(0, 180), weights=weights)
    peaks = []
    scratch = hist.copy()
    for _ in range(8):
        index = int(np.argmax(scratch))
        if scratch[index] <= 0:
            break
        nearby = [(index + offset) % len(hist) for offset in range(-2, 3)]
        angle_values = []
        weight_values = []
        for item in nearby:
            center = float((bins[item] + bins[item + 1]) / 2)
            angle_values.append(center)
            weight_values.append(float(hist[item]))
        peaks.append((weighted_circular_mean(angle_values, weight_values), float(sum(weight_values))))
        for offset in range(-5, 6):
            scratch[(index + offset) % len(scratch)] = 0

    best_pair: list[float] = []
    best_score = -1.0
    for left_index, left in enumerate(peaks):
        for right in peaks[left_index + 1:]:
            separation = angle_distance(left[0], right[0])
            if separation < 35 or separation > 145:
                continue
            orthogonality = 1.0 - min(1.0, abs(separation - 90.0) / 90.0)
            score = math.sqrt(left[1] * right[1]) * (0.40 + 0.60 * orthogonality)
            if score > best_score:
                best_score = score
                best_pair = sorted([left[0], right[0]])
    return best_pair


def assign_edge_families(edges: list[dict[str, Any]], axes: list[float]) -> list[Edge]:
    assigned = []
    axis_vectors = [np.array([math.cos(math.radians(axis)), math.sin(math.radians(axis))]) for axis in axes]
    for edge in edges:
        distances = [angle_distance(float(edge["angle"]), axis) for axis in axes]
        family = int(np.argmin(distances))
        if distances[family] > 24:
            continue
        vector = axis_vectors[family]
        delta_point = np.array([0.0, 0.0])
        delta_point[family] = 1.0
        projection = float(np.dot(vector, np.array([math.cos(math.radians(edge["angle"])), math.sin(math.radians(edge["angle"]))])))
        if projection < 0:
            delta_point *= -1
        assigned.append(
            Edge(
                int(edge["left"]),
                int(edge["right"]),
                family,
                (int(delta_point[0]), int(delta_point[1])),
                float(edge["distance"]),
                float(edge["angle"]),
                float(edge["support"]),
            )
        )
    return assigned


def keep_local_step_edges(edges: list[Edge], point_count: int, axes: list[float]) -> list[Edge]:
    best: dict[tuple[int, int, int], Edge] = {}
    for edge in edges:
        for node, other, sign in ((edge.left, edge.right, 1), (edge.right, edge.left, -1)):
            delta = (edge.delta[0] * sign, edge.delta[1] * sign)
            family = edge.family
            axis_sign = 1 if delta[family] > 0 else -1
            key = (node, family, axis_sign)
            existing = best.get(key)
            score = edge.distance / max(0.05, edge.support)
            existing_score = float("inf") if existing is None else existing.distance / max(0.05, existing.support)
            if score < existing_score:
                if node == edge.left:
                    best[key] = edge
                else:
                    best[key] = Edge(edge.right, edge.left, edge.family, delta, edge.distance, edge.angle, edge.support)
    kept = {}
    for edge in best.values():
        left, right = sorted([edge.left, edge.right])
        key = (left, right, edge.family)
        existing = kept.get(key)
        if existing is None or edge.support > existing.support:
            kept[key] = edge
    return list(kept.values())


def assign_lattice_coordinates(edges: list[Edge], point_count: int) -> list[dict[str, Any]]:
    adjacency: dict[int, list[tuple[int, tuple[int, int]]]] = defaultdict(list)
    for edge in edges:
        adjacency[edge.left].append((edge.right, edge.delta))
        adjacency[edge.right].append((edge.left, (-edge.delta[0], -edge.delta[1])))

    components = []
    seen: set[int] = set()
    for start in range(point_count):
        if start in seen or start not in adjacency:
            continue
        coordinates = {start: (0, 0)}
        queue: deque[int] = deque([start])
        conflicts = 0
        edge_visits = 0
        while queue:
            node = queue.popleft()
            seen.add(node)
            origin = coordinates[node]
            for other, delta in adjacency[node]:
                edge_visits += 1
                proposed = (origin[0] + delta[0], origin[1] + delta[1])
                if other in coordinates:
                    if coordinates[other] != proposed:
                        conflicts += 1
                    continue
                coordinates[other] = proposed
                queue.append(other)
        components.append({"coordinates": coordinates, "conflicts": conflicts, "edgeVisits": edge_visits})
    return components


def geometry_metrics(
    homography: np.ndarray,
    coordinates: dict[int, tuple[int, int]],
    points: np.ndarray,
    inliers: list[int],
    median_nn: float,
    line_mask: np.ndarray,
    line_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    line_context = line_context or {"lineDistance": line_distance_transform(line_mask)}
    all_indexes = sorted(coordinates)
    source = np.float32([coordinates[index] for index in all_indexes]).reshape(1, -1, 2)
    projected = cv2.perspectiveTransform(source, homography).reshape(-1, 2)
    observed = np.float32([points[index] for index in all_indexes])
    errors_px = np.linalg.norm(projected - observed, axis=1)
    errors_cells = errors_px / max(1.0, median_nn)
    inlier_set = set(inliers)
    inlier_errors = [float(errors_cells[offset]) for offset, index in enumerate(all_indexes) if index in inlier_set]
    ispan, jspan = coordinate_span(coordinates)
    bounds = coordinate_bounds(coordinates)
    line_support = fitted_line_support(homography, coordinates, line_mask, median_nn, line_context)
    return {
        "homographyInliers": int(len(inliers)),
        "homographyInlierRatio": round_metric(len(inliers) / max(1, len(coordinates))),
        "medianReprojectionErrorCells": None if not inlier_errors else round_metric(float(np.median(inlier_errors))),
        "p90ReprojectionErrorCells": None if not inlier_errors else round_metric(float(np.percentile(inlier_errors, 90))),
        "spanI": int(ispan),
        "spanJ": int(jspan),
        "coordinateBounds": bounds,
        **line_support,
    }


def coordinate_span(coordinates: dict[int, tuple[int, int]]) -> tuple[int, int]:
    if not coordinates:
        return 0, 0
    values = list(coordinates.values())
    ispan = max(value[0] for value in values) - min(value[0] for value in values) + 1
    jspan = max(value[1] for value in values) - min(value[1] for value in values) + 1
    return int(ispan), int(jspan)


def coordinate_bounds(coordinates: dict[int, tuple[int, int]]) -> dict[str, int]:
    if not coordinates:
        return {"minI": 0, "maxI": 0, "minJ": 0, "maxJ": 0}
    values = list(coordinates.values())
    return {
        "minI": int(min(value[0] for value in values)),
        "maxI": int(max(value[0] for value in values)),
        "minJ": int(min(value[1] for value in values)),
        "maxJ": int(max(value[1] for value in values)),
    }


def fitted_line_support(
    homography: np.ndarray,
    coordinates: dict[int, tuple[int, int]],
    line_mask: np.ndarray,
    median_nn: float,
    line_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    line_context = line_context or {"lineDistance": line_distance_transform(line_mask)}
    values = list(coordinates.values())
    min_i, max_i = min(value[0] for value in values), max(value[0] for value in values)
    min_j, max_j = min(value[1] for value in values), max(value[1] for value in values)
    dist = line_context["lineDistance"]
    threshold = max(2.5, min(6.5, median_nn * 0.16))

    i_support = [
        sample_lattice_line_support(dist, homography, [[i, value] for value in np.linspace(min_j, max_j, 90)], threshold)
        for i in range(min_i, max_i + 1)
    ]
    j_support = [
        sample_lattice_line_support(dist, homography, [[value, j] for value in np.linspace(min_i, max_i, 90)], threshold)
        for j in range(min_j, max_j + 1)
    ]
    i_support = [value for value in i_support if value is not None]
    j_support = [value for value in j_support if value is not None]
    all_support = i_support + j_support
    return {
        "lineSupportThresholdPx": round_metric(threshold),
        "supportedILines": int(sum(value >= 0.30 for value in i_support)),
        "supportedJLines": int(sum(value >= 0.30 for value in j_support)),
        "medianLineSupport": None if not all_support else round_metric(float(np.median(all_support))),
        "p25LineSupport": None if not all_support else round_metric(float(np.percentile(all_support, 25))),
        "iMedianLineSupport": None if not i_support else round_metric(float(np.median(i_support))),
        "jMedianLineSupport": None if not j_support else round_metric(float(np.median(j_support))),
    }


def sample_lattice_line_support(dist: np.ndarray, homography: np.ndarray, samples: list[list[float]], threshold: float) -> float | None:
    height, width = dist.shape[:2]
    points = cv2.perspectiveTransform(np.float32(samples).reshape(1, -1, 2), homography).reshape(-1, 2)
    inside = (points[:, 0] >= 0) & (points[:, 0] < width) & (points[:, 1] >= 0) & (points[:, 1] < height)
    if int(inside.sum()) < 4:
        return None
    xs = np.clip(np.rint(points[inside, 0]).astype(int), 0, width - 1)
    ys = np.clip(np.rint(points[inside, 1]).astype(int), 0, height - 1)
    return float(np.mean(dist[ys, xs] <= threshold))


def decide_fit(metrics: dict[str, Any]) -> tuple[str, list[str]]:
    hard = []
    weak = []
    if metrics["lineAgreementDots"] < 80:
        hard.append("too few line-confirmed dots")
    if metrics.get("assignedDots", 0) < 60:
        hard.append("too few dots received lattice coordinates")
    if metrics.get("coordinateConflictPct", 100) > 25:
        hard.append("too many lattice coordinate conflicts")
    if metrics.get("homographyInliers", 0) < 60:
        hard.append("too few homography inliers")
    if min(metrics.get("spanI", 0), metrics.get("spanJ", 0)) < 7:
        hard.append("visible lattice span is too small")
    if metrics.get("p90ReprojectionErrorCells") is None or metrics.get("p90ReprojectionErrorCells", 99) > 0.22:
        hard.append("homography reprojection error is too high")
    strong_low_ratio_fit = (
        metrics.get("homographyInlierRatio", 0) >= 0.50
        and metrics.get("homographyInliers", 0) >= 160
        and min(metrics.get("spanI", 0), metrics.get("spanJ", 0)) >= 10
        and metrics.get("p90ReprojectionErrorCells", 99) <= 0.08
        and metrics.get("lineAgreementPct", 0) >= 95
        and metrics.get("medianLineSupport", 0) >= 0.70
        and metrics.get("p25LineSupport", 0) >= 0.55
        and metrics.get("coordinateConflictPct", 100) <= 10
    )
    compact_high_support_fit = (
        metrics.get("homographyInliers", 0) >= 120
        and min(metrics.get("spanI", 0), metrics.get("spanJ", 0)) >= 12
        and metrics.get("p90ReprojectionErrorCells", 99) <= 0.055
        and metrics.get("lineAgreementPct", 0) >= 95
        and metrics.get("medianLineSupport", 0) >= 0.80
        and metrics.get("p25LineSupport", 0) >= 0.65
        and metrics.get("coordinateConflictPct", 100) <= 8
    )
    if metrics.get("homographyInlierRatio", 0) < 0.65 and not (strong_low_ratio_fit or compact_high_support_fit):
        weak.append("homography inlier ratio is low")
    if metrics.get("coordinateConflictPct", 0) > 12:
        weak.append("lattice coordinate conflicts are elevated")
    if metrics.get("p25LineSupport") is not None and metrics.get("p25LineSupport", 0) < 0.60 and metrics.get("coordinateConflictPct", 0) > 10:
        weak.append("lower-quartile fitted line support is borderline while coordinate conflicts are elevated")
    if metrics.get("medianLineSupport") is None or metrics.get("medianLineSupport", 0) < 0.28:
        weak.append("fitted lines have weak mask support")
    if metrics.get("p25LineSupport") is None or metrics.get("p25LineSupport", 0) < 0.16:
        weak.append("lower-quartile fitted line support is weak")

    if hard:
        return "refuse", hard + weak
    if not weak and metrics.get("homographyInliers", 0) >= 80 and min(metrics.get("spanI", 0), metrics.get("spanJ", 0)) >= 8:
        return "accepted-visible-lattice-geometry", ["visible lattice homography only; full extent is not inferred"]
    return "candidate-visible-lattice-geometry", ["requires manual confirmation before projection", *weak]


def benchmark_fit(ai_grid: Any, label: dict[str, Any], fit: FitResult, points: np.ndarray, line_mask: np.ndarray) -> dict[str, Any]:
    if fit.homography is None or not fit.coordinates:
        return {"truthScored": False}
    scaled_label = ai_grid.scale_label(label, line_mask.shape[1], line_mask.shape[0])
    image_to_truth = cv2.getPerspectiveTransform(
        ai_grid.label_corners(scaled_label),
        np.float32([[0, 0], [scaled_label["columns"], 0], [scaled_label["columns"], scaled_label["rows"]], [0, scaled_label["rows"]]]),
    )
    inlier_points = points[fit.inlier_indexes] if fit.inlier_indexes else np.empty((0, 2), dtype=np.float32)
    dot_score = truth_dot_alignment(image_to_truth, inlier_points)
    line_score = truth_line_alignment(image_to_truth, fit.homography, fit.coordinates)
    mesh_score = truth_observed_mesh_alignment(image_to_truth, points, fit)
    return {
        "truthScored": True,
        **dot_score,
        **line_score,
        **mesh_score,
        **truth_alignment_gap(line_score, mesh_score),
    }


def truth_dot_alignment(image_to_truth: np.ndarray, points: np.ndarray) -> dict[str, Any]:
    if len(points) == 0:
        return {"truthInlierDots": 0}
    grid_points = cv2.perspectiveTransform(np.float32(points).reshape(1, -1, 2), image_to_truth).reshape(-1, 2)
    distance = np.sqrt((grid_points[:, 0] - np.rint(grid_points[:, 0])) ** 2 + (grid_points[:, 1] - np.rint(grid_points[:, 1])) ** 2)
    return {
        "truthInlierDots": int(len(points)),
        "truthMedianDotErrorSquares": round_metric(float(np.median(distance))),
        "truthP90DotErrorSquares": round_metric(float(np.percentile(distance, 90))),
        "truthDotsWithin0_15SquaresPct": round_metric(float(np.mean(distance <= 0.15) * 100)),
    }


def truth_line_alignment(image_to_truth: np.ndarray, homography: np.ndarray, coordinates: dict[int, tuple[int, int]]) -> dict[str, Any]:
    values = list(coordinates.values())
    min_i, max_i = min(value[0] for value in values), max(value[0] for value in values)
    min_j, max_j = min(value[1] for value in values), max(value[1] for value in values)
    samples = []
    for i in range(min_i, max_i + 1):
        samples.extend([[i, value] for value in np.linspace(min_j, max_j, 24)])
    for j in range(min_j, max_j + 1):
        samples.extend([[value, j] for value in np.linspace(min_i, max_i, 24)])
    image_points = cv2.perspectiveTransform(np.float32(samples).reshape(1, -1, 2), homography).reshape(-1, 2)
    truth_points = cv2.perspectiveTransform(np.float32(image_points).reshape(1, -1, 2), image_to_truth).reshape(-1, 2)
    line_distance = np.minimum(
        np.abs(truth_points[:, 0] - np.rint(truth_points[:, 0])),
        np.abs(truth_points[:, 1] - np.rint(truth_points[:, 1])),
    )
    summary = line_distance_summary("truthLine", line_distance)
    return {
        "truthLineSamples": int(len(samples)),
        "truthMedianLineErrorSquares": summary["truthLineMedianLineErrorSquares"],
        "truthP90LineErrorSquares": summary["truthLineP90LineErrorSquares"],
        **summary,
    }


def truth_observed_mesh_alignment(image_to_truth: np.ndarray, points: np.ndarray, fit: FitResult) -> dict[str, Any]:
    if not fit.inlier_indexes or fit.homography is None:
        return {"truthMeshSegments": 0}
    coordinate_to_index = {fit.coordinates[index]: index for index in fit.inlier_indexes if index in fit.coordinates}
    mesh_samples = []
    homography_grid_samples = []
    for i, j in sorted(coordinate_to_index):
        start_index = coordinate_to_index[(i, j)]
        start = points[start_index]
        for neighbor in ((i + 1, j), (i, j + 1)):
            end_index = coordinate_to_index.get(neighbor)
            if end_index is None:
                continue
            end = points[end_index]
            for amount in np.linspace(0, 1, 8):
                mesh_samples.append(start * (1.0 - amount) + end * amount)
                homography_grid_samples.append([i * (1.0 - amount) + neighbor[0] * amount, j * (1.0 - amount) + neighbor[1] * amount])
    if not mesh_samples:
        return {"truthMeshSegments": 0}
    mesh_image_points = np.float32(mesh_samples)
    homography_image_points = cv2.perspectiveTransform(np.float32(homography_grid_samples).reshape(1, -1, 2), fit.homography).reshape(-1, 2)
    mesh_truth_points = cv2.perspectiveTransform(mesh_image_points.reshape(1, -1, 2), image_to_truth).reshape(-1, 2)
    homography_truth_points = cv2.perspectiveTransform(homography_image_points.reshape(1, -1, 2), image_to_truth).reshape(-1, 2)
    mesh_distance = line_distance_to_nearest_grid(mesh_truth_points)
    homography_distance = line_distance_to_nearest_grid(homography_truth_points)
    mesh_within = float(np.mean(mesh_distance <= 0.15) * 100)
    homography_within = float(np.mean(homography_distance <= 0.15) * 100)
    return {
        "truthMeshSegments": int(len(mesh_samples) / 8),
        "truthMeshSamples": int(len(mesh_samples)),
        **line_distance_summary("truthMesh", mesh_distance),
        "truthObservedEdgeHomographySegments": int(len(homography_grid_samples) / 8),
        "truthObservedEdgeHomographySamples": int(len(homography_grid_samples)),
        **line_distance_summary("truthObservedEdgeHomography", homography_distance),
        "truthMeshVsObservedEdgeHomographyGainPct": round_metric(mesh_within - homography_within),
    }


def line_distance_to_nearest_grid(truth_points: np.ndarray) -> np.ndarray:
    return np.minimum(
        np.abs(truth_points[:, 0] - np.rint(truth_points[:, 0])),
        np.abs(truth_points[:, 1] - np.rint(truth_points[:, 1])),
    )


def line_distance_summary(prefix: str, distance: np.ndarray) -> dict[str, Any]:
    return {
        f"{prefix}MedianLineErrorSquares": round_metric(float(np.median(distance))),
        f"{prefix}P90LineErrorSquares": round_metric(float(np.percentile(distance, 90))),
        f"{prefix}P95LineErrorSquares": round_metric(float(np.percentile(distance, 95))),
        f"{prefix}MaxLineErrorSquares": round_metric(float(np.max(distance))),
        f"{prefix}SamplesWithin0_10SquaresPct": round_metric(float(np.mean(distance <= 0.10) * 100)),
        f"{prefix}SamplesWithin0_15SquaresPct": round_metric(float(np.mean(distance <= 0.15) * 100)),
        f"{prefix}SamplesWithin0_25SquaresPct": round_metric(float(np.mean(distance <= 0.25) * 100)),
    }


def truth_alignment_gap(line_score: dict[str, Any], mesh_score: dict[str, Any]) -> dict[str, Any]:
    homography = line_score.get("truthLineSamplesWithin0_15SquaresPct")
    mesh = mesh_score.get("truthMeshSamplesWithin0_15SquaresPct")
    if homography is None or mesh is None:
        return {"truthMeshVsHomographyGainPct": None}
    return {"truthMeshVsHomographyGainPct": round_metric(float(mesh) - float(homography))}


def observed_mesh_geometry(points: np.ndarray, fit: FitResult) -> dict[str, Any]:
    """Export observed inlier mesh geometry without requiring a single flat homography.

    The auto-projection decision remains homography-gated. This mesh is a
    correction/diagnostic product: it captures local inlier lattice evidence.
    """
    if not fit.inlier_indexes:
        return {
            "format": "grid-coordinate-observed-inlier-mesh-v1",
            "vertexCount": 0,
            "edgeCount": 0,
            "cellCount": 0,
            "duplicateCoordinateCount": 0,
            "vertices": [],
            "edges": [],
            "cells": [],
        }
    inlier_set = set(fit.inlier_indexes)
    coordinate_to_indexes: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index in fit.inlier_indexes:
        if index in fit.coordinates:
            coordinate_to_indexes[fit.coordinates[index]].append(index)
    duplicate_coordinate_count = sum(max(0, len(indexes) - 1) for indexes in coordinate_to_indexes.values())
    coord_to_index = {coordinate: indexes[0] for coordinate, indexes in coordinate_to_indexes.items()}
    vertices = []
    for i, j in sorted(coord_to_index):
        index = coord_to_index[(i, j)]
        if index not in inlier_set:
            continue
        point = points[index]
        vertices.append([int(i), int(j), round_metric(float(point[0])), round_metric(float(point[1]))])

    edges = []
    cells = []
    for i, j in sorted(coord_to_index):
        for neighbor in ((i + 1, j), (i, j + 1)):
            if neighbor in coord_to_index:
                edges.append([[int(i), int(j)], [int(neighbor[0]), int(neighbor[1])]])
        if (i + 1, j) in coord_to_index and (i, j + 1) in coord_to_index and (i + 1, j + 1) in coord_to_index:
            cells.append([int(i), int(j)])

    return {
        "format": "grid-coordinate-observed-inlier-mesh-v1",
        "vertexCount": len(vertices),
        "edgeCount": len(edges),
        "cellCount": len(cells),
        "duplicateCoordinateCount": int(duplicate_coordinate_count),
        "vertices": vertices,
        "edges": edges,
        "cells": cells,
    }


def projection_model_comparison(
    benchmark: dict[str, Any],
    observed_mesh: dict[str, Any],
    fit_metrics: dict[str, Any],
    decision: str | None = None,
) -> dict[str, Any]:
    full_homography_pct = benchmark.get("truthLineSamplesWithin0_15SquaresPct")
    observed_edge_homography_pct = benchmark.get("truthObservedEdgeHomographySamplesWithin0_15SquaresPct")
    mesh_pct = benchmark.get("truthMeshSamplesWithin0_15SquaresPct")
    span_i = float(fit_metrics.get("spanI") or 0)
    span_j = float(fit_metrics.get("spanJ") or 0)
    mesh_cells = int(observed_mesh.get("cellCount") or 0)
    mesh_vertices = int(observed_mesh.get("vertexCount") or 0)
    span_cell_count = int(span_i * span_j) if span_i > 0 and span_j > 0 else 0
    unsupported_cell_count = max(0, span_cell_count - mesh_cells)
    density = None if span_cell_count <= 0 else round_metric(mesh_cells / span_cell_count)
    has_projection_mesh = mesh_cells >= 50 and mesh_vertices >= 80 and (density is not None and density >= 0.14)
    full_span_confidence = full_span_projection_confidence(full_homography_pct, observed_edge_homography_pct, density)
    readiness = projection_readiness(full_span_confidence, has_projection_mesh)
    no_label_readiness = no_label_projection_readiness(
        {
            "decision": decision,
            "fit": fit_metrics,
            "observedMesh": observed_mesh,
        }
    )
    comparison = {
        "truthScored": full_homography_pct is not None and mesh_pct is not None,
        "fullSpanHomographyLineWithin0_15Pct": full_homography_pct,
        "observedEdgeHomographyLineWithin0_15Pct": observed_edge_homography_pct,
        "visibleMeshLineWithin0_15Pct": mesh_pct,
        "observedEdgeHomographyGainVsFullSpanPct": (
            None if full_homography_pct is None or observed_edge_homography_pct is None else round_metric(float(observed_edge_homography_pct) - float(full_homography_pct))
        ),
        "visibleMeshGainVsFullSpanHomographyPct": None if full_homography_pct is None or mesh_pct is None else round_metric(float(mesh_pct) - float(full_homography_pct)),
        "visibleMeshGainVsObservedEdgeHomographyPct": (
            None if observed_edge_homography_pct is None or mesh_pct is None else round_metric(float(mesh_pct) - float(observed_edge_homography_pct))
        ),
        "fullSpanHomographyMedianLineErrorSquares": benchmark.get("truthLineMedianLineErrorSquares"),
        "fullSpanHomographyP90LineErrorSquares": benchmark.get("truthLineP90LineErrorSquares"),
        "fullSpanHomographyP95LineErrorSquares": benchmark.get("truthLineP95LineErrorSquares"),
        "observedEdgeHomographyMedianLineErrorSquares": benchmark.get("truthObservedEdgeHomographyMedianLineErrorSquares"),
        "observedEdgeHomographyP90LineErrorSquares": benchmark.get("truthObservedEdgeHomographyP90LineErrorSquares"),
        "observedEdgeHomographyP95LineErrorSquares": benchmark.get("truthObservedEdgeHomographyP95LineErrorSquares"),
        "visibleMeshMedianLineErrorSquares": benchmark.get("truthMeshMedianLineErrorSquares"),
        "visibleMeshP90LineErrorSquares": benchmark.get("truthMeshP90LineErrorSquares"),
        "visibleMeshP95LineErrorSquares": benchmark.get("truthMeshP95LineErrorSquares"),
        "visibleMeshCells": mesh_cells,
        "visibleMeshVertices": mesh_vertices,
        "visibleMeshDuplicateCoordinates": observed_mesh.get("duplicateCoordinateCount"),
        "spanCellCount": span_cell_count,
        "unsupportedCellCount": unsupported_cell_count,
        "visibleMeshCellDensity": density,
        "visibleMeshCoverageSupported": has_projection_mesh,
        "fullSpanProjectionConfidence": full_span_confidence,
        "projectionReadiness": readiness,
        "noLabelProjectionReadiness": no_label_readiness,
        "recommendation": (
            "report-only observed-edge mesh comparison; promotion depends on material same-edge gain"
            if has_projection_mesh
            else "insufficient observed mesh coverage for projection-model comparison"
        ),
    }
    return comparison


def projection_readiness(confidence: dict[str, Any], has_projection_mesh: bool) -> dict[str, Any]:
    level = confidence.get("level", "unscored")
    recommendation = confidence.get("recommendation", "manual-confirmation-required")
    if level == "full-span-high":
        return {
            "mode": "full-span-homography",
            "recommendation": recommendation,
            "fullSpanAutoProject": True,
            "requiresManualExtentConfirmation": False,
            "observedRegionOnly": False,
            "hasObservedMeshSupport": bool(has_projection_mesh),
        }
    if level == "full-span-medium":
        return {
            "mode": "full-span-homography-with-manual-extent-check",
            "recommendation": recommendation,
            "fullSpanAutoProject": False,
            "requiresManualExtentConfirmation": True,
            "observedRegionOnly": False,
            "hasObservedMeshSupport": bool(has_projection_mesh),
        }
    if level == "observed-edge-only":
        return {
            "mode": "observed-edge-homography-only",
            "recommendation": recommendation,
            "fullSpanAutoProject": False,
            "requiresManualExtentConfirmation": True,
            "observedRegionOnly": True,
            "hasObservedMeshSupport": bool(has_projection_mesh),
        }
    return {
        "mode": "manual-confirmation-required",
        "recommendation": recommendation,
        "fullSpanAutoProject": False,
        "requiresManualExtentConfirmation": True,
        "observedRegionOnly": False,
        "hasObservedMeshSupport": bool(has_projection_mesh),
    }


def full_span_projection_confidence(
    full_homography_pct: float | None,
    observed_edge_homography_pct: float | None,
    observed_cell_density: float | None,
) -> dict[str, Any]:
    if full_homography_pct is None or observed_edge_homography_pct is None:
        return {
            "level": "unscored",
            "recommendation": "manual-confirmation-required",
            "reasons": ["benchmark line alignment is unavailable"],
        }
    full = float(full_homography_pct)
    observed = float(observed_edge_homography_pct)
    density = 0.0 if observed_cell_density is None else float(observed_cell_density)
    domain_gap = observed - full
    reasons = []
    if full >= 95.0 and observed >= 95.0 and domain_gap <= 5.0:
        level = "full-span-high"
        recommendation = "full-span-homography-candidate"
        reasons.append("full-span and observed-edge homography both score high")
    elif full >= 90.0 and observed >= 95.0 and domain_gap <= 8.0:
        level = "full-span-medium"
        recommendation = "full-span-homography-candidate-with-manual-extent-check"
        reasons.append("full-span homography is usable but observed-edge score is stronger")
    elif observed >= 92.0 and domain_gap >= 5.0:
        level = "observed-edge-only"
        recommendation = "project-observed-region-only-until-extent-confirmed"
        reasons.append("observed-edge homography is strong while full-span alignment drops")
    else:
        level = "manual-review"
        recommendation = "manual-confirmation-required"
        reasons.append("homography evidence is not strong enough for automatic full-span projection")
    if density < 0.25:
        reasons.append("observed inlier mesh covers a sparse fraction of the fitted span")
    return {
        "level": level,
        "recommendation": recommendation,
        "observedEdgeVsFullSpanGapPct": round_metric(domain_gap),
        "observedCellDensity": None if observed_cell_density is None else round_metric(density),
        "reasons": reasons,
    }


def write_overlay(
    ai_grid: Any,
    label: dict[str, Any],
    source_id: str,
    points: np.ndarray,
    line_mask: np.ndarray,
    fit: FitResult,
    overlays_dir: Path,
    variant_index: int = 1,
) -> Path:
    source_path = ROOT / label["sourceUrl"].removeprefix("/")
    with Image.open(source_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB").resize((line_mask.shape[1], line_mask.shape[0]), Image.Resampling.LANCZOS)
    overlay = np.array(image)
    line_tint = np.zeros_like(overlay)
    line_tint[:, :, 1] = line_mask
    overlay = cv2.addWeighted(overlay, 0.82, line_tint, 0.30, 0)
    draw_fitted_grid(overlay, fit)

    inliers = set(fit.inlier_indexes)
    assigned = set(fit.coordinates)
    for index, point in enumerate(points):
        x, y = int(round(float(point[0]))), int(round(float(point[1])))
        if index in inliers:
            color = (255, 0, 255)
            radius = 3
        elif index in assigned:
            color = (255, 180, 0)
            radius = 2
        else:
            color = (255, 110, 0)
            radius = 1
        cv2.circle(overlay, (x, y), radius, color, -1, cv2.LINE_AA)

    pil_overlay = Image.fromarray(overlay)
    draw = ImageDraw.Draw(pil_overlay)
    text = f"{source_id} v{variant_index:02d} | {fit.decision} | inliers {fit.metrics.get('homographyInliers', 0)}"
    draw.rectangle((8, 8, min(line_mask.shape[1] - 8, 780), 38), fill=(0, 0, 0))
    draw.text((14, 14), text, fill=(255, 255, 255))
    out = overlays_dir / f"{slugify(source_id)}-dot-v{variant_index:02d}-lattice.png"
    pil_overlay.save(out)
    return out


def draw_fitted_grid(overlay: np.ndarray, fit: FitResult) -> None:
    if fit.homography is None or not fit.coordinates:
        return
    height, width = overlay.shape[:2]
    values = list(fit.coordinates.values())
    min_i, max_i = min(value[0] for value in values), max(value[0] for value in values)
    min_j, max_j = min(value[1] for value in values), max(value[1] for value in values)
    for i in range(min_i, max_i + 1):
        draw_projected_polyline(overlay, fit.homography, [[i, value] for value in np.linspace(min_j, max_j, 70)], (0, 255, 255), width, height)
    for j in range(min_j, max_j + 1):
        draw_projected_polyline(overlay, fit.homography, [[value, j] for value in np.linspace(min_i, max_i, 70)], (0, 170, 255), width, height)


def draw_projected_polyline(overlay: np.ndarray, homography: np.ndarray, samples: list[list[float]], color: tuple[int, int, int], width: int, height: int) -> None:
    points = cv2.perspectiveTransform(np.float32(samples).reshape(1, -1, 2), homography).reshape(-1, 2)
    inside = points[(points[:, 0] >= -width * 0.1) & (points[:, 0] <= width * 1.1) & (points[:, 1] >= -height * 0.1) & (points[:, 1] <= height * 1.1)]
    if len(inside) >= 2:
        cv2.polylines(overlay, [np.rint(inside).astype(np.int32)], False, color, 1, cv2.LINE_AA)


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for result in results:
        counts[result["decision"]] = counts.get(result["decision"], 0) + 1
    accepted = [result for result in results if result["decision"] == "accepted-visible-lattice-geometry"]
    candidates = [result for result in results if result["decision"] == "candidate-visible-lattice-geometry"]
    return {
        "total": len(results),
        "decisions": counts,
        "acceptedVisibleGeometry": len(accepted),
        "candidateVisibleGeometry": len(candidates),
        "acceptedOrCandidateVisibleGeometry": len(accepted) + len(candidates),
        "totalDotVariantsEvaluated": sum(int(result.get("dotVariantCount", 1)) for result in results),
        "manualSeedDiffers": sum(1 for result in results if result.get("manualSeedDiffers")),
        "axisPrior": summarize_axis_prior(results),
        "componentPool": summarize_component_pool(results),
        "retryPolicies": summarize_retry_policies(results),
        "selectionDiagnostics": summarize_selection_diagnostics(results),
        "noLabelRiskDiagnostics": summarize_no_label_risk_diagnostics(results),
        "benchmarkOracleDiagnostics": summarize_benchmark_oracle_diagnostics(results),
        "projectionModelComparison": summarize_projection_model_comparison(results),
        "noLabelProjectionReadinessSensitivity": summarize_no_label_projection_readiness_sensitivity(results),
        "meshProjectionDiagnostics": summarize_mesh_projection_diagnostics(results),
    }


def summarize_mesh_projection_diagnostics(results: list[dict[str, Any]]) -> dict[str, Any]:
    scored = [result for result in results if result.get("benchmark", {}).get("truthMeshVsHomographyGainPct") is not None]
    if not scored:
        return {"total": 0}
    candidates = []
    for result in scored:
        bench = result["benchmark"]
        mesh = result.get("observedMesh", {})
        comparison = result.get("projectionModelComparison", {})
        full_gain = float(bench.get("truthMeshVsHomographyGainPct") or 0.0)
        same_edge_gain = float(comparison.get("visibleMeshGainVsObservedEdgeHomographyPct") or 0.0)
        mesh_pct = float(bench.get("truthMeshSamplesWithin0_15SquaresPct") or 0.0)
        line_pct = float(bench.get("truthLineSamplesWithin0_15SquaresPct") or 0.0)
        observed_edge_pct = float(comparison.get("observedEdgeHomographyLineWithin0_15Pct") or 0.0)
        cell_count = int(mesh.get("cellCount") or 0)
        vertex_count = int(mesh.get("vertexCount") or 0)
        density = comparison.get("visibleMeshCellDensity")
        span = result.get("fit", {})
        if same_edge_gain >= 5.0 and mesh_pct >= 90.0 and cell_count >= 50 and vertex_count >= 80:
            candidates.append(
                {
                    "sourceId": result["sourceId"],
                    "dotVariantId": result["dotVariantId"],
                    "homographyLineWithin0_15Pct": round_metric(line_pct),
                    "observedEdgeHomographyLineWithin0_15Pct": round_metric(observed_edge_pct),
                    "meshLineWithin0_15Pct": round_metric(mesh_pct),
                    "fullSpanGainPct": round_metric(full_gain),
                    "sameEdgeGainPct": round_metric(same_edge_gain),
                    "meshCells": cell_count,
                    "meshVertices": vertex_count,
                    "meshCellDensity": density,
                    "span": f"{span.get('spanI')}x{span.get('spanJ')}",
                }
            )
    gains = [float(result["benchmark"].get("truthMeshVsHomographyGainPct") or 0.0) for result in scored]
    same_edge_gains = [
        float(result.get("projectionModelComparison", {}).get("visibleMeshGainVsObservedEdgeHomographyPct") or 0.0)
        for result in scored
    ]
    return {
        "total": len(scored),
        "candidateCount": len(candidates),
        "meanGainPct": mean_or_none(gains),
        "maxGainPct": None if not gains else round_metric(max(gains)),
        "meanSameEdgeGainPct": mean_or_none(same_edge_gains),
        "maxSameEdgeGainPct": None if not same_edge_gains else round_metric(max(same_edge_gains)),
        "candidateCriteria": "same-edge mesh gain >= 5 points, mesh <=.15 >= 90%, cells >= 50, vertices >= 80",
        "candidates": candidates,
        "recommendation": (
            "report-only; evaluate a visible-region mesh warp only where same-edge gain is material and mesh coverage is dense"
            if candidates
            else "report-only; current same-edge gains do not justify visible-region mesh warp promotion"
        ),
    }


def summarize_projection_model_comparison(results: list[dict[str, Any]]) -> dict[str, Any]:
    comparisons = [result.get("projectionModelComparison", {}) for result in results]
    scored = [item for item in comparisons if item.get("truthScored")]
    if not scored:
        return {"total": 0}
    homography_values = [item.get("fullSpanHomographyLineWithin0_15Pct") for item in scored if item.get("fullSpanHomographyLineWithin0_15Pct") is not None]
    observed_edge_homography_values = [
        item.get("observedEdgeHomographyLineWithin0_15Pct")
        for item in scored
        if item.get("observedEdgeHomographyLineWithin0_15Pct") is not None
    ]
    mesh_values = [item.get("visibleMeshLineWithin0_15Pct") for item in scored if item.get("visibleMeshLineWithin0_15Pct") is not None]
    full_span_gains = [item.get("visibleMeshGainVsFullSpanHomographyPct") for item in scored if item.get("visibleMeshGainVsFullSpanHomographyPct") is not None]
    observed_edge_gains = [
        item.get("visibleMeshGainVsObservedEdgeHomographyPct")
        for item in scored
        if item.get("visibleMeshGainVsObservedEdgeHomographyPct") is not None
    ]
    domain_gains = [
        item.get("observedEdgeHomographyGainVsFullSpanPct")
        for item in scored
        if item.get("observedEdgeHomographyGainVsFullSpanPct") is not None
    ]
    densities = [item.get("visibleMeshCellDensity") for item in scored if item.get("visibleMeshCellDensity") is not None]
    cells = [float(item.get("visibleMeshCells") or 0) for item in scored]
    vertices = [float(item.get("visibleMeshVertices") or 0) for item in scored]
    duplicates = [float(item.get("visibleMeshDuplicateCoordinates") or 0) for item in scored]
    confidence_counts: dict[str, int] = {}
    readiness_counts: dict[str, int] = {}
    no_label_readiness_counts: dict[str, int] = {}
    for item in scored:
        level = item.get("fullSpanProjectionConfidence", {}).get("level", "unknown")
        confidence_counts[level] = confidence_counts.get(level, 0) + 1
        readiness_mode = item.get("projectionReadiness", {}).get("mode", "unknown")
        readiness_counts[readiness_mode] = readiness_counts.get(readiness_mode, 0) + 1
        no_label_mode = item.get("noLabelProjectionReadiness", {}).get("mode", "unknown")
        no_label_readiness_counts[no_label_mode] = no_label_readiness_counts.get(no_label_mode, 0) + 1
    full_span_auto_ready = [item for item in scored if item.get("projectionReadiness", {}).get("fullSpanAutoProject")]
    no_label_full_span_auto_ready = [item for item in scored if item.get("noLabelProjectionReadiness", {}).get("fullSpanAutoProject")]
    manual_projection_confirmation = [
        item
        for item in scored
        if item.get("projectionReadiness", {}).get("requiresManualExtentConfirmation")
        or not item.get("projectionReadiness", {}).get("fullSpanAutoProject")
    ]
    no_label_manual_projection_confirmation = [
        item
        for item in scored
        if item.get("noLabelProjectionReadiness", {}).get("requiresManualExtentConfirmation")
        or not item.get("noLabelProjectionReadiness", {}).get("fullSpanAutoProject")
    ]
    no_label_auto_benchmark_not_auto = [
        item
        for item in scored
        if item.get("noLabelProjectionReadiness", {}).get("fullSpanAutoProject")
        and not item.get("projectionReadiness", {}).get("fullSpanAutoProject")
    ]
    benchmark_auto_no_label_not_auto = [
        item
        for item in scored
        if item.get("projectionReadiness", {}).get("fullSpanAutoProject")
        and not item.get("noLabelProjectionReadiness", {}).get("fullSpanAutoProject")
    ]
    observed_edge_only = [
        item
        for item in scored
        if item.get("fullSpanProjectionConfidence", {}).get("level") == "observed-edge-only"
    ]
    material = [
        item
        for item in scored
        if float(item.get("visibleMeshGainVsObservedEdgeHomographyPct") or 0.0) >= 5.0 and item.get("visibleMeshCoverageSupported")
    ]
    return {
        "total": len(scored),
        "visibleMeshCoverageSupported": sum(1 for item in scored if item.get("visibleMeshCoverageSupported")),
        "fullSpanHomographyMeanLineWithin0_15Pct": mean_or_none(homography_values),
        "fullSpanHomographyMinLineWithin0_15Pct": min_or_none(homography_values),
        "observedEdgeHomographyMeanLineWithin0_15Pct": mean_or_none(observed_edge_homography_values),
        "observedEdgeHomographyMinLineWithin0_15Pct": min_or_none(observed_edge_homography_values),
        "visibleMeshMeanLineWithin0_15Pct": mean_or_none(mesh_values),
        "visibleMeshMinLineWithin0_15Pct": min_or_none(mesh_values),
        "meanVisibleMeshGainVsFullSpanHomographyPct": mean_or_none(full_span_gains),
        "maxVisibleMeshGainVsFullSpanHomographyPct": max_or_none(full_span_gains),
        "meanVisibleMeshGainVsObservedEdgeHomographyPct": mean_or_none(observed_edge_gains),
        "maxVisibleMeshGainVsObservedEdgeHomographyPct": max_or_none(observed_edge_gains),
        "meanObservedEdgeHomographyGainVsFullSpanPct": mean_or_none(domain_gains),
        "maxObservedEdgeHomographyGainVsFullSpanPct": max_or_none(domain_gains),
        "materialGainCount": len(material),
        "meanVisibleMeshCellDensity": mean_or_none(densities),
        "minVisibleMeshCellDensity": min_or_none(densities),
        "meanVisibleMeshCells": mean_or_none(cells),
        "meanVisibleMeshVertices": mean_or_none(vertices),
        "totalDuplicateCoordinates": int(sum(duplicates)),
        "fullSpanProjectionConfidenceCounts": confidence_counts,
        "projectionReadinessCounts": readiness_counts,
        "noLabelProjectionReadinessCounts": no_label_readiness_counts,
        "fullSpanAutoProjectCount": len(full_span_auto_ready),
        "noLabelFullSpanAutoProjectCount": len(no_label_full_span_auto_ready),
        "manualProjectionConfirmationCount": len(manual_projection_confirmation),
        "noLabelManualProjectionConfirmationCount": len(no_label_manual_projection_confirmation),
        "wrongConfidentIfAcceptedMeansFullSpanCount": len(manual_projection_confirmation),
        "noLabelAutoButBenchmarkNotAutoCount": len(no_label_auto_benchmark_not_auto),
        "benchmarkAutoButNoLabelAutoCount": len(benchmark_auto_no_label_not_auto),
        "wrongConfidentDefinition": "selected accepted visible geometry that should not be treated as automatic full-span projection",
        "observedEdgeOnlyCount": len(observed_edge_only),
        "observedEdgeOnlyCases": [
            {
                "sourceId": result["sourceId"],
                "dotVariantId": result["dotVariantId"],
                "fullSpanHomographyLineWithin0_15Pct": result["projectionModelComparison"].get("fullSpanHomographyLineWithin0_15Pct"),
                "observedEdgeHomographyLineWithin0_15Pct": result["projectionModelComparison"].get("observedEdgeHomographyLineWithin0_15Pct"),
                "observedEdgeVsFullSpanGapPct": result["projectionModelComparison"].get("fullSpanProjectionConfidence", {}).get("observedEdgeVsFullSpanGapPct"),
                "visibleMeshCellDensity": result["projectionModelComparison"].get("visibleMeshCellDensity"),
                "unsupportedCellCount": result["projectionModelComparison"].get("unsupportedCellCount"),
                "spanCellCount": result["projectionModelComparison"].get("spanCellCount"),
                "readinessMode": result["projectionModelComparison"].get("projectionReadiness", {}).get("mode"),
                "recommendation": result["projectionModelComparison"].get("fullSpanProjectionConfidence", {}).get("recommendation"),
            }
            for result in results
            if result.get("projectionModelComparison", {}).get("fullSpanProjectionConfidence", {}).get("level") == "observed-edge-only"
        ],
        "noLabelAutoButBenchmarkNotAutoCases": [
            {
                "sourceId": result["sourceId"],
                "dotVariantId": result["dotVariantId"],
                "benchmarkReadinessMode": result["projectionModelComparison"].get("projectionReadiness", {}).get("mode"),
                "noLabelReadinessMode": result["projectionModelComparison"].get("noLabelProjectionReadiness", {}).get("mode"),
                "fullSpanHomographyLineWithin0_15Pct": result["projectionModelComparison"].get("fullSpanHomographyLineWithin0_15Pct"),
                "observedEdgeHomographyLineWithin0_15Pct": result["projectionModelComparison"].get("observedEdgeHomographyLineWithin0_15Pct"),
                "noLabelReasons": result["projectionModelComparison"].get("noLabelProjectionReadiness", {}).get("reasons"),
            }
            for result in results
            if result.get("projectionModelComparison", {}).get("noLabelProjectionReadiness", {}).get("fullSpanAutoProject")
            and not result.get("projectionModelComparison", {}).get("projectionReadiness", {}).get("fullSpanAutoProject")
        ],
        "benchmarkAutoButNoLabelAutoCases": [
            {
                "sourceId": result["sourceId"],
                "dotVariantId": result["dotVariantId"],
                "benchmarkReadinessMode": result["projectionModelComparison"].get("projectionReadiness", {}).get("mode"),
                "noLabelReadinessMode": result["projectionModelComparison"].get("noLabelProjectionReadiness", {}).get("mode"),
                "fullSpanHomographyLineWithin0_15Pct": result["projectionModelComparison"].get("fullSpanHomographyLineWithin0_15Pct"),
                "observedEdgeHomographyLineWithin0_15Pct": result["projectionModelComparison"].get("observedEdgeHomographyLineWithin0_15Pct"),
                "noLabelReasons": result["projectionModelComparison"].get("noLabelProjectionReadiness", {}).get("reasons"),
            }
            for result in results
            if result.get("projectionModelComparison", {}).get("projectionReadiness", {}).get("fullSpanAutoProject")
            and not result.get("projectionModelComparison", {}).get("noLabelProjectionReadiness", {}).get("fullSpanAutoProject")
        ],
        "recommendation": (
            "report-only; same-edge mesh gain is material on at least one fit, evaluate visible-region mesh warp cautiously"
            if material
            else "report-only; same-edge comparison does not yet justify mesh-warp promotion"
        ),
    }


def summarize_no_label_projection_readiness_sensitivity(results: list[dict[str, Any]]) -> dict[str, Any]:
    gates = [
        ("current-no-label", no_label_sensitivity_current, "current strict no-label full-span gate"),
        (
            "small-span-relaxed-v1",
            no_label_sensitivity_small_span_relaxed,
            "report-only: accepts small safe fits with strong local support and modest observed-mesh density",
        ),
        (
            "clean-subspan-v1",
            no_label_sensitivity_clean_subspan,
            "report-only: accepts safe clean subspans with no simple no-label risk flags",
        ),
        (
            "medium-density-v1",
            no_label_sensitivity_medium_density,
            "report-only: accepts medium safe fits with enough density/support to test conservative full-span promotion",
        ),
    ]
    summaries = []
    for name, gate, description in gates:
        candidates = []
        promoted = []
        dangerous = []
        selected_different = []
        for result in results:
            variants = result.get("dotVariantsByOrder", [])
            candidate = select_sensitivity_candidate(variants, gate)
            if candidate is None:
                continue
            candidates.append(candidate)
            selected_id = result.get("dotVariantId")
            if candidate.get("dotVariantId") != selected_id:
                selected_different.append(
                    {
                        "sourceId": result["sourceId"],
                        "selectedVariantId": selected_id,
                        "candidateVariantId": candidate.get("dotVariantId"),
                        "selectedNoLabelReadiness": result.get("projectionModelComparison", {}).get("noLabelProjectionReadiness", {}).get("mode"),
                        "candidateTruthLinePct": candidate.get("truthLineSamplesWithin0_15SquaresPct"),
                        "candidateObservedEdgePct": candidate.get("observedEdgeHomographyLineWithin0_15Pct"),
                        "candidateSpan": f"{candidate.get('spanI')}x{candidate.get('spanJ')}",
                    }
                )
            if not candidate.get("noLabelFullSpanAutoProject"):
                promoted.append(
                    {
                        "sourceId": result["sourceId"],
                        "candidateVariantId": candidate.get("dotVariantId"),
                        "currentSelectedVariantId": selected_id,
                        "currentSelectedNoLabelReadiness": result.get("projectionModelComparison", {}).get("noLabelProjectionReadiness", {}).get("mode"),
                        "candidateTruthLinePct": candidate.get("truthLineSamplesWithin0_15SquaresPct"),
                        "candidateObservedEdgePct": candidate.get("observedEdgeHomographyLineWithin0_15Pct"),
                        "candidateMeshPct": candidate.get("truthMeshSamplesWithin0_15SquaresPct"),
                        "candidateSpan": f"{candidate.get('spanI')}x{candidate.get('spanJ')}",
                        "candidateMetrics": sensitivity_metrics(candidate),
                    }
                )
            if sensitivity_is_dangerous(candidate):
                dangerous.append(
                    {
                        "sourceId": result["sourceId"],
                        "candidateVariantId": candidate.get("dotVariantId"),
                        "candidateTruthLinePct": candidate.get("truthLineSamplesWithin0_15SquaresPct"),
                        "candidateObservedEdgePct": candidate.get("observedEdgeHomographyLineWithin0_15Pct"),
                        "candidateMeshPct": candidate.get("truthMeshSamplesWithin0_15SquaresPct"),
                        "candidateSpan": f"{candidate.get('spanI')}x{candidate.get('spanJ')}",
                        "candidateMetrics": sensitivity_metrics(candidate),
                    }
                )
        summaries.append(
            {
                "gate": name,
                "description": description,
                "candidateCount": len(candidates),
                "selectedDifferentCount": len(selected_different),
                "promotedBeyondCurrentCount": len(promoted),
                "dangerousBenchmarkDisagreementCount": len(dangerous),
                "meanTruthLinePct": mean_or_none([candidate.get("truthLineSamplesWithin0_15SquaresPct") for candidate in candidates if candidate.get("truthLineSamplesWithin0_15SquaresPct") is not None]),
                "minTruthLinePct": min_or_none([candidate.get("truthLineSamplesWithin0_15SquaresPct") for candidate in candidates if candidate.get("truthLineSamplesWithin0_15SquaresPct") is not None]),
                "meanObservedEdgePct": mean_or_none([candidate.get("observedEdgeHomographyLineWithin0_15Pct") for candidate in candidates if candidate.get("observedEdgeHomographyLineWithin0_15Pct") is not None]),
                "minObservedEdgePct": min_or_none([candidate.get("observedEdgeHomographyLineWithin0_15Pct") for candidate in candidates if candidate.get("observedEdgeHomographyLineWithin0_15Pct") is not None]),
                "selectedDifferentCases": selected_different,
                "promotedBeyondCurrentCases": promoted,
                "dangerousBenchmarkDisagreements": dangerous,
            }
        )
    return {
        "total": len(results),
        "benchmarkOnly": True,
        "recommendation": "report-only sensitivity sweep; use to design larger-corpus no-label gates, not runtime selection",
        "gates": summaries,
    }


def select_sensitivity_candidate(variants: list[dict[str, Any]], gate: Any) -> dict[str, Any] | None:
    candidates = [
        variant
        for variant in variants
        if variant.get("decision") == "accepted-visible-lattice-geometry" and gate(variant)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda variant: float(variant.get("selectionScore") or 0.0))


def no_label_sensitivity_current(variant: dict[str, Any]) -> bool:
    return bool(variant.get("noLabelFullSpanAutoProject"))


def no_label_sensitivity_small_span_relaxed(variant: dict[str, Any]) -> bool:
    if no_label_sensitivity_current(variant):
        return True
    return (
        bool((variant.get("earlyReturnSafety") or {}).get("safe"))
        and sensitivity_span_area(variant) <= 300
        and sensitivity_value(variant, "homographyInlierRatio") >= 0.80
        and sensitivity_value(variant, "p90ReprojectionErrorCells", 99.0) <= 0.05
        and sensitivity_value(variant, "medianLineSupport") >= 0.88
        and sensitivity_value(variant, "p25LineSupport") >= 0.65
        and sensitivity_value(variant, "coordinateConflictPct", 100.0) <= 4.0
        and sensitivity_value(variant, "observedMeshCellDensity") >= 0.25
    )


def no_label_sensitivity_clean_subspan(variant: dict[str, Any]) -> bool:
    if no_label_sensitivity_small_span_relaxed(variant):
        return True
    return (
        bool((variant.get("earlyReturnSafety") or {}).get("safe"))
        and not sensitivity_risk_flags(variant)
        and min(sensitivity_value(variant, "spanI"), sensitivity_value(variant, "spanJ")) >= 16
        and sensitivity_value(variant, "homographyInlierRatio") >= 0.74
        and sensitivity_value(variant, "p90ReprojectionErrorCells", 99.0) <= 0.03
        and sensitivity_value(variant, "medianLineSupport") >= 0.95
        and sensitivity_value(variant, "p25LineSupport") >= 0.80
        and sensitivity_value(variant, "coordinateConflictPct", 100.0) <= 4.0
        and sensitivity_value(variant, "observedMeshCellDensity") >= 0.29
    )


def no_label_sensitivity_medium_density(variant: dict[str, Any]) -> bool:
    if no_label_sensitivity_clean_subspan(variant):
        return True
    return (
        bool((variant.get("earlyReturnSafety") or {}).get("safe"))
        and not sensitivity_risk_flags(variant)
        and min(sensitivity_value(variant, "spanI"), sensitivity_value(variant, "spanJ")) >= 19
        and sensitivity_value(variant, "homographyInlierRatio") >= 0.58
        and sensitivity_value(variant, "p90ReprojectionErrorCells", 99.0) <= 0.04
        and sensitivity_value(variant, "medianLineSupport") >= 0.85
        and sensitivity_value(variant, "p25LineSupport") >= 0.72
        and sensitivity_value(variant, "coordinateConflictPct", 100.0) <= 10.0
        and sensitivity_value(variant, "observedMeshCellDensity") >= 0.28
    )


def sensitivity_is_dangerous(variant: dict[str, Any]) -> bool:
    return (
        sensitivity_value(variant, "truthLineSamplesWithin0_15SquaresPct") < 95.0
        or sensitivity_value(variant, "observedEdgeHomographyLineWithin0_15Pct") < 95.0
    )


def sensitivity_risk_flags(variant: dict[str, Any]) -> list[str]:
    flags = []
    p90 = sensitivity_value(variant, "p90ReprojectionErrorCells", 99.0)
    conflict = sensitivity_value(variant, "coordinateConflictPct", 100.0)
    density = sensitivity_value(variant, "observedMeshCellDensity")
    p25_support = sensitivity_value(variant, "p25LineSupport")
    inlier_ratio = sensitivity_value(variant, "homographyInlierRatio")
    if p90 >= 0.05 and conflict >= 7.0:
        flags.append("borderline reprojection error plus high coordinate conflicts")
    if p90 >= 0.06 and density < 0.35:
        flags.append("borderline reprojection error plus sparse observed mesh density")
    if p25_support < 0.70 and inlier_ratio < 0.70:
        flags.append("low lower-quartile line support plus lower inlier ratio")
    return flags


def sensitivity_metrics(variant: dict[str, Any]) -> dict[str, Any]:
    return {
        "span": f"{variant.get('spanI')}x{variant.get('spanJ')}",
        "homographyInlierRatio": variant.get("homographyInlierRatio"),
        "p90ReprojectionErrorCells": variant.get("p90ReprojectionErrorCells"),
        "medianLineSupport": variant.get("medianLineSupport"),
        "p25LineSupport": variant.get("p25LineSupport"),
        "coordinateConflictPct": variant.get("coordinateConflictPct"),
        "observedMeshCellDensity": variant.get("observedMeshCellDensity"),
        "earlyReturnSafe": (variant.get("earlyReturnSafety") or {}).get("safe"),
        "riskFlags": sensitivity_risk_flags(variant),
    }


def sensitivity_span_area(variant: dict[str, Any]) -> float:
    return sensitivity_value(variant, "spanI") * sensitivity_value(variant, "spanJ")


def sensitivity_value(variant: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = variant.get(key)
    return float(default) if value is None else float(value)


def summarize_benchmark_oracle_diagnostics(results: list[dict[str, Any]]) -> dict[str, Any]:
    entries = [result.get("benchmarkOracleDiagnostics", {}) for result in results]
    entries = [entry for entry in entries if entry.get("truthScored")]
    if not entries:
        return {"total": 0}
    composite_deltas = [
        entry.get("bestComposite", {}).get("truthDelta", {}).get("compositeLineMeshPct")
        for entry in entries
        if entry.get("bestComposite", {}).get("truthDelta", {}).get("compositeLineMeshPct") is not None
    ]
    material = [entry for entry in entries if float(entry.get("bestComposite", {}).get("truthDelta", {}).get("compositeLineMeshPct") or 0.0) >= 5.0]
    return {
        "total": len(entries),
        "bestCompositeDiffers": sum(1 for entry in entries if entry.get("bestComposite", {}).get("differs")),
        "materialBestCompositeMisses": len(material),
        "meanCompositeDeltaPct": mean_or_none(composite_deltas),
        "maxCompositeDeltaPct": max_or_none(composite_deltas),
        "materialMisses": [
            {
                "sourceId": entry["sourceId"],
                "selectedVariantId": entry["selectedVariantId"],
                "oracleVariantId": entry["bestComposite"]["candidateVariantId"],
                "selectedLinePct": entry["selectedBenchmark"].get("truthLineSamplesWithin0_15SquaresPct"),
                "oracleLinePct": entry["bestComposite"]["candidate"].get("truthLineSamplesWithin0_15SquaresPct"),
                "selectedMeshPct": entry["selectedBenchmark"].get("truthMeshSamplesWithin0_15SquaresPct"),
                "oracleMeshPct": entry["bestComposite"]["candidate"].get("truthMeshSamplesWithin0_15SquaresPct"),
                "compositeDeltaPct": entry["bestComposite"]["truthDelta"].get("compositeLineMeshPct"),
                "oracleDecision": entry["bestComposite"]["candidate"].get("decision"),
                "oracleSpan": f"{entry['bestComposite']['candidate'].get('spanI')}x{entry['bestComposite']['candidate'].get('spanJ')}",
            }
            for entry in material
        ],
        "recommendation": "benchmark-only; use these misses to design no-label quality proxies, never as runtime selection input",
    }


def summarize_axis_prior(results: list[dict[str, Any]]) -> dict[str, Any]:
    variants = [
        variant
        for result in results
        for variant in result.get("dotVariantsByOrder", [])
        if variant.get("axisSelectedMode") is not None
    ]
    selected = [result for result in results if result.get("fit", {}).get("axisSelectedMode") is not None]
    variants_with_line_prior = [
        variant
        for variant in variants
        if "line-mask-angle-prior" in (variant.get("axisCandidateModes") or [])
    ]
    return {
        "selectedResultsWithAxisCandidates": len(selected),
        "selectedLineMaskPrior": sum(1 for result in selected if result.get("fit", {}).get("axisSelectedMode") == "line-mask-angle-prior"),
        "variantAxisCandidatesEvaluated": sum(int(variant.get("axisCandidateCount") or 0) for variant in variants),
        "variantResultsWithAxisCandidates": len(variants),
        "variantLineMaskPriorEvaluated": len(variants_with_line_prior),
        "variantLineMaskPriorSelected": sum(1 for variant in variants if variant.get("axisSelectedMode") == "line-mask-angle-prior"),
    }


def summarize_component_pool(results: list[dict[str, Any]]) -> dict[str, Any]:
    variants = [
        variant
        for result in results
        for variant in result.get("dotVariantsByOrder", [])
        if variant.get("componentPoolEvaluated") is not None
    ]
    selected = [result for result in results if result.get("fit", {}).get("componentPoolSelectedRank") is not None]
    return {
        "selectedResultsWithPool": len(selected),
        "selectedNonLargestComponent": sum(1 for result in selected if result.get("fit", {}).get("componentPoolSelectedRank") != 1),
        "variantPoolsEvaluated": len(variants),
        "variantNonLargestComponent": sum(1 for variant in variants if variant.get("componentPoolSelectedRank") != 1),
    }


def summarize_retry_policies(results: list[dict[str, Any]]) -> dict[str, Any]:
    policy_names = sorted({name for result in results for name in result.get("retryPolicies", {})})
    summary: dict[str, Any] = {}
    for name in policy_names:
        choices = [result["retryPolicies"][name] for result in results if name in result.get("retryPolicies", {})]
        decisions: dict[str, int] = {}
        no_label_readiness: dict[str, int] = {}
        for choice in choices:
            decisions[choice["decision"]] = decisions.get(choice["decision"], 0) + 1
            readiness_mode = choice.get("noLabelProjectionReadinessMode", "unknown")
            no_label_readiness[readiness_mode] = no_label_readiness.get(readiness_mode, 0) + 1
        safe_choices = [choice for choice in choices if choice.get("earlyReturnSafe")]
        no_label_full_span = [choice for choice in choices if choice.get("noLabelFullSpanAutoProject")]
        accepted_no_label_not_full_span = [
            choice
            for choice in choices
            if choice.get("decision") == "accepted-visible-lattice-geometry"
            and not choice.get("noLabelFullSpanAutoProject")
        ]
        summary[name] = {
            "total": len(choices),
            "decisions": decisions,
            "noLabelProjectionReadiness": no_label_readiness,
            "noLabelFullSpanAutoProject": len(no_label_full_span),
            "allNoLabelFullSpanAutoProject": len(no_label_full_span) == len(choices),
            "acceptedButNoLabelNotFullSpan": len(accepted_no_label_not_full_span),
            "earlyReturnSafe": len(safe_choices),
            "allEarlyReturnSafe": len(safe_choices) == len(choices),
            "totalDotSamples": sum(int(choice["samplesUsed"]) for choice in choices),
            "meanDotSamples": None if not choices else round_metric(sum(int(choice["samplesUsed"]) for choice in choices) / len(choices)),
            "totalCompletedDotSamples": None
            if not any(choice.get("completedDotSamples") is not None for choice in choices)
            else sum(int(choice.get("completedDotSamples") or 0) for choice in choices),
            "meanCompletedDotSamples": None
            if not any(choice.get("completedDotSamples") is not None for choice in choices)
            else round_metric(
                sum(int(choice.get("completedDotSamples") or 0) for choice in choices)
                / max(1, sum(1 for choice in choices if choice.get("completedDotSamples") is not None))
            ),
            "meanEstimatedParallelWallMs": None
            if not any(choice.get("estimatedParallelWallMs") is not None for choice in choices)
            else round_metric(
                sum(float(choice.get("estimatedParallelWallMs") or 0) for choice in choices)
                / max(1, sum(1 for choice in choices if choice.get("estimatedParallelWallMs") is not None))
            ),
            "maxEstimatedParallelWallMs": None
            if not any(choice.get("estimatedParallelWallMs") is not None for choice in choices)
            else round_metric(max(float(choice.get("estimatedParallelWallMs") or 0) for choice in choices)),
        }
    return summary


def summarize_selection_diagnostics(results: list[dict[str, Any]]) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {}
    for key in ["acceptedMeshDensity", "guardedMeshDensity"]:
        entries = [
            result.get("selectionDiagnostics", {}).get(key)
            for result in results
            if result.get("selectionDiagnostics", {}).get(key)
        ]
        diagnostics[key] = summarize_selection_diagnostic_entries(entries)
    return diagnostics


def summarize_no_label_risk_diagnostics(results: list[dict[str, Any]]) -> dict[str, Any]:
    entries = [result.get("noLabelRiskDiagnostics", {}) for result in results if result.get("noLabelRiskDiagnostics")]
    if not entries:
        return {"total": 0}
    flag_counts: dict[str, int] = {}
    for entry in entries:
        for flag in entry.get("riskFlags", []):
            flag_counts[flag] = flag_counts.get(flag, 0) + 1
    fuller_entries = [
        (result, result.get("noLabelRiskDiagnostics", {}).get("fullerSameErrorChallenger"))
        for result in results
        if result.get("noLabelRiskDiagnostics", {}).get("fullerSameErrorChallenger")
    ]
    borderline_conflict_fuller_entries = [
        (result, result.get("noLabelRiskDiagnostics", {}).get("borderlineConflictFullerChallenger"))
        for result in results
        if result.get("noLabelRiskDiagnostics", {}).get("borderlineConflictFullerChallenger")
    ]
    precise_subset_entries = [
        (result, result.get("noLabelRiskDiagnostics", {}).get("preciseSubsetChallenger"))
        for result in results
        if result.get("noLabelRiskDiagnostics", {}).get("preciseSubsetChallenger")
    ]
    high_precision_compact_entries = [
        (result, result.get("noLabelRiskDiagnostics", {}).get("highPrecisionCompactChallenger"))
        for result in results
        if result.get("noLabelRiskDiagnostics", {}).get("highPrecisionCompactChallenger")
    ]
    fuller_deltas = [
        item.get("benchmarkCompositeDeltaPct")
        for _, item in fuller_entries
        if item and item.get("benchmarkCompositeDeltaPct") is not None
    ]
    borderline_conflict_fuller_deltas = [
        item.get("benchmarkCompositeDeltaPct")
        for _, item in borderline_conflict_fuller_entries
        if item and item.get("benchmarkCompositeDeltaPct") is not None
    ]
    precise_subset_deltas = [
        item.get("benchmarkCompositeDeltaPct")
        for _, item in precise_subset_entries
        if item and item.get("benchmarkCompositeDeltaPct") is not None
    ]
    high_precision_compact_deltas = [
        item.get("benchmarkCompositeDeltaPct")
        for _, item in high_precision_compact_entries
        if item and item.get("benchmarkCompositeDeltaPct") is not None
    ]
    ambiguous = [result for result in results if result.get("noLabelRiskDiagnostics", {}).get("selectionAmbiguous")]
    return {
        "total": len(entries),
        "selectionAmbiguousCount": len(ambiguous),
        "flagCounts": flag_counts,
        "fullerSameErrorChallengerCount": len(fuller_entries),
        "fullerSameErrorPositiveCount": sum(1 for delta in fuller_deltas if float(delta) > 0),
        "fullerSameErrorNegativeCount": sum(1 for delta in fuller_deltas if float(delta) < 0),
        "fullerSameErrorMeanCompositeDeltaPct": mean_or_none(fuller_deltas),
        "fullerSameErrorMinCompositeDeltaPct": min_or_none(fuller_deltas),
        "fullerSameErrorMaxCompositeDeltaPct": max_or_none(fuller_deltas),
        "borderlineConflictFullerCount": len(borderline_conflict_fuller_entries),
        "borderlineConflictFullerMeanCompositeDeltaPct": mean_or_none(borderline_conflict_fuller_deltas),
        "borderlineConflictFullerMinCompositeDeltaPct": min_or_none(borderline_conflict_fuller_deltas),
        "borderlineConflictFullerMaxCompositeDeltaPct": max_or_none(borderline_conflict_fuller_deltas),
        "preciseSubsetChallengerCount": len(precise_subset_entries),
        "preciseSubsetPositiveCount": sum(1 for delta in precise_subset_deltas if float(delta) > 0),
        "preciseSubsetNegativeCount": sum(1 for delta in precise_subset_deltas if float(delta) < 0),
        "preciseSubsetMeanCompositeDeltaPct": mean_or_none(precise_subset_deltas),
        "preciseSubsetMinCompositeDeltaPct": min_or_none(precise_subset_deltas),
        "preciseSubsetMaxCompositeDeltaPct": max_or_none(precise_subset_deltas),
        "highPrecisionCompactChallengerCount": len(high_precision_compact_entries),
        "highPrecisionCompactPositiveCount": sum(1 for delta in high_precision_compact_deltas if float(delta) > 0),
        "highPrecisionCompactNegativeCount": sum(1 for delta in high_precision_compact_deltas if float(delta) < 0),
        "highPrecisionCompactMeanCompositeDeltaPct": mean_or_none(high_precision_compact_deltas),
        "highPrecisionCompactMinCompositeDeltaPct": min_or_none(high_precision_compact_deltas),
        "highPrecisionCompactMaxCompositeDeltaPct": max_or_none(high_precision_compact_deltas),
        "ambiguousCases": [
            {
                "sourceId": result["sourceId"],
                "selectedVariantId": result["dotVariantId"],
                "riskFlags": result["noLabelRiskDiagnostics"].get("riskFlags", []),
                "acceptedVariantCount": result["noLabelRiskDiagnostics"].get("acceptedVariantCount"),
                "nearestChallengerId": (result["noLabelRiskDiagnostics"].get("nearestScoreChallengers") or [{}])[0].get("dotVariantId"),
                "nearestChallengerScoreGap": (result["noLabelRiskDiagnostics"].get("nearestScoreChallengers") or [{}])[0].get("scoreGapToSelected"),
                "nearestChallengerAgreementPct": ((result["noLabelRiskDiagnostics"].get("nearestScoreChallengers") or [{}])[0].get("latticeAgreementWithSelected") or {}).get("within0_15Pct"),
                "fullerChallengerId": (result["noLabelRiskDiagnostics"].get("fullerSameErrorChallenger") or {}).get("dotVariantId"),
                "fullerChallengerCompositeDeltaPct": (result["noLabelRiskDiagnostics"].get("fullerSameErrorChallenger") or {}).get("benchmarkCompositeDeltaPct"),
                "borderlineConflictFullerChallengerId": (result["noLabelRiskDiagnostics"].get("borderlineConflictFullerChallenger") or {}).get("dotVariantId"),
                "borderlineConflictFullerCompositeDeltaPct": (result["noLabelRiskDiagnostics"].get("borderlineConflictFullerChallenger") or {}).get("benchmarkCompositeDeltaPct"),
                "preciseSubsetChallengerId": (result["noLabelRiskDiagnostics"].get("preciseSubsetChallenger") or {}).get("dotVariantId"),
                "preciseSubsetCompositeDeltaPct": (result["noLabelRiskDiagnostics"].get("preciseSubsetChallenger") or {}).get("benchmarkCompositeDeltaPct"),
                "highPrecisionCompactChallengerId": (result["noLabelRiskDiagnostics"].get("highPrecisionCompactChallenger") or {}).get("dotVariantId"),
                "highPrecisionCompactCompositeDeltaPct": (result["noLabelRiskDiagnostics"].get("highPrecisionCompactChallenger") or {}).get("benchmarkCompositeDeltaPct"),
            }
            for result in ambiguous
        ],
        "recommendation": "report-only; current no-label ambiguity proxies show selector headroom but also false positives",
    }


def summarize_selection_diagnostic_entries(entries: list[dict[str, Any]]) -> dict[str, Any]:
    if not entries:
        return {"total": 0}
    line_values = [
        entry.get("candidate", {}).get("truthLineSamplesWithin0_15SquaresPct")
        for entry in entries
        if entry.get("candidate", {}).get("truthLineSamplesWithin0_15SquaresPct") is not None
    ]
    mesh_values = [
        entry.get("candidate", {}).get("truthMeshSamplesWithin0_15SquaresPct")
        for entry in entries
        if entry.get("candidate", {}).get("truthMeshSamplesWithin0_15SquaresPct") is not None
    ]
    line_deltas = [
        entry.get("truthDelta", {}).get("truthLineSamplesWithin0_15SquaresPct")
        for entry in entries
        if entry.get("truthDelta", {}).get("truthLineSamplesWithin0_15SquaresPct") is not None
    ]
    mesh_deltas = [
        entry.get("truthDelta", {}).get("truthMeshSamplesWithin0_15SquaresPct")
        for entry in entries
        if entry.get("truthDelta", {}).get("truthMeshSamplesWithin0_15SquaresPct") is not None
    ]
    return {
        "total": len(entries),
        "differsFromAuto": sum(1 for entry in entries if entry.get("differs")),
        "meanTruthLineSamplesWithin0_15SquaresPct": mean_or_none(line_values),
        "minTruthLineSamplesWithin0_15SquaresPct": min_or_none(line_values),
        "meanTruthMeshSamplesWithin0_15SquaresPct": mean_or_none(mesh_values),
        "minTruthMeshSamplesWithin0_15SquaresPct": min_or_none(mesh_values),
        "meanTruthLineDeltaPct": mean_or_none(line_deltas),
        "meanTruthMeshDeltaPct": mean_or_none(mesh_deltas),
    }


def write_contact_sheet(results: list[dict[str, Any]], out_dir: Path) -> None:
    write_result_contact_sheet(results, out_dir / "contact-sheet.jpg", use_manual_seed=False)
    write_result_contact_sheet(results, out_dir / "manual-seed-contact-sheet.jpg", use_manual_seed=True)


def write_result_contact_sheet(results: list[dict[str, Any]], path: Path, use_manual_seed: bool) -> None:
    if not results:
        return
    thumbs = []
    for result in results:
        item = result.get("manualSeedVariant", result) if use_manual_seed else result
        image = Image.open(item["overlayImage"]).convert("RGB")
        image.thumbnail((260, 345), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (280, 405), (235, 235, 235))
        canvas.paste(image, ((280 - image.width) // 2, 10))
        draw = ImageDraw.Draw(canvas)
        draw.text((10, 355), result["sourceId"].replace("real-map-home-", "").replace(".jpg", ""), fill=(0, 0, 0))
        draw.text((10, 372), item["decision"], fill=(0, 0, 0))
        draw.text((10, 389), f"{item['dotVariantId']} inliers {item.get('homographyInliers', result['fit'].get('homographyInliers', 0))} span {item.get('spanI', result['fit'].get('spanI', 0))}x{item.get('spanJ', result['fit'].get('spanJ', 0))}", fill=(0, 0, 0))
        thumbs.append(canvas)
    columns = 4
    rows = math.ceil(len(thumbs) / columns)
    sheet = Image.new("RGB", (columns * 280, rows * 405), (220, 220, 220))
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((index % columns) * 280, (index // columns) * 405))
    sheet.save(path, quality=92)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AI Dot Lattice Fit",
        "",
        f"- Selection mode: {report.get('selectionMode', 'single dot sample')}",
        f"- Total: `{report['summary']['total']}`",
        f"- Dot variants evaluated: `{report['summary'].get('totalDotVariantsEvaluated', report['summary']['total'])}`",
        f"- Decisions: `{json.dumps(report['summary']['decisions'], sort_keys=True)}`",
        f"- Manual seed differs from auto selection: `{report['summary'].get('manualSeedDiffers', 0)}`",
        f"- Summary only: `{report.get('summaryOnly', False)}`",
        "",
        "## Retry Policies",
        "",
        "| Policy | Mean launched dots | Total launched dots | Mean completed dots | Est. parallel wall avg | Est. parallel wall max | Decisions | No-label auto full-span | No-label readiness |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | --- |",
    ]
    for name, policy in sorted(report["summary"].get("retryPolicies", {}).items()):
        lines.append(
            f"| `{name}` | {policy['meanDotSamples']} | {policy['totalDotSamples']} | {policy.get('meanCompletedDotSamples') or ''} | "
            f"{format_ms(policy.get('meanEstimatedParallelWallMs'))} | {format_ms(policy.get('maxEstimatedParallelWallMs'))} | "
            f"`{json.dumps(policy['decisions'], sort_keys=True)}` | {policy.get('noLabelFullSpanAutoProject')}/{policy.get('total')} | "
            f"`{json.dumps(policy.get('noLabelProjectionReadiness', {}), sort_keys=True)}` |"
        )
    diagnostics = report["summary"].get("selectionDiagnostics", {})
    diagnostic_rows = [
        ("accepted_mesh_density", diagnostics.get("acceptedMeshDensity", {})),
        ("guarded_mesh_density", diagnostics.get("guardedMeshDensity", {})),
    ]
    if any(summary.get("total") for _, summary in diagnostic_rows):
        lines.extend([
            "",
            "## Selection Diagnostics",
            "",
            "These diagnostics compare report-only alternate picks. They do not change auto selection or acceptance.",
            "",
            "| Diagnostic | Differs | Mean line <=.15 | Min line <=.15 | Mean mesh <=.15 | Min mesh <=.15 | Mean line delta | Mean mesh delta |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ])
        for name, summary in diagnostic_rows:
            if not summary.get("total"):
                continue
            lines.append(
                f"| `{name}` | {summary.get('differsFromAuto')}/{summary.get('total')} | "
                f"{summary.get('meanTruthLineSamplesWithin0_15SquaresPct')} | "
                f"{summary.get('minTruthLineSamplesWithin0_15SquaresPct')} | "
                f"{summary.get('meanTruthMeshSamplesWithin0_15SquaresPct')} | "
                f"{summary.get('minTruthMeshSamplesWithin0_15SquaresPct')} | "
                f"{summary.get('meanTruthLineDeltaPct')} | {summary.get('meanTruthMeshDeltaPct')} |"
            )
    risk = report["summary"].get("noLabelRiskDiagnostics", {})
    if risk.get("total"):
        lines.extend([
            "",
            "## No-Label Risk Diagnostics",
            "",
            "These report-only diagnostics look for accepted-variant ambiguity: cases where no single metric proves the selector is wrong, but plausible accepted variants disagree or trade coverage, support, and density. Benchmark deltas are shown only to evaluate the proxy.",
            "",
            f"- Selection-ambiguous cases: `{risk.get('selectionAmbiguousCount')}/{risk.get('total')}`",
            f"- Fuller same-error challengers: `{risk.get('fullerSameErrorChallengerCount')}/{risk.get('total')}`",
            f"- Fuller challenger benchmark deltas: positive `{risk.get('fullerSameErrorPositiveCount')}`, negative `{risk.get('fullerSameErrorNegativeCount')}`, mean `{risk.get('fullerSameErrorMeanCompositeDeltaPct')}` points, min `{risk.get('fullerSameErrorMinCompositeDeltaPct')}`, max `{risk.get('fullerSameErrorMaxCompositeDeltaPct')}`",
            f"- Borderline-conflict fuller challengers: `{risk.get('borderlineConflictFullerCount')}/{risk.get('total')}`, mean delta `{risk.get('borderlineConflictFullerMeanCompositeDeltaPct')}`, min `{risk.get('borderlineConflictFullerMinCompositeDeltaPct')}`, max `{risk.get('borderlineConflictFullerMaxCompositeDeltaPct')}`",
            f"- Precise subset challengers: `{risk.get('preciseSubsetChallengerCount')}/{risk.get('total')}`, positive `{risk.get('preciseSubsetPositiveCount')}`, negative `{risk.get('preciseSubsetNegativeCount')}`, mean delta `{risk.get('preciseSubsetMeanCompositeDeltaPct')}`, min `{risk.get('preciseSubsetMinCompositeDeltaPct')}`, max `{risk.get('preciseSubsetMaxCompositeDeltaPct')}`",
            f"- High-precision compact challengers: `{risk.get('highPrecisionCompactChallengerCount')}/{risk.get('total')}`, positive `{risk.get('highPrecisionCompactPositiveCount')}`, negative `{risk.get('highPrecisionCompactNegativeCount')}`, mean delta `{risk.get('highPrecisionCompactMeanCompositeDeltaPct')}`, min `{risk.get('highPrecisionCompactMinCompositeDeltaPct')}`, max `{risk.get('highPrecisionCompactMaxCompositeDeltaPct')}`",
            f"- Risk flag counts: `{json.dumps(risk.get('flagCounts', {}), sort_keys=True)}`",
        ])
        if risk.get("ambiguousCases"):
            lines.extend([
                "",
                "| Source | Selected | Accepted variants | Nearest challenger | Score gap | Lattice agreement <=.15 | Fuller challenger | Fuller delta | Conflict-fuller | Conflict-fuller delta | Precise subset | Precise delta | Compact precision | Compact delta | Flags |",
                "| --- | --- | ---: | --- | ---: | ---: | --- | ---: | --- | ---: | --- | ---: | --- | ---: | --- |",
            ])
            for item in risk["ambiguousCases"]:
                lines.append(
                    f"| `{item['sourceId']}` | `{item['selectedVariantId']}` | {item['acceptedVariantCount']} | "
                    f"`{item.get('nearestChallengerId')}` | {item.get('nearestChallengerScoreGap')} | "
                    f"{item.get('nearestChallengerAgreementPct')} | `{item.get('fullerChallengerId')}` | "
                    f"{item.get('fullerChallengerCompositeDeltaPct')} | `{item.get('borderlineConflictFullerChallengerId')}` | "
                    f"{item.get('borderlineConflictFullerCompositeDeltaPct')} | `{item.get('preciseSubsetChallengerId')}` | "
                    f"{item.get('preciseSubsetCompositeDeltaPct')} | `{item.get('highPrecisionCompactChallengerId')}` | "
                    f"{item.get('highPrecisionCompactCompositeDeltaPct')} | {'; '.join(item.get('riskFlags', []))} |"
                )
    oracle = report["summary"].get("benchmarkOracleDiagnostics", {})
    if oracle.get("total"):
        lines.extend([
            "",
            "## Benchmark Oracle Diagnostics",
            "",
            "These diagnostics use labels only after selection to identify accuracy headroom in the current artifact set. They must not feed runtime selection.",
            "",
            f"- Best composite differs: `{oracle.get('bestCompositeDiffers')}/{oracle.get('total')}`",
            f"- Material composite misses: `{oracle.get('materialBestCompositeMisses')}/{oracle.get('total')}`",
            f"- Mean composite delta: `{oracle.get('meanCompositeDeltaPct')}` percentage points",
            f"- Max composite delta: `{oracle.get('maxCompositeDeltaPct')}` percentage points",
        ])
        if oracle.get("materialMisses"):
            lines.extend([
                "",
                "| Source | Selected | Oracle | Selected line <=.15 | Oracle line <=.15 | Selected mesh <=.15 | Oracle mesh <=.15 | Composite delta | Oracle decision | Oracle span |",
                "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
            ])
            for item in oracle["materialMisses"]:
                lines.append(
                    f"| `{item['sourceId']}` | `{item['selectedVariantId']}` | `{item['oracleVariantId']}` | "
                    f"{item['selectedLinePct']} | {item['oracleLinePct']} | "
                    f"{item['selectedMeshPct']} | {item['oracleMeshPct']} | "
                    f"{item['compositeDeltaPct']} | `{item['oracleDecision']}` | `{item['oracleSpan']}` |"
                )
    projection_models = report["summary"].get("projectionModelComparison", {})
    if projection_models.get("total"):
        lines.extend([
            "",
            "## Projection Model Comparison",
            "",
            "This compares the selected single homography against the selected observed inlier mesh. The same-edge row is the fair local comparison: both models are scored on the observed mesh edges. This is benchmark evidence for a future mesh-warp projection path, not proof of full-map extrapolation.",
            "",
            "| Model | Mean line <=.15 | Min line <=.15 | Supported visible meshes | Mean mesh cells | Mean mesh density |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
            f"| `full-span-homography` | {projection_models.get('fullSpanHomographyMeanLineWithin0_15Pct')} | {projection_models.get('fullSpanHomographyMinLineWithin0_15Pct')} |  |  |  |",
            f"| `observed-edge-homography` | {projection_models.get('observedEdgeHomographyMeanLineWithin0_15Pct')} | {projection_models.get('observedEdgeHomographyMinLineWithin0_15Pct')} |  |  |  |",
            f"| `visible-inlier-mesh` | {projection_models.get('visibleMeshMeanLineWithin0_15Pct')} | {projection_models.get('visibleMeshMinLineWithin0_15Pct')} | "
            f"{projection_models.get('visibleMeshCoverageSupported')}/{projection_models.get('total')} | "
            f"{projection_models.get('meanVisibleMeshCells')} | {projection_models.get('meanVisibleMeshCellDensity')} |",
            "",
            f"- Mean visible-mesh gain vs full-span homography: `{projection_models.get('meanVisibleMeshGainVsFullSpanHomographyPct')}` percentage points",
            f"- Mean visible-mesh gain vs observed-edge homography: `{projection_models.get('meanVisibleMeshGainVsObservedEdgeHomographyPct')}` percentage points",
            f"- Max visible-mesh gain vs observed-edge homography: `{projection_models.get('maxVisibleMeshGainVsObservedEdgeHomographyPct')}` percentage points",
            f"- Mean observed-edge homography gain vs full-span homography: `{projection_models.get('meanObservedEdgeHomographyGainVsFullSpanPct')}` percentage points",
            f"- Max observed-edge homography gain vs full-span homography: `{projection_models.get('maxObservedEdgeHomographyGainVsFullSpanPct')}` percentage points",
            f"- Material same-edge gain with supported coverage: `{projection_models.get('materialGainCount')}/{projection_models.get('total')}`",
            f"- Duplicate inlier coordinates collapsed in observed mesh: `{projection_models.get('totalDuplicateCoordinates')}`",
            f"- Full-span projection confidence: `{json.dumps(projection_models.get('fullSpanProjectionConfidenceCounts', {}), sort_keys=True)}`",
            f"- Projection readiness: `{json.dumps(projection_models.get('projectionReadinessCounts', {}), sort_keys=True)}`",
            f"- No-label projection readiness: `{json.dumps(projection_models.get('noLabelProjectionReadinessCounts', {}), sort_keys=True)}`",
            f"- Full-span auto-project candidates: `{projection_models.get('fullSpanAutoProjectCount')}/{projection_models.get('total')}`",
            f"- No-label full-span auto-project candidates: `{projection_models.get('noLabelFullSpanAutoProjectCount')}/{projection_models.get('total')}`",
            f"- Manual projection confirmation required: `{projection_models.get('manualProjectionConfirmationCount')}/{projection_models.get('total')}`",
            f"- No-label manual projection confirmation required: `{projection_models.get('noLabelManualProjectionConfirmationCount')}/{projection_models.get('total')}`",
            f"- No-label auto but benchmark not auto: `{projection_models.get('noLabelAutoButBenchmarkNotAutoCount')}/{projection_models.get('total')}`",
            f"- Benchmark auto but no-label not auto: `{projection_models.get('benchmarkAutoButNoLabelAutoCount')}/{projection_models.get('total')}`",
            f"- Wrong-confident risk if accepted geometry were projected full-span: `{projection_models.get('wrongConfidentIfAcceptedMeansFullSpanCount')}/{projection_models.get('total')}`",
            f"- Observed-edge-only cases: `{projection_models.get('observedEdgeOnlyCount')}/{projection_models.get('total')}`",
        ])
        if projection_models.get("observedEdgeOnlyCases"):
            lines.extend([
                "",
                "| Source | Variant | Full-span <=.15 | Observed-edge <=.15 | Gap | Mesh density | Unsupported cells | Readiness | Recommendation |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
            ])
            for item in projection_models["observedEdgeOnlyCases"]:
                lines.append(
                    f"| `{item['sourceId']}` | `{item['dotVariantId']}` | "
                    f"{item['fullSpanHomographyLineWithin0_15Pct']} | {item['observedEdgeHomographyLineWithin0_15Pct']} | "
                    f"{item['observedEdgeVsFullSpanGapPct']} | {item['visibleMeshCellDensity']} | "
                    f"{item['unsupportedCellCount']}/{item['spanCellCount']} | `{item['readinessMode']}` | `{item['recommendation']}` |"
                )
        if projection_models.get("benchmarkAutoButNoLabelAutoCases"):
            lines.extend([
                "",
                "| Source | Variant | Benchmark readiness | No-label readiness | Full-span <=.15 | Observed-edge <=.15 | No-label reasons |",
                "| --- | --- | --- | --- | ---: | ---: | --- |",
            ])
            for item in projection_models["benchmarkAutoButNoLabelAutoCases"]:
                lines.append(
                    f"| `{item['sourceId']}` | `{item['dotVariantId']}` | `{item['benchmarkReadinessMode']}` | "
                    f"`{item['noLabelReadinessMode']}` | {item['fullSpanHomographyLineWithin0_15Pct']} | "
                    f"{item['observedEdgeHomographyLineWithin0_15Pct']} | {'; '.join(item.get('noLabelReasons') or [])} |"
                )
        if projection_models.get("noLabelAutoButBenchmarkNotAutoCases"):
            lines.extend([
                "",
                "| Source | Variant | Benchmark readiness | No-label readiness | Full-span <=.15 | Observed-edge <=.15 | No-label reasons |",
                "| --- | --- | --- | --- | ---: | ---: | --- |",
            ])
            for item in projection_models["noLabelAutoButBenchmarkNotAutoCases"]:
                lines.append(
                    f"| `{item['sourceId']}` | `{item['dotVariantId']}` | `{item['benchmarkReadinessMode']}` | "
                    f"`{item['noLabelReadinessMode']}` | {item['fullSpanHomographyLineWithin0_15Pct']} | "
                    f"{item['observedEdgeHomographyLineWithin0_15Pct']} | {'; '.join(item.get('noLabelReasons') or [])} |"
                )
    sensitivity = report["summary"].get("noLabelProjectionReadinessSensitivity", {})
    if sensitivity.get("total"):
        lines.extend([
            "",
            "## No-Label Readiness Sensitivity",
            "",
            "This benchmark-only sweep tests whether relaxed no-label full-span gates would have promoted existing generated variants without label-scored regressions. It does not change runtime selection.",
            "",
            "| Gate | Candidates | Promoted beyond current | Dangerous disagreements | Mean line <=.15 | Min line <=.15 | Mean observed-edge <=.15 | Min observed-edge <=.15 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ])
        for gate in sensitivity.get("gates", []):
            lines.append(
                f"| `{gate['gate']}` | {gate['candidateCount']}/{sensitivity.get('total')} | "
                f"{gate['promotedBeyondCurrentCount']} | {gate['dangerousBenchmarkDisagreementCount']} | "
                f"{gate['meanTruthLinePct']} | {gate['minTruthLinePct']} | "
                f"{gate['meanObservedEdgePct']} | {gate['minObservedEdgePct']} |"
            )
        promoted_cases = [
            (gate["gate"], case)
            for gate in sensitivity.get("gates", [])
            for case in gate.get("promotedBeyondCurrentCases", [])
        ]
        if promoted_cases:
            lines.extend([
                "",
                "| Gate | Source | Candidate | Current selected | Candidate line <=.15 | Candidate observed-edge <=.15 | Candidate mesh <=.15 | Candidate span | Key metrics |",
                "| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |",
            ])
            for gate_name, item in promoted_cases:
                metrics = item.get("candidateMetrics", {})
                metric_text = (
                    f"ratio={metrics.get('homographyInlierRatio')}, p90={metrics.get('p90ReprojectionErrorCells')}, "
                    f"p25={metrics.get('p25LineSupport')}, conflict={metrics.get('coordinateConflictPct')}, "
                    f"density={metrics.get('observedMeshCellDensity')}"
                )
                lines.append(
                    f"| `{gate_name}` | `{item['sourceId']}` | `{item['candidateVariantId']}` | `{item['currentSelectedVariantId']}` | "
                    f"{item['candidateTruthLinePct']} | {item['candidateObservedEdgePct']} | {item['candidateMeshPct']} | "
                    f"`{item['candidateSpan']}` | {metric_text} |"
                )
    mesh_projection = report["summary"].get("meshProjectionDiagnostics", {})
    if mesh_projection.get("total"):
        lines.extend([
            "",
            "## Mesh Projection Diagnostics",
            "",
            "These diagnostics identify selected fits where an observed inlier mesh tracks the labeled grid materially better than homography on the same observed edges. They do not change acceptance.",
            "",
            f"- Candidates: `{mesh_projection.get('candidateCount')}/{mesh_projection.get('total')}`",
            f"- Mean mesh gain vs full-span homography: `{mesh_projection.get('meanGainPct')}` percentage points",
            f"- Max mesh gain vs full-span homography: `{mesh_projection.get('maxGainPct')}` percentage points",
            f"- Mean mesh gain vs observed-edge homography: `{mesh_projection.get('meanSameEdgeGainPct')}` percentage points",
            f"- Max mesh gain vs observed-edge homography: `{mesh_projection.get('maxSameEdgeGainPct')}` percentage points",
            f"- Candidate criteria: {mesh_projection.get('candidateCriteria')}",
        ])
        if mesh_projection.get("candidates"):
            lines.extend([
                "",
                "| Source | Variant | Full-span homography <=.15 | Observed-edge homography <=.15 | Mesh <=.15 | Same-edge gain | Mesh cells | Mesh density | Span |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
            ])
            for candidate in mesh_projection["candidates"]:
                lines.append(
                    f"| `{candidate['sourceId']}` | `{candidate['dotVariantId']}` | "
                    f"{candidate['homographyLineWithin0_15Pct']} | {candidate['observedEdgeHomographyLineWithin0_15Pct']} | "
                    f"{candidate['meshLineWithin0_15Pct']} | {candidate['sameEdgeGainPct']} | "
                    f"{candidate['meshCells']} | {candidate['meshCellDensity']} | `{candidate['span']}` |"
                )
    lines.extend([
        "",
        "## Selected Fits",
        "",
        "| Source | Auto | Manual seed | Seed mode | Variants | Decision | Readiness | No-label readiness | Auto full-span | No-label auto full-span | Auto score | Manual score | Inliers | Span | Manual span | Mesh vertices | Mesh cells | Homography line <=.15 | Observed-edge <=.15 | Mesh line <=.15 | Mesh gain | Reasons | Overlay |",
        "| --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- | ---: | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ])
    for result in report["results"]:
        fit = result["fit"]
        bench = result["benchmark"]
        manual = result.get("manualSeedVariant", {})
        seed = result.get("manualSeedRecommendation", {})
        mesh = result.get("observedMesh", {})
        projection = result.get("projectionModelComparison", {})
        readiness = projection.get("projectionReadiness", {})
        no_label_readiness = projection.get("noLabelProjectionReadiness", {})
        lines.append(
            f"| `{result['sourceId']}` | `{result['dotVariantId']}` | `{manual.get('dotVariantId')}` | `{seed.get('mode')}` | {result.get('dotVariantCount', 1)} | `{result['decision']}` | "
            f"`{readiness.get('mode')}` | `{no_label_readiness.get('mode')}` | `{readiness.get('fullSpanAutoProject')}` | `{no_label_readiness.get('fullSpanAutoProject')}` | "
            f"{result['selectionScore']} | {manual.get('manualSeedScore')} | {fit.get('homographyInliers')} | "
            f"{fit.get('spanI')}x{fit.get('spanJ')} | {manual.get('spanI')}x{manual.get('spanJ')} | "
            f"{mesh.get('vertexCount')} | {mesh.get('cellCount')} | "
            f"{bench.get('truthLineSamplesWithin0_15SquaresPct')} | {projection.get('observedEdgeHomographyLineWithin0_15Pct')} | "
            f"{bench.get('truthMeshSamplesWithin0_15SquaresPct')} | {bench.get('truthMeshVsHomographyGainPct')} | "
            f"{'; '.join(result['reasons'])} | `{result['overlayImage']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def render_console(report: dict[str, Any]) -> str:
    lines = [f"AI dot lattice fit: {report['summary']['decisions']}"]
    for result in report["results"]:
        fit = result["fit"]
        bench = result["benchmark"]
        manual = result.get("manualSeedVariant", {})
        seed = result.get("manualSeedRecommendation", {})
        readiness = result.get("projectionModelComparison", {}).get("projectionReadiness", {})
        no_label_readiness = result.get("projectionModelComparison", {}).get("noLabelProjectionReadiness", {})
        lines.append(
            f"- {result['sourceId']}: {result['decision']} selected={result.get('dotVariantId')} score={result.get('selectionScore')} "
            f"manualSeed={manual.get('dotVariantId')} seedMode={seed.get('mode')} manualScore={manual.get('manualSeedScore')} variants={result.get('dotVariantCount', 1)} lineDots={fit.get('lineAgreementDots')} "
            f"assigned={fit.get('assignedDots')} inliers={fit.get('homographyInliers')} span={fit.get('spanI')}x{fit.get('spanJ')} "
            f"readiness={readiness.get('mode')} autoFullSpan={readiness.get('fullSpanAutoProject')} "
            f"noLabelReadiness={no_label_readiness.get('mode')} noLabelAutoFullSpan={no_label_readiness.get('fullSpanAutoProject')} "
            f"truthDotP90={bench.get('truthP90DotErrorSquares')} truthLine<=.15={bench.get('truthLineSamplesWithin0_15SquaresPct')} "
            f"truthMesh<=.15={bench.get('truthMeshSamplesWithin0_15SquaresPct')}"
        )
    lines.append(f"Artifacts: {Path(report['outDir']) / 'report.md'}")
    return "\n".join(lines)


def weighted_circular_mean(angles: list[float], weights: list[float]) -> float:
    if not angles:
        return 0.0
    radians = np.deg2rad(np.array(angles) * 2)
    weights_array = np.array(weights)
    x = float(np.sum(np.cos(radians) * weights_array))
    y = float(np.sum(np.sin(radians) * weights_array))
    return (math.degrees(math.atan2(y, x)) / 2 + 180) % 180


def angle_distance(left: float, right: float) -> float:
    delta = abs(left - right) % 180
    return min(delta, 180 - delta)


def slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-")


def round_metric(value: float) -> float:
    return round(float(value), 3)


def mean_or_none(values: list[float]) -> float | None:
    return None if not values else round_metric(sum(float(value) for value in values) / len(values))


def min_or_none(values: list[float]) -> float | None:
    return None if not values else round_metric(min(float(value) for value in values))


def max_or_none(values: list[float]) -> float | None:
    return None if not values else round_metric(max(float(value) for value in values))


def format_ms(value: float | None) -> str:
    if value is None:
        return ""
    return f"{round_metric(float(value) / 1000)}s"


if __name__ == "__main__":
    main()
