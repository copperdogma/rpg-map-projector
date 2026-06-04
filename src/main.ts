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
import type {
  CalibrationAnchor,
  DetectedGrid,
  Point,
  ProjectorOutputMode,
  SourceSquareFeet,
} from './calibration/types';

let state = readState();
let cameraActive = false;
let stream: MediaStream | null = null;
let networkCameraActive = false;
let networkCameraCanvas: HTMLCanvasElement | null = null;
let activeNetworkCamera: NetworkCameraSource | null = null;
let networkCameraTimer: number | null = null;
let networkFrameInFlight = false;
let loadedSampleImage: HTMLImageElement | null = null;
let loadedImageKind: 'sample' | 'upload' | 'camera' | null = null;
let loadedImageSourceName = '';
let loadedImageSourceUrl = '';
let uploadedObjectUrl: string | null = null;
let dragCornerIndex: number | null = null;

const CAMERA_DEVICE_STORAGE_KEY = 'rpg-map-projector:selected-camera-device';
const NETWORK_CAMERA_PREFIX = 'network:';
const PROJECTOR_BLANK_CAPTURE_DELAY_MS = 700;
const NETWORK_DETECTION_CAPTURE_ATTEMPTS = 5;
const NETWORK_DETECTION_CAPTURE_RETRY_MS = 350;

interface NetworkCameraSource {
  id: string;
  label: string;
  baseUrl: string;
  rotationDegrees?: number;
  detectionCapturePath?: string;
}

interface FrameDiagnostics {
  meanLuma: number;
  contrast: number;
  quality: 'usable' | 'too-dark' | 'low-contrast';
}

interface GatewaySeedOption {
  label: string;
  grid: DetectedGrid;
}

