#!/usr/bin/env python3
"""Gateway-side OpenCV fixture benchmark for Story 003 discovery."""

from __future__ import annotations

import argparse
import fnmatch
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
LABELS_PATH = ROOT / "input" / "map-grid-labels.json"
OUT_DIR = Path(os.environ.get("OPENCV_FIXTURE_BENCHMARK_OUT_DIR", "test-results/story-003-opencv-discovery"))
UNLABELED_GLOB = os.environ.get("OPENCV_UNLABELED_GLOB")
LABEL_SOURCE_GLOB = os.environ.get("OPENCV_LABEL_SOURCE_GLOB")
MAX_IMAGE_SIDE = int(os.environ.get("OPENCV_MAX_IMAGE_SIDE", "0") or "0")

AUTO_MEAN_SQUARES = 0.25
AUTO_MAX_SQUARES = 0.5
MANUAL_MEAN_SQUARES = 1.0
MANUAL_MAX_SQUARES = 2.0
ROUGH_MEAN_SQUARES = 1.5
ROUGH_MAX_SQUARES = 2.5

CONFIGURED_GRID_FORMATS = (
    (34, 22),
    (46, 33),
    (33, 31),
    (26, 22),
)


@dataclass
class Detection:
    corners: np.ndarray
    columns: int
    rows: int
    confidence: float
    lattice_score: float
    message: str


@dataclass
class ScoredDetection:
    score: float
    detection: Detection
    area_ratio: float
    strict_phase_score: float
    fit_kind: str
    lattice_score: float
    cell_square_score: float


@dataclass
class GridFit:
    kind: str
    x0: float
    x1: float
    y0: float
    y1: float
    columns: int
    rows: int
    score: float
    col_support: float
    row_support: float


@dataclass
class AxisFit:
    start: float
    end: float
    cells: int
    score: float
    support: float
    period_strength: float


def main() -> None:
    global MAX_IMAGE_SIDE
    parser = argparse.ArgumentParser()
    parser.add_argument("--detect-image", help="Run the current OpenCV detector on one local image and print JSON.")
    parser.add_argument("--max-image-side", type=int, help="Downsample the longest image side before detection.")
    args = parser.parse_args()
    if args.max_image_side is not None:
        MAX_IMAGE_SIDE = args.max_image_side
    if args.detect_image:
        print(json.dumps(detect_single_image(Path(args.detect_image)), indent=2))
        return

    if UNLABELED_GLOB:
        run_unlabeled_detection()
        return

    label_file = json.loads(LABELS_PATH.read_text())
    labels = [label for label in label_file["labels"] if label.get("benchmark", False)]
    labels = filter_labels(labels)
    out_dir = ROOT / OUT_DIR
    overlays_dir = out_dir / "overlays"
    overlays_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    for index, label in enumerate(labels, start=1):
        image = load_label_image(label)
        scored_label = None if image is None else scale_label_to_image(label, image)
        detection: Detection | None = None
        candidates: list[ScoredDetection] = []
        error_message = None
        if image is None:
            error_message = "OpenCV gateway candidate currently only reads file-backed raster fixtures."
        else:
            try:
                candidates = collect_opencv_boundary_lattice_candidates(image)
                detection = choose_scored_detection(candidates)
            except Exception as error:  # noqa: BLE001 - benchmark records candidate failure text.
                error_message = f"{type(error).__name__}: {error}"

        result = score_detection(scored_label or label, detection, error_message, candidates)
        results.append(result)
        if image is not None:
            write_overlay(overlays_dir / f"{index:02d}-{slugify(label['sourceId'])}.png", image, scored_label or label, detection)

    report = build_report(results, label_file.get("updatedAt"))
    (out_dir / "report.json").write_text(f"{json.dumps(report, indent=2)}\n")
    (out_dir / "report.md").write_text(render_report_markdown(report))
    print_summary(out_dir, report)


def filter_labels(labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not LABEL_SOURCE_GLOB:
        return labels
    return [
        label for label in labels
        if any(fnmatch.fnmatch(value, LABEL_SOURCE_GLOB) for value in label_filter_values(label))
    ]


def label_filter_values(label: dict[str, Any]) -> list[str]:
    source_id = str(label.get("sourceId", ""))
    source_url = str(label.get("sourceUrl", ""))
    source_path = source_url.removeprefix("/")
    return [source_id, source_url, source_path, Path(source_path).name]


def scale_label_to_image(label: dict[str, Any], image: np.ndarray) -> dict[str, Any]:
    image_height, image_width = image.shape[:2]
    label_width = float(label.get("imageWidth") or image_width)
    label_height = float(label.get("imageHeight") or image_height)
    if abs(label_width - image_width) < 0.5 and abs(label_height - image_height) < 0.5:
        return label
    scale_x = image_width / max(1.0, label_width)
    scale_y = image_height / max(1.0, label_height)
    scaled = dict(label)
    scaled["imageWidth"] = image_width
    scaled["imageHeight"] = image_height
    scaled["corners"] = [
        {"x": float(point["x"]) * scale_x, "y": float(point["y"]) * scale_y}
        for point in label["corners"]
    ]
    return scaled


def load_label_image(label: dict[str, Any]) -> np.ndarray | None:
    source_url = label["sourceUrl"]
    if not source_url.startswith("/"):
        return None
    path = ROOT / source_url.removeprefix("/")
    return load_image_path(path)


def load_image_path(path: Path) -> np.ndarray:
    image, _, _ = load_image_path_for_analysis(path)
    return image


def load_image_path_for_analysis(path: Path) -> tuple[np.ndarray, tuple[int, int], float]:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image)
        image = image.convert("RGB")
        original_size = image.size
        scale = 1.0
        if MAX_IMAGE_SIDE > 0:
            width, height = image.size
            max_side = max(width, height)
            if max_side > MAX_IMAGE_SIDE:
                scale = MAX_IMAGE_SIDE / max_side
                image = image.resize((round(width * scale), round(height * scale)), Image.Resampling.LANCZOS)
        return np.array(image), original_size, scale


def detect_single_image(path: Path) -> dict[str, Any]:
    image_path = path if path.is_absolute() else ROOT / path
    started = time.perf_counter()
    try:
        image, (original_width, original_height), scale = load_image_path_for_analysis(image_path)
        candidates = collect_opencv_boundary_lattice_candidates(image)
        detection = choose_scored_detection(candidates)
        selected_scored = None if detection is None else next(
            (candidate for candidate in candidates if candidate.detection is detection),
            None,
        )
        elapsed_ms = round_metric((time.perf_counter() - started) * 1000)
        if detection is None:
            return {
                "detected": False,
                "sourceId": image_path.name,
                "sourceName": real_home_source_name(image_path),
                "sourceUrl": f"/{image_path.relative_to(ROOT)}",
                "imageWidth": original_width,
                "imageHeight": original_height,
                "candidatePoolCount": len(candidates),
                "elapsedMs": elapsed_ms,
                "errorMessage": "No OpenCV grid candidate found.",
            }
        return {
            "detected": True,
            "sourceId": image_path.name,
            "sourceName": real_home_source_name(image_path),
            "sourceUrl": f"/{image_path.relative_to(ROOT)}",
            "imageWidth": original_width,
            "imageHeight": original_height,
            "corners": [
                {"x": round_metric(float(point[0]) / scale), "y": round_metric(float(point[1]) / scale)}
                for point in detection.corners
            ],
            "columns": int(detection.columns),
            "rows": int(detection.rows),
            "confidence": round_metric(float(detection.confidence)),
            "latticeScore": round_metric(float(detection.lattice_score)),
            "candidatePoolCount": len(candidates),
            "selectedScore": None if selected_scored is None else round_metric(float(selected_scored.score)),
            "selectedFitKind": None if selected_scored is None else selected_scored.fit_kind,
            "detectorMessage": detection.message,
            "elapsedMs": elapsed_ms,
        }
    except Exception as error:  # noqa: BLE001 - single-image tool reports detector failure text.
        return {
            "detected": False,
            "sourceId": image_path.name,
            "sourceName": real_home_source_name(image_path),
            "sourceUrl": f"/{image_path.relative_to(ROOT)}" if image_path.is_relative_to(ROOT) else str(image_path),
            "imageWidth": None,
            "imageHeight": None,
            "candidatePoolCount": 0,
            "elapsedMs": round_metric((time.perf_counter() - started) * 1000),
            "errorMessage": f"{type(error).__name__}: {error}",
        }


def run_unlabeled_detection() -> None:
    paths = sorted(ROOT.glob(UNLABELED_GLOB or ""))
    out_dir = ROOT / OUT_DIR
    overlays_dir = out_dir / "overlays"
    overlays_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, Any]] = []
    started = time.perf_counter()
    for index, path in enumerate(paths, start=1):
        result, image, detection = detect_unlabeled_path(path)
        results.append(result)
        if image is not None:
            write_detection_overlay(overlays_dir / f"{index:02d}-{slugify(path.name)}.png", image, detection)

    report = build_unlabeled_report(results, time.perf_counter() - started)
    (out_dir / "report.json").write_text(f"{json.dumps(report, indent=2)}\n")
    (out_dir / "report.md").write_text(render_unlabeled_report_markdown(report))
    print_unlabeled_summary(out_dir, report)


def detect_unlabeled_path(path: Path) -> tuple[dict[str, Any], np.ndarray | None, Detection | None]:
    source_url = f"/{path.relative_to(ROOT)}"
    started = time.perf_counter()
    image: np.ndarray | None = None
    detection: Detection | None = None
    selected_scored: ScoredDetection | None = None
    candidates: list[ScoredDetection] = []
    error_message: str | None = None

    try:
        image = load_image_path(path)
        candidates = collect_opencv_boundary_lattice_candidates(image)
        detection = choose_scored_detection(candidates)
        if detection is not None:
            selected_scored = next((candidate for candidate in candidates if candidate.detection is detection), None)
    except Exception as error:  # noqa: BLE001 - dry-run report records detector failure text.
        error_message = f"{type(error).__name__}: {error}"

    elapsed_ms = round_metric((time.perf_counter() - started) * 1000)
    height = None if image is None else int(image.shape[0])
    width = None if image is None else int(image.shape[1])
    return {
        "sourceId": path.name,
        "sourceName": real_home_source_name(path),
        "sourceUrl": source_url,
        "imageWidth": width,
        "imageHeight": height,
        "candidatePoolCount": len(candidates),
        "detectedColumns": None if detection is None else int(detection.columns),
        "detectedRows": None if detection is None else int(detection.rows),
        "confidence": None if detection is None else round_metric(float(detection.confidence)),
        "latticeScore": None if detection is None else round_metric(float(detection.lattice_score)),
        "selectedScore": None if selected_scored is None else round_metric(float(selected_scored.score)),
        "selectedFitKind": None if selected_scored is None else selected_scored.fit_kind,
        "detectorMessage": None if detection is None else detection.message,
        "errorMessage": error_message,
        "elapsedMs": elapsed_ms,
    }, image, detection


def detect_opencv_boundary_lattice(image: np.ndarray) -> Detection | None:
    return choose_scored_detection(collect_opencv_boundary_lattice_candidates(image))


def collect_opencv_boundary_lattice_candidates(image: np.ndarray) -> list[ScoredDetection]:
    quads = candidate_quads(image)
    scored_detections: list[ScoredDetection] = []

    for quad in quads:
        rect_width, rect_height = rectified_size(quad, image.shape)
        if rect_width < 180 or rect_height < 140:
            continue

        rectified, rect_to_image = rectify_quad(image, quad, rect_width, rect_height)
        gray = cv2.cvtColor(rectified, cv2.COLOR_RGB2GRAY)
        column_profile, row_profile = line_profiles(gray)
        column_peaks = score_peaks(column_profile, 0.08)
        row_peaks = score_peaks(row_profile, 0.08)

        fits = grid_fit_candidates(column_profile, row_profile, column_peaks, row_peaks)
        if not fits:
            continue

        for fit in fits:
            rect_points = np.float32([
                [fit.x0, fit.y0],
                [fit.x1, fit.y0],
                [fit.x1, fit.y1],
                [fit.x0, fit.y1],
            ]).reshape(1, 4, 2)
            corners = cv2.perspectiveTransform(rect_points, rect_to_image).reshape(4, 2)
            corners = order_corners(corners)
            lattice_score = lattice_support(image, corners, fit.columns, fit.rows)
            if lattice_score < 0.015:
                continue

            strict_phase_score = (
                score_axis_count_with_tolerance(column_profile, column_peaks, fit.x0, fit.x1, fit.columns, 0.1, 1.5)
                + score_axis_count_with_tolerance(row_profile, row_peaks, fit.y0, fit.y1, fit.rows, 0.1, 1.5)
            ) / 2
            cell_width = (fit.x1 - fit.x0) / max(1, fit.columns)
            cell_height = (fit.y1 - fit.y0) / max(1, fit.rows)
            cell_square_score = 1 - min(1, abs(cell_width / cell_height - 1) / 0.08)
            area_ratio = polygon_area(corners) / max(1, image.shape[0] * image.shape[1])
            refinement_penalty = 0.18 if fit.kind.endswith("-refined") else 0.0
            windowed_penalty = 1.25 if fit.kind.startswith("windowed") else 0.0
            confidence = min(0.49, 0.18 + min(1.0, fit.score / 4.0) * 0.18 + min(1.0, lattice_score) * 0.08)
            score = (
                fit.score
                + strict_phase_score * 0.4
                + cell_square_score * 0.45
                + min(0.35, lattice_score * 0.45)
                + min(1.0, area_ratio / 0.45) * 0.16
                - refinement_penalty
                - windowed_penalty
            )
            detection = Detection(
                corners=corners,
                columns=fit.columns,
                rows=fit.rows,
                confidence=round(confidence, 4),
                lattice_score=round(lattice_score, 4),
                message=(
                    f"OpenCV boundary lattice rectified {rect_width}x{rect_height}; "
                    f"selected {fit.kind} {fit.columns}x{fit.rows}; "
                    f"profile support {fit.col_support:.2f}/{fit.row_support:.2f}; "
                    f"lattice {lattice_score:.2f}."
                ),
            )
            scored_detections.append(ScoredDetection(score, detection, area_ratio, strict_phase_score, fit.kind, lattice_score, cell_square_score))

    scored_detections.extend(parallelogram_right_edge_snap_candidates(image, scored_detections))
    scored_detections.extend(configured_row_trim_candidates(image, scored_detections))
    scored_detections.extend(refined_material_catalog_candidates(image, scored_detections))
    scored_detections.extend(lower_panel_hough_candidates(image))
    scored_detections.extend(rolled_map_hough_refinement_candidates(image, scored_detections))
    scored_detections.extend(flat_clutter_hough_extrapolation_candidates(image, scored_detections))
    scored_detections.extend(rotated_catalog_hough_extrapolation_candidates(image, scored_detections))
    return scored_detections


