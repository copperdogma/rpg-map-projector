import { applyHomography, solveHomography } from './homography';
import type { DetectedGrid, GridDetectionFamily, Point } from './types';

interface Raster {
  width: number;
  height: number;
  data: Uint8ClampedArray;
}

interface HoughLine {
  theta: number;
  thetaDegrees: number;
  rho: number;
  score: number;
}

interface LineFamily {
  theta: number;
  thetaDegrees: number;
  lines: HoughLine[];
  score: number;
}

interface RegularLineFamily extends LineFamily {
  runLines: HoughLine[];
  regularity: number;
  step: number;
  regularScore: number;
}

interface AxisLineRun {
  positions: number[];
  step: number;
  regularity: number;
}

interface BoundaryGridFit {
  kind: string;
  x0: number;
  x1: number;
  y0: number;
  y1: number;
  columns: number;
  rows: number;
  score: number;
}

const THETA_STEP_DEGREES = 2;
const RHO_STEP = 3;
const MAX_ANALYSIS_SIZE = 720;
const DEFAULT_HOUGH_PEAK_RATIO = 0.18;
const FALLBACK_HOUGH_PEAK_RATIO = 0.12;
const MAX_HOUGH_PEAKS = 320;
const MIN_AXIS_PREVIEW_LATTICE_SUPPORT = 0.05;
const MIN_HOUGH_PREVIEW_LATTICE_SUPPORT = 0.08;

export async function detectGridFromImage(
  image: HTMLImageElement,
  sourceName: string,
  sourceUrl: string,
): Promise<DetectedGrid> {
  const { raster, scale } = rasterizeImage(image);
  const result = detectGridFromRaster(raster);
  if (!result) {
    throw new Error('No reliable grid found. Try a straighter crop or use manual corner correction.');
  }

  return {
    sourceName,
    sourceUrl,
    imageWidth: image.naturalWidth,
    imageHeight: image.naturalHeight,
    corners: result.corners.map((point) => ({
      x: point.x / scale,
      y: point.y / scale,
    })) as [Point, Point, Point, Point],
    columns: result.columns,
    rows: result.rows,
    confidence: result.confidence,
    latticeScore: result.latticeScore,
    families: result.families,
    detectedAt: new Date().toISOString(),
    message: result.message,
  };
}

export async function detectAggressiveHoughGridFromImage(
  image: HTMLImageElement,
  sourceName: string,
  sourceUrl: string,
): Promise<DetectedGrid> {
  const { raster, scale } = rasterizeImage(image);
  const result = detectAggressiveHoughGridFromRaster(raster);
  if (!result) {
    throw new Error('No aggressive Hough grid candidate found.');
  }

  return {
    sourceName,
    sourceUrl,
    imageWidth: image.naturalWidth,
    imageHeight: image.naturalHeight,
    corners: result.corners.map((point) => ({
      x: point.x / scale,
      y: point.y / scale,
    })) as [Point, Point, Point, Point],
    columns: result.columns,
    rows: result.rows,
    confidence: result.confidence,
    latticeScore: result.latticeScore,
    families: result.families,
    detectedAt: new Date().toISOString(),
    message: result.message,
  };
}

export async function detectLooseAxisAlignedGridFromImage(
  image: HTMLImageElement,
  sourceName: string,
  sourceUrl: string,
): Promise<DetectedGrid> {
  const { raster, scale } = rasterizeImage(image);
  const result = detectLooseAxisAlignedGridFromRaster(raster);
  if (!result) {
    throw new Error('No loose axis-aligned grid candidate found.');
  }

  return {
    sourceName,
    sourceUrl,
    imageWidth: image.naturalWidth,
    imageHeight: image.naturalHeight,
    corners: result.corners.map((point) => ({
      x: point.x / scale,
      y: point.y / scale,
    })) as [Point, Point, Point, Point],
    columns: result.columns,
    rows: result.rows,
    confidence: result.confidence,
    latticeScore: result.latticeScore,
    families: result.families,
    detectedAt: new Date().toISOString(),
    message: result.message,
  };
}

export async function detectColorRegionBoundarySeedFromImage(
  image: HTMLImageElement,
  sourceName: string,
  sourceUrl: string,
): Promise<DetectedGrid> {
  const { raster, scale } = rasterizeImage(image);
  const result = detectColorRegionBoundarySeedFromRaster(raster);
  if (!result) {
    throw new Error('No mat-like color region boundary seed found.');
  }

  return {
    sourceName,
    sourceUrl,
    imageWidth: image.naturalWidth,
    imageHeight: image.naturalHeight,
    corners: result.corners.map((point) => ({
      x: point.x / scale,
      y: point.y / scale,
    })) as [Point, Point, Point, Point],
    columns: result.columns,
    rows: result.rows,
    confidence: result.confidence,
    latticeScore: result.latticeScore,
    families: result.families,
    detectedAt: new Date().toISOString(),
    message: result.message,
  };
}

export async function detectBoundaryFirstGridFitFromImage(
  image: HTMLImageElement,
  sourceName: string,
  sourceUrl: string,
): Promise<DetectedGrid> {
  const { raster, scale } = rasterizeImage(image);
  const result = detectBoundaryFirstGridFitFromRaster(raster);
  if (!result) {
    throw new Error('No boundary-first rectified grid fit found.');
  }

  return {
    sourceName,
    sourceUrl,
    imageWidth: image.naturalWidth,
    imageHeight: image.naturalHeight,
    corners: result.corners.map((point) => ({
      x: point.x / scale,
      y: point.y / scale,
    })) as [Point, Point, Point, Point],
    columns: result.columns,
    rows: result.rows,
    confidence: result.confidence,
    latticeScore: result.latticeScore,
    families: result.families,
    detectedAt: new Date().toISOString(),
    message: result.message,
  };
}

export function detectGridFromRaster(raster: Raster): {
  corners: [Point, Point, Point, Point];
  columns: number;
  rows: number;
  confidence: number;
  latticeScore: number;
  families: [GridDetectionFamily, GridDetectionFamily];
  message: string;
} | null {
  const axisAligned = detectAxisAlignedGridFromRaster(raster);
  if (axisAligned && shouldUseAxisAlignedCandidate(axisAligned)) return axisAligned;

  const brightOnDark = detectProjectedGridFromDarkRaster(raster);
  if (brightOnDark) return brightOnDark;

  const edges = collectEdges(raster);
  if (edges.length < 200) return null;

  const hough = buildHough(edges, raster.width, raster.height);
  const primary = detectGridFromHough(raster, edges, hough, DEFAULT_HOUGH_PEAK_RATIO, 0.32);
  if (primary && primary.columns >= 4 && primary.rows >= 4) return primary;

  return detectGridFromHough(raster, edges, hough, FALLBACK_HOUGH_PEAK_RATIO, 0.2) ?? primary;
}

export function detectAggressiveHoughGridFromRaster(raster: Raster): {
  corners: [Point, Point, Point, Point];
  columns: number;
  rows: number;
  confidence: number;
  latticeScore: number;
  families: [GridDetectionFamily, GridDetectionFamily];
  message: string;
} | null {
  const edges = collectEdges(raster);
  if (edges.length < 160) return null;

  const hough = buildHough(edges, raster.width, raster.height);
  const attempts = [
    detectGridFromHough(raster, edges, hough, 0.1, 0.18, {
      allowOutOfFrameCorners: true,
      minLatticeScore: 0.03,
      label: 'Aggressive Hough',
    }),
    detectGridFromHough(raster, edges, hough, 0.075, 0.12, {
      allowOutOfFrameCorners: true,
      minLatticeScore: 0.02,
      label: 'Aggressive Hough',
    }),
    detectGridFromHough(raster, edges, hough, 0.055, 0.08, {
      allowOutOfFrameCorners: true,
      minLatticeScore: 0.01,
      label: 'Aggressive Hough',
    }),
  ].filter((candidate): candidate is NonNullable<typeof candidate> => Boolean(candidate));

  if (attempts.length === 0) return null;
  const best = attempts.sort((a, b) => scoreAggressiveCandidate(b) - scoreAggressiveCandidate(a))[0];
  return {
    ...best,
    confidence: Math.min(0.49, best.confidence),
    message: `${best.message} Kept candidate-only for discovery because this aggressive mode permits weak/out-of-frame geometry.`,
  };
}

