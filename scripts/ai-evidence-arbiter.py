#!/usr/bin/env python3
"""Combine AI line-mask and dot-mask evidence into a conservative grid seed.

The arbiter does not use fixture labels to decide whether to accept or refuse.
Labels are used only for benchmark scoring in the output report.
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
from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[1]
AI_GRID_PATH = ROOT / "scripts" / "ai-grid-experiment.py"
LABELS_PATH = ROOT / "input" / "map-grid-labels.json"
DEFAULT_OUT_DIR = ROOT / "test-results" / "ai-evidence-arbiter"


@dataclass
class Dot:
    x: float
    y: float
    area: int


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--line-reports-glob", default="test-results/ai-grid-experiments-grok-realhome/*/report.json")
    parser.add_argument("--dot-reports-glob", default="test-results/ai-grid-experiments-grok-dots-realhome/*/report.json")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    ai_grid = load_ai_grid_module()
    labels = {label["sourceId"]: label for label in json.loads(LABELS_PATH.read_text())["labels"]}
    line_reports = load_reports(args.line_reports_glob)
    dot_reports = load_reports(args.dot_reports_glob)

    out_dir = Path(args.out_dir)
    overlays_dir = out_dir / "overlays"
    overlays_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for source_id in sorted(set(line_reports) & set(dot_reports)):
        label = labels.get(source_id)
        if not label:
            continue
        result = arbitrate_fixture(ai_grid, source_id, line_reports[source_id], dot_reports[source_id], label, overlays_dir)
        results.append(result)

    report = {
        "outDir": str(out_dir),
        "summary": summarize(results),
        "results": results,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(f"{json.dumps(report, indent=2)}\n")
    (out_dir / "report.md").write_text(render_markdown(report))
    write_contact_sheet(results, out_dir)
    print(render_console(report))


def load_ai_grid_module() -> Any:
    spec = importlib.util.spec_from_file_location("ai_grid_experiment", AI_GRID_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load ai-grid-experiment.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["ai_grid_experiment"] = module
    spec.loader.exec_module(module)
    return module


def load_reports(pattern: str) -> dict[str, dict[str, Any]]:
    reports = {}
    for path in sorted(ROOT.glob(pattern)):
        report = json.loads(path.read_text())
        report["_reportPath"] = str(path)
        reports[report["sourceId"]] = report
    return reports


def arbitrate_fixture(
    ai_grid: Any,
    source_id: str,
    line_report: dict[str, Any],
    dot_report: dict[str, Any],
    label: dict[str, Any],
    overlays_dir: Path,
) -> dict[str, Any]:
    line_experiment = first_image_result(line_report)
    dot_experiment = first_image_result(dot_report)
    line_path = resolve_output_path(line_experiment["outputImage"])
    dot_path = resolve_output_path(dot_experiment["outputImage"])

    line_rgb = load_rgb(line_path)
    dot_rgb = load_rgb(dot_path)
    line_mask = extract_line_mask(ai_grid, line_rgb, line_experiment)
    dot_mask = ai_grid.extract_signal_mask(dot_rgb, "white_mask")
    dots = extract_dots(dot_mask)

    dot_lattice = dot_lattice_features(dots)
    dot_lattice["dotCount"] = len(dots)
    dot_line = dot_line_agreement(dots, line_mask, dot_lattice)
    line_features = line_mask_features(line_mask, line_experiment)
    dot_features = dot_mask_features(dot_mask, dot_experiment)

    decision, reasons = decide(dot_line, dot_lattice, line_features, dot_features)
    benchmark = benchmark_scores(line_experiment, dot_experiment)
    overlay_path = write_overlay(ai_grid, label, source_id, dots, line_mask, dot_line, decision, overlays_dir)

    return {
        "sourceId": source_id,
        "decision": decision,
        "reasons": reasons,
        "lineImage": str(line_path),
        "dotImage": str(dot_path),
        "overlayImage": str(overlay_path),
        "fullExtentStatus": "refused-needs-known-dimensions-or-manual-confirmation",
        "lineMask": line_features,
        "dotMask": {
            "dotCount": len(dots),
            **dot_features,
            **dot_line,
            **dot_lattice,
        },
        "benchmark": benchmark,
    }


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


def extract_line_mask(ai_grid: Any, rgb: np.ndarray, line_experiment: dict[str, Any]) -> np.ndarray:
    """Collapse model grid output to foreground only.

    Generated red/blue axis colors are not reliable metadata: models may switch
    colors along one physical line family. The arbiter only asks whether the
    output contains line evidence in the same coordinate frame.
    """
    kind = str(line_experiment.get("kind") or "color_mask")
    preferred = kind if kind in {"white_mask", "color_mask", "pink_overlay"} else "color_mask"
    fallback = "color_mask" if preferred != "color_mask" else "white_mask"
    mask = ai_grid.extract_signal_mask(rgb, preferred)
    if float((mask > 0).mean()) < 0.005:
        mask = ai_grid.extract_signal_mask(rgb, fallback)
    return mask


def extract_dots(mask: np.ndarray) -> list[Dot]:
    component_count, _labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    dots = []
    for index in range(1, component_count):
        area = int(stats[index, cv2.CC_STAT_AREA])
        width = int(stats[index, cv2.CC_STAT_WIDTH])
        height = int(stats[index, cv2.CC_STAT_HEIGHT])
        if 1 <= area <= 90 and width <= 16 and height <= 16:
            dots.append(Dot(float(centroids[index][0]), float(centroids[index][1]), area))
    return dots


def dot_line_agreement(dots: list[Dot], line_mask: np.ndarray, dot_lattice: dict[str, Any]) -> dict[str, Any]:
    threshold_px = dot_line_threshold(dot_lattice)
    if not dots:
        return {
            "dotLineAgreementPct": 0.0,
            "dotLineThresholdPx": threshold_px,
            "medianLineDistancePx": None,
            "p90LineDistancePx": None,
        }
    distance = cv2.distanceTransform((line_mask == 0).astype(np.uint8) * 255, cv2.DIST_L2, 3)
    height, width = line_mask.shape[:2]
    values = []
    for dot in dots:
        x = int(np.clip(round(dot.x), 0, width - 1))
        y = int(np.clip(round(dot.y), 0, height - 1))
        values.append(float(distance[y, x]))
    distances = np.array(values)
    return {
        "dotLineAgreementPct": round_metric(float(np.mean(distances <= threshold_px) * 100)),
        "dotLineThresholdPx": round_metric(threshold_px),
        "medianLineDistancePx": round_metric(float(np.median(distances))),
        "p90LineDistancePx": round_metric(float(np.percentile(distances, 90))),
    }


def dot_line_threshold(dot_lattice: dict[str, Any]) -> float:
    median = dot_lattice.get("nearestNeighborMedianPx")
    if median is None:
        return 4.0
    return max(4.0, min(7.0, float(median) * 0.10))


def dot_lattice_features(dots: list[Dot]) -> dict[str, Any]:
    if len(dots) < 20:
        return {
            "nearestNeighborMedianPx": None,
            "nearestNeighborCv": None,
            "twoAxisScore": 0.0,
            "dominantAnglesDeg": [],
        }
    points = np.float32([[dot.x, dot.y] for dot in dots])
    deltas = points[:, None, :] - points[None, :, :]
    distances = np.sqrt(np.sum(deltas * deltas, axis=2))
    distances[distances == 0] = np.inf
    nearest = np.min(distances, axis=1)
    finite_nearest = nearest[np.isfinite(nearest)]
    median = float(np.median(finite_nearest))
    cv = float(np.std(finite_nearest) / max(1e-6, median))

    edge_vectors = []
    max_edge = max(12.0, median * 2.4)
    min_edge = max(3.0, median * 0.45)
    for i, point in enumerate(points):
        candidates = np.argsort(distances[i])[:8]
        for j in candidates:
            distance = float(distances[i, j])
            if min_edge <= distance <= max_edge:
                vector = points[j] - point
                angle = (math.degrees(math.atan2(float(vector[1]), float(vector[0]))) + 180) % 180
                edge_vectors.append((angle, distance))
    if not edge_vectors:
        return {
            "nearestNeighborMedianPx": round_metric(median),
            "nearestNeighborCv": round_metric(cv),
            "twoAxisScore": 0.0,
            "dominantAnglesDeg": [],
        }

    angles = np.array([item[0] for item in edge_vectors])
    weights = np.array([1.0 / max(1.0, item[1]) for item in edge_vectors])
    hist, bins = np.histogram(angles, bins=36, range=(0, 180), weights=weights)
    peaks = []
    scratch = hist.copy()
    for _ in range(4):
        index = int(np.argmax(scratch))
        if scratch[index] <= 0:
            break
        angle = float((bins[index] + bins[index + 1]) / 2)
        peaks.append((angle, float(scratch[index])))
        for offset in range(-2, 3):
            scratch[(index + offset) % len(scratch)] = 0
    best_score = 0.0
    best_pair: list[float] = []
    total_weight = float(np.sum(hist))
    for i, left in enumerate(peaks):
        for right in peaks[i + 1:]:
            separation = angle_distance(left[0], right[0])
            if separation < 35 or separation > 145:
                continue
            score = (left[1] + right[1]) / max(1e-6, total_weight)
            if score > best_score:
                best_score = score
                best_pair = [left[0], right[0]]
    return {
        "nearestNeighborMedianPx": round_metric(median),
        "nearestNeighborCv": round_metric(cv),
        "twoAxisScore": round_metric(best_score),
        "dominantAnglesDeg": [round_metric(angle) for angle in best_pair],
    }


def line_mask_features(mask: np.ndarray, experiment: dict[str, Any]) -> dict[str, Any]:
    signal_pct = float((mask > 0).mean() * 100)
    component_count, _labels, stats, _centroids = cv2.connectedComponentsWithStats(mask, 8)
    large_components = int(sum(1 for index in range(1, component_count) if stats[index, cv2.CC_STAT_AREA] >= 20))
    image_score = experiment.get("imageScore", {})
    return {
        "signalPct": round_metric(signal_pct),
        "largeComponents": large_components,
        "aspectRatioDeltaPct": image_score.get("aspectRatioDeltaPct"),
        "elapsedMs": experiment.get("elapsedMs"),
    }


def dot_mask_features(mask: np.ndarray, experiment: dict[str, Any]) -> dict[str, Any]:
    image_score = experiment.get("imageScore", {})
    return {
        "dotSignalPct": round_metric(float((mask > 0).mean() * 100)),
        "aspectRatioDeltaPct": image_score.get("aspectRatioDeltaPct"),
        "elapsedMs": experiment.get("elapsedMs"),
    }


def decide(
    dot_line: dict[str, Any],
    dot_lattice: dict[str, Any],
    line_features: dict[str, Any],
    dot_features: dict[str, Any],
) -> tuple[str, list[str]]:
    hard_reasons = []
    weak_reasons = []
    dot_count = int(dot_lattice.get("dotCount", 0))
    agreement = float(dot_line["dotLineAgreementPct"])
    signal = float(line_features["signalPct"])
    two_axis = float(dot_lattice["twoAxisScore"])
    nearest_cv = dot_lattice["nearestNeighborCv"]
    dot_signal = float(dot_features["dotSignalPct"])
    line_aspect = line_features.get("aspectRatioDeltaPct")
    dot_aspect = dot_features.get("aspectRatioDeltaPct")

    if line_aspect is not None and float(line_aspect) > 1.5:
        hard_reasons.append("line mask aspect ratio changed too much")
    if dot_aspect is not None and float(dot_aspect) > 1.5:
        hard_reasons.append("dot mask aspect ratio changed too much")
    if signal < 3.0:
        hard_reasons.append("line mask has too little foreground")
    if signal > 25.0:
        hard_reasons.append("line mask has too much foreground")
    if dot_signal < 0.03:
        hard_reasons.append("dot mask has too little foreground")
    if dot_signal > 3.0:
        hard_reasons.append("dot mask has too much foreground")
    if dot_count < 200:
        hard_reasons.append("dot mask has too few compact intersections")
    if agreement < 60.0:
        hard_reasons.append("dot mask disagrees with independently generated line mask")
    if two_axis < 0.18:
        weak_reasons.append("dot cloud has weak local two-axis evidence")
    if nearest_cv is not None and nearest_cv > 0.75:
        weak_reasons.append("dot spacing is irregular")

    if hard_reasons:
        return "refuse", hard_reasons + weak_reasons
    if agreement >= 80.0 and dot_count >= 250 and (two_axis >= 0.18 or (agreement >= 92.0 and (nearest_cv is None or nearest_cv <= 0.65))):
        return "accepted-visible-lattice-seed", [
            "line and dot evidence agree",
            "visible lattice seed only; full extent is not inferred",
            *weak_reasons,
        ]
    if agreement >= 70.0 and dot_count >= 100:
        return "candidate-visible-lattice-seed", [
            "line and dot evidence partially agree",
            "requires manual confirmation before projection",
            *weak_reasons,
        ]
    return "refuse", ["insufficient consensus for even a candidate seed", *weak_reasons]


def benchmark_scores(line_experiment: dict[str, Any], dot_experiment: dict[str, Any]) -> dict[str, Any]:
    line_score = line_experiment.get("imageScore", {})
    dot_score = dot_experiment.get("imageScore", {})
    return {
        "lineCoverage": line_score.get("coverage", {}).get("lineMeanCoverage"),
        "linePointsWithin0_10SquaresPct": line_score.get("alignment", {}).get("pointsWithin0_10SquaresPct"),
        "lineAspectRatioDeltaPct": line_score.get("aspectRatioDeltaPct"),
        "dotMatchedVisibleIntersections": dot_score.get("dotScore", {}).get("matchedVisibleIntersections"),
        "dotVisibleExpectedIntersections": dot_score.get("dotScore", {}).get("visibleExpectedIntersections"),
        "dotMatchedVisibleIntersectionRatio": dot_score.get("dotScore", {}).get("matchedVisibleIntersectionRatio"),
        "dotMedianIntersectionErrorSquares": dot_score.get("dotScore", {}).get("medianIntersectionErrorSquares"),
        "dotAspectRatioDeltaPct": dot_score.get("aspectRatioDeltaPct"),
    }


def write_overlay(
    ai_grid: Any,
    label: dict[str, Any],
    source_id: str,
    dots: list[Dot],
    line_mask: np.ndarray,
    dot_line: dict[str, Any],
    decision: str,
    overlays_dir: Path,
) -> Path:
    source_path = ROOT / label["sourceUrl"].removeprefix("/")
    with Image.open(source_path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB").resize((line_mask.shape[1], line_mask.shape[0]), Image.Resampling.LANCZOS)
    overlay = np.array(image)
    line_tint = np.zeros_like(overlay)
    line_tint[:, :, 1] = line_mask
    overlay = cv2.addWeighted(overlay, 0.82, line_tint, 0.35, 0)

    distance = cv2.distanceTransform((line_mask == 0).astype(np.uint8) * 255, cv2.DIST_L2, 3)
    height, width = line_mask.shape[:2]
    threshold_px = float(dot_line["dotLineThresholdPx"])
    for dot in dots:
        x = int(np.clip(round(dot.x), 0, width - 1))
        y = int(np.clip(round(dot.y), 0, height - 1))
        color = (255, 0, 255) if distance[y, x] <= threshold_px else (255, 120, 0)
        cv2.circle(overlay, (x, y), 3, color, -1, cv2.LINE_AA)

    draw = ImageDraw.Draw(Image.fromarray(overlay))
    text = f"{source_id} | {decision} | dot-line {dot_line['dotLineAgreementPct']}%"
    pil_overlay = Image.fromarray(overlay)
    draw = ImageDraw.Draw(pil_overlay)
    draw.rectangle((8, 8, min(width - 8, 760), 38), fill=(0, 0, 0))
    draw.text((14, 14), text, fill=(255, 255, 255))

    out = overlays_dir / f"{slugify(source_id)}-arbiter.png"
    pil_overlay.save(out)
    return out


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for result in results:
        counts[result["decision"]] = counts.get(result["decision"], 0) + 1
    return {
        "total": len(results),
        "decisions": counts,
        "acceptedOrCandidateSeeds": sum(
            1 for result in results if result["decision"] in {"accepted-visible-lattice-seed", "candidate-visible-lattice-seed"}
        ),
        "medianDotLineAgreementPct": None if not results else round_metric(float(np.median([result["dotMask"]["dotLineAgreementPct"] for result in results]))),
    }


def write_contact_sheet(results: list[dict[str, Any]], out_dir: Path) -> None:
    if not results:
        return
    thumbs = []
    for result in results:
        image = Image.open(result["overlayImage"]).convert("RGB")
        image.thumbnail((260, 345), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (280, 390), (235, 235, 235))
        canvas.paste(image, ((280 - image.width) // 2, 10))
        draw = ImageDraw.Draw(canvas)
        draw.text((10, 355), result["sourceId"].replace("real-map-home-", "").replace(".jpg", ""), fill=(0, 0, 0))
        draw.text((10, 372), result["decision"], fill=(0, 0, 0))
        thumbs.append(canvas)
    columns = 4
    rows = math.ceil(len(thumbs) / columns)
    sheet = Image.new("RGB", (columns * 280, rows * 390), (220, 220, 220))
    for index, thumb in enumerate(thumbs):
        sheet.paste(thumb, ((index % columns) * 280, (index // columns) * 390))
    sheet.save(out_dir / "contact-sheet.jpg", quality=92)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AI Evidence Arbiter",
        "",
        f"- Total: `{report['summary']['total']}`",
        f"- Decisions: `{json.dumps(report['summary']['decisions'], sort_keys=True)}`",
        f"- Median dot-line agreement: `{report['summary']['medianDotLineAgreementPct']}`",
        "",
        "| Source | Decision | Dot-line % | Tau px | Dots | Line signal | Dot signal | Two-axis | NN CV | Benchmark dot ratio | Benchmark line coverage | Reasons | Overlay |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for result in report["results"]:
        dot = result["dotMask"]
        bench = result["benchmark"]
        lines.append(
            f"| `{result['sourceId']}` | `{result['decision']}` | {dot['dotLineAgreementPct']} | {dot['dotLineThresholdPx']} | "
            f"{dot['dotCount']} | {result['lineMask']['signalPct']} | {dot['dotSignalPct']} | {dot['twoAxisScore']} | "
            f"{dot['nearestNeighborCv']} | {bench['dotMatchedVisibleIntersectionRatio']} | "
            f"{bench['lineCoverage']} | {'; '.join(result['reasons'])} | `{result['overlayImage']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def render_console(report: dict[str, Any]) -> str:
    lines = [
        f"AI evidence arbiter: {report['summary']['decisions']} "
        f"median dot-line {report['summary']['medianDotLineAgreementPct']}%",
    ]
    for result in report["results"]:
        dot = result["dotMask"]
        bench = result["benchmark"]
        lines.append(
            f"- {result['sourceId']}: {result['decision']} dot-line={dot['dotLineAgreementPct']}% "
            f"dots={dot['dotCount']} axes={dot['twoAxisScore']} benchDot={bench['dotMatchedVisibleIntersectionRatio']} "
            f"lineCoverage={bench['lineCoverage']}"
        )
    lines.append(f"Artifacts: {Path(report.get('outDir', DEFAULT_OUT_DIR)) / 'report.md'}")
    return "\n".join(lines)


def angle_distance(left: float, right: float) -> float:
    delta = abs(left - right) % 180
    return min(delta, 180 - delta)


def slugify(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "-", value).strip("-")


def round_metric(value: float) -> float:
    return round(float(value), 3)


if __name__ == "__main__":
    main()