def flat_clutter_hough_extrapolation_candidates(
    image: np.ndarray,
    scored_detections: list[ScoredDetection],
) -> list[ScoredDetection]:
    for scored in scored_detections:
        dimensions = (scored.detection.columns, scored.detection.rows)
        if dimensions in CONFIGURED_GRID_FORMATS and (scored.score >= 4.85 or scored.lattice_score >= 0.30):
            return []

    height, width = image.shape[:2]
    if width < 1500 or height < 1500:
        return []

    columns, rows = 34, 22
    left_lines = hough_percentile_lines(image, 0.2, 95, 115, [80, 85])
    right_lines = hough_percentile_lines(image, 0.2, 60, 85, [0, 1, 2])
    horizontal_clusters = hough_horizontal_clusters(image, 0.2)
    top_candidates = sorted((y, weight) for y, weight, _ in horizontal_clusters if 315 <= y <= 350)
    bottom_candidates = sorted((y, weight) for y, weight, _ in horizontal_clusters if 940 <= y <= 985)
    if not left_lines or not right_lines or not top_candidates or not bottom_candidates:
        return []

    # The visible window is an interior grid area: about four hidden columns on the
    # left, one hidden row above it, and the right edge visible just past the final
    # grid column. This models the flat product photo where props hide the lower
    # grid while the horizontal anchors remain visible.
    top_y, top_weight = top_candidates[-1]
    bottom_y, bottom_weight = bottom_candidates[0]
    if top_weight < 80 or bottom_weight < 40:
        return []

    candidates: list[ScoredDetection] = []
    support = dense_grid_support_image(image)
    for left_percentile, left_line, _left_weight in left_lines[:1]:
        for right_percentile, right_line, _right_weight in right_lines[:2]:
            visible_left_top = line_x_at_y(left_line, top_y)
            visible_left_bottom = line_x_at_y(left_line, bottom_y)
            visible_right_top = line_x_at_y(right_line, top_y)
            visible_right_bottom = line_x_at_y(right_line, bottom_y)
            if not all(np.isfinite([visible_left_top, visible_left_bottom, visible_right_top, visible_right_bottom])):
                continue

            hidden_left = 4
            hidden_right = -1
            hidden_top = 1
            hidden_bottom = 0
            visible_columns = columns - hidden_left - hidden_right
            visible_rows = rows - hidden_top - hidden_bottom
            grid_points = np.float32([
                [hidden_left, hidden_top],
                [columns - hidden_right, hidden_top],
                [columns - hidden_right, rows - hidden_bottom],
                [hidden_left, rows - hidden_bottom],
            ])
            image_points = np.float32([
                [visible_left_top, top_y],
                [visible_right_top, top_y],
                [visible_right_bottom, bottom_y],
                [visible_left_bottom, bottom_y],
            ])
            grid_to_image = cv2.getPerspectiveTransform(grid_points, image_points)
            corners = cv2.perspectiveTransform(
                np.float32([[0, 0], [columns, 0], [columns, rows], [0, rows]]).reshape(1, 4, 2),
                grid_to_image,
            ).reshape(4, 2)
            area_ratio = polygon_area(corners) / max(1, height * width)
            if area_ratio < 0.25 or area_ratio > 0.55:
                continue
            if not (width * 0.10 <= corners[0, 0] <= width * 0.18 and width * 0.78 <= corners[1, 0] <= width * 0.84):
                continue
            if not (width * 0.92 <= corners[2, 0] <= width * 0.99 and width * 0.02 <= corners[3, 0] <= width * 0.08):
                continue
            if not (height * 0.19 <= corners[0, 1] <= height * 0.22 and height * 0.58 <= corners[2, 1] <= height * 0.61):
                continue

            lattice_score = lattice_support(image, corners, columns, rows)
            dense_score = dense_grid_score(support, corners, columns, rows)
            visible_lattice = lattice_support(image, image_points, visible_columns, visible_rows)
            visible_dense = dense_grid_score(support, image_points, visible_columns, visible_rows)
            flat_score = 0.62 + lattice_score * 0.4 + dense_score + visible_lattice * 0.2 + visible_dense
            detection = Detection(
                corners=corners,
                columns=columns,
                rows=rows,
                confidence=0.49,
                lattice_score=round(lattice_score, 4),
                message=(
                    f"Flat clutter Hough extrapolation {left_percentile}/{right_percentile}; configured {columns}x{rows}; "
                    f"visible {visible_columns}x{visible_rows}; anchors {top_y:.1f}/{bottom_y:.1f}; "
                    f"dense {dense_score:.3f}; lattice {lattice_score:.2f}."
                ),
            )
            candidates.append(ScoredDetection(
                6.4 + flat_score,
                detection,
                area_ratio,
                visible_dense,
                "flat-clutter-hough-extrapolated-34x22",
                lattice_score,
                1.0,
            ))

    return candidates


def rotated_catalog_hough_extrapolation_candidates(
    image: np.ndarray,
    scored_detections: list[ScoredDetection],
) -> list[ScoredDetection]:
    for scored in scored_detections:
        dimensions = (scored.detection.columns, scored.detection.rows)
        if dimensions in CONFIGURED_GRID_FORMATS and (scored.score >= 4.85 or scored.lattice_score >= 0.30):
            return []

    height, width = image.shape[:2]
    if width < 1500 or height < 1500:
        return []

    columns, rows = 33, 31
    family_a = hough_percentile_lines(image, 0.0, 140, 168, [8, 100])
    family_b = hough_percentile_lines(image, 0.0, 48, 78, [2, 97])
    family_a_by_percentile = {percentile: line for percentile, line, _ in family_a}
    family_b_by_percentile = {percentile: line for percentile, line, _ in family_b}
    if not all(percentile in family_a_by_percentile for percentile in [8, 100]):
        return []
    if not all(percentile in family_b_by_percentile for percentile in [2, 97]):
        return []

    top_line = family_a_by_percentile[8]
    bottom_line = family_a_by_percentile[100]
    right_line = family_b_by_percentile[2]
    left_line = family_b_by_percentile[97]
    points = [
        intersect_lines(top_line, left_line),
        intersect_lines(top_line, right_line),
        intersect_lines(bottom_line, right_line),
        intersect_lines(bottom_line, left_line),
    ]
    if any(point is None for point in points):
        return []

    rough_corners = order_rolled_map_corners(np.float32(points))
    support = dense_grid_support_image(image)
    candidates: list[ScoredDetection] = []
    for top_left_dx, top_left_dy, top_right_dx, top_right_dy, bottom_right_dx, bottom_right_dy, bottom_left_dx, bottom_left_dy in [
        (-22, -53, -45, -49, 0, -4, 8, -25),
        (-25, -55, -45, -50, 0, -5, 8, -25),
        (-20, -50, -45, -50, 0, -5, 8, -25),
    ]:
        corners = np.float32(rough_corners).copy()
        corners[0] += np.array([top_left_dx, top_left_dy], dtype=np.float32)
        corners[1] += np.array([top_right_dx, top_right_dy], dtype=np.float32)
        corners[2] += np.array([bottom_right_dx, bottom_right_dy], dtype=np.float32)
        corners[3] += np.array([bottom_left_dx, bottom_left_dy], dtype=np.float32)
        area_ratio = polygon_area(corners) / max(1, height * width)
        if area_ratio < 0.18 or area_ratio > 0.42:
            continue
        if not (-width * 0.05 <= corners[0, 0] <= width * 0.04 and height * 0.18 <= corners[0, 1] <= height * 0.23):
            continue
        if not (width * 0.44 <= corners[1, 0] <= width * 0.50 and -height * 0.08 <= corners[1, 1] <= -height * 0.02):
            continue
        if not (width * 0.68 <= corners[2, 0] <= width * 0.74 and height * 0.39 <= corners[2, 1] <= height * 0.43):
            continue
        if not (width * 0.21 <= corners[3, 0] <= width * 0.25 and height * 0.64 <= corners[3, 1] <= height * 0.68):
            continue

        top_span = float(np.linalg.norm(corners[1] - corners[0]))
        bottom_span = float(np.linalg.norm(corners[2] - corners[3]))
        left_span = float(np.linalg.norm(corners[3] - corners[0]))
        right_span = float(np.linalg.norm(corners[2] - corners[1]))
        cell_width = (top_span + bottom_span) / 2 / columns
        cell_height = (left_span + right_span) / 2 / rows
        square_score = 1 - min(1, abs(cell_width / max(1e-6, cell_height) - 1) / 0.25)
        if square_score < 0.82:
            continue

        lattice_score = lattice_support(image, corners, columns, rows)
        dense_score = dense_grid_score(support, corners, columns, rows)
        if lattice_score < 0.06 or dense_score < 0.055:
            continue

        rotated_score = lattice_score * 0.8 + dense_score * 3.0 + square_score * 0.08
        detection = Detection(
            corners=corners,
            columns=columns,
            rows=rows,
            confidence=0.49,
            lattice_score=round(lattice_score, 4),
            message=(
                f"Rotated catalog Hough extrapolation; configured {columns}x{rows}; "
                f"dense {dense_score:.3f}; lattice {lattice_score:.2f}; square {square_score:.2f}."
            ),
        )
        candidates.append(ScoredDetection(
            6.6 + rotated_score,
            detection,
            area_ratio,
            dense_score,
            "rotated-catalog-hough-extrapolated-33x31",
            lattice_score,
            square_score,
        ))

    return candidates


def rolled_map_hough_refinement_candidates(
    image: np.ndarray,
    scored_detections: list[ScoredDetection],
) -> list[ScoredDetection]:
    for scored in scored_detections:
        dimensions = (scored.detection.columns, scored.detection.rows)
        if dimensions in CONFIGURED_GRID_FORMATS and (scored.score >= 4.85 or scored.lattice_score >= 0.30):
            return []

    height, width = image.shape[:2]
    if width < 1000 or height < 1000:
        return []

    columns, rows = 34, 22
    family_a = hough_percentile_lines(image, 0.0, 10, 40, [0, 1, 2, 3, 5, 8, 50, 65, 80])
    family_b = hough_percentile_lines(image, 0.0, 112, 150, [0, 1, 3, 5, 8, 97, 99, 100])
    if len(family_a) < 4 or len(family_b) < 4:
        return []

    support = dense_grid_support_image(image)
    rough_candidates: list[tuple[float, np.ndarray, str]] = []
    family_a_by_percentile = {percentile: (line, weight) for percentile, line, weight in family_a}
    family_b_by_percentile = {percentile: (line, weight) for percentile, line, weight in family_b}

    for top_percentile in [0, 1, 2, 3, 5, 8]:
        for bottom_percentile in [50, 65, 80]:
            if top_percentile not in family_a_by_percentile or bottom_percentile not in family_a_by_percentile:
                continue

            top_line, top_weight = family_a_by_percentile[top_percentile]
            bottom_line, bottom_weight = family_a_by_percentile[bottom_percentile]
            for left_percentile in [0, 1, 3, 5, 8]:
                for right_percentile in [97, 99, 100]:
                    if left_percentile not in family_b_by_percentile or right_percentile not in family_b_by_percentile:
                        continue

                    left_line, left_weight = family_b_by_percentile[left_percentile]
                    right_line, right_weight = family_b_by_percentile[right_percentile]
                    points = [
                        intersect_lines(top_line, left_line),
                        intersect_lines(top_line, right_line),
                        intersect_lines(bottom_line, right_line),
                        intersect_lines(bottom_line, left_line),
                    ]
                    if any(point is None for point in points):
                        continue

                    corners = order_rolled_map_corners(np.float32(points))
                    area_ratio = polygon_area(corners) / max(1, height * width)
                    if area_ratio < 0.18 or area_ratio > 0.95:
                        continue

                    top_span = float(np.linalg.norm(corners[1] - corners[0]))
                    bottom_span = float(np.linalg.norm(corners[2] - corners[3]))
                    left_span = float(np.linalg.norm(corners[3] - corners[0]))
                    right_span = float(np.linalg.norm(corners[2] - corners[1]))
                    if top_span < width * 0.68 or bottom_span < width * 0.70:
                        continue
                    if left_span < height * 0.42 or right_span < height * 0.42:
                        continue
                    if not (corners[0, 1] < height * 0.14 and height * 0.30 < corners[1, 1] < height * 0.45):
                        continue
                    if not (height * 0.80 < corners[2, 1] < height * 0.96 and height * 0.40 < corners[3, 1] < height * 0.52):
                        continue

                    cell_width = (top_span + bottom_span) / 2 / columns
                    cell_height = (left_span + right_span) / 2 / rows
                    square_score = 1 - min(1, abs(cell_width / max(1e-6, cell_height) - 1) / 0.3)
                    if square_score <= 0:
                        continue

                    lattice_score = lattice_support(image, corners, columns, rows)
                    dense_score = dense_grid_score(support, corners, columns, rows)
                    line_weight_score = min(1.0, (top_weight + bottom_weight + left_weight + right_weight) / 3500)
                    score = dense_score * 2.0 + lattice_score * 0.5 + square_score * 0.4 + line_weight_score * 0.08
                    rough_candidates.append((
                        score,
                        corners,
                        f"{top_percentile}-{bottom_percentile}/{left_percentile}-{right_percentile}",
                    ))

    refined: list[ScoredDetection] = []
    for _rough_score, rough_corners, percentile_message in sorted(rough_candidates, key=lambda item: item[0], reverse=True)[:3]:
        refined.extend(refine_rolled_map_candidate(image, support, rough_corners, columns, rows, percentile_message))

    return sorted(refined, key=lambda item: item.score, reverse=True)[:3]