export function detectLooseAxisAlignedGridFromRaster(raster: Raster): {
  corners: [Point, Point, Point, Point];
  columns: number;
  rows: number;
  confidence: number;
  latticeScore: number;
  families: [GridDetectionFamily, GridDetectionFamily];
  message: string;
} | null {
  const gray = grayscale(raster);
  const { columnScores, rowScores } = thinLineScores(gray, raster.width, raster.height);
  const vertical = chooseBestLooseAxisRun(columnScores, raster.width);
  const horizontal = chooseBestLooseAxisRun(rowScores, raster.height);
  if (!vertical || !horizontal) return null;

  const minX = vertical.positions[0];
  const maxX = vertical.positions[vertical.positions.length - 1];
  const minY = horizontal.positions[0];
  const maxY = horizontal.positions[horizontal.positions.length - 1];
  const columns = Math.max(2, vertical.positions.length - 1);
  const rows = Math.max(2, horizontal.positions.length - 1);
  const corners: [Point, Point, Point, Point] = [
    { x: minX, y: minY },
    { x: maxX, y: minY },
    { x: maxX, y: maxY },
    { x: minX, y: maxY },
  ];
  const latticeScore = scoreLatticeSupport(raster, corners, columns, rows);
  if (latticeScore < 0.04) return null;

  const coverage = Math.min((maxX - minX) / raster.width, (maxY - minY) / raster.height);
  const confidence = Math.round(Math.min(
    0.49,
    vertical.regularity * 0.25 + horizontal.regularity * 0.25 + coverage * 0.16 + Math.min(1, latticeScore) * 0.25,
  ) * 100) / 100;

  return {
    corners,
    columns,
    rows,
    confidence,
    latticeScore,
    families: [
      { angleDegrees: 90, lineCount: vertical.positions.length, score: Math.round(vertical.regularity * 1000) },
      { angleDegrees: 0, lineCount: horizontal.positions.length, score: Math.round(horizontal.regularity * 1000) },
    ],
    message: `Loose axis-aligned candidate found ${columns} x ${rows} grid from low-threshold line spacing.`,
  };
}

export function detectColorRegionBoundarySeedFromRaster(raster: Raster): {
  corners: [Point, Point, Point, Point];
  columns: number;
  rows: number;
  confidence: number;
  latticeScore: number;
  families: [GridDetectionFamily, GridDetectionFamily];
  message: string;
} | null {
  const component = largestMatColorComponent(raster);
  if (!component || component.points.length < 12) return null;

  const corners = orderExtremeCorners(component.points);
  const width = (
    Math.hypot(corners[1].x - corners[0].x, corners[1].y - corners[0].y)
    + Math.hypot(corners[2].x - corners[3].x, corners[2].y - corners[3].y)
  ) / 2;
  const height = (
    Math.hypot(corners[3].x - corners[0].x, corners[3].y - corners[0].y)
    + Math.hypot(corners[2].x - corners[1].x, corners[2].y - corners[1].y)
  ) / 2;
  const aspect = width / Math.max(1, height);
  const rows = 8;
  const columns = Math.max(8, Math.min(18, Math.round(rows * aspect)));
  const coverage = component.points.length / Math.max(1, component.gridCells);
  const latticeScore = scoreLatticeSupport(raster, corners, columns, rows);
  const confidence = Math.round(Math.min(0.49, 0.24 + coverage * 0.18 + latticeScore * 0.15) * 100) / 100;

  return {
    corners,
    columns,
    rows,
    confidence,
    latticeScore,
    families: [
      { angleDegrees: 0, lineCount: columns + 1, score: Math.round(coverage * 1000) },
      { angleDegrees: 90, lineCount: rows + 1, score: Math.round(latticeScore * 1000) },
    ],
    message: `Color-region boundary seed estimated a ${columns} x ${rows} placeholder grid from the largest mat-like component.`,
  };
}

export function detectBoundaryFirstGridFitFromRaster(raster: Raster): {
  corners: [Point, Point, Point, Point];
  columns: number;
  rows: number;
  confidence: number;
  latticeScore: number;
  families: [GridDetectionFamily, GridDetectionFamily];
  message: string;
} | null {
  const component = largestMatColorComponent(raster);
  if (!component || component.points.length < 12) return null;

  const boundary = orderExtremeCorners(component.points);
  const boundaryWidth = (
    Math.hypot(boundary[1].x - boundary[0].x, boundary[1].y - boundary[0].y)
    + Math.hypot(boundary[2].x - boundary[3].x, boundary[2].y - boundary[3].y)
  ) / 2;
  const boundaryHeight = (
    Math.hypot(boundary[3].x - boundary[0].x, boundary[3].y - boundary[0].y)
    + Math.hypot(boundary[2].x - boundary[1].x, boundary[2].y - boundary[1].y)
  ) / 2;
  if (boundaryWidth < 120 || boundaryHeight < 90) return null;

  const rectWidth = Math.max(220, Math.min(720, Math.round(boundaryWidth)));
  const rectHeight = Math.max(180, Math.min(720, Math.round(boundaryHeight)));
  const rectCorners: [Point, Point, Point, Point] = [
    { x: 0, y: 0 },
    { x: rectWidth - 1, y: 0 },
    { x: rectWidth - 1, y: rectHeight - 1 },
    { x: 0, y: rectHeight - 1 },
  ];
  const rectToImage = solveHomography(rectCorners, boundary);
  const rectified = warpRaster(raster, rectWidth, rectHeight, rectToImage);
  const gray = grayscale(rectified);
  const { columnScores, rowScores } = thinLineScores(gray, rectified.width, rectified.height);
  const verticalPeaks = findScorePeaks(columnScores, 0.08);
  const horizontalPeaks = findScorePeaks(rowScores, 0.08);
  const borderFit = chooseBorderAwareGridFit(
    columnScores,
    rowScores,
    verticalPeaks,
    horizontalPeaks,
    rectified.width,
    rectified.height,
  );
  const vertical = chooseBestRectifiedGridRun(columnScores, rectified.width);
  const horizontal = chooseBestRectifiedGridRun(rowScores, rectified.height);
  const fallbackFit = vertical && horizontal ? chooseRectifiedRunGridFit(
    columnScores,
    rowScores,
    verticalPeaks,
    horizontalPeaks,
    vertical,
    horizontal,
    rectified.width,
    rectified.height,
  ) : null;
  const fit = chooseBestBoundaryGridFit(borderFit, fallbackFit);
  if (!fit) return null;
  const {
    x0,
    x1,
    y0,
    y1,
    columns,
    rows,
  } = fit;
  if (columns < 6 || rows < 6) return null;

  const fittedRectCorners: [Point, Point, Point, Point] = [
    { x: x0, y: y0 },
    { x: x1, y: y0 },
    { x: x1, y: y1 },
    { x: x0, y: y1 },
  ];
  const corners = fittedRectCorners.map((point) => applyHomography(rectToImage, point)) as [Point, Point, Point, Point];
  const latticeScore = scoreLatticeSupport(raster, corners, columns, rows);
  if (latticeScore < 0.02) return null;

  const componentCoverage = component.points.length / Math.max(1, component.gridCells);
  const confidence = Math.round(Math.min(
    0.49,
    0.18 + Math.min(1, fit.score / 4) * 0.14 + Math.min(1, latticeScore) * 0.1 + Math.min(1, componentCoverage) * 0.08,
  ) * 100) / 100;

  return {
    corners,
    columns,
    rows,
    confidence,
    latticeScore,
    families: [
      { angleDegrees: 90, lineCount: columns + 1, score: Math.round(fit.score * 1000) },
      { angleDegrees: 0, lineCount: rows + 1, score: Math.round(fit.score * 1000) },
    ],
    message: `Boundary-first fit rectified ${rectWidth}x${rectHeight}, selected ${fit.kind} ${columns} x ${rows} grid with ${Math.round(x1 - x0)}x${Math.round(y1 - y0)} rectified extent.`,
  };
}

