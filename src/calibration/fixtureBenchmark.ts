import { evaluateDetectedGridForAutoAlign, meanCornerDelta } from './detectedGridProjection';
import type { GridFixtureLabel } from './fixtureLabels';
import type { DetectedGrid, Point } from './types';

export type FixtureApplicationState = 'applied' | 'warned' | 'failed';

export type FixtureBenchmarkOutcome =
  | 'auto-accepted-accurate'
  | 'manual-correction-seed'
  | 'rough-correction-seed'
  | 'safe-refusal'
  | 'wrong-confident'
  | 'benchmark-error';

export interface FixtureBenchmarkThresholds {
  autoAcceptedMeanCornerErrorSquares: number;
  autoAcceptedMaxCornerErrorSquares: number;
  manualSeedMeanCornerErrorSquares: number;
  manualSeedMaxCornerErrorSquares: number;
  roughSeedMeanCornerErrorSquares: number;
  roughSeedMaxCornerErrorSquares: number;
}

export interface FixtureBenchmarkCandidateRef {
  candidateId: string;
  candidateName: string;
  candidateCategory?: string;
  candidateRuntime?: string;
  usesGroundTruth?: boolean;
}

export interface FixtureBenchmarkResult {
  candidateId: string;
  candidateName: string;
  candidateCategory: string | null;
  candidateRuntime: string | null;
  usesGroundTruth: boolean;
  sourceId: string;
  sourceName: string;
  fixtureKind: 'generated-control' | 'sales-photo';
  benchmark: boolean;
  extrapolatedGroundTruth: boolean;
  truthOffImageCornerCount: number;
  truthSquarePixels: number;
  applicationState: FixtureApplicationState;
  outcome: FixtureBenchmarkOutcome;
  strictGeometrySuccess: boolean;
  rowColumnExact: boolean;
  rowColumnMatch: boolean;
  rowColumnDeltaPct: number | null;
  expectedColumns: number;
  expectedRows: number;
  detectedColumns: number | null;
  detectedRows: number | null;
  meanCornerErrorPixels: number | null;
  maxCornerErrorPixels: number | null;
  meanCornerErrorSquares: number | null;
  maxCornerErrorSquares: number | null;
  confidence: number | null;
  latticeScore: number | null;
  autoAlignIssues: string[];
  detectorMessage: string | null;
  errorMessage: string | null;
  thresholds: FixtureBenchmarkThresholds;
}

export interface FixtureBenchmarkSummary {
  total: number;
  generatedControlFixtures: number;
  salesPhotoFixtures: number;
  strictGeometrySuccess: number;
  strictSalesPhotoSuccess: number;
  strictGeneratedControlSuccess: number;
  autoAcceptedAccurate: number;
  manualCorrectionSeed: number;
  roughCorrectionSeed: number;
  safeRefusal: number;
  wrongConfident: number;
  benchmarkError: number;
  applied: number;
  warned: number;
  failed: number;
  rowColumnExact: number;
  extrapolatedGroundTruth: number;
}

export interface FixtureBenchmarkCandidateSummary extends FixtureBenchmarkSummary {
  candidateId: string;
  candidateName: string;
  candidateCategory: string | null;
  candidateRuntime: string | null;
  usesGroundTruth: boolean;
}

export interface FixtureBenchmarkReport {
  version: 1;
  generatedAt: string;
  labelUpdatedAt: string | null;
  results: FixtureBenchmarkResult[];
  summary: FixtureBenchmarkSummary;
  candidateSummaries: FixtureBenchmarkCandidateSummary[];
  recommendation: string;
}

const DEFAULT_THRESHOLDS: FixtureBenchmarkThresholds = {
  autoAcceptedMeanCornerErrorSquares: 0.25,
  autoAcceptedMaxCornerErrorSquares: 0.5,
  manualSeedMeanCornerErrorSquares: 1,
  manualSeedMaxCornerErrorSquares: 2,
  roughSeedMeanCornerErrorSquares: 1.5,
  roughSeedMaxCornerErrorSquares: 2.5,
};

const DEFAULT_CANDIDATE: FixtureBenchmarkCandidateRef = {
  candidateId: 'passive-browser-lattice-v1',
  candidateName: 'Current Passive Browser Lattice',
  candidateCategory: 'passive',
  candidateRuntime: 'Browser TypeScript/canvas',
  usesGroundTruth: false,
};

