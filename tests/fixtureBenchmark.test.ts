import { describe, expect, it } from 'vitest';
import {
  buildFixtureBenchmarkReport,
  isExtrapolatedFixtureLabel,
  renderFixtureBenchmarkMarkdown,
  scoreFixtureBenchmarkError,
  scoreFixtureDetection,
} from '../src/calibration/fixtureBenchmark';
import type { GridFixtureLabel } from '../src/calibration/fixtureLabels';
import type { DetectedGrid } from '../src/calibration/types';

describe('fixture benchmark scoring', () => {
  it('marks accurate auto-applied detections as accepted', () => {
    const label = fixtureLabel();
    const result = scoreFixtureDetection(label, detectedGrid({
      corners: [
        { x: 102, y: 100 },
        { x: 900, y: 101 },
        { x: 898, y: 700 },
        { x: 100, y: 699 },
      ],
    }));

    expect(result.applicationState).toBe('applied');
    expect(result.outcome).toBe('auto-accepted-accurate');
    expect(result.strictGeometrySuccess).toBe(true);
    expect(result.rowColumnExact).toBe(true);
    expect(result.meanCornerErrorPixels).toBeLessThan(4);
    expect(result.maxCornerErrorSquares).toBeLessThan(0.1);
  });

  it('flags inaccurate auto-applied detections as wrong confident', () => {
    const result = scoreFixtureDetection(fixtureLabel(), detectedGrid({
      corners: [
        { x: 250, y: 240 },
        { x: 900, y: 180 },
        { x: 850, y: 700 },
        { x: 180, y: 640 },
      ],
    }));

    expect(result.applicationState).toBe('applied');
    expect(result.outcome).toBe('wrong-confident');
    expect(result.strictGeometrySuccess).toBe(false);
    expect(result.meanCornerErrorSquares).toBeGreaterThan(1);
  });

  it('keeps rejected but nearby detections as manual correction seeds', () => {
    const result = scoreFixtureDetection(fixtureLabel(), detectedGrid({
      confidence: 0.45,
      latticeScore: 0.1,
      corners: [
        { x: 120, y: 110 },
        { x: 880, y: 110 },
        { x: 880, y: 680 },
        { x: 120, y: 680 },
      ],
    }));

    expect(result.applicationState).toBe('warned');
    expect(result.outcome).toBe('manual-correction-seed');
    expect(result.autoAlignIssues.join(' ')).toContain('confidence');
  });

  it('separates rough correction seeds from plain refusals', () => {
    const result = scoreFixtureDetection(fixtureLabel(), detectedGrid({
      confidence: 0.35,
      latticeScore: 0.1,
      corners: [
        { x: 170, y: 170 },
        { x: 830, y: 170 },
        { x: 830, y: 630 },
        { x: 170, y: 630 },
      ],
    }));

    expect(result.applicationState).toBe('warned');
    expect(result.outcome).toBe('rough-correction-seed');
    expect(result.meanCornerErrorSquares).toBeLessThan(1.5);
  });

  it('records failed detections without corner metrics', () => {
    const result = scoreFixtureDetection(fixtureLabel(), null, 'No reliable grid found.');

    expect(result.applicationState).toBe('failed');
    expect(result.outcome).toBe('safe-refusal');
    expect(result.meanCornerErrorPixels).toBeNull();
    expect(result.errorMessage).toContain('No reliable grid');
  });

  it('keeps benchmark harness errors separate from detector refusals', () => {
    const result = scoreFixtureBenchmarkError(fixtureLabel(), 'Could not load source image.');

    expect(result.applicationState).toBe('failed');
    expect(result.outcome).toBe('benchmark-error');
    expect(result.errorMessage).toContain('source image');
  });

  it('reports extrapolated fixture labels and renders a markdown summary', () => {
    const extrapolated = fixtureLabel({
      corners: [
        { x: -80, y: -60 },
        { x: 900, y: 100 },
        { x: 900, y: 700 },
        { x: 100, y: 700 },
      ],
    });
    const result = scoreFixtureDetection(extrapolated, null, 'missing source');
    const report = buildFixtureBenchmarkReport([result], '2026-05-28T00:00:00.000Z', '2026-05-28T01:00:00.000Z');
    const markdown = renderFixtureBenchmarkMarkdown(report);

    expect(isExtrapolatedFixtureLabel(extrapolated)).toBe(true);
    expect(result.extrapolatedGroundTruth).toBe(true);
    expect(result.truthOffImageCornerCount).toBe(1);
    expect(report.summary.extrapolatedGroundTruth).toBe(1);
    expect(report.summary.roughCorrectionSeed).toBe(0);
    expect(report.summary.strictSalesPhotoSuccess).toBe(0);
    expect(report.summary.salesPhotoFixtures).toBe(1);
    expect(report.candidateSummaries).toHaveLength(1);
    expect(report.candidateSummaries[0].candidateId).toBe('passive-browser-lattice-v1');
    expect(markdown).toContain('## Candidate Summaries');
    expect(markdown).toContain('Strict sales-photo successes');
    expect(markdown).toContain('extrapolated truth');
    expect(markdown).toContain('Strict sales-photo success is 0/1');
  });

  it('keeps generated controls separate from sales-photo strict success', () => {
    const generated = fixtureLabel({
      sourceId: 'generated-test-mat',
      sourceName: 'Generated test mat',
      sourceUrl: 'data:image/svg+xml,test',
    });
    const result = scoreFixtureDetection(generated, detectedGrid());
    const report = buildFixtureBenchmarkReport([result], '2026-05-28T00:00:00.000Z');

    expect(result.fixtureKind).toBe('generated-control');
    expect(result.strictGeometrySuccess).toBe(true);
    expect(report.summary.strictGeneratedControlSuccess).toBe(1);
    expect(report.summary.generatedControlFixtures).toBe(1);
    expect(report.summary.strictSalesPhotoSuccess).toBe(0);
    expect(report.summary.salesPhotoFixtures).toBe(0);
  });
});

function fixtureLabel(overrides: Partial<GridFixtureLabel> = {}): GridFixtureLabel {
  return {
    sourceId: 'fixture',
    sourceName: 'Fixture',
    sourceUrl: 'data:test',
    note: '',
    imageWidth: 1000,
    imageHeight: 800,
    corners: [
      { x: 100, y: 100 },
      { x: 900, y: 100 },
      { x: 900, y: 700 },
      { x: 100, y: 700 },
    ],
    columns: 12,
    rows: 8,
    benchmark: true,
    labeledAt: '2026-05-28T00:00:00.000Z',
    ...overrides,
  };
}

function detectedGrid(overrides: Partial<DetectedGrid> = {}): DetectedGrid {
  return {
    sourceName: 'Fixture',
    sourceUrl: 'data:test',
    imageWidth: 1000,
    imageHeight: 800,
    corners: [
      { x: 100, y: 100 },
      { x: 900, y: 100 },
      { x: 900, y: 700 },
      { x: 100, y: 700 },
    ],
    columns: 12,
    rows: 8,
    confidence: 0.9,
    latticeScore: 0.9,
    families: [
      { angleDegrees: 0, lineCount: 13, score: 100 },
      { angleDegrees: 90, lineCount: 9, score: 80 },
    ],
    detectedAt: '2026-05-28T00:00:00.000Z',
    message: 'detected',
    ...overrides,
  };
}
