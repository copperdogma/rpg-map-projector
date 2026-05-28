import { applyHomography, solveHomography } from './homography';
import type { CalibrationState, Point, RenderOptions } from './types';

const PHYSICAL_GRID_COLOR = 'rgba(38, 58, 55, 0.28)';
const SOURCE_GRID_COLOR = 'rgba(28, 154, 112, 0.92)';
const SOURCE_GRID_SECONDARY = 'rgba(252, 177, 77, 0.9)';
const ANCHOR_COLOR = '#ff6b35';
const PROJECTOR_BACKGROUND = '#090a0b';

export function renderCalibrationCanvas(
  canvas: HTMLCanvasElement,
  state: CalibrationState,
  options: RenderOptions,
): void {
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width || state.projector.width));
  const height = Math.max(1, Math.round(rect.height || state.projector.height));
  const dpr = window.devicePixelRatio || 1;

  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  const context = canvas.getContext('2d');
  if (!context) return;
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  context.clearRect(0, 0, width, height);

  const scale = Math.min(width / state.projector.width, height / state.projector.height);
  const offset = {
    x: (width - state.projector.width * scale) / 2,
    y: (height - state.projector.height * scale) / 2,
  };

  context.save();
  if (options.background === 'projector') {
    context.fillStyle = PROJECTOR_BACKGROUND;
    context.fillRect(0, 0, width, height);
  } else if (options.background === 'synthetic-mat') {
    drawSyntheticMat(context, width, height);
  }

  context.translate(offset.x, offset.y);
  context.scale(scale, scale);
  context.globalAlpha = clamp(state.brightness, 0.25, 1.5);
  drawProjectedPattern(context, state, options);
  context.restore();
}

export function getProjectedPoint(state: CalibrationState, point: Point): Point {
  const matrix = solveHomography(
    state.anchors.map((anchor) => anchor.physical),
    state.anchors.map((anchor) => anchor.projector),
  );
  return applyHomography(matrix, point);
}

function drawProjectedPattern(
  context: CanvasRenderingContext2D,
  state: CalibrationState,
  options: RenderOptions,
): void {
  const bounds = getPhysicalBounds(state);
  const matrix = solveHomography(
    state.anchors.map((anchor) => anchor.physical),
    state.anchors.map((anchor) => anchor.projector),
  );
  const project = (point: Point) => applyHomography(matrix, point);

  drawProjectedQuad(context, state);

  if (state.showPhysicalGrid) {
    drawGrid(context, bounds, 1, PHYSICAL_GRID_COLOR, 1, project);
  }

  if (state.showSourceGrid) {
    const sourceStep = state.sourceSquareFeet === 10 ? 2 : 1;
    drawGrid(context, bounds, sourceStep, SOURCE_GRID_COLOR, 2, project);
    if (state.sourceSquareFeet === 10) {
      drawGrid(context, bounds, 1, SOURCE_GRID_SECONDARY, 0.75, project, true);
    }
  }

  drawAxes(context, bounds, project);

  if (state.showCalibrationPoints) {
    for (const anchor of state.anchors) {
      drawAnchor(context, anchor.projector, anchor.id, options.showLabels);
    }
  }
}

function drawProjectedQuad(context: CanvasRenderingContext2D, state: CalibrationState): void {
  const [a, b, c, d] = state.anchors.map((anchor) => anchor.projector);
  context.save();
  context.beginPath();
  context.moveTo(a.x, a.y);
  context.lineTo(b.x, b.y);
  context.lineTo(c.x, c.y);
  context.lineTo(d.x, d.y);
  context.closePath();
  context.fillStyle = 'rgba(255, 255, 255, 0.045)';
  context.strokeStyle = 'rgba(255, 255, 255, 0.48)';
  context.lineWidth = 2;
  context.fill();
  context.stroke();
  context.restore();
}

function drawGrid(
  context: CanvasRenderingContext2D,
  bounds: ReturnType<typeof getPhysicalBounds>,
  step: number,
  color: string,
  lineWidth: number,
  project: (point: Point) => Point,
  dashed = false,
): void {
  context.save();
  context.strokeStyle = color;
  context.lineWidth = lineWidth;
  if (dashed) context.setLineDash([8, 8]);

  for (let x = bounds.minX; x <= bounds.maxX + 0.0001; x += step) {
    const start = project({ x, y: bounds.minY });
    const end = project({ x, y: bounds.maxY });
    context.beginPath();
    context.moveTo(start.x, start.y);
    context.lineTo(end.x, end.y);
    context.stroke();
  }

  for (let y = bounds.minY; y <= bounds.maxY + 0.0001; y += step) {
    const start = project({ x: bounds.minX, y });
    const end = project({ x: bounds.maxX, y });
    context.beginPath();
    context.moveTo(start.x, start.y);
    context.lineTo(end.x, end.y);
    context.stroke();
  }

  context.restore();
}

function drawAxes(
  context: CanvasRenderingContext2D,
  bounds: ReturnType<typeof getPhysicalBounds>,
  project: (point: Point) => Point,
): void {
  const topLeft = project({ x: bounds.minX, y: bounds.minY });
  const topRight = project({ x: bounds.maxX, y: bounds.minY });
  const bottomLeft = project({ x: bounds.minX, y: bounds.maxY });

  context.save();
  context.lineWidth = 4;
  context.strokeStyle = 'rgba(255, 255, 255, 0.8)';
  context.beginPath();
  context.moveTo(topLeft.x, topLeft.y);
  context.lineTo(topRight.x, topRight.y);
  context.moveTo(topLeft.x, topLeft.y);
  context.lineTo(bottomLeft.x, bottomLeft.y);
  context.stroke();
  context.restore();
}

function drawAnchor(
  context: CanvasRenderingContext2D,
  point: Point,
  label: string,
  showLabel: boolean,
): void {
  context.save();
  context.fillStyle = ANCHOR_COLOR;
  context.strokeStyle = '#ffffff';
  context.lineWidth = 2;
  context.beginPath();
  context.arc(point.x, point.y, 10, 0, Math.PI * 2);
  context.fill();
  context.stroke();

  context.beginPath();
  context.moveTo(point.x - 20, point.y);
  context.lineTo(point.x + 20, point.y);
  context.moveTo(point.x, point.y - 20);
  context.lineTo(point.x, point.y + 20);
  context.stroke();

  if (showLabel) {
    context.font = '600 18px system-ui, sans-serif';
    context.fillStyle = '#ffffff';
    context.fillText(label, point.x + 16, point.y - 14);
  }
  context.restore();
}

function drawSyntheticMat(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
): void {
  context.fillStyle = '#f5f1e8';
  context.fillRect(0, 0, width, height);

  const step = Math.max(28, Math.min(width, height) / 18);
  context.strokeStyle = 'rgba(51, 64, 56, 0.2)';
  context.lineWidth = 1;
  for (let x = 0; x <= width; x += step) {
    context.beginPath();
    context.moveTo(x, 0);
    context.lineTo(x, height);
    context.stroke();
  }
  for (let y = 0; y <= height; y += step) {
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
  }

  context.fillStyle = 'rgba(71, 60, 44, 0.1)';
  context.fillRect(width * 0.18, height * 0.24, width * 0.32, height * 0.18);
  context.fillRect(width * 0.56, height * 0.44, width * 0.25, height * 0.22);
}

function getPhysicalBounds(state: CalibrationState): {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
} {
  const xs = state.anchors.map((anchor) => anchor.physical.x);
  const ys = state.anchors.map((anchor) => anchor.physical.y);
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}
