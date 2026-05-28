import { describe, expect, it } from 'vitest';
import { applyHomography, solveHomography } from '../src/calibration/homography';
import { defaultState, nudgeAnchors, rotateAnchors, scaleAnchors } from '../src/calibration/state';
import type { Point } from '../src/calibration/types';

describe('homography', () => {
  it('maps all four calibration anchors exactly', () => {
    const from = defaultState.anchors.map((anchor) => anchor.physical);
    const to = defaultState.anchors.map((anchor) => anchor.projector);
    const matrix = solveHomography(from, to);

    from.forEach((point, index) => {
      expectPointClose(applyHomography(matrix, point), to[index]);
    });
  });

  it('maps a rectangle into a perspective quadrilateral', () => {
    const from = [
      { x: 0, y: 0 },
      { x: 10, y: 0 },
      { x: 10, y: 6 },
      { x: 0, y: 6 },
    ];
    const to = [
      { x: 120, y: 90 },
      { x: 900, y: 120 },
      { x: 840, y: 520 },
      { x: 160, y: 560 },
    ];

    const matrix = solveHomography(from, to);

    expectPointClose(applyHomography(matrix, { x: 10, y: 6 }), { x: 840, y: 520 });
    const center = applyHomography(matrix, { x: 5, y: 3 });
    expect(center.x).toBeGreaterThan(430);
    expect(center.x).toBeLessThan(560);
    expect(center.y).toBeGreaterThan(270);
    expect(center.y).toBeLessThan(360);
  });

  it('rejects degenerate point pairs', () => {
    const from = [
      { x: 0, y: 0 },
      { x: 0, y: 0 },
      { x: 0, y: 0 },
      { x: 0, y: 0 },
    ];
    const to = [
      { x: 1, y: 1 },
      { x: 2, y: 1 },
      { x: 2, y: 2 },
      { x: 1, y: 2 },
    ];

    expect(() => solveHomography(from, to)).toThrow(/degenerate/);
  });
});

describe('manual projector controls', () => {
  it('nudges all anchors by the requested pixel delta', () => {
    const moved = nudgeAnchors(defaultState.anchors, 8, -4);

    moved.forEach((anchor, index) => {
      expect(anchor.projector.x).toBe(defaultState.anchors[index].projector.x + 8);
      expect(anchor.projector.y).toBe(defaultState.anchors[index].projector.y - 4);
    });
  });

  it('scales and rotates anchors without changing physical coordinates', () => {
    const scaled = scaleAnchors(defaultState.anchors, 1.02);
    const rotated = rotateAnchors(scaled, 0.5);

    rotated.forEach((anchor, index) => {
      expect(anchor.physical).toEqual(defaultState.anchors[index].physical);
    });
  });
});

function expectPointClose(actual: Point, expected: Point): void {
  expect(actual.x).toBeCloseTo(expected.x, 6);
  expect(actual.y).toBeCloseTo(expected.y, 6);
}
