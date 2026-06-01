#!/usr/bin/env python3
"""Summarize a report-only hybrid of AI dot consensus and AI line-graph evidence.

The branch selector uses only no-label diagnostics from the two upstream
reports. Fixture labels are present in those reports only for benchmark score
fields.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOT_REPORT = ROOT / "test-results" / "ai-dot-lattice-fit-risk-aware-summary-v1" / "report.json"
DEFAULT_LINE_GRAPH_REPORT = ROOT / "test-results" / "ai-line-graph-lattice-v1" / "report.json"
DEFAULT_OUT_DIR = ROOT / "test-results" / "ai-grid-hybrid-summary-v1"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dot-report", default=str(DEFAULT_DOT_REPORT))
    parser.add_argument(
        "--line-graph-report",
        action="append",
        default=None,
        help="Line-graph report path. Repeat to evaluate a no-label prompt ensemble.",
    )
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    args = parser.parse_args()

    dot_report = json.loads(Path(args.dot_report).read_text())
    line_graph_paths = [Path(path) for path in (args.line_graph_report or [str(DEFAULT_LINE_GRAPH_REPORT)])]
    line_graph_reports = [json.loads(path.read_text()) for path in line_graph_paths]
    dot_by_source = {result["sourceId"]: result for result in dot_report.get("results", [])}
    line_by_source = line_candidates_by_source(line_graph_reports)

    results = []
    line_first_results = []
    for source_id in sorted(set(dot_by_source) & set(line_by_source)):
        dot_result = dot_by_source[source_id]
        line_result = select_line_candidate(line_by_source[source_id])
        results.append(select_hybrid(source_id, dot_result, line_result))
        line_first_results.append(select_line_first_speed(source_id, dot_result, line_result))

    out_dir = Path(args.out_dir)
    report = {
        "outDir": str(out_dir),
        "selectionMode": (
            "report-only no-label hybrid: prefer one-line-mask graph geometry, but switch to dot consensus "
            "when no-label diagnostics show a stronger full-span/high-support fit"
        ),
        "inputs": {
            "dotReport": str(Path(args.dot_report)),
            "lineGraphReports": [str(path) for path in line_graph_paths],
        },
        "summary": summarize(results),
        "lineFirstSpeedSummary": summarize_line_first_speed(line_first_results),
        "results": results,
        "lineFirstSpeedResults": line_first_results,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.json").write_text(f"{json.dumps(report, indent=2)}\n")
    (out_dir / "report.md").write_text(render_markdown(report))
    print(render_console(report))


def line_candidates_by_source(line_graph_reports: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    candidates: dict[str, list[dict[str, Any]]] = {}
    for report in line_graph_reports:
        prompt_id = report.get("linePromptId", "unknown-line-prompt")
        report_path = report.get("outDir")
        for result in report.get("results", []):
            selected = dict(result["selected"])
            selected["linePromptId"] = prompt_id
            selected["lineGraphReportOutDir"] = report_path
            candidates.setdefault(result["sourceId"], []).append(selected)
    return candidates


def select_line_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        raise RuntimeError("No line candidates")
    base = candidates[0]
    best = base
    for candidate in candidates[1:]:
        if line_prompt_retry_should_replace(best, candidate):
            best = candidate
    best = dict(best)
    best["linePromptCandidateCount"] = len(candidates)
    best["linePromptCandidates"] = [line_candidate_summary(candidate) for candidate in candidates]
    return best


def line_prompt_retry_should_replace(current: dict[str, Any], candidate: dict[str, Any]) -> bool:
    if candidate.get("decision") == "refuse":
        return False
    if min(int(candidate.get("spanI") or 0), int(candidate.get("spanJ") or 0)) < 12:
        return False
    if int(candidate.get("completeCells") or 0) < 20:
        return False
    if metric(candidate, "coordinateConflictPct", 999.0) > metric(current, "coordinateConflictPct", 999.0) + 0.5:
        return False
    if metric(candidate, "coordinateEdgeDensityPct", 0.0) < metric(current, "coordinateEdgeDensityPct", 0.0) + 5.0:
        return False
    if metric(candidate, "nodeFillPct", 0.0) < metric(current, "nodeFillPct", 0.0) + 7.0:
        return False
    if metric(candidate, "graphScore", 0.0) < metric(current, "graphScore", 0.0) * 0.50:
        return False
    return True


def metric(item: dict[str, Any], key: str, default: float) -> float:
    value = item.get(key)
    return float(default) if value is None else float(value)


def line_candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "linePromptId": candidate.get("linePromptId"),
        "lineGraphReportOutDir": candidate.get("lineGraphReportOutDir"),
        "reportPath": candidate.get("reportPath"),
        "decision": candidate.get("decision"),
        "selectedLineWithin0_15Pct": candidate.get("selectedLineWithin0_15Pct"),
        "graphScore": candidate.get("graphScore"),
        "spanI": candidate.get("spanI"),
        "spanJ": candidate.get("spanJ"),
        "completeCells": candidate.get("completeCells"),
        "coordinateEdgeDensityPct": candidate.get("coordinateEdgeDensityPct"),
        "nodeFillPct": candidate.get("nodeFillPct"),
        "coordinateConflictPct": candidate.get("coordinateConflictPct"),
        "trustedGrownExtent": candidate.get("trustedGrownExtent"),
    }


def select_hybrid(source_id: str, dot: dict[str, Any], line: dict[str, Any]) -> dict[str, Any]:
    dot_projection = dot.get("projectionModelComparison") or {}
    dot_fit = dot.get("fit") or {}
    dot_no_label = (dot_projection.get("noLabelProjectionReadiness") or {}).get("mode")
    dot_visible_mesh = dot_projection.get("visibleMeshLineWithin0_15Pct")
    dot_full_span = dot_projection.get("fullSpanHomographyLineWithin0_15Pct")
    line_score = line.get("selectedLineWithin0_15Pct")
    switch_reason = None

    if dot_no_label == "no-label-full-span-candidate":
        switch_reason = "dot consensus is no-label full-span candidate"
    elif line.get("decision") != "accepted-observed-grid-graph" and not line.get("trustedGrownExtent") and dot_high_support_manual_extent(dot, dot_fit, dot_no_label):
        switch_reason = "line graph is only candidate and dot consensus has high-support manual-extent fit"

    if switch_reason and dot_visible_mesh is not None:
        return {
            "sourceId": source_id,
            "selectedBranch": "dot-consensus",
            "reason": switch_reason,
            "scoreKind": "visible-mesh-line-within-0.15-squares",
            "selectedLineWithin0_15Pct": dot_visible_mesh,
            "lineGraphScorePct": line_score,
            "dotVisibleMeshPct": dot_visible_mesh,
            "dotFullSpanPct": dot_full_span,
            "lineGraphDecision": line.get("decision"),
            "linePromptId": line.get("linePromptId"),
            "lineGraphReportOutDir": line.get("lineGraphReportOutDir"),
            "lineGraphSourceReportPath": line.get("reportPath"),
            "linePromptCandidateCount": line.get("linePromptCandidateCount"),
            "linePromptCandidates": line.get("linePromptCandidates"),
            "lineGraphTrustedGrownExtent": line.get("trustedGrownExtent"),
            "dotNoLabelReadiness": dot_no_label,
            "dotVariantId": dot.get("dotVariantId"),
        }

    return {
        "sourceId": source_id,
        "selectedBranch": "line-graph",
        "reason": "line graph selected-line geometry is preferred by the no-label hybrid gate",
        "scoreKind": "line-graph-selected-line-within-0.15-squares",
        "selectedLineWithin0_15Pct": line_score,
        "lineGraphScorePct": line_score,
        "dotVisibleMeshPct": dot_visible_mesh,
        "dotFullSpanPct": dot_full_span,
        "lineGraphDecision": line.get("decision"),
        "linePromptId": line.get("linePromptId"),
        "lineGraphReportOutDir": line.get("lineGraphReportOutDir"),
        "lineGraphSourceReportPath": line.get("reportPath"),
        "linePromptCandidateCount": line.get("linePromptCandidateCount"),
        "linePromptCandidates": line.get("linePromptCandidates"),
        "lineGraphTrustedGrownExtent": line.get("trustedGrownExtent"),
        "dotNoLabelReadiness": dot_no_label,
        "dotVariantId": dot.get("dotVariantId"),
    }


def select_line_first_speed(source_id: str, dot: dict[str, Any], line: dict[str, Any]) -> dict[str, Any]:
    dot_projection = dot.get("projectionModelComparison") or {}
    dot_fit = dot.get("fit") or {}
    dot_no_label = (dot_projection.get("noLabelProjectionReadiness") or {}).get("mode")
    dot_visible_mesh = dot_projection.get("visibleMeshLineWithin0_15Pct")
    dot_full_span = dot_projection.get("fullSpanHomographyLineWithin0_15Pct")
    line_score = line.get("selectedLineWithin0_15Pct")
    fallback_reason = None

    # This policy models the live-table speed path: run one line mask first and
    # spend dot-consensus calls only when the line graph did not produce a
    # trusted observed-grid seed.
    if line.get("decision") != "accepted-observed-grid-graph" and not line.get("trustedGrownExtent"):
        if dot_high_support_manual_extent(dot, dot_fit, dot_no_label):
            fallback_reason = "line graph is only candidate and dot consensus has high-support manual-extent fit"
        elif dot_no_label == "no-label-full-span-candidate" and dot_visible_mesh is not None:
            fallback_reason = "line graph is only candidate and dot consensus is no-label full-span candidate"

    if fallback_reason and dot_visible_mesh is not None:
        return {
            "sourceId": source_id,
            "selectedBranch": "dot-consensus-fallback",
            "reason": fallback_reason,
            "scoreKind": "visible-mesh-line-within-0.15-squares",
            "selectedLineWithin0_15Pct": dot_visible_mesh,
            "lineGraphScorePct": line_score,
            "dotVisibleMeshPct": dot_visible_mesh,
            "dotFullSpanPct": dot_full_span,
            "lineGraphDecision": line.get("decision"),
            "linePromptId": line.get("linePromptId"),
            "lineGraphReportOutDir": line.get("lineGraphReportOutDir"),
            "lineGraphSourceReportPath": line.get("reportPath"),
            "linePromptCandidateCount": line.get("linePromptCandidateCount"),
            "linePromptCandidates": line.get("linePromptCandidates"),
            "lineGraphTrustedGrownExtent": line.get("trustedGrownExtent"),
            "dotNoLabelReadiness": dot_no_label,
            "dotVariantId": dot.get("dotVariantId"),
        }

    return {
        "sourceId": source_id,
        "selectedBranch": "line-graph-first-pass",
        "reason": "line graph produced an accepted or trusted observed-grid seed, so no dot fallback is modeled",
        "scoreKind": "line-graph-selected-line-within-0.15-squares",
        "selectedLineWithin0_15Pct": line_score,
        "lineGraphScorePct": line_score,
        "dotVisibleMeshPct": dot_visible_mesh,
        "dotFullSpanPct": dot_full_span,
        "lineGraphDecision": line.get("decision"),
        "linePromptId": line.get("linePromptId"),
        "lineGraphReportOutDir": line.get("lineGraphReportOutDir"),
        "lineGraphSourceReportPath": line.get("reportPath"),
        "linePromptCandidateCount": line.get("linePromptCandidateCount"),
        "linePromptCandidates": line.get("linePromptCandidates"),
        "lineGraphTrustedGrownExtent": line.get("trustedGrownExtent"),
        "dotNoLabelReadiness": dot_no_label,
        "dotVariantId": dot.get("dotVariantId"),
    }


def dot_high_support_manual_extent(dot: dict[str, Any], fit: dict[str, Any], dot_no_label: str | None) -> bool:
    if dot.get("decision") != "accepted-visible-lattice-geometry":
        return False
    supported_readiness = dot_no_label in {"no-label-manual-extent-check", "no-label-observed-region-candidate"}
    compact_manual_confirmation = (
        dot_no_label == "no-label-manual-confirmation-required"
        and int(fit.get("homographyInliers") or 0) >= 100
        and min(int(fit.get("spanI") or 0), int(fit.get("spanJ") or 0)) >= 15
        and metric(fit, "homographyInlierRatio", 0.0) >= 0.75
        and metric(fit, "p90ReprojectionErrorCells", 999.0) <= 0.05
        and metric(fit, "p25LineSupport", 0.0) >= 0.95
        and metric(fit, "medianLineSupport", 0.0) >= 0.98
        and metric(fit, "coordinateConflictPct", 999.0) <= 5.0
    )
    if not supported_readiness and not compact_manual_confirmation:
        return False
    return (
        metric(fit, "p25LineSupport", 0.0) >= 0.95
        and metric(fit, "medianLineSupport", 0.0) >= 0.98
        and metric(fit, "coordinateConflictPct", 999.0) <= 8.0
        and metric(fit, "homographyInlierRatio", 0.0) >= 0.55
        and metric(fit, "p90ReprojectionErrorCells", 999.0) <= 0.06
    )


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [float(result["selectedLineWithin0_15Pct"]) for result in results if result.get("selectedLineWithin0_15Pct") is not None]
    branches: dict[str, int] = {}
    for result in results:
        branch = result["selectedBranch"]
        branches[branch] = branches.get(branch, 0) + 1
    return {
        "total": len(results),
        "branches": branches,
        "selectedLineMeanWithin0_15Pct": round_metric(sum(scores) / len(scores)) if scores else None,
        "selectedLineMinWithin0_15Pct": min(scores) if scores else None,
    }


def summarize_line_first_speed(results: list[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize(results)
    fallback_sources = [result["sourceId"] for result in results if result["selectedBranch"] == "dot-consensus-fallback"]
    summary.update(
        {
            "mode": "report-only speed model: one line-mask call for every source, dot consensus only when the line graph is not accepted/trusted",
            "lineMaskCalls": len(results),
            "dotConsensusFallbackSourceCount": len(fallback_sources),
            "dotConsensusFallbackSources": fallback_sources,
            "modeledSourcesAvoidingDotConsensus": len(results) - len(fallback_sources),
        }
    )
    return summary


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AI Grid Hybrid Summary",
        "",
        f"- Selection mode: {report['selectionMode']}",
        f"- Branches: `{json.dumps(report['summary']['branches'], sort_keys=True)}`",
        f"- Selected line mean/min <=0.15 squares: `{report['summary']['selectedLineMeanWithin0_15Pct']}` / `{report['summary']['selectedLineMinWithin0_15Pct']}`",
        "",
        "| Source | Branch | Line Prompt | Selected <=.15 | Line Graph <=.15 | Dot Mesh <=.15 | Dot Full Span <=.15 | Reason |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for result in report["results"]:
        lines.append(
            f"| `{result['sourceId']}` | `{result['selectedBranch']}` | `{result.get('linePromptId')}` | {result['selectedLineWithin0_15Pct']} | "
            f"{result['lineGraphScorePct']} | {result['dotVisibleMeshPct']} | {result['dotFullSpanPct']} | {result['reason']} |"
        )
    speed = report["lineFirstSpeedSummary"]
    lines.extend(
        [
            "",
            "## Line-First Speed Model",
            "",
            f"- Mode: {speed['mode']}",
            f"- Branches: `{json.dumps(speed['branches'], sort_keys=True)}`",
            f"- Selected line mean/min <=0.15 squares: `{speed['selectedLineMeanWithin0_15Pct']}` / `{speed['selectedLineMinWithin0_15Pct']}`",
            f"- Line mask calls: `{speed['lineMaskCalls']}`",
            f"- Dot-consensus fallback sources: `{speed['dotConsensusFallbackSourceCount']}` `{json.dumps(speed['dotConsensusFallbackSources'])}`",
            f"- Modeled sources avoiding dot consensus: `{speed['modeledSourcesAvoidingDotConsensus']}`",
            "",
            "| Source | Branch | Line Prompt | Selected <=.15 | Line Graph <=.15 | Dot Mesh <=.15 | Reason |",
            "| --- | --- | --- | ---: | ---: | ---: | --- |",
        ]
    )
    for result in report["lineFirstSpeedResults"]:
        lines.append(
            f"| `{result['sourceId']}` | `{result['selectedBranch']}` | `{result.get('linePromptId')}` | {result['selectedLineWithin0_15Pct']} | "
            f"{result['lineGraphScorePct']} | {result['dotVisibleMeshPct']} | {result['reason']} |"
        )
    lines.append("")
    lines.append("This is a report-only selector. The gate must be verified on a larger real-photo corpus before runtime promotion.")
    lines.append("")
    return "\n".join(lines)


def render_console(report: dict[str, Any]) -> str:
    speed = report["lineFirstSpeedSummary"]
    lines = [
        f"AI grid hybrid: branches={json.dumps(report['summary']['branches'], sort_keys=True)} "
        f"selected mean/min={report['summary']['selectedLineMeanWithin0_15Pct']}/{report['summary']['selectedLineMinWithin0_15Pct']}",
        f"Line-first speed model: branches={json.dumps(speed['branches'], sort_keys=True)} "
        f"selected mean/min={speed['selectedLineMeanWithin0_15Pct']}/{speed['selectedLineMinWithin0_15Pct']} "
        f"dotFallbacks={speed['dotConsensusFallbackSourceCount']}/{speed['total']}"
    ]
    for result in report["results"]:
        lines.append(
            f"- {result['sourceId']}: {result['selectedBranch']} selected<=.15={result['selectedLineWithin0_15Pct']} "
            f"line={result['lineGraphScorePct']} prompt={result.get('linePromptId')} dotMesh={result['dotVisibleMeshPct']} reason={result['reason']}"
        )
    lines.append(f"Artifacts: {report['outDir']}/report.md")
    return "\n".join(lines)


def round_metric(value: float) -> float:
    return round(float(value), 3)


if __name__ == "__main__":
    main()
