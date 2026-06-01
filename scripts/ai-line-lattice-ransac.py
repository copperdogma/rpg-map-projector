#!/usr/bin/env python3
"""Fit visible lattice geometry from AI-generated line masks only.

This is a discovery/eval script. It uses Hough segment clusters from a single
AI white-line mask, proposes ordered line-family subsets, fits homographies from
their intersections, and scores with the same benchmark helpers as the dot
lattice fitter. Labels are not used for fitting or selecting candidates.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[1]
AI_GRID_PATH = ROOT / "scripts" / "ai-grid-experiment.py"
AI_ARBITER_PATH = ROOT / "scripts" / "ai-evidence-arbiter.py"
AI_DOT_FIT_PATH = ROOT / "scripts" / "ai-dot-lattice-fit.py"
AI_MASK_PROBE_PATH = ROOT / "scripts" / "ai-mask-lattice-probe.py"
LABELS_PATH = ROOT / "input" / "map-grid-labels.json"
DEFAULT_OUT_DIR = ROOT / "test-results" / "ai-line-lattice-ransac-v1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--line-reports-glob", default="test-results/ai-grid-experiments-grok-white-v1/*/report.json")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    ai_grid = load_module("ai_grid_experiment", AI_GRID_PATH)
    ai_arbiter = load_module("ai_evidence_arbiter", AI_ARBITER_PATH)
    dot_fit = load_module("ai_dot_lattice_fit", AI_DOT_FIT_PATH)
    mask_probe = load_module("ai_mask_lattice_probe", AI_MASK_PROBE_PATH)
    labels = {label["sourceId"]: label for label in json.loads(LABELS_PATH.read_text())["labels"]}

    out_dir = Path(args.out_dir)
    overlays_dir = out_dir / "overlays"
    overlays_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for report_path in sorted(ROOT.glob(args.line_reports_glob)):
        report = json.loads(report_path.read_text())
        source_id = report["sourceId"]
        label = labels.get(source_id)
        if not label:
            continue
        experiment = first_image_result(report)
        image_path = resolve_output_path(experiment["outputImage"])
        rgb = load_rgb(image_path)
        line_mask = ai_arbiter.extract_line_mask(ai_grid, rgb, experiment)
        result = analyze_source(ai_grid, dot_fit, mask_probe, source_id, label, line_mask, overlays_dir)
        results.append(result)

    output = {
        "outDir": str(out_dir),
        "selectionMode": "single AI line mask; ordered Hough line-family subset search selected without labels",
        "summary": summarize(results),
        "results": results,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(f"{json.dumps(output, indent=2)}\n")
    (out_dir / "report.md").write_text(render_markdown(output))
    write_contact_sheet(results, out_dir)
    print(render_console(output))


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def first_image_result(report: dict[str, Any]) -> dict[str, Any]:
    for result in report.get("results", []):
        if result.get("ok") and result.get("outputImage"):
            return result
    raise RuntimeError("No successful line-mask result")


def resolve_output_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.array(ImageOps.exif_transpose(image).convert("RGB"))


def analyze_source(
    ai_grid: Any,
    dot_fit: Any,
    mask_probe: Any,
    source_id: str,
    label: dict[str, Any],
    line_mask: np.ndarray,
    overlays_dir: Path,
) -> dict[str, Any]:
    family_candidates = line_family_candidates(mask_probe, line_mask)
    variants = []
    candidate_summaries = []
    for candidate in family_candidates:
        clusters_by_family = candidate["families"]
        candidate_variants = fit_line_subset_variants(dot_fit, clusters_by_family, line_mask)
        for variant in candidate_variants:
            variant["familyMode"] = candidate["mode"]
        variants.extend(candidate_variants)
        candidate_summaries.append(
            {
                "mode": candidate["mode"],
                "lineFamilyCounts": [len(item) for item in clusters_by_family],
                "variantCount": len(candidate_variants),
            }
        )
    if not variants:
        fit = dot_fit.FitResult(
            "refuse",
            ["could not fit ordered line-family lattice"],
            None,
            {},
            [],
            {"lineFamilyCounts": [summary["lineFamilyCounts"] for summary in candidate_summaries]},
        )
        points = np.empty((0, 2), dtype=np.float32)
        best = {"selectionScore": 0.0, "subset": None, "fit": fit, "points": points, "familyMode": None}
    else:
        best = max(variants, key=lambda item: item["selectionScore"])
        fit = best["fit"]
        points = best["points"]

    benchmark = dot_fit.benchmark_fit(ai_grid, label, fit, points, line_mask)
    overlay_path = write_overlay(dot_fit, ai_grid, label, source_id, points, line_mask, fit, overlays_dir, best.get("subset"))
    return {
        "sourceId": source_id,
        "decision": fit.decision,
        "reasons": fit.reasons,
        "selectionScore": round_metric(best["selectionScore"]),
        "familyMode": best.get("familyMode"),
        "lineFamilyCounts": [fit.metrics.get("lineFamilyACount"), fit.metrics.get("lineFamilyBCount")]
        if fit.metrics.get("lineFamilyACount") is not None
        else [],
        "candidateSummaries": candidate_summaries,
        "subset": best.get("subset"),
        "variantCount": len(variants),
        "overlayImage": str(overlay_path),
        "fit": fit.metrics,
        "benchmark": benchmark,
        "variantSummaries": [variant_summary(item) for item in sorted(variants, key=lambda item: item["selectionScore"], reverse=True)[:12]],
    }


def line_family_candidates(mask_probe: Any, line_mask: np.ndarray) -> list[dict[str, Any]]:
    candidates = []
    hough_families = hough_line_families(mask_probe, line_mask)
    if hough_families:
        candidates.append({"mode": "hough-segment-clusters", "families": hough_families})
    profile_families = profile_line_families(mask_probe, line_mask, hough_families)
    if profile_families:
        candidates.append({"mode": "profile-peaks-from-family-angles", "families": profile_families})
    return candidates


def hough_line_families(mask_probe: Any, line_mask: np.ndarray) -> list[list[Any]]:
    segments = mask_probe.hough_segments(line_mask)
    families = mask_probe.choose_families(segments)
    if len(families) < 2:
        return []
    separation = mask_probe.angle_distance(float(families[0]["angle"]), float(families[1]["angle"]))
    if separation < 60 or separation > 120:
        return []
    clusters_by_family = []
    for family in families[:2]:
        selected = mask_probe.select_segments_for_family(segments, family["angle"])
        clusters = mask_probe.cluster_family_lines(selected, line_mask.shape[1], line_mask.shape[0])
        clusters = mask_probe.prune_regular_sequence(clusters)
        clusters_by_family.append(clusters)
    return clusters_by_family


def profile_line_families(mask_probe: Any, line_mask: np.ndarray, seed_families: list[list[Any]]) -> list[list[Any]]:
    angles = family_angles_from_clusters(seed_families)
    if len(angles) < 2:
        angles = standard_hough_family_angles(mask_probe, line_mask)
    if len(angles) < 2:
        return []
    separation = mask_probe.angle_distance(float(angles[0]), float(angles[1]))
    if separation < 60 or separation > 120:
        return []
    clusters_by_family = [profile_clusters_for_angle(mask_probe, line_mask, angle) for angle in angles[:2]]
    if min(len(item) for item in clusters_by_family) < 6:
        return []
    return clusters_by_family


def family_angles_from_clusters(seed_families: list[list[Any]]) -> list[float]:
    angles = []
    for family in seed_families[:2]:
        if not family:
            continue
        angles.append(weighted_circular_mean([float(cluster.angle) for cluster in family], [float(cluster.support) for cluster in family]))
    return angles


def standard_hough_family_angles(mask_probe: Any, line_mask: np.ndarray) -> list[float]:
    binary = threshold_line_mask(line_mask)
    height, width = binary.shape[:2]
    threshold = max(70, int(min(width, height) * 0.08))
    raw = cv2.HoughLines(binary, 1, np.pi / 720, threshold=threshold)
    if raw is None:
        return []
    segments = []
    for rho_theta in raw[:600, 0, :]:
        rho = float(rho_theta[0])
        theta = float(rho_theta[1])
        angle = (math.degrees(theta) - 90.0 + 180.0) % 180.0
        line = np.array([math.cos(theta), math.sin(theta), -rho], dtype=float)
        points = endpoints_for_line(line, width, height)
        if points is None:
            continue
        x1, y1 = points[0]
        x2, y2 = points[1]
        length = float(math.hypot(x2 - x1, y2 - y1))
        segments.append(mask_probe.SegmentLine(angle, length, line, np.array([x1, y1, x2, y2], dtype=float)))
    families = mask_probe.choose_families(segments)
    return [float(family["angle"]) for family in families[:2]]


def profile_clusters_for_angle(mask_probe: Any, line_mask: np.ndarray, angle: float) -> list[Any]:
    binary = threshold_line_mask(line_mask)
    height, width = binary.shape[:2]
    ys, xs = np.nonzero(binary)
    if len(xs) < 200:
        return []

    angle_rad = math.radians(angle)
    normal = np.array([-math.sin(angle_rad), math.cos(angle_rad)], dtype=float)
    center = np.array([width / 2.0, height / 2.0], dtype=float)
    offsets = (xs.astype(float) - center[0]) * normal[0] + (ys.astype(float) - center[1]) * normal[1]
    weights = np.maximum(1.0, line_mask[ys, xs].astype(float) / 255.0)
    start = math.floor(float(offsets.min())) - 2
    stop = math.ceil(float(offsets.max())) + 3
    if stop <= start:
        return []
    bins = np.arange(start, stop + 1, 1.0)
    hist, edges = np.histogram(offsets, bins=bins, weights=weights)
    if len(hist) < 5 or float(hist.max()) <= 0.0:
        return []
    smooth = np.convolve(hist, np.ones(7, dtype=float) / 7.0, mode="same")
    peak_floor = max(float(np.percentile(smooth, 76)) * 1.12, float(smooth.max()) * 0.13, 3.0)
    peaks = []
    for index in range(1, len(smooth) - 1):
        if smooth[index] >= peak_floor and smooth[index] >= smooth[index - 1] and smooth[index] >= smooth[index + 1]:
            offset = float((edges[index] + edges[index + 1]) / 2.0)
            peaks.append((float(smooth[index]), offset))
    if not peaks:
        return []

    selected: list[tuple[float, float]] = []
    for support, offset in sorted(peaks, reverse=True):
        if all(abs(offset - kept_offset) >= 8.0 for _kept_support, kept_offset in selected):
            selected.append((support, offset))
    selected = sorted(selected[:80], key=lambda item: item[1])

    clusters = []
    for support, offset in selected:
        line = np.array([normal[0], normal[1], -(float(np.dot(normal, center)) + offset)], dtype=float)
        clusters.append(mask_probe.LineCluster(offset=offset, support=support, line=line, angle=angle))
    return mask_probe.prune_regular_sequence(clusters)


def threshold_line_mask(line_mask: np.ndarray) -> np.ndarray:
    if line_mask.dtype != np.uint8:
        line_mask = np.clip(line_mask, 0, 255).astype(np.uint8)
    _threshold, otsu = cv2.threshold(line_mask, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    binary = (otsu > 0).astype(np.uint8) * 255
    if int((binary > 0).sum()) == 0:
        binary = (line_mask >= 32).astype(np.uint8) * 255
    return cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)


def endpoints_for_line(line: np.ndarray, width: int, height: int) -> np.ndarray | None:
    points = sample_line_points(line, width, height, count=2)
    if len(points) < 2:
        return None
    return np.float32(points[:2])


def sample_line_points(line: np.ndarray, width: int, height: int, count: int = 80) -> list[list[float]]:
    a, b, c = [float(value) for value in line]
    points = []
    if abs(b) > abs(a):
        xs = np.linspace(-width * 0.05, width * 1.05, count)
        for x in xs:
            y = -(a * x + c) / b
            if -height * 0.25 <= y <= height * 1.25:
                points.append([float(x), float(y)])
    elif abs(a) > 1e-9:
        ys = np.linspace(-height * 0.05, height * 1.05, count)
        for y in ys:
            x = -(b * y + c) / a
            if -width * 0.25 <= x <= width * 1.25:
                points.append([float(x), float(y)])
    return points


def weighted_circular_mean(angles: list[float], weights: list[float]) -> float:
    radians = np.deg2rad(np.array(angles) * 2.0)
    weights_array = np.array(weights)
    x = float(np.sum(np.cos(radians) * weights_array))
    y = float(np.sum(np.sin(radians) * weights_array))
    return (math.degrees(math.atan2(y, x)) / 2.0 + 180.0) % 180.0


def fit_line_subset_variants(dot_fit: Any, clusters_by_family: list[list[Any]], line_mask: np.ndarray) -> list[dict[str, Any]]:
    if len(clusters_by_family) < 2 or min(len(item) for item in clusters_by_family[:2]) < 6:
        return []
    variants = []
    for stride_a in (1, 2, 3):
        for stride_b in (1, 2, 3):
            for offset_a in range(stride_a):
                for offset_b in range(stride_b):
                    selected_a = clusters_by_family[0][offset_a::stride_a]
                    selected_b = clusters_by_family[1][offset_b::stride_b]
                    if len(selected_a) < 6 or len(selected_b) < 6:
                        continue
                    variant = fit_subset(dot_fit, selected_a, selected_b, line_mask, stride_a, stride_b, offset_a, offset_b)
                    if variant is None:
                        continue
                    variants.append(variant)
                    refined = refine_subset_from_inliers(dot_fit, selected_a, selected_b, line_mask, variant)
                    if refined is not None:
                        variants.append(refined)
    return variants


def fit_subset(
    dot_fit: Any,
    family_a: list[Any],
    family_b: list[Any],
    line_mask: np.ndarray,
    stride_a: int,
    stride_b: int,
    offset_a: int,
    offset_b: int,
) -> dict[str, Any] | None:
    points = []
    coords = []
    line_pairs = []
    height, width = line_mask.shape[:2]
    for i, line_a in enumerate(family_a):
        for j, line_b in enumerate(family_b):
            point = intersect_lines(line_a.line, line_b.line)
            if point is None:
                continue
            if -0.05 * width <= point[0] <= 1.05 * width and -0.05 * height <= point[1] <= 1.05 * height:
                points.append(point)
                coords.append([i, j])
                line_pairs.append((i, j))
    if len(points) < 36:
        return None

    src = np.float32(coords)
    dst = np.float32(points)
    homography, inlier_mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0, maxIters=5000, confidence=0.995)
    if homography is None or inlier_mask is None:
        return None

    coordinates = {index: (int(src[index][0]), int(src[index][1])) for index in range(len(src))}
    inliers = [int(index) for index in np.nonzero(inlier_mask.ravel())[0]]
    median_cell_px = median_line_spacing(family_a, family_b)
    metrics = dot_fit.geometry_metrics(homography, coordinates, dst, inliers, median_cell_px, line_mask)
    metrics.update(
        {
            "lineAgreementDots": int(len(dst)),
            "assignedDots": int(len(dst)),
            "coordinateConflictPct": 0.0,
            "lineAgreementPct": 100.0,
            "lineFamilyACount": int(len(family_a)),
            "lineFamilyBCount": int(len(family_b)),
            "lineSubsetStrideA": int(stride_a),
            "lineSubsetStrideB": int(stride_b),
            "lineSubsetOffsetA": int(offset_a),
            "lineSubsetOffsetB": int(offset_b),
            "medianLineSpacingPx": round_metric(median_cell_px),
        }
    )
    decision, reasons = dot_fit.decide_fit(metrics)
    decision, reasons = decide_line_fit(metrics, decision, reasons)
    fit = dot_fit.FitResult(decision, reasons, homography, coordinates, inliers, metrics)
    score = line_selection_score(dot_fit, metrics, decision)
    return {
        "selectionScore": round_metric(score),
        "fit": fit,
        "points": dst,
        "linePairs": line_pairs,
        "subset": {
            "strideA": stride_a,
            "strideB": stride_b,
            "offsetA": offset_a,
            "offsetB": offset_b,
            "lineFamilyACount": len(family_a),
            "lineFamilyBCount": len(family_b),
            "refinedInlierLines": False,
        },
    }


def refine_subset_from_inliers(
    dot_fit: Any,
    family_a: list[Any],
    family_b: list[Any],
    line_mask: np.ndarray,
    base: dict[str, Any],
) -> dict[str, Any] | None:
    fit = base["fit"]
    line_pairs = base.get("linePairs") or []
    if not fit.inlier_indexes or not line_pairs:
        return None

    counts_a = [0 for _ in family_a]
    counts_b = [0 for _ in family_b]
    for index in fit.inlier_indexes:
        if index >= len(line_pairs):
            continue
        line_a, line_b = line_pairs[index]
        counts_a[line_a] += 1
        counts_b[line_b] += 1

    threshold_a = max(3, int(math.ceil(len(family_b) * 0.10)))
    threshold_b = max(3, int(math.ceil(len(family_a) * 0.10)))
    keep_a = [index for index, count in enumerate(counts_a) if count >= threshold_a]
    keep_b = [index for index, count in enumerate(counts_b) if count >= threshold_b]
    if len(keep_a) < 6 or len(keep_b) < 6:
        return None
    if len(keep_a) == len(family_a) and len(keep_b) == len(family_b):
        return None

    refined_a = [family_a[index] for index in keep_a]
    refined_b = [family_b[index] for index in keep_b]
    refined = fit_subset(dot_fit, refined_a, refined_b, line_mask, 1, 1, 0, 0)
    if refined is None:
        return None
    refined["subset"]["refinedInlierLines"] = True
    refined["subset"]["sourceLineFamilyACount"] = len(family_a)
    refined["subset"]["sourceLineFamilyBCount"] = len(family_b)
    refined["fit"].metrics["lineRefinedSubset"] = True
    return refined


def line_selection_score(dot_fit: Any, metrics: dict[str, Any], decision: str) -> float:
    score = dot_fit.selection_score_for_fit(metrics, decision)
    stride_penalty = (float(metrics.get("lineSubsetStrideA") or 1) - 1.0 + float(metrics.get("lineSubsetStrideB") or 1) - 1.0) * 900.0
    low_support_penalty = max(0.0, 0.35 - float(metrics.get("p25LineSupport") or 0.0)) * 3500.0
    huge_span_penalty = max(0.0, max(float(metrics.get("spanI") or 0.0), float(metrics.get("spanJ") or 0.0)) - 45.0) * 45.0
    refined_bonus = 450.0 if metrics.get("lineRefinedSubset") else 0.0
    return score - stride_penalty - low_support_penalty - huge_span_penalty + refined_bonus


def decide_line_fit(metrics: dict[str, Any], base_decision: str, base_reasons: list[str]) -> tuple[str, list[str]]:
    hard = []
    weak = []
    if min(int(metrics.get("lineFamilyACount") or 0), int(metrics.get("lineFamilyBCount") or 0)) < 8:
        hard.append("too few ordered lines in one family")
    if int(metrics.get("homographyInliers") or 0) < 80:
        hard.append("too few line intersections survived homography")
    if float(metrics.get("homographyInlierRatio") or 0.0) < 0.65:
        weak.append("line-intersection inlier ratio is low")
    if metrics.get("p90ReprojectionErrorCells") is None or float(metrics.get("p90ReprojectionErrorCells") or 99.0) > 0.12:
        weak.append("line-intersection reprojection error is high")
    if float(metrics.get("medianLineSupport") or 0.0) < 0.70:
        weak.append("line-only fitted median support is weak")
    if float(metrics.get("p25LineSupport") or 0.0) < 0.55:
        weak.append("line-only fitted lower-quartile support is weak")

    if hard:
        return "refuse", hard + weak + [reason for reason in base_reasons if reason not in hard and reason not in weak]
    if not weak and base_decision != "refuse":
        return "accepted-visible-lattice-geometry", ["visible line-family lattice homography only; full extent is not inferred"]
    if base_decision == "refuse":
        return "refuse", base_reasons + weak
    return "candidate-visible-lattice-geometry", ["requires manual confirmation before projection", *weak]


def median_line_spacing(family_a: list[Any], family_b: list[Any]) -> float:
    spacings = []
    for family in (family_a, family_b):
        offsets = [float(item.offset) for item in family]
        diffs = np.diff(offsets)
        if len(diffs):
            spacings.extend(abs(diffs).tolist())
    if not spacings:
        return 30.0
    return max(1.0, float(np.median(spacings)))


def intersect_lines(left: np.ndarray, right: np.ndarray) -> np.ndarray | None:
    point = np.cross(left, right)
    if abs(float(point[2])) < 1e-6:
        return None
    return np.array([float(point[0] / point[2]), float(point[1] / point[2])], dtype=np.float32)


def variant_summary(variant: dict[str, Any]) -> dict[str, Any]:
    fit = variant["fit"]
    metrics = fit.metrics
    return {
        "selectionScore": variant["selectionScore"],
        "decision": fit.decision,
        "subset": variant["subset"],
        "homographyInliers": metrics.get("homographyInliers"),
        "homographyInlierRatio": metrics.get("homographyInlierRatio"),
        "spanI": metrics.get("spanI"),
        "spanJ": metrics.get("spanJ"),
        "p90ReprojectionErrorCells": metrics.get("p90ReprojectionErrorCells"),
        "medianLineSupport": metrics.get("medianLineSupport"),
        "p25LineSupport": metrics.get("p25LineSupport"),
    }


def write_overlay(
    dot_fit: Any,
    ai_grid: Any,
    label: dict[str, Any],
    source_id: str,
    points: np.ndarray,
    line_mask: np.ndarray,
    fit: Any,
    overlays_dir: Path,
    subset: dict[str, Any] | None,
) -> Path:
    path = dot_fit.write_overlay(ai_grid, label, source_id, points, line_mask, fit, overlays_dir, variant_index=98)
    target = overlays_dir / f"{slugify(source_id)}-line-lattice.png"
    path.replace(target)

    with Image.open(target) as image:
        canvas = image.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    if subset:
        draw.rectangle((8, 42, min(canvas.width - 8, 700), 68), fill=(0, 0, 0))
        draw.text(
            (14, 47),
            f"subset a {subset['offsetA']}:{subset['strideA']} b {subset['offsetB']}:{subset['strideB']} lines {subset['lineFamilyACount']}x{subset['lineFamilyBCount']}",
            fill=(255, 255, 255),
        )
    canvas.save(target)
    return target


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    decisions: dict[str, int] = {}
    for result in results:
        decisions[result["decision"]] = decisions.get(result["decision"], 0) + 1
    return {
        "total": len(results),
        "decisions": decisions,
        "acceptedVisibleGeometry": decisions.get("accepted-visible-lattice-geometry", 0),
        "candidateVisibleGeometry": decisions.get("candidate-visible-lattice-geometry", 0),
        "acceptedOrCandidateVisibleGeometry": decisions.get("accepted-visible-lattice-geometry", 0)
        + decisions.get("candidate-visible-lattice-geometry", 0),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AI Line Lattice RANSAC",
        "",
        f"- Selection mode: {report['selectionMode']}",
        f"- Total: `{report['summary']['total']}`",
        f"- Decisions: `{json.dumps(report['summary']['decisions'], sort_keys=True)}`",
        "",
        "| Source | Decision | Mode | Families | Subset | Variants | Inliers | Span | Homography line <=.15 | Mesh line <=.15 | Reasons | Overlay |",
        "| --- | --- | --- | --- | --- | ---: | ---: | --- | ---: | ---: | --- | --- |",
    ]
    for result in report["results"]:
        fit = result["fit"]
        bench = result["benchmark"]
        subset = result.get("subset") or {}
        subset_text = (
            ""
            if not subset
            else f"{subset.get('offsetA')}:{subset.get('strideA')} / {subset.get('offsetB')}:{subset.get('strideB')}"
        )
        lines.append(
            f"| `{result['sourceId']}` | `{result['decision']}` | {result.get('familyMode')} | {result['lineFamilyCounts']} | {subset_text} | "
            f"{result['variantCount']} | {fit.get('homographyInliers')} | {fit.get('spanI')}x{fit.get('spanJ')} | "
            f"{bench.get('truthLineSamplesWithin0_15SquaresPct')} | {bench.get('truthMeshSamplesWithin0_15SquaresPct')} | "
            f"{'; '.join(result['reasons'])} | `{result['overlayImage']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def render_console(report: dict[str, Any]) -> str:
    lines = [f"AI line lattice RANSAC: {json.dumps(report['summary']['decisions'], sort_keys=True)}"]
    for result in report["results"]:
        fit = result["fit"]
        bench = result["benchmark"]
        lines.append(
            f"- {result['sourceId']}: {result['decision']} families={result['lineFamilyCounts']} "
            f"mode={result.get('familyMode')} subset={result.get('subset')} inliers={fit.get('homographyInliers')} "
            f"truthLine<=.15={bench.get('truthLineSamplesWithin0_15SquaresPct')}"
        )
    lines.append(f"Artifacts: {report['outDir']}/report.md")
    return "\n".join(lines)


def write_contact_sheet(results: list[dict[str, Any]], out_dir: Path) -> None:
    if not results:
        return
    thumbs = []
    for result in results:
        image = Image.open(result["overlayImage"]).convert("RGB")
        image.thumbnail((260, 345), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (280, 405), (235, 235, 235))
        canvas.paste(image, ((280 - image.width) // 2, 10))
        draw = ImageDraw.Draw(canvas)
        fit = result["fit"]
        draw.text((10, 355), result["sourceId"].replace("real-map-home-", "").replace(".jpg", ""), fill=(0, 0, 0))
        draw.text((10, 372), result["decision"], fill=(0, 0, 0))
        draw.text((10, 389), f"in {fit.get('homographyInliers')} span {fit.get('spanI')}x{fit.get('spanJ')}", fill=(0, 0, 0))
        thumbs.append(canvas)
    columns = 4
    rows = math.ceil(len(thumbs) / columns)
    sheet = Image.new("RGB", (columns * 280, rows * 405), (220, 220, 220))
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((index % columns) * 280, (index // columns) * 405))
    sheet.save(out_dir / "contact-sheet.jpg", quality=92)


def slugify(value: str) -> str:
    return "".join(char if char.isalnum() or char in "._-" else "-" for char in value).strip("-")


def round_metric(value: float) -> float:
    return round(float(value), 3)


if __name__ == "__main__":
    main()
