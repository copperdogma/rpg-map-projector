#!/usr/bin/env python3
"""Compare boundary-seeking AI grid seeds with bounded image-frame seeds.

The frame plan treats the detected lattice as an alignment coordinate system
and expands it over the source photo, instead of trying to infer the physical
mat boundary. This report is label-backed evidence for whether that product
pivot improves usable coverage without changing the selected alignment model.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HYBRID_REPORT = ROOT / "test-results" / "ai-grid-hybrid-prompt-ensemble-summary-v1" / "report.json"
DEFAULT_DOT_REPORT = ROOT / "test-results" / "ai-dot-lattice-fit-risk-aware-summary-v1" / "report.json"
DEFAULT_LABEL_FILE = ROOT / "input" / "map-grid-labels.json"
DEFAULT_OUT_DIR = ROOT / "test-results" / "ai-grid-frame-summary-v1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hybrid-report", default=str(DEFAULT_HYBRID_REPORT))
    parser.add_argument("--dot-report", default=str(DEFAULT_DOT_REPORT))
    parser.add_argument("--label-file", default=str(DEFAULT_LABEL_FILE))
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--max-span", type=int, default=100)
    parser.add_argument("--min-band-overlap", type=float, default=0.10)
    args = parser.parse_args()

    hybrid_report = read_json(Path(args.hybrid_report))
    dot_by_source = {result["sourceId"]: result for result in read_json(Path(args.dot_report)).get("results", [])}
    labels = {
        label["sourceId"]: label
        for label in read_json(Path(args.label_file)).get("labels", [])
        if label.get("benchmark") and str(label.get("sourceId", "")).startswith("real-map-home-")
    }

    results = []
    for hybrid in hybrid_report.get("results", []):
        source_id = hybrid["sourceId"]
        label = labels.get(source_id)
        if not label:
            continue
        candidate = resolve_selected_candidate(hybrid, dot_by_source[source_id], label)
        frame_bounds = bounds_for_image_frame(
            candidate["homography"],
            label["imageWidth"],
            label["imageHeight"],
            candidate["oldBounds"],
            args.max_span,
            args.min_band_overlap,
        )
        old_coverage = label_intersection_coverage(candidate["homography"], candidate["oldBounds"], label)
        frame_coverage = label_intersection_coverage(candidate["homography"], frame_bounds, label)
        old_empty = empty_image_bands(candidate["homography"], candidate["oldBounds"], label["imageWidth"], label["imageHeight"])
        frame_empty = empty_image_bands(candidate["homography"], frame_bounds, label["imageWidth"], label["imageHeight"])
        results.append(
            {
                "sourceId": source_id,
                "selectedBranch": hybrid["selectedBranch"],
                "linePromptId": hybrid.get("linePromptId"),
                "selectedLineWithin0_15Pct": hybrid.get("selectedLineWithin0_15Pct"),
                "labelColumns": label["columns"],
                "labelRows": label["rows"],
                "oldColumns": bounds_width(candidate["oldBounds"]),
                "oldRows": bounds_height(candidate["oldBounds"]),
                "frameColumns": bounds_width(frame_bounds),
                "frameRows": bounds_height(frame_bounds),
                "oldVisibleLabelIntersectionCoveragePct": old_coverage["coveragePct"],
                "frameVisibleLabelIntersectionCoveragePct": frame_coverage["coveragePct"],
                "coverageGainPct": round_metric(frame_coverage["coveragePct"] - old_coverage["coveragePct"]),
                "oldCoveredVisibleIntersections": old_coverage["covered"],
                "frameCoveredVisibleIntersections": frame_coverage["covered"],
                "visibleLabelIntersections": frame_coverage["total"],
                "oldEmptyImageBands": old_empty,
                "frameEmptyImageBands": frame_empty,
                "oldBounds": candidate["oldBounds"],
                "frameBounds": frame_bounds,
                "frameWithinCap": bounds_width(frame_bounds) <= args.max_span and bounds_height(frame_bounds) <= args.max_span,
            }
        )

    report = {
        "outDir": str(Path(args.out_dir)),
        "mode": (
            "report-only bounded grid-frame comparison: preserve the selected lattice alignment, "
            "replace boundary-seeking extents with image-frame extents capped at maxSpan"
        ),
        "maxSpan": args.max_span,
        "minBandOverlap": args.min_band_overlap,
        "inputs": {
            "hybridReport": str(Path(args.hybrid_report)),
            "dotReport": str(Path(args.dot_report)),
            "labelFile": str(Path(args.label_file)),
        },
        "summary": summarize(results),
        "results": results,
    }
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(f"{json.dumps(report, indent=2)}\n")
    (out_dir / "report.md").write_text(render_markdown(report))
    print(render_console(report))


def resolve_selected_candidate(hybrid: dict[str, Any], dot: dict[str, Any], label: dict[str, Any]) -> dict[str, Any]:
    if hybrid["selectedBranch"] == "line-graph":
        report_dir = resolve_repo_path(hybrid["lineGraphReportOutDir"])
        report = read_json(report_dir / "report.json")
        selected = next(item["selected"] for item in report["results"] if item["sourceId"] == hybrid["sourceId"])
        seed = selected["labelerSeed"]
        sx = label["imageWidth"] / max(1, seed["imageWidth"])
        sy = label["imageHeight"] / max(1, seed["imageHeight"])
        return {
            "homography": scale_homography(flat_to_matrix(seed["gridHomography"]), sx, sy),
            "oldBounds": normalize_bounds(seed["gridBounds"]),
        }

    line_width, line_height = image_dimensions(resolve_repo_path(dot["lineImage"]))
    sx = label["imageWidth"] / max(1, line_width)
    sy = label["imageHeight"] / max(1, line_height)
    return {
        "homography": scale_homography(dot["fit"]["homography"], sx, sy),
        "oldBounds": bounds_from_observed_cells(dot["observedMesh"]["cells"]),
    }


def bounds_for_image_frame(
    homography: list[list[float]],
    image_width: int,
    image_height: int,
    base_bounds: dict[str, int],
    max_span: int,
    min_band_overlap: float,
) -> dict[str, int]:
    inverse = invert_homography(homography)
    image_points = [
        (0, 0),
        (image_width, 0),
        (image_width, image_height),
        (0, image_height),
        (image_width / 2, 0),
        (image_width, image_height / 2),
        (image_width / 2, image_height),
        (0, image_height / 2),
        (image_width / 2, image_height / 2),
    ]
    grid_points = [project(inverse, x, y) for x, y in image_points]
    grid_points.append(((base_bounds["minI"] + base_bounds["maxI"]) / 2, (base_bounds["minJ"] + base_bounds["maxJ"]) / 2))
    bounds = {
        "minI": math.floor(min(point[0] for point in grid_points)) - 1,
        "maxI": math.ceil(max(point[0] for point in grid_points)) + 1,
        "minJ": math.floor(min(point[1] for point in grid_points)) - 1,
        "maxJ": math.ceil(max(point[1] for point in grid_points)) + 1,
    }
    return trim_bounds_to_image_overlap(
        cap_bounds_span(bounds, base_bounds, max_span),
        homography,
        image_width,
        image_height,
        min_band_overlap,
    )


def cap_bounds_span(bounds: dict[str, int], base_bounds: dict[str, int], max_span: int) -> dict[str, int]:
    min_i, max_i = cap_axis(bounds["minI"], bounds["maxI"], (base_bounds["minI"] + base_bounds["maxI"]) / 2, max_span)
    min_j, max_j = cap_axis(bounds["minJ"], bounds["maxJ"], (base_bounds["minJ"] + base_bounds["maxJ"]) / 2, max_span)
    return {"minI": min_i, "maxI": max_i, "minJ": min_j, "maxJ": max_j}


def cap_axis(min_value: int, max_value: int, center: float, max_span: int) -> tuple[int, int]:
    if max_value - min_value <= max_span:
        return min_value, max_value
    next_min = math.floor(center - max_span / 2)
    return next_min, next_min + max_span


def trim_bounds_to_image_overlap(
    bounds: dict[str, int],
    homography: list[list[float]],
    image_width: int,
    image_height: int,
    min_band_overlap: float,
) -> dict[str, int]:
    next_bounds = dict(bounds)
    for _ in range(240):
        changed = False
        if bounds_width(next_bounds) > 1 and axis_band_image_overlap(homography, next_bounds, "i", next_bounds["minI"], image_width, image_height) < min_band_overlap:
            next_bounds["minI"] += 1
            changed = True
        if bounds_width(next_bounds) > 1 and axis_band_image_overlap(homography, next_bounds, "i", next_bounds["maxI"] - 1, image_width, image_height) < min_band_overlap:
            next_bounds["maxI"] -= 1
            changed = True
        if bounds_height(next_bounds) > 1 and axis_band_image_overlap(homography, next_bounds, "j", next_bounds["minJ"], image_width, image_height) < min_band_overlap:
            next_bounds["minJ"] += 1
            changed = True
        if bounds_height(next_bounds) > 1 and axis_band_image_overlap(homography, next_bounds, "j", next_bounds["maxJ"] - 1, image_width, image_height) < min_band_overlap:
            next_bounds["maxJ"] -= 1
            changed = True
        if not changed:
            break
    return next_bounds


def axis_band_image_overlap(
    homography: list[list[float]],
    bounds: dict[str, int],
    axis: str,
    index: int,
    image_width: int,
    image_height: int,
) -> float:
    other_min = bounds["minJ"] if axis == "i" else bounds["minI"]
    other_max = bounds["maxJ"] if axis == "i" else bounds["maxI"]
    span = max(1, other_max - other_min)
    steps = min(120, max(8, math.ceil(span * 3)))
    inside = 0
    total = 0
    for step in range(steps + 1):
        t = other_min + span * step / steps
        for offset in (0.2, 0.5, 0.8):
            x = index + offset if axis == "i" else t
            y = t if axis == "i" else index + offset
            total += 1
            try:
                if is_image_point(project(homography, x, y), image_width, image_height):
                    inside += 1
            except ValueError:
                pass
    return inside / total if total else 0.0


def empty_image_bands(
    homography: list[list[float]],
    bounds: dict[str, int],
    image_width: int,
    image_height: int,
) -> dict[str, int]:
    columns = sum(
        1
        for i in range(bounds["minI"], bounds["maxI"])
        if axis_band_image_overlap(homography, bounds, "i", i, image_width, image_height) <= 0
    )
    rows = sum(
        1
        for j in range(bounds["minJ"], bounds["maxJ"])
        if axis_band_image_overlap(homography, bounds, "j", j, image_width, image_height) <= 0
    )
    return {"columns": columns, "rows": rows}


def label_intersection_coverage(
    candidate_homography: list[list[float]],
    bounds: dict[str, int],
    label: dict[str, Any],
) -> dict[str, Any]:
    inverse_candidate = invert_homography(candidate_homography)
    label_homography = solve_homography(
        [(0, 0), (label["columns"], 0), (label["columns"], label["rows"]), (0, label["rows"])],
        [(point["x"], point["y"]) for point in label["corners"]],
    )
    covered = 0
    total = 0
    for i in range(label["columns"] + 1):
        for j in range(label["rows"] + 1):
            image_point = project(label_homography, i, j)
            if not is_image_point(image_point, label["imageWidth"], label["imageHeight"]):
                continue
            grid_point = project(inverse_candidate, image_point[0], image_point[1])
            total += 1
            if (
                bounds["minI"] - 0.5 <= grid_point[0] <= bounds["maxI"] + 0.5
                and bounds["minJ"] - 0.5 <= grid_point[1] <= bounds["maxJ"] + 0.5
            ):
                covered += 1
    return {
        "covered": covered,
        "total": total,
        "coveragePct": round_metric(0.0 if total == 0 else 100 * covered / total),
    }


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    old_coverages = [result["oldVisibleLabelIntersectionCoveragePct"] for result in results]
    frame_coverages = [result["frameVisibleLabelIntersectionCoveragePct"] for result in results]
    return {
        "total": len(results),
        "oldMeanVisibleLabelIntersectionCoveragePct": round_metric(sum(old_coverages) / len(old_coverages)) if old_coverages else None,
        "oldMinVisibleLabelIntersectionCoveragePct": min(old_coverages) if old_coverages else None,
        "frameMeanVisibleLabelIntersectionCoveragePct": round_metric(sum(frame_coverages) / len(frame_coverages)) if frame_coverages else None,
        "frameMinVisibleLabelIntersectionCoveragePct": min(frame_coverages) if frame_coverages else None,
        "allFrameSeedsWithinCap": all(result["frameWithinCap"] for result in results),
        "allFrameSeedsAvoidEmptyImageBands": all(
            result["frameEmptyImageBands"]["columns"] == 0 and result["frameEmptyImageBands"]["rows"] == 0
            for result in results
        ),
        "frameCoverageImprovedSources": [
            result["sourceId"]
            for result in results
            if result["frameVisibleLabelIntersectionCoveragePct"] > result["oldVisibleLabelIntersectionCoveragePct"]
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# AI Grid Frame Summary",
        "",
        f"- Mode: {report['mode']}",
        f"- Max span: `{report['maxSpan']}` cells per axis",
        f"- Minimum kept edge-band image overlap: `{report['minBandOverlap']}`",
        f"- Old visible-label coverage mean/min: `{summary['oldMeanVisibleLabelIntersectionCoveragePct']}` / `{summary['oldMinVisibleLabelIntersectionCoveragePct']}`",
        f"- Frame visible-label coverage mean/min: `{summary['frameMeanVisibleLabelIntersectionCoveragePct']}` / `{summary['frameMinVisibleLabelIntersectionCoveragePct']}`",
        f"- Frame seeds within cap: `{summary['allFrameSeedsWithinCap']}`",
        f"- Frame seeds avoid fully off-image rows/columns: `{summary['allFrameSeedsAvoidEmptyImageBands']}`",
        "",
        "| Source | Branch | Label | Old extent | Old visible coverage | Frame extent | Frame visible coverage | Empty frame bands | Selected line <=.15 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for result in report["results"]:
        lines.append(
            f"| `{result['sourceId']}` | `{result['selectedBranch']}` | {result['labelColumns']}x{result['labelRows']} | "
            f"{result['oldColumns']}x{result['oldRows']} | {result['oldVisibleLabelIntersectionCoveragePct']} | "
            f"{result['frameColumns']}x{result['frameRows']} | {result['frameVisibleLabelIntersectionCoveragePct']} | "
            f"{result['frameEmptyImageBands']['columns']}c/{result['frameEmptyImageBands']['rows']}r | "
            f"{result['selectedLineWithin0_15Pct']} |"
        )
    lines.extend(
        [
            "",
            "Interpretation: the frame plan does not improve or degrade lattice alignment; it keeps the selected homography and changes only the projected extent.",
            "",
        ]
    )
    return "\n".join(lines)


def render_console(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "AI grid frame summary: "
        f"old mean/min coverage={summary['oldMeanVisibleLabelIntersectionCoveragePct']}/{summary['oldMinVisibleLabelIntersectionCoveragePct']} "
        f"frame mean/min coverage={summary['frameMeanVisibleLabelIntersectionCoveragePct']}/{summary['frameMinVisibleLabelIntersectionCoveragePct']} "
        f"withinCap={summary['allFrameSeedsWithinCap']} noEmptyBands={summary['allFrameSeedsAvoidEmptyImageBands']}"
    ]
    for result in report["results"]:
        lines.append(
            f"- {result['sourceId']}: old {result['oldColumns']}x{result['oldRows']} "
            f"coverage={result['oldVisibleLabelIntersectionCoveragePct']} -> frame {result['frameColumns']}x{result['frameRows']} "
            f"coverage={result['frameVisibleLabelIntersectionCoveragePct']}"
        )
    lines.append(f"Artifacts: {report['outDir']}/report.md")
    return "\n".join(lines)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def resolve_repo_path(path: str) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def normalize_bounds(value: dict[str, Any]) -> dict[str, int]:
    return {
        "minI": int(round(value["minI"])),
        "maxI": int(round(value["maxI"])),
        "minJ": int(round(value["minJ"])),
        "maxJ": int(round(value["maxJ"])),
    }


def bounds_from_observed_cells(cells: list[list[int]]) -> dict[str, int]:
    return {
        "minI": min(cell[0] for cell in cells),
        "maxI": max(cell[0] + 1 for cell in cells),
        "minJ": min(cell[1] for cell in cells),
        "maxJ": max(cell[1] + 1 for cell in cells),
    }


def bounds_width(bounds: dict[str, int]) -> int:
    return max(0, bounds["maxI"] - bounds["minI"])


def bounds_height(bounds: dict[str, int]) -> int:
    return max(0, bounds["maxJ"] - bounds["minJ"])


def flat_to_matrix(values: list[float]) -> list[list[float]]:
    return [values[0:3], values[3:6], values[6:9]]


def scale_homography(homography: list[list[float]], scale_x: float, scale_y: float) -> list[list[float]]:
    return [
        [homography[0][0] * scale_x, homography[0][1] * scale_x, homography[0][2] * scale_x],
        [homography[1][0] * scale_y, homography[1][1] * scale_y, homography[1][2] * scale_y],
        [homography[2][0], homography[2][1], homography[2][2]],
    ]


def solve_homography(source: list[tuple[float, float]], target: list[tuple[float, float]]) -> list[list[float]]:
    matrix = []
    values = []
    for (x, y), (target_x, target_y) in zip(source, target):
        matrix.append([x, y, 1, 0, 0, 0, -x * target_x, -y * target_x])
        values.append(target_x)
        matrix.append([0, 0, 0, x, y, 1, -x * target_y, -y * target_y])
        values.append(target_y)
    solution = solve_linear_system(matrix, values)
    return [
        [solution[0], solution[1], solution[2]],
        [solution[3], solution[4], solution[5]],
        [solution[6], solution[7], 1.0],
    ]


def solve_linear_system(matrix: list[list[float]], values: list[float]) -> list[float]:
    size = len(values)
    augmented = [row[:] + [values[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        pivot_value = augmented[column][column]
        if abs(pivot_value) < 1e-10:
            raise ValueError("Cannot solve degenerate homography")
        for cell in range(column, size + 1):
            augmented[column][cell] /= pivot_value
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            for cell in range(column, size + 1):
                augmented[row][cell] -= factor * augmented[column][cell]
    return [row[size] for row in augmented]


def invert_homography(homography: list[list[float]]) -> list[list[float]]:
    [[a, b, c], [d, e, f], [g, h, i]] = homography
    determinant = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    if abs(determinant) < 1e-10:
        raise ValueError("Homography is not invertible")
    return [
        [(e * i - f * h) / determinant, (c * h - b * i) / determinant, (b * f - c * e) / determinant],
        [(f * g - d * i) / determinant, (a * i - c * g) / determinant, (c * d - a * f) / determinant],
        [(d * h - e * g) / determinant, (b * g - a * h) / determinant, (a * e - b * d) / determinant],
    ]


def project(homography: list[list[float]], x: float, y: float) -> tuple[float, float]:
    denominator = homography[2][0] * x + homography[2][1] * y + homography[2][2]
    if abs(denominator) < 1e-10:
        raise ValueError("Homography projects point to infinity")
    return (
        (homography[0][0] * x + homography[0][1] * y + homography[0][2]) / denominator,
        (homography[1][0] * x + homography[1][1] * y + homography[1][2]) / denominator,
    )


def is_image_point(point: tuple[float, float], image_width: int, image_height: int) -> bool:
    return 0 <= point[0] <= image_width and 0 <= point[1] <= image_height


def image_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if len(data) >= 4 and data[:2] == b"\xff\xd8":
        offset = 2
        frame_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
        while offset + 4 < len(data):
            while offset < len(data) and data[offset] != 0xFF:
                offset += 1
            while offset < len(data) and data[offset] == 0xFF:
                offset += 1
            if offset >= len(data):
                continue
            marker = data[offset]
            offset += 1
            if marker == 0xD9 or 0xD0 <= marker <= 0xD7:
                continue
            if offset + 2 > len(data):
                break
            length = int.from_bytes(data[offset : offset + 2], "big")
            if marker in frame_markers:
                return (
                    int.from_bytes(data[offset + 5 : offset + 7], "big"),
                    int.from_bytes(data[offset + 3 : offset + 5], "big"),
                )
            offset += length
    raise ValueError(f"Expected PNG or JPEG image at {path}")


def round_metric(value: float) -> float:
    return round(float(value), 3)


if __name__ == "__main__":
    main()