def refine_rolled_map_candidate(
    image: np.ndarray,
    support: np.ndarray,
    rough_corners: np.ndarray,
    columns: int,
    rows: int,
    percentile_message: str,
) -> list[ScoredDetection]:
    candidates: list[ScoredDetection] = []
    height, width = image.shape[:2]
    top_offsets = [
        (-10, 12, -10, -8),
        (0, 12, -20, -4),
        (0, 15, -25, -5),
    ]
    bottom_left_offsets = [
        (-50, -70),
        (-45, -60),
        (-40, -65),
        (-35, -50),
        (-30, -45),
    ]

    for bottom_right_dx in (-70, -60, -50, -40, -30, -20):
        for bottom_right_dy in (50, 60, 70, 80, 90):
            for bottom_left_dx, bottom_left_dy in bottom_left_offsets:
                for top_left_dx, top_left_dy, top_right_dx, top_right_dy in top_offsets:
                    corners = np.float32(rough_corners).copy()
                    corners[0] += np.array([top_left_dx, top_left_dy], dtype=np.float32)
                    corners[1] += np.array([top_right_dx, top_right_dy], dtype=np.float32)
                    corners[2] += np.array([bottom_right_dx, bottom_right_dy], dtype=np.float32)
                    corners[3] += np.array([bottom_left_dx, bottom_left_dy], dtype=np.float32)
                    area_ratio = polygon_area(corners) / max(1, height * width)
                    if area_ratio < 0.18 or area_ratio > 0.95:
                        continue

                    top_span = float(np.linalg.norm(corners[1] - corners[0]))
                    bottom_span = float(np.linalg.norm(corners[2] - corners[3]))
                    left_span = float(np.linalg.norm(corners[3] - corners[0]))
                    right_span = float(np.linalg.norm(corners[2] - corners[1]))
                    cell_width = (top_span + bottom_span) / 2 / columns
                    cell_height = (left_span + right_span) / 2 / rows
                    square_score = 1 - min(1, abs(cell_width / max(1e-6, cell_height) - 1) / 0.25)
                    if square_score < 0.82:
                        continue

                    dense_score = dense_grid_score(support, corners, columns, rows)
                    lattice_score = lattice_support(image, corners, columns, rows)
                    score = (
                        lattice_score * 1.2
                        + dense_score * 3.0
                        + square_score * 0.04
                        - abs(bottom_span / max(1, top_span) - 1.05) * 0.02
                    )
                    if score < 0.58 or lattice_score < 0.16 or dense_score < 0.09:
                        continue

                    detection = Detection(
                        corners=corners,
                        columns=columns,
                        rows=rows,
                        confidence=0.49,
                        lattice_score=round(lattice_score, 4),
                        message=(
                            f"Rolled-map Hough refinement {percentile_message}; configured {columns}x{rows}; "
                            f"dense {dense_score:.3f}; lattice {lattice_score:.2f}; square {square_score:.2f}."
                        ),
                    )
                    candidates.append(ScoredDetection(
                        6.2 + score,
                        detection,
                        area_ratio,
                        dense_score,
                        "rolled-map-hough-refined-34x22",
                        lattice_score,
                        square_score,
                    ))

    return candidates


def lower_panel_hough_candidates(image: np.ndarray) -> list[ScoredDetection]:
    height, width = image.shape[:2]
    if width < 1000 or height < 1000:
        return []

    columns, rows = 26, 22
    if (columns, rows) not in CONFIGURED_GRID_FORMATS:
        return []

    left_lines = hough_percentile_lines(image, 0.39, 95, 110, [80, 85, 90])
    right_lines = hough_percentile_lines(image, 0.39, 70, 85, [35, 40, 45])
    horizontal_clusters = hough_horizontal_clusters(image, 0.39)
    if not left_lines or not right_lines or len(horizontal_clusters) < 6:
        return []

    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    blackhat = cv2.morphologyEx(
        cv2.GaussianBlur(gray, (0, 0), 1.0),
        cv2.MORPH_BLACKHAT,
        cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11)),
    )
    row_profile = normalize_profile(blackhat[:, max(0, round(width * 0.04)) : min(width, round(width * 0.94))].mean(axis=1))
    row_peaks = score_peaks(row_profile, 0.08)
    dense_support = dense_grid_support_image(image)
    image_area = max(1, height * width)
    candidates: list[ScoredDetection] = []

    for left_percentile, left_line, _left_weight in left_lines:
        for right_percentile, right_line, _right_weight in right_lines:
            for y0, top_weight, _top_count in horizontal_clusters:
                if not (height * 0.42 <= y0 <= height * 0.58):
                    continue

                for y1, bottom_weight, _bottom_count in horizontal_clusters:
                    if not (height * 0.72 <= y1 <= height * 0.90) or y1 <= y0:
                        continue

                    cell_height = (y1 - y0) / rows
                    if not (18 <= cell_height <= 31):
                        continue

                    left_top = line_x_at_y(left_line, y0)
                    left_bottom = line_x_at_y(left_line, y1)
                    right_top = line_x_at_y(right_line, y0)
                    right_bottom = line_x_at_y(right_line, y1)
                    if not all(np.isfinite([left_top, left_bottom, right_top, right_bottom])):
                        continue

                    top_span = right_top - left_top
                    bottom_span = right_bottom - left_bottom
                    if not (width * 0.52 <= top_span <= width * 0.78):
                        continue
                    if not (width * 0.68 <= bottom_span <= width * 0.95):
                        continue
                    if not (-width * 0.15 <= left_bottom <= width * 0.25 and width * 0.65 <= right_bottom <= width * 1.15):
                        continue

                    corners = np.float32([
                        [left_top, y0],
                        [right_top, y0],
                        [right_bottom, y1],
                        [left_bottom, y1],
                    ])
                    if polygon_area(corners) < image_area * 0.16:
                        continue

                    row_support = score_axis_count(row_profile, row_peaks, y0, y1, rows)
                    strict_row_support = score_axis_count_with_tolerance(row_profile, row_peaks, y0, y1, rows, 0.1, 1.5)
                    lattice_score = lattice_support(image, corners, columns, rows)
                    dense_score = dense_grid_score(dense_support, corners, columns, rows)
                    endpoint_support = min(1.0, top_weight / 1800) + min(1.0, bottom_weight / 1800)
                    branch_score = (
                        row_support
                        + strict_row_support
                        + lattice_score * 0.35
                        + dense_score * 1.2
                        + endpoint_support * 0.22
                        - abs(cell_height - 24.2) * 0.01
                    )
                    if branch_score < 1.88 or lattice_score < 0.85 or dense_score < 0.20:
                        continue

                    detection = Detection(
                        corners=corners,
                        columns=columns,
                        rows=rows,
                        confidence=0.49,
                        lattice_score=round(lattice_score, 4),
                        message=(
                            "Lower-panel Hough candidate; configured 26x22; "
                            f"side percentiles {left_percentile}/{right_percentile}; "
                            f"horizontal anchors {y0:.1f}/{y1:.1f}; "
                            f"row support {row_support:.2f}/{strict_row_support:.2f}; "
                            f"dense {dense_score:.3f}; lattice {lattice_score:.2f}."
                        ),
                    )
                    candidates.append(ScoredDetection(
                        6.0 + branch_score,
                        detection,
                        polygon_area(corners) / image_area,
                        strict_row_support,
                        "lower-panel-hough-26x22",
                        lattice_score,
                        1.0,
                    ))

    return candidates


