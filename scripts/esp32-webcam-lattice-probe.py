#!/usr/bin/env python3
"""Experimental ESP32 webcam lattice probe.

This is intentionally separate from the browser detector in
src/calibration/gridDetection.ts. It probes low-resolution, noisy ESP32 stills
for a manual seed candidate by enhancing dark grid strokes, sweeping Hough
parameters, fitting two periodic line families, then trimming the candidate so
the draggable handles stay mostly inside the image.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps

from real_camera_lattice_probe import (
    DirectionFamily,
    Segment,
    axial_angle_delta,
    detect_direction_families,
    intersect_normal_lines,
    order_corners,
    round_metric,
)


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class ProbeCandidate:
    score: float
    variant: str
    params: tuple[int, int, int, int]
    families: tuple[DirectionFamily, DirectionFamily]
    corners: np.ndarray
    columns: int
    rows: int
    in_frame_fraction: float
    area_ratio: float
    off_frame_ratio: float
    axis_alignment: float


@dataclass(frozen=True)
class FrameQuality:
    mean_luma: float
    contrast: float
    quality: str


def main() -> int:
    args = parse_args()
    started = time.perf_counter()
    image_path = resolve_repo_path(args.detect_image)
    image = load_bgr_image(image_path)
    quality = frame_quality(image)
    candidates = [] if quality.quality != "usable" else collect_candidates(image)
    selected = candidates[0] if candidates else None
    report = build_report(image_path, image, quality, selected, candidates, started)

    if args.out_dir:
      out_dir = resolve_repo_path(args.out_dir)
      out_dir.mkdir(parents=True, exist_ok=True)
      (out_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf8")
      if selected:
          write_overlay(out_dir / "overlay.png", image, selected)

    print(json.dumps(report, indent=2))
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe one low-resolution ESP32 webcam still for a grid seed.")
    parser.add_argument("--detect-image", required=True, help="Image path to analyze.")
    parser.add_argument("--out-dir", help="Optional output directory for report.json and overlay.png.")
    return parser.parse_args()


def resolve_repo_path(path: str | Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else ROOT / value


def load_bgr_image(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        rgb = np.array(image)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def collect_candidates(image: np.ndarray) -> list[ProbeCandidate]:
    variants = enhanced_variants(image)
    candidates: list[ProbeCandidate] = []
    parameter_sweep = [
        ("blackhat", 25, 80, 30, 22),
        ("blackhat", 25, 80, 18, 28),
        ("blackhat", 20, 70, 30, 22),
        ("blackhat", 20, 70, 12, 28),
        ("clahe-blackhat-mix", 45, 135, 24, 22),
    ]
    for variant_name, low, high, threshold, min_length in parameter_sweep:
        gray = variants[variant_name]
        segments = detect_segments(gray, low, high, threshold, min_length)
        if len(segments) < 10:
            continue
        families = [
            family
            for family in detect_direction_families(
                segments,
                image.shape[:2],
                angle_tolerance=14,
                min_pitch=16,
                max_pitch=80,
            )
            if family.period is not None
        ]
        if len(families) < 2:
            continue
        candidates.extend(
            visible_subset_candidates(
                image.shape[:2],
                variant_name,
                (low, high, threshold, min_length),
                families,
            ),
        )
    candidates.sort(key=lambda candidate: candidate.score, reverse=True)
    return dedupe_candidates(candidates)[:8]


def enhanced_variants(image: np.ndarray) -> dict[str, np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    closed = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9)))
    blackhat = cv2.normalize(cv2.subtract(closed, gray), None, 0, 255, cv2.NORM_MINMAX)
    return {
        "gray": gray,
        "clahe": clahe,
        "blackhat": blackhat,
        "clahe-blackhat-mix": cv2.addWeighted(clahe, 0.75, blackhat, 0.9, 0),
    }


def detect_segments(gray: np.ndarray, low: int, high: int, threshold: int, min_length: int) -> list[Segment]:
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blurred, low, high, apertureSize=3, L2gradient=True)
    lines = cv2.HoughLinesP(
        edges,
        1,
        np.pi / 180,
        threshold=threshold,
        minLineLength=min_length,
        maxLineGap=14,
    )
    if lines is None:
        return []

    segments: list[Segment] = []
    for x1, y1, x2, y2 in lines[:, 0, :]:
        start = np.array([float(x1), float(y1)], dtype=np.float32)
        end = np.array([float(x2), float(y2)], dtype=np.float32)
        delta = end - start
        length = float(np.linalg.norm(delta))
        if length < min_length:
            continue
        angle_rad = math.atan2(float(delta[1]), float(delta[0])) % math.pi
        segments.append(
            Segment(
                start=start,
                end=end,
                midpoint=(start + end) / 2,
                angle_rad=angle_rad,
                angle_deg=math.degrees(angle_rad),
                length=length,
            ),
        )
    return segments


def frame_quality(image: np.ndarray) -> FrameQuality:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    mean_luma = float(np.mean(gray))
    contrast = float(np.std(gray))
    if mean_luma < 24 and contrast < 18:
        quality = "too-dark"
    elif contrast < 7:
        quality = "low-contrast"
    else:
        quality = "usable"
    return FrameQuality(mean_luma=mean_luma, contrast=contrast, quality=quality)


def visible_subset_candidates(
    image_shape: tuple[int, int],
    variant: str,
    params: tuple[int, int, int, int],
    families: list[DirectionFamily],
) -> list[ProbeCandidate]:
    height, width = image_shape
    output: list[ProbeCandidate] = []
    for first_index, first in enumerate(families):
        for second in families[first_index + 1:]:
            separation = axial_angle_delta(first.angle_deg, second.angle_deg)
            if separation < 35 or separation > 145:
                continue
            if first.period is None or second.period is None:
                continue
            first_ranges = family_index_ranges(first)
            second_ranges = family_index_ranges(second)
            for first_min, first_max in first_ranges:
                for second_min, second_max in second_ranges:
                    corners = corners_for_indexes(first, second, first_min, first_max, second_min, second_max)
                    if corners is None:
                        continue
                    candidate = score_candidate(
                        image_shape,
                        variant,
                        params,
                        first,
                        second,
                        first_max - first_min,
                        second_max - second_min,
                        corners,
                        separation,
                    )
                    if candidate.score > 2.5:
                        output.append(candidate)
    return output


def family_line_indexes(family: DirectionFamily) -> list[int]:
    assert family.period is not None
    low = math.floor((family.period.offset_min - family.period.phase) / family.period.pitch)
    high = math.ceil((family.period.offset_max - family.period.phase) / family.period.pitch)
    return list(range(low, high + 1))


def family_index_ranges(family: DirectionFamily) -> list[tuple[int, int]]:
    indexes = family_line_indexes(family)
    ranges: list[tuple[int, int]] = []
    for start_position, start in enumerate(indexes):
        for end in indexes[start_position + 3:]:
            span = end - start
            if span > 24:
                break
            ranges.append((start, end))

    # Prefer wide-but-plausible ranges, while keeping the noisy-frame search
    # bounded. The ESP32 probe is a manual seed fallback; a few dozen strong
    # endpoint hypotheses are more valuable than exhaustive endpoint search.
    ranges.sort(key=lambda item: (-(item[1] - item[0]), abs((item[1] - item[0]) - 12), abs(item[0]) + abs(item[1])))
    return ranges[:80]


def corners_for_indexes(
    first: DirectionFamily,
    second: DirectionFamily,
    first_min: int,
    first_max: int,
    second_min: int,
    second_max: int,
) -> np.ndarray | None:
    assert first.period is not None and second.period is not None
    first_low = first.period.phase + first_min * first.period.pitch
    first_high = first.period.phase + first_max * first.period.pitch
    second_low = second.period.phase + second_min * second.period.pitch
    second_high = second.period.phase + second_max * second.period.pitch
    points = [
        intersect_normal_lines(first.normal, first_low, second.normal, second_low),
        intersect_normal_lines(first.normal, first_high, second.normal, second_low),
        intersect_normal_lines(first.normal, first_high, second.normal, second_high),
        intersect_normal_lines(first.normal, first_low, second.normal, second_high),
    ]
    if any(point is None for point in points):
        return None
    return order_corners(np.array(points, dtype=np.float32))


def score_candidate(
    image_shape: tuple[int, int],
    variant: str,
    params: tuple[int, int, int, int],
    first: DirectionFamily,
    second: DirectionFamily,
    columns: int,
    rows: int,
    corners: np.ndarray,
    separation: float,
) -> ProbeCandidate:
    height, width = image_shape
    in_frame = sum(1 for x, y in corners if -5 <= x <= width + 5 and -5 <= y <= height + 5) / 4
    off_frame = sum(max(0.0, -x, x - width, -y, y - height) for x, y in corners) / max(width, height)
    area = abs(cv2.contourArea(corners.astype(np.float32))) / max(1, width * height)
    line_span = columns + rows + 2
    axis_alignment = axis_pair_alignment(first.angle_deg, second.angle_deg)
    assert first.period is not None and second.period is not None
    score = (
        first.period.score
        + second.period.score
        + in_frame * 1.5
        + min(area, 1.25) * 0.75
        # Low-resolution ESP32 frames often produce strong harmonic fits that
        # skip every other faint grid line. When scores are otherwise close,
        # prefer the denser visible lattice so the manual seed keeps map scale.
        + min(1.0, line_span / 30) * 0.55
        + min(1.0, separation / 75) * 0.20
        + axis_alignment * 0.55
        - off_frame * 1.2
    )
    return ProbeCandidate(
        score=score,
        variant=variant,
        params=params,
        families=(first, second),
        corners=corners,
        columns=columns,
        rows=rows,
        in_frame_fraction=in_frame,
        area_ratio=area,
        off_frame_ratio=off_frame,
        axis_alignment=axis_alignment,
    )


def axis_pair_alignment(first_angle: float, second_angle: float) -> float:
    first_horizontal = axis_distance(first_angle, 0)
    first_vertical = axis_distance(first_angle, 90)
    second_horizontal = axis_distance(second_angle, 0)
    second_vertical = axis_distance(second_angle, 90)
    best_total = min(
        first_horizontal + second_vertical,
        first_vertical + second_horizontal,
    )
    return max(0.0, min(1.0, 1.0 - best_total / 55.0))


def axis_distance(angle: float, target: float) -> float:
    delta = abs((angle - target + 90) % 180 - 90)
    return min(delta, 90.0)


def dedupe_candidates(candidates: list[ProbeCandidate]) -> list[ProbeCandidate]:
    selected: list[ProbeCandidate] = []
    for candidate in candidates:
        center = candidate.corners.mean(axis=0)
        similar = False
        for existing in selected:
            existing_center = existing.corners.mean(axis=0)
            same_shape = abs(candidate.columns - existing.columns) <= 1 and abs(candidate.rows - existing.rows) <= 1
            if same_shape and float(np.linalg.norm(center - existing_center)) < 35:
                similar = True
                break
        if not similar:
            selected.append(candidate)
    return selected


def build_report(
    image_path: Path,
    image: np.ndarray,
    quality: FrameQuality,
    selected: ProbeCandidate | None,
    candidates: list[ProbeCandidate],
    started: float,
) -> dict[str, Any]:
    height, width = image.shape[:2]
    report: dict[str, Any] = {
        "detected": selected is not None,
        "candidateId": "esp32-webcam-lattice-probe-v1",
        "sourceId": image_path.name,
        "sourceName": f"ESP32 webcam probe {image_path.name}",
        "sourceUrl": repo_url(image_path),
        "imageWidth": int(width),
        "imageHeight": int(height),
        "elapsedMs": round_metric((time.perf_counter() - started) * 1000),
        "frameMeanLuma": round_metric(quality.mean_luma),
        "frameContrast": round_metric(quality.contrast),
        "frameQuality": quality.quality,
        "topCandidates": [summarize_candidate(candidate) for candidate in candidates[:5]],
    }
    if selected is None:
        report["errorMessage"] = (
            "ESP32 webcam frame is too dark or low contrast for a trustworthy lattice candidate."
            if quality.quality != "usable"
            else "No two-family low-resolution webcam lattice candidate found."
        )
        return report

    confidence = min(0.55, max(0.2, selected.score / 8))
    lattice_score = min(0.5, max(0.0, (selected.families[0].period.score + selected.families[1].period.score) / 4))
    report.update(
        {
            "corners": points_payload(selected.corners),
            "columns": selected.columns,
            "rows": selected.rows,
            "confidence": round_metric(confidence),
            "latticeScore": round_metric(lattice_score),
            "selectedScore": round_metric(selected.score),
            "selectedFitKind": selected.variant,
            "detectorMessage": (
                "ESP32 webcam lattice probe; "
                f"{selected.variant} params {list(selected.params)}; "
                f"{selected.columns}x{selected.rows}; "
                f"in-frame {selected.in_frame_fraction:.2f}; area {selected.area_ratio:.2f}."
            ),
        },
    )
    return report


def summarize_candidate(candidate: ProbeCandidate) -> dict[str, Any]:
    return {
        "score": round_metric(candidate.score),
        "variant": candidate.variant,
        "params": list(candidate.params),
        "columns": candidate.columns,
        "rows": candidate.rows,
        "inFrameFraction": round_metric(candidate.in_frame_fraction),
        "areaRatio": round_metric(candidate.area_ratio),
        "offFrameRatio": round_metric(candidate.off_frame_ratio),
        "axisAlignment": round_metric(candidate.axis_alignment),
        "corners": points_payload(candidate.corners),
        "families": [
            {
                "angleDeg": round_metric(family.angle_deg),
                "pitch": round_metric(family.period.pitch if family.period else 0),
                "periodScore": round_metric(family.period.score if family.period else 0),
                "lines": int(family.period.line_count if family.period else 0),
            }
            for family in candidate.families
        ],
    }


def points_payload(points: np.ndarray) -> list[dict[str, float]]:
    return [{"x": round_metric(float(x)), "y": round_metric(float(y))} for x, y in points]


def repo_url(path: Path) -> str:
    try:
        return "/" + str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def write_overlay(path: Path, image: np.ndarray, candidate: ProbeCandidate) -> None:
    output = image.copy()
    colors = [(0, 255, 255), (255, 0, 255)]
    for color, family in zip(colors, candidate.families):
        assert family.period is not None
        low = math.floor((family.period.offset_min - family.period.phase) / family.period.pitch) - 1
        high = math.ceil((family.period.offset_max - family.period.phase) / family.period.pitch) + 1
        direction = np.array([family.normal[1], -family.normal[0]], dtype=np.float64)
        for index in range(low, high + 1):
            rho = family.period.phase + index * family.period.pitch
            base = family.normal.astype(np.float64) * rho
            start = base - direction * 1000
            end = base + direction * 1000
            cv2.line(output, tuple(np.round(start).astype(int)), tuple(np.round(end).astype(int)), color, 1, cv2.LINE_AA)
    cv2.polylines(output, [np.round(candidate.corners).astype(np.int32)], True, (0, 140, 255), 2, cv2.LINE_AA)
    for index, point in enumerate(candidate.corners):
        cv2.circle(output, tuple(np.round(point).astype(int)), 6, (0, 80, 255), -1, cv2.LINE_AA)
        cv2.putText(
            output,
            chr(65 + index),
            tuple(np.round(point + np.array([8, -8])).astype(int)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
    cv2.imwrite(str(path), output)


if __name__ == "__main__":
    sys.exit(main())
