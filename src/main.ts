import './styles.css';
import {
  cloneState,
  createStateChannel,
  defaultState,
  nudgeAnchors,
  readState,
  rotateAnchors,
  scaleAnchors,
} from './calibration/state';
import { detectGridFromImage } from './calibration/gridDetection';
import { renderCalibrationCanvas } from './calibration/render';
import { applyHomography, solveHomography } from './calibration/homography';
import { sampleImages } from './calibration/sampleImages';
import {
  evaluateDetectedGridForAutoAlign,
  mapDetectedGridToAnchors,
  meanCornerDelta,
} from './calibration/detectedGridProjection';
import type { CalibrationAnchor, DetectedGrid, Point, SourceSquareFeet } from './calibration/types';

let state = readState();
let cameraActive = false;
let stream: MediaStream | null = null;
let loadedSampleImage: HTMLImageElement | null = null;
let uploadedObjectUrl: string | null = null;
let dragCornerIndex: number | null = null;

const app = document.querySelector<HTMLDivElement>('#app');
if (!app) throw new Error('Missing app root');

const sampleOptions = sampleImages
  .map((sample, index) => `<option value="${index}">${sample.label}</option>`)
  .join('');

app.innerHTML = `
  <main class="app-shell">
    <header class="topbar">
      <div>
        <h1>Calibration Projection Spike</h1>
        <p>Auto-first mat-grid detection workbench for Story 001.</p>
      </div>
      <div class="topbar-actions">
        <a class="button primary" href="/projector.html" target="_blank" rel="noreferrer">Open Projector View</a>
        <a class="button" href="/labeler.html">Label Fixtures</a>
        <button class="button" id="reset-state" type="button">Reset</button>
      </div>
    </header>

    <section class="workspace">
      <section class="preview-column" aria-label="Calibration preview">
        <div class="surface-title">
          <div>
            <h2>Camera / Mat Preview</h2>
            <p id="preview-mode">Synthetic mat preview</p>
          </div>
          <button class="button" id="camera-toggle" type="button">Start Camera</button>
        </div>
        <div class="preview-stage">
          <video id="camera-video" muted playsinline></video>
          <canvas id="controller-preview" aria-label="Controller calibration preview"></canvas>
        </div>
        <p class="hint">
          First run auto detection on a camera frame or false input. If it misses, drag the orange corner handles directly on the preview.
        </p>
      </section>

      <section class="controls-column" aria-label="Calibration controls">
        <section class="panel">
          <div class="panel-heading">
            <h2>Auto Grid Detection</h2>
            <p>Load a false camera input, then attempt to detect the battle-mat grid from the image.</p>
          </div>
          <div class="control-grid">
            <label>
              <span>Sample image</span>
              <select id="sample-image">${sampleOptions}</select>
            </label>
            <label>
              <span>Upload image</span>
              <input id="image-upload" type="file" accept="image/*" />
            </label>
          </div>
          <div class="button-row">
            <button class="button primary" id="auto-detect-grid" type="button">Auto Detect Grid</button>
            <button class="button" id="apply-detected-grid" type="button">Apply To Projector</button>
            <button class="button" id="clear-detected-grid" type="button">Clear Image</button>
          </div>
          <p class="detection-status" id="detection-status">No image analyzed yet.</p>
          <p class="alignment-status" id="alignment-status">Projection not aligned to a detected grid yet.</p>
        </section>

        <section class="panel">
          <div class="panel-heading">
            <h2>Fallback Projection Controls</h2>
            <p>Debug controls for the projected pattern. Primary correction should be direct handle dragging.</p>
          </div>

          <div class="segmented" role="group" aria-label="Source square scale">
            <button class="segment" data-source-scale="5" type="button">5 ft source</button>
            <button class="segment" data-source-scale="10" type="button">10 ft source</button>
          </div>

          <div class="control-grid">
            <label>
              <span>Nudge step</span>
              <input id="nudge-step" type="number" min="1" max="80" step="1" value="8" />
            </label>
            <label>
              <span>Brightness</span>
              <input id="brightness" type="range" min="0.35" max="1.4" step="0.05" />
            </label>
          </div>

          <div class="nudge-pad" aria-label="Nudge projected pattern">
            <button class="button" data-nudge="0,-1" type="button">Up</button>
            <button class="button" data-nudge="-1,0" type="button">Left</button>
            <button class="button" data-nudge="1,0" type="button">Right</button>
            <button class="button" data-nudge="0,1" type="button">Down</button>
          </div>

          <div class="button-row">
            <button class="button" data-scale="0.985" type="button">Scale -</button>
            <button class="button" data-scale="1.015" type="button">Scale +</button>
            <button class="button" data-rotate="-0.5" type="button">Rotate -</button>
            <button class="button" data-rotate="0.5" type="button">Rotate +</button>
          </div>

          <div class="checkbox-row">
            <label><input id="show-physical-grid" type="checkbox" /> Physical 1 in grid</label>
            <label><input id="show-source-grid" type="checkbox" /> Source grid</label>
            <label><input id="show-calibration-points" type="checkbox" /> Calibration points</label>
          </div>
        </section>

        <section class="panel">
          <div class="panel-heading">
            <h2>Anchor Pairs</h2>
            <p>Physical values are mat squares. Projector values are pixels in the projector view.</p>
          </div>
          <div class="anchor-table" id="anchor-table"></div>
        </section>

        <section class="panel">
          <div class="panel-heading">
            <h2>Session Evidence</h2>
            <p>Record the physical pass when projector/camera hardware is attached.</p>
          </div>
          <div class="control-grid">
            <label>
              <span>Setup time (minutes)</span>
              <input id="setup-minutes" type="number" min="0" step="0.5" />
            </label>
            <label>
              <span>Measured error (inches)</span>
              <input id="measured-error" type="number" min="0" step="0.05" />
            </label>
          </div>
          <label class="full-field">
            <span>Camera / projector placement notes</span>
            <textarea id="placement-notes" rows="3"></textarea>
          </label>
          <label class="full-field">
            <span>Failure modes</span>
            <textarea id="failure-modes" rows="3"></textarea>
          </label>
          <div class="button-row">
            <button class="button" id="export-evidence" type="button">Export Evidence JSON</button>
            <button class="button" id="copy-projector-url" type="button">Copy Projector URL</button>
          </div>
        </section>
      </section>
    </section>
  </main>
`;