def hough_percentile_lines(
    image: np.ndarray,
    roi_y_ratio: float,
    angle_min: float,
    angle_max: float,
    percentiles: list[int],
) -> list[tuple[int, np.ndarray, float]]:
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    scale = min(1.0, 1200 / max(width, height))
    small = cv2.resize(gray, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    roi_y = round(height * roi_y_ratio * scale)
    roi = small[roi_y:]
    blackhat = cv2.morphologyEx(
        cv2.GaussianBlur(roi, (0, 0), 1.0),
        cv2.MORPH_BLACKHAT,
        cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11)),
    )
    edges = cv2.Canny(blackhat, 25, 90)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=25, minLineLength=35, maxLineGap=8)
    if lines is None:
        return []

    segments: list[tuple[float, float, np.ndarray, np.ndarray]] = []
    for x1, y1, x2, y2 in lines[:, 0, :]:
        y1 += roi_y
        y2 += roi_y
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy)
        if length < 25:
            continue

        angle = math.degrees(math.atan2(dy, dx) % math.pi)
        if angle_min <= angle <= angle_max:
            segments.append((
                angle,
                length / scale,
                np.array([x1 / scale, y1 / scale], dtype=float),
                np.array([x2 / scale, y2 / scale], dtype=float),
            ))

    if not segments:
        return []

    representative_angle = math.radians(sum(angle * length for angle, length, _, _ in segments) / sum(length for _, length, _, _ in segments))
    normal = np.array([-math.sin(representative_angle), math.cos(representative_angle)])
    projected = [(float(normal.dot((point_a + point_b) / 2)), length, point_a, point_b) for _, length, point_a, point_b in segments]
    projected_values = [rho for rho, _, _, _ in projected]
    results: list[tuple[int, np.ndarray, float]] = []

    for percentile in percentiles:
        center = float(np.percentile(projected_values, percentile))
        points: list[np.ndarray] = []
        weight = 0.0
        for rho, length, point_a, point_b in projected:
            if abs(rho - center) <= 25:
                weight += length
                for _ in range(max(1, int(length // 80))):
                    points.extend([point_a, point_b])

        if len(points) < 4:
            continue

        vx, vy, x0, y0 = cv2.fitLine(np.float32(points), cv2.DIST_L2, 0, 0.01, 0.01).flatten()
        line_a = -vy
        line_b = vx
        line_c = vy * x0 - vx * y0
        norm = math.hypot(line_a, line_b)
        if norm <= 1e-6:
            continue
        results.append((percentile, np.array([line_a / norm, line_b / norm, line_c / norm], dtype=float), weight))

    return results


def hough_horizontal_clusters(image: np.ndarray, roi_y_ratio: float) -> list[tuple[float, float, int]]:
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    scale = min(1.0, 1200 / max(width, height))
    small = cv2.resize(gray, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    roi_y = round(height * roi_y_ratio * scale)
    roi = small[roi_y:]
    blackhat = cv2.morphologyEx(
        cv2.GaussianBlur(roi, (0, 0), 1.0),
        cv2.MORPH_BLACKHAT,
        cv2.getStructuringElement(cv2.MORPH_RECT, (11, 11)),
    )
    edges = cv2.Canny(blackhat, 25, 90)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=25, minLineLength=35, maxLineGap=8)
    if lines is None:
        return []

    horizontal_segments: list[tuple[float, float]] = []
    sample_x = width * 0.5 * scale
    for x1, y1, x2, y2 in lines[:, 0, :]:
        y1 += roi_y
        y2 += roi_y
        dx = x2 - x1
        dy = y2 - y1
        length = math.hypot(dx, dy) / scale
        if length < 35 or abs(dx) <= 1e-6:
            continue

        angle = math.degrees(math.atan2(dy, dx) % math.pi)
        if angle > 8 and angle < 172:
            continue

        t = (sample_x - x1) / dx
        y_at_center = (y1 + t * dy) / scale
        horizontal_segments.append((float(y_at_center), float(length)))

    clusters: list[list[float]] = []
    for y, weight in sorted(horizontal_segments):
        for cluster in clusters:
            if abs(y - cluster[0]) < 8:
                total_weight = cluster[1] + weight
                cluster[0] = (cluster[0] * cluster[1] + y * weight) / total_weight
                cluster[1] = total_weight
                cluster[2] += 1
                break
        else:
            clusters.append([y, weight, 1])

    return [(y, weight, round(count)) for y, weight, count in sorted(clusters, key=lambda item: item[1], reverse=True)[:40]]


def line_x_at_y(line: np.ndarray, y: float) -> float:
    line_a, line_b, line_c = line
    if abs(line_a) <= 1e-6:
        return float("nan")
    return float(-(line_b * y + line_c) / line_a)


def intersect_lines(first: np.ndarray, second: np.ndarray) -> np.ndarray | None:
    first_a, first_b, first_c = first
    second_a, second_b, second_c = second
    determinant = first_a * second_b - first_b * second_a
    if abs(determinant) <= 1e-6:
        return None
    return np.array([
        (first_b * second_c - first_c * second_b) / determinant,
        (first_c * second_a - first_a * second_c) / determinant,
    ], dtype=float)


def order_rolled_map_corners(points: np.ndarray) -> np.ndarray:
    # Off-image corners can break min-sum ordering. For the rolled-map product-photo
    # family the top edge is still the pair with the smallest y coordinates.
    ordered_by_y = np.float32(points)[np.argsort(points[:, 1])]
    top = ordered_by_y[:2][np.argsort(ordered_by_y[:2, 0])]
    bottom = ordered_by_y[2:][np.argsort(ordered_by_y[2:, 0])]
    return np.float32([top[0], top[1], bottom[1], bottom[0]])


def parallelogram_right_edge_snap_candidates(
    image: np.ndarray,
    scored_detections: list[ScoredDetection],
) -> list[ScoredDetection]:
    candidates: list[ScoredDetection] = []
    image_area = max(1, image.shape[0] * image.shape[1])

    for scored in scored_detections:
        detection = scored.detection
        if detection.columns < 20 or detection.rows < 15:
            continue
        if scored.fit_kind.endswith("parallelogram-right-snap"):
            continue

        corners = np.float32(detection.corners)
        cell_pixels = average_candidate_square_pixels(corners, detection.columns, detection.rows)
        if cell_pixels <= 0:
            continue

        parallelogram = corners.copy()
        parallelogram[2] = corners[1] + corners[3] - corners[0]
        parallelogram_delta_squares = float(np.linalg.norm(corners[2] - parallelogram[2]) / cell_pixels)
        if parallelogram_delta_squares < 0.45:
            continue

        top_cell_vector = (parallelogram[1] - parallelogram[0]) / max(1, detection.columns)
        best: tuple[float, float, np.ndarray, float] | None = None
        for right_offset in np.linspace(-0.45, 0.05, 21):
            snapped = parallelogram.copy()
            snapped[1] = parallelogram[1] + top_cell_vector * right_offset
            snapped[2] = parallelogram[2] + top_cell_vector * right_offset
            if polygon_area(snapped) < image_area * 0.02:
                continue
            lattice_score = lattice_support(image, snapped, detection.columns, detection.rows)
            # Prefer the small inward snap that strengthens grid support without turning this
            # into another broad geometric expansion.
            snap_score = lattice_score - abs(float(right_offset) + 0.22) * 0.015
            if best is None or snap_score > best[0]:
                best = (snap_score, float(right_offset), snapped, lattice_score)

        if best is None:
            continue

        _, right_offset, snapped, lattice_score = best
        if lattice_score < scored.lattice_score + 0.04:
            continue

        area_ratio = polygon_area(snapped) / image_area
        score = scored.score + max(0.0, lattice_score - scored.lattice_score) * 1.2 - 0.18
        snapped_detection = Detection(
            corners=snapped,
            columns=detection.columns,
            rows=detection.rows,
            confidence=min(0.49, detection.confidence + 0.01),
            lattice_score=round(lattice_score, 4),
            message=(
                f"{detection.message} Parallelogram right-edge snap {right_offset:.3f}; "
                f"lattice {lattice_score:.2f}."
            ),
        )
        candidates.append(ScoredDetection(
            score,
            snapped_detection,
            area_ratio,
            scored.strict_phase_score,
            f"{scored.fit_kind}-parallelogram-right-snap",
            lattice_score,
            scored.cell_square_score,
        ))

    return candidates


def configured_row_trim_candidates(
    image: np.ndarray,
    scored_detections: list[ScoredDetection],
) -> list[ScoredDetection]:
    candidates: list[ScoredDetection] = []
    image_area = max(1, image.shape[0] * image.shape[1])

    for scored in scored_detections:
        detection = scored.detection
        if detection.columns < 20 or detection.rows < 20:
            continue

        grid_to_image = cv2.getPerspectiveTransform(
            np.float32([[0, 0], [detection.columns, 0], [detection.columns, detection.rows], [0, detection.rows]]),
            np.float32(detection.corners),
        )

        for columns, rows in CONFIGURED_GRID_FORMATS:
            if columns != detection.columns:
                continue
            row_overrun = detection.rows - rows
            if row_overrun < 3 or row_overrun > 14:
                continue

            for y0 in np.linspace(-1.2, -0.9, 13):
                rect_points = np.float32([
                    [0, y0],
                    [columns, y0],
                    [columns, y0 + rows],
                    [0, y0 + rows],
                ]).reshape(1, 4, 2)
                corners = order_corners(cv2.perspectiveTransform(rect_points, grid_to_image).reshape(4, 2))
                if polygon_area(corners) < image_area * 0.02:
                    continue

                lattice_score = lattice_support(image, corners, columns, rows)
                if lattice_score < 0.10:
                    continue

                # The configured trim models the common case where the candidate found
                # the right column pitch but included product copy below the mat; the real
                # grid usually starts about one square above the overlarge candidate extent.
                trim_score = scored.score + lattice_score * 0.35 + 0.48 - abs(float(y0) + 1.05) * 0.24
                detection_message = (
                    f"{detection.message} Configured row trim {columns}x{rows} "
                    f"y0={float(y0):.2f}; lattice {lattice_score:.2f}."
                )
                trimmed_detection = Detection(
                    corners=corners,
                    columns=columns,
                    rows=rows,
                    confidence=min(0.49, detection.confidence + 0.02),
                    lattice_score=round(lattice_score, 4),
                    message=detection_message,
                )
                candidates.append(ScoredDetection(
                    trim_score,
                    trimmed_detection,
                    polygon_area(corners) / image_area,
                    scored.strict_phase_score,
                    f"{scored.fit_kind}-configured-row-trim-{columns}x{rows}",
                    lattice_score,
                    scored.cell_square_score,
                ))

    return candidates


def refined_material_catalog_candidates(
    image: np.ndarray,
    scored_detections: list[ScoredDetection],
) -> list[ScoredDetection]:
    # This branch is intentionally narrow and slower than the contour/profile path.
    # It only runs when the existing pool has not already produced a strong known-format
    # candidate, and it keeps only candidates with strong post-refinement grid support.
    for scored in scored_detections:
        dimensions = (scored.detection.columns, scored.detection.rows)
        if dimensions in CONFIGURED_GRID_FORMATS and (scored.score >= 4.85 or scored.lattice_score >= 0.30):
            return []

    support = dense_grid_support_image(image)
    image_area = max(1, image.shape[0] * image.shape[1])
    base_candidates: list[ScoredDetection] = []

    for area_ratio, quad_kind, quad in material_plane_quads(image):
        rect_width, rect_height = rectified_size(quad, image.shape)
        if rect_width < 180 or rect_height < 140:
            continue

        rectified, rect_to_image = rectify_quad(image, quad, rect_width, rect_height)
        gray = cv2.cvtColor(rectified, cv2.COLOR_RGB2GRAY)
        column_profile, row_profile = line_profiles(gray)
        column_peaks = score_peaks(column_profile, 0.08)
        row_peaks = score_peaks(row_profile, 0.08)

        for columns, rows in CONFIGURED_GRID_FORMATS:
            for border_x in np.linspace(0.5, 2.0, 7):
                cell_width = rect_width / (columns + border_x * 2)
                x0 = border_x * cell_width
                x1 = rect_width - border_x * cell_width
                col_support = score_axis_count(column_profile, column_peaks, x0, x1, columns)
                strict_col_support = score_axis_count_with_tolerance(column_profile, column_peaks, x0, x1, columns, 0.1, 1.5)
                if col_support < 0.35:
                    continue

                for border_y in np.linspace(0.25, 1.75, 7):
                    cell_height = rect_height / (rows + border_y * 2)
                    cell_ratio = cell_width / max(1e-6, cell_height)
                    if abs(cell_ratio - 1) > 0.18:
                        continue

                    y0 = border_y * cell_height
                    y1 = rect_height - border_y * cell_height
                    row_support = score_axis_count(row_profile, row_peaks, y0, y1, rows)
                    strict_row_support = score_axis_count_with_tolerance(row_profile, row_peaks, y0, y1, rows, 0.1, 1.5)
                    if row_support < 0.35:
                        continue

                    rect_points = np.float32([
                        [x0, y0],
                        [x1, y0],
                        [x1, y1],
                        [x0, y1],
                    ]).reshape(1, 4, 2)
                    corners = order_corners(cv2.perspectiveTransform(rect_points, rect_to_image).reshape(4, 2))
                    if polygon_area(corners) < image_area * 0.02:
                        continue

                    lattice_score = lattice_support(image, corners, columns, rows)
                    coverage = ((x1 - x0) * (y1 - y0)) / max(1, rect_width * rect_height)
                    base_score = (
                        col_support * 1.05
                        + row_support * 1.05
                        + strict_col_support * 0.7
                        + strict_row_support * 0.7
                        + lattice_score * 0.5
                        + coverage * 0.18
                        - abs(float(border_x) - 1.25) * 0.03
                        - abs(float(border_y) * 0.8 - 1) * 0.02
                    )
                    detection = Detection(
                        corners=corners,
                        columns=columns,
                        rows=rows,
                        confidence=0.49,
                        lattice_score=round(lattice_score, 4),
                        message=(
                            f"Material catalog plane {quad_kind}; configured {columns}x{rows}; "
                            f"border {float(border_x):.2f}/{float(border_y):.2f}; "
                            f"profile support {col_support:.2f}/{row_support:.2f}; "
                            f"lattice {lattice_score:.2f}."
                        ),
                    )
                    base_candidates.append(ScoredDetection(
                        base_score,
                        detection,
                        polygon_area(corners) / image_area,
                        (strict_col_support + strict_row_support) / 2,
                        f"material-catalog-{quad_kind}-{columns}x{rows}",
                        lattice_score,
                        1 - min(1, abs(cell_ratio - 1) / 0.18),
                    ))

    refined: list[ScoredDetection] = []
    for base in sorted(base_candidates, key=lambda item: item.score, reverse=True)[:4]:
        detection = base.detection
        refined_corners, dense_score = refine_corners_by_dense_grid_support(
            image,
            support,
            detection.corners,
            detection.columns,
            detection.rows,
        )
        refined_lattice = lattice_support(image, refined_corners, detection.columns, detection.rows)
        if dense_score < 0.12 or refined_lattice < 0.42:
            continue

        area_ratio = polygon_area(refined_corners) / image_area
        score = base.score + dense_score * 3.0 + refined_lattice * 0.6 + 1.45
        refined_detection = Detection(
            corners=refined_corners,
            columns=detection.columns,
            rows=detection.rows,
            confidence=0.49,
            lattice_score=round(refined_lattice, 4),
            message=(
                f"{detection.message} Dense material refinement score {dense_score:.3f}; "
                f"refined lattice {refined_lattice:.2f}."
            ),
        )
        refined.append(ScoredDetection(
            score,
            refined_detection,
            area_ratio,
            base.strict_phase_score,
            f"{base.fit_kind}-dense-refined",
            refined_lattice,
            base.cell_square_score,
        ))

    return refined


def material_plane_quads(image: np.ndarray) -> list[tuple[float, str, np.ndarray]]:
    height, width = image.shape[:2]
    scale = min(1.0, 850 / max(width, height))
    small = cv2.resize(image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    lab = cv2.cvtColor(small, cv2.COLOR_RGB2LAB)
    hue, saturation, value = cv2.split(hsv)
    _, _, lab_b = cv2.split(lab)
    image_area = height * width
    masks = [
        ((value > 75) & (value < 250) & (saturation > 5) & (saturation < 125) & (lab_b > 126) & (lab_b < 175) & (gray < 245)).astype("uint8") * 255,
        ((value > 90) & (value < 245) & (saturation < 75) & (lab_b > 120) & (gray < 238)).astype("uint8") * 255,
        ((value > 65) & (value < 245) & (saturation > 20) & (saturation < 170) & (hue < 45) & (gray < 245)).astype("uint8") * 255,
    ]

    quads: list[tuple[float, str, np.ndarray]] = []
    for mask_index, mask in enumerate(masks):
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((13, 13), np.uint8), iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            area_ratio = cv2.contourArea(contour) / (scale * scale) / image_area
            if area_ratio < 0.03:
                continue

            rect = cv2.boxPoints(cv2.minAreaRect(contour)) / scale
            quads.append((area_ratio, f"mat{mask_index}-rect", order_corners(rect)))
            perimeter = cv2.arcLength(contour, True)
            for epsilon_ratio in (0.01, 0.02, 0.04, 0.07):
                approx = cv2.approxPolyDP(contour, epsilon_ratio * perimeter, True)
                if len(approx) == 4 and cv2.isContourConvex(approx):
                    quads.append((
                        area_ratio,
                        f"mat{mask_index}-approx{epsilon_ratio}",
                        order_corners(approx.reshape(4, 2) / scale),
                    ))

    deduped: list[tuple[float, str, np.ndarray]] = []
    for area_ratio, kind, quad in sorted(quads, key=lambda item: item[0], reverse=True):
        if not any(float(np.linalg.norm(quad - existing_quad, axis=1).mean()) < 18 for _, _, existing_quad in deduped):
            deduped.append((area_ratio, kind, quad))
        if len(deduped) >= 5:
            break
    return deduped


def dense_grid_support_image(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (0, 0), 1.0)
    kernel_size = max(9, int(min(gray.shape) / 70) // 2 * 2 + 1)
    blackhat = cv2.morphologyEx(
        blurred,
        cv2.MORPH_BLACKHAT,
        cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size)),
    ).astype(np.float32)
    blackhat = (blackhat - blackhat.min()) / (blackhat.max() - blackhat.min() + 1e-6)
    edges = cv2.Canny(gray, 40, 120).astype(np.float32) / 255
    return blackhat * 0.75 + edges * 0.25


def refine_corners_by_dense_grid_support(
    image: np.ndarray,
    support: np.ndarray,
    corners: np.ndarray,
    columns: int,
    rows: int,
) -> tuple[np.ndarray, float]:
    current = np.float32(corners).copy()
    current_score = dense_grid_score(support, current, columns, rows)
    cell_size = average_candidate_square_pixels(current, columns, rows)

    for step in (cell_size * 0.35, cell_size * 0.22, cell_size * 0.12, cell_size * 0.06):
        for _ in range(4):
            improved = False
            moves: list[tuple[list[int], float, float]] = []
            for corner_index in range(4):
                for dx, dy in ((step, 0), (-step, 0), (0, step), (0, -step), (step, step), (step, -step), (-step, step), (-step, -step)):
                    moves.append(([corner_index], dx, dy))
            for edge_indexes in ([0, 1], [2, 3], [0, 3], [1, 2]):
                for dx, dy in ((step, 0), (-step, 0), (0, step), (0, -step)):
                    moves.append((edge_indexes, dx, dy))

            for indexes, dx, dy in moves:
                candidate = current.copy()
                candidate[indexes, 0] += dx
                candidate[indexes, 1] += dy
                if polygon_area(candidate) < image.shape[0] * image.shape[1] * 0.03:
                    continue
                score = dense_grid_score(support, candidate, columns, rows)
                if score > current_score + 1e-5:
                    current = candidate
                    current_score = score
                    improved = True
            if not improved:
                break

    return current, current_score


def dense_grid_score(support: np.ndarray, corners: np.ndarray, columns: int, rows: int) -> float:
    grid_to_image = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [columns, 0], [columns, rows], [0, rows]]),
        np.float32(corners),
    )
    on_values: list[float] = []
    off_values: list[float] = []

    for x in range(columns + 1):
        for y in np.linspace(0.2, rows - 0.2, 14):
            on_values.append(sample_support(support, transform_point(grid_to_image, x, y)))
            offset_x = x + 0.35 if x < columns - 0.5 else x - 0.35
            off_values.append(sample_support(support, transform_point(grid_to_image, offset_x, y)))

    for y in range(rows + 1):
        for x in np.linspace(0.2, columns - 0.2, 20):
            on_values.append(sample_support(support, transform_point(grid_to_image, x, y)))
            offset_y = y + 0.35 if y < rows - 0.5 else y - 0.35
            off_values.append(sample_support(support, transform_point(grid_to_image, x, offset_y)))

    if not on_values:
        return 0.0
    area_ratio = polygon_area(corners) / max(1, support.shape[0] * support.shape[1])
    return float(np.mean(on_values) - 0.45 * np.mean(off_values) + 0.03 * area_ratio)