export function scoreFixtureDetection(
  label: GridFixtureLabel,
  detected: DetectedGrid | null,
  errorMessage: string | null = null,
  candidate: FixtureBenchmarkCandidateRef = DEFAULT_CANDIDATE,
): FixtureBenchmarkResult {
  const thresholds = DEFAULT_THRESHOLDS;
  const fixtureKind = classifyFixtureKind(label);
  const extrapolatedGroundTruth = isExtrapolatedFixtureLabel(label);
  const truthOffImageCornerCount = countOffImageCorners(label);
  const truthSquarePixels = roundMetric(averageTruthSquarePixels(label));

  if (!detected) {
    return {
      ...candidateResultFields(candidate),
      sourceId: label.sourceId,
      sourceName: label.sourceName,
      fixtureKind,
      benchmark: label.benchmark,
      extrapolatedGroundTruth,
      truthOffImageCornerCount,
      truthSquarePixels,
      applicationState: 'failed',
      outcome: 'safe-refusal',
      strictGeometrySuccess: false,
      rowColumnExact: false,
      rowColumnMatch: false,
      rowColumnDeltaPct: null,
      expectedColumns: label.columns,
      expectedRows: label.rows,
      detectedColumns: null,
      detectedRows: null,
      meanCornerErrorPixels: null,
      maxCornerErrorPixels: null,
      meanCornerErrorSquares: null,
      maxCornerErrorSquares: null,
      confidence: null,
      latticeScore: null,
      autoAlignIssues: [],
      detectorMessage: null,
      errorMessage,
      thresholds,
    };
  }

  const quality = evaluateDetectedGridForAutoAlign(detected);
  const applicationState: FixtureApplicationState = quality.ok ? 'applied' : 'warned';
  const rowColumnExact = detected.columns === label.columns && detected.rows === label.rows;
  const rowColumnDeltaPct = roundMetric(Math.max(
    Math.abs(detected.columns - label.columns) / Math.max(1, label.columns),
    Math.abs(detected.rows - label.rows) / Math.max(1, label.rows),
  ) * 100);
  const meanCornerErrorPixels = roundMetric(meanCornerDelta(detected.corners, label.corners));
  const maxCornerErrorPixels = roundMetric(maxCornerDelta(detected.corners, label.corners));
  const meanCornerErrorSquares = roundMetric(meanCornerErrorPixels / Math.max(1, truthSquarePixels));
  const maxCornerErrorSquares = roundMetric(maxCornerErrorPixels / Math.max(1, truthSquarePixels));
  const accurate = rowColumnExact
    && meanCornerErrorSquares <= thresholds.autoAcceptedMeanCornerErrorSquares
    && maxCornerErrorSquares <= thresholds.autoAcceptedMaxCornerErrorSquares;
  const strictGeometrySuccess = accurate;
  const manualSeed = meanCornerErrorSquares <= thresholds.manualSeedMeanCornerErrorSquares
    && maxCornerErrorSquares <= thresholds.manualSeedMaxCornerErrorSquares;
  const roughSeed = meanCornerErrorSquares <= thresholds.roughSeedMeanCornerErrorSquares
    && maxCornerErrorSquares <= thresholds.roughSeedMaxCornerErrorSquares;

  let outcome: FixtureBenchmarkOutcome;
  if (applicationState === 'applied' && accurate) {
    outcome = 'auto-accepted-accurate';
  } else if (applicationState === 'applied') {
    outcome = 'wrong-confident';
  } else if (manualSeed) {
    outcome = 'manual-correction-seed';
  } else if (roughSeed) {
    outcome = 'rough-correction-seed';
  } else {
    outcome = 'safe-refusal';
  }

  return {
    ...candidateResultFields(candidate),
    sourceId: label.sourceId,
    sourceName: label.sourceName,
    fixtureKind,
    benchmark: label.benchmark,
    extrapolatedGroundTruth,
    truthOffImageCornerCount,
    truthSquarePixels,
    applicationState,
    outcome,
    strictGeometrySuccess,
    rowColumnExact,
    rowColumnMatch: rowColumnExact,
    rowColumnDeltaPct,
    expectedColumns: label.columns,
    expectedRows: label.rows,
    detectedColumns: detected.columns,
    detectedRows: detected.rows,
    meanCornerErrorPixels,
    maxCornerErrorPixels,
    meanCornerErrorSquares,
    maxCornerErrorSquares,
    confidence: roundMetric(detected.confidence),
    latticeScore: detected.latticeScore === undefined ? null : roundMetric(detected.latticeScore),
    autoAlignIssues: quality.issues,
    detectorMessage: detected.message,
    errorMessage,
    thresholds,
  };
}