let networkCameraSources: NetworkCameraSource[] = [];
let gatewaySeedOptions: GatewaySeedOption[] = [];

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
        </div>
        <div class="camera-controls" aria-label="Camera controls">
          <label>
            <span>Camera</span>
            <select id="camera-device">
              <option value="">Default camera</option>
            </select>
          </label>
          <button class="button" id="refresh-camera-devices" type="button">Refresh Cameras</button>
          <button class="button" id="camera-toggle" type="button">Start Camera</button>
          <button class="button primary" id="capture-camera-frame" type="button" disabled>Capture & Detect Frame</button>
          <button class="button primary" id="capture-clean-mat-frame" type="button" disabled>Blank & Capture Mat</button>
        </div>
        <div class="network-camera-controls" aria-label="Network camera tuning">
          <button class="button compact" id="camera-bright-preset" type="button" disabled>Boost Low Light</button>
          <button class="button compact" id="camera-default-preset" type="button" disabled>Camera Defaults</button>
          <span id="camera-control-status">Network camera controls unavailable.</span>
        </div>
        <div class="projector-mode-controls" aria-label="Projector output">
          <span>Projector output</span>
          <button class="segment" data-projector-mode="blank" type="button">Blank</button>
          <button class="segment" data-projector-mode="alignment" type="button">Alignment grid</button>
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
            <button class="button" id="gateway-seed-grid" type="button">Gateway Seed Candidate</button>
            <button class="button" id="seed-manual-grid" type="button">Manual Seed Handles</button>
            <button class="button" id="clear-detected-grid" type="button">Clear Image</button>
          </div>
          <p class="detection-status" id="detection-status">No image analyzed yet.</p>
          <div class="gateway-candidates" id="gateway-candidates" aria-label="Gateway seed candidates" hidden></div>
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
          <p class="camera-evidence" id="camera-evidence">No camera frame captured yet.</p>
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
void refreshCameraDevices();
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

  document.querySelector('#refresh-camera-devices')?.addEventListener('click', () => {
    void refreshCameraDevices();
  });

  document.querySelector('#camera-bright-preset')?.addEventListener('click', () => {
    void applyNetworkCameraPreset('bright-mat');
  });

  document.querySelector('#camera-default-preset')?.addEventListener('click', () => {
    void applyNetworkCameraPreset('default');
  });

  document.querySelector<HTMLSelectElement>('#camera-device')?.addEventListener('change', (event) => {
    window.localStorage.setItem(CAMERA_DEVICE_STORAGE_KEY, (event.target as HTMLSelectElement).value);
    syncNetworkCameraControls();
  });

  document.querySelector('#capture-camera-frame')?.addEventListener('click', () => {
    void captureCameraFrame();
  });

  document.querySelector('#capture-clean-mat-frame')?.addEventListener('click', () => {
    void captureCleanMatFrame();
  });

  document.querySelectorAll<HTMLButtonElement>('[data-projector-mode]').forEach((button) => {
    button.addEventListener('click', () => {
      state.projectorMode = button.dataset.projectorMode as ProjectorOutputMode;
      publish();
    });
  });

  video.addEventListener('loadedmetadata', () => {
    updateCameraEvidenceFromStream('');
    syncCameraButtons();
    renderCameraEvidence();
  });

  document.querySelector('#auto-detect-grid')?.addEventListener('click', () => {
    void autoDetectSelectedImage();
  });

  document.querySelector('#gateway-seed-grid')?.addEventListener('click', () => {
    void runGatewaySeedCandidate();
  });

  document.querySelector('#gateway-candidates')?.addEventListener('click', (event) => {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>('button[data-gateway-candidate-index]');
    if (!button) return;
    selectGatewaySeedOption(Number(button.dataset.gatewayCandidateIndex));
  });

  document.querySelector('#apply-detected-grid')?.addEventListener('click', () => {
    if (!state.detectedGrid) {
      setAlignmentStatus('Run auto detection before applying a grid to the projector.');
      return;
    }
    applyDetectedGridToProjection('Projection anchors manually applied from the detected grid.', { force: true });
    publish();
  });

  document.querySelector('#seed-manual-grid')?.addEventListener('click', () => {
    seedManualGridHandles();
  });

  document.querySelector('#clear-detected-grid')?.addEventListener('click', () => {
    loadedSampleImage = null;
    loadedImageKind = null;
    loadedImageSourceName = '';
    loadedImageSourceUrl = '';
    gatewaySeedOptions = [];
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
    void runGridDetection(file.name, uploadedObjectUrl, { kind: 'upload' });
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
  document.querySelectorAll<HTMLButtonElement>('[data-projector-mode]').forEach((button) => {
    button.classList.toggle('selected', button.dataset.projectorMode === state.projectorMode);
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
  renderCameraEvidence();
  syncNetworkCameraControls();
  renderGatewaySeedOptions();
  syncApplyButton();
  syncCameraButtons();
  syncManualSeedButton();
  renderAnchorTable();
}

function syncCameraButtons(): void {
  const disabled = !cameraActive || !stream || video.readyState < 2 || video.videoWidth <= 0 || video.videoHeight <= 0;
  document.querySelectorAll<HTMLButtonElement>('#capture-camera-frame, #capture-clean-mat-frame').forEach((button) => {
    button.disabled = disabled;
  });
}

function syncNetworkCameraControls(message?: string): void {
  const networkCamera = selectedNetworkCamera();
  const disabled = !networkCamera;
  document.querySelectorAll<HTMLButtonElement>('#camera-bright-preset, #camera-default-preset').forEach((button) => {
    button.disabled = disabled;
  });
  const status = document.querySelector<HTMLSpanElement>('#camera-control-status');
  if (status) {
    status.textContent = message ?? (networkCamera
      ? 'ESP32 tuning controls target the selected network camera.'
      : 'Network camera controls unavailable.');
  }
}

function syncManualSeedButton(): void {
  const seedButton = document.querySelector<HTMLButtonElement>('#seed-manual-grid');
  if (seedButton) seedButton.disabled = !loadedSampleImage;
  const gatewaySeedButton = document.querySelector<HTMLButtonElement>('#gateway-seed-grid');
  if (gatewaySeedButton) gatewaySeedButton.disabled = !loadedSampleImage;
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
      ? loadedImageKind === 'camera'
        ? 'Captured camera frame with detected grid overlay'
        : 'False camera input with detected grid overlay'
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
    stopCamera();
    setButtonText('#camera-toggle', 'Start Camera');
    syncCameraButtons();
    render();
    return;
  }

  try {
    const networkCamera = selectedNetworkCamera();
    if (networkCamera) {
      await startNetworkCamera(networkCamera);
      return;
    }

    stream = await navigator.mediaDevices.getUserMedia({
      video: cameraVideoConstraints(),
      audio: false,
    });
    video.srcObject = stream;
    await video.play();
    cameraActive = true;
    video.classList.add('active');
    setButtonText('#camera-toggle', 'Stop Camera');
    updateCameraEvidenceFromStream('');
    await refreshCameraDevices();
    syncCameraButtons();
    channel.publish(state);
    render();
  } catch (error) {
    cameraActive = false;
    syncCameraButtons();
    window.alert(`Camera unavailable: ${(error as Error).message}`);
  }
}

function stopCamera(): void {
  if (networkCameraTimer !== null) {
    window.clearInterval(networkCameraTimer);
    networkCameraTimer = null;
  }
  stream?.getTracks().forEach((track) => track.stop());
  stream = null;
  cameraActive = false;
  networkCameraActive = false;
  networkCameraCanvas = null;
  activeNetworkCamera = null;
  networkFrameInFlight = false;
  video.srcObject = null;
  video.classList.remove('active');
}

function cameraVideoConstraints(): MediaTrackConstraints {
  const deviceId = document.querySelector<HTMLSelectElement>('#camera-device')?.value;
  const base: MediaTrackConstraints = {
    width: { ideal: 1280 },
    height: { ideal: 720 },
  };

  return deviceId
    ? { ...base, deviceId: { exact: deviceId } }
    : { ...base, facingMode: { ideal: 'environment' } };
}

async function refreshCameraDevices(): Promise<void> {
  const select = document.querySelector<HTMLSelectElement>('#camera-device');
  if (!select) return;

  const preferredDeviceId = select.value || window.localStorage.getItem(CAMERA_DEVICE_STORAGE_KEY) || '';
  const devices = navigator.mediaDevices?.enumerateDevices
    ? (await navigator.mediaDevices.enumerateDevices()).filter((device) => device.kind === 'videoinput')
    : [];
  networkCameraSources = await fetchNetworkCameraSources();
  select.replaceChildren();
  select.append(optionForCamera('', 'Default camera'));

  devices.forEach((device, index) => {
    const label = device.label || `Camera ${index + 1}`;
    select.append(optionForCamera(device.deviceId, label));
  });

  networkCameraSources.forEach((camera) => {
    select.append(optionForCamera(networkCameraValue(camera.id), camera.label));
  });

  const preferredNetwork = preferredDeviceId.startsWith(NETWORK_CAMERA_PREFIX)
    && networkCameraSources.some((camera) => networkCameraValue(camera.id) === preferredDeviceId);
  if (preferredDeviceId && (devices.some((device) => device.deviceId === preferredDeviceId) || preferredNetwork)) {
    select.value = preferredDeviceId;
  }
}

function optionForCamera(value: string, label: string): HTMLOptionElement {
  const option = document.createElement('option');
  option.value = value;
  option.textContent = label;
  return option;
}

async function fetchNetworkCameraSources(): Promise<NetworkCameraSource[]> {
  try {
    const response = await fetch('/__network-cameras', { cache: 'no-store' });
    if (!response.ok) return [];
    const payload = await response.json() as { cameras?: NetworkCameraSource[] };
    return Array.isArray(payload.cameras)
      ? payload.cameras.filter((camera) => (
          camera
          && typeof camera.id === 'string'
          && typeof camera.label === 'string'
        ))
      : [];
  } catch {
    return [];
  }
}

function cameraRotationDegrees(camera: NetworkCameraSource): 0 | 90 | 180 | 270 {
  const degrees = Number(camera.rotationDegrees ?? 0);
  return degrees === 90 || degrees === 180 || degrees === 270 ? degrees : 0;
}

function selectedNetworkCamera(): NetworkCameraSource | null {
  const select = document.querySelector<HTMLSelectElement>('#camera-device');
  const value = select?.value ?? '';
  if (!value.startsWith(NETWORK_CAMERA_PREFIX)) return null;
  const id = value.slice(NETWORK_CAMERA_PREFIX.length);
  return networkCameraSources.find((camera) => camera.id === id) ?? null;
}

function networkCameraValue(id: string): string {
  return `${NETWORK_CAMERA_PREFIX}${id}`;
}

async function startNetworkCamera(camera: NetworkCameraSource): Promise<void> {
  stopCamera();
  const canvas = document.createElement('canvas');
  await drawNetworkCameraFrame(camera, canvas, { waitForFreshFrame: true });
  networkCameraCanvas = canvas;
  activeNetworkCamera = camera;
  stream = canvas.captureStream(4);
  video.srcObject = stream;
  await video.play();
  cameraActive = true;
  networkCameraActive = true;
  video.classList.add('active');
  setButtonText('#camera-toggle', 'Stop Camera');
  updateCameraEvidenceFromStream('');
  syncCameraButtons();
  channel.publish(state);
  render();

  networkCameraTimer = window.setInterval(() => {
    void drawNetworkCameraFrame(camera, canvas);
  }, 500);
}

async function drawNetworkCameraFrame(
  camera: NetworkCameraSource,
  canvas: HTMLCanvasElement,
  options: { waitForFreshFrame?: boolean; captureMode?: 'preview' | 'detection' } = {},
): Promise<FrameDiagnostics | null> {
  if (networkFrameInFlight && !options.waitForFreshFrame) return null;
  while (networkFrameInFlight) {
    await delay(25);
  }
  networkFrameInFlight = true;
  try {
    const mode = options.captureMode === 'detection' ? '&mode=detection' : '';
    const attempts = options.captureMode === 'detection' ? NETWORK_DETECTION_CAPTURE_ATTEMPTS : 1;
    let diagnostics: FrameDiagnostics | null = null;

    for (let attempt = 0; attempt < attempts; attempt += 1) {
      const response = await fetch(`/__network-camera-capture?id=${encodeURIComponent(camera.id)}${mode}&t=${Date.now()}`, {
        cache: 'no-store',
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      const image = await loadImageBlob(await response.blob());
      const rotationDegrees = cameraRotationDegrees(camera);
      const isSideways = rotationDegrees === 90 || rotationDegrees === 270;
      canvas.width = isSideways ? image.naturalHeight : image.naturalWidth;
      canvas.height = isSideways ? image.naturalWidth : image.naturalHeight;
      const context = canvas.getContext('2d');
      if (!context) throw new Error('Network camera canvas unavailable.');
      drawNetworkCameraImage(context, image, rotationDegrees);
      diagnostics = measureFrameDiagnostics(context, canvas.width, canvas.height);
      if (options.captureMode !== 'detection' || diagnostics.quality === 'usable') break;
      if (attempt < attempts - 1) await delay(NETWORK_DETECTION_CAPTURE_RETRY_MS);
    }
    syncCameraButtons();
    return diagnostics;
  } finally {
    networkFrameInFlight = false;
  }
}

function drawNetworkCameraImage(
  context: CanvasRenderingContext2D,
  image: HTMLImageElement,
  rotationDegrees: 0 | 90 | 180 | 270,
): void {
  context.save();
  if (rotationDegrees === 90) {
    context.translate(image.naturalHeight, 0);
    context.rotate(Math.PI / 2);
  } else if (rotationDegrees === 180) {
    context.translate(image.naturalWidth, image.naturalHeight);
    context.rotate(Math.PI);
  } else if (rotationDegrees === 270) {
    context.translate(0, image.naturalWidth);
    context.rotate(-Math.PI / 2);
  }
  context.drawImage(image, 0, 0);
  context.restore();
}

function loadImageBlob(blob: Blob): Promise<HTMLImageElement> {
  return new Promise((resolveImage, reject) => {
    const image = new Image();
    const objectUrl = URL.createObjectURL(blob);
    image.onload = () => {
      URL.revokeObjectURL(objectUrl);
      resolveImage(image);
    };
    image.onerror = () => {
      URL.revokeObjectURL(objectUrl);
      reject(new Error('Network camera returned an undecodable image.'));
    };
    image.src = objectUrl;
  });
}

async function captureCameraFrame(): Promise<void> {
  try {
    await refreshActiveNetworkCameraFrame('detection');
  } catch (error) {
    setDetectionStatus(`Camera refresh failed: ${errorMessage(error)}`, 'warning');
    return;
  }

  const frame = captureVideoStill('camera-frame');
  if (!frame) return;

  updateCameraEvidenceFromStream(frame.sourceName, frame.capturedAt.toISOString(), frame.diagnostics);
  syncControls();
  await delay(0);
  await runGridDetection(frame.sourceName, frame.dataUrl, { kind: 'camera' });
}

async function captureCleanMatFrame(): Promise<void> {
  if (!canCaptureCameraFrame()) {
    window.alert('Start the camera before capturing a clean mat frame.');
    return;
  }

  const restoreMode: ProjectorOutputMode = 'alignment';
  state.projectorMode = 'blank';
  setDetectionStatus('Projector blanking for clean mat capture...');
  channel.publish(state);
  syncControls();
  render();

  let frame: ReturnType<typeof captureVideoStill> = null;
  try {
    await delay(PROJECTOR_BLANK_CAPTURE_DELAY_MS);
    await refreshActiveNetworkCameraFrame('detection');
    frame = captureVideoStill('clean-mat-frame');
  } catch (error) {
    setDetectionStatus(`Clean mat capture failed: ${errorMessage(error)}`, 'warning');
  } finally {
    state.projectorMode = restoreMode;
    channel.publish(state);
    syncControls();
    render();
  }
  if (!frame) return;

  updateCameraEvidenceFromStream(frame.sourceName, frame.capturedAt.toISOString(), frame.diagnostics);
  syncControls();
  await runGridDetection(frame.sourceName, frame.dataUrl, { kind: 'camera' });
}

function canCaptureCameraFrame(): boolean {
  return Boolean(stream && cameraActive && video.videoWidth > 0 && video.videoHeight > 0);
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

async function refreshActiveNetworkCameraFrame(captureMode: 'preview' | 'detection' = 'preview'): Promise<void> {
  if (!networkCameraActive || !activeNetworkCamera || !networkCameraCanvas) return;
  const diagnostics = await drawNetworkCameraFrame(activeNetworkCamera, networkCameraCanvas, { waitForFreshFrame: true, captureMode });
  if (captureMode === 'detection' && diagnostics?.quality !== 'usable') {
    setDetectionStatus(
      `Network camera frame is ${diagnostics?.quality ?? 'unavailable'} after warm-up; detection may refuse it.`,
      'warning',
    );
  }
  if (captureMode === 'detection') await delay(100);
}

async function applyNetworkCameraPreset(name: 'bright-mat' | 'default'): Promise<void> {
  const camera = selectedNetworkCamera();
  if (!camera) {
    syncNetworkCameraControls('Select an ESP32 network camera before applying a preset.');
    return;
  }

  const label = name === 'bright-mat' ? 'Boost Low Light' : 'Camera Defaults';
  syncNetworkCameraControls(`Applying ${label}...`);
  try {
    const response = await fetch(`/__network-camera-preset?id=${encodeURIComponent(camera.id)}&name=${encodeURIComponent(name)}`, {
      cache: 'no-store',
    });
    if (!response.ok) throw new Error(await response.text());
    if (networkCameraActive) {
      await refreshActiveNetworkCameraFrame('preview');
      render();
    }
    syncNetworkCameraControls(`${label} applied.`);
  } catch (error) {
    syncNetworkCameraControls(`${label} failed: ${errorMessage(error)}`);
  }
}

function captureVideoStill(prefix: string): {
  sourceName: string;
  dataUrl: string;
  capturedAt: Date;
  diagnostics: FrameDiagnostics;
} | null {
  if (!stream || !cameraActive || video.videoWidth <= 0 || video.videoHeight <= 0) {
    window.alert('Start the camera before capturing a calibration frame.');
    return null;
  }

  const canvas = document.createElement('canvas');
  const sourceCanvas = networkCameraActive ? networkCameraCanvas : null;
  canvas.width = sourceCanvas?.width || video.videoWidth;
  canvas.height = sourceCanvas?.height || video.videoHeight;
  const context = canvas.getContext('2d');
  if (!context) {
    window.alert('Could not capture the current camera frame.');
    return null;
  }

  if (sourceCanvas) context.drawImage(sourceCanvas, 0, 0, canvas.width, canvas.height);
  else context.drawImage(video, 0, 0, canvas.width, canvas.height);
  const capturedAt = new Date();
  const sourceName = `${prefix}-${capturedAt.toISOString().replace(/[:.]/g, '-')}.jpg`;
  const diagnostics = measureFrameDiagnostics(context, canvas.width, canvas.height);
  const dataUrl = canvas.toDataURL('image/jpeg', 0.9);
  return { sourceName, dataUrl, capturedAt, diagnostics };
}

function measureFrameDiagnostics(
  context: CanvasRenderingContext2D,
  width: number,
  height: number,
): FrameDiagnostics {
  const data = context.getImageData(0, 0, width, height).data;
  const step = Math.max(1, Math.floor(Math.sqrt((width * height) / 2400)));
  let count = 0;
  let sum = 0;
  let sumSquares = 0;
  for (let y = 0; y < height; y += step) {
    for (let x = 0; x < width; x += step) {
      const offset = (y * width + x) * 4;
      const luma = data[offset] * 0.299 + data[offset + 1] * 0.587 + data[offset + 2] * 0.114;
      sum += luma;
      sumSquares += luma * luma;
      count += 1;
    }
  }
  const meanLuma = count > 0 ? sum / count : 0;
  const variance = count > 0 ? Math.max(0, sumSquares / count - meanLuma * meanLuma) : 0;
  const contrast = Math.sqrt(variance);
  return {
    meanLuma: Math.round(meanLuma * 10) / 10,
    contrast: Math.round(contrast * 10) / 10,
    quality: classifyFrameQuality(meanLuma, contrast),
  };
}

function classifyFrameQuality(
  meanLuma: number,
  contrast: number,
): FrameDiagnostics['quality'] {
  if (meanLuma < 24 && contrast < 18) return 'too-dark';
  if (contrast < 7) return 'low-contrast';
  return 'usable';
}

function updateCameraEvidenceFromStream(
  capturedFrameName: string,
  capturedAt = '',
  diagnostics?: FrameDiagnostics,
): void {
  const track = stream?.getVideoTracks()[0];
  const settings = track?.getSettings();
  const selectedLabel = selectedCameraLabel();
  state.evidence.camera = {
    deviceLabel: selectedLabel !== 'Default camera' ? selectedLabel : track?.label || selectedLabel,
    streamWidth: Number((networkCameraActive && networkCameraCanvas?.width) || settings?.width || video.videoWidth || 0),
    streamHeight: Number((networkCameraActive && networkCameraCanvas?.height) || settings?.height || video.videoHeight || 0),
    capturedFrameName: capturedFrameName || state.evidence.camera?.capturedFrameName || '',
    capturedAt: capturedAt || state.evidence.camera?.capturedAt || '',
    frameMeanLuma: diagnostics?.meanLuma ?? state.evidence.camera?.frameMeanLuma,
    frameContrast: diagnostics?.contrast ?? state.evidence.camera?.frameContrast,
    frameQuality: diagnostics?.quality ?? state.evidence.camera?.frameQuality,
    frameRotationDegrees: activeNetworkCamera ? cameraRotationDegrees(activeNetworkCamera) : undefined,
  };
}

function selectedCameraLabel(): string {
  const select = document.querySelector<HTMLSelectElement>('#camera-device');
  return select?.selectedOptions[0]?.textContent || 'Default camera';
}

function seedManualGridHandles(): void {
  if (!loadedSampleImage) {
    window.alert('Capture or load a frame before placing manual grid handles.');
    return;
  }

  gatewaySeedOptions = [];
  state.detectedGrid = {
    sourceName: loadedImageSourceName || 'manual-grid-seed',
    sourceUrl: loadedImageSourceUrl || loadedSampleImage.src,
    imageWidth: loadedSampleImage.naturalWidth,
    imageHeight: loadedSampleImage.naturalHeight,
    corners: manualSeedCorners(loadedSampleImage, loadedImageKind),
    columns: 12,
    rows: 8,
    confidence: 0.2,
    latticeScore: 0,
    families: [
      { angleDegrees: 0, lineCount: 13, score: 0 },
      { angleDegrees: 90, lineCount: 9, score: 0 },
    ],
    detectedAt: new Date().toISOString(),
    message: 'Manual seed handles placed. Drag the orange corners onto the real grid, then force apply or keep adjusting.',
  };
  state.projectionAlignment = null;
  state.projectionAlignmentIssue = 'Manual correction required: manual seed handles need to be aligned before projection anchors are trusted.';
  publish();
}

function manualSeedCorners(
  image: HTMLImageElement,
  kind: typeof loadedImageKind,
): [Point, Point, Point, Point] {
  const cameraFrame = kind === 'camera';
  const portraitCameraFrame = cameraFrame && image.naturalHeight > image.naturalWidth;
  const left = image.naturalWidth * (cameraFrame ? 0.18 : 0.15);
  const right = image.naturalWidth * (cameraFrame ? 0.88 : 0.85);
  const top = image.naturalHeight * (portraitCameraFrame ? 0.14 : cameraFrame ? 0.52 : 0.18);
  const bottom = image.naturalHeight * (portraitCameraFrame ? 0.86 : cameraFrame ? 0.92 : 0.82);
  return [
    { x: left, y: top },
    { x: right, y: top },
    { x: right, y: bottom },
    { x: left, y: bottom },
  ];
}

async function autoDetectSelectedImage(): Promise<void> {
  const select = document.querySelector<HTMLSelectElement>('#sample-image');
  const sample = sampleImages[Number(select?.value ?? 0)] ?? sampleImages[0];
  await runGridDetection(sample.label, sample.url, { kind: 'sample' });
}

async function runGridDetection(
  sourceName: string,
  sourceUrl: string,
  options: { kind: 'sample' | 'upload' | 'camera' } = { kind: 'sample' },
): Promise<void> {
  try {
    gatewaySeedOptions = [];
    state.detectedGrid = null;
    state.projectionAlignment = null;
    state.projectionAlignmentIssue = null;
    loadedSampleImage = null;
    loadedImageKind = options.kind;
    loadedImageSourceName = sourceName;
    loadedImageSourceUrl = sourceUrl;
    setDetectionStatus('Analyzing image...');
    setAlignmentStatus('Projection not aligned to a detected grid yet.');
    publish();
    await delay(0);
    loadedSampleImage = await loadImage(sourceUrl);
    render();
    await delay(0);
    state.detectedGrid = await detectGridFromImage(loadedSampleImage, sourceName, sourceUrl);
    applyDetectedGridToProjection('Auto-aligned projection anchors from detected grid bounds.');
    publish();
  } catch (error) {
    gatewaySeedOptions = [];
    state.detectedGrid = null;
    state.projectionAlignment = null;
    state.projectionAlignmentIssue = null;
    channel.publish(state);
    render();
    setDetectionStatus(`Detection failed: ${(error as Error).message}`);
    setAlignmentStatus('Projection not aligned to a detected grid yet.');
    syncManualSeedButton();
  }
}

async function runGatewaySeedCandidate(): Promise<void> {
  if (!loadedSampleImage || !loadedImageSourceUrl) {
    window.alert('Capture or load a frame before asking the gateway for a seed candidate.');
    return;
  }

  try {
    setDetectionStatus('Running gateway detector for a seed candidate...');
    setAlignmentStatus('Projection not aligned to a detected grid yet.');
    await delay(0);
    const response = await fetch('/__opencv-detection-upload', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ imageDataUrl: imageToJpegDataUrl(loadedSampleImage) }),
    });
    if (!response.ok) {
      throw new Error(await response.text());
    }
    const payload = await response.json() as OpenCvDetectionPayload;
    if (!payload.detected) {
      throw new Error(payload.errorMessage || 'Gateway detector did not find a grid candidate.');
    }
    gatewaySeedOptions = gatewaySeedOptionsFromPayload(payload);
    if (gatewaySeedOptions.length === 0) {
      throw new Error('Gateway detector did not return any usable candidates.');
    }
    state.detectedGrid = cloneDetectedGrid(gatewaySeedOptions[0].grid);
    state.projectionAlignment = null;
    state.projectionAlignmentIssue = 'Manual correction required: gateway detector candidate needs visual confirmation before projection anchors are trusted.';
    publish();
  } catch (error) {
    setDetectionStatus(`Gateway seed failed: ${errorMessage(error)}`, 'warning');
    setAlignmentStatus('Projection not aligned to a detected grid yet.');
  }
}

interface OpenCvDetectionPayload {
  detected?: boolean;
  candidateId?: string;
  sourceName?: string;
  sourceUrl?: string;
  imageWidth?: number;
  imageHeight?: number;
  corners?: Point[];
  columns?: number;
  rows?: number;
  confidence?: number;
  latticeScore?: number;
  topCandidates?: GatewayCandidatePayload[];
  detectorMessage?: string;
  errorMessage?: string;
}

interface GatewayCandidatePayload {
  score?: number;
  variant?: string;
  params?: number[];
  columns?: number;
  rows?: number;
  inFrameFraction?: number;
  areaRatio?: number;
  offFrameRatio?: number;
  corners?: Point[];
  families?: GatewayCandidateFamilyPayload[];
}

interface GatewayCandidateFamilyPayload {
  angleDeg?: number;
  pitch?: number;
  periodScore?: number;
  lines?: number;
}

function gatewaySeedOptionsFromPayload(payload: OpenCvDetectionPayload): GatewaySeedOption[] {
  const topCandidates = Array.isArray(payload.topCandidates)
    ? payload.topCandidates.filter((candidate) => Array.isArray(candidate.corners) && candidate.corners.length === 4)
    : [];

  if (topCandidates.length === 0) {
    return [
      {
        label: gatewaySeedLabel(payload, undefined, 0),
        grid: detectedGridFromOpenCvPayload(payload),
      },
    ];
  }

  return topCandidates.map((candidate, index) => ({
    label: gatewaySeedLabel(payload, candidate, index),
    grid: detectedGridFromOpenCvPayload(payload, candidate, index),
  }));
}

function gatewaySeedLabel(
  payload: OpenCvDetectionPayload,
  candidate: GatewayCandidatePayload | undefined,
  index: number,
): string {
  const columns = Math.max(1, Math.round(Number(candidate?.columns ?? payload.columns ?? 12)));
  const rows = Math.max(1, Math.round(Number(candidate?.rows ?? payload.rows ?? 8)));
  const score = Number(candidate?.score);
  const scoreText = Number.isFinite(score) ? `, score ${score.toFixed(2)}` : '';
  return `Candidate ${index + 1}: ${columns} x ${rows}${scoreText}`;
}

function detectedGridFromOpenCvPayload(
  payload: OpenCvDetectionPayload,
  candidate?: GatewayCandidatePayload,
  candidateIndex = 0,
): DetectedGrid {
  const corners = candidate?.corners ?? payload.corners;
  if (!Array.isArray(corners) || corners.length !== 4) {
    throw new Error('Gateway detector returned invalid corners.');
  }
  const columns = Math.max(1, Math.round(Number(candidate?.columns ?? payload.columns ?? 12)));
  const rows = Math.max(1, Math.round(Number(candidate?.rows ?? payload.rows ?? 8)));
  const confidence = candidate ? confidenceFromGatewayCandidate(candidate, payload) : Number(payload.confidence ?? 0.2);
  const latticeScore = candidate ? latticeScoreFromGatewayCandidate(candidate, payload) : Number(payload.latticeScore ?? 0);
  const candidateLabel = payload.candidateId === 'esp32-webcam-lattice-probe-v1'
    ? 'Gateway ESP32 webcam seed candidate'
    : 'Gateway OpenCV seed candidate';
  const optionText = candidate
    ? ` option ${candidateIndex + 1}: ${columns}x${rows}; score ${formatCandidateScore(candidate.score)}.`
    : '.';
  return {
    sourceName: loadedImageSourceName || payload.sourceName || 'gateway-seed-candidate',
    sourceUrl: loadedImageSourceUrl || payload.sourceUrl || '',
    imageWidth: loadedSampleImage?.naturalWidth ?? Number(payload.imageWidth ?? 0),
    imageHeight: loadedSampleImage?.naturalHeight ?? Number(payload.imageHeight ?? 0),
    corners: corners.map((corner) => ({
      x: Number(corner.x),
      y: Number(corner.y),
    })) as [Point, Point, Point, Point],
    columns,
    rows,
    confidence,
    latticeScore,
    families: gatewayCandidateFamilies(candidate, columns, rows, confidence),
    detectedAt: new Date().toISOString(),
    message: `${candidateLabel}${optionText} ${payload.detectorMessage || 'Review and drag handles before applying.'}`,
  };
}

function confidenceFromGatewayCandidate(candidate: GatewayCandidatePayload, payload: OpenCvDetectionPayload): number {
  const score = Number(candidate.score);
  if (Number.isFinite(score)) return Math.min(0.55, Math.max(0.2, score / 8));
  return Number(payload.confidence ?? 0.2);
}

function latticeScoreFromGatewayCandidate(candidate: GatewayCandidatePayload, payload: OpenCvDetectionPayload): number {
  const familyScores = candidate.families
    ?.map((family) => Number(family.periodScore))
    .filter((score) => Number.isFinite(score)) ?? [];
  if (familyScores.length >= 2) {
    return Math.min(0.5, Math.max(0, (familyScores[0] + familyScores[1]) / 4));
  }
  return Number(payload.latticeScore ?? 0);
}

function gatewayCandidateFamilies(
  candidate: GatewayCandidatePayload | undefined,
  columns: number,
  rows: number,
  confidence: number,
): [DetectedGrid['families'][0], DetectedGrid['families'][1]] {
  if (Array.isArray(candidate?.families) && candidate.families.length >= 2) {
    return [
      {
        angleDegrees: Number(candidate.families[0].angleDeg ?? 0),
        lineCount: Math.max(0, Math.round(Number(candidate.families[0].lines ?? columns + 1))),
        score: Number(candidate.families[0].periodScore ?? confidence),
      },
      {
        angleDegrees: Number(candidate.families[1].angleDeg ?? 90),
        lineCount: Math.max(0, Math.round(Number(candidate.families[1].lines ?? rows + 1))),
        score: Number(candidate.families[1].periodScore ?? confidence),
      },
    ];
  }
  return [
    { angleDegrees: 0, lineCount: columns + 1, score: confidence },
    { angleDegrees: 90, lineCount: rows + 1, score: confidence },
  ];
}

function formatCandidateScore(score: unknown): string {
  const numericScore = Number(score);
  return Number.isFinite(numericScore) ? numericScore.toFixed(2) : 'n/a';
}

function selectGatewaySeedOption(index: number): void {
  const option = gatewaySeedOptions[index];
  if (!option) return;
  state.detectedGrid = cloneDetectedGrid(option.grid);
  state.projectionAlignment = null;
  state.projectionAlignmentIssue = 'Manual correction required: gateway detector candidate needs visual confirmation before projection anchors are trusted.';
  publish();
}

function cloneDetectedGrid(grid: DetectedGrid): DetectedGrid {
  return {
    ...grid,
    corners: grid.corners.map((corner) => ({ ...corner })) as [Point, Point, Point, Point],
    families: grid.families.map((family) => ({ ...family })) as DetectedGrid['families'],
    detectedAt: new Date().toISOString(),
  };
}

async function restoreDetectedImage(): Promise<void> {
  if (!state.detectedGrid) return;
  try {
    loadedSampleImage = await loadImage(state.detectedGrid.sourceUrl);
    loadedImageKind = state.detectedGrid.sourceName.startsWith('camera-frame-') || state.detectedGrid.sourceName.startsWith('clean-mat-frame-')
      ? 'camera'
      : 'sample';
    loadedImageSourceName = state.detectedGrid.sourceName;
    loadedImageSourceUrl = state.detectedGrid.sourceUrl;
    render();
  } catch {
    state.detectedGrid = null;
    loadedImageKind = null;
    loadedImageSourceName = '';
    loadedImageSourceUrl = '';
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

function imageToJpegDataUrl(image: HTMLImageElement): string {
  const canvas = document.createElement('canvas');
  canvas.width = image.naturalWidth;
  canvas.height = image.naturalHeight;
  const context = canvas.getContext('2d');
  if (!context) throw new Error('Could not prepare image for gateway detection.');
  context.drawImage(image, 0, 0);
  return canvas.toDataURL('image/jpeg', 0.92);
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

function renderGatewaySeedOptions(): void {
  const container = document.querySelector<HTMLDivElement>('#gateway-candidates');
  if (!container) return;

  if (gatewaySeedOptions.length <= 1 || !state.detectedGrid) {
    container.hidden = true;
    container.replaceChildren();
    return;
  }

  const selectedIndex = selectedGatewaySeedOptionIndex();
  container.hidden = false;
  container.replaceChildren();

  const heading = document.createElement('p');
  heading.className = 'gateway-candidates-heading';
  heading.textContent = 'Gateway candidates';
  container.append(heading);

  const row = document.createElement('div');
  row.className = 'gateway-candidate-row';
  gatewaySeedOptions.forEach((option, index) => {
    const button = document.createElement('button');
    button.className = 'button compact gateway-candidate-button';
    if (index === selectedIndex) button.classList.add('selected');
    button.type = 'button';
    button.dataset.gatewayCandidateIndex = String(index);
    button.textContent = option.label;
    row.append(button);
  });
  container.append(row);
}

function selectedGatewaySeedOptionIndex(): number {
  if (!state.detectedGrid) return -1;
  const current = gatewayGridSignature(state.detectedGrid);
  return gatewaySeedOptions.findIndex((option) => gatewayGridSignature(option.grid) === current);
}

function gatewayGridSignature(grid: DetectedGrid): string {
  return [
    grid.columns,
    grid.rows,
    ...grid.corners.flatMap((corner) => [Math.round(corner.x), Math.round(corner.y)]),
  ].join(':');
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

function renderCameraEvidence(): void {
  const element = document.querySelector<HTMLParagraphElement>('#camera-evidence');
  if (!element) return;

  if (!state.evidence.camera) {
    element.textContent = 'No camera frame captured yet.';
    return;
  }

  const camera = state.evidence.camera;
  const resolution = camera.streamWidth && camera.streamHeight
    ? `${camera.streamWidth} x ${camera.streamHeight}`
    : 'unknown resolution';
  const frame = camera.capturedFrameName
    ? ` Last captured frame: ${camera.capturedFrameName}.`
    : '';
  const quality = camera.frameQuality
    ? ` Frame luma ${camera.frameMeanLuma ?? '?'} / contrast ${camera.frameContrast ?? '?'}: ${camera.frameQuality}.`
    : '';
  const rotation = camera.frameRotationDegrees
    ? ` Rotated ${camera.frameRotationDegrees} deg.`
    : '';
  element.textContent = `Camera: ${camera.deviceLabel || 'Default camera'} at ${resolution}.${frame}${rotation}${quality}`;
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

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}