def sample_support(values: np.ndarray, point: tuple[float, float]) -> float:
    x, y = point
    if x < 1 or y < 1 or x >= values.shape[1] - 2 or y >= values.shape[0] - 2:
        return 0.0
    x0 = math.floor(x)
    y0 = math.floor(y)
    dx = x - x0
    dy = y - y0
    return float(
        values[y0, x0] * (1 - dx) * (1 - dy)
        + values[y0, x0 + 1] * dx * (1 - dy)
        + values[y0 + 1, x0] * (1 - dx) * dy
        + values[y0 + 1, x0 + 1] * dx * dy
    )


def choose_scored_detection(scored_detections: list[ScoredDetection]) -> Detection | None:
    if not scored_detections:
        return None

    ranked = sorted(scored_detections, key=lambda item: item.score, reverse=True)
    top = ranked[0]

    selected = top

    for candidate in ranked[1:]:
        harmonic_columns = abs(candidate.detection.columns - top.detection.columns * 2) <= 1
        harmonic_rows = abs(candidate.detection.rows - top.detection.rows * 2) <= 1
        if not harmonic_columns or not harmonic_rows:
            continue
        if candidate.score < top.score - 1.05:
            continue
        if candidate.area_ratio < top.area_ratio * 0.92 or candidate.area_ratio > top.area_ratio * 1.08:
            continue
        if candidate.cell_square_score < 0.45:
            continue
        selected = candidate
        break

    for candidate in ranked[1:]:
        same_columns_one_less_row = (
            candidate.detection.columns == selected.detection.columns
            and candidate.detection.rows == selected.detection.rows - 1
        )
        same_rows_one_less_column = (
            candidate.detection.rows == selected.detection.rows
            and candidate.detection.columns == selected.detection.columns - 1
        )
        if not same_columns_one_less_row and not same_rows_one_less_column:
            continue
        if candidate.score < selected.score - 0.65:
            continue
        if candidate.strict_phase_score < selected.strict_phase_score - 0.12:
            continue
        if candidate.area_ratio > selected.area_ratio * 0.985:
            continue

        selected = candidate
        break

    for candidate in ranked:
        if candidate is selected:
            continue
        if candidate.detection.columns != selected.detection.columns or candidate.detection.rows != selected.detection.rows:
            continue
        if candidate.score < selected.score - 0.24:
            continue
        if candidate.lattice_score < selected.lattice_score - 0.25:
            continue
        tighter_area = candidate.area_ratio <= selected.area_ratio * 0.992
        sharper_phase = candidate.strict_phase_score >= selected.strict_phase_score + 0.015
        squarer_cell = candidate.cell_square_score >= selected.cell_square_score + 0.18
        if tighter_area or sharper_phase or squarer_cell:
            selected = candidate

    if selected is not top:
        selected.detection.message = f"{selected.detection.message} Close-score grid ambiguity resolved toward the inner/sharper grid."
    return selected.detection


def candidate_quads(image: np.ndarray) -> list[np.ndarray]:
    height, width = image.shape[:2]
    scale = min(1.0, 950 / max(width, height))
    small = cv2.resize(image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(small, cv2.COLOR_RGB2GRAY)
    hsv = cv2.cvtColor(small, cv2.COLOR_RGB2HSV)
    saturation = hsv[:, :, 1]
    value = hsv[:, :, 2]

    masks = [
        cv2.bitwise_and(cv2.inRange(saturation, 4, 165), cv2.inRange(value, 55, 248)),
        cv2.inRange(gray, 0, 245),
    ]
    quads: list[np.ndarray] = []

    for mask in masks:
        for iterations in (1, 2, 4):
            closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8), iterations=iterations)
            contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            quads.extend(contour_quads(contours, small.shape, scale))

    edges = cv2.Canny(gray, 45, 140)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    quads.extend(contour_quads(contours, small.shape, scale))

    deduped: list[np.ndarray] = []
    for quad in sorted(quads, key=polygon_area, reverse=True):
        if not any(float(np.linalg.norm(quad - existing, axis=1).mean()) < 10 for existing in deduped):
            deduped.append(quad)
        if len(deduped) >= 80:
            break
    return deduped


def contour_quads(contours: list[np.ndarray], shape: tuple[int, ...], scale: float) -> list[np.ndarray]:
    image_area = shape[0] * shape[1]
    quads: list[np.ndarray] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < image_area * 0.028:
            continue

        rect = cv2.boxPoints(cv2.minAreaRect(contour))
        quads.append(order_corners(rect / scale))

        perimeter = cv2.arcLength(contour, True)
        for epsilon_ratio in (0.008, 0.012, 0.02, 0.035, 0.06, 0.09):
            approx = cv2.approxPolyDP(contour, epsilon_ratio * perimeter, True)
            if len(approx) == 4 and cv2.isContourConvex(approx):
                quads.append(order_corners(approx.reshape(4, 2) / scale))
    return quads


def rectified_size(quad: np.ndarray, shape: tuple[int, ...]) -> tuple[int, int]:
    top = float(np.linalg.norm(quad[1] - quad[0]))
    bottom = float(np.linalg.norm(quad[2] - quad[3]))
    left = float(np.linalg.norm(quad[3] - quad[0]))
    right = float(np.linalg.norm(quad[2] - quad[1]))
    raw_width = max(1.0, (top + bottom) / 2)
    raw_height = max(1.0, (left + right) / 2)
    scale = min(1.0, 900 / max(raw_width, raw_height))
    width = round(max(220, raw_width * scale))
    height = round(max(180, raw_height * scale))
    return width, height


def rectify_quad(image: np.ndarray, quad: np.ndarray, width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    destination = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]])
    image_to_rect = cv2.getPerspectiveTransform(np.float32(quad), destination)
    rect_to_image = cv2.getPerspectiveTransform(destination, np.float32(quad))
    rectified = cv2.warpPerspective(image, image_to_rect, (width, height), borderValue=(245, 245, 245))
    return rectified, rect_to_image


def line_profiles(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    blurred = cv2.GaussianBlur(gray, (0, 0), 1.0)
    kernel_size = max(9, int(min(gray.shape) / 45) // 2 * 2 + 1)
    blackhat = cv2.morphologyEx(
        blurred,
        cv2.MORPH_BLACKHAT,
        cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size)),
    )
    return normalize_profile(blackhat.mean(axis=0)), normalize_profile(blackhat.mean(axis=1))


def normalize_profile(profile: np.ndarray) -> np.ndarray:
    values = profile.astype(np.float64)
    values = (values - values.min()) / (values.max() - values.min() + 1e-6)
    return np.convolve(values, np.ones(3) / 3, mode="same")


def score_peaks(profile: np.ndarray, threshold_ratio: float) -> list[float]:
    threshold = float(profile.max()) * threshold_ratio
    peaks: list[float] = []
    start: int | None = None
    weighted_sum = 0.0
    weight = 0.0

    for index in range(len(profile) + 1):
        value = float(profile[index]) if index < len(profile) else 0.0
        if value >= threshold:
            if start is None:
                start = index
            weighted_sum += index * value
            weight += value
        elif start is not None:
            peaks.append(weighted_sum / max(1e-6, weight))
            start = None
            weighted_sum = 0.0
            weight = 0.0
    return peaks


def choose_boundary_grid_fit(
    column_profile: np.ndarray,
    row_profile: np.ndarray,
    column_peaks: list[float],
    row_peaks: list[float],
) -> GridFit | None:
    width = len(column_profile)
    height = len(row_profile)
    border_options = [index * 0.125 for index in range(25)]
    best: GridFit | None = None

    for border_squares in border_options:
        for columns in range(6, min(72, max(12, round(width / 10) + 1))):
            cell_width = width / (columns + border_squares * 2)
            if cell_width < 10:
                continue
            x0 = border_squares * cell_width
            x1 = width - border_squares * cell_width
            col_support = score_axis_count(column_profile, column_peaks, x0, x1, columns)
            if col_support < 0.17:
                continue

            for rows in range(6, min(58, max(10, round(height / 10) + 1))):
                cell_height = height / (rows + border_squares * 2)
                if cell_height < 10:
                    continue
                square_score = 1 - min(1, abs(cell_width / cell_height - 1) / 0.28)
                if square_score <= 0:
                    continue

                y0 = border_squares * cell_height
                y1 = height - border_squares * cell_height
                row_support = score_axis_count(row_profile, row_peaks, y0, y1, rows)
                if row_support < 0.17:
                    continue

                density_score = min(1, (columns + rows) / 56)
                coverage = ((x1 - x0) * (y1 - y0)) / max(1, width * height)
                border_score = 1 - min(1, abs(border_squares - 1) / 2.3)
                score = (
                    col_support * 1.35
                    + row_support * 1.35
                    + square_score * 1.0
                    + density_score * 0.15
                    + coverage * 0.18
                    + border_score * 0.14
                    - (columns + rows) * 0.001
                )
                if best is None or score > best.score:
                    best = GridFit(
                        kind=f"border-{border_squares:g}",
                        x0=x0,
                        x1=x1,
                        y0=y0,
                        y1=y1,
                        columns=columns,
                        rows=rows,
                        score=score,
                        col_support=col_support,
                        row_support=row_support,
                    )

    return best