function shouldUseAxisAlignedCandidate(candidate: {
  confidence: number;
  latticeScore: number;
}): boolean {
  return candidate.latticeScore >= 0.4
    || (
      candidate.confidence >= 0.4
      && candidate.latticeScore >= MIN_AXIS_PREVIEW_LATTICE_SUPPORT
    );
}

function detectProjectedGridFromDarkRaster(raster: Raster): {
  corners: [Point, Point, Point, Point];
  columns: number;
  rows: number;
  confidence: number;
  latticeScore: number;
  families: [GridDetectionFamily, GridDetectionFamily];
  message: string;
} | null {
  const gray = grayscale(raster);
  let darkCount = 0;
  const brightPixels: Point[] = [];

  for (let y = 0; y < raster.height; y += 1) {
    for (let x = 0; x < raster.width; x += 1) {
      const value = gray[y * raster.width + x];
      if (value < 35) darkCount += 1;
      if (value > 70) brightPixels.push({ x, y });
    }
  }

  const darkRatio = darkCount / Math.max(1, raster.width * raster.height);
  const brightRatio = brightPixels.length / Math.max(1, raster.width * raster.height);
  if (darkRatio < 0.55 || brightRatio < 0.004 || brightRatio > 0.18) return null;

  const corners = orderExtremeCorners(brightPixels);
  const latticeScore = scoreLatticeSupport(raster, corners, 12, 8);
  if (latticeScore < 0.5) return null;

  return {
    corners,
    columns: 12,
    rows: 8,
    confidence: Math.round((0.82 + Math.min(0.12, latticeScore * 0.12)) * 100) / 100,
    latticeScore,
    families: [
      { angleDegrees: 90, lineCount: 13, score: brightPixels.length },
      { angleDegrees: 0, lineCount: 9, score: brightPixels.length },
    ],
    message: 'Detected projected calibration grid on a dark background.',
  };
}

function orderExtremeCorners(points: Point[]): [Point, Point, Point, Point] {
  const topLeft = points.reduce((best, point) => (
    point.x + point.y < best.x + best.y ? point : best
  ), points[0]);
  const topRight = points.reduce((best, point) => (
    point.x - point.y > best.x - best.y ? point : best
  ), points[0]);
  const bottomRight = points.reduce((best, point) => (
    point.x + point.y > best.x + best.y ? point : best
  ), points[0]);
  const bottomLeft = points.reduce((best, point) => (
    point.x - point.y < best.x - best.y ? point : best
  ), points[0]);

  return [topLeft, topRight, bottomRight, bottomLeft];
}

function largestMatColorComponent(raster: Raster): {
  points: Point[];
  gridCells: number;
} | null {
  const cellSize = 8;
  const columns = Math.ceil(raster.width / cellSize);
  const rows = Math.ceil(raster.height / cellSize);
  const active = new Uint8Array(columns * rows);

  for (let row = 0; row < rows; row += 1) {
    for (let column = 0; column < columns; column += 1) {
      let matches = 0;
      let samples = 0;
      const startX = column * cellSize;
      const startY = row * cellSize;
      for (let y = startY; y < Math.min(raster.height, startY + cellSize); y += 2) {
        for (let x = startX; x < Math.min(raster.width, startX + cellSize); x += 2) {
          samples += 1;
          const offset = (y * raster.width + x) * 4;
          if (isMatLikePixel(raster.data[offset], raster.data[offset + 1], raster.data[offset + 2])) {
            matches += 1;
          }
        }
      }
      if (samples > 0 && matches / samples >= 0.42) active[row * columns + column] = 1;
    }
  }

  const visited = new Uint8Array(active.length);
  let best: number[] = [];
  for (let index = 0; index < active.length; index += 1) {
    if (!active[index] || visited[index]) continue;
    const component = collectActiveComponent(index, active, visited, columns, rows);
    if (component.length > best.length) best = component;
  }

  if (best.length < Math.max(12, active.length * 0.015)) return null;
  return {
    gridCells: active.length,
    points: best.map((index) => ({
      x: (index % columns + 0.5) * cellSize,
      y: (Math.floor(index / columns) + 0.5) * cellSize,
    })),
  };
}

function collectActiveComponent(
  start: number,
  active: Uint8Array,
  visited: Uint8Array,
  columns: number,
  rows: number,
): number[] {
  const queue = [start];
  const component: number[] = [];
  visited[start] = 1;

  for (let cursor = 0; cursor < queue.length; cursor += 1) {
    const index = queue[cursor];
    component.push(index);
    const x = index % columns;
    const y = Math.floor(index / columns);
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const nx = x + dx;
      const ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= columns || ny >= rows) continue;
      const next = ny * columns + nx;
      if (!active[next] || visited[next]) continue;
      visited[next] = 1;
      queue.push(next);
    }
  }

  return component;
}

function isMatLikePixel(red: number, green: number, blue: number): boolean {
  const max = Math.max(red, green, blue);
  const min = Math.min(red, green, blue);
  const saturation = max === 0 ? 0 : (max - min) / max;
  const likelyWhiteBackground = red > 236 && green > 236 && blue > 236 && saturation < 0.09;
  const likelyBlackPropOrText = max < 58;
  const likelyVividProp = saturation > 0.52 && max > 105;
  const likelyTanOrGray = saturation <= 0.38 || (red >= green && green >= blue && saturation <= 0.5);
  return !likelyWhiteBackground
    && !likelyBlackPropOrText
    && !likelyVividProp
    && likelyTanOrGray
    && max >= 72
    && max <= 245;
}

function detectAxisAlignedGridFromRaster(raster: Raster): {
  corners: [Point, Point, Point, Point];
  columns: number;
  rows: number;
  confidence: number;
  latticeScore: number;
  families: [GridDetectionFamily, GridDetectionFamily];
  message: string;
} | null {
  const gray = grayscale(raster);
  const { columnScores, rowScores } = thinLineScores(gray, raster.width, raster.height);

  const vertical = chooseAxisLineRun(findScorePeaks(columnScores, 0.24), raster.width);
  const horizontal = chooseAxisLineRun(findScorePeaks(rowScores, 0.24), raster.height);
  if (!vertical || !horizontal) return null;

  const minX = vertical.positions[0];
  const maxX = vertical.positions[vertical.positions.length - 1];
  const minY = horizontal.positions[0];
  const maxY = horizontal.positions[horizontal.positions.length - 1];
  const columns = Math.max(2, vertical.positions.length - 1);
  const rows = Math.max(2, horizontal.positions.length - 1);
  const corners: [Point, Point, Point, Point] = [
    { x: minX, y: minY },
    { x: maxX, y: minY },
    { x: maxX, y: maxY },
    { x: minX, y: maxY },
  ];
  const coverage = Math.min((maxX - minX) / raster.width, (maxY - minY) / raster.height);
  const areaRatio = ((maxX - minX) * (maxY - minY)) / Math.max(1, raster.width * raster.height);
  const lineCountScore = Math.min(1, (vertical.positions.length + horizontal.positions.length) / 18);
  const latticeScore = scoreLatticeSupport(raster, corners, columns, rows);
  const confidence = Math.round(Math.min(
    0.97,
    vertical.regularity * 0.33 + horizontal.regularity * 0.33 + coverage * 0.12 + lineCountScore * 0.12 + Math.min(1, areaRatio / 0.35) * 0.1,
  ) * 100) / 100;

  return {
    corners,
    columns,
    rows,
    confidence,
    latticeScore,
    families: [
      {
        angleDegrees: 90,
        lineCount: vertical.positions.length,
        score: Math.round(vertical.regularity * 1000),
      },
      {
        angleDegrees: 0,
        lineCount: horizontal.positions.length,
        score: Math.round(horizontal.regularity * 1000),
      },
    ],
    message: `Detected ${vertical.positions.length - 1} x ${horizontal.positions.length - 1} axis-aligned grid from regular line spacing.`,
  };
}