export function scoreFixtureBenchmarkError(
  label: GridFixtureLabel,
  errorMessage: string,
  candidate: FixtureBenchmarkCandidateRef = DEFAULT_CANDIDATE,
): FixtureBenchmarkResult {
  const extrapolatedGroundTruth = isExtrapolatedFixtureLabel(label);
  return {
    ...candidateResultFields(candidate),
    sourceId: label.sourceId,
    sourceName: label.sourceName,
    fixtureKind: classifyFixtureKind(label),
    benchmark: label.benchmark,
    extrapolatedGroundTruth,
    truthOffImageCornerCount: countOffImageCorners(label),
    truthSquarePixels: roundMetric(averageTruthSquarePixels(label)),
    applicationState: 'failed',
    outcome: 'benchmark-error',
    strictGeometrySuccess: false,
    rowColumnExact: false,
    rowColumnMatch: false,
    rowColumnDeltaPct: null,
    expectedColumns: label.columns,
    expectedRows: label.rows,
    detectedColumns: null,
    detectedRows: null,
    meanCornerErrorPixels: null,
    maxCornerErrorPixels: null,
    meanCornerErrorSquares: null,
    maxCornerErrorSquares: null,
    confidence: null,
    latticeScore: null,
    autoAlignIssues: [],
    detectorMessage: null,
    errorMessage,
    thresholds: DEFAULT_THRESHOLDS,
  };
}

export function buildFixtureBenchmarkReport(
  results: FixtureBenchmarkResult[],
  labelUpdatedAt: string | null,
  generatedAt = new Date().toISOString(),
): FixtureBenchmarkReport {
  const summary = summarizeFixtureBenchmark(results);
  const candidateSummaries = summarizeFixtureBenchmarkByCandidate(results);
  return {
    version: 1,
    generatedAt,
    labelUpdatedAt,
    results,
    summary,
    candidateSummaries,
    recommendation: recommendFixtureBenchmarkNextStep(summary, candidateSummaries),
  };
}

export function summarizeFixtureBenchmark(results: FixtureBenchmarkResult[]): FixtureBenchmarkSummary {
  return {
    total: results.length,
    generatedControlFixtures: results.filter((result) => result.fixtureKind === 'generated-control').length,
    salesPhotoFixtures: results.filter((result) => result.fixtureKind === 'sales-photo').length,
    strictGeometrySuccess: results.filter((result) => result.strictGeometrySuccess).length,
    strictSalesPhotoSuccess: results.filter((result) => (
      result.fixtureKind === 'sales-photo' && result.strictGeometrySuccess
    )).length,
    strictGeneratedControlSuccess: results.filter((result) => (
      result.fixtureKind === 'generated-control' && result.strictGeometrySuccess
    )).length,
    autoAcceptedAccurate: countOutcome(results, 'auto-accepted-accurate'),
    manualCorrectionSeed: countOutcome(results, 'manual-correction-seed'),
    roughCorrectionSeed: countOutcome(results, 'rough-correction-seed'),
    safeRefusal: countOutcome(results, 'safe-refusal'),
    wrongConfident: countOutcome(results, 'wrong-confident'),
    benchmarkError: countOutcome(results, 'benchmark-error'),
    applied: results.filter((result) => result.applicationState === 'applied').length,
    warned: results.filter((result) => result.applicationState === 'warned').length,
    failed: results.filter((result) => result.applicationState === 'failed').length,
    rowColumnExact: results.filter((result) => result.rowColumnExact).length,
    extrapolatedGroundTruth: results.filter((result) => result.extrapolatedGroundTruth).length,
  };
}

export function summarizeFixtureBenchmarkByCandidate(
  results: FixtureBenchmarkResult[],
): FixtureBenchmarkCandidateSummary[] {
  const byCandidate = new Map<string, FixtureBenchmarkResult[]>();
  for (const result of results) {
    byCandidate.set(result.candidateId, [...(byCandidate.get(result.candidateId) ?? []), result]);
  }

  return [...byCandidate.values()].map((candidateResults) => {
    const first = candidateResults[0];
    return {
      candidateId: first.candidateId,
      candidateName: first.candidateName,
      candidateCategory: first.candidateCategory,
      candidateRuntime: first.candidateRuntime,
      usesGroundTruth: first.usesGroundTruth,
      ...summarizeFixtureBenchmark(candidateResults),
    };
  });
}

