#!/usr/bin/env python3
"""Fit visible lattice geometry from AI-generated dots without a line mask.

This is an ablation probe. It intentionally gives the deterministic fitter a
synthetic all-foreground line mask so dot geometry is tested without independent
AI gridline validation. Labels are used only for benchmark scoring.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
AI_GRID_PATH = ROOT / "scripts" / "ai-grid-experiment.py"
AI_ARBITER_PATH = ROOT / "scripts" / "ai-evidence-arbiter.py"
AI_DOT_FIT_PATH = ROOT / "scripts" / "ai-dot-lattice-fit.py"
LABELS_PATH = ROOT / "input" / "map-grid-labels.json"
DEFAULT_OUT_DIR = ROOT / "test-results" / "ai-dot-only-lattice-probe-v1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dot-reports-glob",
        action="append",
        default=["test-results/ai-grid-parallel-current/*/*/*/dot-*/report.json"],
    )
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    ai_grid = load_module("ai_grid_experiment", AI_GRID_PATH)
    ai_arbiter = load_module("ai_evidence_arbiter", AI_ARBITER_PATH)
    dot_fit = load_module("ai_dot_lattice_fit", AI_DOT_FIT_PATH)
    labels = {label["sourceId"]: label for label in json.loads(LABELS_PATH.read_text())["labels"]}
    dot_reports = load_report_groups(args.dot_reports_glob)

    out_dir = Path(args.out_dir)
    overlays_dir = out_dir / "overlays"
    overlays_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for source_id in sorted(dot_reports):
        label = labels.get(source_id)
        if not label:
            continue
        variants = [
            analyze_variant(ai_grid, ai_arbiter, dot_fit, source_id, label, dot_report, overlays_dir, index)
            for index, dot_report in enumerate(dot_reports[source_id], start=1)
        ]
        selected = dot_fit.select_best_variant(variants, policy="guarded-risk-aware")
        selected = dict(selected)
        selected["dotVariantCount"] = len(variants)
        selected["dotVariants"] = [variant_summary(dot_fit, variant) for variant in sorted(variants, key=lambda item: item["selectionScore"], reverse=True)]
        results.append(selected)

    report = {
        "outDir": str(out_dir),
        "selectionMode": "dot-only ablation; synthetic all-foreground line mask, no independent line validation",
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


def load_report_groups(patterns: list[str]) -> dict[str, list[dict[str, Any]]]:
    reports: dict[str, list[dict[str, Any]]] = defaultdict(list)
    seen: set[Path] = set()
    for pattern in patterns:
        for path in sorted(ROOT.glob(pattern)):
            if path in seen:
                continue
            seen.add(path)
            report = json.loads(path.read_text())
            report["_reportPath"] = str(path)
            reports[report["sourceId"]].append(report)
    return reports


def analyze_variant(
    ai_grid: Any,
    ai_arbiter: Any,
    dot_fit: Any,
    source_id: str,
    label: dict[str, Any],
    dot_report: dict[str, Any],
    overlays_dir: Path,
    variant_index: int,
) -> dict[str, Any]:
    dot_experiment = first_image_result(dot_report)
    dot_path = resolve_output_path(dot_experiment["outputImage"])
    dot_rgb = load_rgb(dot_path)
    dot_mask = ai_grid.extract_signal_mask(dot_rgb, "white_mask")
    dots = ai_arbiter.extract_dots(dot_mask)
    points = np.float32([[dot.x, dot.y] for dot in dots])
    synthetic_line_mask = np.full(dot_mask.shape, 255, dtype=np.uint8)
    line_context = {
        "lineDistance": np.zeros(dot_mask.shape, dtype=np.float32),
        "lineMaskDilated": synthetic_line_mask,
        "lineAxisAngles": [],
    }
    fit = dot_fit.fit_visible_lattice(points, synthetic_line_mask, line_context=line_context)
    benchmark = dot_fit.benchmark_fit(ai_grid, label, fit, points, synthetic_line_mask)
    selection_score = dot_fit.selection_score_for_fit(fit.metrics, fit.decision)
    overlay_path = dot_fit.write_overlay(ai_grid, label, source_id, points, synthetic_line_mask, fit, overlays_dir, variant_index=variant_index)
    observed_mesh = dot_fit.observed_mesh_geometry(points, fit)
    return {
        "sourceId": source_id,
        "dotVariantId": f"dot-v{variant_index:02d}",
        "dotReportPath": dot_report.get("_reportPath"),
        "dotElapsedMs": dot_experiment.get("elapsedMs"),
        "selectionScore": round_metric(selection_score),
        "decision": fit.decision,
        "reasons": fit.reasons,
        "dotImage": str(dot_path),
        "overlayImage": str(overlay_path),
        "fit": fit.metrics,
        "observedMesh": observed_mesh,
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


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    decisions: dict[str, int] = {}
    for result in results:
        decisions[result["decision"]] = decisions.get(result["decision"], 0) + 1
    scored = [result["benchmark"] for result in results if result["benchmark"].get("truthScored")]
    return {
        "total": len(results),
        "decisions": decisions,
        "acceptedVisibleGeometry": decisions.get("accepted-visible-lattice-geometry", 0),
        "candidateVisibleGeometry": decisions.get("candidate-visible-lattice-geometry", 0),
        "acceptedOrCandidateVisibleGeometry": decisions.get("accepted-visible-lattice-geometry", 0)
        + decisions.get("candidate-visible-lattice-geometry", 0),
        "meanTruthLineSamplesWithin0_15SquaresPct": None
        if not scored
        else round_metric(sum(item.get("truthLineSamplesWithin0_15SquaresPct", 0.0) for item in scored) / len(scored)),
        "meanTruthMeshSamplesWithin0_15SquaresPct": None
        if not scored
        else round_metric(sum(item.get("truthMeshSamplesWithin0_15SquaresPct", 0.0) for item in scored) / len(scored)),
    }


def variant_summary(dot_fit: Any, variant: dict[str, Any]) -> dict[str, Any]:
    fit = variant["fit"]
    bench = variant["benchmark"]
    return {
        "dotVariantId": variant["dotVariantId"],
        "decision": variant["decision"],
        "selectionScore": variant["selectionScore"],
        "spanI": fit.get("spanI"),
        "spanJ": fit.get("spanJ"),
        "homographyInliers": fit.get("homographyInliers"),
        "homographyInlierRatio": fit.get("homographyInlierRatio"),
        "p90ReprojectionErrorCells": fit.get("p90ReprojectionErrorCells"),
        "coordinateConflictPct": fit.get("coordinateConflictPct"),
        "earlyReturnSafety": dot_fit.early_return_safety(variant),
        "truthLineSamplesWithin0_15SquaresPct": bench.get("truthLineSamplesWithin0_15SquaresPct"),
        "truthMeshSamplesWithin0_15SquaresPct": bench.get("truthMeshSamplesWithin0_15SquaresPct"),
        "overlayImage": variant["overlayImage"],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AI Dot-Only Lattice Probe",
        "",
        f"- Selection mode: {report['selectionMode']}",
        f"- Total: `{report['summary']['total']}`",
        f"- Decisions: `{json.dumps(report['summary']['decisions'], sort_keys=True)}`",
        "",
        "| Source | Decision | Variant | Span | Inliers | Homography line <=.15 | Mesh line <=.15 | Reasons | Overlay |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for result in report["results"]:
        fit = result["fit"]
        bench = result["benchmark"]
        lines.append(
            f"| `{result['sourceId']}` | `{result['decision']}` | `{result['dotVariantId']}` | "
            f"{fit.get('spanI')}x{fit.get('spanJ')} | {fit.get('homographyInliers')} | "
            f"{bench.get('truthLineSamplesWithin0_15SquaresPct')} | {bench.get('truthMeshSamplesWithin0_15SquaresPct')} | "
            f"{'; '.join(result['reasons'])} | `{result['overlayImage']}` |"
        )
    lines.append("")
    return "\n".join(lines)


def render_console(report: dict[str, Any]) -> str:
    lines = [f"AI dot-only lattice probe: {json.dumps(report['summary']['decisions'], sort_keys=True)}"]
    for result in report["results"]:
        fit = result["fit"]
        bench = result["benchmark"]
        lines.append(
            f"- {result['sourceId']}: {result['decision']} selected={result['dotVariantId']} "
            f"span={fit.get('spanI')}x{fit.get('spanJ')} inliers={fit.get('homographyInliers')} "
            f"truthLine<=.15={bench.get('truthLineSamplesWithin0_15SquaresPct')} "
            f"truthMesh<=.15={bench.get('truthMeshSamplesWithin0_15SquaresPct')}"
        )
    lines.append(f"Artifacts: {report['outDir']}/report.md")
    return "\n".join(lines)


def round_metric(value: float) -> float:
    return round(float(value), 3)


if __name__ == "__main__":
    main()