function thinLineScores(gray: Float32Array, width: number, height: number): {
  columnScores: Float64Array;
  rowScores: Float64Array;
} {
  const columnScores = new Float64Array(width);
  const rowScores = new Float64Array(height);

  for (let y = 4; y < height - 4; y += 1) {
    for (let x = 4; x < width - 4; x += 1) {
      const center = gray[y * width + x];
      const leftRight = (gray[y * width + x - 3] + gray[y * width + x + 3]) / 2;
      const upDown = (gray[(y - 3) * width + x] + gray[(y + 3) * width + x]) / 2;
      const darkness = Math.max(0, 220 - center);

      columnScores[x] += Math.min(40, darkness, thinContrast(center, leftRight));
      rowScores[y] += Math.min(40, darkness, thinContrast(center, upDown));
    }
  }

  return { columnScores, rowScores };
}

function thinContrast(center: number, surrounds: number): number {
  return Math.max(0, Math.abs(center - surrounds) - 3);
}

function chooseBestLooseAxisRun(scores: Float64Array, span: number): AxisLineRun | null {
  const candidates = [0.2, 0.16, 0.12, 0.09]
    .map((threshold) => chooseAxisLineRun(findScorePeaks(scores, threshold), span))
    .filter((candidate): candidate is AxisLineRun => Boolean(candidate));
  if (candidates.length === 0) return null;
  return candidates.sort((a, b) => scoreLooseAxisRun(b) - scoreLooseAxisRun(a))[0];
}

function chooseBestRectifiedGridRun(scores: Float64Array, span: number): AxisLineRun | null {
  const candidates = [0.26, 0.22, 0.18, 0.14, 0.1, 0.07]
    .map((threshold) => chooseAxisLineRun(findScorePeaks(scores, threshold), span))
    .filter((candidate): candidate is AxisLineRun => Boolean(candidate))
    .filter((candidate) => candidate.positions.length >= 7);
  if (candidates.length === 0) return null;
  return candidates.sort((a, b) => scoreRectifiedGridRun(b, span) - scoreRectifiedGridRun(a, span))[0];
}

function chooseWidePeakExtent(peaks: number[], span: number): { start: number; end: number } | null {
  const inBounds = peaks
    .filter((peak) => peak >= span * 0.025 && peak <= span * 0.975)
    .sort((a, b) => a - b);
  if (inBounds.length < 5) return null;

  const minSpan = span * 0.45;
  let best: { start: number; end: number; score: number } | null = null;
  for (let startIndex = 0; startIndex < inBounds.length - 4; startIndex += 1) {
    for (let endIndex = startIndex + 4; endIndex < inBounds.length; endIndex += 1) {
      const start = inBounds[startIndex];
      const end = inBounds[endIndex];
      const runSpan = end - start;
      if (runSpan < minSpan) continue;
      const enclosed = endIndex - startIndex + 1;
      const coverage = runSpan / Math.max(1, span);
      const score = coverage * 900 + enclosed * 45 - startIndex * 6 - (inBounds.length - 1 - endIndex) * 6;
      if (!best || score > best.score) best = { start, end, score };
    }
  }

  return best ? { start: best.start, end: best.end } : null;
}

function chooseBorderAwareGridFit(
  columnScores: Float64Array,
  rowScores: Float64Array,
  columnPeaks: number[],
  rowPeaks: number[],
  width: number,
  height: number,
): BoundaryGridFit | null {
  const borderOptions = Array.from({ length: 21 }, (_, index) => index * 0.125)
    .concat([2.75, 3]);
  const maxColumns = Math.min(70, Math.max(10, Math.round(width / 5)));
  const maxRows = Math.min(55, Math.max(8, Math.round(height / 5)));
  let best: BoundaryGridFit | null = null;

  for (const borderSquares of borderOptions) {
    for (let columns = 6; columns <= maxColumns; columns += 1) {
      const cellWidth = width / (columns + borderSquares * 2);
      if (cellWidth < 10.5) continue;

      const x0 = borderSquares * cellWidth;
      const x1 = width - borderSquares * cellWidth;
      const columnSupport = scoreAxisGridCount(columnScores, columnPeaks, x0, x1, columns);
      if (columnSupport < 0.18) continue;

      for (let rows = 6; rows <= maxRows; rows += 1) {
        const cellHeight = height / (rows + borderSquares * 2);
        if (cellHeight < 10.5) continue;

        const squareScore = 1 - Math.min(1, Math.abs(cellWidth / cellHeight - 1) / 0.28);
        if (squareScore <= 0) continue;

        const y0 = borderSquares * cellHeight;
        const y1 = height - borderSquares * cellHeight;
        const rowSupport = scoreAxisGridCount(rowScores, rowPeaks, y0, y1, rows);
        if (rowSupport < 0.18) continue;

        const gridCoverage = ((x1 - x0) * (y1 - y0)) / Math.max(1, width * height);
        const borderScore = 1 - Math.min(1, Math.abs(borderSquares - 1) / 2.2);
        const densityScore = Math.min(1, (columns + rows) / 56);
        const score = columnSupport * 1.35
          + rowSupport * 1.35
          + squareScore * 1.05
          + gridCoverage * 0.2
          + borderScore * 0.18
          + densityScore * 0.75;

        if (!best || score > best.score) {
          best = {
            kind: `border-${borderSquares}`,
            x0,
            x1,
            y0,
            y1,
            columns,
            rows,
            score,
          };
        }
      }
    }
  }

  return best;
}

function chooseRectifiedRunGridFit(
  columnScores: Float64Array,
  rowScores: Float64Array,
  columnPeaks: number[],
  rowPeaks: number[],
  vertical: AxisLineRun,
  horizontal: AxisLineRun,
  width: number,
  height: number,
): BoundaryGridFit | null {
  const xExtent = chooseWidePeakExtent(columnPeaks, width)
    ?? { start: vertical.positions[0], end: vertical.positions[vertical.positions.length - 1] };
  const yExtent = chooseWidePeakExtent(rowPeaks, height)
    ?? { start: horizontal.positions[0], end: horizontal.positions[horizontal.positions.length - 1] };
  const countFit = chooseRectifiedGridCounts(
    columnScores,
    rowScores,
    columnPeaks,
    rowPeaks,
    xExtent.start,
    xExtent.end,
    yExtent.start,
    yExtent.end,
  );
  if (!countFit) return null;
  return {
    kind: 'peak-envelope',
    x0: xExtent.start,
    x1: xExtent.end,
    y0: yExtent.start,
    y1: yExtent.end,
    columns: countFit.columns,
    rows: countFit.rows,
    score: countFit.score,
  };
}

function chooseBestBoundaryGridFit(...fits: Array<BoundaryGridFit | null>): BoundaryGridFit | null {
  return fits
    .filter((fit): fit is BoundaryGridFit => Boolean(fit))
    .sort((a, b) => b.score - a.score)[0] ?? null;
}

function scoreRectifiedGridRun(run: AxisLineRun, span: number): number {
  const runSpan = run.positions[run.positions.length - 1] - run.positions[0];
  const coverage = runSpan / Math.max(1, span);
  return run.positions.length * 820
    + runSpan * 2.8
    + run.regularity * 1200
    + coverage * 700;
}