export function renderFixtureBenchmarkMarkdown(report: FixtureBenchmarkReport): string {
  const lines = [
    '# Fixture Grid Benchmark',
    '',
    `Generated: ${report.generatedAt}`,
    `Labels updated: ${report.labelUpdatedAt ?? 'unknown'}`,
    '',
    '## Summary',
    '',
    `- Total fixtures: ${report.summary.total}`,
    `- Strict sales-photo successes: ${report.summary.strictSalesPhotoSuccess} / ${report.summary.salesPhotoFixtures}`,
    `- Strict generated-control successes: ${report.summary.strictGeneratedControlSuccess} / ${report.summary.generatedControlFixtures}`,
    `- Auto-accepted accurate: ${report.summary.autoAcceptedAccurate}`,
    `- Manual correction seeds: ${report.summary.manualCorrectionSeed}`,
    `- Rough correction seeds: ${report.summary.roughCorrectionSeed}`,
    `- Safe refusals: ${report.summary.safeRefusal}`,
    `- Wrong confident: ${report.summary.wrongConfident}`,
    `- Benchmark errors: ${report.summary.benchmarkError}`,
    `- Application states: ${report.summary.applied} applied, ${report.summary.warned} warned, ${report.summary.failed} failed`,
    `- Extrapolated ground truth fixtures: ${report.summary.extrapolatedGroundTruth}`,
    '',
    '## Candidate Summaries',
    '',
    '| Candidate | Category | Total | Strict sales | Accepted | Seeds | Rough seeds | Refusals | Wrong confident | Errors | Row/column exact | Runtime |',
    '|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|',
  ];

  for (const summary of report.candidateSummaries) {
    lines.push([
      summary.candidateName,
      summary.usesGroundTruth ? `${summary.candidateCategory ?? '-'} control` : summary.candidateCategory ?? '-',
      String(summary.total),
      `${summary.strictSalesPhotoSuccess}/${summary.salesPhotoFixtures}`,
      String(summary.autoAcceptedAccurate),
      String(summary.manualCorrectionSeed),
      String(summary.roughCorrectionSeed),
      String(summary.safeRefusal),
      String(summary.wrongConfident),
      String(summary.benchmarkError),
      String(summary.rowColumnExact),
      summary.candidateRuntime ?? '-',
    ].map(escapeMarkdownTableCell).join(' | ').replace(/^/, '| ').replace(/$/, ' |'));
  }

  lines.push(
    '',
    '## Recommendation',
    '',
    report.recommendation,
    '',
    '## Fixtures',
    '',
    '| Candidate | Fixture | Kind | Strict | Outcome | State | Expected | Detected | Mean sq | Max sq | Mean px | Max px | Confidence | Lattice | Notes |',
    '|---|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|',
  );

  for (const result of report.results) {
    const notes = [
      result.extrapolatedGroundTruth ? 'extrapolated truth' : '',
      result.errorMessage ?? '',
      ...result.autoAlignIssues,
    ].filter(Boolean).join('; ');
    lines.push([
      result.candidateName,
      result.sourceName,
      result.fixtureKind,
      result.strictGeometrySuccess ? 'yes' : 'no',
      result.outcome,
      result.applicationState,
      `${result.expectedColumns}x${result.expectedRows}`,
      result.detectedColumns === null || result.detectedRows === null ? '-' : `${result.detectedColumns}x${result.detectedRows}`,
      formatNullableMetric(result.meanCornerErrorSquares),
      formatNullableMetric(result.maxCornerErrorSquares),
      formatNullableMetric(result.meanCornerErrorPixels),
      formatNullableMetric(result.maxCornerErrorPixels),
      formatNullableMetric(result.confidence),
      formatNullableMetric(result.latticeScore),
      notes || '-',
    ].map(escapeMarkdownTableCell).join(' | ').replace(/^/, '| ').replace(/$/, ' |'));
  }

  lines.push('');
  return `${lines.join('\n')}\n`;
}

