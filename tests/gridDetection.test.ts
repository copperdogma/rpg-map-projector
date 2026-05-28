import { describe, expect, it } from 'vitest';
import { detectGridFromRaster } from '../src/calibration/gridDetection';

describe('grid detection', () => {
  it('detects a clean orthogonal battle-mat grid from pixels', () => {
    const raster = syntheticGridRaster(520, 360, 60);
    const detected = detectGridFromRaster(raster);

    expect(detected).not.toBeNull();
    expect(detected?.confidence).toBeGreaterThan(0.45);
    expect(detected?.columns).toBeGreaterThanOrEqual(4);
    expect(detected?.rows).toBeGreaterThanOrEqual(4);
  });

  it('keeps the detected corners close to a known axis-aligned grid', () => {
    const raster = syntheticOffsetGridRaster();
    const detected = detectGridFromRaster(raster);

    expect(detected).not.toBeNull();
    expect(detected?.columns).toBe(6);
    expect(detected?.rows).toBe(4);
    expect(meanCornerError(detected?.corners ?? [], [
      { x: 80, y: 60 },
      { x: 440, y: 60 },
      { x: 440, y: 300 },
      { x: 80, y: 300 },
    ])).toBeLessThan(3);
  });

  it('keeps the outer bounds when some axis-aligned grid lines are occluded', () => {
    const raster = syntheticOccludedGridRaster();
    const detected = detectGridFromRaster(raster);

    expect(detected).not.toBeNull();
    expect(detected?.message).toContain('axis-aligned grid');
    expect(detected?.columns).toBeGreaterThanOrEqual(12);
    expect(detected?.rows).toBeGreaterThanOrEqual(8);
    expect(meanCornerError(detected?.corners ?? [], [
      { x: 60, y: 50 },
      { x: 660, y: 50 },
      { x: 660, y: 410 },
      { x: 60, y: 410 },
    ])).toBeLessThan(10);
  });
});

function syntheticGridRaster(width: number, height: number, step: number): {
  width: number;
  height: number;
  data: Uint8ClampedArray;
} {
  const data = new Uint8ClampedArray(width * height * 4);

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = (y * width + x) * 4;
      const onGrid = x % step <= 1 || y % step <= 1;
      const value = onGrid ? 80 : 236;
      data[index] = value;
      data[index + 1] = value;
      data[index + 2] = value;
      data[index + 3] = 255;
    }
  }

  return { width, height, data };
}

function syntheticOffsetGridRaster(): {
  width: number;
  height: number;
  data: Uint8ClampedArray;
} {
  const width = 520;
  const height = 360;
  const data = new Uint8ClampedArray(width * height * 4);

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = (y * width + x) * 4;
      const inBounds = x >= 80 && x <= 440 && y >= 60 && y <= 300;
      const onVertical = inBounds && Math.abs(((x - 80) % 60)) <= 1;
      const onHorizontal = inBounds && Math.abs(((y - 60) % 60)) <= 1;
      const onBorder = inBounds && (Math.abs(x - 80) <= 1 || Math.abs(x - 440) <= 1 || Math.abs(y - 60) <= 1 || Math.abs(y - 300) <= 1);
      const value = onVertical || onHorizontal || onBorder ? 80 : 236;
      data[index] = value;
      data[index + 1] = value;
      data[index + 2] = value;
      data[index + 3] = 255;
    }
  }

  return { width, height, data };
}

function syntheticOccludedGridRaster(): {
  width: number;
  height: number;
  data: Uint8ClampedArray;
} {
  const width = 720;
  const height = 520;
  const data = new Uint8ClampedArray(width * height * 4);

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = (y * width + x) * 4;
      const inBounds = x >= 60 && x <= 660 && y >= 50 && y <= 410;
      const onVertical = inBounds && Math.abs(((x - 60) % 40)) <= 1;
      const onHorizontal = inBounds && Math.abs(((y - 50) % 40)) <= 1;
      const onBorder = inBounds && (Math.abs(x - 60) <= 1 || Math.abs(x - 660) <= 1 || Math.abs(y - 50) <= 1 || Math.abs(y - 410) <= 1);
      const occluded = (x >= 90 && x <= 210 && y >= 20 && y <= 210)
        || (x >= 430 && x <= 620 && y >= 285 && y <= 380);
      const value = occluded ? 205 : onVertical || onHorizontal || onBorder ? 92 : inBounds ? 238 : 252;
      data[index] = value;
      data[index + 1] = value;
      data[index + 2] = value;
      data[index + 3] = 255;
    }
  }

  return { width, height, data };
}

function meanCornerError(actual: Array<{ x: number; y: number }>, expected: Array<{ x: number; y: number }>): number {
  return actual.reduce((sum, point, index) => (
    sum + Math.hypot(point.x - expected[index].x, point.y - expected[index].y)
  ), 0) / expected.length;
}
