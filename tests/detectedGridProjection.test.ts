import { describe, expect, it } from 'vitest';
import {
  evaluateDetectedGridForAutoAlign,
  fitImageInProjector,
  mapDetectedGridToAnchors,
} from '../src/calibration/detectedGridProjection';
import type { CalibrationAnchor, DetectedGrid } from '../src/calibration/types';

describe('detected grid projection alignment', () => {
  it('fits camera-image coordinates into projector coordinates', () => {
    const fit = fitImageInProjector(1000, 500, { width: 1280, height: 800 });

    expect(fit.x).toBe(0);
    expect(fit.y).toBe(80);
    expect(fit.width).toBe(1280);
    expect(fit.height).toBe(640);
  });

  it('maps detected camera corners onto projector anchors while preserving physical square span', () => {
    const anchors = defaultAnchors();
    const detected: DetectedGrid = {
      sourceName: 'test frame',
      sourceUrl: 'data:test',
      imageWidth: 1000,
      imageHeight: 500,
      corners: [
        { x: 100, y: 50 },
        { x: 900, y: 40 },
        { x: 860, y: 460 },
        { x: 120, y: 450 },
      ],
      columns: 99,
      rows: 40,
      confidence: 0.8,
      families: [
        { angleDegrees: 0, lineCount: 13, score: 100 },
        { angleDegrees: 90, lineCount: 9, score: 80 },
      ],
      detectedAt: '2026-05-27T00:00:00.000Z',
      message: 'detected',
    };

    const mapped = mapDetectedGridToAnchors(detected, anchors, { width: 1280, height: 800 });

    expect(mapped[1].physical).toEqual({ x: 12, y: 0 });
    expect(mapped[2].physical).toEqual({ x: 12, y: 8 });
    expect(mapped[0].projector.x).toBeCloseTo(128);
    expect(mapped[0].projector.y).toBeCloseTo(144);
    expect(mapped[2].projector.x).toBeCloseTo(1100.8);
    expect(mapped[2].projector.y).toBeCloseTo(668.8);
  });

  it('rejects small or out-of-frame detections for automatic projector alignment', () => {
    expect(evaluateDetectedGridForAutoAlign(detectedGrid([
      { x: 100, y: 100 },
      { x: 300, y: 100 },
      { x: 300, y: 700 },
      { x: 100, y: 700 },
    ])).ok).toBe(false);

    const outOfFrame = evaluateDetectedGridForAutoAlign(detectedGrid([
      { x: -40, y: 100 },
      { x: 900, y: 100 },
      { x: 900, y: 700 },
      { x: -40, y: 700 },
    ]));
    expect(outOfFrame.ok).toBe(false);
    expect(outOfFrame.issues.join(' ')).toContain('outside the image');
  });

  it('rejects detected grids that are larger than the current calibration span', () => {
    const quality = evaluateDetectedGridForAutoAlign({
      ...detectedGrid([
        { x: 100, y: 100 },
        { x: 900, y: 100 },
        { x: 900, y: 650 },
        { x: 100, y: 650 },
      ]),
      columns: 28,
      rows: 26,
      confidence: 0.92,
    });

    expect(quality.ok).toBe(false);
    expect(quality.issues.join(' ')).toContain('larger than the current 12 x 8 calibration span');
  });

  it('rejects low-lattice detections even when the outline looks plausible', () => {
    const quality = evaluateDetectedGridForAutoAlign({
      ...detectedGrid([
        { x: 100, y: 100 },
        { x: 900, y: 100 },
        { x: 900, y: 650 },
        { x: 100, y: 650 },
      ]),
      confidence: 0.93,
      latticeScore: 0.1,
    });

    expect(quality.ok).toBe(false);
    expect(quality.issues.join(' ')).toContain('lattice support is below the auto-align threshold');
  });
});

function defaultAnchors(): CalibrationAnchor[] {
  return [
    { id: 'A', physical: { x: 0, y: 0 }, projector: { x: 138, y: 118 } },
    { id: 'B', physical: { x: 12, y: 0 }, projector: { x: 1140, y: 96 } },
    { id: 'C', physical: { x: 12, y: 8 }, projector: { x: 1084, y: 680 } },
    { id: 'D', physical: { x: 0, y: 8 }, projector: { x: 170, y: 706 } },
  ];
}

function detectedGrid(corners: DetectedGrid['corners']): DetectedGrid {
  return {
    sourceName: 'test',
    sourceUrl: 'data:test',
    imageWidth: 1000,
    imageHeight: 800,
    corners,
    columns: 12,
    rows: 8,
    confidence: 0.9,
    latticeScore: 0.9,
    families: [
      { angleDegrees: 0, lineCount: 13, score: 100 },
      { angleDegrees: 90, lineCount: 9, score: 80 },
    ],
    detectedAt: '2026-05-27T00:00:00.000Z',
    message: 'detected',
  };
}