const channel = createStateChannel((nextState) => {
  state = nextState;
  syncControls();
  render();
});

const previewCanvas = document.querySelector<HTMLCanvasElement>('#controller-preview')!;
const video = document.querySelector<HTMLVideoElement>('#camera-video')!;
if (!previewCanvas || !video) throw new Error('Missing preview elements');

bindControls();
syncControls();
publish();
void restoreDetectedImage();
render();

window.addEventListener('resize', render);

function bindControls(): void {
  document.querySelector('#reset-state')?.addEventListener('click', () => {
    state = cloneState(defaultState);
    syncControls();
    publish();
  });

  document.querySelector('#camera-toggle')?.addEventListener('click', () => {
    void toggleCamera();
  });

  document.querySelector('#auto-detect-grid')?.addEventListener('click', () => {
    void autoDetectSelectedImage();
  });

  document.querySelector('#apply-detected-grid')?.addEventListener('click', () => {
    if (!state.detectedGrid) {
      setAlignmentStatus('Run auto detection before applying a grid to the projector.');
      return;
    }
    applyDetectedGridToProjection('Projection anchors manually applied from the detected grid.', { force: true });
    publish();
  });

  document.querySelector('#clear-detected-grid')?.addEventListener('click', () => {
    loadedSampleImage = null;
    state.detectedGrid = null;
    state.projectionAlignment = null;
    state.projectionAlignmentIssue = null;
    setDetectionStatus('No image analyzed yet.');
    setAlignmentStatus('Projection not aligned to a detected grid yet.');
    publish();
  });

  document.querySelector<HTMLInputElement>('#image-upload')?.addEventListener('change', (event) => {
    const file = (event.target as HTMLInputElement).files?.[0];
    if (!file) return;
    if (uploadedObjectUrl) URL.revokeObjectURL(uploadedObjectUrl);
    uploadedObjectUrl = URL.createObjectURL(file);
    void runGridDetection(file.name, uploadedObjectUrl);
  });

  previewCanvas.addEventListener('pointerdown', (event) => {
    dragCornerIndex = findNearestDetectedCorner(event);
    if (dragCornerIndex !== null) {
      previewCanvas.setPointerCapture(event.pointerId);
      event.preventDefault();
    }
  });
  previewCanvas.addEventListener('pointermove', (event) => {
    if (dragCornerIndex === null || !state.detectedGrid) return;
    const point = pointerToNaturalPoint(event);
    if (!point) return;
    state.detectedGrid.corners[dragCornerIndex] = point;
    state.detectedGrid.message = 'Manual corner correction applied after auto detection.';
    applyDetectedGridToProjection('Projection anchors updated from manual corner correction.', { force: true });
    channel.publish(state);
    syncControls();
    render();
  });
  previewCanvas.addEventListener('pointerup', (event) => {
    if (dragCornerIndex !== null) {
      previewCanvas.releasePointerCapture(event.pointerId);
      dragCornerIndex = null;
    }
  });

  document.querySelectorAll<HTMLButtonElement>('[data-source-scale]').forEach((button) => {
    button.addEventListener('click', () => {
      state.sourceSquareFeet = Number(button.dataset.sourceScale) as SourceSquareFeet;
      publish();
    });
  });

  document.querySelectorAll<HTMLButtonElement>('[data-nudge]').forEach((button) => {
    button.addEventListener('click', () => {
      const [x, y] = button.dataset.nudge?.split(',').map(Number) ?? [0, 0];
      const step = readNudgeStep();
      state.anchors = nudgeAnchors(state.anchors, x * step, y * step);
      publish();
    });
  });

  document.querySelectorAll<HTMLButtonElement>('[data-scale]').forEach((button) => {
    button.addEventListener('click', () => {
      state.anchors = scaleAnchors(state.anchors, Number(button.dataset.scale));
      publish();
    });
  });

  document.querySelectorAll<HTMLButtonElement>('[data-rotate]').forEach((button) => {
    button.addEventListener('click', () => {
      state.anchors = rotateAnchors(state.anchors, Number(button.dataset.rotate));
      publish();
    });
  });

  bindCheckbox('#show-physical-grid', (checked) => { state.showPhysicalGrid = checked; });
  bindCheckbox('#show-source-grid', (checked) => { state.showSourceGrid = checked; });
  bindCheckbox('#show-calibration-points', (checked) => { state.showCalibrationPoints = checked; });

  document.querySelector<HTMLInputElement>('#brightness')?.addEventListener('input', (event) => {
    state.brightness = Number((event.target as HTMLInputElement).value);
    publish();
  });

  bindEvidenceField('#setup-minutes', (value) => { state.evidence.setupMinutes = Number(value) || 0; });
  bindEvidenceField('#measured-error', (value) => { state.evidence.measuredErrorInches = Number(value) || 0; });
  bindEvidenceField('#placement-notes', (value) => { state.evidence.placementNotes = value; });
  bindEvidenceField('#failure-modes', (value) => { state.evidence.failureModes = value; });

  document.querySelector('#export-evidence')?.addEventListener('click', () => {
    downloadEvidence();
  });

  document.querySelector('#copy-projector-url')?.addEventListener('click', () => {
    void navigator.clipboard?.writeText(new URL('/projector.html', window.location.href).href);
  });
}