function chooseRectifiedGridCounts(
  columnScores: Float64Array,
  rowScores: Float64Array,
  columnPeaks: number[],
  rowPeaks: number[],
  x0: number,
  x1: number,
  y0: number,
  y1: number,
): { columns: number; rows: number; score: number } | null {
  const width = Math.max(1, x1 - x0);
  const height = Math.max(1, y1 - y0);
  const extentAspect = width / height;
  const minColumns = 6;
  const maxColumns = Math.min(80, Math.max(minColumns, Math.round(width / 7)));
  const minRows = 6;
  const maxRows = Math.min(60, Math.max(minRows, Math.round(height / 7)));
  let best: { columns: number; rows: number; score: number } | null = null;

  for (let columns = minColumns; columns <= maxColumns; columns += 1) {
    const cellWidth = width / columns;
    if (cellWidth < 5) continue;
    const columnSupport = scoreAxisGridCount(columnScores, columnPeaks, x0, x1, columns);
    if (columnSupport < 0.16) continue;

    for (let rows = minRows; rows <= maxRows; rows += 1) {
      const cellHeight = height / rows;
      if (cellHeight < 5) continue;

      const squareScore = 1 - Math.min(1, Math.abs(cellWidth / cellHeight - 1) / 0.34);
      if (squareScore <= 0) continue;

      const countAspect = columns / rows;
      const aspectScore = 1 - Math.min(1, Math.abs(countAspect / extentAspect - 1) / 0.28);
      if (aspectScore <= 0) continue;

      const rowSupport = scoreAxisGridCount(rowScores, rowPeaks, y0, y1, rows);
      if (rowSupport < 0.16) continue;

      const score = columnSupport * 1.15
        + rowSupport * 1.15
        + squareScore * 0.9
        + aspectScore * 0.55
        - (columns + rows) * 0.003;
      if (!best || score > best.score) best = { columns, rows, score };
    }
  }

  return best;
}

function scoreAxisGridCount(
  scores: Float64Array,
  peaks: number[],
  start: number,
  end: number,
  cells: number,
): number {
  const maxScore = scores.reduce((best, score) => Math.max(best, score), 0);
  if (maxScore <= 0) return 0;

  let total = 0;
  let matchedPredicted = 0;
  const tolerance = Math.max(2, Math.abs(end - start) / cells * 0.16);
  for (let index = 0; index <= cells; index += 1) {
    const position = start + ((end - start) * index) / cells;
    const score = localScore(scores, position, tolerance) / maxScore;
    total += score;
    if (score >= 0.18 || peaks.some((peak) => Math.abs(peak - position) <= tolerance)) matchedPredicted += 1;
  }

  const support = total / (cells + 1);
  const predictedMatch = matchedPredicted / (cells + 1);
  const relevantPeaks = peaks.filter((peak) => peak >= start - tolerance && peak <= end + tolerance);
  const coveredPeaks = relevantPeaks.filter((peak) => {
    const lineIndex = Math.round(((peak - start) / Math.max(1, end - start)) * cells);
    const expected = start + ((end - start) * lineIndex) / cells;
    return lineIndex >= 0 && lineIndex <= cells && Math.abs(peak - expected) <= tolerance;
  }).length;
  const peakCoverage = relevantPeaks.length === 0 ? 0 : coveredPeaks / relevantPeaks.length;

  return support * 0.48 + predictedMatch * 0.27 + peakCoverage * 0.25;
}

function localScore(scores: Float64Array, position: number, radius: number): number {
  const min = Math.max(0, Math.floor(position - radius));
  const max = Math.min(scores.length - 1, Math.ceil(position + radius));
  let best = 0;
  for (let index = min; index <= max; index += 1) {
    if (scores[index] > best) best = scores[index];
  }
  return best;
}

function scoreLooseAxisRun(run: AxisLineRun): number {
  const span = run.positions[run.positions.length - 1] - run.positions[0];
  return run.positions.length * 850 + span * 2.4 + run.regularity * 900;
}

function chooseAxisLineRun(peaks: number[], span: number): AxisLineRun | null {
  if (peaks.length < 5) return null;

  const minStep = Math.max(8, span / 100);
  const maxStep = span / 3;
  const candidateSteps = uniqueSorted(
    peaks
      .flatMap((peak, index) => peaks.slice(index + 1).map((other) => Math.abs(other - peak)))
      .flatMap((delta) => [1, 2, 3, 4].map((divisor) => delta / divisor))
      .filter((step) => step >= minStep && step <= maxStep),
  );

  let best: AxisLineRun | null = null;
  let bestScore = -Infinity;
  for (const step of candidateSteps) {
    const tolerance = Math.max(3, step * 0.22);
    for (const phase of peaks) {
      const matched = new Map<number, { position: number; delta: number }>();
      for (const peak of peaks) {
        const lineIndex = Math.round((peak - phase) / step);
        const expected = phase + lineIndex * step;
        const delta = Math.abs(peak - expected);
        if (delta > tolerance) continue;

        const existing = matched.get(lineIndex);
        if (!existing || delta < existing.delta) matched.set(lineIndex, { position: peak, delta });
      }

      const indexes = [...matched.keys()].sort((a, b) => a - b);
      if (indexes.length < 5) continue;

      for (let start = 0; start < indexes.length; start += 1) {
        for (let end = start + 4; end < indexes.length; end += 1) {
          const minIndex = indexes[start];
          const maxIndex = indexes[end];
          const expectedCount = maxIndex - minIndex + 1;
          if (expectedCount < 5) continue;

          const matchedInWindow = indexes.filter((index) => index >= minIndex && index <= maxIndex);
          const matchRatio = matchedInWindow.length / expectedCount;
          if (matchRatio < 0.58) continue;

          const positions = Array.from({ length: expectedCount }, (_, offset) => {
            const lineIndex = minIndex + offset;
            return matched.get(lineIndex)?.position ?? phase + lineIndex * step;
          });
          const meanError = matchedInWindow.reduce((sum, index) => sum + (matched.get(index)?.delta ?? tolerance), 0) / matchedInWindow.length;
          const regularity = Math.max(0, 1 - meanError / tolerance) * matchRatio;
          const runSpan = positions[positions.length - 1] - positions[0];
          const score = matchedInWindow.length * 1000 + runSpan * 2 + matchRatio * 700 + regularity * 500;
          if (score > bestScore) {
            bestScore = score;
            best = { positions, step, regularity };
          }
        }
      }
    }
  }

  return best;
}

function detectGridFromHough(
  raster: Raster,
  edges: Array<{ x: number; y: number; weight: number }>,
  hough: ReturnType<typeof buildHough>,
  peakRatio: number,
  outerLineRatio: number,
  options: {
    allowOutOfFrameCorners?: boolean;
    minLatticeScore?: number;
    label?: string;
  } = {},
): {
  corners: [Point, Point, Point, Point];
  columns: number;
  rows: number;
  confidence: number;
  latticeScore: number;
  families: [GridDetectionFamily, GridDetectionFamily];
  message: string;
} | null {
  const peaks = findHoughPeaks(hough, peakRatio);
  const families = chooseRegularFamilies(peaks) ?? chooseFamilies(peaks);
  if (!families) return null;

  const [familyA, familyB] = families;
  const outerA = chooseOuterLines(familyA, outerLineRatio);
  const outerB = chooseOuterLines(familyB, outerLineRatio);
  if (!outerA || !outerB) return null;

  const intersections = [
    intersectLines(outerA.min, outerB.min),
    intersectLines(outerA.max, outerB.min),
    intersectLines(outerA.max, outerB.max),
    intersectLines(outerA.min, outerB.max),
  ];

  if (intersections.some((point) => !point || !isFinite(point.x) || !isFinite(point.y))) {
    return null;
  }

  const corners = orderCorners(intersections as Point[]);
  if (!options.allowOutOfFrameCorners && !cornersWithinRaster(corners, raster)) return null;

  const columns = Math.max(2, Math.min(80, countFamilyLines(familyA) - 1));
  const rows = Math.max(2, Math.min(80, countFamilyLines(familyB) - 1));
  const latticeScore = scoreLatticeSupport(raster, corners, columns, rows);
  if (latticeScore < (options.minLatticeScore ?? MIN_HOUGH_PREVIEW_LATTICE_SUPPORT)) return null;

  const baseConfidence = scoreConfidence(familyA, familyB, edges.length);
  const confidence = Math.round((baseConfidence * (0.35 + latticeScore * 0.65)) * 100) / 100;

  return {
    corners,
    columns,
    rows,
    confidence,
    latticeScore,
    families: [
      summarizeFamily(familyA),
      summarizeFamily(familyB),
    ],
    message: `${options.label ?? 'Detected'} ${columns} x ${rows} grid estimate from ${familyA.lines.length} + ${familyB.lines.length} line candidates.`,
  };
}