export function recommendFixtureBenchmarkNextStep(
  summary: FixtureBenchmarkSummary,
  candidateSummaries: FixtureBenchmarkCandidateSummary[] = [],
): string {
  if (summary.benchmarkError > 0) {
    return 'Fix the benchmark harness or local fixture availability before drawing detector conclusions.';
  }

  if (summary.wrongConfident > 0) {
    return 'Do not tune for more detections yet. Harden auto-apply gates first because at least one fixture would project a wrong result confidently.';
  }

  const comparableSummaries = candidateSummaries.filter((candidate) => !candidate.usesGroundTruth);
  const bestCandidate = comparableSummaries
    .sort((a, b) => candidateUsefulnessScore(b) - candidateUsefulnessScore(a))[0];
  const reference = bestCandidate ?? summary;
  const usefulSeeds = reference.manualCorrectionSeed + reference.roughCorrectionSeed;

  if (reference.strictSalesPhotoSuccess === reference.salesPhotoFixtures && reference.salesPhotoFixtures > 0) {
    return 'The best candidate hit the strict sales-photo gate with zero benchmark errors. Promote it only after browser/manual overlay review confirms the geometry is visually plausible.';
  }

  if (reference.autoAcceptedAccurate <= 1 && usefulSeeds === 0) {
    return `Strict sales-photo success is ${reference.strictSalesPhotoSuccess}/${reference.salesPhotoFixtures}. Treat passive grid detection as a limited helper and continue broader discovery before closing this story.`;
  }

  if (reference.autoAcceptedAccurate <= 1) {
    return `Strict sales-photo success is ${reference.strictSalesPhotoSuccess}/${reference.salesPhotoFixtures}. Some candidates are useful as manual correction seeds, but automatic passive detection is still weak; keep testing stronger passive, assisted, active, or fiducial approaches.`;
  }

  return `Strict sales-photo success is ${reference.strictSalesPhotoSuccess}/${reference.salesPhotoFixtures}. Continue candidate tuning inside this benchmark harness and keep wrong-confident detections at zero before changing projection behavior.`;
}

function candidateUsefulnessScore(summary: FixtureBenchmarkSummary): number {
  return summary.strictSalesPhotoSuccess * 50
    + summary.autoAcceptedAccurate * 10
    + summary.manualCorrectionSeed * 5
    + summary.roughCorrectionSeed * 2
    - summary.wrongConfident * 20
    - summary.benchmarkError * 20;
}

function candidateResultFields(candidate: FixtureBenchmarkCandidateRef): Pick<
  FixtureBenchmarkResult,
  'candidateId' | 'candidateName' | 'candidateCategory' | 'candidateRuntime' | 'usesGroundTruth'
> {
  return {
    candidateId: candidate.candidateId,
    candidateName: candidate.candidateName,
    candidateCategory: candidate.candidateCategory ?? null,
    candidateRuntime: candidate.candidateRuntime ?? null,
    usesGroundTruth: candidate.usesGroundTruth === true,
  };
}

function classifyFixtureKind(label: GridFixtureLabel): FixtureBenchmarkResult['fixtureKind'] {
  if (label.sourceUrl.startsWith('data:image/') || label.sourceId.startsWith('generated-')) {
    return 'generated-control';
  }
  return 'sales-photo';
}

export function isExtrapolatedFixtureLabel(label: GridFixtureLabel): boolean {
  return countOffImageCorners(label) > 0;
}

function countOffImageCorners(label: GridFixtureLabel): number {
  return label.corners.filter((corner) => (
    corner.x < 0
    || corner.y < 0
    || corner.x > label.imageWidth
    || corner.y > label.imageHeight
  )).length;
}

function averageTruthSquarePixels(label: GridFixtureLabel): number {
  const [topLeft, topRight, bottomRight, bottomLeft] = label.corners;
  const horizontalSquare = (
    Math.hypot(topRight.x - topLeft.x, topRight.y - topLeft.y)
    + Math.hypot(bottomRight.x - bottomLeft.x, bottomRight.y - bottomLeft.y)
  ) / Math.max(1, label.columns * 2);
  const verticalSquare = (
    Math.hypot(bottomLeft.x - topLeft.x, bottomLeft.y - topLeft.y)
    + Math.hypot(bottomRight.x - topRight.x, bottomRight.y - topRight.y)
  ) / Math.max(1, label.rows * 2);
  return (horizontalSquare + verticalSquare) / 2;
}

function countOutcome(results: FixtureBenchmarkResult[], outcome: FixtureBenchmarkOutcome): number {
  return results.filter((result) => result.outcome === outcome).length;
}

function maxCornerDelta(a: Point[], b: Point[]): number {
  const pairs = Math.min(a.length, b.length);
  if (pairs === 0) return 0;
  return Math.max(...a.slice(0, pairs).map((point, index) => (
    Math.hypot(point.x - b[index].x, point.y - b[index].y)
  )));
}

function roundMetric(value: number): number {
  return Math.round(value * 100) / 100;
}

function formatNullableMetric(value: number | null): string {
  return value === null ? '-' : String(value);
}

function escapeMarkdownTableCell(value: string): string {
  return value.replace(/\|/g, '\\|');
}
