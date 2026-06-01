#!/usr/bin/env python3
"""Experimental real-camera lattice probe for labeled home map photos.

Run with uv when OpenCV is not installed in the active Python:

    uv run --with opencv-python --with numpy --with pillow \
      python scripts/real_camera_lattice_probe.py --format markdown

This is intentionally diagnostic-only. It estimates two dominant Hough segment
families, fits periodic line offsets for each family, and compares the rough
visible lattice against input/map-grid-labels.json.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import cv2
    import numpy as np
    from PIL import Image, ImageOps
except ModuleNotFoundError as error:  # pragma: no cover - dependency hint path.
    raise SystemExit(
        "Missing Python image dependency. Try:\n"
        "  uv run --with opencv-python --with numpy --with pillow "
        "python scripts/real_camera_lattice_probe.py --format markdown"
    ) from error


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LABELS_PATH = ROOT / "input" / "map-grid-labels.json"


@dataclass(frozen=True)
class Segment:
    start: np.ndarray
    end: np.ndarray
    midpoint: np.ndarray
    angle_rad: float
    angle_deg: float
    length: float


@dataclass(frozen=True)
class OffsetCluster:
    center: float
    weight: float
    count: int


@dataclass(frozen=True)
class PeriodFit:
    pitch: float
    phase: float
    score: float
    strength: float
    near_weight_fraction: float
    occupancy: float
    line_count: int
    cell_count: int
    offset_min: float
    offset_max: float
    residual_median: float
    residual_p90: float


@dataclass(frozen=True)
class DirectionFamily:
    angle_rad: float
    angle_deg: float
    normal: np.ndarray
    support_segments: int
    support_weight: float
    clusters: list[OffsetCluster]
    period: PeriodFit | None


def main() -> None:
    args = parse_args()
    labels = load_real_home_labels(args.labels, args.source_glob)
    started = time.perf_counter()
    results = [probe_label(label, args) for label in labels]
    report = {
        "candidateId": "real-camera-lattice-probe-v1",
        "candidateName": "Real Camera Lattice Probe",
        "candidateCategory": "passive-diagnostic",
        "usesGroundTruthForDetection": False,
        "labelsPath": str(args.labels.relative_to(ROOT) if args.labels.is_relative_to(ROOT) else args.labels),
        "sourceGlob": args.source_glob,
        "maxImageSide": args.max_image_side,
        "elapsedMs": round_metric((time.perf_counter() - started) * 1000),
        "summary": summarize_results(results),
        "results": results,
    }

    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(render_markdown(report))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe real-camera map photos with an alternate Hough lattice approach.",
    )
    parser.add_argument(
        "--labels",
        type=Path,
        default=DEFAULT_LABELS_PATH,
        help="Path to map-grid-labels.json.",
    )
    parser.add_argument(
        "--source-glob",
        default="real-map-home-*",
        help="fnmatch pattern matched against label sourceId and source image basename.",
    )
    parser.add_argument(
        "--max-image-side",
        type=int,
        default=1600,
        help="Downsample the longest side before analysis. Use 0 for native size.",
    )
    parser.add_argument(
        "--angle-tolerance",
        type=float,
        default=10.0,
        help="Degrees around each dominant line direction to include in a family.",
    )
    parser.add_argument(
        "--min-pitch",
        type=float,
        default=6.0,
        help="Minimum analysis-space lattice pitch to consider.",
    )
    parser.add_argument(
        "--max-pitch",
        type=float,
        default=90.0,
        help="Maximum analysis-space lattice pitch to consider.",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        help="Output format written to stdout.",
    )
    return parser.parse_args()


def load_real_home_labels(path: Path, source_glob: str) -> list[dict[str, Any]]:
    labels_path = path if path.is_absolute() else ROOT / path
    label_file = json.loads(labels_path.read_text())
    labels: list[dict[str, Any]] = []
    for label in label_file.get("labels", []):
        source_url = str(label.get("sourceUrl", ""))
        source_id = str(label.get("sourceId", ""))
        source_name = Path(source_url).name
        values = [source_id, source_url, source_name]
        if not any(fnmatch.fnmatch(value, source_glob) for value in values):
            continue
        if not source_url.startswith("/"):
            continue
        if "corners" not in label or "columns" not in label or "rows" not in label:
            continue
        labels.append(label)
    return labels


def probe_label(label: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    image_path = ROOT / str(label["sourceUrl"]).removeprefix("/")
    started = time.perf_counter()
    try:
        image, original_size, scale = load_rgb_image(image_path, args.max_image_side)
        segments, edge_pixel_count = detect_segments(image)
        families = detect_direction_families(
            segments,
            image.shape[:2],
            angle_tolerance=args.angle_tolerance,
            min_pitch=args.min_pitch,
            max_pitch=args.max_pitch,
        )
        return build_detection_result(label, image.shape[:2], original_size, scale, segments, edge_pixel_count, families, started)
    except Exception as error:  # noqa: BLE001 - diagnostic script should keep the batch going.
        return {
            "sourceId": label.get("sourceId"),
            "sourceName": label.get("sourceName"),
            "detected": False,
            "errorMessage": f"{type(error).__name__}: {error}",
            "elapsedMs": round_metric((time.perf_counter() - started) * 1000),
        }


def load_rgb_image(path: Path, max_side: int) -> tuple[np.ndarray, tuple[int, int], float]:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")
        original_size = image.size
        scale = 1.0
        if max_side > 0:
            width, height = image.size
            side = max(width, height)
            if side > max_side:
                scale = max_side / side
                image = image.resize((round(width * scale), round(height * scale)), Image.Resampling.LANCZOS)
        return np.array(image), original_size, scale


def detect_segments(image: np.ndarray) -> tuple[list[Segment], int]:
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    blurred = cv2.GaussianBlur(clahe, (3, 3), 0)
    edges = cv2.Canny(blurred, 55, 145, apertureSize=3, L2gradient=True)
    height, width = gray.shape
    min_side = min(height, width)
    raw_lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=max(42, min_side // 22),
        minLineLength=max(28, min_side // 34),
        maxLineGap=max(7, min_side // 100),
    )
    if raw_lines is None:
        return [], int(np.count_nonzero(edges))

    segments: list[Segment] = []
    for line in raw_lines[:, 0, :]:
        x1, y1, x2, y2 = [float(value) for value in line]
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length < max(28, min_side / 36):
            continue
        angle_rad = math.atan2(dy, dx) % math.pi
        segments.append(
            Segment(
                start=np.array([x1, y1], dtype=np.float32),
                end=np.array([x2, y2], dtype=np.float32),
                midpoint=np.array([(x1 + x2) / 2, (y1 + y2) / 2], dtype=np.float32),
                angle_rad=angle_rad,
                angle_deg=math.degrees(angle_rad),
                length=length,
            ),
        )
    return segments, int(np.count_nonzero(edges))


def detect_direction_families(
    segments: list[Segment],
    image_shape: tuple[int, int],
    angle_tolerance: float,
    min_pitch: float,
    max_pitch: float,
) -> list[DirectionFamily]:
    if len(segments) < 2:
        return []

    dominant_angles = choose_dominant_angles(segments)
    families: list[DirectionFamily] = []
    for angle_deg in dominant_angles:
        angle_rad = math.radians(angle_deg)
        support = [segment for segment in segments if axial_angle_delta(segment.angle_deg, angle_deg) <= angle_tolerance]
        if len(support) < 4:
            continue
        refined_angle = weighted_axial_mean_angle(support)
        normal = np.array([-math.sin(refined_angle), math.cos(refined_angle)], dtype=np.float32)
        offsets = np.array([float(np.dot(normal, segment.midpoint)) for segment in support], dtype=np.float32)
        weights = np.array([segment.length for segment in support], dtype=np.float32)
        clusters = cluster_offsets(offsets, weights, cluster_epsilon=max(2.5, min(image_shape) * 0.003))
        period = estimate_period(clusters, min_pitch=min_pitch, max_pitch=max_pitch)
        families.append(
            DirectionFamily(
                angle_rad=refined_angle,
                angle_deg=normalize_angle_deg(math.degrees(refined_angle)),
                normal=normal,
                support_segments=len(support),
                support_weight=float(weights.sum()),
                clusters=clusters,
                period=period,
            ),
        )
    return families


def choose_dominant_angles(segments: list[Segment]) -> list[float]:
    bins = 180
    histogram = np.zeros(bins, dtype=np.float64)
    for segment in segments:
        index = int(round(segment.angle_deg)) % bins
        histogram[index] += segment.length

    padded = np.concatenate([histogram[-3:], histogram, histogram[:3]])
    kernel = np.array([1, 2, 4, 6, 4, 2, 1], dtype=np.float64)
    smoothed = np.convolve(padded, kernel / kernel.sum(), mode="same")[3:-3]
    peaks = []
    for index, value in enumerate(smoothed):
        if value >= smoothed[(index - 1) % bins] and value >= smoothed[(index + 1) % bins]:
            peaks.append((float(value), float(index)))
    peaks.sort(reverse=True)

    selected: list[float] = []
    for _weight, angle in peaks:
        if all(axial_angle_delta(angle, existing) >= 28 for existing in selected):
            selected.append(angle)
        if len(selected) == 2:
            break
    return selected


def weighted_axial_mean_angle(segments: list[Segment]) -> float:
    sin_sum = 0.0
    cos_sum = 0.0
    for segment in segments:
        sin_sum += math.sin(segment.angle_rad * 2) * segment.length
        cos_sum += math.cos(segment.angle_rad * 2) * segment.length
    return math.atan2(sin_sum, cos_sum) / 2 % math.pi


def cluster_offsets(offsets: np.ndarray, weights: np.ndarray, cluster_epsilon: float) -> list[OffsetCluster]:
    if len(offsets) == 0:
        return []
    order = np.argsort(offsets)
    sorted_offsets = offsets[order]
    sorted_weights = weights[order]

    clusters: list[OffsetCluster] = []
    current_offsets = [float(sorted_offsets[0])]
    current_weights = [float(sorted_weights[0])]
    for offset, weight in zip(sorted_offsets[1:], sorted_weights[1:]):
        if abs(float(offset) - weighted_average(current_offsets, current_weights)) <= cluster_epsilon:
            current_offsets.append(float(offset))
            current_weights.append(float(weight))
        else:
            clusters.append(
                OffsetCluster(
                    center=weighted_average(current_offsets, current_weights),
                    weight=float(sum(current_weights)),
                    count=len(current_offsets),
                ),
            )
            current_offsets = [float(offset)]
            current_weights = [float(weight)]

    clusters.append(
        OffsetCluster(
            center=weighted_average(current_offsets, current_weights),
            weight=float(sum(current_weights)),
            count=len(current_offsets),
        ),
    )
    return clusters


def estimate_period(clusters: list[OffsetCluster], min_pitch: float, max_pitch: float) -> PeriodFit | None:
    useful = [cluster for cluster in clusters if cluster.weight > 0]
    if len(useful) < 4:
        return None

    offsets = np.array([cluster.center for cluster in useful], dtype=np.float64)
    weights = np.array([cluster.weight for cluster in useful], dtype=np.float64)
    pitch_values = np.arange(min_pitch, max_pitch + 0.001, 0.5)
    best: PeriodFit | None = None
    for pitch in pitch_values:
        fit = score_pitch(offsets, weights, float(pitch))
        if fit is None:
            continue
        if best is None or fit.score > best.score:
            best = fit
    return best


def score_pitch(offsets: np.ndarray, weights: np.ndarray, pitch: float) -> PeriodFit | None:
    residues = np.mod(offsets, pitch)
    bin_count = max(18, int(round(pitch * 2)))
    hist = np.zeros(bin_count, dtype=np.float64)
    indexes = np.floor(residues / pitch * bin_count).astype(int) % bin_count
    for index, weight in zip(indexes, weights):
        hist[index] += weight
    padded = np.concatenate([hist[-2:], hist, hist[:2]])
    smoothed = np.convolve(padded, np.array([1, 2, 3, 2, 1], dtype=np.float64) / 9, mode="same")[2:-2]
    peak_index = int(np.argmax(smoothed))
    phase = (peak_index + 0.5) / bin_count * pitch

    residuals = periodic_residual(offsets, phase, pitch)
    tolerance = max(2.0, pitch * 0.18)
    near = residuals <= tolerance
    if int(np.count_nonzero(near)) < 4:
        return None

    near_weight_fraction = float(weights[near].sum() / max(1e-6, weights.sum()))
    line_indexes = np.round((offsets[near] - phase) / pitch).astype(int)
    unique_lines = np.unique(line_indexes)
    if len(unique_lines) < 4:
        return None

    expected_lines = int(unique_lines.max() - unique_lines.min() + 1)
    occupancy = min(1.0, len(unique_lines) / max(1, expected_lines))
    vectors = weights * np.exp(2j * np.pi * offsets / pitch)
    strength = float(abs(vectors.sum()) / max(1e-6, weights.sum()))
    residual_median = float(np.median(residuals[near]))
    residual_p90 = float(np.percentile(residuals[near], 90))
    coverage_bonus = min(1.0, len(unique_lines) / 18)
    residual_penalty = min(0.25, residual_median / max(1e-6, pitch) * 0.25)
    score = (
        near_weight_fraction * 0.40
        + occupancy * 0.30
        + coverage_bonus * 0.18
        + strength * 0.12
        - residual_penalty
    )
    return PeriodFit(
        pitch=pitch,
        phase=phase,
        score=float(score),
        strength=strength,
        near_weight_fraction=near_weight_fraction,
        occupancy=occupancy,
        line_count=int(len(unique_lines)),
        cell_count=int(max(0, expected_lines - 1)),
        offset_min=float(phase + unique_lines.min() * pitch),
        offset_max=float(phase + unique_lines.max() * pitch),
        residual_median=residual_median,
        residual_p90=residual_p90,
    )


def build_detection_result(
    label: dict[str, Any],
    image_shape: tuple[int, int],
    original_size: tuple[int, int],
    scale: float,
    segments: list[Segment],
    edge_pixel_count: int,
    families: list[DirectionFamily],
    started: float,
) -> dict[str, Any]:
    expected = expected_lattice(label, scale)
    matched = match_families_to_expected(families, expected)
    candidate = candidate_from_matched_families(label, matched, scale)
    family_summaries = [
        summarize_family(role, family, expected[role], scale)
        for role, family in matched.items()
        if family is not None
    ]

    detected = len(family_summaries) == 2
    result: dict[str, Any] = {
        "sourceId": label["sourceId"],
        "sourceName": label.get("sourceName"),
        "detected": detected,
        "imageWidth": int(original_size[0]),
        "imageHeight": int(original_size[1]),
        "analysisWidth": int(image_shape[1]),
        "analysisHeight": int(image_shape[0]),
        "analysisScale": round_metric(scale),
        "edgePixelCount": edge_pixel_count,
        "segmentCount": len(segments),
        "expectedColumns": int(label["columns"]),
        "expectedRows": int(label["rows"]),
        "expectedPitchPx": {
            "columns": round_metric(expected["columns"]["pitch_original"]),
            "rows": round_metric(expected["rows"]["pitch_original"]),
        },
        "families": family_summaries,
        "elapsedMs": round_metric((time.perf_counter() - started) * 1000),
    }
    if candidate is None:
        result.update(
            {
                "candidateColumns": None,
                "candidateRows": None,
                "countDelta": None,
                "meanCornerErrorPixels": None,
                "maxCornerErrorPixels": None,
                "meanCornerErrorSquares": None,
                "maxCornerErrorSquares": None,
                "candidateCorners": None,
                "message": "Could not form two-family lattice corner candidate.",
            },
        )
    else:
        result.update(candidate)
    return result


def expected_lattice(label: dict[str, Any], scale: float) -> dict[str, dict[str, float]]:
    corners = np.float32([[point["x"], point["y"]] for point in label["corners"]])
    top_left, top_right, bottom_right, bottom_left = corners * scale
    top_angle = segment_angle(top_left, top_right)
    bottom_angle = segment_angle(bottom_left, bottom_right)
    left_angle = segment_angle(top_left, bottom_left)
    right_angle = segment_angle(top_right, bottom_right)
    columns_pitch = (
        float(np.linalg.norm(top_right - top_left)) + float(np.linalg.norm(bottom_right - bottom_left))
    ) / max(1, int(label["columns"]) * 2)
    rows_pitch = (
        float(np.linalg.norm(bottom_left - top_left)) + float(np.linalg.norm(bottom_right - top_right))
    ) / max(1, int(label["rows"]) * 2)
    return {
        "columns": {
            "angle_deg": axial_mean_degrees([left_angle, right_angle]),
            "pitch_analysis": columns_pitch,
            "pitch_original": columns_pitch / max(scale, 1e-6),
            "cells": float(label["columns"]),
        },
        "rows": {
            "angle_deg": axial_mean_degrees([top_angle, bottom_angle]),
            "pitch_analysis": rows_pitch,
            "pitch_original": rows_pitch / max(scale, 1e-6),
            "cells": float(label["rows"]),
        },
    }


def match_families_to_expected(
    families: list[DirectionFamily],
    expected: dict[str, dict[str, float]],
) -> dict[str, DirectionFamily | None]:
    viable = [family for family in families if family.period is not None]
    if len(viable) < 2:
        return {"columns": viable[0] if viable else None, "rows": None}
    first, second = viable[:2]
    score_a = axial_angle_delta(first.angle_deg, expected["columns"]["angle_deg"]) + axial_angle_delta(
        second.angle_deg,
        expected["rows"]["angle_deg"],
    )
    score_b = axial_angle_delta(first.angle_deg, expected["rows"]["angle_deg"]) + axial_angle_delta(
        second.angle_deg,
        expected["columns"]["angle_deg"],
    )
    if score_a <= score_b:
        return {"columns": first, "rows": second}
    return {"columns": second, "rows": first}


def summarize_family(
    role: str,
    family: DirectionFamily,
    expected: dict[str, float],
    scale: float,
) -> dict[str, Any]:
    period = family.period
    assert period is not None
    pitch_original = period.pitch / max(scale, 1e-6)
    expected_pitch = expected["pitch_original"]
    return {
        "role": role,
        "angleDeg": round_metric(family.angle_deg),
        "expectedAngleDeg": round_metric(expected["angle_deg"]),
        "angleDeltaDeg": round_metric(axial_angle_delta(family.angle_deg, expected["angle_deg"])),
        "pitchPxAnalysis": round_metric(period.pitch),
        "pitchPxOriginal": round_metric(pitch_original),
        "expectedPitchPxOriginal": round_metric(expected_pitch),
        "pitchDeltaPct": round_metric(abs(pitch_original - expected_pitch) / max(1e-6, expected_pitch) * 100),
        "phasePxAnalysis": round_metric(period.phase),
        "periodScore": round_metric(period.score),
        "periodicityStrength": round_metric(period.strength),
        "nearWeightFraction": round_metric(period.near_weight_fraction),
        "lineOccupancy": round_metric(period.occupancy),
        "clusterCount": len(family.clusters),
        "supportSegments": family.support_segments,
        "supportWeight": round_metric(family.support_weight),
        "inferredVisibleCells": period.cell_count,
        "expectedCells": int(expected["cells"]),
        "cellDelta": int(period.cell_count - expected["cells"]),
        "residualMedianPxAnalysis": round_metric(period.residual_median),
        "residualP90PxAnalysis": round_metric(period.residual_p90),
    }


def candidate_from_matched_families(
    label: dict[str, Any],
    matched: dict[str, DirectionFamily | None],
    scale: float,
) -> dict[str, Any] | None:
    column_family = matched.get("columns")
    row_family = matched.get("rows")
    if column_family is None or row_family is None or column_family.period is None or row_family.period is None:
        return None

    points = [
        intersect_normal_lines(column_family.normal, column_family.period.offset_min, row_family.normal, row_family.period.offset_min),
        intersect_normal_lines(column_family.normal, column_family.period.offset_max, row_family.normal, row_family.period.offset_min),
        intersect_normal_lines(column_family.normal, column_family.period.offset_max, row_family.normal, row_family.period.offset_max),
        intersect_normal_lines(column_family.normal, column_family.period.offset_min, row_family.normal, row_family.period.offset_max),
    ]
    if any(point is None for point in points):
        return None

    corners_analysis = order_corners(np.float32(points))
    corners_original = corners_analysis / max(scale, 1e-6)
    truth = np.float32([[point["x"], point["y"]] for point in label["corners"]])
    deltas = best_corner_deltas(corners_original, truth)
    square_pixels = average_truth_square_pixels(label)
    candidate_columns = int(column_family.period.cell_count)
    candidate_rows = int(row_family.period.cell_count)
    return {
        "candidateColumns": candidate_columns,
        "candidateRows": candidate_rows,
        "countDelta": {
            "columns": candidate_columns - int(label["columns"]),
            "rows": candidate_rows - int(label["rows"]),
        },
        "meanCornerErrorPixels": round_metric(float(deltas.mean())),
        "maxCornerErrorPixels": round_metric(float(deltas.max())),
        "meanCornerErrorSquares": round_metric(float(deltas.mean() / max(1e-6, square_pixels))),
        "maxCornerErrorSquares": round_metric(float(deltas.max() / max(1e-6, square_pixels))),
        "candidateCorners": [
            {"x": round_metric(float(point[0])), "y": round_metric(float(point[1]))}
            for point in corners_original
        ],
        "message": "Visible-support candidate from dominant line-family outer offsets; intended as diagnostic evidence only.",
    }


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    detected = [result for result in results if result.get("detected")]
    count_matches = [
        result
        for result in detected
        if result.get("candidateColumns") == result.get("expectedColumns")
        and result.get("candidateRows") == result.get("expectedRows")
    ]
    corner_square_errors = [
        float(result["meanCornerErrorSquares"])
        for result in detected
        if result.get("meanCornerErrorSquares") is not None
    ]
    pitch_deltas = [
        float(family["pitchDeltaPct"])
        for result in detected
        for family in result.get("families", [])
        if family.get("pitchDeltaPct") is not None
    ]
    return {
        "imageCount": len(results),
        "detectedImageCount": len(detected),
        "exactVisibleCountMatches": len(count_matches),
        "meanCornerErrorSquaresAvg": round_metric(sum(corner_square_errors) / len(corner_square_errors))
        if corner_square_errors
        else None,
        "pitchDeltaPctAvg": round_metric(sum(pitch_deltas) / len(pitch_deltas)) if pitch_deltas else None,
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# Real Camera Lattice Probe",
        "",
        f"- Images: {summary['detectedImageCount']}/{summary['imageCount']} produced two lattice families.",
        f"- Exact visible count matches: {summary['exactVisibleCountMatches']}/{summary['imageCount']}.",
        f"- Average pitch delta: {metric(summary['pitchDeltaPctAvg'])}%.",
        f"- Average mean corner error: {metric(summary['meanCornerErrorSquaresAvg'])} squares.",
        "",
        "| Source | Pitch px col/row | Angle delta col/row | Visible cells vs label | Corner err sq | Segments | Note |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for result in report["results"]:
        if not result.get("detected"):
            lines.append(
                f"| {result.get('sourceId', '-')} | - | - | - | - | - | {result.get('errorMessage', 'failed')} |",
            )
            continue
        families = {family["role"]: family for family in result.get("families", [])}
        columns = families.get("columns", {})
        rows = families.get("rows", {})
        pitch = (
            f"{metric(columns.get('pitchPxOriginal'))}/{metric(rows.get('pitchPxOriginal'))} "
            f"(exp {metric(columns.get('expectedPitchPxOriginal'))}/{metric(rows.get('expectedPitchPxOriginal'))})"
        )
        angle = f"{metric(columns.get('angleDeltaDeg'))}/{metric(rows.get('angleDeltaDeg'))}"
        counts = (
            f"{metric(result.get('candidateColumns'))}x{metric(result.get('candidateRows'))} "
            f"vs {result.get('expectedColumns')}x{result.get('expectedRows')}"
        )
        corner_error = (
            f"{metric(result.get('meanCornerErrorSquares'))}/"
            f"{metric(result.get('maxCornerErrorSquares'))}"
        )
        note = compact_note(result, columns, rows)
        lines.append(
            "| "
            + " | ".join(
                [
                    str(result["sourceId"]),
                    pitch,
                    angle,
                    counts,
                    corner_error,
                    str(result.get("segmentCount", "-")),
                    note,
                ],
            )
            + " |",
        )
    return "\n".join(lines)


def compact_note(result: dict[str, Any], columns: dict[str, Any], rows: dict[str, Any]) -> str:
    count_delta = result.get("countDelta") or {}
    return (
        f"period score {metric(columns.get('periodScore'))}/{metric(rows.get('periodScore'))}; "
        f"count delta {metric(count_delta.get('columns'))}/{metric(count_delta.get('rows'))}"
    )


def intersect_normal_lines(n1: np.ndarray, rho1: float, n2: np.ndarray, rho2: float) -> np.ndarray | None:
    matrix = np.array([[float(n1[0]), float(n1[1])], [float(n2[0]), float(n2[1])]], dtype=np.float64)
    rhs = np.array([rho1, rho2], dtype=np.float64)
    determinant = float(np.linalg.det(matrix))
    if abs(determinant) < 1e-6:
        return None
    return np.linalg.solve(matrix, rhs).astype(np.float32)


def best_corner_deltas(candidate: np.ndarray, truth: np.ndarray) -> np.ndarray:
    candidate = np.float32(candidate).reshape(4, 2)
    truth = np.float32(truth).reshape(4, 2)
    variants = []
    for shift in range(4):
        rolled = np.roll(candidate, shift, axis=0)
        variants.append(np.linalg.norm(rolled - truth, axis=1))
        variants.append(np.linalg.norm(rolled[::-1] - truth, axis=1))
    return min(variants, key=lambda deltas: float(deltas.mean()))


def average_truth_square_pixels(label: dict[str, Any]) -> float:
    corners = np.float32([[point["x"], point["y"]] for point in label["corners"]])
    top_left, top_right, bottom_right, bottom_left = corners
    horizontal = (
        float(np.linalg.norm(top_right - top_left)) + float(np.linalg.norm(bottom_right - bottom_left))
    ) / max(1, int(label["columns"]) * 2)
    vertical = (
        float(np.linalg.norm(bottom_left - top_left)) + float(np.linalg.norm(bottom_right - top_right))
    ) / max(1, int(label["rows"]) * 2)
    return (horizontal + vertical) / 2


def order_corners(points: np.ndarray) -> np.ndarray:
    pts = np.float32(points).reshape(-1, 2)
    center = pts.mean(axis=0)
    angles = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])
    ordered = pts[np.argsort(angles)]
    start = int(np.argmin(ordered.sum(axis=1)))
    return np.concatenate([ordered[start:], ordered[:start]]).astype(np.float32)


def periodic_residual(values: np.ndarray, phase: float, pitch: float) -> np.ndarray:
    return np.abs((values - phase + pitch / 2) % pitch - pitch / 2)


def weighted_average(values: list[float], weights: list[float]) -> float:
    total_weight = sum(weights)
    if total_weight <= 0:
        return float(sum(values) / max(1, len(values)))
    return float(sum(value * weight for value, weight in zip(values, weights)) / total_weight)


def axial_angle_delta(a: float, b: float) -> float:
    delta = abs((a - b) % 180)
    return min(delta, 180 - delta)


def segment_angle(start: np.ndarray, end: np.ndarray) -> float:
    return normalize_angle_deg(math.degrees(math.atan2(float(end[1] - start[1]), float(end[0] - start[0]))))


def axial_mean_degrees(angles: list[float]) -> float:
    radians = [math.radians(angle) for angle in angles]
    sin_sum = sum(math.sin(angle * 2) for angle in radians)
    cos_sum = sum(math.cos(angle * 2) for angle in radians)
    return normalize_angle_deg(math.degrees(math.atan2(sin_sum, cos_sum) / 2))


def normalize_angle_deg(angle: float) -> float:
    return angle % 180


def round_metric(value: float) -> float:
    return round(float(value) * 100) / 100


def metric(value: Any) -> str:
    return "-" if value is None else str(value)


if __name__ == "__main__":
    sys.exit(main())
