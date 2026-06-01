#!/usr/bin/env python3
"""Parse AI-generated gridline masks as a local grid graph.

This is a discovery/eval script. It uses one generated line mask, skeletonizes
it, treats grid intersections as graph nodes, treats skeleton runs as graph
edges, and assigns local grid coordinates by walking the graph. Labels are used
only for benchmark scoring.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps


ROOT = Path(__file__).resolve().parents[1]
AI_GRID_PATH = ROOT / "scripts" / "ai-grid-experiment.py"
AI_ARBITER_PATH = ROOT / "scripts" / "ai-evidence-arbiter.py"
AI_LINE_SKELETON_PATH = ROOT / "scripts" / "ai-line-skeleton-junction-probe.py"
LABELS_PATH = ROOT / "input" / "map-grid-labels.json"
DEFAULT_OUT_DIR = ROOT / "test-results" / "ai-line-graph-lattice-v1"
DEFAULT_LINE_PROMPT_ID = "white-grid-exact-copy-no-marks-v1"


@dataclass(frozen=True)
class GraphSetting:
    threshold: int
    close_kernel: int
    close_iterations: int


@dataclass
class GraphCandidate:
    source_id: str
    report_path: str
    setting: GraphSetting
    node_count: int
    edge_count: int
    component_count: int
    component_nodes: int
    component_edges: int
    component_node_ids: list[int]
    component_edge_pairs: list[tuple[int, int]]
    assigned_nodes: int
    coordinate_conflicts: int
    coordinate_conflict_pct: float
    span_i: int
    span_j: int
    axis_balance: float
    coordinate_edges: int
    possible_coordinate_edges: int
    coordinate_edge_density_pct: float
    complete_cells: int
    possible_cells: int
    complete_cell_density_pct: float
    node_fill_pct: float
    grown_span_i: int | None
    grown_span_j: int | None
    grown_line_support_mean_pct: float | None
    grown_line_samples: int
    grown_line_within_0_15_pct: float | None
    trusted_grown_extent: bool
    trusted_grown_reason: str
    selected_line_within_0_15_pct: float | None
    graph_score: float
    decision: str
    reasons: list[str]
    mesh_samples: int
    mesh_within_0_15_pct: float | None
    dot_within_0_15_pct: float | None
    overlay_image: str | None = None
    labeler_seed: dict[str, Any] | None = None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--line-reports-glob", default="test-results/ai-grid-parallel-current/*/*/*/line/report.json")
    parser.add_argument("--line-prompt-id", default=DEFAULT_LINE_PROMPT_ID)
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument(
        "--settings",
        default="64:3:1,64:3:2,64:5:2",
        help="Comma-separated threshold:close-kernel:close-iterations settings.",
    )
    args = parser.parse_args()

    ai_grid = load_module("ai_grid_experiment", AI_GRID_PATH)
    ai_arbiter = load_module("ai_evidence_arbiter", AI_ARBITER_PATH)
    line_skeleton = load_module("ai_line_skeleton_junction_probe", AI_LINE_SKELETON_PATH)
    labels = {label["sourceId"]: label for label in json.loads(LABELS_PATH.read_text())["labels"]}
    reports = load_report_groups(args.line_reports_glob, args.line_prompt_id)
    settings = parse_settings(args.settings)

    out_dir = Path(args.out_dir)
    overlays_dir = out_dir / "overlays"
    if not args.summary_only:
        overlays_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for source_id in sorted(set(reports) & set(labels)):
        candidates: list[GraphCandidate] = []
        for report in reports[source_id]:
            for setting in settings:
                candidate = analyze_report(
                    ai_grid,
                    ai_arbiter,
                    line_skeleton,
                    labels[source_id],
                    report,
                    args.line_prompt_id,
                    setting,
                    overlays_dir,
                    write_visuals=not args.summary_only,
                )
                if candidate is not None:
                    candidates.append(candidate)
        if not candidates:
            continue
        selected = select_candidate(candidates)
        results.append({
            "sourceId": source_id,
            "selected": candidate_to_json(selected),
            "candidates": [candidate_to_json(candidate) for candidate in sorted(candidates, key=lambda item: item.graph_score, reverse=True)],
        })

    report = {
        "outDir": str(out_dir),
        "linePromptId": args.line_prompt_id,
        "selectionMode": "single AI line mask parsed as an observed grid graph; labels are benchmark-only",
        "settings": [setting_to_json(setting) for setting in settings],
        "summaryOnly": args.summary_only,
        "summary": summarize(results),
        "results": results,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(f"{json.dumps(report, indent=2)}\n")
    (out_dir / "report.md").write_text(render_markdown(report))
    print(render_console(report))


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def parse_settings(value: str) -> list[GraphSetting]:
    settings = []
    for chunk in value.split(","):
        if not chunk.strip():
            continue
        threshold, close_kernel, close_iterations = [int(part) for part in chunk.split(":")]
        settings.append(GraphSetting(threshold, close_kernel, close_iterations))
    return settings


def load_report_groups(pattern: str, prompt_id: str) -> dict[str, list[dict[str, Any]]]:
    reports: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in sorted(ROOT.glob(pattern)):
        report = json.loads(path.read_text())
        if not report_has_prompt(report, prompt_id):
            continue
        report["_reportPath"] = str(path)
        reports[report["sourceId"]].append(report)
    return reports


def report_has_prompt(report: dict[str, Any], prompt_id: str) -> bool:
    return any(result.get("ok") and result.get("outputImage") and result.get("promptId") == prompt_id for result in report.get("results", []))


def analyze_report(
    ai_grid: Any,
    ai_arbiter: Any,
    line_skeleton: Any,
    label: dict[str, Any],
    report: dict[str, Any],
    line_prompt_id: str,
    setting: GraphSetting,
    overlays_dir: Path,
    write_visuals: bool,
) -> GraphCandidate | None:
    line_experiment = first_prompt_result(report, line_prompt_id)
    line_path = resolve_output_path(line_experiment["outputImage"])
    line_rgb = load_rgb(line_path)
    line_mask = ai_arbiter.extract_line_mask(ai_grid, line_rgb, line_experiment)
    graph = build_graph(line_skeleton, line_mask, setting)
    if not graph["components"]:
        return None
    scaled_label = ai_grid.scale_label(label, line_mask.shape[1], line_mask.shape[0])
    image_to_truth = cv2.getPerspectiveTransform(
        ai_grid.label_corners(scaled_label),
        np.float32([[0, 0], [scaled_label["columns"], 0], [scaled_label["columns"], scaled_label["rows"]], [0, scaled_label["rows"]]]),
    )
    candidates = [
        component_candidate(label["sourceId"], report["_reportPath"], setting, graph, component, image_to_truth)
        for component in graph["components"]
    ]
    candidates = [candidate for candidate in candidates if candidate is not None]
    if not candidates:
        return None
    candidate = select_component_candidate(candidates)
    if write_visuals:
        candidate.overlay_image = str(write_overlay(ai_grid, label, graph, candidate, overlays_dir))
    return candidate


def first_prompt_result(report: dict[str, Any], prompt_id: str) -> dict[str, Any]:
    for result in report.get("results", []):
        if result.get("ok") and result.get("outputImage") and result.get("promptId") == prompt_id:
            return result
    raise RuntimeError(f"No successful image result for {prompt_id}")


def resolve_output_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def load_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.array(ImageOps.exif_transpose(image).convert("RGB"))


def build_graph(line_skeleton: Any, line_mask: np.ndarray, setting: GraphSetting) -> dict[str, Any]:
    binary = (line_mask >= setting.threshold).astype(np.uint8)
    binary = cv2.morphologyEx(
        binary,
        cv2.MORPH_CLOSE,
        np.ones((setting.close_kernel, setting.close_kernel), np.uint8),
        iterations=setting.close_iterations,
    )
    skeleton = line_skeleton.zhang_suen_thinning(binary)
    neighbors = cv2.filter2D(skeleton, cv2.CV_16S, np.ones((3, 3), dtype=np.uint8), borderType=cv2.BORDER_CONSTANT) - skeleton
    branch = ((skeleton > 0) & (neighbors >= 4)).astype(np.uint8)
    branch = cv2.dilate(branch, np.ones((3, 3), np.uint8), iterations=1)
    node_count, node_labels, stats, centroids = cv2.connectedComponentsWithStats(branch, 8)
    nodes = []
    for index in range(1, node_count):
        area = int(stats[index, cv2.CC_STAT_AREA])
        width = int(stats[index, cv2.CC_STAT_WIDTH])
        height = int(stats[index, cv2.CC_STAT_HEIGHT])
        if 2 <= area <= 350 and width <= 24 and height <= 24:
            nodes.append((index, centroids[index]))
    id_map = {old_id: new_id for new_id, (old_id, _centroid) in enumerate(nodes)}
    points = np.float32([centroid for _old_id, centroid in nodes])
    node_mask = np.isin(node_labels, list(id_map)).astype(np.uint8)
    edge_skeleton = ((skeleton > 0) & (node_mask == 0)).astype(np.uint8)
    edge_count, edge_labels, edge_stats, _edge_centroids = cv2.connectedComponentsWithStats(edge_skeleton, 8)
    edges: set[tuple[int, int]] = set()
    edge_touch_kernel = np.ones((7, 7), np.uint8)
    for edge_index in range(1, edge_count):
        if int(edge_stats[edge_index, cv2.CC_STAT_AREA]) < 3:
            continue
        component = (edge_labels == edge_index).astype(np.uint8)
        touching_nodes = cv2.dilate(component, edge_touch_kernel, iterations=1) & node_mask
        touching_ids = set(node_labels[touching_nodes > 0].tolist()) - {0}
        mapped_ids = [id_map[node_id] for node_id in touching_ids if node_id in id_map]
        if len(mapped_ids) == 2:
            edges.add(tuple(sorted(mapped_ids)))
    adjacency = [set() for _node in nodes]
    for start, end in edges:
        adjacency[start].add(end)
        adjacency[end].add(start)
    components = connected_components(adjacency)
    return {
        "lineMask": line_mask,
        "skeleton": skeleton,
        "points": points,
        "edges": edges,
        "adjacency": adjacency,
        "components": components,
    }


def connected_components(adjacency: list[set[int]]) -> list[list[int]]:
    seen: set[int] = set()
    components = []
    for index in range(len(adjacency)):
        if index in seen:
            continue
        stack = [index]
        seen.add(index)
        component = []
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(component)
    return components


def component_candidate(
    source_id: str,
    report_path: str,
    setting: GraphSetting,
    graph: dict[str, Any],
    component: list[int],
    image_to_truth: np.ndarray,
) -> GraphCandidate | None:
    points = graph["points"]
    component_set = set(component)
    component_edges = [(start, end) for start, end in graph["edges"] if start in component_set and end in component_set]
    coordinates, coordinate_conflicts = assign_coordinates(points, graph["adjacency"], component, component_edges)
    if not coordinates:
        return None
    mesh_samples = observed_edge_samples(points, component_edges, coordinates)
    mesh_within = None if len(mesh_samples) == 0 else line_within_pct(image_to_truth, mesh_samples)
    assigned_points = points[list(coordinates)]
    dot_within = None if len(assigned_points) == 0 else dot_within_pct(image_to_truth, assigned_points)
    span_i, span_j = coordinate_span(coordinates)
    axis_balance = min(span_i, span_j) / max(1, max(span_i, span_j))
    conflict_pct = coordinate_conflicts / max(1, len(component_edges)) * 100.0
    topology = coordinate_topology_metrics(coordinates, component_edges, span_i, span_j)
    grown_extent = support_grown_extent(graph["lineMask"], points, coordinates, image_to_truth)
    graph_score = graph_selection_score(len(mesh_samples), axis_balance, conflict_pct, topology)
    decision, reasons = decide_graph(len(coordinates), len(mesh_samples), axis_balance, conflict_pct, topology)
    trusted_grown_extent, trusted_grown_reason = decide_trusted_grown_extent(span_i, span_j, grown_extent, decision, topology)
    selected_line_within = grown_extent["lineWithin0_15Pct"] if trusted_grown_extent else mesh_within
    return GraphCandidate(
        source_id=source_id,
        report_path=report_path,
        setting=setting,
        node_count=len(points),
        edge_count=len(graph["edges"]),
        component_count=len(graph["components"]),
        component_nodes=len(component),
        component_edges=len(component_edges),
        component_node_ids=component,
        component_edge_pairs=component_edges,
        assigned_nodes=len(coordinates),
        coordinate_conflicts=coordinate_conflicts,
        coordinate_conflict_pct=round_metric(conflict_pct),
        span_i=span_i,
        span_j=span_j,
        axis_balance=round_metric(axis_balance),
        coordinate_edges=topology["coordinateEdges"],
        possible_coordinate_edges=topology["possibleCoordinateEdges"],
        coordinate_edge_density_pct=round_metric(topology["coordinateEdgeDensity"] * 100.0),
        complete_cells=topology["completeCells"],
        possible_cells=topology["possibleCells"],
        complete_cell_density_pct=round_metric(topology["completeCellDensity"] * 100.0),
        node_fill_pct=round_metric(topology["nodeFill"] * 100.0),
        grown_span_i=grown_extent["spanI"],
        grown_span_j=grown_extent["spanJ"],
        grown_line_support_mean_pct=grown_extent["lineSupportMeanPct"],
        grown_line_samples=grown_extent["lineSamples"],
        grown_line_within_0_15_pct=grown_extent["lineWithin0_15Pct"],
        trusted_grown_extent=trusted_grown_extent,
        trusted_grown_reason=trusted_grown_reason,
        selected_line_within_0_15_pct=selected_line_within,
        graph_score=round_metric(graph_score),
        decision=decision,
        reasons=reasons,
        mesh_samples=len(mesh_samples),
        mesh_within_0_15_pct=mesh_within,
        dot_within_0_15_pct=dot_within,
        labeler_seed=labeler_seed_for_component(graph, coordinates, component_edges),
    )


def assign_coordinates(
    points: np.ndarray,
    adjacency: list[set[int]],
    component: list[int],
    component_edges: list[tuple[int, int]],
) -> tuple[dict[int, tuple[int, int]], int]:
    edge_axes = classify_edge_axes(points, component_edges)
    if edge_axes is None:
        return {}, 0
    component_set = set(component)
    coordinates: dict[int, tuple[int, int]] = {component[0]: (0, 0)}
    queue = [component[0]]
    conflicts = 0
    while queue:
        current = queue.pop(0)
        current_coordinate = coordinates[current]
        for neighbor in adjacency[current]:
            if neighbor not in component_set:
                continue
            delta = edge_axes.get((current, neighbor))
            if delta is None:
                continue
            next_coordinate = (current_coordinate[0] + delta[0], current_coordinate[1] + delta[1])
            if neighbor in coordinates:
                if coordinates[neighbor] != next_coordinate:
                    conflicts += 1
            else:
                coordinates[neighbor] = next_coordinate
                queue.append(neighbor)
    return coordinates, conflicts


def classify_edge_axes(points: np.ndarray, component_edges: list[tuple[int, int]]) -> dict[tuple[int, int], tuple[int, int]] | None:
    vectors = []
    usable_edges = []
    for start, end in component_edges:
        vector = points[end] - points[start]
        if float(np.linalg.norm(vector)) < 4.0:
            continue
        angle = math.atan2(float(vector[1]), float(vector[0]))
        vectors.append([math.cos(2.0 * angle), math.sin(2.0 * angle)])
        usable_edges.append((start, end, vector))
    if len(usable_edges) < 4:
        return None
    _compactness, labels, centers = cv2.kmeans(
        np.array(vectors, dtype=np.float32),
        2,
        None,
        (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 1e-4),
        3,
        cv2.KMEANS_PP_CENTERS,
    )
    labels = labels.ravel()
    axes = []
    for index in (0, 1):
        center = centers[index]
        angle = 0.5 * math.atan2(float(center[1]), float(center[0]))
        axes.append(np.array([math.cos(angle), math.sin(angle)], dtype=np.float32))
    edge_axes: dict[tuple[int, int], tuple[int, int]] = {}
    for index, (start, end, vector) in enumerate(usable_edges):
        family = int(labels[index])
        sign = 1 if float(np.dot(vector, axes[family])) >= 0 else -1
        delta = (sign, 0) if family == 0 else (0, sign)
        edge_axes[(start, end)] = delta
        edge_axes[(end, start)] = (-delta[0], -delta[1])
    return edge_axes


def observed_edge_samples(points: np.ndarray, component_edges: list[tuple[int, int]], coordinates: dict[int, tuple[int, int]]) -> np.ndarray:
    samples = []
    for start, end in component_edges:
        if start not in coordinates or end not in coordinates:
            continue
        start_coordinate = coordinates[start]
        end_coordinate = coordinates[end]
        if abs(start_coordinate[0] - end_coordinate[0]) + abs(start_coordinate[1] - end_coordinate[1]) != 1:
            continue
        start_point = points[start]
        end_point = points[end]
        for amount in np.linspace(0.0, 1.0, 8):
            samples.append(start_point * (1.0 - amount) + end_point * amount)
    return np.float32(samples)


def coordinate_span(coordinates: dict[int, tuple[int, int]]) -> tuple[int, int]:
    values = list(coordinates.values())
    span_i = max(value[0] for value in values) - min(value[0] for value in values) + 1
    span_j = max(value[1] for value in values) - min(value[1] for value in values) + 1
    return int(span_i), int(span_j)


def coordinate_topology_metrics(
    coordinates: dict[int, tuple[int, int]],
    component_edges: list[tuple[int, int]],
    span_i: int,
    span_j: int,
) -> dict[str, float | int]:
    coord_nodes = set(coordinates.values())
    coord_edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    for start, end in component_edges:
        if start not in coordinates or end not in coordinates:
            continue
        start_coord = coordinates[start]
        end_coord = coordinates[end]
        if abs(start_coord[0] - end_coord[0]) + abs(start_coord[1] - end_coord[1]) != 1:
            continue
        coord_edges.add(tuple(sorted((start_coord, end_coord))))

    possible_edges = max(0, (span_i - 1) * span_j + (span_j - 1) * span_i)
    possible_cells = max(0, (span_i - 1) * (span_j - 1))
    min_i = min(coord[0] for coord in coord_nodes)
    max_i = max(coord[0] for coord in coord_nodes)
    min_j = min(coord[1] for coord in coord_nodes)
    max_j = max(coord[1] for coord in coord_nodes)
    complete_cells = 0
    for i in range(min_i, max_i):
        for j in range(min_j, max_j):
            corners = ((i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1))
            if any(corner not in coord_nodes for corner in corners):
                continue
            edges = (
                tuple(sorted(((i, j), (i + 1, j)))),
                tuple(sorted(((i, j), (i, j + 1)))),
                tuple(sorted(((i + 1, j), (i + 1, j + 1)))),
                tuple(sorted(((i, j + 1), (i + 1, j + 1)))),
            )
            if all(edge in coord_edges for edge in edges):
                complete_cells += 1

    return {
        "coordinateEdges": len(coord_edges),
        "possibleCoordinateEdges": possible_edges,
        "coordinateEdgeDensity": 0.0 if possible_edges == 0 else len(coord_edges) / possible_edges,
        "completeCells": complete_cells,
        "possibleCells": possible_cells,
        "completeCellDensity": 0.0 if possible_cells == 0 else complete_cells / possible_cells,
        "nodeFill": len(coord_nodes) / max(1, span_i * span_j),
    }


def labeler_seed_for_component(
    graph: dict[str, Any],
    coordinates: dict[int, tuple[int, int]],
    component_edges: list[tuple[int, int]],
) -> dict[str, Any] | None:
    if len(coordinates) < 8:
        return None
    points = graph["points"]
    ordered_ids = sorted(coordinates)
    src = np.float32([coordinates[node_id] for node_id in ordered_ids])
    dst = np.float32([points[node_id] for node_id in ordered_ids])
    homography, inlier_mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0, maxIters=3000, confidence=0.995)
    if homography is None or inlier_mask is None or int(inlier_mask.sum()) < 8:
        return None
    values = list(coordinates.values())
    bounds = {
        "minI": int(min(value[0] for value in values)),
        "maxI": int(max(value[0] for value in values)),
        "minJ": int(min(value[1] for value in values)),
        "maxJ": int(max(value[1] for value in values)),
    }
    height, width = graph["lineMask"].shape[:2]
    cells = complete_support_cells(coordinates, component_edges, homography)
    return {
        "imageWidth": int(width),
        "imageHeight": int(height),
        "corners": project_grid_corners(homography, bounds),
        "columns": max(1, bounds["maxI"] - bounds["minI"]),
        "rows": max(1, bounds["maxJ"] - bounds["minJ"]),
        "gridBounds": bounds,
        "gridHomography": [round_metric(float(value)) for value in homography.reshape(-1)],
        "supportOverlay": {
            "vertexCount": int(len(coordinates)),
            "cellCount": len(cells),
            "cells": cells,
        },
    }


def complete_support_cells(
    coordinates: dict[int, tuple[int, int]],
    component_edges: list[tuple[int, int]],
    homography: np.ndarray,
) -> list[dict[str, Any]]:
    coord_nodes = set(coordinates.values())
    coord_edges: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    for start, end in component_edges:
        if start not in coordinates or end not in coordinates:
            continue
        start_coord = coordinates[start]
        end_coord = coordinates[end]
        if abs(start_coord[0] - end_coord[0]) + abs(start_coord[1] - end_coord[1]) != 1:
            continue
        coord_edges.add(tuple(sorted((start_coord, end_coord))))
    cells = []
    min_i, max_i = min(coord[0] for coord in coord_nodes), max(coord[0] for coord in coord_nodes)
    min_j, max_j = min(coord[1] for coord in coord_nodes), max(coord[1] for coord in coord_nodes)
    for i in range(min_i, max_i):
        for j in range(min_j, max_j):
            corners = ((i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1))
            if any(corner not in coord_nodes for corner in corners):
                continue
            edges = (
                tuple(sorted(((i, j), (i + 1, j)))),
                tuple(sorted(((i, j), (i, j + 1)))),
                tuple(sorted(((i + 1, j), (i + 1, j + 1)))),
                tuple(sorted(((i, j + 1), (i + 1, j + 1)))),
            )
            if all(edge in coord_edges for edge in edges):
                cells.append({
                    "i": int(i),
                    "j": int(j),
                    "corners": project_grid_corners(
                        homography,
                        {"minI": i, "maxI": i + 1, "minJ": j, "maxJ": j + 1},
                    ),
                })
    return cells


def project_grid_corners(homography: np.ndarray, bounds: dict[str, int]) -> list[dict[str, float]]:
    points = np.float32([
        [bounds["minI"], bounds["minJ"]],
        [bounds["maxI"], bounds["minJ"]],
        [bounds["maxI"], bounds["maxJ"]],
        [bounds["minI"], bounds["maxJ"]],
    ]).reshape(1, -1, 2)
    projected = cv2.perspectiveTransform(points, homography).reshape(-1, 2)
    return [
        {"x": round_metric(float(point[0])), "y": round_metric(float(point[1]))}
        for point in projected
    ]


def support_grown_extent(
    line_mask: np.ndarray,
    points: np.ndarray,
    coordinates: dict[int, tuple[int, int]],
    image_to_truth: np.ndarray,
) -> dict[str, Any]:
    if len(coordinates) < 8:
        return empty_grown_extent()
    ordered_ids = sorted(coordinates)
    src = np.float32([coordinates[node_id] for node_id in ordered_ids])
    dst = np.float32([points[node_id] for node_id in ordered_ids])
    homography, inlier_mask = cv2.findHomography(src, dst, cv2.RANSAC, 5.0, maxIters=3000, confidence=0.995)
    if homography is None or inlier_mask is None or int(inlier_mask.sum()) < 8:
        return empty_grown_extent()

    values = list(coordinates.values())
    min_i, max_i = min(value[0] for value in values), max(value[0] for value in values)
    min_j, max_j = min(value[1] for value in values), max(value[1] for value in values)
    threshold_px = grown_line_threshold_px(homography, min_i, max_i, min_j, max_j)
    line_distance = cv2.distanceTransform((line_mask == 0).astype(np.uint8) * 255, cv2.DIST_L2, 3)

    def support_i(index: int, lower_j: int, upper_j: int) -> float:
        samples = np.float32([[index, value] for value in np.linspace(lower_j, upper_j, 80)])
        return projected_line_support(line_distance, homography, samples, threshold_px)

    def support_j(index: int, lower_i: int, upper_i: int) -> float:
        samples = np.float32([[value, index] for value in np.linspace(lower_i, upper_i, 80)])
        return projected_line_support(line_distance, homography, samples, threshold_px)

    support_floor = 0.60
    grown_min_i = grow_lower(lambda index: support_i(index, min_j, max_j), min_i, support_floor)
    grown_max_i = grow_upper(lambda index: support_i(index, min_j, max_j), max_i, support_floor)
    grown_min_j = grow_lower(lambda index: support_j(index, grown_min_i, grown_max_i), min_j, support_floor)
    grown_max_j = grow_upper(lambda index: support_j(index, grown_min_i, grown_max_i), max_j, support_floor)

    line_supports = []
    line_samples = []
    for i in range(grown_min_i, grown_max_i + 1):
        samples = np.float32([[i, value] for value in np.linspace(grown_min_j, grown_max_j, 80)])
        line_supports.append(projected_line_support(line_distance, homography, samples, threshold_px))
        line_samples.extend(samples.tolist())
    for j in range(grown_min_j, grown_max_j + 1):
        samples = np.float32([[value, j] for value in np.linspace(grown_min_i, grown_max_i, 80)])
        line_supports.append(projected_line_support(line_distance, homography, samples, threshold_px))
        line_samples.extend(samples.tolist())
    if not line_samples:
        return empty_grown_extent()
    image_samples = cv2.perspectiveTransform(np.float32(line_samples).reshape(1, -1, 2), homography).reshape(-1, 2)
    return {
        "spanI": int(grown_max_i - grown_min_i + 1),
        "spanJ": int(grown_max_j - grown_min_j + 1),
        "lineSupportMeanPct": round_metric(float(np.mean(line_supports)) * 100.0),
        "lineSamples": int(len(line_samples)),
        "lineWithin0_15Pct": line_within_pct(image_to_truth, image_samples),
    }


def decide_trusted_grown_extent(
    span_i: int,
    span_j: int,
    grown_extent: dict[str, Any],
    decision: str,
    topology: dict[str, float | int],
) -> tuple[bool, str]:
    grown_i = grown_extent.get("spanI")
    grown_j = grown_extent.get("spanJ")
    support = grown_extent.get("lineSupportMeanPct")
    if grown_i is None or grown_j is None or support is None:
        return False, "no grown extent"
    if decision == "accepted-observed-grid-graph" and float(topology["completeCellDensity"]) >= 0.20:
        return False, "observed graph is already dense enough; grown extent remains diagnostic"
    ratio_i = float(grown_i) / max(1.0, float(span_i))
    ratio_j = float(grown_j) / max(1.0, float(span_j))
    if float(support) < 84.0:
        return False, "grown extent line support is below report-only trust gate"
    if min(span_i, span_j) < 16:
        return False, "observed graph is too small to trust grown extent"
    if max(ratio_i, ratio_j) > 1.45:
        return False, "grown extent expands too far for a single local homography"
    if min(ratio_i, ratio_j) > 1.12:
        return False, "grown extent expands both axes and needs manual confirmation"
    if max(ratio_i, ratio_j) <= 1.05:
        return False, "grown extent does not materially expand the observed graph"
    return True, "report-only trusted modest one-axis line-supported extent growth"


def empty_grown_extent() -> dict[str, Any]:
    return {
        "spanI": None,
        "spanJ": None,
        "lineSupportMeanPct": None,
        "lineSamples": 0,
        "lineWithin0_15Pct": None,
    }


def grown_line_threshold_px(homography: np.ndarray, min_i: int, max_i: int, min_j: int, max_j: int) -> float:
    center_i = (min_i + max_i) / 2.0
    center_j = (min_j + max_j) / 2.0
    samples = np.float32([
        [center_i, center_j],
        [center_i + 1, center_j],
        [center_i, center_j + 1],
    ])
    projected = cv2.perspectiveTransform(samples.reshape(1, -1, 2), homography).reshape(-1, 2)
    cell_px = min(float(np.linalg.norm(projected[1] - projected[0])), float(np.linalg.norm(projected[2] - projected[0])))
    return max(2.5, min(8.0, cell_px * 0.18))


def projected_line_support(line_distance: np.ndarray, homography: np.ndarray, grid_samples: np.ndarray, threshold_px: float) -> float:
    projected = cv2.perspectiveTransform(np.float32(grid_samples).reshape(1, -1, 2), homography).reshape(-1, 2)
    height, width = line_distance.shape[:2]
    valid = (projected[:, 0] >= 0) & (projected[:, 0] < width) & (projected[:, 1] >= 0) & (projected[:, 1] < height)
    if int(valid.sum()) < max(8, len(projected) * 0.25):
        return 0.0
    xs = np.clip(np.rint(projected[valid, 0]).astype(int), 0, width - 1)
    ys = np.clip(np.rint(projected[valid, 1]).astype(int), 0, height - 1)
    return float(np.mean(line_distance[ys, xs] <= threshold_px))


def grow_lower(score_fn: Any, start: int, support_floor: float, limit: int = 80) -> int:
    current = start
    misses = 0
    for index in range(start - 1, start - limit - 1, -1):
        if score_fn(index) >= support_floor:
            current = index
            misses = 0
        else:
            misses += 1
            if misses >= 2:
                break
    return current


def grow_upper(score_fn: Any, start: int, support_floor: float, limit: int = 80) -> int:
    current = start
    misses = 0
    for index in range(start + 1, start + limit + 1):
        if score_fn(index) >= support_floor:
            current = index
            misses = 0
        else:
            misses += 1
            if misses >= 2:
                break
    return current


def line_within_pct(image_to_truth: np.ndarray, image_samples: np.ndarray) -> float:
    truth = cv2.perspectiveTransform(image_samples.reshape(1, -1, 2), image_to_truth).reshape(-1, 2)
    distance = np.minimum(np.abs(truth[:, 0] - np.rint(truth[:, 0])), np.abs(truth[:, 1] - np.rint(truth[:, 1])))
    return round_metric(float(np.mean(distance <= 0.15) * 100.0))


def dot_within_pct(image_to_truth: np.ndarray, points: np.ndarray) -> float:
    truth = cv2.perspectiveTransform(points.reshape(1, -1, 2), image_to_truth).reshape(-1, 2)
    distance = np.sqrt((truth[:, 0] - np.rint(truth[:, 0])) ** 2 + (truth[:, 1] - np.rint(truth[:, 1])) ** 2)
    return round_metric(float(np.mean(distance <= 0.15) * 100.0))


def graph_selection_score(mesh_samples: int, axis_balance: float, conflict_pct: float, topology: dict[str, float | int]) -> float:
    conflict_factor = max(0.0, 1.0 - conflict_pct / 12.0) ** 2
    cell_factor = 0.35 + 0.65 * math.sqrt(float(topology["completeCellDensity"]))
    edge_factor = 0.50 + 0.50 * math.sqrt(float(topology["coordinateEdgeDensity"]))
    node_factor = 0.50 + 0.50 * math.sqrt(float(topology["nodeFill"]))
    balance_factor = axis_balance ** 1.6
    return float(mesh_samples) * balance_factor * conflict_factor * cell_factor * edge_factor * node_factor


def decide_graph(
    assigned_nodes: int,
    mesh_samples: int,
    axis_balance: float,
    conflict_pct: float,
    topology: dict[str, float | int],
) -> tuple[str, list[str]]:
    hard = []
    weak = []
    if assigned_nodes < 20:
        hard.append("too few graph nodes received coordinates")
    if mesh_samples < 160:
        hard.append("too few observed grid-edge samples")
    if axis_balance < 0.12:
        hard.append("selected graph component is too skinny")
    if conflict_pct > 18.0:
        hard.append("too many graph coordinate conflicts")
    if int(topology["completeCells"]) < 8:
        hard.append("too few complete graph cells")
    if axis_balance < 0.45:
        weak.append("selected graph component is narrow")
    if conflict_pct > 12.0:
        weak.append("graph coordinate conflicts are elevated")
    if float(topology["completeCellDensity"]) < 0.10:
        weak.append("selected graph component is sparse")
    if hard:
        return "refuse", hard + weak
    if not weak and assigned_nodes >= 40 and mesh_samples >= 300 and int(topology["completeCells"]) >= 20:
        return "accepted-observed-grid-graph", ["observed grid graph has enough balanced local support"]
    return "candidate-observed-grid-graph", ["requires manual confirmation before projection", *weak]


def select_component_candidate(candidates: list[GraphCandidate]) -> GraphCandidate:
    usable = [candidate for candidate in candidates if candidate.decision != "refuse"]
    if not usable:
        return max(candidates, key=lambda candidate: candidate.graph_score)
    return max(usable, key=lambda candidate: candidate.graph_score)


def select_candidate(candidates: list[GraphCandidate]) -> GraphCandidate:
    accepted = [candidate for candidate in candidates if candidate.decision == "accepted-observed-grid-graph"]
    if accepted:
        return max(accepted, key=lambda candidate: candidate.graph_score)
    candidates_only = [candidate for candidate in candidates if candidate.decision == "candidate-observed-grid-graph"]
    if candidates_only:
        return max(candidates_only, key=lambda candidate: candidate.graph_score)
    return max(candidates, key=lambda candidate: candidate.graph_score)


def write_overlay(ai_grid: Any, label: dict[str, Any], graph: dict[str, Any], candidate: GraphCandidate, overlays_dir: Path) -> Path:
    source_path = ROOT / label["sourceUrl"].removeprefix("/")
    with Image.open(source_path) as image:
        source = ImageOps.exif_transpose(image).convert("RGB")
    height, width = graph["lineMask"].shape[:2]
    source = source.resize((width, height), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(source)
    points = graph["points"]
    for start, end in candidate.component_edge_pairs:
        start_point = points[start]
        end_point = points[end]
        draw.line((float(start_point[0]), float(start_point[1]), float(end_point[0]), float(end_point[1])), fill=(0, 255, 255), width=1)
    for node_id in candidate.component_node_ids:
        x, y = points[node_id]
        draw.ellipse((float(x) - 1.5, float(y) - 1.5, float(x) + 1.5, float(y) + 1.5), fill=(255, 0, 255))
    draw.rectangle((8, 8, 640, 32), fill=(0, 0, 0))
    draw.text((12, 12), f"{candidate.source_id} {candidate.decision} graphScore={candidate.graph_score}", fill=(255, 255, 255))
    path = overlays_dir / f"{slugify(candidate.source_id)}-line-graph-{candidate.setting.threshold}-{candidate.setting.close_kernel}-{candidate.setting.close_iterations}.png"
    source.save(path)
    return path


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    decisions: dict[str, int] = {}
    meshes = []
    selected_lines = []
    trusted_grown_count = 0
    for result in results:
        selected = result["selected"]
        decisions[selected["decision"]] = decisions.get(selected["decision"], 0) + 1
        if selected.get("meshWithin0_15Pct") is not None:
            meshes.append(float(selected["meshWithin0_15Pct"]))
        if selected.get("selectedLineWithin0_15Pct") is not None:
            selected_lines.append(float(selected["selectedLineWithin0_15Pct"]))
        if selected.get("trustedGrownExtent"):
            trusted_grown_count += 1
    return {
        "total": len(results),
        "decisions": decisions,
        "meshMeanWithin0_15Pct": mean_or_none(meshes),
        "meshMinWithin0_15Pct": min(meshes) if meshes else None,
        "reportOnlySelectedLineMeanWithin0_15Pct": mean_or_none(selected_lines),
        "reportOnlySelectedLineMinWithin0_15Pct": min(selected_lines) if selected_lines else None,
        "reportOnlyTrustedGrownExtentCount": trusted_grown_count,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AI Line Graph Lattice Probe",
        "",
        f"- Selection mode: {report['selectionMode']}",
        f"- Decisions: `{json.dumps(report['summary']['decisions'], sort_keys=True)}`",
        f"- Mesh mean/min <=0.15 squares: `{report['summary']['meshMeanWithin0_15Pct']}` / `{report['summary']['meshMinWithin0_15Pct']}`",
        f"- Report-only selected line mean/min <=0.15 squares: `{report['summary']['reportOnlySelectedLineMeanWithin0_15Pct']}` / `{report['summary']['reportOnlySelectedLineMinWithin0_15Pct']}`",
        f"- Report-only trusted grown extents: `{report['summary']['reportOnlyTrustedGrownExtentCount']}`",
        "",
        "| Source | Decision | Setting | Nodes | Edges | Span | Grown Span | Trusted Grown | Cells | Cell Density | Conflicts | Score | Mesh <=.15 | Selected <=.15 | Reasons |",
        "| --- | --- | --- | ---: | ---: | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for result in report["results"]:
        selected = result["selected"]
        setting = selected["setting"]
        lines.append(
            f"| `{result['sourceId']}` | `{selected['decision']}` | `{setting['threshold']}:{setting['closeKernel']}:{setting['closeIterations']}` | "
            f"{selected['assignedNodes']} | {selected['componentEdges']} | {selected['spanI']}x{selected['spanJ']} | "
            f"{selected['grownSpanI']}x{selected['grownSpanJ']} | "
            f"{selected['trustedGrownExtent']} | "
            f"{selected['completeCells']} | {selected['completeCellDensityPct']}% | "
            f"{selected['coordinateConflictPct']}% | {selected['graphScore']} | {selected['meshWithin0_15Pct']} | "
            f"{selected['selectedLineWithin0_15Pct']} | {'; '.join(selected['reasons'])} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_console(report: dict[str, Any]) -> str:
    lines = [f"AI line graph lattice: {json.dumps(report['summary']['decisions'], sort_keys=True)}"]
    for result in report["results"]:
        selected = result["selected"]
        lines.append(
            f"- {result['sourceId']}: {selected['decision']} setting={selected['setting']['threshold']}:{selected['setting']['closeKernel']}:{selected['setting']['closeIterations']} "
            f"nodes={selected['assignedNodes']} span={selected['spanI']}x{selected['spanJ']} grown={selected['grownSpanI']}x{selected['grownSpanJ']} "
            f"trustedGrown={selected['trustedGrownExtent']} "
            f"cells={selected['completeCells']} cellDensity={selected['completeCellDensityPct']}% "
            f"conflicts={selected['coordinateConflictPct']}% mesh<=.15={selected['meshWithin0_15Pct']} selected<=.15={selected['selectedLineWithin0_15Pct']} score={selected['graphScore']}"
        )
    lines.append(f"Artifacts: {report['outDir']}/report.md")
    return "\n".join(lines)


def candidate_to_json(candidate: GraphCandidate) -> dict[str, Any]:
    return {
        "sourceId": candidate.source_id,
        "reportPath": candidate.report_path,
        "setting": setting_to_json(candidate.setting),
        "decision": candidate.decision,
        "reasons": candidate.reasons,
        "nodeCount": candidate.node_count,
        "edgeCount": candidate.edge_count,
        "componentCount": candidate.component_count,
        "componentNodes": candidate.component_nodes,
        "componentEdges": candidate.component_edges,
        "assignedNodes": candidate.assigned_nodes,
        "coordinateConflicts": candidate.coordinate_conflicts,
        "coordinateConflictPct": candidate.coordinate_conflict_pct,
        "spanI": candidate.span_i,
        "spanJ": candidate.span_j,
        "axisBalance": candidate.axis_balance,
        "coordinateEdges": candidate.coordinate_edges,
        "possibleCoordinateEdges": candidate.possible_coordinate_edges,
        "coordinateEdgeDensityPct": candidate.coordinate_edge_density_pct,
        "completeCells": candidate.complete_cells,
        "possibleCells": candidate.possible_cells,
        "completeCellDensityPct": candidate.complete_cell_density_pct,
        "nodeFillPct": candidate.node_fill_pct,
        "grownSpanI": candidate.grown_span_i,
        "grownSpanJ": candidate.grown_span_j,
        "grownLineSupportMeanPct": candidate.grown_line_support_mean_pct,
        "grownLineSamples": candidate.grown_line_samples,
        "grownLineWithin0_15Pct": candidate.grown_line_within_0_15_pct,
        "trustedGrownExtent": candidate.trusted_grown_extent,
        "trustedGrownReason": candidate.trusted_grown_reason,
        "selectedLineWithin0_15Pct": candidate.selected_line_within_0_15_pct,
        "graphScore": candidate.graph_score,
        "meshSamples": candidate.mesh_samples,
        "meshWithin0_15Pct": candidate.mesh_within_0_15_pct,
        "dotWithin0_15Pct": candidate.dot_within_0_15_pct,
        "overlayImage": candidate.overlay_image,
        "labelerSeed": candidate.labeler_seed,
    }


def setting_to_json(setting: GraphSetting) -> dict[str, int]:
    return {
        "threshold": setting.threshold,
        "closeKernel": setting.close_kernel,
        "closeIterations": setting.close_iterations,
    }


def mean_or_none(values: list[float]) -> float | None:
    return None if not values else round_metric(float(sum(values) / len(values)))


def round_metric(value: float) -> float:
    return round(float(value), 3)


def slugify(value: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in value).strip("-").lower()


if __name__ == "__main__":
    main()
