#!/usr/bin/env python3
"""Simulate one-frame projected active calibration patterns.

This is not a product runtime. It is a projection-mapping proof harness for the
hardware path: the app projects known points at known projector pixels, the
camera detects them, and the gateway solves an overdetermined projector-to-camera
homography with robust rejection.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = ROOT / "test-results" / "projected-fiducial-calibration-sim"
CANDIDATE_FRAME_COUNTS = {
    "projected-coded-fiducials": 1,
    "projected-circle-grid": 1,
    "projected-charuco-board": 1,
    "projected-asymmetric-circle-grid": 1,
    "projected-composite-fiducials-and-surface-circles": 1,
    "projected-perimeter-fiducials-and-interior-circles": 1,
    "projected-coded-fiducials-with-circle-refinement": 2,
    "target-adapted-fiducials-with-surface-circles": 2,
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--trials", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20260530)
    parser.add_argument("--projector-width", type=int, default=1280)
    parser.add_argument("--projector-height", type=int, default=800)
    parser.add_argument("--camera-width", type=int, default=1280)
    parser.add_argument("--camera-height", type=int, default=960)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    marker_pattern, marker_corners = render_projected_marker_pattern(args.projector_width, args.projector_height)
    circle_pattern, circle_points, circle_shape = render_projected_circle_pattern(args.projector_width, args.projector_height)
    charuco_pattern, charuco_source_points, charuco_board = render_projected_charuco_pattern(args.projector_width, args.projector_height)
    asymmetric_pattern, asymmetric_points, asymmetric_shape = render_projected_asymmetric_circle_pattern(args.projector_width, args.projector_height)
    composite_pattern, composite_circle_points = render_projected_composite_pattern(args.projector_width, args.projector_height, marker_pattern, marker_corners)
    perimeter_pattern, perimeter_marker_corners, perimeter_circle_points = render_projected_perimeter_composite_pattern(args.projector_width, args.projector_height)
    cv2.imwrite(str(out_dir / "projected-marker-pattern.png"), marker_pattern)
    cv2.imwrite(str(out_dir / "projected-circle-grid-pattern.png"), circle_pattern)
    cv2.imwrite(str(out_dir / "projected-charuco-pattern.png"), charuco_pattern)
    cv2.imwrite(str(out_dir / "projected-asymmetric-circle-grid-pattern.png"), asymmetric_pattern)
    cv2.imwrite(str(out_dir / "projected-composite-fiducial-circle-pattern.png"), composite_pattern)
    cv2.imwrite(str(out_dir / "projected-perimeter-fiducial-interior-circle-pattern.png"), perimeter_pattern)

    fiducial_reports = []
    circle_reports = []
    charuco_reports = []
    asymmetric_reports = []
    composite_reports = []
    perimeter_reports = []
    hybrid_reports = []
    targeted_hybrid_reports = []
    lens_stress_reports = []
    projector_stress_reports = []
    photometric_reports = []
    sample_images: list[tuple[str, np.ndarray]] = []
    for index in range(args.trials):
        trial_seed = rng.randint(0, 1_000_000_000)
        fiducial_trial = simulate_fiducial_trial(marker_pattern, marker_corners, args.camera_width, args.camera_height, random.Random(trial_seed))
        circle_trial = simulate_circle_trial(circle_pattern, circle_points, circle_shape, args.camera_width, args.camera_height, random.Random(trial_seed))
        charuco_trial = simulate_charuco_trial(charuco_pattern, charuco_source_points, charuco_board, args.camera_width, args.camera_height, random.Random(trial_seed))
        asymmetric_trial = simulate_asymmetric_circle_trial(
            asymmetric_pattern,
            asymmetric_points,
            asymmetric_shape,
            args.camera_width,
            args.camera_height,
            random.Random(trial_seed),
        )
        composite_trial = simulate_composite_trial(
            composite_pattern,
            marker_corners,
            composite_circle_points,
            args.camera_width,
            args.camera_height,
            random.Random(trial_seed),
        )
        perimeter_trial = simulate_composite_trial(
            perimeter_pattern,
            perimeter_marker_corners,
            perimeter_circle_points,
            args.camera_width,
            args.camera_height,
            random.Random(trial_seed),
        )
        hybrid_trial = simulate_hybrid_trial(
            marker_pattern,
            marker_corners,
            circle_pattern,
            circle_points,
            args.camera_width,
            args.camera_height,
            random.Random(trial_seed),
        )
        targeted_hybrid_trial = simulate_targeted_hybrid_trial(
            marker_pattern,
            marker_corners,
            args.camera_width,
            args.camera_height,
            random.Random(trial_seed),
        )
        lens_stress_trial = simulate_lens_stress_trial(
            marker_corners,
            circle_points,
            args.projector_width,
            args.projector_height,
            args.camera_width,
            args.camera_height,
            random.Random(trial_seed),
        )
        projector_stress_trial = simulate_projector_distortion_stress_trial(
            marker_corners,
            circle_points,
            args.projector_width,
            args.projector_height,
            args.camera_width,
            args.camera_height,
            random.Random(trial_seed),
        )
        photometric_trial = simulate_photometric_preflight_trial(
            marker_pattern,
            marker_corners,
            args.camera_width,
            args.camera_height,
            random.Random(trial_seed),
        )
        fiducial_reports.append(fiducial_trial["report"])
        circle_reports.append(circle_trial["report"])
        charuco_reports.append(charuco_trial["report"])
        asymmetric_reports.append(asymmetric_trial["report"])
        composite_reports.append(composite_trial["report"])
        perimeter_reports.append(perimeter_trial["report"])
        hybrid_reports.append(hybrid_trial["report"])
        targeted_hybrid_reports.append(targeted_hybrid_trial["report"])
        lens_stress_reports.append(lens_stress_trial)
        projector_stress_reports.append(projector_stress_trial)
        photometric_reports.append(photometric_trial["report"])
        if len(sample_images) < 4:
            sample_images.append((f"trial-{index + 1:02d}-fiducial", fiducial_trial["overlay"]))
            sample_images.append((f"trial-{index + 1:02d}-circle-grid", circle_trial["overlay"]))
            sample_images.append((f"trial-{index + 1:02d}-charuco", charuco_trial["overlay"]))
            sample_images.append((f"trial-{index + 1:02d}-asymmetric-circle-grid", asymmetric_trial["overlay"]))
            sample_images.append((f"trial-{index + 1:02d}-composite-fiducial-circle", composite_trial["overlay"]))
            sample_images.append((f"trial-{index + 1:02d}-perimeter-fiducial-circle", perimeter_trial["overlay"]))
            sample_images.append((f"trial-{index + 1:02d}-hybrid-two-frame", hybrid_trial["overlay"]))
            sample_images.append((f"trial-{index + 1:02d}-targeted-hybrid-two-frame", targeted_hybrid_trial["overlay"]))
            sample_images.append((f"trial-{index + 1:02d}-photometric-preflight", photometric_trial["overlay"]))

    for name, image in sample_images:
        cv2.imwrite(str(out_dir / f"{name}-camera-detections.png"), image)

    report = {
        "outDir": str(out_dir),
        "description": "Projected active-calibration simulation: compare known-ID ArUco markers against anonymous sparse circle grids under the same randomized camera/projector geometry.",
        "config": vars(args),
        "summary": {
            "fiducials": summarize(fiducial_reports, detected_key="detectedMarkers", mean_key="meanDetectedMarkers"),
            "circleGrid": summarize(circle_reports, detected_key="detectedCircles", mean_key="meanDetectedCircles"),
            "charuco": summarize(charuco_reports, detected_key="detectedCharucoCorners", mean_key="meanDetectedCharucoCorners"),
            "asymmetricCircleGrid": summarize(asymmetric_reports, detected_key="detectedCircles", mean_key="meanDetectedAsymmetricCircles"),
            "compositeFiducialCircle": summarize(composite_reports, detected_key="detectedFeatures", mean_key="meanDetectedFeatures"),
            "perimeterFiducialCircle": summarize(perimeter_reports, detected_key="detectedFeatures", mean_key="meanDetectedFeatures"),
            "hybridTwoFrame": summarize(hybrid_reports, detected_key="detectedFeatures", mean_key="meanDetectedFeatures"),
            "targetedHybridTwoFrame": summarize(targeted_hybrid_reports, detected_key="detectedFeatures", mean_key="meanDetectedFeatures"),
            "lensStress": summarize_lens_stress(lens_stress_reports),
            "projectorDistortionStress": summarize_projector_distortion_stress(projector_stress_reports),
            "photometricPreflightStress": summarize_photometric_preflight(photometric_reports),
        },
        "comparison": compare_summaries(
            {
                "projected-coded-fiducials": fiducial_reports,
                "projected-circle-grid": circle_reports,
                "projected-charuco-board": charuco_reports,
                "projected-asymmetric-circle-grid": asymmetric_reports,
                "projected-composite-fiducials-and-surface-circles": composite_reports,
                "projected-perimeter-fiducials-and-interior-circles": perimeter_reports,
                "projected-coded-fiducials-with-circle-refinement": hybrid_reports,
                "target-adapted-fiducials-with-surface-circles": targeted_hybrid_reports,
            }
        ),
        "trials": {
            "fiducials": fiducial_reports,
            "circleGrid": circle_reports,
            "charuco": charuco_reports,
            "asymmetricCircleGrid": asymmetric_reports,
            "compositeFiducialCircle": composite_reports,
            "perimeterFiducialCircle": perimeter_reports,
            "hybridTwoFrame": hybrid_reports,
            "targetedHybridTwoFrame": targeted_hybrid_reports,
            "lensStress": lens_stress_reports,
            "projectorDistortionStress": projector_stress_reports,
            "photometricPreflightStress": photometric_reports,
        },
    }
    (out_dir / "report.json").write_text(f"{json.dumps(report, indent=2)}\n")
    (out_dir / "report.md").write_text(render_markdown(report))
    print(render_console(report))


def render_projected_marker_pattern(width: int, height: int) -> tuple[np.ndarray, dict[int, np.ndarray]]:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    canvas = np.zeros((height, width), dtype=np.uint8)
    marker_corners: dict[int, np.ndarray] = {}
    rows = 4
    columns = 5
    marker_size = 82
    tile_size = 118
    start_x = int((width - columns * tile_size) / 2)
    start_y = int((height - rows * tile_size) / 2)
    marker_id = 0
    for row in range(rows):
        for column in range(columns):
            tile_x = start_x + column * tile_size
            tile_y = start_y + row * tile_size
            pad = int((tile_size - marker_size) / 2)
            x = tile_x + pad
            y = tile_y + pad
            cv2.rectangle(canvas, (tile_x, tile_y), (tile_x + tile_size - 1, tile_y + tile_size - 1), 255, -1)
            marker = cv2.aruco.generateImageMarker(dictionary, marker_id, marker_size)
            canvas[y : y + marker_size, x : x + marker_size] = marker
            marker_corners[marker_id] = np.float32(
                [
                    [x, y],
                    [x + marker_size - 1, y],
                    [x + marker_size - 1, y + marker_size - 1],
                    [x, y + marker_size - 1],
                ]
            )
            marker_id += 1
    return canvas, marker_corners


def render_projected_circle_pattern(width: int, height: int) -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    canvas = np.zeros((height, width), dtype=np.uint8)
    rows = 4
    columns = 5
    spacing_x = 118
    spacing_y = 118
    radius = 17
    start_x = int((width - (columns - 1) * spacing_x) / 2)
    start_y = int((height - (rows - 1) * spacing_y) / 2)
    points = []
    for row in range(rows):
        for column in range(columns):
            point = (float(start_x + column * spacing_x), float(start_y + row * spacing_y))
            points.append(point)
            cv2.circle(canvas, (int(point[0]), int(point[1])), radius, 255, -1, cv2.LINE_AA)
    return canvas, np.float32(points), (rows, columns)


def render_projected_circle_points(width: int, height: int, points: np.ndarray, radius: int = 15) -> np.ndarray:
    canvas = np.zeros((height, width), dtype=np.uint8)
    for point in points:
        x = int(round(float(point[0])))
        y = int(round(float(point[1])))
        if 0 <= x < width and 0 <= y < height:
            cv2.circle(canvas, (x, y), radius, 255, -1, cv2.LINE_AA)
    return canvas


def target_adapted_circle_points(projector_width: int, projector_height: int, seed_homography: np.ndarray | None, camera_width: int, camera_height: int) -> np.ndarray:
    xs = np.linspace(projector_width * 0.08, projector_width * 0.92, 7)
    ys = np.linspace(projector_height * 0.08, projector_height * 0.92, 5)
    points = np.float32([[float(x), float(y)] for y in ys for x in xs])
    if seed_homography is None:
        return points
    projected = cv2.perspectiveTransform(points.reshape(1, -1, 2), seed_homography).reshape(-1, 2)
    margin = 28.0
    keep = (
        (projected[:, 0] >= margin)
        & (projected[:, 0] <= camera_width - margin)
        & (projected[:, 1] >= margin)
        & (projected[:, 1] <= camera_height - margin)
    )
    if int(np.count_nonzero(keep)) >= 16:
        return points[keep]
    return points


def render_projected_charuco_pattern(width: int, height: int) -> tuple[np.ndarray, np.ndarray, Any]:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    squares_x = 7
    squares_y = 6
    square_size = 78
    marker_size = 52
    board = cv2.aruco.CharucoBoard((squares_x, squares_y), float(square_size), float(marker_size), dictionary)
    board_image = board.generateImage((squares_x * square_size, squares_y * square_size), marginSize=0)
    canvas = np.zeros((height, width), dtype=np.uint8)
    start_x = int((width - board_image.shape[1]) / 2)
    start_y = int((height - board_image.shape[0]) / 2)
    canvas[start_y : start_y + board_image.shape[0], start_x : start_x + board_image.shape[1]] = board_image
    corners = board.getChessboardCorners()[:, :2].astype(np.float32)
    corners[:, 0] += start_x
    corners[:, 1] += start_y
    return canvas, corners, board


def render_projected_asymmetric_circle_pattern(width: int, height: int) -> tuple[np.ndarray, np.ndarray, tuple[int, int]]:
    canvas = np.zeros((height, width), dtype=np.uint8)
    rows = 5
    columns = 7
    spacing = 46
    radius = 14
    pattern_width = int((2 * (columns - 1) + 1) * spacing)
    pattern_height = int((rows - 1) * spacing)
    start_x = int((width - pattern_width) / 2)
    start_y = int((height - pattern_height) / 2)
    points = []
    for row in range(rows):
        for column in range(columns):
            x = float(start_x + (2 * column + (row % 2)) * spacing)
            y = float(start_y + row * spacing)
            points.append((x, y))
            cv2.circle(canvas, (int(round(x)), int(round(y))), radius, 255, -1, cv2.LINE_AA)
    return canvas, np.float32(points), (rows, columns)


def render_projected_composite_pattern(
    width: int,
    height: int,
    marker_pattern: np.ndarray,
    marker_corners: dict[int, np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    canvas = marker_pattern.copy()
    circle_points = composite_surface_circle_points(width, height, marker_corners)
    for point in circle_points:
        cv2.circle(canvas, (int(round(float(point[0]))), int(round(float(point[1])))), 13, 255, -1, cv2.LINE_AA)
    return canvas, circle_points


def render_projected_perimeter_composite_pattern(width: int, height: int) -> tuple[np.ndarray, dict[int, np.ndarray], np.ndarray]:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    canvas = np.zeros((height, width), dtype=np.uint8)
    marker_corners: dict[int, np.ndarray] = {}
    marker_size = 68
    tile_size = 96
    positions = perimeter_marker_positions(width, height, tile_size)
    for marker_id, (tile_x, tile_y) in enumerate(positions):
        pad = int((tile_size - marker_size) / 2)
        x = int(round(tile_x + pad))
        y = int(round(tile_y + pad))
        cv2.rectangle(canvas, (int(round(tile_x)), int(round(tile_y))), (int(round(tile_x + tile_size - 1)), int(round(tile_y + tile_size - 1))), 255, -1)
        marker = cv2.aruco.generateImageMarker(dictionary, marker_id, marker_size)
        canvas[y : y + marker_size, x : x + marker_size] = marker
        marker_corners[marker_id] = np.float32(
            [
                [x, y],
                [x + marker_size - 1, y],
                [x + marker_size - 1, y + marker_size - 1],
                [x, y + marker_size - 1],
            ]
        )

    circle_points = perimeter_interior_circle_points(width, height, marker_corners)
    for point in circle_points:
        cv2.circle(canvas, (int(round(float(point[0]))), int(round(float(point[1])))), 13, 255, -1, cv2.LINE_AA)
    return canvas, marker_corners, circle_points


def perimeter_marker_positions(width: int, height: int, tile_size: int) -> list[tuple[float, float]]:
    left = width * 0.055
    right = width - left - tile_size
    top = height * 0.055
    bottom = height - top - tile_size
    top_xs = np.linspace(width * 0.18, width * 0.82 - tile_size, 4)
    bottom_xs = top_xs
    middle_ys = np.linspace(height * 0.29, height * 0.71 - tile_size, 3)
    positions: list[tuple[float, float]] = []
    positions.extend((float(x), float(top)) for x in top_xs)
    positions.extend((float(x), float(bottom)) for x in bottom_xs)
    positions.extend((float(left), float(y)) for y in middle_ys)
    positions.extend((float(right), float(y)) for y in middle_ys)
    return positions


def perimeter_interior_circle_points(width: int, height: int, marker_corners: dict[int, np.ndarray]) -> np.ndarray:
    xs = np.linspace(width * 0.14, width * 0.86, 8)
    ys = np.linspace(height * 0.16, height * 0.84, 6)
    candidates = np.float32([[float(x), float(y)] for y in ys for x in xs])
    marker_boxes = []
    for corners in marker_corners.values():
        marker_boxes.append(
            (
                float(np.min(corners[:, 0])),
                float(np.min(corners[:, 1])),
                float(np.max(corners[:, 0])),
                float(np.max(corners[:, 1])),
            )
        )

    margin = 44.0
    kept = []
    for point in candidates:
        x = float(point[0])
        y = float(point[1])
        overlaps_marker = any((min_x - margin) <= x <= (max_x + margin) and (min_y - margin) <= y <= (max_y + margin) for min_x, min_y, max_x, max_y in marker_boxes)
        if not overlaps_marker:
            kept.append(point)
    if len(kept) >= 24:
        return np.float32(kept)
    return candidates


def composite_surface_circle_points(width: int, height: int, marker_corners: dict[int, np.ndarray]) -> np.ndarray:
    candidates = target_adapted_circle_points(width, height, None, width, height)
    marker_boxes = []
    for corners in marker_corners.values():
        min_x = float(np.min(corners[:, 0]))
        max_x = float(np.max(corners[:, 0]))
        min_y = float(np.min(corners[:, 1]))
        max_y = float(np.max(corners[:, 1]))
        marker_boxes.append((min_x, min_y, max_x, max_y))

    kept = []
    margin = 48.0
    for point in candidates:
        x = float(point[0])
        y = float(point[1])
        overlaps_marker = any((min_x - margin) <= x <= (max_x + margin) and (min_y - margin) <= y <= (max_y + margin) for min_x, min_y, max_x, max_y in marker_boxes)
        if not overlaps_marker:
            kept.append(point)

    if len(kept) >= 16:
        return np.float32(kept)
    return np.float32(candidates)


def simulate_fiducial_trial(
    pattern: np.ndarray,
    marker_corners: dict[int, np.ndarray],
    camera_width: int,
    camera_height: int,
    rng: random.Random,
) -> dict[str, Any]:
    projector_height, projector_width = pattern.shape[:2]
    src_corners = np.float32([[0, 0], [projector_width - 1, 0], [projector_width - 1, projector_height - 1], [0, projector_height - 1]])
    dst_corners = random_camera_quad(camera_width, camera_height, rng)
    true_homography = cv2.getPerspectiveTransform(src_corners, dst_corners)
    frame = np.full((camera_height, camera_width), rng.randint(18, 48), dtype=np.uint8)
    warped = cv2.warpPerspective(pattern, true_homography, (camera_width, camera_height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    frame = np.maximum(frame, warped)
    frame = apply_camera_artifacts(frame, rng)

    detections = detect_markers(frame)
    source_points: list[np.ndarray] = []
    camera_points: list[np.ndarray] = []
    for marker_id, corners in detections.items():
        projector = marker_corners.get(marker_id)
        if projector is None:
            continue
        source_points.extend(projector)
        camera_points.extend(corners)

    report: dict[str, Any] = {
        "detectedMarkers": int(len(detections)),
        "detectedCorners": int(len(camera_points)),
        "cameraQuad": [[round_metric(value) for value in point] for point in dst_corners.tolist()],
    }
    estimated = None
    inliers: list[int] = []
    errors = np.array([], dtype=np.float32)
    if len(camera_points) >= 16:
        estimated, inlier_mask = cv2.findHomography(np.float32(source_points), np.float32(camera_points), cv2.RANSAC, 3.0, maxIters=3000, confidence=0.995)
        if estimated is not None and inlier_mask is not None:
            inliers = [int(index) for index, keep in enumerate(inlier_mask.ravel().tolist()) if int(keep) == 1]
            projected = cv2.perspectiveTransform(np.float32(source_points).reshape(1, -1, 2), estimated).reshape(-1, 2)
            true_projected = cv2.perspectiveTransform(np.float32(source_points).reshape(1, -1, 2), true_homography).reshape(-1, 2)
            errors = np.linalg.norm(projected - true_projected, axis=1)
    surface_errors = holdout_surface_errors(estimated, true_homography, projector_width, projector_height)
    report.update(homography_report(errors, inliers, estimated, surface_errors))

    overlay = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    draw_detected_markers(overlay, detections)
    if estimated is not None:
        draw_projected_outline(overlay, estimated, projector_width, projector_height)
    return {"report": report, "overlay": overlay}


def simulate_circle_trial(
    pattern: np.ndarray,
    circle_points: np.ndarray,
    circle_shape: tuple[int, int],
    camera_width: int,
    camera_height: int,
    rng: random.Random,
) -> dict[str, Any]:
    projector_height, projector_width = pattern.shape[:2]
    src_corners = np.float32([[0, 0], [projector_width - 1, 0], [projector_width - 1, projector_height - 1], [0, projector_height - 1]])
    dst_corners = random_camera_quad(camera_width, camera_height, rng)
    true_homography = cv2.getPerspectiveTransform(src_corners, dst_corners)
    frame = np.full((camera_height, camera_width), rng.randint(18, 48), dtype=np.uint8)
    warped = cv2.warpPerspective(pattern, true_homography, (camera_width, camera_height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    frame = np.maximum(frame, warped)
    frame = apply_camera_artifacts(frame, rng)

    detected_points = detect_circle_grid(frame, circle_shape)
    report: dict[str, Any] = {
        "detectedCircles": int(0 if detected_points is None else len(detected_points)),
        "detectedCorners": int(0 if detected_points is None else len(detected_points)),
        "cameraQuad": [[round_metric(value) for value in point] for point in dst_corners.tolist()],
    }
    estimated = None
    inliers: list[int] = []
    errors = np.array([], dtype=np.float32)
    if detected_points is not None and len(detected_points) == len(circle_points):
        estimated, inlier_mask = cv2.findHomography(circle_points, detected_points, cv2.RANSAC, 3.0, maxIters=3000, confidence=0.995)
        if estimated is not None and inlier_mask is not None:
            inliers = [int(index) for index, keep in enumerate(inlier_mask.ravel().tolist()) if int(keep) == 1]
            projected = cv2.perspectiveTransform(circle_points.reshape(1, -1, 2), estimated).reshape(-1, 2)
            true_projected = cv2.perspectiveTransform(circle_points.reshape(1, -1, 2), true_homography).reshape(-1, 2)
            errors = np.linalg.norm(projected - true_projected, axis=1)
    surface_errors = holdout_surface_errors(estimated, true_homography, projector_width, projector_height)
    report.update(homography_report(errors, inliers, estimated, surface_errors))

    overlay = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    if detected_points is not None:
        draw_detected_circles(overlay, detected_points)
    if estimated is not None:
        draw_projected_outline(overlay, estimated, projector_width, projector_height)
    return {"report": report, "overlay": overlay}


def simulate_charuco_trial(
    pattern: np.ndarray,
    charuco_source_points: np.ndarray,
    board: Any,
    camera_width: int,
    camera_height: int,
    rng: random.Random,
) -> dict[str, Any]:
    projector_height, projector_width = pattern.shape[:2]
    src_corners = np.float32([[0, 0], [projector_width - 1, 0], [projector_width - 1, projector_height - 1], [0, projector_height - 1]])
    dst_corners = random_camera_quad(camera_width, camera_height, rng)
    true_homography = cv2.getPerspectiveTransform(src_corners, dst_corners)
    frame = render_camera_frame(pattern, true_homography, camera_width, camera_height, rng)

    detections = detect_charuco_corners(frame, board)
    source_points: list[np.ndarray] = []
    camera_points: list[np.ndarray] = []
    for corner_id, point in detections.items():
        if corner_id < 0 or corner_id >= len(charuco_source_points):
            continue
        source_points.append(charuco_source_points[corner_id])
        camera_points.append(point)

    report: dict[str, Any] = {
        "detectedCharucoCorners": int(len(camera_points)),
        "detectedCorners": int(len(camera_points)),
        "cameraQuad": [[round_metric(value) for value in point] for point in dst_corners.tolist()],
    }
    estimated = None
    inliers: list[int] = []
    errors = np.array([], dtype=np.float32)
    if len(camera_points) >= 12:
        estimated, inlier_mask = cv2.findHomography(np.float32(source_points), np.float32(camera_points), cv2.RANSAC, 3.0, maxIters=3000, confidence=0.995)
        if estimated is not None and inlier_mask is not None:
            inliers = [int(index) for index, keep in enumerate(inlier_mask.ravel().tolist()) if int(keep) == 1]
            projected = cv2.perspectiveTransform(np.float32(source_points).reshape(1, -1, 2), estimated).reshape(-1, 2)
            true_projected = cv2.perspectiveTransform(np.float32(source_points).reshape(1, -1, 2), true_homography).reshape(-1, 2)
            errors = np.linalg.norm(projected - true_projected, axis=1)
    surface_errors = holdout_surface_errors(estimated, true_homography, projector_width, projector_height)
    report.update(homography_report(errors, inliers, estimated, surface_errors))

    overlay = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    if detections:
        draw_detected_points(overlay, np.float32(list(detections.values())), (255, 0, 255))
    if estimated is not None:
        draw_projected_outline(overlay, estimated, projector_width, projector_height)
    return {"report": report, "overlay": overlay}


def simulate_asymmetric_circle_trial(
    pattern: np.ndarray,
    circle_points: np.ndarray,
    circle_shape: tuple[int, int],
    camera_width: int,
    camera_height: int,
    rng: random.Random,
) -> dict[str, Any]:
    projector_height, projector_width = pattern.shape[:2]
    src_corners = np.float32([[0, 0], [projector_width - 1, 0], [projector_width - 1, projector_height - 1], [0, projector_height - 1]])
    dst_corners = random_camera_quad(camera_width, camera_height, rng)
    true_homography = cv2.getPerspectiveTransform(src_corners, dst_corners)
    frame = render_camera_frame(pattern, true_homography, camera_width, camera_height, rng)

    detected_points = detect_asymmetric_circle_grid(frame, circle_shape)
    report: dict[str, Any] = {
        "detectedCircles": int(0 if detected_points is None else len(detected_points)),
        "detectedCorners": int(0 if detected_points is None else len(detected_points)),
        "cameraQuad": [[round_metric(value) for value in point] for point in dst_corners.tolist()],
    }
    estimated = None
    inliers: list[int] = []
    errors = np.array([], dtype=np.float32)
    if detected_points is not None and len(detected_points) == len(circle_points):
        estimated, inlier_mask = cv2.findHomography(circle_points, detected_points, cv2.RANSAC, 3.0, maxIters=3000, confidence=0.995)
        if estimated is not None and inlier_mask is not None:
            inliers = [int(index) for index, keep in enumerate(inlier_mask.ravel().tolist()) if int(keep) == 1]
            projected = cv2.perspectiveTransform(circle_points.reshape(1, -1, 2), estimated).reshape(-1, 2)
            true_projected = cv2.perspectiveTransform(circle_points.reshape(1, -1, 2), true_homography).reshape(-1, 2)
            errors = np.linalg.norm(projected - true_projected, axis=1)
    surface_errors = holdout_surface_errors(estimated, true_homography, projector_width, projector_height)
    report.update(homography_report(errors, inliers, estimated, surface_errors))

    overlay = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    if detected_points is not None:
        draw_detected_circles(overlay, detected_points)
    if estimated is not None:
        draw_projected_outline(overlay, estimated, projector_width, projector_height)
    return {"report": report, "overlay": overlay}


def simulate_composite_trial(
    pattern: np.ndarray,
    marker_corners: dict[int, np.ndarray],
    circle_points: np.ndarray,
    camera_width: int,
    camera_height: int,
    rng: random.Random,
) -> dict[str, Any]:
    projector_height, projector_width = pattern.shape[:2]
    src_corners = np.float32([[0, 0], [projector_width - 1, 0], [projector_width - 1, projector_height - 1], [0, projector_height - 1]])
    dst_corners = random_camera_quad(camera_width, camera_height, rng)
    true_homography = cv2.getPerspectiveTransform(src_corners, dst_corners)
    frame = render_camera_frame(pattern, true_homography, camera_width, camera_height, rng)

    detections = detect_markers(frame)
    marker_source_points: list[np.ndarray] = []
    marker_camera_points: list[np.ndarray] = []
    for marker_id, corners in detections.items():
        projector = marker_corners.get(marker_id)
        if projector is None:
            continue
        marker_source_points.extend(projector)
        marker_camera_points.extend(corners)

    marker_estimate = None
    if len(marker_camera_points) >= 16:
        marker_estimate, _marker_inliers = cv2.findHomography(
            np.float32(marker_source_points),
            np.float32(marker_camera_points),
            cv2.RANSAC,
            3.0,
            maxIters=3000,
            confidence=0.995,
        )

    raw_detected_circles = detect_circle_centers(frame)
    circle_frame = mask_detected_marker_regions(frame, detections, padding=8.0)
    detected_circles = detect_circle_centers(circle_frame)
    assigned_circle_source: list[np.ndarray] = []
    assigned_circle_camera: list[np.ndarray] = []
    if marker_estimate is not None and len(detected_circles):
        assigned_circle_source, assigned_circle_camera = assign_circles_from_seed(circle_points, detected_circles, marker_estimate)

    source_points: list[np.ndarray] = []
    camera_points: list[np.ndarray] = []
    source_points.extend(marker_source_points)
    camera_points.extend(marker_camera_points)
    source_points.extend(assigned_circle_source)
    camera_points.extend(assigned_circle_camera)

    report: dict[str, Any] = {
        "detectedMarkers": int(len(detections)),
        "targetedCircles": int(len(circle_points)),
        "rawDetectedCircles": int(len(raw_detected_circles)),
        "detectedCircles": int(len(detected_circles)),
        "assignedCircles": int(len(assigned_circle_camera)),
        "detectedFeatures": int(len(camera_points)),
        "detectedCorners": int(len(camera_points)),
        "cameraQuad": [[round_metric(value) for value in point] for point in dst_corners.tolist()],
    }
    estimated = None
    inliers: list[int] = []
    errors = np.array([], dtype=np.float32)
    if len(camera_points) >= 16:
        estimated, inlier_mask = cv2.findHomography(np.float32(source_points), np.float32(camera_points), cv2.RANSAC, 3.0, maxIters=3000, confidence=0.995)
        if estimated is not None and inlier_mask is not None:
            inliers = [int(index) for index, keep in enumerate(inlier_mask.ravel().tolist()) if int(keep) == 1]
            projected = cv2.perspectiveTransform(np.float32(source_points).reshape(1, -1, 2), estimated).reshape(-1, 2)
            true_projected = cv2.perspectiveTransform(np.float32(source_points).reshape(1, -1, 2), true_homography).reshape(-1, 2)
            errors = np.linalg.norm(projected - true_projected, axis=1)
    surface_errors = holdout_surface_errors(estimated, true_homography, projector_width, projector_height)
    report.update(homography_report(errors, inliers, estimated, surface_errors))

    overlay = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
    draw_detected_markers(overlay, detections)
    if len(raw_detected_circles):
        draw_detected_circles(overlay, raw_detected_circles)
    if len(assigned_circle_camera):
        draw_assigned_circles(overlay, np.float32(assigned_circle_camera))
    if estimated is not None:
        draw_projected_outline(overlay, estimated, projector_width, projector_height)
    return {"report": report, "overlay": overlay}


def simulate_hybrid_trial(
    marker_pattern: np.ndarray,
    marker_corners: dict[int, np.ndarray],
    circle_pattern: np.ndarray,
    circle_points: np.ndarray,
    camera_width: int,
    camera_height: int,
    rng: random.Random,
) -> dict[str, Any]:
    projector_height, projector_width = marker_pattern.shape[:2]
    src_corners = np.float32([[0, 0], [projector_width - 1, 0], [projector_width - 1, projector_height - 1], [0, projector_height - 1]])
    dst_corners = random_camera_quad(camera_width, camera_height, rng)
    true_homography = cv2.getPerspectiveTransform(src_corners, dst_corners)

    marker_frame = render_camera_frame(marker_pattern, true_homography, camera_width, camera_height, random.Random(rng.randint(0, 1_000_000_000)))
    circle_frame = render_camera_frame(circle_pattern, true_homography, camera_width, camera_height, random.Random(rng.randint(0, 1_000_000_000)))

    detections = detect_markers(marker_frame)
    marker_source_points: list[np.ndarray] = []
    marker_camera_points: list[np.ndarray] = []
    for marker_id, corners in detections.items():
        projector = marker_corners.get(marker_id)
        if projector is None:
            continue
        marker_source_points.extend(projector)
        marker_camera_points.extend(corners)

    marker_estimate = None
    if len(marker_camera_points) >= 16:
        marker_estimate, _marker_inliers = cv2.findHomography(
            np.float32(marker_source_points),
            np.float32(marker_camera_points),
            cv2.RANSAC,
            3.0,
            maxIters=3000,
            confidence=0.995,
        )

    detected_circles = detect_circle_centers(circle_frame)
    assigned_circle_source: list[np.ndarray] = []
    assigned_circle_camera: list[np.ndarray] = []
    if marker_estimate is not None and len(detected_circles):
        assigned_circle_source, assigned_circle_camera = assign_circles_from_seed(circle_points, detected_circles, marker_estimate)

    source_points: list[np.ndarray] = []
    camera_points: list[np.ndarray] = []
    source_points.extend(marker_source_points)
    camera_points.extend(marker_camera_points)
    source_points.extend(assigned_circle_source)
    camera_points.extend(assigned_circle_camera)

    report: dict[str, Any] = {
        "detectedMarkers": int(len(detections)),
        "detectedCircles": int(len(detected_circles)),
        "assignedCircles": int(len(assigned_circle_camera)),
        "detectedFeatures": int(len(camera_points)),
        "detectedCorners": int(len(camera_points)),
        "cameraQuad": [[round_metric(value) for value in point] for point in dst_corners.tolist()],
    }
    estimated = None
    inliers: list[int] = []
    errors = np.array([], dtype=np.float32)
    if len(camera_points) >= 16:
        estimated, inlier_mask = cv2.findHomography(np.float32(source_points), np.float32(camera_points), cv2.RANSAC, 3.0, maxIters=3000, confidence=0.995)
        if estimated is not None and inlier_mask is not None:
            inliers = [int(index) for index, keep in enumerate(inlier_mask.ravel().tolist()) if int(keep) == 1]
            projected = cv2.perspectiveTransform(np.float32(source_points).reshape(1, -1, 2), estimated).reshape(-1, 2)
            true_projected = cv2.perspectiveTransform(np.float32(source_points).reshape(1, -1, 2), true_homography).reshape(-1, 2)
            errors = np.linalg.norm(projected - true_projected, axis=1)
    surface_errors = holdout_surface_errors(estimated, true_homography, projector_width, projector_height)
    report.update(homography_report(errors, inliers, estimated, surface_errors))

    marker_overlay = cv2.cvtColor(marker_frame, cv2.COLOR_GRAY2BGR)
    circle_overlay = cv2.cvtColor(circle_frame, cv2.COLOR_GRAY2BGR)
    draw_detected_markers(marker_overlay, detections)
    if len(detected_circles):
        draw_detected_circles(circle_overlay, detected_circles)
    if len(assigned_circle_camera):
        draw_assigned_circles(circle_overlay, np.float32(assigned_circle_camera))
    if estimated is not None:
        draw_projected_outline(marker_overlay, estimated, projector_width, projector_height)
        draw_projected_outline(circle_overlay, estimated, projector_width, projector_height)
    overlay = np.concatenate([marker_overlay, circle_overlay], axis=1)
    return {"report": report, "overlay": overlay}


def simulate_targeted_hybrid_trial(
    marker_pattern: np.ndarray,
    marker_corners: dict[int, np.ndarray],
    camera_width: int,
    camera_height: int,
    rng: random.Random,
) -> dict[str, Any]:
    projector_height, projector_width = marker_pattern.shape[:2]
    src_corners = np.float32([[0, 0], [projector_width - 1, 0], [projector_width - 1, projector_height - 1], [0, projector_height - 1]])
    dst_corners = random_camera_quad(camera_width, camera_height, rng)
    true_homography = cv2.getPerspectiveTransform(src_corners, dst_corners)

    marker_frame = render_camera_frame(marker_pattern, true_homography, camera_width, camera_height, random.Random(rng.randint(0, 1_000_000_000)))
    detections = detect_markers(marker_frame)
    marker_source_points: list[np.ndarray] = []
    marker_camera_points: list[np.ndarray] = []
    for marker_id, corners in detections.items():
        projector = marker_corners.get(marker_id)
        if projector is None:
            continue
        marker_source_points.extend(projector)
        marker_camera_points.extend(corners)

    marker_estimate = None
    if len(marker_camera_points) >= 16:
        marker_estimate, _marker_inliers = cv2.findHomography(
            np.float32(marker_source_points),
            np.float32(marker_camera_points),
            cv2.RANSAC,
            3.0,
            maxIters=3000,
            confidence=0.995,
        )

    targeted_points = target_adapted_circle_points(projector_width, projector_height, marker_estimate, camera_width, camera_height)
    targeted_pattern = render_projected_circle_points(projector_width, projector_height, targeted_points, radius=15)
    circle_frame = render_camera_frame(targeted_pattern, true_homography, camera_width, camera_height, random.Random(rng.randint(0, 1_000_000_000)))
    detected_circles = detect_circle_centers(circle_frame)
    assigned_circle_source: list[np.ndarray] = []
    assigned_circle_camera: list[np.ndarray] = []
    if marker_estimate is not None and len(detected_circles):
        assigned_circle_source, assigned_circle_camera = assign_circles_from_seed(targeted_points, detected_circles, marker_estimate)

    source_points: list[np.ndarray] = []
    camera_points: list[np.ndarray] = []
    source_points.extend(marker_source_points)
    camera_points.extend(marker_camera_points)
    source_points.extend(assigned_circle_source)
    camera_points.extend(assigned_circle_camera)

    report: dict[str, Any] = {
        "detectedMarkers": int(len(detections)),
        "targetedCircles": int(len(targeted_points)),
        "detectedCircles": int(len(detected_circles)),
        "assignedCircles": int(len(assigned_circle_camera)),
        "detectedFeatures": int(len(camera_points)),
        "detectedCorners": int(len(camera_points)),
        "cameraQuad": [[round_metric(value) for value in point] for point in dst_corners.tolist()],
    }
    estimated = None
    inliers: list[int] = []
    errors = np.array([], dtype=np.float32)
    if len(camera_points) >= 16:
        estimated, inlier_mask = cv2.findHomography(np.float32(source_points), np.float32(camera_points), cv2.RANSAC, 3.0, maxIters=3000, confidence=0.995)
        if estimated is not None and inlier_mask is not None:
            inliers = [int(index) for index, keep in enumerate(inlier_mask.ravel().tolist()) if int(keep) == 1]
            projected = cv2.perspectiveTransform(np.float32(source_points).reshape(1, -1, 2), estimated).reshape(-1, 2)
            true_projected = cv2.perspectiveTransform(np.float32(source_points).reshape(1, -1, 2), true_homography).reshape(-1, 2)
            errors = np.linalg.norm(projected - true_projected, axis=1)
    surface_errors = holdout_surface_errors(estimated, true_homography, projector_width, projector_height)
    report.update(homography_report(errors, inliers, estimated, surface_errors))

    marker_overlay = cv2.cvtColor(marker_frame, cv2.COLOR_GRAY2BGR)
    circle_overlay = cv2.cvtColor(circle_frame, cv2.COLOR_GRAY2BGR)
    draw_detected_markers(marker_overlay, detections)
    if len(detected_circles):
        draw_detected_circles(circle_overlay, detected_circles)
    if len(assigned_circle_camera):
        draw_assigned_circles(circle_overlay, np.float32(assigned_circle_camera))
    if estimated is not None:
        draw_projected_outline(marker_overlay, estimated, projector_width, projector_height)
        draw_projected_outline(circle_overlay, estimated, projector_width, projector_height)
    overlay = np.concatenate([marker_overlay, circle_overlay], axis=1)
    return {"report": report, "overlay": overlay}


def simulate_lens_stress_trial(
    marker_corners: dict[int, np.ndarray],
    circle_points: np.ndarray,
    projector_width: int,
    projector_height: int,
    camera_width: int,
    camera_height: int,
    rng: random.Random,
) -> dict[str, Any]:
    src_corners = np.float32([[0, 0], [projector_width - 1, 0], [projector_width - 1, projector_height - 1], [0, projector_height - 1]])
    dst_corners = random_camera_quad(camera_width, camera_height, rng)
    true_homography = cv2.getPerspectiveTransform(src_corners, dst_corners)
    source_points = active_feature_points(marker_corners, circle_points)
    ideal_points = cv2.perspectiveTransform(source_points.reshape(1, -1, 2), true_homography).reshape(-1, 2)

    camera_matrix, dist_coeffs = synthetic_camera_model(camera_width, camera_height)
    distorted_points = distort_points(ideal_points, camera_matrix, dist_coeffs)
    noise = np.random.default_rng(rng.randint(0, 1_000_000)).normal(0, rng.uniform(0.08, 0.35), distorted_points.shape)
    distorted_points = (distorted_points + noise).astype(np.float32)
    keep = visible_point_mask(distorted_points, camera_width, camera_height)
    keep &= random_feature_keep_mask(distorted_points, camera_width, camera_height, rng)
    kept_source = source_points[keep]
    kept_ideal = ideal_points[keep]
    kept_distorted = distorted_points[keep]

    raw_report = solve_homography_metric(kept_source, kept_distorted, kept_distorted)
    raw_vs_ideal_report = solve_homography_metric(kept_source, kept_distorted, kept_ideal)
    undistorted_points = undistort_points(kept_distorted, camera_matrix, dist_coeffs)
    undistorted_report = solve_homography_metric(kept_source, undistorted_points, kept_ideal)
    return {
        "keptFeatures": int(len(kept_source)),
        "cameraQuad": [[round_metric(value) for value in point] for point in dst_corners.tolist()],
        "distortion": {
            "fx": round_metric(float(camera_matrix[0, 0])),
            "fy": round_metric(float(camera_matrix[1, 1])),
            "cx": round_metric(float(camera_matrix[0, 2])),
            "cy": round_metric(float(camera_matrix[1, 2])),
            "k1": round_metric(float(dist_coeffs[0])),
            "k2": round_metric(float(dist_coeffs[1])),
        },
        "rawDistortedSpace": raw_report,
        "rawComparedToUndistortedTruth": raw_vs_ideal_report,
        "knownUndistortion": undistorted_report,
    }


def simulate_projector_distortion_stress_trial(
    marker_corners: dict[int, np.ndarray],
    circle_points: np.ndarray,
    projector_width: int,
    projector_height: int,
    camera_width: int,
    camera_height: int,
    rng: random.Random,
) -> dict[str, Any]:
    src_corners = np.float32([[0, 0], [projector_width - 1, 0], [projector_width - 1, projector_height - 1], [0, projector_height - 1]])
    dst_corners = random_camera_quad(camera_width, camera_height, rng)
    true_homography = cv2.getPerspectiveTransform(src_corners, dst_corners)
    surface_circle_points = target_adapted_circle_points(projector_width, projector_height, None, camera_width, camera_height)
    source_points = active_feature_points(marker_corners, surface_circle_points)
    holdout_points = holdout_surface_points(projector_width, projector_height)

    projector_matrix, dist_coeffs = synthetic_projector_model(projector_width, projector_height)
    displayed_source_points = distort_points(source_points, projector_matrix, dist_coeffs)
    displayed_holdout_points = distort_points(holdout_points, projector_matrix, dist_coeffs)
    observed_points = cv2.perspectiveTransform(displayed_source_points.reshape(1, -1, 2), true_homography).reshape(-1, 2)
    holdout_truth = cv2.perspectiveTransform(displayed_holdout_points.reshape(1, -1, 2), true_homography).reshape(-1, 2)

    noise = np.random.default_rng(rng.randint(0, 1_000_000)).normal(0, rng.uniform(0.06, 0.22), observed_points.shape)
    observed_points = (observed_points + noise).astype(np.float32)
    keep = visible_point_mask(observed_points, camera_width, camera_height)
    keep &= random_feature_keep_mask(observed_points, camera_width, camera_height, rng)

    kept_commanded_source = source_points[keep]
    kept_displayed_source = displayed_source_points[keep]
    kept_observed = observed_points[keep]

    raw_report = solve_homography_metric(
        kept_commanded_source,
        kept_observed,
        kept_observed,
        holdout_source_points=holdout_points,
        holdout_truth_points=holdout_truth,
    )
    residual_mesh_report = residual_mesh_metric(
        kept_commanded_source,
        kept_observed,
        holdout_points,
        holdout_truth,
    )
    known_compensation_report = solve_homography_metric(
        kept_displayed_source,
        kept_observed,
        kept_observed,
        holdout_source_points=displayed_holdout_points,
        holdout_truth_points=holdout_truth,
    )
    return {
        "keptFeatures": int(len(kept_observed)),
        "cameraQuad": [[round_metric(value) for value in point] for point in dst_corners.tolist()],
        "distortion": {
            "fx": round_metric(float(projector_matrix[0, 0])),
            "fy": round_metric(float(projector_matrix[1, 1])),
            "cx": round_metric(float(projector_matrix[0, 2])),
            "cy": round_metric(float(projector_matrix[1, 2])),
            "k1": round_metric(float(dist_coeffs[0])),
            "k2": round_metric(float(dist_coeffs[1])),
        },
        "rawCommandedHomography": raw_report,
        "residualMeshCorrection": residual_mesh_report,
        "knownProjectorCompensation": known_compensation_report,
    }


def simulate_photometric_preflight_trial(
    marker_pattern: np.ndarray,
    marker_corners: dict[int, np.ndarray],
    camera_width: int,
    camera_height: int,
    rng: random.Random,
) -> dict[str, Any]:
    projector_height, projector_width = marker_pattern.shape[:2]
    src_corners = np.float32([[0, 0], [projector_width - 1, 0], [projector_width - 1, projector_height - 1], [0, projector_height - 1]])
    dst_corners = random_camera_quad(camera_width, camera_height, rng)
    true_homography = cv2.getPerspectiveTransform(src_corners, dst_corners)
    model = photometric_model(camera_width, camera_height, rng)
    black_frame = render_photometric_frame(np.zeros_like(marker_pattern), true_homography, camera_width, camera_height, model, random.Random(rng.randint(0, 1_000_000_000)))
    white_frame = render_photometric_frame(np.full_like(marker_pattern, 255), true_homography, camera_width, camera_height, model, random.Random(rng.randint(0, 1_000_000_000)))
    raw_frame = render_photometric_frame(marker_pattern, true_homography, camera_width, camera_height, model, random.Random(rng.randint(0, 1_000_000_000)))
    normalized_frame = normalize_with_preflight(raw_frame, black_frame, white_frame)

    raw_report, raw_estimated = solve_marker_frame(raw_frame, marker_corners, true_homography, projector_width, projector_height)
    normalized_report, normalized_estimated = solve_marker_frame(normalized_frame, marker_corners, true_homography, projector_width, projector_height)
    report = {
        "cameraQuad": [[round_metric(value) for value in point] for point in dst_corners.tolist()],
        "model": {
            "ambientBase": round_metric(model["ambientBase"]),
            "gainBase": round_metric(model["gainBase"]),
            "shadowStrength": round_metric(model["shadowStrength"]),
            "glareStrength": round_metric(model["glareStrength"]),
            "noiseSigma": round_metric(model["noiseSigma"]),
        },
        "raw": raw_report,
        "preflightNormalized": normalized_report,
    }

    raw_overlay = cv2.cvtColor(raw_frame, cv2.COLOR_GRAY2BGR)
    normalized_overlay = cv2.cvtColor(normalized_frame, cv2.COLOR_GRAY2BGR)
    draw_detected_markers(raw_overlay, detect_markers(raw_frame))
    draw_detected_markers(normalized_overlay, detect_markers(normalized_frame))
    if raw_estimated is not None:
        draw_projected_outline(raw_overlay, raw_estimated, projector_width, projector_height)
    if normalized_estimated is not None:
        draw_projected_outline(normalized_overlay, normalized_estimated, projector_width, projector_height)
    overlay = np.concatenate([raw_overlay, normalized_overlay], axis=1)
    return {"report": report, "overlay": overlay}


def solve_marker_frame(
    frame: np.ndarray,
    marker_corners: dict[int, np.ndarray],
    true_homography: np.ndarray,
    projector_width: int,
    projector_height: int,
) -> tuple[dict[str, Any], np.ndarray | None]:
    detections = detect_markers(frame)
    source_points: list[np.ndarray] = []
    camera_points: list[np.ndarray] = []
    for marker_id, corners in detections.items():
        projector = marker_corners.get(marker_id)
        if projector is None:
            continue
        source_points.extend(projector)
        camera_points.extend(corners)

    report: dict[str, Any] = {
        "detectedMarkers": int(len(detections)),
        "detectedCorners": int(len(camera_points)),
    }
    estimated = None
    inliers: list[int] = []
    errors = np.array([], dtype=np.float32)
    if len(camera_points) >= 16:
        estimated, inlier_mask = cv2.findHomography(np.float32(source_points), np.float32(camera_points), cv2.RANSAC, 3.0, maxIters=3000, confidence=0.995)
        if estimated is not None and inlier_mask is not None:
            inliers = [int(index) for index, keep in enumerate(inlier_mask.ravel().tolist()) if int(keep) == 1]
            projected = cv2.perspectiveTransform(np.float32(source_points).reshape(1, -1, 2), estimated).reshape(-1, 2)
            true_projected = cv2.perspectiveTransform(np.float32(source_points).reshape(1, -1, 2), true_homography).reshape(-1, 2)
            errors = np.linalg.norm(projected - true_projected, axis=1)
    surface_errors = holdout_surface_errors(estimated, true_homography, projector_width, projector_height)
    report.update(homography_report(errors, inliers, estimated, surface_errors))
    return report, estimated


def active_feature_points(marker_corners: dict[int, np.ndarray], circle_points: np.ndarray) -> np.ndarray:
    points: list[np.ndarray] = []
    for marker_id in sorted(marker_corners):
        points.extend(marker_corners[marker_id])
    points.extend(circle_points)
    return np.float32(points)


def synthetic_camera_model(width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    focal = float(max(width, height) * 0.82)
    camera_matrix = np.float32([[focal, 0, width / 2], [0, focal, height / 2], [0, 0, 1]])
    dist_coeffs = np.float32([-0.24, 0.08, 0.0, 0.0, 0.0])
    return camera_matrix, dist_coeffs


def synthetic_projector_model(width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    focal = float(max(width, height) * 0.90)
    projector_matrix = np.float32([[focal, 0, width / 2], [0, focal, height / 2], [0, 0, 1]])
    dist_coeffs = np.float32([-0.16, 0.045, 0.0, 0.0, 0.0])
    return projector_matrix, dist_coeffs


def distort_points(points: np.ndarray, camera_matrix: np.ndarray, dist_coeffs: np.ndarray) -> np.ndarray:
    fx = float(camera_matrix[0, 0])
    fy = float(camera_matrix[1, 1])
    cx = float(camera_matrix[0, 2])
    cy = float(camera_matrix[1, 2])
    k1 = float(dist_coeffs[0])
    k2 = float(dist_coeffs[1])
    x = (points[:, 0] - cx) / fx
    y = (points[:, 1] - cy) / fy
    r2 = x * x + y * y
    scale = 1.0 + k1 * r2 + k2 * r2 * r2
    xd = x * scale
    yd = y * scale
    return np.float32(np.column_stack([fx * xd + cx, fy * yd + cy]))


def undistort_points(points: np.ndarray, camera_matrix: np.ndarray, dist_coeffs: np.ndarray) -> np.ndarray:
    undistorted = cv2.undistortPoints(points.reshape(-1, 1, 2), camera_matrix, dist_coeffs, P=camera_matrix)
    return undistorted.reshape(-1, 2).astype(np.float32)


def visible_point_mask(points: np.ndarray, width: int, height: int) -> np.ndarray:
    return (points[:, 0] >= 0) & (points[:, 0] < width) & (points[:, 1] >= 0) & (points[:, 1] < height)


def random_feature_keep_mask(points: np.ndarray, width: int, height: int, rng: random.Random) -> np.ndarray:
    keep = np.ones(len(points), dtype=bool)
    if rng.random() < 0.35:
        x = rng.uniform(width * 0.10, width * 0.75)
        y = rng.uniform(height * 0.10, height * 0.75)
        w = rng.uniform(width * 0.08, width * 0.18)
        h = rng.uniform(height * 0.08, height * 0.18)
        inside = (points[:, 0] >= x) & (points[:, 0] <= x + w) & (points[:, 1] >= y) & (points[:, 1] <= y + h)
        keep &= ~inside
    random_keep = np.array([rng.random() > 0.04 for _ in range(len(points))], dtype=bool)
    keep &= random_keep
    return keep


def holdout_surface_points(width: int, height: int) -> np.ndarray:
    xs = np.linspace(width * 0.04, width * 0.96, 9)
    ys = np.linspace(height * 0.04, height * 0.96, 7)
    return np.float32([[float(x), float(y)] for y in ys for x in xs])


def holdout_surface_errors(estimated: np.ndarray | None, true_homography: np.ndarray, width: int, height: int) -> np.ndarray:
    if estimated is None:
        return np.array([], dtype=np.float32)
    points = holdout_surface_points(width, height)
    projected = cv2.perspectiveTransform(points.reshape(1, -1, 2), estimated).reshape(-1, 2)
    truth = cv2.perspectiveTransform(points.reshape(1, -1, 2), true_homography).reshape(-1, 2)
    return np.linalg.norm(projected - truth, axis=1)


def solve_homography_metric(
    source_points: np.ndarray,
    observed_points: np.ndarray,
    truth_points: np.ndarray,
    holdout_source_points: np.ndarray | None = None,
    holdout_truth_points: np.ndarray | None = None,
) -> dict[str, Any]:
    if len(source_points) < 16:
        return {
            "decision": "refuse",
            "homographySolved": False,
            "inlierFeatures": 0,
            "medianErrorPx": None,
            "p95ErrorPx": None,
            "maxErrorPx": None,
            "medianSurfaceErrorPx": None,
            "p95SurfaceErrorPx": None,
            "maxSurfaceErrorPx": None,
        }
    estimated, inlier_mask = cv2.findHomography(source_points, observed_points, cv2.RANSAC, 3.0, maxIters=3000, confidence=0.995)
    if estimated is None or inlier_mask is None:
        return {
            "decision": "refuse",
            "homographySolved": False,
            "inlierFeatures": 0,
            "medianErrorPx": None,
            "p95ErrorPx": None,
            "maxErrorPx": None,
            "medianSurfaceErrorPx": None,
            "p95SurfaceErrorPx": None,
            "maxSurfaceErrorPx": None,
        }
    projected = cv2.perspectiveTransform(source_points.reshape(1, -1, 2), estimated).reshape(-1, 2)
    errors = np.linalg.norm(projected - truth_points, axis=1)
    surface_errors = np.array([], dtype=np.float32)
    if holdout_source_points is not None and holdout_truth_points is not None and len(holdout_source_points):
        projected_holdout = cv2.perspectiveTransform(holdout_source_points.reshape(1, -1, 2), estimated).reshape(-1, 2)
        surface_errors = np.linalg.norm(projected_holdout - holdout_truth_points, axis=1)
    p95 = float(np.percentile(errors, 95))
    surface_p95 = None if len(surface_errors) == 0 else float(np.percentile(surface_errors, 95))
    inliers = int(np.count_nonzero(inlier_mask))
    return {
        "decision": "accepted-active-calibration"
        if inliers >= 16 and p95 <= 3.0 and (surface_p95 is None or surface_p95 <= 3.0)
        else "candidate-active-calibration",
        "homographySolved": True,
        "inlierFeatures": inliers,
        "medianErrorPx": round_metric(float(np.median(errors))),
        "p95ErrorPx": round_metric(p95),
        "maxErrorPx": round_metric(float(np.max(errors))),
        "medianSurfaceErrorPx": None if len(surface_errors) == 0 else round_metric(float(np.median(surface_errors))),
        "p95SurfaceErrorPx": None if surface_p95 is None else round_metric(surface_p95),
        "maxSurfaceErrorPx": None if len(surface_errors) == 0 else round_metric(float(np.max(surface_errors))),
    }


def residual_mesh_metric(source_points: np.ndarray, observed_points: np.ndarray, holdout_source_points: np.ndarray, holdout_truth_points: np.ndarray) -> dict[str, Any]:
    if len(source_points) < 16:
        return {
            "decision": "refuse",
            "homographySolved": False,
            "inlierFeatures": 0,
            "medianP95FeatureErrorPx": None,
            "medianErrorPx": None,
            "p95ErrorPx": None,
            "maxErrorPx": None,
            "medianSurfaceErrorPx": None,
            "p95SurfaceErrorPx": None,
            "maxSurfaceErrorPx": None,
        }
    estimated, inlier_mask = cv2.findHomography(source_points, observed_points, cv2.RANSAC, 3.0, maxIters=3000, confidence=0.995)
    if estimated is None or inlier_mask is None:
        return {
            "decision": "refuse",
            "homographySolved": False,
            "inlierFeatures": 0,
            "medianErrorPx": None,
            "p95ErrorPx": None,
            "maxErrorPx": None,
            "medianSurfaceErrorPx": None,
            "p95SurfaceErrorPx": None,
            "maxSurfaceErrorPx": None,
        }
    projected_source = cv2.perspectiveTransform(source_points.reshape(1, -1, 2), estimated).reshape(-1, 2)
    residuals = observed_points - projected_source
    corrected_source = projected_source + interpolate_residuals(source_points, residuals, source_points)
    feature_errors = np.linalg.norm(corrected_source - observed_points, axis=1)
    projected_holdout = cv2.perspectiveTransform(holdout_source_points.reshape(1, -1, 2), estimated).reshape(-1, 2)
    corrected_holdout = projected_holdout + interpolate_residuals(source_points, residuals, holdout_source_points)
    surface_errors = np.linalg.norm(corrected_holdout - holdout_truth_points, axis=1)
    feature_p95 = float(np.percentile(feature_errors, 95))
    surface_p95 = float(np.percentile(surface_errors, 95))
    inliers = int(np.count_nonzero(inlier_mask))
    return {
        "decision": "accepted-active-calibration" if inliers >= 16 and feature_p95 <= 3.0 and surface_p95 <= 3.0 else "candidate-active-calibration",
        "homographySolved": True,
        "inlierFeatures": inliers,
        "medianErrorPx": round_metric(float(np.median(feature_errors))),
        "p95ErrorPx": round_metric(feature_p95),
        "maxErrorPx": round_metric(float(np.max(feature_errors))),
        "medianSurfaceErrorPx": round_metric(float(np.median(surface_errors))),
        "p95SurfaceErrorPx": round_metric(surface_p95),
        "maxSurfaceErrorPx": round_metric(float(np.max(surface_errors))),
    }


def interpolate_residuals(source_points: np.ndarray, residuals: np.ndarray, query_points: np.ndarray, k: int = 8) -> np.ndarray:
    if len(source_points) == 0 or len(query_points) == 0:
        return np.zeros((len(query_points), 2), dtype=np.float32)
    output = []
    for query in query_points:
        deltas = source_points - query
        distances = np.sqrt(np.sum(deltas * deltas, axis=1))
        order = np.argsort(distances)[: min(k, len(distances))]
        nearest = distances[order]
        if len(nearest) and nearest[0] < 1e-6:
            output.append(residuals[order[0]])
            continue
        weights = 1.0 / np.maximum(nearest, 1e-6) ** 2
        value = np.sum(residuals[order] * weights.reshape(-1, 1), axis=0) / max(1e-9, float(np.sum(weights)))
        output.append(value)
    return np.float32(output)


def render_camera_frame(pattern: np.ndarray, true_homography: np.ndarray, camera_width: int, camera_height: int, rng: random.Random) -> np.ndarray:
    frame = np.full((camera_height, camera_width), rng.randint(18, 48), dtype=np.uint8)
    warped = cv2.warpPerspective(pattern, true_homography, (camera_width, camera_height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    frame = np.maximum(frame, warped)
    return apply_camera_artifacts(frame, rng)


def photometric_model(width: int, height: int, rng: random.Random) -> dict[str, Any]:
    yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
    xn = (xx / max(1, width - 1)) - 0.5
    yn = (yy / max(1, height - 1)) - 0.5
    ambient_base = rng.uniform(18.0, 48.0)
    ambient = ambient_base + rng.uniform(-18.0, 18.0) * xn + rng.uniform(-16.0, 16.0) * yn
    gain_base = rng.uniform(0.70, 1.12)
    gain = gain_base + rng.uniform(-0.55, 0.55) * xn + rng.uniform(-0.45, 0.45) * yn
    shadow_cx = rng.uniform(width * 0.18, width * 0.82)
    shadow_cy = rng.uniform(height * 0.18, height * 0.82)
    shadow_rx = rng.uniform(width * 0.11, width * 0.26)
    shadow_ry = rng.uniform(height * 0.10, height * 0.24)
    shadow = np.exp(-(((xx - shadow_cx) / shadow_rx) ** 2 + ((yy - shadow_cy) / shadow_ry) ** 2))
    shadow_strength = rng.uniform(0.42, 0.78)
    gain *= 1.0 - shadow_strength * shadow
    glare_cx = rng.uniform(width * 0.20, width * 0.80)
    glare_cy = rng.uniform(height * 0.18, height * 0.82)
    glare_rx = rng.uniform(width * 0.05, width * 0.13)
    glare_ry = rng.uniform(height * 0.04, height * 0.11)
    glare_strength = rng.uniform(42.0, 105.0)
    glare = glare_strength * np.exp(-(((xx - glare_cx) / glare_rx) ** 2 + ((yy - glare_cy) / glare_ry) ** 2))
    return {
        "ambientBase": ambient_base,
        "gainBase": gain_base,
        "ambient": ambient.astype(np.float32),
        "gain": np.clip(gain, 0.05, 1.35).astype(np.float32),
        "glare": glare.astype(np.float32),
        "shadowStrength": shadow_strength,
        "glareStrength": glare_strength,
        "noiseSigma": rng.uniform(3.0, 8.0),
    }


def render_photometric_frame(pattern: np.ndarray, true_homography: np.ndarray, camera_width: int, camera_height: int, model: dict[str, Any], rng: random.Random) -> np.ndarray:
    warped = cv2.warpPerspective(pattern, true_homography, (camera_width, camera_height), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0).astype(np.float32)
    frame = model["ambient"] + warped * model["gain"]
    if warped.max() > 0:
        frame += model["glare"] * (warped / 255.0)
    noise = np.random.default_rng(rng.randint(0, 1_000_000)).normal(0, float(model["noiseSigma"]), frame.shape)
    frame += noise
    blur = rng.choice([1, 1, 3])
    frame = np.clip(frame, 0, 255).astype(np.uint8)
    if blur > 1:
        frame = cv2.GaussianBlur(frame, (blur, blur), 0)
    return frame


def normalize_with_preflight(raw_frame: np.ndarray, black_frame: np.ndarray, white_frame: np.ndarray) -> np.ndarray:
    raw = raw_frame.astype(np.float32)
    black = black_frame.astype(np.float32)
    white = white_frame.astype(np.float32)
    denom = np.maximum(white - black, 8.0)
    normalized = (raw - black) / denom * 255.0
    normalized = np.clip(normalized, 0, 255).astype(np.uint8)
    normalized = cv2.medianBlur(normalized, 3)
    return normalized


def random_camera_quad(width: int, height: int, rng: random.Random) -> np.ndarray:
    margin_x = width * 0.12
    margin_y = height * 0.12
    top_y = rng.uniform(margin_y * 0.6, margin_y * 1.6)
    bottom_y = rng.uniform(height - margin_y * 1.7, height - margin_y * 0.4)
    left_x = rng.uniform(margin_x * 0.4, margin_x * 1.5)
    right_x = rng.uniform(width - margin_x * 1.5, width - margin_x * 0.4)
    skew = rng.uniform(-width * 0.10, width * 0.10)
    return np.float32(
        [
            [left_x + rng.uniform(-30, 50), top_y + rng.uniform(-20, 30)],
            [right_x + skew + rng.uniform(-50, 30), top_y + rng.uniform(-25, 35)],
            [right_x + rng.uniform(-40, 40), bottom_y + rng.uniform(-35, 25)],
            [left_x - skew + rng.uniform(-30, 50), bottom_y + rng.uniform(-25, 35)],
        ]
    )


def apply_camera_artifacts(frame: np.ndarray, rng: random.Random) -> np.ndarray:
    result = frame.astype(np.float32)
    result *= rng.uniform(0.75, 1.20)
    result += rng.uniform(-6, 12)
    noise = np.random.default_rng(rng.randint(0, 1_000_000)).normal(0, rng.uniform(1.5, 5.0), result.shape)
    result += noise
    result = np.clip(result, 0, 255).astype(np.uint8)
    if rng.random() < 0.35:
        x = rng.randint(0, max(1, frame.shape[1] - 220))
        y = rng.randint(0, max(1, frame.shape[0] - 180))
        w = rng.randint(80, 220)
        h = rng.randint(60, 180)
        cv2.rectangle(result, (x, y), (min(frame.shape[1] - 1, x + w), min(frame.shape[0] - 1, y + h)), rng.randint(20, 70), -1)
    blur = rng.choice([1, 1, 3, 3, 5])
    if blur > 1:
        result = cv2.GaussianBlur(result, (blur, blur), 0)
    return result


def detect_markers(frame: np.ndarray) -> dict[int, np.ndarray]:
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    parameters = cv2.aruco.DetectorParameters()
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    detector = cv2.aruco.ArucoDetector(dictionary, parameters)
    corners, ids, _rejected = detector.detectMarkers(frame)
    if ids is None:
        return {}
    return {int(marker_id[0]): np.float32(corner.reshape(4, 2)) for marker_id, corner in zip(ids, corners)}


def detect_charuco_corners(frame: np.ndarray, board: Any) -> dict[int, np.ndarray]:
    detector = cv2.aruco.CharucoDetector(board)
    corners, ids, _marker_corners, _marker_ids = detector.detectBoard(frame)
    if ids is None or corners is None:
        return {}
    return {int(corner_id[0]): np.float32(corner.reshape(2)) for corner_id, corner in zip(ids, corners)}


def detect_circle_grid(frame: np.ndarray, circle_shape: tuple[int, int]) -> np.ndarray | None:
    rows, columns = circle_shape
    _threshold, binary = cv2.threshold(frame, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    component_count, _labels, stats, centroids = cv2.connectedComponentsWithStats(binary, 8)
    centers = []
    for index in range(1, component_count):
        area = int(stats[index, cv2.CC_STAT_AREA])
        width = int(stats[index, cv2.CC_STAT_WIDTH])
        height = int(stats[index, cv2.CC_STAT_HEIGHT])
        if not (80 <= area <= 2800 and 8 <= width <= 90 and 8 <= height <= 90):
            continue
        ratio = width / max(1, height)
        if 0.45 <= ratio <= 2.25:
            centers.append(centroids[index])
    expected = rows * columns
    if len(centers) != expected:
        return None
    points = np.float32(centers)
    order = np.argsort(points[:, 1])
    sorted_by_y = points[order]
    rows_out = []
    for row_index in range(rows):
        row = sorted_by_y[row_index * columns : (row_index + 1) * columns]
        if len(row) != columns:
            return None
        rows_out.append(row[np.argsort(row[:, 0])])
    return np.float32([point for row in rows_out for point in row])


def detect_asymmetric_circle_grid(frame: np.ndarray, circle_shape: tuple[int, int]) -> np.ndarray | None:
    rows, columns = circle_shape
    params = cv2.SimpleBlobDetector_Params()
    params.filterByColor = True
    params.blobColor = 255
    params.filterByArea = True
    params.minArea = 60
    params.maxArea = 4500
    params.filterByCircularity = False
    params.filterByInertia = False
    params.filterByConvexity = False
    detector = cv2.SimpleBlobDetector_create(params)
    _threshold, binary = cv2.threshold(frame, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    ok, centers = cv2.findCirclesGrid(
        binary,
        (columns, rows),
        flags=cv2.CALIB_CB_ASYMMETRIC_GRID | cv2.CALIB_CB_CLUSTERING,
        blobDetector=detector,
    )
    if not ok or centers is None:
        return None
    return centers.reshape(-1, 2).astype(np.float32)


def detect_circle_centers(frame: np.ndarray) -> np.ndarray:
    _threshold, binary = cv2.threshold(frame, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    component_count, _labels, stats, centroids = cv2.connectedComponentsWithStats(binary, 8)
    centers = []
    for index in range(1, component_count):
        area = int(stats[index, cv2.CC_STAT_AREA])
        width = int(stats[index, cv2.CC_STAT_WIDTH])
        height = int(stats[index, cv2.CC_STAT_HEIGHT])
        if not (80 <= area <= 2800 and 8 <= width <= 90 and 8 <= height <= 90):
            continue
        ratio = width / max(1, height)
        if 0.45 <= ratio <= 2.25:
                centers.append(centroids[index])
    return np.float32(centers)


def mask_detected_marker_regions(frame: np.ndarray, detections: dict[int, np.ndarray], padding: float) -> np.ndarray:
    output = frame.copy()
    for corners in detections.values():
        center = np.mean(corners, axis=0)
        expanded = []
        for corner in corners:
            vector = corner - center
            length = float(np.linalg.norm(vector))
            scale = 1.0 if length < 1e-6 else 1.0 + (padding / length)
            expanded.append(center + vector * scale)
        cv2.fillConvexPoly(output, np.rint(np.float32(expanded)).astype(np.int32), 0, cv2.LINE_AA)
    return output


def assign_circles_from_seed(circle_points: np.ndarray, detected_points: np.ndarray, seed_homography: np.ndarray) -> tuple[list[np.ndarray], list[np.ndarray]]:
    projected = cv2.perspectiveTransform(circle_points.reshape(1, -1, 2), seed_homography).reshape(-1, 2)
    candidates = []
    for source_index, point in enumerate(projected):
        deltas = detected_points - point
        distances = np.sqrt(np.sum(deltas * deltas, axis=1))
        for detected_index, distance in enumerate(distances.tolist()):
            if distance <= 22.0:
                candidates.append((float(distance), source_index, detected_index))
    candidates.sort(key=lambda item: item[0])
    used_sources: set[int] = set()
    used_detected: set[int] = set()
    source_out: list[np.ndarray] = []
    camera_out: list[np.ndarray] = []
    for _distance, source_index, detected_index in candidates:
        if source_index in used_sources or detected_index in used_detected:
            continue
        used_sources.add(source_index)
        used_detected.add(detected_index)
        source_out.append(circle_points[source_index])
        camera_out.append(detected_points[detected_index])
    return source_out, camera_out


def homography_report(errors: np.ndarray, inliers: list[int], estimated: np.ndarray | None, surface_errors: np.ndarray | None = None) -> dict[str, Any]:
    if estimated is None or len(errors) == 0:
        return {
            "decision": "refuse",
            "homographySolved": False,
            "inlierCorners": 0,
            "medianCornerErrorPx": None,
            "p95CornerErrorPx": None,
            "maxCornerErrorPx": None,
            "medianSurfaceErrorPx": None,
            "p95SurfaceErrorPx": None,
            "maxSurfaceErrorPx": None,
        }
    p95 = float(np.percentile(errors, 95))
    surface_errors = np.array([], dtype=np.float32) if surface_errors is None else surface_errors
    surface_p95 = None if len(surface_errors) == 0 else float(np.percentile(surface_errors, 95))
    decision = "accepted-active-calibration" if len(inliers) >= 16 and p95 <= 3.0 and (surface_p95 is None or surface_p95 <= 3.0) else "candidate-active-calibration"
    return {
        "decision": decision,
        "homographySolved": True,
        "inlierCorners": int(len(inliers)),
        "medianCornerErrorPx": round_metric(float(np.median(errors))),
        "p95CornerErrorPx": round_metric(p95),
        "maxCornerErrorPx": round_metric(float(np.max(errors))),
        "medianSurfaceErrorPx": None if len(surface_errors) == 0 else round_metric(float(np.median(surface_errors))),
        "p95SurfaceErrorPx": None if surface_p95 is None else round_metric(surface_p95),
        "maxSurfaceErrorPx": None if len(surface_errors) == 0 else round_metric(float(np.max(surface_errors))),
    }


def draw_detected_markers(overlay: np.ndarray, detections: dict[int, np.ndarray]) -> None:
    for marker_id, corners in detections.items():
        pts = np.rint(corners).astype(np.int32)
        cv2.polylines(overlay, [pts], True, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(overlay, str(marker_id), tuple(pts[0]), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 180, 0), 1, cv2.LINE_AA)


def draw_detected_circles(overlay: np.ndarray, points: np.ndarray) -> None:
    for index, point in enumerate(points):
        x, y = int(round(float(point[0]))), int(round(float(point[1])))
        cv2.circle(overlay, (x, y), 7, (0, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(overlay, str(index), (x + 6, y - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 180, 0), 1, cv2.LINE_AA)


def draw_detected_points(overlay: np.ndarray, points: np.ndarray, color: tuple[int, int, int]) -> None:
    for index, point in enumerate(points):
        x, y = int(round(float(point[0]))), int(round(float(point[1])))
        cv2.circle(overlay, (x, y), 6, color, 2, cv2.LINE_AA)
        cv2.putText(overlay, str(index), (x + 5, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.34, color, 1, cv2.LINE_AA)


def draw_assigned_circles(overlay: np.ndarray, points: np.ndarray) -> None:
    for point in points:
        x, y = int(round(float(point[0]))), int(round(float(point[1])))
        cv2.circle(overlay, (x, y), 11, (255, 0, 255), 2, cv2.LINE_AA)


def draw_projected_outline(overlay: np.ndarray, homography: np.ndarray, width: int, height: int) -> None:
    corners = np.float32([[0, 0], [width - 1, 0], [width - 1, height - 1], [0, height - 1]]).reshape(1, -1, 2)
    projected = cv2.perspectiveTransform(corners, homography).reshape(-1, 2)
    cv2.polylines(overlay, [np.rint(projected).astype(np.int32)], True, (0, 120, 255), 2, cv2.LINE_AA)


def summarize(trials: list[dict[str, Any]], detected_key: str, mean_key: str) -> dict[str, Any]:
    decisions: dict[str, int] = {}
    for trial in trials:
        decisions[trial["decision"]] = decisions.get(trial["decision"], 0) + 1
    accepted = [trial for trial in trials if trial["decision"] == "accepted-active-calibration"]
    solved = [trial for trial in trials if trial["homographySolved"]]
    return {
        "total": len(trials),
        "decisions": decisions,
        "accepted": len(accepted),
        "solved": len(solved),
        mean_key: round_metric(sum(trial.get(detected_key, 0) for trial in trials) / max(1, len(trials))),
        "medianP95CornerErrorPx": None if not solved else round_metric(float(np.median([trial["p95CornerErrorPx"] for trial in solved]))),
        "maxP95CornerErrorPx": None if not solved else round_metric(float(max(trial["p95CornerErrorPx"] for trial in solved))),
        "medianP95SurfaceErrorPx": None
        if not solved
        else round_metric(float(np.median([trial["p95SurfaceErrorPx"] for trial in solved if trial.get("p95SurfaceErrorPx") is not None]))),
        "maxP95SurfaceErrorPx": None
        if not solved
        else round_metric(float(max(trial["p95SurfaceErrorPx"] for trial in solved if trial.get("p95SurfaceErrorPx") is not None))),
    }


def compare_summaries(candidate_trials: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    candidates = []
    for name, trials in candidate_trials.items():
        solved = [trial for trial in trials if trial["homographySolved"]]
        accepted = sum(1 for trial in trials if trial["decision"] == "accepted-active-calibration")
        median_p95 = None if not solved else round_metric(float(np.median([trial["p95CornerErrorPx"] for trial in solved])))
        surface_values = [trial["p95SurfaceErrorPx"] for trial in solved if trial.get("p95SurfaceErrorPx") is not None]
        median_surface_p95 = None if not surface_values else round_metric(float(np.median(surface_values)))
        candidates.append(
            {
                "name": name,
                "frameCount": CANDIDATE_FRAME_COUNTS.get(name),
                "accepted": accepted,
                "solved": len(solved),
                "medianP95CornerErrorPx": median_p95,
                "medianP95SurfaceErrorPx": median_surface_p95,
            }
        )
    candidates.sort(
        key=lambda item: (
            -int(item["accepted"]),
            float("inf") if item["medianP95SurfaceErrorPx"] is None else float(item["medianP95SurfaceErrorPx"]),
            float("inf") if item["medianP95CornerErrorPx"] is None else float(item["medianP95CornerErrorPx"]),
        )
    )
    recommendation = candidates[0]["name"] if candidates else "compare-on-hardware"
    one_frame = [candidate for candidate in candidates if candidate.get("frameCount") == 1 and candidate["accepted"] == max(item["accepted"] for item in candidates)]
    one_frame.sort(
        key=lambda item: (
            float("inf") if item["medianP95SurfaceErrorPx"] is None else float(item["medianP95SurfaceErrorPx"]),
            float("inf") if item["medianP95CornerErrorPx"] is None else float(item["medianP95CornerErrorPx"]),
        )
    )
    return {
        "candidates": candidates,
        "recommendation": recommendation,
        "fastestAcceptedRecommendation": None if not one_frame else one_frame[0]["name"],
        "note": "Synthetic comparison only; hardware pass still needs projector brightness, mat reflectivity, camera exposure, focus, and occlusion evidence.",
    }


def summarize_lens_stress(trials: list[dict[str, Any]]) -> dict[str, Any]:
    def summarize_section(name: str) -> dict[str, Any]:
        section = [trial[name] for trial in trials]
        solved = [item for item in section if item["homographySolved"]]
        decisions: dict[str, int] = {}
        for item in section:
            decisions[item["decision"]] = decisions.get(item["decision"], 0) + 1
        return {
            "decisions": decisions,
            "accepted": decisions.get("accepted-active-calibration", 0),
            "solved": len(solved),
            "medianP95ErrorPx": None if not solved else round_metric(float(np.median([item["p95ErrorPx"] for item in solved]))),
            "maxP95ErrorPx": None if not solved else round_metric(float(max(item["p95ErrorPx"] for item in solved))),
        }

    raw_truth = summarize_section("rawComparedToUndistortedTruth")
    undistorted = summarize_section("knownUndistortion")
    return {
        "total": len(trials),
        "meanKeptFeatures": round_metric(sum(trial["keptFeatures"] for trial in trials) / max(1, len(trials))),
        "rawDistortedSpace": summarize_section("rawDistortedSpace"),
        "rawComparedToUndistortedTruth": raw_truth,
        "knownUndistortion": undistorted,
        "medianP95ImprovementPx": (
            None
            if raw_truth["medianP95ErrorPx"] is None or undistorted["medianP95ErrorPx"] is None
            else round_metric(float(raw_truth["medianP95ErrorPx"] - undistorted["medianP95ErrorPx"]))
        ),
    }


def summarize_projector_distortion_stress(trials: list[dict[str, Any]]) -> dict[str, Any]:
    def summarize_section(name: str) -> dict[str, Any]:
        section = [trial[name] for trial in trials]
        solved = [item for item in section if item["homographySolved"]]
        decisions: dict[str, int] = {}
        for item in section:
            decisions[item["decision"]] = decisions.get(item["decision"], 0) + 1
        surface_values = [item["p95SurfaceErrorPx"] for item in solved if item.get("p95SurfaceErrorPx") is not None]
        return {
            "decisions": decisions,
            "accepted": decisions.get("accepted-active-calibration", 0),
            "solved": len(solved),
            "medianP95FeatureErrorPx": None if not solved else round_metric(float(np.median([item["p95ErrorPx"] for item in solved]))),
            "medianP95SurfaceErrorPx": None if not surface_values else round_metric(float(np.median(surface_values))),
            "maxP95SurfaceErrorPx": None if not surface_values else round_metric(float(max(surface_values))),
        }

    raw = summarize_section("rawCommandedHomography")
    residual_mesh = summarize_section("residualMeshCorrection")
    compensated = summarize_section("knownProjectorCompensation")
    return {
        "total": len(trials),
        "meanKeptFeatures": round_metric(sum(trial["keptFeatures"] for trial in trials) / max(1, len(trials))),
        "rawCommandedHomography": raw,
        "residualMeshCorrection": residual_mesh,
        "knownProjectorCompensation": compensated,
        "medianP95SurfaceImprovementPx": (
            None
            if raw["medianP95SurfaceErrorPx"] is None or compensated["medianP95SurfaceErrorPx"] is None
            else round_metric(float(raw["medianP95SurfaceErrorPx"] - compensated["medianP95SurfaceErrorPx"]))
        ),
        "medianP95ResidualMeshImprovementPx": (
            None
            if raw["medianP95SurfaceErrorPx"] is None or residual_mesh["medianP95SurfaceErrorPx"] is None
            else round_metric(float(raw["medianP95SurfaceErrorPx"] - residual_mesh["medianP95SurfaceErrorPx"]))
        ),
    }


def summarize_photometric_preflight(trials: list[dict[str, Any]]) -> dict[str, Any]:
    def summarize_section(name: str) -> dict[str, Any]:
        section = [trial[name] for trial in trials]
        solved = [item for item in section if item["homographySolved"]]
        decisions: dict[str, int] = {}
        for item in section:
            decisions[item["decision"]] = decisions.get(item["decision"], 0) + 1
        surface_values = [item["p95SurfaceErrorPx"] for item in solved if item.get("p95SurfaceErrorPx") is not None]
        return {
            "decisions": decisions,
            "accepted": decisions.get("accepted-active-calibration", 0),
            "solved": len(solved),
            "meanDetectedMarkers": round_metric(sum(item.get("detectedMarkers", 0) for item in section) / max(1, len(section))),
            "medianP95FeatureErrorPx": None if not solved else round_metric(float(np.median([item["p95CornerErrorPx"] for item in solved]))),
            "medianP95SurfaceErrorPx": None if not surface_values else round_metric(float(np.median(surface_values))),
        }

    raw = summarize_section("raw")
    preflight = summarize_section("preflightNormalized")
    return {
        "total": len(trials),
        "raw": raw,
        "preflightNormalized": preflight,
        "acceptedGain": int(preflight["accepted"] - raw["accepted"]),
        "meanDetectedMarkerGain": round_metric(float(preflight["meanDetectedMarkers"] - raw["meanDetectedMarkers"])),
    }


def render_markdown(report: dict[str, Any]) -> str:
    fiducials = report["summary"]["fiducials"]
    circles = report["summary"]["circleGrid"]
    charuco = report["summary"]["charuco"]
    asymmetric = report["summary"]["asymmetricCircleGrid"]
    composite = report["summary"]["compositeFiducialCircle"]
    perimeter = report["summary"]["perimeterFiducialCircle"]
    hybrid = report["summary"]["hybridTwoFrame"]
    targeted_hybrid = report["summary"]["targetedHybridTwoFrame"]
    lens = report["summary"]["lensStress"]
    projector = report["summary"]["projectorDistortionStress"]
    photometric = report["summary"]["photometricPreflightStress"]
    comparison = report["comparison"]
    lines = [
        "# Projected Active Calibration Simulation",
        "",
        "| Pattern | Accepted | Decisions | Mean Detections | Median Feature P95 | Median Surface P95 | Max Surface P95 |",
        "| --- | ---: | --- | ---: | ---: | ---: | ---: |",
        f"| Projected coded fiducials | {fiducials['accepted']}/{fiducials['total']} | `{json.dumps(fiducials['decisions'], sort_keys=True)}` | {fiducials['meanDetectedMarkers']} | {format_px(fiducials['medianP95CornerErrorPx'])} | {format_px(fiducials['medianP95SurfaceErrorPx'])} | {format_px(fiducials['maxP95SurfaceErrorPx'])} |",
        f"| Projected circle grid | {circles['accepted']}/{circles['total']} | `{json.dumps(circles['decisions'], sort_keys=True)}` | {circles['meanDetectedCircles']} | {format_px(circles['medianP95CornerErrorPx'])} | {format_px(circles['medianP95SurfaceErrorPx'])} | {format_px(circles['maxP95SurfaceErrorPx'])} |",
        f"| Projected ChArUco board | {charuco['accepted']}/{charuco['total']} | `{json.dumps(charuco['decisions'], sort_keys=True)}` | {charuco['meanDetectedCharucoCorners']} | {format_px(charuco['medianP95CornerErrorPx'])} | {format_px(charuco['medianP95SurfaceErrorPx'])} | {format_px(charuco['maxP95SurfaceErrorPx'])} |",
        f"| Projected asymmetric circle grid | {asymmetric['accepted']}/{asymmetric['total']} | `{json.dumps(asymmetric['decisions'], sort_keys=True)}` | {asymmetric['meanDetectedAsymmetricCircles']} | {format_px(asymmetric['medianP95CornerErrorPx'])} | {format_px(asymmetric['medianP95SurfaceErrorPx'])} | {format_px(asymmetric['maxP95SurfaceErrorPx'])} |",
        f"| One-frame fiducial + surface circles | {composite['accepted']}/{composite['total']} | `{json.dumps(composite['decisions'], sort_keys=True)}` | {composite['meanDetectedFeatures']} | {format_px(composite['medianP95CornerErrorPx'])} | {format_px(composite['medianP95SurfaceErrorPx'])} | {format_px(composite['maxP95SurfaceErrorPx'])} |",
        f"| One-frame perimeter fiducials + interior circles | {perimeter['accepted']}/{perimeter['total']} | `{json.dumps(perimeter['decisions'], sort_keys=True)}` | {perimeter['meanDetectedFeatures']} | {format_px(perimeter['medianP95CornerErrorPx'])} | {format_px(perimeter['medianP95SurfaceErrorPx'])} | {format_px(perimeter['maxP95SurfaceErrorPx'])} |",
        f"| Two-frame fiducial + circle refinement | {hybrid['accepted']}/{hybrid['total']} | `{json.dumps(hybrid['decisions'], sort_keys=True)}` | {hybrid['meanDetectedFeatures']} | {format_px(hybrid['medianP95CornerErrorPx'])} | {format_px(hybrid['medianP95SurfaceErrorPx'])} | {format_px(hybrid['maxP95SurfaceErrorPx'])} |",
        f"| Target-adapted fiducial + surface circles | {targeted_hybrid['accepted']}/{targeted_hybrid['total']} | `{json.dumps(targeted_hybrid['decisions'], sort_keys=True)}` | {targeted_hybrid['meanDetectedFeatures']} | {format_px(targeted_hybrid['medianP95CornerErrorPx'])} | {format_px(targeted_hybrid['medianP95SurfaceErrorPx'])} | {format_px(targeted_hybrid['maxP95SurfaceErrorPx'])} |",
        "",
        f"- Synthetic recommendation: `{comparison['recommendation']}`",
        f"- Fastest accepted one-frame recommendation: `{comparison['fastestAcceptedRecommendation']}`",
        f"- Caveat: {comparison['note']}",
        "",
        "## Lens-Distortion Stress",
        "",
        "Point-level stress test using the same active feature coordinates with synthetic radial camera distortion. This tests geometry compensation, not marker/blob detector robustness.",
        "",
        "| Solve Space | Accepted | Median P95 Error | Max P95 Error |",
        "| --- | ---: | ---: | ---: |",
        f"| Raw distorted camera pixels vs distorted observations | {lens['rawDistortedSpace']['accepted']}/{lens['total']} | {format_px(lens['rawDistortedSpace']['medianP95ErrorPx'])} | {format_px(lens['rawDistortedSpace']['maxP95ErrorPx'])} |",
        f"| Raw distorted camera pixels vs undistorted truth | {lens['rawComparedToUndistortedTruth']['accepted']}/{lens['total']} | {format_px(lens['rawComparedToUndistortedTruth']['medianP95ErrorPx'])} | {format_px(lens['rawComparedToUndistortedTruth']['maxP95ErrorPx'])} |",
        f"| Known camera undistortion before homography | {lens['knownUndistortion']['accepted']}/{lens['total']} | {format_px(lens['knownUndistortion']['medianP95ErrorPx'])} | {format_px(lens['knownUndistortion']['maxP95ErrorPx'])} |",
        "",
        f"- Mean kept features: `{lens['meanKeptFeatures']}`",
        f"- Median P95 improvement from known undistortion: `{format_px(lens['medianP95ImprovementPx'])}`",
        "",
        "## Projector-Distortion Stress",
        "",
        "Point-level stress test for nonlinear projector distortion. Raw commanded-pixel homography is compared against a known projector compensation model. This tests geometry compensation, not detector robustness.",
        "",
        "| Solve Space | Accepted | Median Feature P95 | Median Surface P95 | Max Surface P95 |",
        "| --- | ---: | ---: | ---: | ---: |",
        f"| Raw commanded projector pixels | {projector['rawCommandedHomography']['accepted']}/{projector['total']} | {format_px(projector['rawCommandedHomography']['medianP95FeatureErrorPx'])} | {format_px(projector['rawCommandedHomography']['medianP95SurfaceErrorPx'])} | {format_px(projector['rawCommandedHomography']['maxP95SurfaceErrorPx'])} |",
        f"| Residual mesh from active points | {projector['residualMeshCorrection']['accepted']}/{projector['total']} | {format_px(projector['residualMeshCorrection']['medianP95FeatureErrorPx'])} | {format_px(projector['residualMeshCorrection']['medianP95SurfaceErrorPx'])} | {format_px(projector['residualMeshCorrection']['maxP95SurfaceErrorPx'])} |",
        f"| Known projector compensation | {projector['knownProjectorCompensation']['accepted']}/{projector['total']} | {format_px(projector['knownProjectorCompensation']['medianP95FeatureErrorPx'])} | {format_px(projector['knownProjectorCompensation']['medianP95SurfaceErrorPx'])} | {format_px(projector['knownProjectorCompensation']['maxP95SurfaceErrorPx'])} |",
        "",
        f"- Mean kept features: `{projector['meanKeptFeatures']}`",
        f"- Median P95 surface improvement from residual mesh: `{format_px(projector['medianP95ResidualMeshImprovementPx'])}`",
        f"- Median P95 surface improvement from known projector compensation: `{format_px(projector['medianP95SurfaceImprovementPx'])}`",
        "",
        "## Photometric Preflight Stress",
        "",
        "Synthetic harsh-lighting check for black/white reference frames before projected marker detection. This tests exposure/shadow normalization, not physical projector brightness.",
        "",
        "| Input | Accepted | Mean Detected Markers | Median Feature P95 | Median Surface P95 |",
        "| --- | ---: | ---: | ---: | ---: |",
        f"| Raw marker frame | {photometric['raw']['accepted']}/{photometric['total']} | {photometric['raw']['meanDetectedMarkers']} | {format_px(photometric['raw']['medianP95FeatureErrorPx'])} | {format_px(photometric['raw']['medianP95SurfaceErrorPx'])} |",
        f"| Black/white normalized marker frame | {photometric['preflightNormalized']['accepted']}/{photometric['total']} | {photometric['preflightNormalized']['meanDetectedMarkers']} | {format_px(photometric['preflightNormalized']['medianP95FeatureErrorPx'])} | {format_px(photometric['preflightNormalized']['medianP95SurfaceErrorPx'])} |",
        "",
        f"- Accepted gain from preflight: `{photometric['acceptedGain']}`",
        f"- Mean detected marker gain from preflight: `{photometric['meanDetectedMarkerGain']}`",
        "",
        "## Fiducial Trials",
        "",
        "| Trial | Decision | Markers | Inlier Corners | Median Error | P95 Error |",
        "| ---: | --- | ---: | ---: | ---: | ---: |",
    ]
    for index, trial in enumerate(report["trials"]["fiducials"], start=1):
        lines.append(
            f"| {index} | `{trial['decision']}` | {trial['detectedMarkers']} | {trial['inlierCorners']} | "
            f"{format_px(trial['medianCornerErrorPx'])} | {format_px(trial['p95CornerErrorPx'])} |"
        )
    lines.extend(
        [
            "",
            "## Circle-Grid Trials",
            "",
            "| Trial | Decision | Circles | Inlier Centers | Median Error | P95 Error |",
            "| ---: | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for index, trial in enumerate(report["trials"]["circleGrid"], start=1):
        lines.append(
            f"| {index} | `{trial['decision']}` | {trial['detectedCircles']} | {trial['inlierCorners']} | "
            f"{format_px(trial['medianCornerErrorPx'])} | {format_px(trial['p95CornerErrorPx'])} |"
        )
    lines.extend(
        [
            "",
            "## ChArUco Trials",
            "",
            "| Trial | Decision | Corners | Inlier Corners | Median Error | P95 Error |",
            "| ---: | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for index, trial in enumerate(report["trials"]["charuco"], start=1):
        lines.append(
            f"| {index} | `{trial['decision']}` | {trial['detectedCharucoCorners']} | {trial['inlierCorners']} | "
            f"{format_px(trial['medianCornerErrorPx'])} | {format_px(trial['p95CornerErrorPx'])} |"
        )
    lines.extend(
        [
            "",
            "## Asymmetric Circle-Grid Trials",
            "",
            "| Trial | Decision | Circles | Inlier Centers | Median Error | P95 Error |",
            "| ---: | --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for index, trial in enumerate(report["trials"]["asymmetricCircleGrid"], start=1):
        lines.append(
            f"| {index} | `{trial['decision']}` | {trial['detectedCircles']} | {trial['inlierCorners']} | "
            f"{format_px(trial['medianCornerErrorPx'])} | {format_px(trial['p95CornerErrorPx'])} |"
        )
    lines.extend(
        [
            "",
            "## One-Frame Composite Trials",
            "",
            "| Trial | Decision | Markers | Targeted Circles | Detected Circles | Assigned Circles | Inlier Features | Median Error | P95 Error | Surface P95 |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for index, trial in enumerate(report["trials"]["compositeFiducialCircle"], start=1):
        lines.append(
            f"| {index} | `{trial['decision']}` | {trial['detectedMarkers']} | {trial['targetedCircles']} | "
            f"{trial['detectedCircles']} | {trial['assignedCircles']} | {trial['inlierCorners']} | "
            f"{format_px(trial['medianCornerErrorPx'])} | {format_px(trial['p95CornerErrorPx'])} | "
            f"{format_px(trial['p95SurfaceErrorPx'])} |"
        )
    lines.extend(
        [
            "",
            "## One-Frame Perimeter Composite Trials",
            "",
            "| Trial | Decision | Markers | Targeted Circles | Detected Circles | Assigned Circles | Inlier Features | Median Error | P95 Error | Surface P95 |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for index, trial in enumerate(report["trials"]["perimeterFiducialCircle"], start=1):
        lines.append(
            f"| {index} | `{trial['decision']}` | {trial['detectedMarkers']} | {trial['targetedCircles']} | "
            f"{trial['detectedCircles']} | {trial['assignedCircles']} | {trial['inlierCorners']} | "
            f"{format_px(trial['medianCornerErrorPx'])} | {format_px(trial['p95CornerErrorPx'])} | "
            f"{format_px(trial['p95SurfaceErrorPx'])} |"
        )
    lines.extend(
        [
            "",
            "## Hybrid Two-Frame Trials",
            "",
            "| Trial | Decision | Markers | Circles | Assigned Circles | Inlier Features | Median Error | P95 Error |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for index, trial in enumerate(report["trials"]["hybridTwoFrame"], start=1):
        lines.append(
            f"| {index} | `{trial['decision']}` | {trial['detectedMarkers']} | {trial['detectedCircles']} | "
            f"{trial['assignedCircles']} | {trial['inlierCorners']} | {format_px(trial['medianCornerErrorPx'])} | "
            f"{format_px(trial['p95CornerErrorPx'])} |"
        )
    lines.extend(
        [
            "",
            "## Target-Adapted Hybrid Two-Frame Trials",
            "",
            "| Trial | Decision | Markers | Targeted Circles | Detected Circles | Assigned Circles | Inlier Features | Median Error | P95 Error | Surface P95 |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for index, trial in enumerate(report["trials"]["targetedHybridTwoFrame"], start=1):
        lines.append(
            f"| {index} | `{trial['decision']}` | {trial['detectedMarkers']} | {trial['targetedCircles']} | "
            f"{trial['detectedCircles']} | {trial['assignedCircles']} | {trial['inlierCorners']} | "
            f"{format_px(trial['medianCornerErrorPx'])} | {format_px(trial['p95CornerErrorPx'])} | "
            f"{format_px(trial['p95SurfaceErrorPx'])} |"
        )
    lines.extend(
        [
            "",
            "Artifacts:",
            "",
            "- `projected-marker-pattern.png`",
            "- `projected-circle-grid-pattern.png`",
            "- `projected-charuco-pattern.png`",
            "- `projected-asymmetric-circle-grid-pattern.png`",
            "- `projected-composite-fiducial-circle-pattern.png`",
            "- `projected-perimeter-fiducial-interior-circle-pattern.png`",
            "- sample fiducial, circle-grid, ChArUco, asymmetric-circle-grid, composite, perimeter composite, hybrid two-frame, target-adapted hybrid, and photometric-preflight overlays for trials 01-04",
        ]
    )
    return "\n".join(lines)


def render_console(report: dict[str, Any]) -> str:
    fiducials = report["summary"]["fiducials"]
    circles = report["summary"]["circleGrid"]
    charuco = report["summary"]["charuco"]
    asymmetric = report["summary"]["asymmetricCircleGrid"]
    composite = report["summary"]["compositeFiducialCircle"]
    perimeter = report["summary"]["perimeterFiducialCircle"]
    hybrid = report["summary"]["hybridTwoFrame"]
    targeted_hybrid = report["summary"]["targetedHybridTwoFrame"]
    lens = report["summary"]["lensStress"]
    projector = report["summary"]["projectorDistortionStress"]
    photometric = report["summary"]["photometricPreflightStress"]
    comparison = report["comparison"]
    return "\n".join(
        [
            f"Projected active calibration sim: fiducials {fiducials['decisions']} circle-grid {circles['decisions']}",
            f"- fiducial median p95 corner error: {fiducials['medianP95CornerErrorPx']} px",
            f"- circle-grid median p95 center error: {circles['medianP95CornerErrorPx']} px",
            f"- ChArUco median p95 corner error: {charuco['medianP95CornerErrorPx']} px",
            f"- asymmetric circle-grid median p95 center error: {asymmetric['medianP95CornerErrorPx']} px",
            f"- one-frame composite median surface p95 error: {composite['medianP95SurfaceErrorPx']} px",
            f"- one-frame perimeter composite median surface p95 error: {perimeter['medianP95SurfaceErrorPx']} px",
            f"- hybrid two-frame median p95 feature error: {hybrid['medianP95CornerErrorPx']} px",
            f"- target-adapted hybrid median surface p95 error: {targeted_hybrid['medianP95SurfaceErrorPx']} px",
            f"- lens stress raw-vs-undistorted p95: {lens['rawComparedToUndistortedTruth']['medianP95ErrorPx']} px -> {lens['knownUndistortion']['medianP95ErrorPx']} px with known undistortion",
            f"- projector stress raw/mesh/compensated surface p95: {projector['rawCommandedHomography']['medianP95SurfaceErrorPx']} px -> {projector['residualMeshCorrection']['medianP95SurfaceErrorPx']} px -> {projector['knownProjectorCompensation']['medianP95SurfaceErrorPx']} px",
            f"- photometric preflight accepted: {photometric['raw']['accepted']}/{photometric['total']} raw -> {photometric['preflightNormalized']['accepted']}/{photometric['total']} normalized",
            f"- synthetic recommendation: {comparison['recommendation']}",
            f"- fastest accepted one-frame recommendation: {comparison['fastestAcceptedRecommendation']}",
            f"- artifacts: {report['outDir']}/report.md",
        ]
    )


def format_px(value: float | None) -> str:
    return "" if value is None else f"{value} px"


def round_metric(value: float) -> float:
    return round(float(value), 3)


if __name__ == "__main__":
    main()