function syncControls(): void {
  document.querySelectorAll<HTMLButtonElement>('[data-source-scale]').forEach((button) => {
    button.classList.toggle('selected', Number(button.dataset.sourceScale) === state.sourceSquareFeet);
  });

  setInputValue('#brightness', String(state.brightness));
  setInputChecked('#show-physical-grid', state.showPhysicalGrid);
  setInputChecked('#show-source-grid', state.showSourceGrid);
  setInputChecked('#show-calibration-points', state.showCalibrationPoints);
  setInputValue('#setup-minutes', String(state.evidence.setupMinutes));
  setInputValue('#measured-error', String(state.evidence.measuredErrorInches));
  setInputValue('#placement-notes', state.evidence.placementNotes);
  setInputValue('#failure-modes', state.evidence.failureModes);
  renderDetectionStatus();
  renderAlignmentStatus();
  syncApplyButton();
  renderAnchorTable();
}

function syncApplyButton(): void {
  const button = document.querySelector<HTMLButtonElement>('#apply-detected-grid');
  if (!button) return;

  button.disabled = !state.detectedGrid;
  button.classList.toggle('warning', Boolean(state.detectedGrid && state.projectionAlignmentIssue));
  button.textContent = state.detectedGrid && state.projectionAlignmentIssue
    ? 'Force Apply Candidate'
    : 'Apply To Projector';
}