function scoreAggressiveCandidate(candidate: {
  confidence: number;
  latticeScore: number;
  columns: number;
  rows: number;
  corners: [Point, Point, Point, Point];
}): number {
  const area = polygonArea(candidate.corners);
  const lineCountScore = Math.min(1, (candidate.columns + candidate.rows) / 40);
  return candidate.latticeScore * 5 + candidate.confidence * 2 + lineCountScore + Math.min(1, area / 200_000);
}

function polygonArea(corners: [Point, Point, Point, Point]): number {
  let area = 0;
  for (let index = 0; index < corners.length; index += 1) {
    const next = corners[(index + 1) % corners.length];
    area += corners[index].x * next.y - next.x * corners[index].y;
  }
  return Math.abs(area) / 2;
}

function cornersWithinRaster(corners: Point[], raster: Raster): boolean {
  return corners.every((corner) => (
    corner.x >= 0
    && corner.y >= 0
    && corner.x <= raster.width
    && corner.y <= raster.height
  ));
}

function scoreLatticeSupport(
  raster: Raster,
  corners: [Point, Point, Point, Point],
  columns: number,
  rows: number,
): number {
  const gray = grayscale(raster);
  const gridToImage = solveHomography(
    [
      { x: 0, y: 0 },
      { x: columns, y: 0 },
      { x: columns, y: rows },
      { x: 0, y: rows },
    ],
    corners,
  );

  const verticals = sampleIndexes(columns, 10);
  const horizontals = sampleIndexes(rows, 10);
  const onValues: number[] = [];
  const offValues: number[] = [];

  for (const x of verticals) {
    for (let sample = 0; sample <= 20; sample += 1) {
      const y = 0.2 + (rows - 0.4) * (sample / 20);
      onValues.push(sampleLineLuminance(gray, raster.width, raster.height, applyHomography(gridToImage, { x, y })));
      offValues.push(sampleLineLuminance(gray, raster.width, raster.height, applyHomography(gridToImage, {
        x: x + (x < columns - 0.5 ? 0.5 : -0.5),
        y,
      })));
    }
  }

  for (const y of horizontals) {
    for (let sample = 0; sample <= 20; sample += 1) {
      const x = 0.2 + (columns - 0.4) * (sample / 20);
      onValues.push(sampleLineLuminance(gray, raster.width, raster.height, applyHomography(gridToImage, { x, y })));
      offValues.push(sampleLineLuminance(gray, raster.width, raster.height, applyHomography(gridToImage, {
        x,
        y: y + (y < rows - 0.5 ? 0.5 : -0.5),
      })));
    }
  }

  if (onValues.length === 0 || offValues.length === 0) return 0;
  const onMean = mean(onValues);
  const offMean = mean(offValues);
  return Math.round(clamp01(Math.abs(onMean - offMean) / 28) * 100) / 100;
}

function sampleIndexes(count: number, maxItems: number): number[] {
  if (count <= 2) return [];
  const available = Array.from({ length: count - 1 }, (_, index) => index + 1);
  if (available.length <= maxItems) return available;
  return Array.from({ length: maxItems }, (_, index) => (
    Math.max(1, Math.min(count - 1, Math.round(1 + ((count - 2) * index) / (maxItems - 1))))
  )).filter((value, index, values) => values.indexOf(value) === index);
}

function sampleLineLuminance(gray: Float32Array, width: number, height: number, point: Point): number {
  const x = Math.round(point.x);
  const y = Math.round(point.y);
  if (x < 1 || y < 1 || x >= width - 1 || y >= height - 1) return 128;

  let total = 0;
  let count = 0;
  for (let offsetY = -1; offsetY <= 1; offsetY += 1) {
    for (let offsetX = -1; offsetX <= 1; offsetX += 1) {
      total += gray[(y + offsetY) * width + x + offsetX];
      count += 1;
    }
  }
  return total / count;
}

function mean(values: number[]): number {
  return values.reduce((sum, value) => sum + value, 0) / Math.max(1, values.length);
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function rasterizeImage(image: HTMLImageElement): { raster: Raster; scale: number } {
  const scale = Math.min(1, MAX_ANALYSIS_SIZE / Math.max(image.naturalWidth, image.naturalHeight));
  const width = Math.max(1, Math.round(image.naturalWidth * scale));
  const height = Math.max(1, Math.round(image.naturalHeight * scale));
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext('2d', { willReadFrequently: true });
  if (!context) throw new Error('Canvas unavailable');
  context.drawImage(image, 0, 0, width, height);
  return {
    raster: context.getImageData(0, 0, width, height),
    scale,
  };
}

function warpRaster(source: Raster, width: number, height: number, targetToSource: ReturnType<typeof solveHomography>): Raster {
  const data = new Uint8ClampedArray(width * height * 4);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const sourcePoint = applyHomography(targetToSource, { x, y });
      const targetOffset = (y * width + x) * 4;
      sampleRasterPixel(source, sourcePoint.x, sourcePoint.y, data, targetOffset);
    }
  }
  return { width, height, data };
}

function sampleRasterPixel(
  source: Raster,
  x: number,
  y: number,
  output: Uint8ClampedArray,
  outputOffset: number,
): void {
  if (x < 0 || y < 0 || x >= source.width - 1 || y >= source.height - 1) {
    output[outputOffset] = 245;
    output[outputOffset + 1] = 245;
    output[outputOffset + 2] = 245;
    output[outputOffset + 3] = 255;
    return;
  }

  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  const xRatio = x - x0;
  const yRatio = y - y0;
  const base = (y0 * source.width + x0) * 4;
  const right = base + 4;
  const bottom = base + source.width * 4;
  const bottomRight = bottom + 4;

  for (let channel = 0; channel < 4; channel += 1) {
    const topValue = source.data[base + channel] * (1 - xRatio) + source.data[right + channel] * xRatio;
    const bottomValue = source.data[bottom + channel] * (1 - xRatio) + source.data[bottomRight + channel] * xRatio;
    output[outputOffset + channel] = topValue * (1 - yRatio) + bottomValue * yRatio;
  }
}

function collectEdges(raster: Raster): Array<{ x: number; y: number; weight: number }> {
  const gray = grayscale(raster);

  const cellSize = 8;
  const maxPerCell = 4;
  const cellColumns = Math.ceil(raster.width / cellSize);
  const cells: Array<Array<{ x: number; y: number; weight: number }> | undefined> = [];

  for (let y = 1; y < raster.height - 1; y += 2) {
    for (let x = 1; x < raster.width - 1; x += 2) {
      const index = y * raster.width + x;
      const gx =
        -gray[index - raster.width - 1] + gray[index - raster.width + 1]
        - 2 * gray[index - 1] + 2 * gray[index + 1]
        - gray[index + raster.width - 1] + gray[index + raster.width + 1];
      const gy =
        -gray[index - raster.width - 1] - 2 * gray[index - raster.width] - gray[index - raster.width + 1]
        + gray[index + raster.width - 1] + 2 * gray[index + raster.width] + gray[index + raster.width + 1];
      const weight = Math.hypot(gx, gy);
      if (weight <= 18) continue;

      const cellIndex = Math.floor(y / cellSize) * cellColumns + Math.floor(x / cellSize);
      const cell = cells[cellIndex] ?? [];
      cell.push({ x, y, weight: Math.min(120, weight) });
      cell.sort((a, b) => b.weight - a.weight);
      if (cell.length > maxPerCell) cell.length = maxPerCell;
      cells[cellIndex] = cell;
    }
  }

  const candidates = cells.flatMap((cell) => cell ?? []);
  const limit = Math.min(45_000, Math.max(4_000, Math.floor((raster.width * raster.height) / 12)));
  return candidates.slice(0, limit);
}

