#!/usr/bin/env python3
"""Probe whether AI-generated grid masks can become usable lattice geometry.

This script treats generated color as foreground only. It infers line families
geometrically, then uses fixture labels only to score the result.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
AI_GRID_PATH = ROOT / "scripts" / "ai-grid-experiment.py"
LABELS_PATH = ROOT / "input" / "map-grid-labels.json"
OUT_DIR = ROOT / "test-results" / "ai-mask-lattice-probe"


@dataclass
class SegmentLine:
    angle: float
    length: float
    line: np.ndarray
    segment: np.ndarray


@dataclass
class LineCluster:
    offset: float
    support: float
    line: np.ndarray
    angle: float


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports-glob", default="test-results/ai-grid-experiments-grok-realhome/*/report.json")
    parser.add_argument("--extra-report", action="append", default=[])
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args()

    ai_grid = load_ai_grid_module()
    labels = {label["sourceId"]: label for label in json.loads(LABELS_PATH.read_text())["labels"]}
    report_paths = sorted(ROOT.glob(args.reports_glob))
    report_paths.extend(Path(path) if Path(path).is_absolute() else ROOT / path for path in args.extra_report)

    out_dir = Path(args.out_dir)
    overlays_dir = out_dir / "overlays"
    overlays_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for report_path in report_paths:
        report = json.loads(report_path.read_text())
        source_id = report["sourceId"]
        label = labels.get(source_id)
        if not label:
            continue
        for experiment in report["results"]:
            output_image = experiment.get("outputImage")
            if not output_image:
                continue
            image_path = Path(output_image)
            if not image_path.is_absolute():
                image_path = ROOT / image_path
            result = analyze_mask(ai_grid, source_id, image_path, label, experiment.get("kind"), experiment.get("experimentId"))
            results.append(result)
            if result.get("overlayImage") is not None:
                overlay = Path(result["overlayImage"])
                target = overlays_dir / f"{slugify(source_id)}-{slugify(result['experimentId'])}.png"
                if overlay.exists():
                    overlay.replace(target)
                    result["overlayImage"] = str(target)

    summary = summarize(results)
    output = {"outDir": str(out_dir), "summary": summary, "results": results}
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(f"{json.dumps(output, indent=2)}\n")
    (out_dir / "report.md").write_text(render_markdown(output))
    print(render_console(output))


def load_ai_grid_module() -> Any:
    spec = importlib.util.spec_from_file_location("ai_grid_experiment", AI_GRID_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load ai-grid-experiment.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["ai_grid_experiment"] = module
    spec.loader.exec_module(module)
    return module


def analyze_mask(
    ai_grid: Any,
    source_id: str,
    image_path: Path,
    label: dict[str, Any],
    kind: str | None = None,
    experiment_id: str | None = None,
) -> dict[str, Any]:
    with Image.open(image_path) as image:
        rgb = np.array(ImageOps.exif_transpose(image).convert("RGB"))
    mask_kind = "white_mask" if kind == "dot_mask" else "color_mask"
    mask = ai_grid.extract_signal_mask(rgb, mask_kind)
    if float((mask > 0).mean()) < 0.005:
        mask = ai_grid.extract_signal_mask(rgb, "white_mask")
    analysis_mask = mask
    if kind == "dot_mask":
        analysis_mask = cv2.dilate(mask, np.ones((5, 5), np.uint8), iterations=1)

    segments = hough_segments(analysis_mask, dot_mode=kind == "dot_mask")
    families = choose_families(segments)
    scaled_label = ai_grid.scale_label(label, rgb.shape[1], rgb.shape[0])
    family_results = []
    all_clusters: list[tuple[int, LineCluster]] = []
    for index, family in enumerate(families):
        selected = select_segments_for_family(segments, family["angle"])
        clusters = cluster_family_lines(selected, rgb.shape[1], rgb.shape[0])
        clusters = prune_regular_sequence(clusters)
        all_clusters.extend((index, cluster) for cluster in clusters)
        family_results.append(score_family(ai_grid, clusters, scaled_label, rgb.shape[1], rgb.shape[0]))

    visible_quad = visible_quad_from_families([cluster for index, cluster in all_clusters if index == 0], [cluster for index, cluster in all_clusters if index == 1])
    overlay_path = write_overlay(image_path, mask, all_clusters, visible_quad)
    matched_axes = {result.get("axis") for result in family_results}
    usable = (
        len(family_results) == 2
        and matched_axes == {"column", "row"}
        and min((result.get("matchedLineRatio") or 0.0) for result in family_results) >= 0.55
        and max((result.get("medianLineErrorSquares") or 99.0) for result in family_results) <= 0.18
    )

    result = {
        "sourceId": source_id,
        "experimentId": experiment_id or image_path.stem,
        "imagePath": str(image_path),
        "width": int(rgb.shape[1]),
        "height": int(rgb.shape[0]),
        "signalPct": round_metric(float((mask > 0).mean() * 100)),
        "houghSegments": len(segments),
        "familyAngles": [round_metric(family["angle"]) for family in families],
        "familyScores": family_results,
        "visibleQuad": None if visible_quad is None else [{"x": round_metric(float(point[0])), "y": round_metric(float(point[1]))} for point in visible_quad],
        "usableLatticeSeed": usable,
        "overlayImage": str(overlay_path) if overlay_path else None,
    }
    if kind == "dot_mask":
        result["dotScore"] = ai_grid.dot_intersection_score(mask, scaled_label)
    return result


def hough_segments(mask: np.ndarray, dot_mode: bool = False) -> list[SegmentLine]:
    height, width = mask.shape[:2]
    lines = cv2.HoughLinesP(
        mask,
        1,
        np.pi / 720,
        threshold=20 if dot_mode else 35,
        minLineLength=max(70, int(min(width, height) * 0.08)) if dot_mode else max(28, int(min(width, height) * 0.035)),
        maxLineGap=max(28, int(min(width, height) * 0.035)) if dot_mode else max(6, int(min(width, height) * 0.01)),
    )
    if lines is None:
        return []
    segments = []
    for x1, y1, x2, y2 in lines[:, 0, :]:
        dx = float(x2 - x1)
        dy = float(y2 - y1)
        length = float(math.hypot(dx, dy))
        if length < 28:
            continue
        angle = (math.degrees(math.atan2(dy, dx)) + 180) % 180
        line = np.cross([float(x1), float(y1), 1.0], [float(x2), float(y2), 1.0]).astype(float)
        norm = math.hypot(float(line[0]), float(line[1]))
        if norm == 0:
            continue
        line /= norm
        if line[2] < 0:
            line *= -1
        segments.append(SegmentLine(angle, length, line, np.array([x1, y1, x2, y2], dtype=float)))
    return segments


def choose_families(segments: list[SegmentLine]) -> list[dict[str, float]]:
    if not segments:
        return []
    angles = np.array([segment.angle for segment in segments])
    lengths = np.array([segment.length for segment in segments])
    hist, bins = np.histogram(angles, bins=180, range=(0, 180), weights=lengths)
    candidates = []
    scratch = hist.copy()
    for _ in range(12):
        index = int(np.argmax(scratch))
        weight = float(scratch[index])
        if weight <= 0:
            break
        angle = float((bins[index] + bins[index + 1]) / 2)
        candidates.append({"angle": angle, "weight": weight})
        for offset in range(-8, 9):
            scratch[(index + offset) % len(scratch)] = 0
    if len(candidates) < 2:
        return candidates

    best_pair = None
    best_score = -1.0
    for i, left in enumerate(candidates):
        for right in candidates[i + 1:]:
            separation = angle_distance(left["angle"], right["angle"])
            if separation < 25 or separation > 155:
                continue
            orthogonality = 1.0 - min(1.0, abs(separation - 90) / 90)
            score = math.sqrt(left["weight"] * right["weight"]) * (0.35 + 0.65 * orthogonality)
            if score > best_score:
                best_pair = [left, right]
                best_score = score
    if best_pair is None:
        return candidates[:2]
    return sorted(best_pair, key=lambda item: item["angle"])


def select_segments_for_family(segments: list[SegmentLine], angle: float) -> list[SegmentLine]:
    return [segment for segment in segments if angle_distance(segment.angle, angle) <= 20]


def cluster_family_lines(segments: list[SegmentLine], width: int, height: int) -> list[LineCluster]:
    if not segments:
        return []
    angle_rad = math.radians(weighted_circular_mean([segment.angle for segment in segments], [segment.length for segment in segments]))
    normal = np.array([-math.sin(angle_rad), math.cos(angle_rad)], dtype=float)
    center = np.array([width / 2, height / 2], dtype=float)

    values = []
    for segment in segments:
        x1, y1, x2, y2 = segment.segment
        midpoint = np.array([(x1 + x2) / 2, (y1 + y2) / 2], dtype=float)
        offset = float(np.dot(midpoint - center, normal))
        values.append((offset, segment))
    values.sort(key=lambda item: item[0])

    raw_clusters: list[list[tuple[float, SegmentLine]]] = []
    for item in values:
        if not raw_clusters:
            raw_clusters.append([item])
            continue
        current_offsets = [value[0] for value in raw_clusters[-1]]
        current_weights = [value[1].length for value in raw_clusters[-1]]
        current_center = float(np.average(current_offsets, weights=current_weights))
        if abs(item[0] - current_center) > 9:
            raw_clusters.append([item])
        else:
            raw_clusters[-1].append(item)

    clusters = []
    for cluster in raw_clusters:
        support = float(sum(segment.length for _, segment in cluster))
        if support < 90:
            continue
        ref = cluster[0][1].line.copy()
        line_sum = np.zeros(3, dtype=float)
        angle_values = []
        weights = []
        for offset, segment in cluster:
            line = segment.line.copy()
            if float(np.dot(ref, line)) < 0:
                line *= -1
            line_sum += line * segment.length
            angle_values.append(segment.angle)
            weights.append(segment.length)
        line_sum /= max(1.0, support)
        norm = math.hypot(float(line_sum[0]), float(line_sum[1]))
        if norm == 0:
            continue
        line_sum /= norm
        offset = float(np.average([value[0] for value in cluster], weights=[value[1].length for value in cluster]))
        angle = weighted_circular_mean(angle_values, weights)
        clusters.append(LineCluster(offset, support, line_sum, angle))
    clusters.sort(key=lambda cluster: cluster.offset)
    return clusters


def prune_regular_sequence(clusters: list[LineCluster]) -> list[LineCluster]:
    if len(clusters) < 6:
        return clusters
    supports = np.array([cluster.support for cluster in clusters])
    strong_floor = max(80.0, float(np.percentile(supports, 25)) * 0.45)
    strong = [cluster for cluster in clusters if cluster.support >= strong_floor]
    if len(strong) < 6:
        return clusters
    return strong


def score_family(ai_grid: Any, clusters: list[LineCluster], label: dict[str, Any], width: int, height: int) -> dict[str, Any]:
    if not clusters:
        return {"lineCount": 0, "axis": None}
    image_to_grid = cv2.getPerspectiveTransform(
        ai_grid.label_corners(label),
        np.float32([[0, 0], [label["columns"], 0], [label["columns"], label["rows"]], [0, label["rows"]]]),
    )

    scored = []
    for cluster in clusters:
        points = sample_line_points(cluster.line, width, height, count=120)
        if len(points) < 8:
            continue
        grid_points = cv2.perspectiveTransform(np.float32(points).reshape(1, -1, 2), image_to_grid).reshape(-1, 2)
        finite = np.isfinite(grid_points).all(axis=1)
        grid_points = grid_points[finite]
        if len(grid_points) < 8:
            continue
        inside = (
            (grid_points[:, 0] >= -1.5)
            & (grid_points[:, 0] <= label["columns"] + 1.5)
            & (grid_points[:, 1] >= -1.5)
            & (grid_points[:, 1] <= label["rows"] + 1.5)
        )
        grid_points = grid_points[inside]
        if len(grid_points) < 8:
            continue
        column_error = np.median(np.abs(grid_points[:, 0] - np.rint(grid_points[:, 0])))
        row_error = np.median(np.abs(grid_points[:, 1] - np.rint(grid_points[:, 1])))
        if column_error <= row_error:
            axis = "column"
            index = int(round(float(np.median(grid_points[:, 0]))))
            error = float(column_error)
        else:
            axis = "row"
            index = int(round(float(np.median(grid_points[:, 1]))))
            error = float(row_error)
        scored.append({"axis": axis, "index": index, "error": error, "support": cluster.support})

    if not scored:
        return {"lineCount": len(clusters), "axis": None}
    axis = "column" if sum(1 for item in scored if item["axis"] == "column") >= sum(1 for item in scored if item["axis"] == "row") else "row"
    axis_items = [item for item in scored if item["axis"] == axis and item["error"] <= 0.25]
    unique_indices = sorted({item["index"] for item in axis_items})
    expected_indices = visible_label_indices(ai_grid, label, axis)
    matched = len(set(unique_indices) & set(expected_indices))
    ratio = matched / max(1, len(expected_indices))
    median_error = float(np.median([item["error"] for item in axis_items])) if axis_items else None
    return {
        "lineCount": len(clusters),
        "axis": axis,
        "matchedLines": matched,
        "expectedVisibleLines": len(expected_indices),
        "matchedLineRatio": round_metric(ratio),
        "uniqueIndices": unique_indices,
        "expectedIndexRange": [expected_indices[0], expected_indices[-1]] if expected_indices else None,
        "medianLineErrorSquares": None if median_error is None else round_metric(median_error),
        "p90LineErrorSquares": None if not axis_items else round_metric(float(np.percentile([item["error"] for item in axis_items], 90))),
    }


def visible_label_indices(ai_grid: Any, label: dict[str, Any], axis: str) -> list[int]:
    width = int(label["imageWidth"])
    height = int(label["imageHeight"])
    columns = int(label["columns"])
    rows = int(label["rows"])
    grid_to_image = cv2.getPerspectiveTransform(np.float32([[0, 0], [columns, 0], [columns, rows], [0, rows]]), ai_grid.label_corners(label))
    values = []
    limit = columns if axis == "column" else rows
    other_limit = rows if axis == "column" else columns
    for index in range(limit + 1):
        if axis == "column":
            samples = [[index, value] for value in np.linspace(0, other_limit, 80)]
        else:
            samples = [[value, index] for value in np.linspace(0, other_limit, 80)]
        points = cv2.perspectiveTransform(np.float32(samples).reshape(1, -1, 2), grid_to_image).reshape(-1, 2)
        inside = (points[:, 0] >= 0) & (points[:, 0] < width) & (points[:, 1] >= 0) & (points[:, 1] < height)
        if int(inside.sum()) >= 3:
            values.append(index)
    return values


def sample_line_points(line: np.ndarray, width: int, height: int, count: int = 80) -> list[list[float]]:
    a, b, c = [float(value) for value in line]
    points = []
    if abs(b) > abs(a):
        xs = np.linspace(0, width - 1, count)
        for x in xs:
            y = -(a * x + c) / b
            if -height * 0.5 <= y <= height * 1.5:
                points.append([float(x), float(y)])
    else:
        ys = np.linspace(0, height - 1, count)
        for y in ys:
            x = -(b * y + c) / a
            if -width * 0.5 <= x <= width * 1.5:
                points.append([float(x), float(y)])
    return points


def visible_quad_from_families(left_family: list[LineCluster], right_family: list[LineCluster]) -> np.ndarray | None:
    if len(left_family) < 2 or len(right_family) < 2:
        return None
    a0 = left_family[0].line
    a1 = left_family[-1].line
    b0 = right_family[0].line
    b1 = right_family[-1].line
    points = [intersect_lines(a0, b0), intersect_lines(a1, b0), intersect_lines(a1, b1), intersect_lines(a0, b1)]
    if any(point is None for point in points):
        return None
    return np.float32(points)


def intersect_lines(left: np.ndarray, right: np.ndarray) -> np.ndarray | None:
    point = np.cross(left, right)
    if abs(float(point[2])) < 1e-6:
        return None
    return np.array([float(point[0] / point[2]), float(point[1] / point[2])], dtype=float)


def write_overlay(image_path: Path, mask: np.ndarray, clusters: list[tuple[int, LineCluster]], visible_quad: np.ndarray | None) -> Path | None:
    height, width = mask.shape
    overlay = cv2.cvtColor(mask, cv2.COLOR_GRAY2RGB)
    colors = [(0, 255, 255), (255, 128, 0)]
    for family_index, cluster in clusters:
        points = sample_line_points(cluster.line, width, height, 2)
        if len(points) >= 2:
            p1 = tuple(np.rint(points[0]).astype(int))
            p2 = tuple(np.rint(points[-1]).astype(int))
            cv2.line(overlay, p1, p2, colors[family_index % len(colors)], 2, cv2.LINE_AA)
    if visible_quad is not None:
        cv2.polylines(overlay, [np.rint(visible_quad).astype(np.int32)], True, (255, 255, 255), 2, cv2.LINE_AA)
    tmp = image_path.parent / f"{image_path.stem}-lattice-overlay.png"
    cv2.imwrite(str(tmp), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
    return tmp


def weighted_circular_mean(angles: list[float], weights: list[float]) -> float:
    radians = np.deg2rad(np.array(angles) * 2)
    weights_array = np.array(weights)
    x = float(np.sum(np.cos(radians) * weights_array))
    y = float(np.sum(np.sin(radians) * weights_array))
    return (math.degrees(math.atan2(y, x)) / 2 + 180) % 180


def angle_distance(left: float, right: float) -> float:
    delta = abs(left - right) % 180
    return min(delta, 180 - delta)


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    usable = [result for result in results if result.get("usableLatticeSeed")]
    return {
        "total": len(results),
        "usableLatticeSeeds": len(usable),
        "usablePct": round_metric(len(usable) / max(1, len(results)) * 100),
        "medianSignalPct": None if not results else round_metric(float(np.median([result["signalPct"] for result in results]))),
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AI Mask Lattice Probe",
        "",
        f"- Total masks: `{report['summary']['total']}`",
        f"- Usable lattice seeds: `{report['summary']['usableLatticeSeeds']}`",
        "",
        "| Source | Usable | Signal % | Angles | Family Scores | Overlay |",
        "| --- | --- | ---: | --- | --- | --- |",
    ]
    for result in report["results"]:
        scores = "; ".join(
            f"{score.get('axis')} {score.get('matchedLines')}/{score.get('expectedVisibleLines')} err {score.get('medianLineErrorSquares')}"
            for score in result["familyScores"]
        )
        lines.append(
            f"| `{result['sourceId']}` | {result['usableLatticeSeed']} | {result['signalPct']} | "
            f"{result['familyAngles']} | {scores} | `{result.get('overlayImage')}` |"
        )
    lines.append("")
    return "\n".join(lines)


def render_console(report: dict[str, Any]) -> str:
    lines = [f"AI mask lattice probe: {report['summary']['usableLatticeSeeds']}/{report['summary']['total']} usable"]
    for result in report["results"]:
        score_text = ", ".join(
            f"{score.get('axis')} {score.get('matchedLines')}/{score.get('expectedVisibleLines')} err={score.get('medianLineErrorSquares')}"
            for score in result["familyScores"]
        )
        lines.append(f"- {result['sourceId']}: usable={result['usableLatticeSeed']} signal={result['signalPct']} angles={result['familyAngles']} {score_text}")
    lines.append(f"Artifacts: {report.get('outDir', OUT_DIR)}/report.md")
    return "\n".join(lines)


def slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-")


def round_metric(value: float) -> float:
    return round(float(value), 3)


if __name__ == "__main__":
    main()