function renderAnchorTable(): void {
  const table = document.querySelector<HTMLDivElement>('#anchor-table');
  if (!table) return;

  table.innerHTML = `
    <div class="anchor-row anchor-header">
      <span>Point</span>
      <span>Mat X</span>
      <span>Mat Y</span>
      <span>Projector X</span>
      <span>Projector Y</span>
    </div>
    ${state.anchors.map((anchor) => anchorRow(anchor)).join('')}
  `;

  table.querySelectorAll<HTMLInputElement>('input[data-anchor]').forEach((input) => {
    input.addEventListener('input', () => {
      const id = input.dataset.anchor as CalibrationAnchor['id'];
      const field = input.dataset.field;
      const anchor = state.anchors.find((item) => item.id === id);
      if (!anchor || !field) return;

      const value = Number(input.value);
      if (!Number.isFinite(value)) return;

      if (field === 'physical.x') anchor.physical.x = value;
      if (field === 'physical.y') anchor.physical.y = value;
      if (field === 'projector.x') anchor.projector.x = value;
      if (field === 'projector.y') anchor.projector.y = value;
      publish();
    });
  });
}

function anchorRow(anchor: CalibrationAnchor): string {
  return `
    <div class="anchor-row">
      <strong>${anchor.id}</strong>
      <input data-anchor="${anchor.id}" data-field="physical.x" type="number" step="0.5" value="${format(anchor.physical.x)}" />
      <input data-anchor="${anchor.id}" data-field="physical.y" type="number" step="0.5" value="${format(anchor.physical.y)}" />
      <input data-anchor="${anchor.id}" data-field="projector.x" type="number" step="1" value="${format(anchor.projector.x)}" />
      <input data-anchor="${anchor.id}" data-field="projector.y" type="number" step="1" value="${format(anchor.projector.y)}" />
    </div>
  `;
}

function render(): void {
  const mode = document.querySelector<HTMLParagraphElement>('#preview-mode');
  if (mode) {
    mode.textContent = loadedSampleImage
      ? 'False camera input with detected grid overlay'
      : cameraActive ? 'Live camera preview with projected overlay' : 'Synthetic mat preview';
  }

  if (loadedSampleImage) {
    renderSampleImagePreview();
    return;
  }

  renderCalibrationCanvas(previewCanvas, state, {
    background: cameraActive ? 'transparent' : 'synthetic-mat',
    showLabels: true,
  });
}

function publish(): void {
  channel.publish(state);
  syncControls();
  render();
}

async function toggleCamera(): Promise<void> {
  if (cameraActive) {
    stream?.getTracks().forEach((track) => track.stop());
    stream = null;
    cameraActive = false;
    video.srcObject = null;
    video.classList.remove('active');
    setButtonText('#camera-toggle', 'Start Camera');
    render();
    return;
  }

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: {
        facingMode: 'environment',
        width: { ideal: 1280 },
        height: { ideal: 720 },
      },
      audio: false,
    });
    video.srcObject = stream;
    await video.play();
    cameraActive = true;
    video.classList.add('active');
    setButtonText('#camera-toggle', 'Stop Camera');
    render();
  } catch (error) {
    cameraActive = false;
    window.alert(`Camera unavailable: ${(error as Error).message}`);
  }
}