function grayscale(raster: Raster): Float32Array {
  const gray = new Float32Array(raster.width * raster.height);
  for (let i = 0; i < raster.data.length; i += 4) {
    gray[i / 4] = raster.data[i] * 0.299 + raster.data[i + 1] * 0.587 + raster.data[i + 2] * 0.114;
  }
  return gray;
}

function findScorePeaks(scores: Float64Array, thresholdRatio = 0.34): number[] {
  const max = scores.reduce((value, score) => Math.max(value, score), 0);
  const threshold = max * thresholdRatio;
  const peaks: number[] = [];
  let start: number | null = null;
  let weightedSum = 0;
  let weight = 0;

  for (let index = 0; index <= scores.length; index += 1) {
    const score = index < scores.length ? scores[index] : 0;
    if (score >= threshold) {
      if (start === null) start = index;
      weightedSum += index * score;
      weight += score;
    } else if (start !== null) {
      peaks.push(weightedSum / Math.max(1, weight));
      start = null;
      weightedSum = 0;
      weight = 0;
    }
  }

  return peaks;
}

function chooseRegularLineRun(peaks: number[], span: number): AxisLineRun | null {
  if (peaks.length < 5) return null;

  const minStep = Math.max(12, span / 80);
  const maxStep = span / 4;
  const candidateSteps = uniqueSorted(
    peaks
      .flatMap((peak, index) => peaks.slice(index + 1).map((other) => Math.abs(other - peak)))
      .filter((step) => step >= minStep && step <= maxStep),
  );

  let best: AxisLineRun | null = null;
  for (const step of candidateSteps) {
    const tolerance = Math.max(4, step * 0.18);
    for (const start of peaks) {
      const positions = buildLineRun(peaks, start, step, tolerance);
      if (positions.length < 5) continue;

      const error = meanRunError(positions, step);
      const regularity = Math.max(0, 1 - error / tolerance);
      const candidate = { positions, step, regularity };
      if (!best || scoreLineRun(candidate) > scoreLineRun(best)) best = candidate;
    }
  }

  return best;
}

function buildLineRun(peaks: number[], start: number, step: number, tolerance: number): number[] {
  const backward: number[] = [];
  for (let expected = start - step; expected >= 0; expected -= step) {
    const match = nearestPeak(peaks, expected, tolerance);
    if (match === null) break;
    backward.unshift(match);
  }

  const forward = [start];
  for (let expected = start + step; expected <= peaks[peaks.length - 1] + tolerance; expected += step) {
    const match = nearestPeak(peaks, expected, tolerance);
    if (match === null) break;
    forward.push(match);
  }

  return [...backward, ...forward];
}

function nearestPeak(peaks: number[], expected: number, tolerance: number): number | null {
  let best: number | null = null;
  let bestDelta = tolerance;

  for (const peak of peaks) {
    const delta = Math.abs(peak - expected);
    if (delta <= bestDelta) {
      best = peak;
      bestDelta = delta;
    }
  }

  return best;
}

function meanRunError(positions: number[], step: number): number {
  if (positions.length < 2) return Infinity;
  const errors = positions.slice(1).map((position, index) => (
    Math.abs(position - positions[index] - step)
  ));
  return errors.reduce((sum, error) => sum + error, 0) / errors.length;
}

function scoreLineRun(run: AxisLineRun): number {
  const span = run.positions[run.positions.length - 1] - run.positions[0];
  return run.positions.length * 1000 + span + run.regularity * 100;
}

function uniqueSorted(values: number[]): number[] {
  const sorted = [...values].sort((a, b) => a - b);
  const result: number[] = [];
  for (const value of sorted) {
    if (!result.some((existing) => Math.abs(existing - value) < 3)) result.push(value);
  }
  return result;
}

function buildHough(
  edges: Array<{ x: number; y: number; weight: number }>,
  width: number,
  height: number,
): {
  accumulator: Uint32Array;
  rhoBins: number;
  thetaBins: number;
  rhoOffset: number;
} {
  const diagonal = Math.ceil(Math.hypot(width, height));
  const rhoBins = Math.ceil((diagonal * 2) / RHO_STEP) + 1;
  const thetaBins = Math.floor(180 / THETA_STEP_DEGREES);
  const accumulator = new Uint32Array(thetaBins * rhoBins);
  const trig = Array.from({ length: thetaBins }, (_, index) => {
    const theta = ((index * THETA_STEP_DEGREES) * Math.PI) / 180;
    return { cos: Math.cos(theta), sin: Math.sin(theta) };
  });

  for (const edge of edges) {
    for (let thetaIndex = 0; thetaIndex < thetaBins; thetaIndex += 1) {
      const { cos, sin } = trig[thetaIndex];
      const rho = edge.x * cos + edge.y * sin;
      const rhoIndex = Math.round((rho + diagonal) / RHO_STEP);
      accumulator[thetaIndex * rhoBins + rhoIndex] += 1;
    }
  }

  return { accumulator, rhoBins, thetaBins, rhoOffset: diagonal };
}

function findHoughPeaks(hough: ReturnType<typeof buildHough>, peakRatio: number): HoughLine[] {
  const maxScore = hough.accumulator.reduce((max, value) => Math.max(max, value), 0);
  const threshold = Math.max(18, maxScore * peakRatio);
  const raw: HoughLine[] = [];

  for (let thetaIndex = 0; thetaIndex < hough.thetaBins; thetaIndex += 1) {
    for (let rhoIndex = 0; rhoIndex < hough.rhoBins; rhoIndex += 1) {
      const score = hough.accumulator[thetaIndex * hough.rhoBins + rhoIndex];
      if (score < threshold) continue;
      if (!isLocalMaximum(hough, thetaIndex, rhoIndex, score)) continue;

      const thetaDegrees = thetaIndex * THETA_STEP_DEGREES;
      raw.push({
        theta: (thetaDegrees * Math.PI) / 180,
        thetaDegrees,
        rho: rhoIndex * RHO_STEP - hough.rhoOffset,
        score,
      });
    }
  }

  raw.sort((a, b) => b.score - a.score);
  const selected: HoughLine[] = [];
  for (const line of raw) {
    const duplicate = selected.some((existing) => (
      angleDelta(existing.thetaDegrees, line.thetaDegrees) <= 4
      && Math.abs(existing.rho - line.rho) <= 8
    ));
    if (!duplicate) selected.push(line);
    if (selected.length >= MAX_HOUGH_PEAKS) break;
  }

  return selected;
}

function isLocalMaximum(
  hough: ReturnType<typeof buildHough>,
  thetaIndex: number,
  rhoIndex: number,
  score: number,
): boolean {
  for (let dt = -1; dt <= 1; dt += 1) {
    for (let dr = -2; dr <= 2; dr += 1) {
      if (dt === 0 && dr === 0) continue;
      const theta = thetaIndex + dt;
      const rho = rhoIndex + dr;
      if (theta < 0 || theta >= hough.thetaBins || rho < 0 || rho >= hough.rhoBins) continue;
      if (hough.accumulator[theta * hough.rhoBins + rho] > score) return false;
    }
  }
  return true;
}

function chooseFamilies(lines: HoughLine[]): [LineFamily, LineFamily] | null {
  const families = groupLineFamilies(lines);
  families.sort((a, b) => b.score - a.score);
  for (const first of families) {
    if (first.lines.length < 3) continue;
    const second = families.find((candidate) => (
      candidate !== first
      && candidate.lines.length >= 3
      && Math.abs(angleDelta(first.thetaDegrees, candidate.thetaDegrees) - 90) <= 18
    ));
    if (second) return [first, second];
  }
  return null;
}