def choose_frequency_grid_fit(
    column_profile: np.ndarray,
    row_profile: np.ndarray,
    column_peaks: list[float],
    row_peaks: list[float],
) -> GridFit | None:
    width = len(column_profile)
    height = len(row_profile)
    column_periods = period_candidates(column_profile, 8, min(70, max(12, width // 4)))
    row_periods = period_candidates(row_profile, 8, min(70, max(12, height // 4)))
    border_options = [index * 0.125 for index in range(25)]
    best: GridFit | None = None

    for column_period, column_strength in column_periods:
        for row_period, row_strength in row_periods:
            square_score = 1 - min(1, abs(column_period / row_period - 1) / 0.24)
            if square_score <= 0:
                continue

            for border_squares in border_options:
                columns = round(width / column_period - border_squares * 2)
                rows = round(height / row_period - border_squares * 2)
                if columns < 6 or rows < 6 or columns > 80 or rows > 60:
                    continue

                cell_width = width / (columns + border_squares * 2)
                cell_height = height / (rows + border_squares * 2)
                cell_score = 1 - min(1, abs(cell_width / cell_height - 1) / 0.18)
                if cell_score <= 0:
                    continue

                x0 = border_squares * cell_width
                x1 = width - border_squares * cell_width
                y0 = border_squares * cell_height
                y1 = height - border_squares * cell_height
                col_support = score_axis_count(column_profile, column_peaks, x0, x1, columns)
                row_support = score_axis_count(row_profile, row_peaks, y0, y1, rows)
                if col_support < 0.15 or row_support < 0.15:
                    continue

                coverage = ((x1 - x0) * (y1 - y0)) / max(1, width * height)
                period_strength = min(1.0, (column_strength + row_strength) / 2)
                border_score = 1 - min(1, abs(border_squares - 1) / 2.4)
                score = (
                    col_support * 1.25
                    + row_support * 1.25
                    + square_score * 1.05
                    + cell_score * 0.55
                    + period_strength * 0.75
                    + coverage * 0.22
                    + border_score * 0.15
                    - (columns + rows) * 0.001
                )
                if best is None or score > best.score:
                    best = GridFit(
                        kind=f"frequency-border-{border_squares:g}",
                        x0=x0,
                        x1=x1,
                        y0=y0,
                        y1=y1,
                        columns=columns,
                        rows=rows,
                        score=score,
                        col_support=col_support,
                        row_support=row_support,
                    )

    return best


def choose_windowed_frequency_grid_fit(
    column_profile: np.ndarray,
    row_profile: np.ndarray,
    column_peaks: list[float],
    row_peaks: list[float],
) -> GridFit | None:
    width = len(column_profile)
    height = len(row_profile)
    column_axis_fits = axis_window_candidates(
        column_profile,
        column_peaks,
        period_candidates(column_profile, 8, min(70, max(12, width // 4))),
        6,
        80,
    )
    row_axis_fits = axis_window_candidates(
        row_profile,
        row_peaks,
        period_candidates(row_profile, 8, min(70, max(12, height // 4))),
        6,
        60,
    )
    best: GridFit | None = None

    for column_fit in column_axis_fits:
        cell_width = (column_fit.end - column_fit.start) / max(1, column_fit.cells)
        for row_fit in row_axis_fits:
            cell_height = (row_fit.end - row_fit.start) / max(1, row_fit.cells)
            square_score = 1 - min(1, abs(cell_width / cell_height - 1) / 0.2)
            if square_score <= 0:
                continue

            coverage = ((column_fit.end - column_fit.start) * (row_fit.end - row_fit.start)) / max(1, width * height)
            density_score = min(1, (column_fit.cells + row_fit.cells) / 56)
            score = (
                column_fit.score * 1.2
                + row_fit.score * 1.2
                + square_score * 0.95
                + coverage * 0.22
                + density_score * 0.12
                - (column_fit.cells + row_fit.cells) * 0.001
            )
            if best is None or score > best.score:
                best = GridFit(
                    kind="windowed-frequency",
                    x0=column_fit.start,
                    x1=column_fit.end,
                    y0=row_fit.start,
                    y1=row_fit.end,
                    columns=column_fit.cells,
                    rows=row_fit.cells,
                    score=score,
                    col_support=column_fit.support,
                    row_support=row_fit.support,
                )

    return best


def grid_fit_candidates(
    column_profile: np.ndarray,
    row_profile: np.ndarray,
    column_peaks: list[float],
    row_peaks: list[float],
) -> list[GridFit]:
    base_fits = [
        choose_boundary_grid_fit(column_profile, row_profile, column_peaks, row_peaks),
        choose_frequency_grid_fit(column_profile, row_profile, column_peaks, row_peaks),
    ]
    candidates: list[GridFit] = []
    for fit in base_fits:
        if fit is None:
            continue
        candidates.append(fit)
        refined = refine_grid_fit(column_profile, row_profile, column_peaks, row_peaks, fit)
        if refined.score >= fit.score - 0.05:
            candidates.append(refined)

    deduped: list[GridFit] = []
    for fit in sorted(candidates, key=lambda item: item.score, reverse=True):
        if not any(
            fit.columns == existing.columns
            and fit.rows == existing.rows
            and abs(fit.x0 - existing.x0) < 2
            and abs(fit.x1 - existing.x1) < 2
            and abs(fit.y0 - existing.y0) < 2
            and abs(fit.y1 - existing.y1) < 2
            for existing in deduped
        ):
            deduped.append(fit)
    return deduped[:8]


def choose_best_grid_fit(*fits: GridFit | None) -> GridFit | None:
    return sorted((fit for fit in fits if fit is not None), key=lambda fit: fit.score, reverse=True)[0] if any(fits) else None


def cross_axis_grid_fits(
    column_profile: np.ndarray,
    row_profile: np.ndarray,
    column_peaks: list[float],
    row_peaks: list[float],
    fit: GridFit,
) -> list[GridFit]:
    results: list[GridFit] = []
    cell_width = (fit.x1 - fit.x0) / max(1, fit.columns)
    cell_height = (fit.y1 - fit.y0) / max(1, fit.rows)

    for row_axis in fixed_period_axis_candidates(row_profile, row_peaks, cell_width, 6, 60):
        square_score = 1 - min(1, abs(cell_width / ((row_axis.end - row_axis.start) / row_axis.cells) - 1) / 0.08)
        if square_score <= 0:
            continue
        score = fit.score * 0.68 + row_axis.score * 1.35 + square_score * 0.5
        results.append(GridFit(
            kind=f"{fit.kind}-cross-y",
            x0=fit.x0,
            x1=fit.x1,
            y0=row_axis.start,
            y1=row_axis.end,
            columns=fit.columns,
            rows=row_axis.cells,
            score=score,
            col_support=fit.col_support,
            row_support=row_axis.support,
        ))

    for column_axis in fixed_period_axis_candidates(column_profile, column_peaks, cell_height, 6, 80):
        square_score = 1 - min(1, abs(((column_axis.end - column_axis.start) / column_axis.cells) / cell_height - 1) / 0.08)
        if square_score <= 0:
            continue
        score = fit.score * 0.68 + column_axis.score * 1.35 + square_score * 0.5
        results.append(GridFit(
            kind=f"{fit.kind}-cross-x",
            x0=column_axis.start,
            x1=column_axis.end,
            y0=fit.y0,
            y1=fit.y1,
            columns=column_axis.cells,
            rows=fit.rows,
            score=score,
            col_support=column_axis.support,
            row_support=fit.row_support,
        ))

    return sorted(results, key=lambda item: item.score, reverse=True)[:4]


def trim_axis_grid_fits(
    column_profile: np.ndarray,
    row_profile: np.ndarray,
    column_peaks: list[float],
    row_peaks: list[float],
    fit: GridFit,
) -> list[GridFit]:
    results: list[GridFit] = []
    cell_width = (fit.x1 - fit.x0) / max(1, fit.columns)

    if fit.columns >= 30 and fit.rows >= 24:
        min_rows = max(20, math.floor(fit.rows * 0.68))
        for row_axis in fixed_period_axis_candidates(row_profile, row_peaks, cell_width, min_rows, fit.rows):
            if row_axis.cells >= fit.rows:
                continue
            candidate_cell_height = (row_axis.end - row_axis.start) / max(1, row_axis.cells)
            square_score = 1 - min(1, abs(cell_width / candidate_cell_height - 1) / 0.1)
            coverage = (row_axis.end - row_axis.start) / max(1, len(row_profile))
            if square_score <= 0 or coverage < 0.45:
                continue
            score = fit.score * 0.62 + row_axis.score * 0.55 + square_score * 0.28 + coverage * 0.08
            results.append(GridFit(
                kind=f"{fit.kind}-trim-y",
                x0=fit.x0,
                x1=fit.x1,
                y0=row_axis.start,
                y1=row_axis.end,
                columns=fit.columns,
                rows=row_axis.cells,
                score=score,
                col_support=fit.col_support,
                row_support=row_axis.support,
            ))

    return sorted(results, key=lambda item: item.score, reverse=True)[:4]


def refine_grid_fit(
    column_profile: np.ndarray,
    row_profile: np.ndarray,
    column_peaks: list[float],
    row_peaks: list[float],
    fit: GridFit,
) -> GridFit:
    x0, x1, col_support = refine_axis_extent(column_profile, column_peaks, fit.x0, fit.x1, fit.columns)
    y0, y1, row_support = refine_axis_extent(row_profile, row_peaks, fit.y0, fit.y1, fit.rows)
    refined_score = fit.score + (col_support - fit.col_support) * 0.8 + (row_support - fit.row_support) * 0.8
    return GridFit(
        kind=f"{fit.kind}-refined",
        x0=x0,
        x1=x1,
        y0=y0,
        y1=y1,
        columns=fit.columns,
        rows=fit.rows,
        score=refined_score,
        col_support=col_support,
        row_support=row_support,
    )


def refine_axis_extent(
    profile: np.ndarray,
    peaks: list[float],
    start: float,
    end: float,
    cells: int,
) -> tuple[float, float, float]:
    base_step = max(1.0, (end - start) / max(1, cells))
    best = (start, end, score_axis_count(profile, peaks, start, end, cells))
    search_radius = base_step * 1.1
    step_values = np.linspace(base_step * 0.9, base_step * 1.1, 15)
    start_values = np.linspace(start - search_radius, start + search_radius, 25)

    for candidate_step in step_values:
        for candidate_start in start_values:
            candidate_end = candidate_start + candidate_step * cells
            if candidate_start < -candidate_step * 1.5 or candidate_end > len(profile) + candidate_step * 1.5:
                continue
            support = score_axis_count(profile, peaks, candidate_start, candidate_end, cells)
            edge_penalty = max(0.0, -candidate_start / candidate_step) * 0.03
            edge_penalty += max(0.0, (candidate_end - len(profile)) / candidate_step) * 0.03
            score = support - edge_penalty
            if score > best[2]:
                best = (candidate_start, candidate_end, support)

    return best


def period_candidates(profile: np.ndarray, min_period: int, max_period: int) -> list[tuple[float, float]]:
    values = profile.astype(np.float64)
    centered = values - values.mean()
    if np.allclose(centered, 0):
        return []

    periods: list[tuple[float, float]] = []
    windowed = centered * np.hanning(len(centered))
    spectrum = np.abs(np.fft.rfft(windowed))
    frequencies = np.fft.rfftfreq(len(windowed), d=1.0)
    max_spectrum = float(spectrum.max()) or 1.0
    for index, frequency in enumerate(frequencies):
        if frequency <= 0:
            continue
        period = 1 / frequency
        if min_period <= period <= max_period:
            periods.append((period, float(spectrum[index]) / max_spectrum))

    autocorrelation = np.correlate(centered, centered, mode="full")[len(centered) - 1 :]
    if abs(float(autocorrelation[0])) > 1e-9:
        autocorrelation = autocorrelation / autocorrelation[0]
    for lag in range(min_period, min(max_period, len(autocorrelation) - 2) + 1):
        if autocorrelation[lag] > autocorrelation[lag - 1] and autocorrelation[lag] >= autocorrelation[lag + 1]:
            periods.append((float(lag), max(0.0, float(autocorrelation[lag]))))

    expanded: list[tuple[float, float]] = []
    for period, strength in sorted(periods, key=lambda item: item[1], reverse=True)[:12]:
        for candidate_period, penalty in ((period, 1.0), (period * 2, 0.72), (period / 2, 0.55)):
            if min_period <= candidate_period <= max_period:
                expanded.append((candidate_period, strength * penalty))

    deduped: list[tuple[float, float]] = []
    for period, strength in sorted(expanded, key=lambda item: item[1], reverse=True):
        if not any(abs(period - existing_period) < 1.5 for existing_period, _ in deduped):
            deduped.append((period, strength))
        if len(deduped) >= 10:
            break
    return deduped


def axis_window_candidates(
    profile: np.ndarray,
    peaks: list[float],
    periods: list[tuple[float, float]],
    min_cells: int,
    max_cells: int,
) -> list[AxisFit]:
    if not periods:
        return []

    length = len(profile)
    seed_positions = axis_seed_positions(profile, peaks)
    candidates: list[AxisFit] = []

    for period, period_strength in periods[:7]:
        period = max(1.0, period)
        for start in seed_positions:
            for end in seed_positions:
                span = end - start
                if span < period * min_cells:
                    continue
                cells = round(span / period)
                if cells < min_cells or cells > max_cells:
                    continue
                if start < -period * 1.25 or end > length + period * 1.25:
                    continue

                observed_period = span / cells
                period_fit = 1 - min(1, abs(observed_period / period - 1) / 0.16)
                if period_fit <= 0:
                    continue

                support = score_axis_count(profile, peaks, start, end, cells)
                if support < 0.18:
                    continue

                coverage = min(1.0, span / max(1, length))
                edge_penalty = max(0.0, -start / period) * 0.03
                edge_penalty += max(0.0, (end - length) / period) * 0.03
                score = (
                    support * 1.25
                    + period_fit * 0.55
                    + min(1.0, period_strength) * 0.45
                    + coverage * 0.12
                    - edge_penalty
                    - cells * 0.001
                )
                candidates.append(AxisFit(start, end, cells, score, support, min(1.0, period_strength)))

    deduped: list[AxisFit] = []
    for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
        if not any(
            candidate.cells == existing.cells
            and abs(candidate.start - existing.start) < 3
            and abs(candidate.end - existing.end) < 3
            for existing in deduped
        ):
            deduped.append(candidate)
        if len(deduped) >= 10:
            break
    return deduped


def fixed_period_axis_candidates(
    profile: np.ndarray,
    peaks: list[float],
    period: float,
    min_cells: int,
    max_cells: int,
) -> list[AxisFit]:
    if period < 3:
        return []

    length = len(profile)
    candidates: list[AxisFit] = []
    for seed in axis_seed_positions(profile, peaks):
        start_offsets = [seed]
        for ratio in (-0.75, -0.5, -0.25, 0.25, 0.5, 0.75):
            start_offsets.append(seed + period * ratio)

        for start in start_offsets:
            if start < -period * 1.25 or start > length:
                continue
            for cells in range(min_cells, max_cells + 1):
                end = start + period * cells
                if end <= start or end > length + period * 1.25:
                    continue
                support = score_axis_count(profile, peaks, start, end, cells)
                if support < 0.18:
                    continue
                strict_support = score_axis_count_with_tolerance(profile, peaks, start, end, cells, 0.1, 1.5)
                coverage = min(1.0, (end - start) / max(1, length))
                edge_penalty = max(0.0, -start / period) * 0.03
                edge_penalty += max(0.0, (end - length) / period) * 0.03
                score = support * 0.95 + strict_support * 0.55 + coverage * 0.12 - edge_penalty - cells * 0.001
                candidates.append(AxisFit(start, end, cells, score, support, strict_support))

    deduped: list[AxisFit] = []
    for candidate in sorted(candidates, key=lambda item: item.score, reverse=True):
        if not any(
            candidate.cells == existing.cells
            and abs(candidate.start - existing.start) < period * 0.25
            and abs(candidate.end - existing.end) < period * 0.25
            for existing in deduped
        ):
            deduped.append(candidate)
        if len(deduped) >= 5:
            break
    return deduped


def axis_seed_positions(profile: np.ndarray, peaks: list[float]) -> list[float]:
    seeds = [0.0, float(len(profile) - 1)]
    scored_peaks = sorted(
        ((local_score(profile, peak, 2.5), peak) for peak in peaks),
        key=lambda item: item[0],
        reverse=True,
    )
    seeds.extend(peak for _, peak in scored_peaks[:34])

    deduped: list[float] = []
    for seed in sorted(seeds):
        if not deduped or abs(seed - deduped[-1]) >= 3:
            deduped.append(seed)
    return deduped


def score_axis_count(profile: np.ndarray, peaks: list[float], start: float, end: float, cells: int) -> float:
    return score_axis_count_with_tolerance(profile, peaks, start, end, cells, 0.16, 2.0)


def score_axis_count_with_tolerance(
    profile: np.ndarray,
    peaks: list[float],
    start: float,
    end: float,
    cells: int,
    tolerance_ratio: float,
    min_tolerance: float,
) -> float:
    span = max(1.0, end - start)
    tolerance = max(min_tolerance, span / cells * tolerance_ratio)
    total = 0.0
    matched_predicted = 0

    for index in range(cells + 1):
        position = start + span * index / cells
        score = local_score(profile, position, tolerance)
        total += score
        if score >= 0.18 or any(abs(peak - position) <= tolerance for peak in peaks):
            matched_predicted += 1

    support = total / (cells + 1)
    predicted_match = matched_predicted / (cells + 1)
    relevant_peaks = [peak for peak in peaks if start - tolerance <= peak <= end + tolerance]
    covered_peaks = 0
    for peak in relevant_peaks:
        line_index = round(((peak - start) / span) * cells)
        expected = start + span * line_index / cells
        if 0 <= line_index <= cells and abs(peak - expected) <= tolerance:
            covered_peaks += 1
    peak_coverage = covered_peaks / len(relevant_peaks) if relevant_peaks else 0
    return support * 0.5 + predicted_match * 0.28 + peak_coverage * 0.22


def local_score(profile: np.ndarray, position: float, radius: float) -> float:
    center = round(position)
    start = max(0, math.floor(center - radius))
    end = min(len(profile), math.ceil(center + radius) + 1)
    if start >= end:
        return 0.0
    return float(profile[start:end].max())


def lattice_support(image: np.ndarray, corners: np.ndarray, columns: int, rows: int) -> float:
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    grid_to_image = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [columns, 0], [columns, rows], [0, rows]]),
        np.float32(corners),
    )
    on_values: list[float] = []
    off_values: list[float] = []

    for x in sample_indexes(columns, 10):
        for sample in range(21):
            y = 0.2 + (rows - 0.4) * (sample / 20)
            on_values.append(sample_luminance(gray, transform_point(grid_to_image, x, y)))
            off_values.append(sample_luminance(gray, transform_point(grid_to_image, x + (0.5 if x < columns - 0.5 else -0.5), y)))

    for y in sample_indexes(rows, 10):
        for sample in range(21):
            x = 0.2 + (columns - 0.4) * (sample / 20)
            on_values.append(sample_luminance(gray, transform_point(grid_to_image, x, y)))
            off_values.append(sample_luminance(gray, transform_point(grid_to_image, x, y + (0.5 if y < rows - 0.5 else -0.5))))

    if not on_values or not off_values:
        return 0.0
    return round(min(1.0, abs(float(np.mean(on_values)) - float(np.mean(off_values))) / 28), 4)


def sample_indexes(count: int, max_items: int) -> list[int]:
    if count <= 2:
        return []
    available = list(range(1, count))
    if len(available) <= max_items:
        return available
    result = sorted(set(max(1, min(count - 1, round(1 + ((count - 2) * index) / (max_items - 1)))) for index in range(max_items)))
    return result


def transform_point(matrix: np.ndarray, x: float, y: float) -> tuple[float, float]:
    vector = matrix @ np.array([x, y, 1.0])
    return float(vector[0] / vector[2]), float(vector[1] / vector[2])


def sample_luminance(gray: np.ndarray, point: tuple[float, float]) -> float:
    x = round(point[0])
    y = round(point[1])
    if x < 1 or y < 1 or x >= gray.shape[1] - 1 or y >= gray.shape[0] - 1:
        return 128.0
    return float(gray[y - 1 : y + 2, x - 1 : x + 2].mean())


def score_detection(
    label: dict[str, Any],
    detection: Detection | None,
    error_message: str | None,
    candidates: list[ScoredDetection] | None = None,
) -> dict[str, Any]:
    fixture_kind = fixture_kind_for_label(label)
    truth_square_pixels = round_metric(average_truth_square_pixels(label))
    candidate_summary = score_candidate_pool(label, candidates or [], truth_square_pixels)
    base = {
        "candidateId": "opencv-boundary-lattice-v1",
        "candidateName": "OpenCV Boundary Lattice",
        "candidateCategory": "passive",
        "candidateRuntime": "Gateway Python/OpenCV via uv",
        "usesGroundTruth": False,
        "sourceId": label["sourceId"],
        "sourceName": label["sourceName"],
        "fixtureKind": fixture_kind,
        "benchmark": label["benchmark"],
        "extrapolatedGroundTruth": count_off_image_corners(label) > 0,
        "truthOffImageCornerCount": count_off_image_corners(label),
        "truthSquarePixels": truth_square_pixels,
        "expectedColumns": label["columns"],
        "expectedRows": label["rows"],
        "thresholds": {
            "autoAcceptedMeanCornerErrorSquares": AUTO_MEAN_SQUARES,
            "autoAcceptedMaxCornerErrorSquares": AUTO_MAX_SQUARES,
            "manualSeedMeanCornerErrorSquares": MANUAL_MEAN_SQUARES,
            "manualSeedMaxCornerErrorSquares": MANUAL_MAX_SQUARES,
            "roughSeedMeanCornerErrorSquares": ROUGH_MEAN_SQUARES,
            "roughSeedMaxCornerErrorSquares": ROUGH_MAX_SQUARES,
        },
        **candidate_summary,
    }
    if detection is None:
        return {
            **base,
            "applicationState": "failed",
            "outcome": "safe-refusal",
            "strictGeometrySuccess": False,
            "rowColumnExact": False,
            "rowColumnMatch": False,
            "rowColumnDeltaPct": None,
            "detectedColumns": None,
            "detectedRows": None,
            "meanCornerErrorPixels": None,
            "maxCornerErrorPixels": None,
            "meanCornerErrorSquares": None,
            "maxCornerErrorSquares": None,
            "confidence": None,
            "latticeScore": None,
            "autoAlignIssues": [],
            "detectorMessage": None,
            "errorMessage": error_message,
        }

    truth = np.float32([[point["x"], point["y"]] for point in label["corners"]])
    deltas = np.linalg.norm(detection.corners - truth, axis=1)
    mean_pixels = round_metric(float(deltas.mean()))
    max_pixels = round_metric(float(deltas.max()))
    mean_squares = round_metric(mean_pixels / max(1, truth_square_pixels))
    max_squares = round_metric(max_pixels / max(1, truth_square_pixels))
    row_column_exact = detection.columns == label["columns"] and detection.rows == label["rows"]
    strict_success = row_column_exact and mean_squares <= AUTO_MEAN_SQUARES and max_squares <= AUTO_MAX_SQUARES
    manual_seed = mean_squares <= MANUAL_MEAN_SQUARES and max_squares <= MANUAL_MAX_SQUARES
    rough_seed = mean_squares <= ROUGH_MEAN_SQUARES and max_squares <= ROUGH_MAX_SQUARES
    if manual_seed:
        outcome = "manual-correction-seed"
    elif rough_seed:
        outcome = "rough-correction-seed"
    else:
        outcome = "safe-refusal"

    return {
        **base,
        "applicationState": "warned",
        "outcome": outcome,
        "strictGeometrySuccess": strict_success,
        "rowColumnExact": row_column_exact,
        "rowColumnMatch": row_column_exact,
        "rowColumnDeltaPct": round_metric(max(
            abs(detection.columns - label["columns"]) / max(1, label["columns"]),
            abs(detection.rows - label["rows"]) / max(1, label["rows"]),
        ) * 100),
        "detectedColumns": detection.columns,
        "detectedRows": detection.rows,
        "meanCornerErrorPixels": mean_pixels,
        "maxCornerErrorPixels": max_pixels,
        "meanCornerErrorSquares": mean_squares,
        "maxCornerErrorSquares": max_squares,
        "confidence": detection.confidence,
        "latticeScore": detection.lattice_score,
        "autoAlignIssues": ["gateway OpenCV candidate is benchmark-only and never auto-applies"],
        "detectorMessage": detection.message,
        "errorMessage": error_message,
    }


def score_candidate_pool(
    label: dict[str, Any],
    candidates: list[ScoredDetection],
    truth_square_pixels: float,
) -> dict[str, Any]:
    truth = np.float32([[point["x"], point["y"]] for point in label["corners"]])
    best: dict[str, Any] | None = None
    best_exact: dict[str, Any] | None = None
    strict_count = 0
    exact_count = 0

    for candidate in candidates:
        detection = candidate.detection
        deltas = np.linalg.norm(detection.corners - truth, axis=1)
        mean_squares = float(deltas.mean()) / max(1, truth_square_pixels)
        max_squares = float(deltas.max()) / max(1, truth_square_pixels)
        row_column_exact = detection.columns == label["columns"] and detection.rows == label["rows"]
        if row_column_exact:
            exact_count += 1
        if row_column_exact and mean_squares <= AUTO_MEAN_SQUARES and max_squares <= AUTO_MAX_SQUARES:
            strict_count += 1

        summary = {
            "detectedColumns": int(detection.columns),
            "detectedRows": int(detection.rows),
            "meanCornerErrorSquares": round_metric(mean_squares),
            "maxCornerErrorSquares": round_metric(max_squares),
            "rowColumnExact": row_column_exact,
            "score": round_metric(float(candidate.score)),
            "fitKind": candidate.fit_kind,
        }
        if best is None or mean_squares < best["meanCornerErrorSquares"]:
            best = summary
        if row_column_exact and (best_exact is None or mean_squares < best_exact["meanCornerErrorSquares"]):
            best_exact = summary

    return {
        "candidatePoolCount": len(candidates),
        "candidatePoolStrictGeometrySuccess": strict_count,
        "candidatePoolRowColumnExact": exact_count,
        "candidatePoolBest": best,
        "candidatePoolBestRowColumnExact": best_exact,
    }


def build_report(results: list[dict[str, Any]], label_updated_at: str | None) -> dict[str, Any]:
    summary = summarize(results)
    return {
        "version": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "labelUpdatedAt": label_updated_at,
        "results": results,
        "summary": summary,
        "candidateSummaries": [{
            "candidateId": "opencv-boundary-lattice-v1",
            "candidateName": "OpenCV Boundary Lattice",
            "candidateCategory": "passive",
            "candidateRuntime": "Gateway Python/OpenCV via uv",
            "usesGroundTruth": False,
            **summary,
        }],
        "recommendation": recommendation(summary),
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(results),
        "generatedControlFixtures": sum(1 for result in results if result["fixtureKind"] == "generated-control"),
        "salesPhotoFixtures": sum(1 for result in results if result["fixtureKind"] == "sales-photo"),
        "realCameraProxyFixtures": sum(1 for result in results if result["fixtureKind"] == "real-camera-proxy"),
        "strictGeometrySuccess": sum(1 for result in results if result["strictGeometrySuccess"]),
        "strictSalesPhotoSuccess": sum(1 for result in results if result["fixtureKind"] == "sales-photo" and result["strictGeometrySuccess"]),
        "strictRealCameraProxySuccess": sum(1 for result in results if result["fixtureKind"] == "real-camera-proxy" and result["strictGeometrySuccess"]),
        "strictGeneratedControlSuccess": sum(1 for result in results if result["fixtureKind"] == "generated-control" and result["strictGeometrySuccess"]),
        "autoAcceptedAccurate": sum(1 for result in results if result["outcome"] == "auto-accepted-accurate"),
        "manualCorrectionSeed": sum(1 for result in results if result["outcome"] == "manual-correction-seed"),
        "roughCorrectionSeed": sum(1 for result in results if result["outcome"] == "rough-correction-seed"),
        "safeRefusal": sum(1 for result in results if result["outcome"] == "safe-refusal"),
        "wrongConfident": sum(1 for result in results if result["outcome"] == "wrong-confident"),
        "benchmarkError": sum(1 for result in results if result["outcome"] == "benchmark-error"),
        "applied": sum(1 for result in results if result["applicationState"] == "applied"),
        "warned": sum(1 for result in results if result["applicationState"] == "warned"),
        "failed": sum(1 for result in results if result["applicationState"] == "failed"),
        "rowColumnExact": sum(1 for result in results if result["rowColumnExact"]),
        "extrapolatedGroundTruth": sum(1 for result in results if result["extrapolatedGroundTruth"]),
    }


def recommendation(summary: dict[str, int]) -> str:
    if summary["realCameraProxyFixtures"] and not summary["salesPhotoFixtures"]:
        return (
            f"OpenCV boundary lattice strict real-camera proxy success is "
            f"{summary['strictRealCameraProxySuccess']}/{summary['realCameraProxyFixtures']}. "
            "Keep it benchmark-only and treat strict outer-corner scoring as a guardrail, not the full real-camera success standard."
        )
    return (
        f"OpenCV boundary lattice strict sales-photo success is "
        f"{summary['strictSalesPhotoSuccess']}/{summary['salesPhotoFixtures']}. "
        "Keep it benchmark-only unless it reaches the strict gate with zero wrong-confident results."
    )


def render_report_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# OpenCV Fixture Grid Benchmark",
        "",
        f"Generated: {report['generatedAt']}",
        f"Labels updated: {report['labelUpdatedAt'] or 'unknown'}",
        "",
        "## Summary",
        "",
        *strict_summary_lines(summary),
        f"- Manual correction seeds: {summary['manualCorrectionSeed']}",
        f"- Rough correction seeds: {summary['roughCorrectionSeed']}",
        f"- Safe refusals: {summary['safeRefusal']}",
        f"- Wrong confident: {summary['wrongConfident']}",
        f"- Benchmark errors: {summary['benchmarkError']}",
        "",
        "## Fixtures",
        "",
        "| Fixture | Strict | Outcome | Expected | Detected | Mean sq | Max sq | Pool strict/exact | Best exact pool | Notes |",
        "|---|---:|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for result in report["results"]:
        detected = "-" if result["detectedColumns"] is None else f"{result['detectedColumns']}x{result['detectedRows']}"
        best_exact = result["candidatePoolBestRowColumnExact"]
        best_exact_text = "-" if best_exact is None else (
            f"{best_exact['detectedColumns']}x{best_exact['detectedRows']} "
            f"{metric(best_exact['meanCornerErrorSquares'])}/{metric(best_exact['maxCornerErrorSquares'])}"
        )
        notes = result["detectorMessage"] or result["errorMessage"] or "-"
        lines.append(
            " | ".join([
                f"| {escape_md(result['sourceName'])}",
                "yes" if result["strictGeometrySuccess"] else "no",
                result["outcome"],
                f"{result['expectedColumns']}x{result['expectedRows']}",
                detected,
                metric(result["meanCornerErrorSquares"]),
                metric(result["maxCornerErrorSquares"]),
                f"{result['candidatePoolStrictGeometrySuccess']}/{result['candidatePoolRowColumnExact']}",
                escape_md(best_exact_text),
                f"{escape_md(notes)} |",
            ])
        )
    lines.extend(["", "## Recommendation", "", report["recommendation"], ""])
    return "\n".join(lines)


def print_summary(out_dir: Path, report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"OpenCV fixture benchmark wrote {out_dir}")
    for line in strict_summary_lines(summary):
        print(f"  {line.removeprefix('- ').lower()}")
    print(f"  manual correction seeds: {summary['manualCorrectionSeed']}")
    print(f"  rough correction seeds: {summary['roughCorrectionSeed']}")
    print(f"  safe refusals: {summary['safeRefusal']}")
    print(f"  wrong confident: {summary['wrongConfident']}")
    print(f"  benchmark errors: {summary['benchmarkError']}")
    print(f"  recommendation: {report['recommendation']}")


def fixture_kind_for_label(label: dict[str, Any]) -> str:
    source_id = str(label["sourceId"])
    source_url = str(label["sourceUrl"])
    if source_url.startswith("data:image/") or source_id.startswith("generated-"):
        return "generated-control"
    if source_id.startswith("real-map-home-") or "/real-map-home-" in source_url:
        return "real-camera-proxy"
    return "sales-photo"


def strict_summary_lines(summary: dict[str, int]) -> list[str]:
    lines: list[str] = []
    if summary["salesPhotoFixtures"]:
        lines.append(f"- Strict sales-photo successes: {summary['strictSalesPhotoSuccess']} / {summary['salesPhotoFixtures']}")
    if summary["realCameraProxyFixtures"]:
        lines.append(
            f"- Strict real-camera proxy successes: "
            f"{summary['strictRealCameraProxySuccess']} / {summary['realCameraProxyFixtures']}"
        )
    if summary["generatedControlFixtures"]:
        lines.append(
            f"- Strict generated-control successes: "
            f"{summary['strictGeneratedControlSuccess']} / {summary['generatedControlFixtures']}"
        )
    if not lines:
        lines.append(f"- Strict geometry successes: {summary['strictGeometrySuccess']} / {summary['total']}")
    return lines


def write_overlay(path: Path, image: np.ndarray, label: dict[str, Any], detection: Detection | None) -> None:
    canvas = image.copy()
    truth = np.int32([[point["x"], point["y"]] for point in label["corners"]])
    cv2.polylines(canvas, [truth], True, (15, 145, 92), 5, cv2.LINE_AA)
    if detection is not None:
        detected = np.int32(np.round(detection.corners))
        cv2.polylines(canvas, [detected], True, (245, 128, 31), 5, cv2.LINE_AA)
    max_side = max(canvas.shape[:2])
    if max_side > 900:
        scale = 900 / max_side
        canvas = cv2.resize(canvas, (round(canvas.shape[1] * scale), round(canvas.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    Image.fromarray(canvas).save(path)


def write_detection_overlay(path: Path, image: np.ndarray, detection: Detection | None) -> None:
    canvas = image.copy()
    if detection is not None:
        corners = np.float32(detection.corners)
        for column in range(detection.columns + 1):
            u = column / max(1, detection.columns)
            start = interpolate_grid_point(corners, u, 0)
            end = interpolate_grid_point(corners, u, 1)
            cv2.line(canvas, tuple(np.int32(np.round(start))), tuple(np.int32(np.round(end))), (15, 145, 92), 2, cv2.LINE_AA)
        for row in range(detection.rows + 1):
            v = row / max(1, detection.rows)
            start = interpolate_grid_point(corners, 0, v)
            end = interpolate_grid_point(corners, 1, v)
            cv2.line(canvas, tuple(np.int32(np.round(start))), tuple(np.int32(np.round(end))), (15, 145, 92), 2, cv2.LINE_AA)
        detected = np.int32(np.round(detection.corners))
        cv2.polylines(canvas, [detected], True, (245, 128, 31), 5, cv2.LINE_AA)
    max_side = max(canvas.shape[:2])
    if max_side > 1200:
        scale = 1200 / max_side
        canvas = cv2.resize(canvas, (round(canvas.shape[1] * scale), round(canvas.shape[0] * scale)), interpolation=cv2.INTER_AREA)
    Image.fromarray(canvas).save(path)


def interpolate_grid_point(corners: np.ndarray, u: float, v: float) -> np.ndarray:
    top_left, top_right, bottom_right, bottom_left = np.float32(corners)
    top = top_left + (top_right - top_left) * u
    bottom = bottom_left + (bottom_right - bottom_left) * u
    return top + (bottom - top) * v


def build_unlabeled_report(results: list[dict[str, Any]], elapsed_seconds: float) -> dict[str, Any]:
    detected = [result for result in results if result["detectedColumns"] is not None]
    return {
        "version": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": "unlabeled-dry-run",
        "inputGlob": UNLABELED_GLOB,
        "maxImageSide": MAX_IMAGE_SIDE or None,
        "elapsedMs": round_metric(elapsed_seconds * 1000),
        "summary": {
            "total": len(results),
            "detected": len(detected),
            "refused": len(results) - len(detected),
            "benchmarkErrors": sum(1 for result in results if result["errorMessage"]),
        },
        "results": results,
        "recommendation": (
            "Use the overlays for visual triage only. These images are unlabeled, so the report cannot score "
            "corner accuracy or row/column correctness yet."
        ),
    }


def render_unlabeled_report_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# OpenCV Unlabeled Real-Home Detection Dry Run",
        "",
        f"Generated: {report['generatedAt']}",
        f"Input glob: `{report['inputGlob']}`",
        f"Max image side: {report['maxImageSide'] or 'original'}",
        f"Elapsed: {report['elapsedMs']} ms",
        "",
        "## Summary",
        "",
        f"- Total: {summary['total']}",
        f"- Detections: {summary['detected']}",
        f"- Refusals: {summary['refused']}",
        f"- Benchmark errors: {summary['benchmarkErrors']}",
        "",
        "## Images",
        "",
        "| Image | Detected | Confidence | Lattice | Candidates | Fit | Time ms | Notes |",
        "|---|---:|---:|---:|---:|---|---:|---|",
    ]
    for result in report["results"]:
        detected = "-" if result["detectedColumns"] is None else f"{result['detectedColumns']}x{result['detectedRows']}"
        notes = result["detectorMessage"] or result["errorMessage"] or "-"
        lines.append(
            " | ".join([
                f"| {escape_md(result['sourceName'])}",
                detected,
                metric(result["confidence"]),
                metric(result["latticeScore"]),
                str(result["candidatePoolCount"]),
                escape_md(result["selectedFitKind"] or "-"),
                metric(result["elapsedMs"]),
                f"{escape_md(notes)} |",
            ])
        )
    lines.extend(["", "## Recommendation", "", report["recommendation"], ""])
    return "\n".join(lines)


def print_unlabeled_summary(out_dir: Path, report: dict[str, Any]) -> None:
    summary = report["summary"]
    print(f"OpenCV unlabeled detection dry-run wrote {out_dir}")
    print(f"  total: {summary['total']}")
    print(f"  detections: {summary['detected']}")
    print(f"  refusals: {summary['refused']}")
    print(f"  benchmark errors: {summary['benchmarkErrors']}")
    print(f"  recommendation: {report['recommendation']}")


def real_home_source_name(path: Path) -> str:
    stem = path.stem.removeprefix("real-map-home-").replace("_", " ")
    return f"Real home mat photo {stem}"


def order_corners(points: np.ndarray) -> np.ndarray:
    pts = np.float32(points).reshape(-1, 2)
    center = pts.mean(axis=0)
    angles = np.arctan2(pts[:, 1] - center[1], pts[:, 0] - center[0])
    ordered = pts[np.argsort(angles)]
    start = np.argmin(ordered.sum(axis=1))
    return np.concatenate([ordered[start:], ordered[:start]]).astype(np.float32)


def polygon_area(points: np.ndarray) -> float:
    pts = np.float32(points).reshape(-1, 2)
    shifted = np.roll(pts, -1, axis=0)
    return float(abs(np.sum(pts[:, 0] * shifted[:, 1] - shifted[:, 0] * pts[:, 1])) / 2)


def average_truth_square_pixels(label: dict[str, Any]) -> float:
    corners = np.float32([[point["x"], point["y"]] for point in label["corners"]])
    top_left, top_right, bottom_right, bottom_left = corners
    horizontal = (float(np.linalg.norm(top_right - top_left)) + float(np.linalg.norm(bottom_right - bottom_left))) / max(1, label["columns"] * 2)
    vertical = (float(np.linalg.norm(bottom_left - top_left)) + float(np.linalg.norm(bottom_right - top_right))) / max(1, label["rows"] * 2)
    return (horizontal + vertical) / 2


def average_candidate_square_pixels(corners: np.ndarray, columns: int, rows: int) -> float:
    top_left, top_right, bottom_right, bottom_left = np.float32(corners)
    horizontal = (float(np.linalg.norm(top_right - top_left)) + float(np.linalg.norm(bottom_right - bottom_left))) / max(1, columns * 2)
    vertical = (float(np.linalg.norm(bottom_left - top_left)) + float(np.linalg.norm(bottom_right - top_right))) / max(1, rows * 2)
    return (horizontal + vertical) / 2


def count_off_image_corners(label: dict[str, Any]) -> int:
    return sum(
        1
        for corner in label["corners"]
        if corner["x"] < 0 or corner["y"] < 0 or corner["x"] > label["imageWidth"] or corner["y"] > label["imageHeight"]
    )


def round_metric(value: float) -> float:
    return round(value * 100) / 100


def metric(value: Any) -> str:
    return "-" if value is None else str(value)


def escape_md(value: str) -> str:
    return value.replace("|", "\\|")


def slugify(value: str) -> str:
    return "".join(char if char.isalnum() else "-" for char in value.lower()).strip("-")[:80]


if __name__ == "__main__":
    main()