async function autoDetectSelectedImage(): Promise<void> {
  const select = document.querySelector<HTMLSelectElement>('#sample-image');
  const sample = sampleImages[Number(select?.value ?? 0)] ?? sampleImages[0];
  await runGridDetection(sample.label, sample.url);
}

async function runGridDetection(sourceName: string, sourceUrl: string): Promise<void> {
  try {
    state.detectedGrid = null;
    state.projectionAlignment = null;
    state.projectionAlignmentIssue = null;
    setDetectionStatus('Analyzing image...');
    setAlignmentStatus('Projection not aligned to a detected grid yet.');
    channel.publish(state);
    render();
    loadedSampleImage = await loadImage(sourceUrl);
    state.detectedGrid = await detectGridFromImage(loadedSampleImage, sourceName, sourceUrl);
    applyDetectedGridToProjection('Auto-aligned projection anchors from detected grid bounds.');
    publish();
  } catch (error) {
    state.detectedGrid = null;
    state.projectionAlignment = null;
    state.projectionAlignmentIssue = null;
    channel.publish(state);
    render();
    setDetectionStatus(`Detection failed: ${(error as Error).message}`);
    setAlignmentStatus('Projection not aligned to a detected grid yet.');
  }
}

async function restoreDetectedImage(): Promise<void> {
  if (!state.detectedGrid) return;
  try {
    loadedSampleImage = await loadImage(state.detectedGrid.sourceUrl);
    render();
  } catch {
    state.detectedGrid = null;
    render();
  }
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.decoding = 'async';
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error(`Could not load ${url}`));
    image.src = url;
  });
}

function renderSampleImagePreview(): void {
  if (!loadedSampleImage) return;
  const rect = previewCanvas.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  const dpr = window.devicePixelRatio || 1;
  previewCanvas.width = Math.round(width * dpr);
  previewCanvas.height = Math.round(height * dpr);
  const context = previewCanvas.getContext('2d');
  if (!context) return;
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  context.clearRect(0, 0, width, height);
  context.fillStyle = '#151714';
  context.fillRect(0, 0, width, height);

  const fit = imageFit(loadedSampleImage, width, height);
  context.drawImage(loadedSampleImage, fit.x, fit.y, fit.width, fit.height);
  if (state.detectedGrid) {
    drawDetectedGrid(context, state.detectedGrid, fit, state.anchors, Boolean(state.projectionAlignment));
  }
}

function drawDetectedGrid(
  context: CanvasRenderingContext2D,
  detected: DetectedGrid,
  fit: ReturnType<typeof imageFit>,
  anchors: CalibrationAnchor[],
  autoAligned: boolean,
): void {
  const corners = detected.corners.map((corner) => naturalToCanvas(corner, fit)) as [Point, Point, Point, Point];
  const matrix = solveHomography(
    anchors.map((anchor) => anchor.physical),
    corners,
  );
  const project = (point: Point) => applyHomography(matrix, point);
  const bounds = physicalBounds(anchors);

  context.save();
  if (autoAligned) {
    context.strokeStyle = 'rgba(15, 138, 98, 0.95)';
    context.lineWidth = 1.5;
    for (let x = bounds.minX; x <= bounds.maxX + 0.0001; x += 1) {
      const top = project({ x, y: bounds.minY });
      const bottom = project({ x, y: bounds.maxY });
      context.beginPath();
      context.moveTo(top.x, top.y);
      context.lineTo(bottom.x, bottom.y);
      context.stroke();
    }
    for (let y = bounds.minY; y <= bounds.maxY + 0.0001; y += 1) {
      const left = project({ x: bounds.minX, y });
      const right = project({ x: bounds.maxX, y });
      context.beginPath();
      context.moveTo(left.x, left.y);
      context.lineTo(right.x, right.y);
      context.stroke();
    }
  }

  context.strokeStyle = autoAligned ? 'rgba(255, 255, 255, 0.92)' : 'rgba(255, 177, 77, 0.95)';
  context.lineWidth = 3;
  if (!autoAligned) context.setLineDash([12, 8]);
  context.beginPath();
  corners.forEach((corner, index) => {
    if (index === 0) context.moveTo(corner.x, corner.y);
    else context.lineTo(corner.x, corner.y);
  });
  context.closePath();
  context.stroke();

  corners.forEach((corner, index) => {
    context.setLineDash([]);
    context.fillStyle = autoAligned ? '#ff6b35' : '#f5a623';
    context.strokeStyle = '#ffffff';
    context.lineWidth = 2;
    context.beginPath();
    context.arc(corner.x, corner.y, 8, 0, Math.PI * 2);
    context.fill();
    context.stroke();
    context.fillStyle = '#ffffff';
    context.font = '700 13px system-ui, sans-serif';
    context.fillText(String.fromCharCode(65 + index), corner.x + 11, corner.y - 9);
  });
  context.restore();
}

