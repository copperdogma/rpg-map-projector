import { applyHomography, solveHomography } from './homography';
import type { CalibrationAnchor, DetectedGrid, Point } from './types';

interface ProjectorSize {
  width: number;
  height: number;
}

export interface FitRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface AutoAlignQuality {
  ok: boolean;
  areaRatio: number;
  outsideCornerCount: number;
  issues: string[];
}

const MIN_AUTO_ALIGN_AREA_RATIO = 0.35;
const MIN_AUTO_ALIGN_LATTICE_SUPPORT = 0.2;
const MAX_AUTO_ALIGN_COLUMNS = 16;
const MAX_AUTO_ALIGN_ROWS = 12;

export function fitImageInProjector(
  imageWidth: number,
  imageHeight: number,
  projector: ProjectorSize,
): FitRect {
  const scale = Math.min(projector.width / imageWidth, projector.height / imageHeight);
  const width = imageWidth * scale;
  const height = imageHeight * scale;

  return {
    x: (projector.width - width) / 2,
    y: (projector.height - height) / 2,
    width,
    height,
  };
}

export function mapDetectedGridToAnchors(
  detected: DetectedGrid,
  existingAnchors: CalibrationAnchor[],
  projector: ProjectorSize,
): CalibrationAnchor[] {
  const fit = fitImageInProjector(detected.imageWidth, detected.imageHeight, projector);
  const imageToProjector = solveHomography(
    [
      { x: 0, y: 0 },
      { x: detected.imageWidth, y: 0 },
      { x: detected.imageWidth, y: detected.imageHeight },
      { x: 0, y: detected.imageHeight },
    ],
    [
      { x: fit.x, y: fit.y },
      { x: fit.x + fit.width, y: fit.y },
      { x: fit.x + fit.width, y: fit.y + fit.height },
      { x: fit.x, y: fit.y + fit.height },
    ],
  );

  return existingAnchors.map((anchor, index) => ({
    ...anchor,
    projector: applyHomography(imageToProjector, detected.corners[index] ?? detected.corners[0]),
  }));
}

export function evaluateDetectedGridForAutoAlign(detected: DetectedGrid): AutoAlignQuality {
  const areaRatio = polygonArea(detected.corners) / Math.max(1, detected.imageWidth * detected.imageHeight);
  const outsideCornerCount = detected.corners.filter((corner) => (
    corner.x < 0
    || corner.y < 0
    || corner.x > detected.imageWidth
    || corner.y > detected.imageHeight
  )).length;
  const issues: string[] = [];

  if (outsideCornerCount > 0) {
    issues.push(`${outsideCornerCount} detected corner${outsideCornerCount === 1 ? ' is' : 's are'} outside the image`);
  }
  if (areaRatio < MIN_AUTO_ALIGN_AREA_RATIO) {
    issues.push(`detected grid covers only ${Math.round(areaRatio * 100)}% of the image`);
  }
  if (areaRatio > 0.95) {
    issues.push(`detected grid covers ${Math.round(areaRatio * 100)}% of the image`);
  }
  if (detected.confidence < 0.72) {
    issues.push(`${Math.round(detected.confidence * 100)}% confidence is below the auto-align threshold`);
  }
  if (detected.latticeScore !== undefined && detected.latticeScore < MIN_AUTO_ALIGN_LATTICE_SUPPORT) {
    issues.push(`${Math.round(detected.latticeScore * 100)}% lattice support is below the auto-align threshold`);
  }
  if (detected.columns > MAX_AUTO_ALIGN_COLUMNS || detected.rows > MAX_AUTO_ALIGN_ROWS) {
    issues.push(`detected ${detected.columns} x ${detected.rows} grid is larger than the current 12 x 8 calibration span`);
  }

  return {
    ok: issues.length === 0,
    areaRatio: Math.round(areaRatio * 1000) / 1000,
    outsideCornerCount,
    issues,
  };
}

export function meanCornerDelta(a: Point[], b: Point[]): number {
  const pairs = Math.min(a.length, b.length);
  if (pairs === 0) return 0;

  const total = a.slice(0, pairs).reduce((sum, point, index) => (
    sum + Math.hypot(point.x - b[index].x, point.y - b[index].y)
  ), 0);
  return total / pairs;
}

function polygonArea(points: Point[]): number {
  let area = 0;
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index];
    const next = points[(index + 1) % points.length];
    area += current.x * next.y - next.x * current.y;
  }
  return Math.abs(area) / 2;
}