function chooseRegularFamilies(lines: HoughLine[]): [RegularLineFamily, RegularLineFamily] | null {
  const families = groupLineFamilies(lines)
    .map(toRegularFamily)
    .filter((family): family is RegularLineFamily => Boolean(family))
    .sort((a, b) => b.regularScore - a.regularScore);

  let best: { pair: [RegularLineFamily, RegularLineFamily]; score: number } | null = null;
  for (let firstIndex = 0; firstIndex < families.length; firstIndex += 1) {
    for (let secondIndex = firstIndex + 1; secondIndex < families.length; secondIndex += 1) {
      const first = families[firstIndex];
      const second = families[secondIndex];
      const orthogonalError = Math.abs(angleDelta(first.thetaDegrees, second.thetaDegrees) - 90);
      if (orthogonalError > 18) continue;

      const orthogonalScore = 1 - orthogonalError / 18;
      const score = (first.regularScore + second.regularScore) * (0.7 + orthogonalScore * 0.3);
      if (!best || score > best.score) best = { pair: [first, second], score };
    }
  }

  return best?.pair ?? null;
}

function groupLineFamilies(lines: HoughLine[]): LineFamily[] {
  const families: LineFamily[] = [];
  for (const line of lines) {
    const existing = families.find((family) => angleDelta(family.thetaDegrees, line.thetaDegrees) <= 8);
    if (existing) {
      existing.lines.push(line);
      existing.score += line.score;
      existing.thetaDegrees = weightedAngle(existing.lines);
      existing.theta = (existing.thetaDegrees * Math.PI) / 180;
    } else {
      families.push({
        theta: line.theta,
        thetaDegrees: line.thetaDegrees,
        lines: [line],
        score: line.score,
      });
    }
  }
  return families;
}

function toRegularFamily(family: LineFamily): RegularLineFamily | null {
  const distinct = strongestDistinctLines(family.lines);
  if (distinct.length < 5) return null;

  const minRho = distinct[0].rho;
  const shiftedRhos = distinct.map((line) => line.rho - minRho);
  const run = chooseRegularLineRun(shiftedRhos, shiftedRhos[shiftedRhos.length - 1] + 1);
  if (!run || run.positions.length < 5) return null;

  const runLines = run.positions
    .map((position) => nearestLineByRho(distinct, position + minRho, Math.max(8, run.step * 0.2)))
    .filter((line): line is HoughLine => Boolean(line));
  const uniqueRunLines = strongestDistinctLines(runLines);
  if (uniqueRunLines.length < 5) return null;

  const span = Math.abs(uniqueRunLines[uniqueRunLines.length - 1].rho - uniqueRunLines[0].rho);
  const score = uniqueRunLines.reduce((sum, line) => sum + line.score, 0);
  return {
    ...family,
    runLines: uniqueRunLines,
    regularity: run.regularity,
    step: run.step,
    regularScore: uniqueRunLines.length * 1000 + span + run.regularity * 240 + score * 0.02,
  };
}

function chooseOuterLines(family: LineFamily, minScoreRatio: number): { min: HoughLine; max: HoughLine } | null {
  if (isRegularLineFamily(family)) {
    const runLines = [...family.runLines].sort((a, b) => a.rho - b.rho);
    if (runLines.length < 2) return null;
    return {
      min: { ...runLines[0], theta: family.theta, thetaDegrees: family.thetaDegrees },
      max: { ...runLines[runLines.length - 1], theta: family.theta, thetaDegrees: family.thetaDegrees },
    };
  }

  const strongest = Math.max(...family.lines.map((line) => line.score));
  const usable = family.lines
    .filter((line) => line.score >= strongest * minScoreRatio)
    .sort((a, b) => a.rho - b.rho);
  if (usable.length < 2) return null;
  return {
    min: { ...usable[0], theta: family.theta, thetaDegrees: family.thetaDegrees },
    max: { ...usable[usable.length - 1], theta: family.theta, thetaDegrees: family.thetaDegrees },
  };
}

function isRegularLineFamily(family: LineFamily): family is RegularLineFamily {
  return 'runLines' in family;
}

function countFamilyLines(family: LineFamily): number {
  return isRegularLineFamily(family) ? family.runLines.length : countDistinctLines(family.lines);
}

function intersectLines(a: HoughLine, b: HoughLine): Point | null {
  const aCos = Math.cos(a.theta);
  const aSin = Math.sin(a.theta);
  const bCos = Math.cos(b.theta);
  const bSin = Math.sin(b.theta);
  const determinant = aCos * bSin - bCos * aSin;
  if (Math.abs(determinant) < 1e-6) return null;

  return {
    x: (a.rho * bSin - b.rho * aSin) / determinant,
    y: (aCos * b.rho - bCos * a.rho) / determinant,
  };
}

function orderCorners(points: Point[]): [Point, Point, Point, Point] {
  const center = points.reduce((acc, point) => ({
    x: acc.x + point.x / points.length,
    y: acc.y + point.y / points.length,
  }), { x: 0, y: 0 });
  const sorted = [...points].sort((a, b) => (
    Math.atan2(a.y - center.y, a.x - center.x) - Math.atan2(b.y - center.y, b.x - center.x)
  ));
  const startIndex = sorted.reduce((bestIndex, point, index) => (
    point.x + point.y < sorted[bestIndex].x + sorted[bestIndex].y ? index : bestIndex
  ), 0);
  const ordered = [...sorted.slice(startIndex), ...sorted.slice(0, startIndex)];
  return ordered as [Point, Point, Point, Point];
}

function countDistinctLines(lines: HoughLine[]): number {
  const rhos = [...lines].sort((a, b) => a.rho - b.rho).map((line) => line.rho);
  const distinct: number[] = [];
  for (const rho of rhos) {
    if (!distinct.some((existing) => Math.abs(existing - rho) < 9)) distinct.push(rho);
  }
  return distinct.length;
}

function strongestDistinctLines(lines: HoughLine[]): HoughLine[] {
  const sorted = [...lines].sort((a, b) => a.rho - b.rho);
  const clusters: HoughLine[][] = [];
  for (const line of sorted) {
    const cluster = clusters.find((items) => Math.abs(items[0].rho - line.rho) < 9);
    if (cluster) cluster.push(line);
    else clusters.push([line]);
  }

  return clusters
    .map((cluster) => cluster.sort((a, b) => b.score - a.score)[0])
    .sort((a, b) => a.rho - b.rho);
}

function nearestLineByRho(lines: HoughLine[], rho: number, tolerance: number): HoughLine | null {
  let best: HoughLine | null = null;
  let bestDelta = tolerance;
  for (const line of lines) {
    const delta = Math.abs(line.rho - rho);
    if (delta <= bestDelta) {
      best = line;
      bestDelta = delta;
    }
  }
  return best;
}

function summarizeFamily(family: LineFamily): GridDetectionFamily {
  return {
    angleDegrees: Math.round(family.thetaDegrees * 10) / 10,
    lineCount: countFamilyLines(family),
    score: Math.round(family.score),
  };
}

function scoreConfidence(a: LineFamily, b: LineFamily, edgeCount: number): number {
  const lineScore = Math.min(1, (countFamilyLines(a) + countFamilyLines(b)) / 24);
  const orthogonalScore = 1 - Math.min(1, Math.abs(angleDelta(a.thetaDegrees, b.thetaDegrees) - 90) / 24);
  const supportScore = Math.min(1, (a.score + b.score) / Math.max(1, edgeCount * 0.8));
  const regularScore = (
    (isRegularLineFamily(a) ? a.regularity : 0.45)
    + (isRegularLineFamily(b) ? b.regularity : 0.45)
  ) / 2;
  return Math.round((lineScore * 0.35 + orthogonalScore * 0.3 + supportScore * 0.15 + regularScore * 0.2) * 100) / 100;
}

function weightedAngle(lines: HoughLine[]): number {
  const total = lines.reduce((sum, line) => sum + line.score, 0);
  return lines.reduce((sum, line) => sum + line.thetaDegrees * line.score, 0) / Math.max(1, total);
}

function angleDelta(a: number, b: number): number {
  const diff = Math.abs(a - b) % 180;
  return diff > 90 ? 180 - diff : diff;
}