function findNearestDetectedCorner(event: PointerEvent): number | null {
  if (!loadedSampleImage || !state.detectedGrid) return null;
  const rect = previewCanvas.getBoundingClientRect();
  const fit = imageFit(loadedSampleImage, rect.width, rect.height);
  const pointer = { x: event.clientX - rect.left, y: event.clientY - rect.top };
  let nearestIndex: number | null = null;
  let nearestDistance = 24;

  state.detectedGrid.corners.forEach((corner, index) => {
    const canvasPoint = naturalToCanvas(corner, fit);
    const distance = Math.hypot(canvasPoint.x - pointer.x, canvasPoint.y - pointer.y);
    if (distance < nearestDistance) {
      nearestIndex = index;
      nearestDistance = distance;
    }
  });

  return nearestIndex;
}

function pointerToNaturalPoint(event: PointerEvent): Point | null {
  if (!loadedSampleImage) return null;
  const rect = previewCanvas.getBoundingClientRect();
  const fit = imageFit(loadedSampleImage, rect.width, rect.height);
  const x = (event.clientX - rect.left - fit.x) / fit.scale;
  const y = (event.clientY - rect.top - fit.y) / fit.scale;
  return {
    x: Math.max(0, Math.min(loadedSampleImage.naturalWidth, x)),
    y: Math.max(0, Math.min(loadedSampleImage.naturalHeight, y)),
  };
}

function imageFit(image: HTMLImageElement, width: number, height: number): {
  x: number;
  y: number;
  width: number;
  height: number;
  scale: number;
} {
  const scale = Math.min(width / image.naturalWidth, height / image.naturalHeight);
  const imageWidth = image.naturalWidth * scale;
  const imageHeight = image.naturalHeight * scale;
  return {
    x: (width - imageWidth) / 2,
    y: (height - imageHeight) / 2,
    width: imageWidth,
    height: imageHeight,
    scale,
  };
}

function naturalToCanvas(point: Point, fit: ReturnType<typeof imageFit>): Point {
  return {
    x: fit.x + point.x * fit.scale,
    y: fit.y + point.y * fit.scale,
  };
}

function physicalBounds(anchors: CalibrationAnchor[]): {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
} {
  const xs = anchors.map((anchor) => anchor.physical.x);
  const ys = anchors.map((anchor) => anchor.physical.y);
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
  };
}

function renderDetectionStatus(): void {
  if (!state.detectedGrid) {
    setDetectionStatus('No image analyzed yet.', 'neutral');
    return;
  }
  const confidence = Math.round(state.detectedGrid.confidence * 100);
  const latticeText = state.detectedGrid.latticeScore !== undefined
    ? `, ${Math.round(state.detectedGrid.latticeScore * 100)}% lattice support`
    : '';
  const statusType = state.projectionAlignmentIssue ? 'warning' : 'success';
  const prefix = state.projectionAlignmentIssue ? 'Candidate only; not applied. ' : '';
  setDetectionStatus(
    `${prefix}${state.detectedGrid.sourceName}: ${confidence}% confidence${latticeText}. ${state.detectedGrid.message}`,
    statusType,
  );
}

