#!/usr/bin/env python3
"""Fit visible lattice geometry from skeletonized AI line-mask junctions.

This discovery script tests whether a single generated gridline mask can
replace separate AI dot calls. It skeletonizes the line mask, extracts branch
points where gridline strokes cross, and reuses the existing deterministic
dot-lattice fitter. Labels are used only for benchmark scoring.
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
LABELS_PATH = ROOT / "input" / "map-grid-labels.json"
DEFAULT_OUT_DIR = ROOT / "test-results" / "ai-line-skeleton-junction-probe-v1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--line-reports-glob", default="test-results/ai-grid-experiments-grok-white-v1/*/report.json")
    parser.add_argument("--line-prompt-id", default="white-grid-exact-copy-no-marks-v1")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--thresholds", default="64,96,128")
    args = parser.parse_args()

    ai_grid = load_module("ai_grid_experiment", AI_GRID_PATH)
    ai_arbiter = load_module("ai_evidence_arbiter", AI_ARBITER_PATH)
    dot_fit = load_module("ai_dot_lattice_fit", AI_DOT_FIT_PATH)
    labels = {label["sourceId"]: label for label in json.loads(LABELS_PATH.read_text())["labels"]}
    thresholds = [int(value.strip()) for value in args.thresholds.split(",") if value.strip()]

    out_dir = Path(args.out_dir)
    overlays_dir = out_dir / "overlays"
    overlays_dir.mkdir(parents=True, exist_ok=True)

    reports_by_source: dict[str, list[dict[str, Any]]] = {}
    for report_path in sorted(ROOT.glob(args.line_reports_glob)):
        report = json.loads(report_path.read_text())
        if not report_has_prompt(report, args.line_prompt_id):
            continue
        source_id = report["sourceId"]
        report["_reportPath"] = str(report_path)
        reports_by_source.setdefault(source_id, []).append(report)

    results = []
    for source_id, reports in sorted(reports_by_source.items()):
        label = labels.get(source_id)
        if not label:
            continue
        variants = []
        for report in reports:
            line_experiment = first_image_result(report)
            line_path = resolve_output_path(line_experiment["outputImage"])
            line_rgb = load_rgb(line_path)
            line_mask = ai_arbiter.extract_line_mask(ai_grid, line_rgb, line_experiment)
            variants.extend(
                analyze_threshold(ai_grid, dot_fit, source_id, label, line_mask, overlays_dir, threshold)
                for threshold in thresholds
            )
        selected = dict(max(variants, key=lambda variant: variant["selectionScore"]))
        selected["variants"] = variants
        results.append(selected)

    output = {
        "outDir": str(out_dir),
        "selectionMode": "single AI line mask; skeleton branch-point thresholds selected without labels",
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


def report_has_prompt(report: dict[str, Any], prompt_id: str) -> bool:
    return any(result.get("ok") and result.get("outputImage") and result.get("promptId") == prompt_id for result in report.get("results", []))


def resolve_output_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.array(ImageOps.exif_transpose(image).convert("RGB"))


def analyze_threshold(
    ai_grid: Any,
    dot_fit: Any,
    source_id: str,
    label: dict[str, Any],
    line_mask: np.ndarray,
    overlays_dir: Path,
    threshold: int,
) -> dict[str, Any]:
    points, skeleton = skeleton_junction_points(line_mask, threshold)
    fit = dot_fit.fit_visible_lattice(points, line_mask)
    benchmark = dot_fit.benchmark_fit(ai_grid, label, fit, points, line_mask)
    selection_score = dot_fit.selection_score_for_fit(fit.metrics, fit.decision)
    overlay_path = write_overlay(dot_fit, ai_grid, label, source_id, points, line_mask, skeleton, fit, overlays_dir, threshold)
    return {
        "sourceId": source_id,
        "threshold": threshold,
        "selectionScore": round_metric(selection_score),
        "decision": fit.decision,
        "reasons": fit.reasons,
        "junctionCount": int(len(points)),
        "skeletonPixels": int((skeleton > 0).sum()),
        "overlayImage": str(overlay_path),
        "fit": fit.metrics,
        "benchmark": benchmark,
    }


def skeleton_junction_points(line_mask: np.ndarray, threshold: int) -> tuple[np.ndarray, np.ndarray]:
    binary = (line_mask >= threshold).astype(np.uint8)
    if int(binary.sum()) == 0:
        return np.empty((0, 2), dtype=np.float32), binary
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8), iterations=1)
    skeleton = zhang_suen_thinning(binary)
    neighbors = cv2.filter2D(skeleton, cv2.CV_16S, np.ones((3, 3), dtype=np.uint8), borderType=cv2.BORDER_CONSTANT) - skeleton
    branch_mask = ((skeleton > 0) & (neighbors >= 3)).astype(np.uint8) * 255
    branch_mask = cv2.dilate(branch_mask, np.ones((5, 5), np.uint8), iterations=1)
    branch_mask = cv2.morphologyEx(branch_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8), iterations=1)
    component_count, _labels, stats, centroids = cv2.connectedComponentsWithStats(branch_mask, 8)
    points = []
    for index in range(1, component_count):
        area = int(stats[index, cv2.CC_STAT_AREA])
        width = int(stats[index, cv2.CC_STAT_WIDTH])
        height = int(stats[index, cv2.CC_STAT_HEIGHT])
        if 3 <= area <= 380 and width <= 28 and height <= 28:
            points.append(centroids[index])
    return np.float32(points), skeleton * 255


def zhang_suen_thinning(binary: np.ndarray) -> np.ndarray:
    image = (binary > 0).astype(np.uint8)
    changed = True
    while changed:
        changed = False
        for step in (0, 1):
            center = image[1:-1, 1:-1]
            p2 = image[:-2, 1:-1]
            p3 = image[:-2, 2:]
            p4 = image[1:-1, 2:]
            p5 = image[2:, 2:]
            p6 = image[2:, 1:-1]
            p7 = image[2:, :-2]
            p8 = image[1:-1, :-2]
            p9 = image[:-2, :-2]
            neighbors = [p2, p3, p4, p5, p6, p7, p8, p9]
            transitions = np.zeros_like(center, dtype=np.uint8)
            for left, right in zip(neighbors, neighbors[1:] + neighbors[:1]):
                transitions += ((left == 0) & (right == 1)).astype(np.uint8)
            neighbor_count = sum(neighbors)
            if step == 0:
                keep_shape = (p2 * p4 * p6 == 0) & (p4 * p6 * p8 == 0)
            else:
                keep_shape = (p2 * p4 * p8 == 0) & (p2 * p6 * p8 == 0)
            delete = (center == 1) & (neighbor_count >= 2) & (neighbor_count <= 6) & (transitions == 1) & keep_shape
            if bool(delete.any()):
                inner = image[1:-1, 1:-1]
                inner[delete] = 0
                changed = True
    return image


def write_overlay(
    dot_fit: Any,
    ai_grid: Any,
    label: dict[str, Any],
    source_id: str,
    points: np.ndarray,
    line_mask: np.ndarray,
    skeleton: np.ndarray,
    fit: Any,
    overlays_dir: Path,
    threshold: int,
) -> Path:
    path = dot_fit.write_overlay(ai_grid, label, source_id, points, line_mask, fit, overlays_dir, variant_index=threshold)
    target = overlays_dir / f"{slugify(source_id)}-skeleton-junction-{threshold}.png"
    path.replace(target)

    with Image.open(target) as image:
        canvas = image.convert("RGB")
    skeleton_rgb = np.zeros((skeleton.shape[0], skeleton.shape[1], 3), dtype=np.uint8)
    skeleton_rgb[..., 1] = np.where(skeleton > 0, 120, 0)
    skeleton_layer = Image.fromarray(skeleton_rgb, "RGB").resize(canvas.size, Image.Resampling.NEAREST)
    canvas = Image.blend(canvas, skeleton_layer, 0.25)
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((8, 42, min(canvas.width - 8, 500), 68), fill=(0, 0, 0))
    draw.text((14, 47), f"skeleton threshold {threshold}", fill=(255, 255, 255))
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
        "# AI Line Skeleton Junction Probe",
        "",
        f"- Selection mode: {report['selectionMode']}",
        f"- Total: `{report['summary']['total']}`",
        f"- Decisions: `{json.dumps(report['summary']['decisions'], sort_keys=True)}`",
        "",
        "| Source | Threshold | Decision | Junctions | Skeleton Px | Inliers | Span | Homography line <=.15 | Mesh line <=.15 | Reasons | Overlay |",
        "| --- | ---: | --- | ---: | ---: | ---: | --- | ---: | ---: | --- | --- |",
    ]
    for result in report["results"]:
        fit = result["fit"]
        bench = result["benchmark"]
        lines.append(
            f"| `{result['sourceId']}` | {result['threshold']} | `{result['decision']}` | "
            f"{result['junctionCount']} | {result['skeletonPixels']} | {fit.get('homographyInliers')} | "
            f"{fit.get('spanI')}x{fit.get('spanJ')} | {bench.get('truthLineSamplesWithin0_15SquaresPct')} | "
            f"{bench.get('truthMeshSamplesWithin0_15SquaresPct')} | {'; '.join(result['reasons'])} | `{result['overlayImage']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def render_console(report: dict[str, Any]) -> str:
    lines = [f"AI line skeleton junction probe: {json.dumps(report['summary']['decisions'], sort_keys=True)}"]
    for result in report["results"]:
        fit = result["fit"]
        bench = result["benchmark"]
        lines.append(
            f"- {result['sourceId']}: {result['decision']} threshold={result['threshold']} "
            f"junctions={result['junctionCount']} inliers={fit.get('homographyInliers')} "
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
        draw.text((10, 355), result["sourceId"].replace("real-map-home-", "").replace(".jpg", ""), fill=(0, 0, 0))
        draw.text((10, 372), result["decision"], fill=(0, 0, 0))
        fit = result["fit"]
        draw.text((10, 389), f"j {result['junctionCount']} in {fit.get('homographyInliers')} span {fit.get('spanI')}x{fit.get('spanJ')}", fill=(0, 0, 0))
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
