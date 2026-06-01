#!/usr/bin/env python3
"""Fit visible lattice geometry from two AI-generated one-family line masks.

This is the direct test of the "horizontal-only plus vertical-only" idea. It
does not ask one mask to contain a full grid. Instead, it extracts ordered
line clusters from each family-only output, intersects the two cluster sets,
and scores the resulting lattice with the existing line-lattice fitter.
Labels are used only for benchmark fields.
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
AI_LINE_LATTICE_PATH = ROOT / "scripts" / "ai-line-lattice-ransac.py"
LABELS_PATH = ROOT / "input" / "map-grid-labels.json"
DEFAULT_OUT_DIR = ROOT / "test-results" / "ai-family-pair-lattice-v1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reports-glob", default="test-results/ai-grid-experiments-grok-family-stripes-v2/*/report.json")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--first-prompt", default="white-grid-family-less-steep-stripes-v2")
    parser.add_argument("--second-prompt", default="white-grid-family-more-steep-stripes-v2")
    args = parser.parse_args()

    ai_grid = load_module("ai_grid_experiment", AI_GRID_PATH)
    ai_arbiter = load_module("ai_evidence_arbiter", AI_ARBITER_PATH)
    dot_fit = load_module("ai_dot_lattice_fit", AI_DOT_FIT_PATH)
    mask_probe = load_module("ai_mask_lattice_probe", AI_MASK_PROBE_PATH)
    line_lattice = load_module("ai_line_lattice_ransac", AI_LINE_LATTICE_PATH)
    labels = {label["sourceId"]: label for label in json.loads(LABELS_PATH.read_text())["labels"]}

    out_dir = Path(args.out_dir)
    overlays_dir = out_dir / "overlays"
    overlays_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for report_path in sorted(ROOT.glob(args.reports_glob)):
        report = json.loads(report_path.read_text())
        source_id = report["sourceId"]
        label = labels.get(source_id)
        if not label:
            continue
        first = result_by_prompt(report, args.first_prompt)
        second = result_by_prompt(report, args.second_prompt)
        if first is None or second is None:
            continue
        results.append(analyze_pair(ai_grid, ai_arbiter, dot_fit, mask_probe, line_lattice, source_id, label, first, second, overlays_dir))

    output = {
        "outDir": str(out_dir),
        "selectionMode": "two AI one-family masks; dominant Hough clusters from each mask intersected and selected without labels",
        "firstPrompt": args.first_prompt,
        "secondPrompt": args.second_prompt,
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


def result_by_prompt(report: dict[str, Any], prompt_id: str) -> dict[str, Any] | None:
    for result in report.get("results", []):
        if result.get("ok") and result.get("outputImage") and result.get("promptId") == prompt_id:
            return result
    return None


def resolve_output_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.array(ImageOps.exif_transpose(image).convert("RGB"))


def analyze_pair(
    ai_grid: Any,
    ai_arbiter: Any,
    dot_fit: Any,
    mask_probe: Any,
    line_lattice: Any,
    source_id: str,
    label: dict[str, Any],
    first_result: dict[str, Any],
    second_result: dict[str, Any],
    overlays_dir: Path,
) -> dict[str, Any]:
    first_mask = extract_mask(ai_grid, ai_arbiter, first_result)
    second_mask = extract_mask(ai_grid, ai_arbiter, second_result)
    combined_mask = np.maximum(first_mask, second_mask)
    first_clusters, first_angle, first_segments = dominant_family_clusters(mask_probe, first_mask)
    second_clusters, second_angle, second_segments = dominant_family_clusters(mask_probe, second_mask)
    variants = line_lattice.fit_line_subset_variants(dot_fit, [first_clusters, second_clusters], combined_mask)
    if not variants:
        fit = dot_fit.FitResult(
            "refuse",
            ["could not fit paired one-family line masks"],
            None,
            {},
            [],
            {
                "lineFamilyACount": len(first_clusters),
                "lineFamilyBCount": len(second_clusters),
                "firstSegments": first_segments,
                "secondSegments": second_segments,
            },
        )
        points = np.empty((0, 2), dtype=np.float32)
        best = {"selectionScore": 0.0, "subset": None, "fit": fit, "points": points}
    else:
        best = max(variants, key=lambda item: item["selectionScore"])
        fit = best["fit"]
        points = best["points"]

    benchmark = dot_fit.benchmark_fit(ai_grid, label, fit, points, combined_mask)
    overlay_path = write_overlay(line_lattice, dot_fit, ai_grid, label, source_id, points, combined_mask, fit, overlays_dir, best.get("subset"), first_angle, second_angle)
    return {
        "sourceId": source_id,
        "decision": fit.decision,
        "reasons": fit.reasons,
        "selectionScore": round_metric(best["selectionScore"]),
        "firstAngle": round_metric(first_angle) if first_angle is not None else None,
        "secondAngle": round_metric(second_angle) if second_angle is not None else None,
        "firstSegments": first_segments,
        "secondSegments": second_segments,
        "lineFamilyCounts": [len(first_clusters), len(second_clusters)],
        "subset": best.get("subset"),
        "variantCount": len(variants),
        "overlayImage": str(overlay_path),
        "fit": fit.metrics,
        "benchmark": benchmark,
        "variantSummaries": [line_lattice.variant_summary(item) for item in sorted(variants, key=lambda item: item["selectionScore"], reverse=True)[:12]],
    }


def extract_mask(ai_grid: Any, ai_arbiter: Any, result: dict[str, Any]) -> np.ndarray:
    image_path = resolve_output_path(result["outputImage"])
    rgb = load_rgb(image_path)
    mask = ai_arbiter.extract_line_mask(ai_grid, rgb, result)
    if float((mask > 0).mean()) < 0.005:
        mask = ai_grid.extract_signal_mask(rgb, "white_mask")
    return mask


def dominant_family_clusters(mask_probe: Any, line_mask: np.ndarray) -> tuple[list[Any], float | None, int]:
    segments = mask_probe.hough_segments(line_mask)
    if not segments:
        return [], None, 0
    angle = dominant_angle(segments)
    selected = mask_probe.select_segments_for_family(segments, angle)
    clusters = mask_probe.cluster_family_lines(selected, line_mask.shape[1], line_mask.shape[0])
    clusters = mask_probe.prune_regular_sequence(clusters)
    return clusters, angle, len(segments)


def dominant_angle(segments: list[Any]) -> float:
    angles = np.array([segment.angle for segment in segments])
    lengths = np.array([segment.length for segment in segments])
    hist, bins = np.histogram(angles, bins=180, range=(0, 180), weights=lengths)
    index = int(np.argmax(hist))
    local_angles = []
    local_weights = []
    center = float((bins[index] + bins[index + 1]) / 2)
    for segment in segments:
        if circular_angle_distance(segment.angle, center) <= 16:
            local_angles.append(segment.angle)
            local_weights.append(segment.length)
    if not local_angles:
        return center
    doubled = np.radians(np.array(local_angles) * 2.0)
    sin_sum = float(np.sum(np.sin(doubled) * np.array(local_weights)))
    cos_sum = float(np.sum(np.cos(doubled) * np.array(local_weights)))
    return (math.degrees(math.atan2(sin_sum, cos_sum)) / 2.0 + 180.0) % 180.0


def circular_angle_distance(left: float, right: float) -> float:
    diff = abs((left - right + 90.0) % 180.0 - 90.0)
    return min(diff, 180.0 - diff)


def write_overlay(
    line_lattice: Any,
    dot_fit: Any,
    ai_grid: Any,
    label: dict[str, Any],
    source_id: str,
    points: np.ndarray,
    line_mask: np.ndarray,
    fit: Any,
    overlays_dir: Path,
    subset: dict[str, Any] | None,
    first_angle: float | None,
    second_angle: float | None,
) -> Path:
    path = line_lattice.write_overlay(dot_fit, ai_grid, label, source_id, points, line_mask, fit, overlays_dir, subset)
    target = overlays_dir / f"{slugify(source_id)}-family-pair.png"
    path.replace(target)
    with Image.open(target) as image:
        canvas = image.convert("RGB")
    draw = ImageDraw.Draw(canvas)
    draw.rectangle((8, 70, min(canvas.width - 8, 650), 96), fill=(0, 0, 0))
    draw.text((14, 75), f"family pair angles {format_angle(first_angle)} / {format_angle(second_angle)}", fill=(255, 255, 255))
    canvas.save(target)
    return target


def format_angle(value: float | None) -> str:
    return "?" if value is None else f"{value:.1f}"


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
        "# AI Family Pair Lattice",
        "",
        f"- Selection mode: {report['selectionMode']}",
        f"- First prompt: `{report['firstPrompt']}`",
        f"- Second prompt: `{report['secondPrompt']}`",
        f"- Total: `{report['summary']['total']}`",
        f"- Decisions: `{json.dumps(report['summary']['decisions'], sort_keys=True)}`",
        "",
        "| Source | Decision | Angles | Families | Subset | Variants | Inliers | Span | Homography line <=.15 | Mesh line <=.15 | Reasons | Overlay |",
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
            f"| `{result['sourceId']}` | `{result['decision']}` | {format_angle(result['firstAngle'])}/{format_angle(result['secondAngle'])} | "
            f"{result['lineFamilyCounts']} | {subset_text} | {result['variantCount']} | {fit.get('homographyInliers')} | "
            f"{fit.get('spanI')}x{fit.get('spanJ')} | {bench.get('truthLineSamplesWithin0_15SquaresPct')} | "
            f"{bench.get('truthMeshSamplesWithin0_15SquaresPct')} | {'; '.join(result['reasons'])} | `{result['overlayImage']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def render_console(report: dict[str, Any]) -> str:
    lines = [f"AI family pair lattice: {json.dumps(report['summary']['decisions'], sort_keys=True)}"]
    for result in report["results"]:
        fit = result["fit"]
        bench = result["benchmark"]
        lines.append(
            f"- {result['sourceId']}: {result['decision']} families={result['lineFamilyCounts']} "
            f"angles={format_angle(result['firstAngle'])}/{format_angle(result['secondAngle'])} "
            f"inliers={fit.get('homographyInliers')} truthLine<=.15={bench.get('truthLineSamplesWithin0_15SquaresPct')}"
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