function applyDetectedGridToProjection(message: string, options: { force?: boolean } = {}): void {
  if (!state.detectedGrid) {
    state.projectionAlignment = null;
    state.projectionAlignmentIssue = null;
    return;
  }
  const quality = evaluateDetectedGridForAutoAlign(state.detectedGrid);
  if (!quality.ok && !options.force) {
    state.projectionAlignment = null;
    state.projectionAlignmentIssue = `Manual correction required: ${quality.issues.join('; ')}. Projector anchors unchanged.`;
    return;
  }

  const previousProjectorCorners = state.anchors.map((anchor) => anchor.projector);
  state.anchors = mapDetectedGridToAnchors(state.detectedGrid, state.anchors, state.projector);
  state.projectionAlignmentIssue = null;
  state.projectionAlignment = {
    source: 'detected-grid',
    mode: 'simulated-image-fit',
    alignedAt: new Date().toISOString(),
    meanCornerDeltaPixels: Math.round(meanCornerDelta(previousProjectorCorners, state.anchors.map((anchor) => anchor.projector)) * 10) / 10,
    message: quality.ok ? message : `${message} after manual override.`,
  };
}

function renderAlignmentStatus(): void {
  if (!state.projectionAlignment) {
    setAlignmentStatus(
      state.projectionAlignmentIssue ?? 'Projection not aligned to a detected grid yet.',
      state.projectionAlignmentIssue ? 'warning' : 'neutral',
    );
    return;
  }

  setAlignmentStatus(
    `${state.projectionAlignment.message} Simulated camera-to-projector fit; physical camera delta is still separate.`,
    'success',
  );
}

function setDetectionStatus(message: string, type: 'neutral' | 'success' | 'warning' = 'neutral'): void {
  const status = document.querySelector<HTMLParagraphElement>('#detection-status');
  if (!status) return;
  status.textContent = message;
  setStatusType(status, type);
}

function setAlignmentStatus(message: string, type: 'neutral' | 'success' | 'warning' = 'neutral'): void {
  const status = document.querySelector<HTMLParagraphElement>('#alignment-status');
  if (!status) return;
  status.textContent = message;
  setStatusType(status, type);
}

function setStatusType(element: HTMLElement, type: 'neutral' | 'success' | 'warning'): void {
  element.classList.toggle('status-success', type === 'success');
  element.classList.toggle('status-warning', type === 'warning');
  element.classList.toggle('status-neutral', type === 'neutral');
}

function bindCheckbox(selector: string, update: (checked: boolean) => void): void {
  document.querySelector<HTMLInputElement>(selector)?.addEventListener('change', (event) => {
    update((event.target as HTMLInputElement).checked);
    publish();
  });
}

function bindEvidenceField(selector: string, update: (value: string) => void): void {
  document.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector)?.addEventListener('input', (event) => {
    update((event.target as HTMLInputElement | HTMLTextAreaElement).value);
    channel.publish(state);
  });
}

function downloadEvidence(): void {
  const payload = {
    exportedAt: new Date().toISOString(),
    state,
  };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = `story-001-calibration-evidence-${new Date().toISOString().slice(0, 10)}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
}

function readNudgeStep(): number {
  const value = Number(document.querySelector<HTMLInputElement>('#nudge-step')?.value ?? 8);
  return Number.isFinite(value) ? value : 8;
}

function setInputValue(selector: string, value: string): void {
  const input = document.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector);
  if (input && input.value !== value) input.value = value;
}

function setInputChecked(selector: string, checked: boolean): void {
  const input = document.querySelector<HTMLInputElement>(selector);
  if (input) input.checked = checked;
}

function setButtonText(selector: string, text: string): void {
  const button = document.querySelector<HTMLButtonElement>(selector);
  if (button) button.textContent = text;
}

function format(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(2);
}
