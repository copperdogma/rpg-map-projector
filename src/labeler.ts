import './styles.css';
import { applyHomography, solveHomography, type Homography } from './calibration/homography';
import { sampleImages } from './calibration/sampleImages';
import {
  EMPTY_LABEL_FILE,
  findFixtureLabel,
  sampleToFixtureIdentity,
  upsertFixtureLabel,
  type GridFixtureLabel,
  type GridFixtureLabelFile,
  type GridFixtureIdentity,
} from './calibration/fixtureLabels';
import type { Point } from './calibration/types';

const LABEL_STORAGE_KEY = 'rpg-map-projector:grid-fixture-labels:draft';
const LABELER_GRID_VISIBILITY_KEY = 'rpg-map-projector:grid-fixture-labels:show-grid';
const LABEL_ENDPOINT = '/__fixture-labels';
const OPENCV_DETECTION_ENDPOINT = '/__opencv-detection';
const AI_GRID_SEED_ENDPOINT = '/__ai-grid-seed';
const WHEEL_ZOOM_SPEED = 0.003;
const DRAG_AUTOPAN_MARGIN = 72;
const DRAG_AUTOPAN_MAX_STEP = 96;

let labelFile: GridFixtureLabelFile = structuredClone(EMPTY_LABEL_FILE);
let selectedIndex = 0;
let selectedImage: HTMLImageElement | null = null;
let currentLabel: GridFixtureLabel | null = null;
let dragCornerIndex: number | null = null;
let dragEdgeIndex: number | null = null;
let dragViewportFit: LabelViewportFit | null = null;
let dragStartPoint: Point | null = null;
let dragStartCorners: [Point, Point, Point, Point] | null = null;
let panState: PanState | null = null;
let activeCornerIndex = 0;
let dirty = false;
let showVirtualGrid = window.localStorage.getItem(LABELER_GRID_VISIBILITY_KEY) !== 'false';
let showAiSupportOverlay = false;
let activeAiSupportOverlay: AiGridSupportOverlay | null = null;
let viewState: LabelViewState = {
  mode: 'fit',
  scale: 1,
  center: { x: 0, y: 0 },
};

const root = document.querySelector<HTMLDivElement>('#labeler-root');
if (!root) throw new Error('Missing labeler root');

interface LabelViewportFit {
  x: number;
  y: number;
  width: number;
  height: number;
  scale: number;
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

interface LabelViewState {
  mode: 'fit' | 'manual';
  scale: number;
  center: Point;
}

interface PanState {
  pointerId: number;
  startPointer: Point;
  startCenter: Point;
  scale: number;
}

interface OpenCvDetectionSeed {
  detected: boolean;
  imageWidth: number | null;
  imageHeight: number | null;
  corners?: [Point, Point, Point, Point];
  columns?: number;
  rows?: number;
  confidence?: number;
  latticeScore?: number;
  selectedFitKind?: string | null;
  detectorMessage?: string;
  errorMessage?: string;
  elapsedMs?: number;
}

interface AiGridSeed extends OpenCvDetectionSeed {
  modeId?: string;
  modeLabel?: string;
  riskLevel?: string;
  explanation?: string;
  selectedModeId?: string;
  gridBounds?: AiGridBounds;
  gridHomography?: Homography;
  dotVariantId?: string;
  decision?: string;
  projectionReadinessMode?: string;
  noLabelProjectionReadinessMode?: string;
  fullSpanHomographyLineWithin0_15Pct?: number;
  observedEdgeHomographyLineWithin0_15Pct?: number;
  visibleMeshLineWithin0_15Pct?: number;
  visibleMeshCells?: number;
  unsupportedCellCount?: number;
  visibleMeshCellDensity?: number;
  sourceForegroundTrimmedCells?: number;
  supportOverlay?: AiGridSupportOverlay;
}

interface AiGridSupportOverlay {
  vertexCount: number;
  cellCount: number;
  cells: Array<{
    i: number;
    j: number;
    corners: [Point, Point, Point, Point];
  }>;
}

interface AiGridBounds {
  minI: number;
  maxI: number;
  minJ: number;
  maxJ: number;
}

const EDGE_DEFINITIONS = [
  { cornerIndexes: [0, 1], axis: 'y' },
  { cornerIndexes: [1, 2], axis: 'x' },
  { cornerIndexes: [2, 3], axis: 'y' },
  { cornerIndexes: [3, 0], axis: 'x' },
] as const;

const sampleOptions = sampleImages
  .map((sample, index) => `<option value="${index}">${sample.label}</option>`)
  .join('');

root.innerHTML = `
  <main class="app-shell labeler-shell">
    <header class="topbar">
      <div>
        <h1>Grid Fixture Labeler</h1>
        <p>Drag the four corners, set the square counts, and save benchmark labels for detector iteration.</p>
      </div>
      <div class="topbar-actions">
        <a class="button" href="/">Calibration Workbench</a>
        <button class="button" id="download-labels" type="button">Download JSON</button>
        <button class="button primary" id="save-label" type="button">Save Fixture</button>
      </div>
    </header>

    <section class="labeler-workspace">
      <section class="labeler-preview" aria-label="Fixture labeling canvas">
        <div class="surface-title">
          <div>
            <h2 id="fixture-title">Fixture</h2>
            <p id="fixture-meta">Loading labels...</p>
          </div>
          <div class="button-row">
            <button class="button" id="previous-fixture" type="button">Previous</button>
            <button class="button" id="next-fixture" type="button">Next</button>
            <button class="button" id="next-unlabeled" type="button">Next Unlabeled</button>
          </div>
        </div>
        <div class="labeler-stage">
          <canvas id="labeler-canvas" tabindex="0" aria-label="Fixture image with editable grid label"></canvas>
        </div>
      </section>

      <section class="controls-column" aria-label="Fixture label controls">
        <section class="panel">
          <div class="panel-heading">
            <h2>Fixture</h2>
            <p>Select a false input and seed or edit its benchmark grid.</p>
          </div>
          <label>
            <span>Sample image</span>
            <select id="fixture-select">${sampleOptions}</select>
          </label>
          <label>
            <span>AI seed mode</span>
            <select id="ai-seed-mode">
              <option value="grid-frame">Bounded image-frame grid</option>
              <option value="supported">Supported visible patch</option>
              <option value="fit-span">Selected dot extent (extrapolates)</option>
              <option value="manual-span-diagnostic">Wider manual span (diagnostic)</option>
              <option value="label-sized-diagnostic">Label-sized diagnostic (uses labels)</option>
            </select>
          </label>
          <div class="button-row labeler-actions">
            <button class="button" id="seed-detector" type="button">Use OpenCV Seed</button>
            <button class="button" id="seed-ai-current" type="button">Use AI Seed</button>
            <button class="button" id="reset-bounds" type="button">Reset To Image Bounds</button>
          </div>
          <label class="checkbox-line">
            <input id="show-ai-support" type="checkbox" />
            <span>Show AI support cells</span>
          </label>
          <p class="detection-status status-neutral" id="labeler-status">Loading labels...</p>
        </section>

        <section class="panel">
          <div class="panel-heading">
            <h2>View</h2>
          </div>
          <div class="labeler-view-controls">
            <button class="button compact" id="zoom-fit" type="button">Fit</button>
            <button class="button compact" id="zoom-100" type="button">100%</button>
            <button class="button compact" id="zoom-200" type="button">200%</button>
            <button class="button compact" id="zoom-out" type="button">-</button>
            <input id="label-zoom" type="range" min="0.05" max="3" step="0.05" />
            <button class="button compact" id="zoom-in" type="button">+</button>
            <span id="zoom-readout" class="zoom-readout">Fit</span>
            <span id="native-readout" class="zoom-readout native-readout">Native</span>
          </div>
        </section>

        <section class="panel">
          <div class="panel-heading">
            <h2>Grid Size</h2>
            <p>Columns and rows are square counts between the four labeled corners.</p>
          </div>
          <div class="labeler-stepper">
            <span>Columns <span class="shortcut-hint"><kbd>⇧C</kbd> - <kbd>C</kbd> +</span></span>
            <button class="button compact" data-step-field="columns" data-step="-1" type="button">-</button>
            <input id="label-columns" type="number" min="1" max="120" step="1" />
            <button class="button compact" data-step-field="columns" data-step="1" type="button">+</button>
          </div>
          <div class="labeler-stepper">
            <span>Rows <span class="shortcut-hint"><kbd>⇧R</kbd> - <kbd>R</kbd> +</span></span>
            <button class="button compact" data-step-field="rows" data-step="-1" type="button">-</button>
            <input id="label-rows" type="number" min="1" max="120" step="1" />
            <button class="button compact" data-step-field="rows" data-step="1" type="button">+</button>
          </div>
          <label class="checkbox-line">
            <input id="label-benchmark" type="checkbox" />
            <span>Use this fixture in accuracy scoring</span>
          </label>
          <label class="checkbox-line">
            <input id="show-label-grid" type="checkbox" />
            <span>Show virtual grid overlay <span class="shortcut-hint"><kbd>G</kbd></span></span>
          </label>
        </section>

        <section class="panel">
          <div class="panel-heading">
            <h2>Corner Precision</h2>
            <p>Select a corner, then use arrow keys for one-pixel moves. Hold Shift for ten pixels.</p>
          </div>
          <div class="segmented corner-segments" role="group" aria-label="Active corner">
            <button class="segment selected" data-corner="0" type="button">A</button>
            <button class="segment" data-corner="1" type="button">B</button>
            <button class="segment" data-corner="2" type="button">C</button>
            <button class="segment" data-corner="3" type="button">D</button>
          </div>
          <div class="labeler-corner-table" id="corner-table"></div>
        </section>
      </section>
    </section>
  </main>
`;

const canvas = document.querySelector<HTMLCanvasElement>('#labeler-canvas')!;
const fixtureSelect = document.querySelector<HTMLSelectElement>('#fixture-select')!;
const statusElement = document.querySelector<HTMLParagraphElement>('#labeler-status')!;

bindControls();
void boot();
window.addEventListener('resize', render);

async function boot(): Promise<void> {
  labelFile = await loadLabelFile();
  await loadFixture(0);
}

function bindControls(): void {
  fixtureSelect.addEventListener('change', () => {
    void loadFixture(Number(fixtureSelect.value));
  });

  document.querySelector('#previous-fixture')?.addEventListener('click', () => {
    void loadFixture((selectedIndex - 1 + sampleImages.length) % sampleImages.length);
  });

  document.querySelector('#next-fixture')?.addEventListener('click', () => {
    void loadFixture((selectedIndex + 1) % sampleImages.length);
  });

  document.querySelector('#next-unlabeled')?.addEventListener('click', () => {
    const nextIndex = findNextUnlabeledIndex();
    void loadFixture(nextIndex);
  });

  document.querySelector('#seed-detector')?.addEventListener('click', () => {
    void seedFromDetector();
  });

  document.querySelector('#seed-ai-current')?.addEventListener('click', () => {
    void seedFromAiGrid();
  });

  document.querySelector('#reset-bounds')?.addEventListener('click', () => {
    if (!selectedImage) return;
    activeAiSupportOverlay = null;
    currentLabel = createDefaultLabel(currentIdentity(), selectedImage);
    markDirty('Reset to image bounds.');
  });

  document.querySelector('#save-label')?.addEventListener('click', () => {
    void saveCurrentFixture();
  });

  document.querySelector('#download-labels')?.addEventListener('click', () => {
    upsertCurrentDraft();
    downloadLabels();
  });

  document.querySelector<HTMLInputElement>('#label-columns')?.addEventListener('input', (event) => {
    if (!currentLabel) return;
    currentLabel.columns = clampInteger(Number((event.target as HTMLInputElement).value), 1, 120);
    markDirty('Columns updated.');
  });

  document.querySelector<HTMLInputElement>('#label-rows')?.addEventListener('input', (event) => {
    if (!currentLabel) return;
    currentLabel.rows = clampInteger(Number((event.target as HTMLInputElement).value), 1, 120);
    markDirty('Rows updated.');
  });

  document.querySelector<HTMLInputElement>('#label-benchmark')?.addEventListener('change', (event) => {
    if (!currentLabel) return;
    currentLabel.benchmark = (event.target as HTMLInputElement).checked;
    markDirty('Benchmark flag updated.');
  });

  document.querySelector<HTMLInputElement>('#show-label-grid')?.addEventListener('change', (event) => {
    setVirtualGridVisible((event.target as HTMLInputElement).checked);
  });

  document.querySelector<HTMLInputElement>('#show-ai-support')?.addEventListener('change', (event) => {
    showAiSupportOverlay = (event.target as HTMLInputElement).checked;
    syncControls();
    render();
  });

  document.querySelector('#zoom-fit')?.addEventListener('click', () => {
    setFitView();
  });

  document.querySelector('#zoom-100')?.addEventListener('click', () => {
    setManualZoom(1, activeViewFocusPoint());
  });

  document.querySelector('#zoom-200')?.addEventListener('click', () => {
    setManualZoom(2, activeViewFocusPoint());
  });

  document.querySelector('#zoom-out')?.addEventListener('click', () => {
    zoomAtCanvasCenter(1 / 1.35);
  });

  document.querySelector('#zoom-in')?.addEventListener('click', () => {
    zoomAtCanvasCenter(1.35);
  });

  document.querySelector<HTMLInputElement>('#label-zoom')?.addEventListener('input', (event) => {
    setManualZoom(Number((event.target as HTMLInputElement).value), currentViewCenter());
  });

  window.addEventListener('keydown', (event) => {
    if (event.altKey || event.ctrlKey || event.metaKey) return;
    if (isTextEntryTarget(event.target)) return;

    const key = event.key.toLowerCase();
    if (key === 'g') {
      event.preventDefault();
      setVirtualGridVisible(!showVirtualGrid);
      return;
    }

    if (key === 'c') {
      event.preventDefault();
      adjustGridSize('columns', event.shiftKey ? -1 : 1);
      return;
    }

    if (key === 'r') {
      event.preventDefault();
      adjustGridSize('rows', event.shiftKey ? -1 : 1);
    }
  });

  document.querySelectorAll<HTMLButtonElement>('[data-step-field]').forEach((button) => {
    button.addEventListener('click', () => {
      if (!currentLabel) return;
      const field = button.dataset.stepField as 'columns' | 'rows';
      const step = Number(button.dataset.step ?? 0);
      currentLabel[field] = clampInteger(currentLabel[field] + step, 1, 120);
      markDirty(`${field === 'columns' ? 'Columns' : 'Rows'} updated.`);
    });
  });

  document.querySelectorAll<HTMLButtonElement>('[data-corner]').forEach((button) => {
    button.addEventListener('click', () => {
      activeCornerIndex = Number(button.dataset.corner ?? 0);
      syncCornerButtons();
      render();
    });
  });

  canvas.addEventListener('pointerdown', (event) => {
    const index = findNearestCorner(event);
    if (index !== null) {
      dragCornerIndex = index;
      activeCornerIndex = index;
      dragViewportFit = selectedImage && currentLabel
        ? currentLabelViewportFit(selectedImage, currentLabel, canvas.clientWidth, canvas.clientHeight)
        : null;
      dragStartPoint = null;
      dragStartCorners = null;
      updatePointerState();
      canvas.setPointerCapture(event.pointerId);
      canvas.focus({ preventScroll: true });
      syncCornerButtons();
      render();
      event.preventDefault();
      return;
    }

    const edgeIndex = findNearestEdgeHandle(event);
    if (edgeIndex !== null && selectedImage && currentLabel) {
      dragEdgeIndex = edgeIndex;
      dragViewportFit = currentLabelViewportFit(selectedImage, currentLabel, canvas.clientWidth, canvas.clientHeight);
      dragStartPoint = pointerToNaturalPoint(event);
      dragStartCorners = cloneCorners(currentLabel.corners);
      updatePointerState();
      canvas.setPointerCapture(event.pointerId);
      canvas.focus({ preventScroll: true });
      render();
      event.preventDefault();
      return;
    }

    if (viewState.mode === 'manual') {
      startPan(event);
      event.preventDefault();
    }
  });

  canvas.addEventListener('pointermove', (event) => {
    if (panState) {
      updatePan(event);
      event.preventDefault();
      return;
    }
    if (dragEdgeIndex !== null) {
      updateEdgeDrag(event);
      event.preventDefault();
      return;
    }
    if (dragCornerIndex === null || !currentLabel) return;
    const point = pointerToNaturalPoint(event);
    if (!point) return;
    currentLabel.corners[dragCornerIndex] = point;
    markDirty('Corner moved.');
  });

  canvas.addEventListener('pointerup', (event) => {
    endCornerDrag(event.pointerId);
  });

  canvas.addEventListener('pointercancel', (event) => {
    endCornerDrag(event.pointerId);
  });

  canvas.addEventListener('lostpointercapture', () => {
    if (dragCornerIndex === null && dragEdgeIndex === null && !panState) return;
    dragCornerIndex = null;
    dragEdgeIndex = null;
    dragStartPoint = null;
    dragStartCorners = null;
    panState = null;
    dragViewportFit = null;
    updatePointerState();
    render();
  });

  canvas.addEventListener('wheel', (event) => {
    if (!selectedImage || !currentLabel) return;
    const rect = canvas.getBoundingClientRect();
    const point = { x: event.clientX - rect.left, y: event.clientY - rect.top };
    const factor = Math.exp(-event.deltaY * WHEEL_ZOOM_SPEED);
    zoomAtCanvasPoint(point, factor);
    event.preventDefault();
  }, { passive: false });

  canvas.addEventListener('keydown', (event) => {
    if (!currentLabel) return;
    const direction = keyDirection(event.key);
    if (!direction) return;
    const amount = event.shiftKey ? 10 : 1;
    const corner = currentLabel.corners[activeCornerIndex];
    currentLabel.corners[activeCornerIndex] = {
      x: corner.x + direction.x * amount,
      y: corner.y + direction.y * amount,
    };
    markDirty('Corner nudged.');
    event.preventDefault();
  });
}

async function loadFixture(index: number): Promise<void> {
  selectedIndex = index;
  fixtureSelect.value = String(index);
  selectedImage = null;
  currentLabel = null;
  activeAiSupportOverlay = null;
  dirty = false;
  setStatus('Loading fixture...', 'neutral');
  render();

  const sample = sampleImages[index];
  const identity = sampleToFixtureIdentity(sample);
  selectedImage = await loadImage(identity.sourceUrl);
  const saved = findFixtureLabel(labelFile, identity.sourceId);
  currentLabel = saved
    ? cloneLabel(saved)
    : createDefaultLabel(identity, selectedImage);
  viewState = {
    mode: 'fit',
    scale: 1,
    center: { x: selectedImage.naturalWidth / 2, y: selectedImage.naturalHeight / 2 },
  };
  dirty = false;
  syncControls();
  setStatus(saved ? 'Loaded saved label.' : 'No saved label yet. Drag corners and save this fixture.', saved ? 'success' : 'neutral');
  render();
}

async function seedFromDetector(): Promise<void> {
  if (!selectedImage) return;
  try {
    setStatus('Running OpenCV seed. This can take around 20 seconds on large photos...', 'neutral');
    const detected = await detectOpenCvSeed(currentIdentity().sourceUrl);
    if (!detected.detected || !detected.corners || !detected.columns || !detected.rows) {
      throw new Error(detected.errorMessage || 'No OpenCV grid candidate found.');
    }
    const scaledCorners = scaleDetectionCorners(detected, selectedImage);
    activeAiSupportOverlay = null;
    currentLabel = {
      ...currentIdentity(),
      imageWidth: selectedImage.naturalWidth,
      imageHeight: selectedImage.naturalHeight,
      corners: scaledCorners,
      columns: detected.columns,
      rows: detected.rows,
      benchmark: currentLabel?.benchmark ?? true,
      labeledAt: new Date().toISOString(),
    };
    const elapsed = detected.elapsedMs ? ` in ${(detected.elapsedMs / 1000).toFixed(1)}s` : '';
    const fit = detected.selectedFitKind ? ` using ${detected.selectedFitKind}` : '';
    markDirty(`OpenCV seed applied${elapsed}: ${detected.columns} x ${detected.rows}${fit}. Adjust it before saving if needed.`);
  } catch (error) {
    setStatus(`OpenCV seed failed: ${(error as Error).message}`, 'warning');
  }
}

async function seedFromAiGrid(): Promise<void> {
  if (!selectedImage) return;
  try {
    setStatus('Loading current AI grid seed from saved benchmark artifacts...', 'neutral');
    const detected = await detectAiGridSeed(currentIdentity().sourceId, selectedAiGridMode());
    if (!detected.detected || !detected.corners || !detected.columns || !detected.rows) {
      throw new Error(detected.errorMessage || 'No current AI grid seed found for this fixture.');
    }
    const trimmed = trimAiSeedAgainstSourceImage(detected, selectedImage);
    if (!trimmed.columns || !trimmed.rows) {
      throw new Error('AI grid seed lost its row/column count after source-image trimming.');
    }
    const scaledCorners = scaleDetectionCorners(trimmed, selectedImage);
    activeAiSupportOverlay = trimmed.supportOverlay ?? null;
    currentLabel = {
      ...currentIdentity(),
      imageWidth: selectedImage.naturalWidth,
      imageHeight: selectedImage.naturalHeight,
      corners: scaledCorners,
      columns: trimmed.columns,
      rows: trimmed.rows,
      benchmark: currentLabel?.benchmark ?? true,
      labeledAt: new Date().toISOString(),
    };
    const variant = trimmed.dotVariantId ? ` ${trimmed.dotVariantId}` : '';
    const readiness = trimmed.noLabelProjectionReadinessMode
      ? `; ${trimmed.noLabelProjectionReadinessMode}`
      : '';
    const score = typeof trimmed.fullSpanHomographyLineWithin0_15Pct === 'number'
      ? `; full-span score ${trimmed.fullSpanHomographyLineWithin0_15Pct.toFixed(1)}%`
      : '';
    const mode = trimmed.modeLabel ? ` ${trimmed.modeLabel}` : '';
    const risk = trimmed.riskLevel ? `; risk ${trimmed.riskLevel}` : '';
    const support = typeof trimmed.visibleMeshCells === 'number' && typeof trimmed.unsupportedCellCount === 'number'
      ? `; supported ${trimmed.visibleMeshCells} cells / unsupported ${trimmed.unsupportedCellCount}`
      : '';
    const trimNote = trimmed.sourceForegroundTrimmedCells
      ? `; source-trimmed ${trimmed.sourceForegroundTrimmedCells} foreground cells`
      : '';
    markDirty(`AI seed${mode}${variant} applied: ${trimmed.columns} x ${trimmed.rows}${readiness}${score}${risk}${support}${trimNote}. Adjust it before saving if needed.`);
  } catch (error) {
    setStatus(`AI seed failed: ${(error as Error).message}`, 'warning');
  }
}

async function detectOpenCvSeed(sourceUrl: string): Promise<OpenCvDetectionSeed> {
  const response = await fetch(`${OPENCV_DETECTION_ENDPOINT}?sourceUrl=${encodeURIComponent(sourceUrl)}`);
  if (!response.ok) throw new Error(await response.text());
  return normalizeOpenCvDetectionSeed(await response.json());
}

async function detectAiGridSeed(sourceId: string, mode: string): Promise<AiGridSeed> {
  const params = new URLSearchParams({ sourceId, mode });
  const response = await fetch(`${AI_GRID_SEED_ENDPOINT}?${params.toString()}`);
  if (!response.ok) throw new Error(await response.text());
  return normalizeAiGridSeed(await response.json());
}

function normalizeOpenCvDetectionSeed(candidate: unknown): OpenCvDetectionSeed {
  if (!candidate || typeof candidate !== 'object') {
    throw new Error('OpenCV detector returned an invalid response.');
  }
  const seed = candidate as Partial<OpenCvDetectionSeed>;
  return {
    detected: seed.detected === true,
    imageWidth: typeof seed.imageWidth === 'number' ? seed.imageWidth : null,
    imageHeight: typeof seed.imageHeight === 'number' ? seed.imageHeight : null,
    corners: normalizeOpenCvCorners(seed.corners),
    columns: typeof seed.columns === 'number' ? seed.columns : undefined,
    rows: typeof seed.rows === 'number' ? seed.rows : undefined,
    confidence: typeof seed.confidence === 'number' ? seed.confidence : undefined,
    latticeScore: typeof seed.latticeScore === 'number' ? seed.latticeScore : undefined,
    selectedFitKind: typeof seed.selectedFitKind === 'string' ? seed.selectedFitKind : null,
    detectorMessage: typeof seed.detectorMessage === 'string' ? seed.detectorMessage : undefined,
    errorMessage: typeof seed.errorMessage === 'string' ? seed.errorMessage : undefined,
    elapsedMs: typeof seed.elapsedMs === 'number' ? seed.elapsedMs : undefined,
  };
}

function normalizeAiGridSeed(candidate: unknown): AiGridSeed {
  const seed = normalizeOpenCvDetectionSeed(candidate);
  const extras = candidate && typeof candidate === 'object' ? candidate as Partial<AiGridSeed> : {};
  return {
    ...seed,
    modeId: typeof extras.modeId === 'string' ? extras.modeId : undefined,
    modeLabel: typeof extras.modeLabel === 'string' ? extras.modeLabel : undefined,
    riskLevel: typeof extras.riskLevel === 'string' ? extras.riskLevel : undefined,
    explanation: typeof extras.explanation === 'string' ? extras.explanation : undefined,
    selectedModeId: typeof extras.selectedModeId === 'string' ? extras.selectedModeId : undefined,
    gridBounds: normalizeAiGridBounds(extras.gridBounds),
    gridHomography: normalizeHomography(extras.gridHomography),
    dotVariantId: typeof extras.dotVariantId === 'string' ? extras.dotVariantId : undefined,
    decision: typeof extras.decision === 'string' ? extras.decision : undefined,
    projectionReadinessMode: typeof extras.projectionReadinessMode === 'string'
      ? extras.projectionReadinessMode
      : undefined,
    noLabelProjectionReadinessMode: typeof extras.noLabelProjectionReadinessMode === 'string'
      ? extras.noLabelProjectionReadinessMode
      : undefined,
    fullSpanHomographyLineWithin0_15Pct: typeof extras.fullSpanHomographyLineWithin0_15Pct === 'number'
      ? extras.fullSpanHomographyLineWithin0_15Pct
      : undefined,
    observedEdgeHomographyLineWithin0_15Pct: typeof extras.observedEdgeHomographyLineWithin0_15Pct === 'number'
      ? extras.observedEdgeHomographyLineWithin0_15Pct
      : undefined,
    visibleMeshLineWithin0_15Pct: typeof extras.visibleMeshLineWithin0_15Pct === 'number'
      ? extras.visibleMeshLineWithin0_15Pct
      : undefined,
    visibleMeshCells: typeof extras.visibleMeshCells === 'number' ? extras.visibleMeshCells : undefined,
    unsupportedCellCount: typeof extras.unsupportedCellCount === 'number' ? extras.unsupportedCellCount : undefined,
    visibleMeshCellDensity: typeof extras.visibleMeshCellDensity === 'number'
      ? extras.visibleMeshCellDensity
      : undefined,
    sourceForegroundTrimmedCells: typeof extras.sourceForegroundTrimmedCells === 'number'
      ? extras.sourceForegroundTrimmedCells
      : undefined,
    supportOverlay: normalizeAiSupportOverlay(extras.supportOverlay),
  };
}

function normalizeAiGridBounds(value: unknown): AiGridBounds | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const bounds = value as Partial<AiGridBounds>;
  if (
    typeof bounds.minI !== 'number'
    || typeof bounds.maxI !== 'number'
    || typeof bounds.minJ !== 'number'
    || typeof bounds.maxJ !== 'number'
  ) {
    return undefined;
  }
  return {
    minI: bounds.minI,
    maxI: bounds.maxI,
    minJ: bounds.minJ,
    maxJ: bounds.maxJ,
  };
}

function normalizeHomography(value: unknown): Homography | undefined {
  if (!Array.isArray(value) || value.length !== 9) return undefined;
  return value.every((item) => typeof item === 'number' && Number.isFinite(item))
    ? value as Homography
    : undefined;
}

function normalizeAiSupportOverlay(value: unknown): AiGridSupportOverlay | undefined {
  if (!value || typeof value !== 'object') return undefined;
  const overlay = value as Partial<AiGridSupportOverlay>;
  const cells = Array.isArray(overlay.cells)
    ? overlay.cells.flatMap((cell) => {
        if (!cell || typeof cell !== 'object') return [];
        const maybeCell = cell as { i?: unknown; j?: unknown; corners?: unknown };
        const corners = normalizeOpenCvCorners(maybeCell.corners);
        if (!corners) return [];
        return [{
          i: typeof maybeCell.i === 'number' ? maybeCell.i : 0,
          j: typeof maybeCell.j === 'number' ? maybeCell.j : 0,
          corners,
        }];
      })
    : [];
  return {
    vertexCount: typeof overlay.vertexCount === 'number' ? overlay.vertexCount : 0,
    cellCount: typeof overlay.cellCount === 'number' ? overlay.cellCount : cells.length,
    cells,
  };
}

function selectedAiGridMode(): string {
  return document.querySelector<HTMLSelectElement>('#ai-seed-mode')?.value ?? 'grid-frame';
}

function normalizeOpenCvCorners(corners: unknown): [Point, Point, Point, Point] | undefined {
  if (!Array.isArray(corners) || corners.length !== 4) return undefined;
  const points = corners.map((point) => {
    if (!point || typeof point !== 'object') return null;
    const maybePoint = point as Partial<Point>;
    return typeof maybePoint.x === 'number' && typeof maybePoint.y === 'number'
      ? { x: maybePoint.x, y: maybePoint.y }
      : null;
  });
  return points.every(Boolean) ? points as [Point, Point, Point, Point] : undefined;
}

function scaleDetectionCorners(seed: OpenCvDetectionSeed, image: HTMLImageElement): [Point, Point, Point, Point] {
  if (!seed.corners) throw new Error('OpenCV detector returned no corners.');
  const sourceWidth = seed.imageWidth || image.naturalWidth;
  const sourceHeight = seed.imageHeight || image.naturalHeight;
  const scaleX = image.naturalWidth / Math.max(1, sourceWidth);
  const scaleY = image.naturalHeight / Math.max(1, sourceHeight);
  return seed.corners.map((point) => ({
    x: point.x * scaleX,
    y: point.y * scaleY,
  })) as [Point, Point, Point, Point];
}

function trimAiSeedAgainstSourceImage(seed: AiGridSeed, image: HTMLImageElement): AiGridSeed {
  if (
    seed.modeId !== 'supported'
    || !seed.supportOverlay
    || !seed.gridHomography
    || seed.supportOverlay.cells.length === 0
  ) {
    return seed;
  }

  const sampler = createSourceImageSampler(image);
  const keptCells = seed.supportOverlay.cells.filter((cell) => isLikelyVisibleMatCell(cell, sampler));
  const trimmedCells = seed.supportOverlay.cells.length - keptCells.length;
  if (trimmedCells <= 0 || keptCells.length < 8) return seed;

  const materialBounds = trimBoundsToVisibleMaterial(seed.gridHomography, boundsFromSupportCells(keptCells), sampler);
  const boundedCells = keptCells.filter((cell) => isCellInsideBounds(cell, materialBounds));
  if (boundedCells.length < 8) return seed;
  const corners = cornersFromGridBounds(seed.gridHomography, materialBounds);
  return {
    ...seed,
    corners,
    columns: Math.max(1, materialBounds.maxI - materialBounds.minI),
    rows: Math.max(1, materialBounds.maxJ - materialBounds.minJ),
    gridBounds: materialBounds,
    sourceForegroundTrimmedCells: seed.supportOverlay.cells.length - boundedCells.length,
    supportOverlay: {
      ...seed.supportOverlay,
      cellCount: boundedCells.length,
      cells: boundedCells,
    },
  };
}

function createSourceImageSampler(image: HTMLImageElement): (point: Point) => [number, number, number, number] {
  const maxSide = 1100;
  const scale = Math.min(1, maxSide / Math.max(image.naturalWidth, image.naturalHeight));
  const width = Math.max(1, Math.round(image.naturalWidth * scale));
  const height = Math.max(1, Math.round(image.naturalHeight * scale));
  const canvasElement = document.createElement('canvas');
  canvasElement.width = width;
  canvasElement.height = height;
  const context = canvasElement.getContext('2d', { willReadFrequently: true });
  if (!context) return () => [0, 0, 0, 0];
  context.drawImage(image, 0, 0, width, height);
  return (point: Point) => {
    const x = clampInteger(Math.round(point.x * scale), 0, width - 1);
    const y = clampInteger(Math.round(point.y * scale), 0, height - 1);
    const data = context.getImageData(x, y, 1, 1).data;
    return [data[0], data[1], data[2], data[3]];
  };
}

function isLikelyVisibleMatCell(
  cell: AiGridSupportOverlay['cells'][number],
  sampler: (point: Point) => [number, number, number, number],
): boolean {
  const samples = [
    interpolateCellPoint(cell.corners, 0.5, 0.5),
    interpolateCellPoint(cell.corners, 0.25, 0.25),
    interpolateCellPoint(cell.corners, 0.75, 0.25),
    interpolateCellPoint(cell.corners, 0.75, 0.75),
    interpolateCellPoint(cell.corners, 0.25, 0.75),
  ];
  const visibleMatSamples = samples.filter((point) => isLikelyVisibleMatPixel(sampler(point))).length;
  return visibleMatSamples >= 3;
}

function interpolateCellPoint(corners: [Point, Point, Point, Point], u: number, v: number): Point {
  const [a, b, c, d] = corners;
  const top = { x: a.x + (b.x - a.x) * u, y: a.y + (b.y - a.y) * u };
  const bottom = { x: d.x + (c.x - d.x) * u, y: d.y + (c.y - d.y) * u };
  return {
    x: top.x + (bottom.x - top.x) * v,
    y: top.y + (bottom.y - top.y) * v,
  };
}

function isLikelyVisibleMatPixel([red, green, blue, alpha]: [number, number, number, number]): boolean {
  if (alpha < 64) return false;
  const brightness = (red + green + blue) / 3;
  if (brightness < 58) return false;
  const greenDominant = green > red * 1.16 && green > blue * 1.08 && green - red > 22;
  if (greenDominant) return false;
  const darkSaturated = brightness < 95 && Math.max(red, green, blue) - Math.min(red, green, blue) > 45;
  if (darkSaturated) return false;
  return true;
}

function boundsFromSupportCells(cells: AiGridSupportOverlay['cells']): AiGridBounds {
  return {
    minI: Math.min(...cells.map((cell) => cell.i)),
    maxI: Math.max(...cells.map((cell) => cell.i + 1)),
    minJ: Math.min(...cells.map((cell) => cell.j)),
    maxJ: Math.max(...cells.map((cell) => cell.j + 1)),
  };
}

function trimBoundsToVisibleMaterial(
  homography: Homography,
  bounds: AiGridBounds,
  sampler: (point: Point) => [number, number, number, number],
): AiGridBounds {
  const next = { ...bounds };
  for (let iteration = 0; iteration < 80; iteration += 1) {
    let changed = false;
    if (next.maxI - next.minI > 4 && edgeMaterialRatio(homography, next, 'left', sampler) < 0.88) {
      next.minI += 1;
      changed = true;
    }
    if (next.maxI - next.minI > 4 && edgeMaterialRatio(homography, next, 'right', sampler) < 0.88) {
      next.maxI -= 1;
      changed = true;
    }
    if (next.maxJ - next.minJ > 4 && edgeMaterialRatio(homography, next, 'top', sampler) < 0.88) {
      next.minJ += 1;
      changed = true;
    }
    if (next.maxJ - next.minJ > 4 && edgeMaterialRatio(homography, next, 'bottom', sampler) < 0.88) {
      next.maxJ -= 1;
      changed = true;
    }
    if (!changed) break;
  }
  return next;
}

function edgeMaterialRatio(
  homography: Homography,
  bounds: AiGridBounds,
  edge: 'left' | 'right' | 'top' | 'bottom',
  sampler: (point: Point) => [number, number, number, number],
): number {
  const points: Point[] = [];
  if (edge === 'left' || edge === 'right') {
    const x = edge === 'left' ? bounds.minI : bounds.maxI;
    for (let y = bounds.minJ; y <= bounds.maxJ; y += 0.5) points.push({ x, y });
  } else {
    const y = edge === 'top' ? bounds.minJ : bounds.maxJ;
    for (let x = bounds.minI; x <= bounds.maxI; x += 0.5) points.push({ x, y });
  }
  if (points.length === 0) return 0;
  const materialCount = points.filter((point) => isLikelyVisibleMatPixel(sampler(applyHomography(homography, point)))).length;
  return materialCount / points.length;
}

function isCellInsideBounds(cell: AiGridSupportOverlay['cells'][number], bounds: AiGridBounds): boolean {
  return cell.i >= bounds.minI
    && cell.i + 1 <= bounds.maxI
    && cell.j >= bounds.minJ
    && cell.j + 1 <= bounds.maxJ;
}

function cornersFromGridBounds(homography: Homography, bounds: AiGridBounds): [Point, Point, Point, Point] {
  return [
    applyHomography(homography, { x: bounds.minI, y: bounds.minJ }),
    applyHomography(homography, { x: bounds.maxI, y: bounds.minJ }),
    applyHomography(homography, { x: bounds.maxI, y: bounds.maxJ }),
    applyHomography(homography, { x: bounds.minI, y: bounds.maxJ }),
  ];
}

async function saveCurrentFixture(): Promise<void> {
  if (!currentLabel) return;
  const nextLabel = normalizeCurrentLabel(currentLabel);
  const nextFile = upsertFixtureLabel(labelFile, nextLabel);
  try {
    const response = await fetch(LABEL_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(nextFile, null, 2),
    });
    if (!response.ok) throw new Error(await response.text());
    labelFile = nextFile;
    currentLabel = cloneLabel(nextLabel);
    dirty = false;
    persistDraftToLocalStorage();
    syncControls();
    render();
    setStatus(`Saved ${currentLabel.sourceName}. This fixture is now labeled.`, 'success');
  } catch (error) {
    setStatus(`Saved draft in browser, but repo write failed: ${(error as Error).message}`, 'warning');
  }
}

async function loadLabelFile(): Promise<GridFixtureLabelFile> {
  try {
    const response = await fetch(LABEL_ENDPOINT);
    if (response.ok) return normalizeLabelFile(await response.json());
  } catch {
    // Fall back to browser storage below.
  }

  const local = window.localStorage.getItem(LABEL_STORAGE_KEY);
  return local ? normalizeLabelFile(JSON.parse(local)) : structuredClone(EMPTY_LABEL_FILE);
}

function upsertCurrentDraft(): void {
  if (!currentLabel) return;
  currentLabel = normalizeCurrentLabel(currentLabel);
  labelFile = upsertFixtureLabel(labelFile, currentLabel);
  persistDraftToLocalStorage();
}

function normalizeCurrentLabel(label: GridFixtureLabel): GridFixtureLabel {
  return {
    ...label,
    corners: cloneCorners(label.corners),
    columns: clampInteger(label.columns, 1, 120),
    rows: clampInteger(label.rows, 1, 120),
    labeledAt: label.labeledAt || new Date().toISOString(),
  };
}

function persistDraftToLocalStorage(): void {
  window.localStorage.setItem(LABEL_STORAGE_KEY, JSON.stringify(labelFile));
}

function markDirty(message: string): void {
  dirty = true;
  if (currentLabel) currentLabel.labeledAt = new Date().toISOString();
  syncControls();
  setStatus(`${message} Unsaved changes.`, 'warning');
  render();
}

function adjustGridSize(field: 'columns' | 'rows', delta: number): void {
  if (!currentLabel) return;
  currentLabel[field] = clampInteger(currentLabel[field] + delta, 1, 120);
  markDirty(`${field === 'columns' ? 'Columns' : 'Rows'} updated.`);
}

function setVirtualGridVisible(visible: boolean): void {
  showVirtualGrid = visible;
  window.localStorage.setItem(LABELER_GRID_VISIBILITY_KEY, String(showVirtualGrid));
  syncControls();
  render();
}

function setFitView(): void {
  if (!selectedImage) return;
  viewState = {
    mode: 'fit',
    scale: 1,
    center: { x: selectedImage.naturalWidth / 2, y: selectedImage.naturalHeight / 2 },
  };
  syncZoomControls();
  render();
}

function setManualZoom(scale: number, center: Point): void {
  if (!selectedImage || !currentLabel) return;
  const rect = canvas.getBoundingClientRect();
  const baseFit = labelViewportFit(selectedImage, currentLabel, rect.width, rect.height);
  const nextScale = clampNumber(scale, baseFit.scale, 3);
  viewState = {
    mode: 'manual',
    scale: nextScale,
    center: clampViewCenter(center, nextScale, rect.width, rect.height),
  };
  syncZoomControls();
  render();
}

function zoomAtCanvasCenter(factor: number): void {
  const rect = canvas.getBoundingClientRect();
  zoomAtCanvasPoint({ x: rect.width / 2, y: rect.height / 2 }, factor);
}

function zoomAtCanvasPoint(canvasPoint: Point, factor: number): void {
  if (!selectedImage || !currentLabel) return;
  const rect = canvas.getBoundingClientRect();
  const fit = currentLabelViewportFit(selectedImage, currentLabel, rect.width, rect.height);
  const anchor = canvasToNatural(canvasPoint, fit);
  const baseFit = labelViewportFit(selectedImage, currentLabel, rect.width, rect.height);
  const nextScale = clampNumber(fit.scale * factor, baseFit.scale, 3);
  const nextCenter = {
    x: anchor.x - (canvasPoint.x - rect.width / 2) / nextScale,
    y: anchor.y - (canvasPoint.y - rect.height / 2) / nextScale,
  };
  viewState = {
    mode: nextScale <= baseFit.scale * 1.01 ? 'fit' : 'manual',
    scale: nextScale,
    center: clampViewCenter(nextCenter, nextScale, rect.width, rect.height),
  };
  syncZoomControls();
  render();
}

function activeViewFocusPoint(): Point {
  if (currentLabel) return currentLabel.corners[activeCornerIndex];
  if (selectedImage) return { x: selectedImage.naturalWidth / 2, y: selectedImage.naturalHeight / 2 };
  return { x: 0, y: 0 };
}

function currentViewCenter(): Point {
  if (viewState.mode === 'manual') return viewState.center;
  return activeViewFocusPoint();
}

function startPan(event: PointerEvent): void {
  if (!selectedImage || !currentLabel) return;
  const rect = canvas.getBoundingClientRect();
  const fit = currentLabelViewportFit(selectedImage, currentLabel, rect.width, rect.height);
  panState = {
    pointerId: event.pointerId,
    startPointer: { x: event.clientX, y: event.clientY },
    startCenter: viewState.mode === 'manual' ? viewState.center : currentViewCenter(),
    scale: fit.scale,
  };
  canvas.setPointerCapture(event.pointerId);
  canvas.focus({ preventScroll: true });
  updatePointerState();
  render();
}

function updatePan(event: PointerEvent): void {
  if (!panState) return;
  const rect = canvas.getBoundingClientRect();
  const deltaX = event.clientX - panState.startPointer.x;
  const deltaY = event.clientY - panState.startPointer.y;
  viewState = {
    mode: 'manual',
    scale: panState.scale,
    center: clampViewCenter({
      x: panState.startCenter.x - deltaX / panState.scale,
      y: panState.startCenter.y - deltaY / panState.scale,
    }, panState.scale, rect.width, rect.height),
  };
  syncZoomControls();
  render();
}

function isTextEntryTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tagName = target.tagName.toLowerCase();
  if (target instanceof HTMLInputElement) {
    return !['button', 'checkbox', 'radio', 'range', 'reset', 'submit'].includes(target.type);
  }
  return target.isContentEditable
    || tagName === 'textarea'
    || tagName === 'select';
}

function syncControls(): void {
  if (!currentLabel) return;
  setInputValue('#label-columns', String(currentLabel.columns));
  setInputValue('#label-rows', String(currentLabel.rows));
  const benchmark = document.querySelector<HTMLInputElement>('#label-benchmark');
  if (benchmark) benchmark.checked = currentLabel.benchmark;
  const gridToggle = document.querySelector<HTMLInputElement>('#show-label-grid');
  if (gridToggle) gridToggle.checked = showVirtualGrid;
  const aiSupportToggle = document.querySelector<HTMLInputElement>('#show-ai-support');
  if (aiSupportToggle) {
    aiSupportToggle.checked = showAiSupportOverlay;
    aiSupportToggle.disabled = !activeAiSupportOverlay;
  }
  syncZoomControls();
  const title = document.querySelector<HTMLHeadingElement>('#fixture-title');
  if (title) title.textContent = currentLabel.sourceName;
  const meta = document.querySelector<HTMLParagraphElement>('#fixture-meta');
  if (meta) {
    const saved = findFixtureLabel(labelFile, currentLabel.sourceId);
    const extrapolated = isExtrapolatedLabel(currentLabel) ? ' | extrapolated grid' : '';
    meta.textContent = `${selectedIndex + 1} of ${sampleImages.length} | ${currentLabel.imageWidth} x ${currentLabel.imageHeight} | ${saved ? 'labeled' : 'unlabeled'}${extrapolated}${dirty ? ' | unsaved changes' : ''}`;
  }
  syncCornerButtons();
  renderCornerTable();
}

function syncZoomControls(): void {
  const zoomInput = document.querySelector<HTMLInputElement>('#label-zoom');
  const readout = document.querySelector<HTMLSpanElement>('#zoom-readout');
  const nativeReadout = document.querySelector<HTMLSpanElement>('#native-readout');
  if (!zoomInput || !readout) return;
  const rect = canvas.getBoundingClientRect();
  const fit = selectedImage && currentLabel
    ? currentLabelViewportFit(selectedImage, currentLabel, Math.max(1, rect.width), Math.max(1, rect.height))
    : null;
  const scale = fit?.scale ?? 1;
  const value = String(roundForDisplay(scale));
  if (zoomInput.value !== value) zoomInput.value = value;
  readout.textContent = viewState.mode === 'fit' ? `Fit ${Math.round(scale * 100)}%` : `${Math.round(scale * 100)}%`;
  if (nativeReadout && selectedImage) {
    nativeReadout.textContent = `Native ${selectedImage.naturalWidth} x ${selectedImage.naturalHeight}`;
  }
}

function syncCornerButtons(): void {
  document.querySelectorAll<HTMLButtonElement>('[data-corner]').forEach((button) => {
    button.classList.toggle('selected', Number(button.dataset.corner ?? 0) === activeCornerIndex);
  });
}

function renderCornerTable(): void {
  const table = document.querySelector<HTMLDivElement>('#corner-table');
  if (!table || !currentLabel) return;
  table.innerHTML = currentLabel.corners.map((corner, index) => `
    <div class="labeler-corner-row${index === activeCornerIndex ? ' active' : ''}">
      <strong>${String.fromCharCode(65 + index)}</strong>
      <span>x ${Math.round(corner.x)}</span>
      <span>y ${Math.round(corner.y)}</span>
    </div>
  `).join('');
}

function render(): void {
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(1, Math.round(rect.width));
  const height = Math.max(1, Math.round(rect.height));
  const dpr = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  const context = canvas.getContext('2d');
  if (!context) return;
  context.setTransform(dpr, 0, 0, dpr, 0, 0);
  context.clearRect(0, 0, width, height);
  context.fillStyle = '#151714';
  context.fillRect(0, 0, width, height);

  if (!selectedImage || !currentLabel) {
    delete canvas.dataset.gridOverlay;
    delete canvas.dataset.aiSupportOverlay;
    delete canvas.dataset.labelViewport;
    delete canvas.dataset.extrapolatedGrid;
    delete canvas.dataset.viewMode;
    delete canvas.dataset.zoomScale;
    return;
  }

  const fit = dragViewportFit ?? currentLabelViewportFit(selectedImage, currentLabel, width, height);
  const imageTopLeft = naturalToCanvas({ x: 0, y: 0 }, fit);
  context.imageSmoothingEnabled = fit.scale < 1;
  context.drawImage(
    selectedImage,
    imageTopLeft.x,
    imageTopLeft.y,
    selectedImage.naturalWidth * fit.scale,
    selectedImage.naturalHeight * fit.scale,
  );
  drawSourceImageFrame(context, selectedImage, fit);
  canvas.dataset.gridOverlay = showVirtualGrid ? 'visible' : 'hidden';
  canvas.dataset.aiSupportOverlay = activeAiSupportOverlay && showAiSupportOverlay ? 'visible' : 'hidden';
  canvas.dataset.labelViewport = JSON.stringify(fit);
  canvas.dataset.extrapolatedGrid = isExtrapolatedLabel(currentLabel) ? 'true' : 'false';
  canvas.dataset.viewMode = viewState.mode;
  canvas.dataset.zoomScale = String(roundForDisplay(fit.scale));
  drawAiSupportOverlay(context, activeAiSupportOverlay, fit);
  drawLabelGrid(context, currentLabel, fit, selectedImage);
  drawDragMagnifier(context, currentLabel, fit, width, height);
}

function drawAiSupportOverlay(
  context: CanvasRenderingContext2D,
  overlay: AiGridSupportOverlay | null,
  fit: LabelViewportFit,
): void {
  if (!overlay || !showAiSupportOverlay) return;
  context.save();
  context.fillStyle = 'rgba(41, 135, 255, 0.16)';
  context.strokeStyle = 'rgba(41, 135, 255, 0.55)';
  context.lineWidth = 1;
  for (const cell of overlay.cells) {
    const corners = cell.corners.map((corner) => naturalToCanvas(corner, fit));
    context.beginPath();
    corners.forEach((corner, index) => {
      if (index === 0) context.moveTo(corner.x, corner.y);
      else context.lineTo(corner.x, corner.y);
    });
    context.closePath();
    context.fill();
    context.stroke();
  }
  context.restore();
}

function drawLabelGrid(
  context: CanvasRenderingContext2D,
  label: GridFixtureLabel,
  fit: LabelViewportFit,
  image: HTMLImageElement,
): void {
  const corners = label.corners.map((corner) => naturalToCanvas(corner, fit)) as [Point, Point, Point, Point];
  const gridToNatural = solveHomography(
    [
      { x: 0, y: 0 },
      { x: label.columns, y: 0 },
      { x: label.columns, y: label.rows },
      { x: 0, y: label.rows },
    ],
    label.corners,
  );
  const projectNatural = (point: Point) => applyHomography(gridToNatural, point);
  const project = (point: Point) => naturalToCanvas(projectNatural(point), fit);

  if (showVirtualGrid) {
    context.save();
    context.strokeStyle = 'rgba(0, 143, 100, 0.20)';
    context.lineWidth = 1;
    drawGridLines(context, label, project);
    context.restore();

    context.save();
    clipToSourceImageFrame(context, image, fit);
    context.strokeStyle = 'rgba(0, 143, 100, 0.95)';
    context.lineWidth = 1.7;
    drawGridLines(context, label, project);
    context.restore();

    context.save();
    context.strokeStyle = 'rgba(255, 255, 255, 0.32)';
    context.lineWidth = 2;
    drawGridOutline(context, corners);
    context.restore();

    context.save();
    clipToSourceImageFrame(context, image, fit);
    context.strokeStyle = 'rgba(255, 255, 255, 0.95)';
    context.lineWidth = 3;
    drawGridOutline(context, corners);
    context.restore();
  }

  drawEdgeHandles(context, corners);

  corners.forEach((corner, index) => {
    const active = index === activeCornerIndex;
    context.fillStyle = active ? '#f5a623' : '#ff6b35';
    context.strokeStyle = '#ffffff';
    context.lineWidth = active ? 4 : 2;
    context.beginPath();
    context.arc(corner.x, corner.y, active ? 11 : 8, 0, Math.PI * 2);
    context.fill();
    context.stroke();
    context.fillStyle = '#ffffff';
    context.font = '700 14px system-ui, sans-serif';
    context.fillText(String.fromCharCode(65 + index), corner.x + 13, corner.y - 10);
  });
}

function drawGridLines(
  context: CanvasRenderingContext2D,
  label: GridFixtureLabel,
  project: (point: Point) => Point,
): void {
  for (let column = 0; column <= label.columns; column += 1) {
    drawProjectedSegment(
      context,
      project({ x: column, y: 0 }),
      project({ x: column, y: label.rows }),
    );
  }
  for (let row = 0; row <= label.rows; row += 1) {
    drawProjectedSegment(
      context,
      project({ x: 0, y: row }),
      project({ x: label.columns, y: row }),
    );
  }
}

function drawProjectedSegment(context: CanvasRenderingContext2D, start: Point, end: Point): void {
  context.beginPath();
  context.moveTo(start.x, start.y);
  context.lineTo(end.x, end.y);
  context.stroke();
}

function drawGridOutline(
  context: CanvasRenderingContext2D,
  corners: [Point, Point, Point, Point],
): void {
  context.beginPath();
  corners.forEach((corner, index) => {
    if (index === 0) context.moveTo(corner.x, corner.y);
    else context.lineTo(corner.x, corner.y);
  });
  context.closePath();
  context.stroke();
}

function clipToSourceImageFrame(
  context: CanvasRenderingContext2D,
  image: HTMLImageElement,
  fit: LabelViewportFit,
): void {
  const topLeft = naturalToCanvas({ x: 0, y: 0 }, fit);
  context.beginPath();
  context.rect(
    topLeft.x,
    topLeft.y,
    image.naturalWidth * fit.scale,
    image.naturalHeight * fit.scale,
  );
  context.clip();
}

function drawEdgeHandles(
  context: CanvasRenderingContext2D,
  corners: [Point, Point, Point, Point],
): void {
  EDGE_DEFINITIONS.forEach((edge, index) => {
    const a = corners[edge.cornerIndexes[0]];
    const b = corners[edge.cornerIndexes[1]];
    const midpoint = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    const active = index === dragEdgeIndex;
    context.save();
    context.translate(midpoint.x, midpoint.y);
    if (edge.axis === 'x') context.rotate(Math.PI / 2);
    context.fillStyle = active ? '#f5a623' : '#ff6b35';
    context.strokeStyle = '#ffffff';
    context.lineWidth = active ? 4 : 2;
    context.beginPath();
    context.rect(-18, -6, 36, 12);
    context.fill();
    context.stroke();
    context.restore();
  });
}

function drawDragMagnifier(
  context: CanvasRenderingContext2D,
  label: GridFixtureLabel,
  fit: LabelViewportFit,
  canvasWidth: number,
  canvasHeight: number,
): void {
  if (dragCornerIndex === null || !selectedImage) return;

  const focus = label.corners[dragCornerIndex];
  const focusCanvas = naturalToCanvas(focus, fit);
  const maxDiameter = Math.max(140, Math.min(canvasWidth, canvasHeight) - 40);
  const preferredDiameter = Math.max(320, Math.min(460, Math.min(canvasWidth, canvasHeight) * 0.58));
  const diameter = Math.min(maxDiameter, preferredDiameter);
  const radius = diameter / 2;
  const margin = 20;
  const center = {
    x: focusCanvas.x < canvasWidth / 2 ? canvasWidth - radius - margin : radius + margin,
    y: focusCanvas.y < canvasHeight / 2 ? canvasHeight - radius - margin : radius + margin,
  };
  const zoomScale = 6;
  const sourceHalfWidth = radius / zoomScale;
  const sourceLeft = clampNumber(focus.x - sourceHalfWidth, 0, selectedImage.naturalWidth);
  const sourceTop = clampNumber(focus.y - sourceHalfWidth, 0, selectedImage.naturalHeight);
  const sourceRight = clampNumber(focus.x + sourceHalfWidth, 0, selectedImage.naturalWidth);
  const sourceBottom = clampNumber(focus.y + sourceHalfWidth, 0, selectedImage.naturalHeight);
  const sourceWidth = sourceRight - sourceLeft;
  const sourceHeight = sourceBottom - sourceTop;

  context.save();
  context.shadowColor = 'rgba(0, 0, 0, 0.38)';
  context.shadowBlur = 18;
  context.shadowOffsetY = 8;
  context.fillStyle = 'rgba(255, 252, 245, 0.88)';
  context.beginPath();
  context.arc(center.x, center.y, radius + 5, 0, Math.PI * 2);
  context.fill();
  context.restore();

  context.save();
  context.beginPath();
  context.arc(center.x, center.y, radius, 0, Math.PI * 2);
  context.clip();
  context.fillStyle = '#151714';
  context.fillRect(center.x - radius, center.y - radius, diameter, diameter);
  context.imageSmoothingEnabled = false;
  if (sourceWidth > 0 && sourceHeight > 0) {
    context.drawImage(
      selectedImage,
      sourceLeft,
      sourceTop,
      sourceWidth,
      sourceHeight,
      center.x + (sourceLeft - focus.x) * zoomScale,
      center.y + (sourceTop - focus.y) * zoomScale,
      sourceWidth * zoomScale,
      sourceHeight * zoomScale,
    );
  }
  if (showVirtualGrid) drawMagnifiedGrid(context, label, center, focus, zoomScale);
  drawReticle(context, center, radius);
  context.restore();

  context.save();
  context.strokeStyle = 'rgba(255, 255, 255, 0.9)';
  context.lineWidth = 3;
  context.beginPath();
  context.arc(center.x, center.y, radius, 0, Math.PI * 2);
  context.stroke();
  context.restore();
}

function drawMagnifiedGrid(
  context: CanvasRenderingContext2D,
  label: GridFixtureLabel,
  center: Point,
  focus: Point,
  zoomScale: number,
): void {
  const gridToNatural = solveHomography(
    [
      { x: 0, y: 0 },
      { x: label.columns, y: 0 },
      { x: label.columns, y: label.rows },
      { x: 0, y: label.rows },
    ],
    label.corners,
  );
  const project = (point: Point) => magnifyPoint(applyHomography(gridToNatural, point), center, focus, zoomScale);

  context.save();
  context.strokeStyle = 'rgba(0, 143, 100, 0.82)';
  context.lineWidth = 1;
  for (let column = 0; column <= label.columns; column += 1) {
    const top = project({ x: column, y: 0 });
    const bottom = project({ x: column, y: label.rows });
    context.beginPath();
    context.moveTo(top.x, top.y);
    context.lineTo(bottom.x, bottom.y);
    context.stroke();
  }
  for (let row = 0; row <= label.rows; row += 1) {
    const left = project({ x: 0, y: row });
    const right = project({ x: label.columns, y: row });
    context.beginPath();
    context.moveTo(left.x, left.y);
    context.lineTo(right.x, right.y);
    context.stroke();
  }
  context.restore();
}

function drawReticle(
  context: CanvasRenderingContext2D,
  center: Point,
  radius: number,
): void {
  context.save();
  context.globalAlpha = 0.58;
  context.strokeStyle = '#ffffff';
  context.lineWidth = 2;
  context.beginPath();
  context.arc(center.x, center.y, 30, 0, Math.PI * 2);
  context.stroke();
  context.beginPath();
  context.arc(center.x, center.y, 7, 0, Math.PI * 2);
  context.stroke();
  context.beginPath();
  context.moveTo(center.x - radius + 18, center.y);
  context.lineTo(center.x - 10, center.y);
  context.moveTo(center.x + 10, center.y);
  context.lineTo(center.x + radius - 18, center.y);
  context.moveTo(center.x, center.y - radius + 18);
  context.lineTo(center.x, center.y - 10);
  context.moveTo(center.x, center.y + 10);
  context.lineTo(center.x, center.y + radius - 18);
  context.stroke();

  context.strokeStyle = '#ff6b35';
  context.lineWidth = 3;
  context.beginPath();
  context.moveTo(center.x - 22, center.y);
  context.lineTo(center.x + 22, center.y);
  context.moveTo(center.x, center.y - 22);
  context.lineTo(center.x, center.y + 22);
  context.stroke();
  context.restore();
}

function magnifyPoint(point: Point, center: Point, focus: Point, zoomScale: number): Point {
  return {
    x: center.x + (point.x - focus.x) * zoomScale,
    y: center.y + (point.y - focus.y) * zoomScale,
  };
}

function createDefaultLabel(identity: GridFixtureIdentity, image: HTMLImageElement): GridFixtureLabel {
  const insetX = image.naturalWidth * 0.08;
  const insetY = image.naturalHeight * 0.08;
  return {
    ...identity,
    imageWidth: image.naturalWidth,
    imageHeight: image.naturalHeight,
    corners: [
      { x: insetX, y: insetY },
      { x: image.naturalWidth - insetX, y: insetY },
      { x: image.naturalWidth - insetX, y: image.naturalHeight - insetY },
      { x: insetX, y: image.naturalHeight - insetY },
    ],
    columns: 12,
    rows: 8,
    benchmark: true,
    labeledAt: new Date().toISOString(),
  };
}

function currentIdentity(): GridFixtureIdentity {
  return sampleToFixtureIdentity(sampleImages[selectedIndex]);
}

function findNextUnlabeledIndex(): number {
  for (let offset = 1; offset <= sampleImages.length; offset += 1) {
    const index = (selectedIndex + offset) % sampleImages.length;
    const identity = sampleToFixtureIdentity(sampleImages[index]);
    if (!findFixtureLabel(labelFile, identity.sourceId)) return index;
  }
  return (selectedIndex + 1) % sampleImages.length;
}

function findNearestCorner(event: PointerEvent): number | null {
  if (!selectedImage || !currentLabel) return null;
  const rect = canvas.getBoundingClientRect();
  const fit = currentLabelViewportFit(selectedImage, currentLabel, rect.width, rect.height);
  const pointer = { x: event.clientX - rect.left, y: event.clientY - rect.top };
  let nearestIndex: number | null = null;
  let nearestDistance = 28;
  currentLabel.corners.forEach((corner, index) => {
    const canvasPoint = naturalToCanvas(corner, fit);
    const distance = Math.hypot(canvasPoint.x - pointer.x, canvasPoint.y - pointer.y);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestIndex = index;
    }
  });
  return nearestIndex;
}

function findNearestEdgeHandle(event: PointerEvent): number | null {
  if (!selectedImage || !currentLabel) return null;
  const rect = canvas.getBoundingClientRect();
  const fit = currentLabelViewportFit(selectedImage, currentLabel, rect.width, rect.height);
  const pointer = { x: event.clientX - rect.left, y: event.clientY - rect.top };
  const corners = currentLabel.corners.map((corner) => naturalToCanvas(corner, fit)) as [Point, Point, Point, Point];
  let nearestIndex: number | null = null;
  let nearestDistance = 26;
  EDGE_DEFINITIONS.forEach((edge, index) => {
    const a = corners[edge.cornerIndexes[0]];
    const b = corners[edge.cornerIndexes[1]];
    const midpoint = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
    const distance = Math.hypot(midpoint.x - pointer.x, midpoint.y - pointer.y);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestIndex = index;
    }
  });
  return nearestIndex;
}

function updateEdgeDrag(event: PointerEvent): void {
  if (!currentLabel || dragEdgeIndex === null || !dragStartPoint || !dragStartCorners) return;
  const point = pointerToNaturalPoint(event);
  if (!point) return;
  const edge = EDGE_DEFINITIONS[dragEdgeIndex];
  const startCorners = dragStartCorners;
  const delta = edge.axis === 'x'
    ? point.x - dragStartPoint.x
    : point.y - dragStartPoint.y;
  const nextCorners = cloneCorners(startCorners);
  edge.cornerIndexes.forEach((cornerIndex) => {
    if (edge.axis === 'x') {
      nextCorners[cornerIndex].x = startCorners[cornerIndex].x + delta;
    } else {
      nextCorners[cornerIndex].y = startCorners[cornerIndex].y + delta;
    }
  });
  currentLabel.corners = nextCorners;
  markDirty('Grid edge moved.');
}

function pointerToNaturalPoint(event: PointerEvent): Point | null {
  if (!selectedImage || !currentLabel) return null;
  const rect = canvas.getBoundingClientRect();
  if (dragViewportFit) autoPanDragViewport(event, rect);
  const fit = dragViewportFit ?? currentLabelViewportFit(selectedImage, currentLabel, rect.width, rect.height);
  return canvasToNatural({
    x: clampNumber(event.clientX - rect.left, 0, rect.width),
    y: clampNumber(event.clientY - rect.top, 0, rect.height),
  }, fit);
}

function autoPanDragViewport(event: PointerEvent, rect: DOMRect): void {
  if (!dragViewportFit) return;
  const pointer = {
    x: event.clientX - rect.left,
    y: event.clientY - rect.top,
  };
  const canvasStep = {
    x: edgePressureStep(pointer.x, rect.width),
    y: edgePressureStep(pointer.y, rect.height),
  };
  if (canvasStep.x === 0 && canvasStep.y === 0) return;
  const naturalStep = {
    x: canvasStep.x / dragViewportFit.scale,
    y: canvasStep.y / dragViewportFit.scale,
  };
  const nextFit = {
    ...dragViewportFit,
    minX: dragViewportFit.minX + naturalStep.x,
    maxX: dragViewportFit.maxX + naturalStep.x,
    minY: dragViewportFit.minY + naturalStep.y,
    maxY: dragViewportFit.maxY + naturalStep.y,
  };
  dragViewportFit = nextFit;
  viewState = {
    mode: 'manual',
    scale: nextFit.scale,
    center: {
      x: nextFit.minX + (rect.width / 2 - nextFit.x) / nextFit.scale,
      y: nextFit.minY + (rect.height / 2 - nextFit.y) / nextFit.scale,
    },
  };
}

function edgePressureStep(position: number, size: number): number {
  if (position < DRAG_AUTOPAN_MARGIN) {
    return -dragAutoPanStep(DRAG_AUTOPAN_MARGIN - position);
  }
  if (position > size - DRAG_AUTOPAN_MARGIN) {
    return dragAutoPanStep(position - (size - DRAG_AUTOPAN_MARGIN));
  }
  return 0;
}

function dragAutoPanStep(pressure: number): number {
  if (pressure <= 0) return 0;
  return Math.min(DRAG_AUTOPAN_MAX_STEP, Math.max(12, pressure * 0.85));
}

function endCornerDrag(pointerId: number): void {
  if (dragCornerIndex === null && dragEdgeIndex === null && !panState) return;
  if (canvas.hasPointerCapture(pointerId)) {
    canvas.releasePointerCapture(pointerId);
  }
  dragCornerIndex = null;
  dragEdgeIndex = null;
  dragStartPoint = null;
  dragStartCorners = null;
  panState = null;
  dragViewportFit = null;
  updatePointerState();
  render();
}

function updatePointerState(): void {
  if (dragCornerIndex === null) {
    delete canvas.dataset.magnifier;
    delete canvas.dataset.draggingCorner;
  } else {
    canvas.dataset.magnifier = 'visible';
    canvas.dataset.draggingCorner = String.fromCharCode(65 + dragCornerIndex);
  }
  if (!panState) delete canvas.dataset.panning;
  else canvas.dataset.panning = 'true';
  if (dragEdgeIndex === null) delete canvas.dataset.draggingEdge;
  else canvas.dataset.draggingEdge = String(dragEdgeIndex);
}

function drawSourceImageFrame(
  context: CanvasRenderingContext2D,
  image: HTMLImageElement,
  fit: LabelViewportFit,
): void {
  const topLeft = naturalToCanvas({ x: 0, y: 0 }, fit);
  context.save();
  context.strokeStyle = 'rgba(255, 255, 255, 0.38)';
  context.lineWidth = 1;
  context.strokeRect(
    topLeft.x,
    topLeft.y,
    image.naturalWidth * fit.scale,
    image.naturalHeight * fit.scale,
  );
  context.restore();
}

function isExtrapolatedLabel(label: GridFixtureLabel): boolean {
  return label.corners.some((corner) => (
    corner.x < 0
    || corner.y < 0
    || corner.x > label.imageWidth
    || corner.y > label.imageHeight
  ));
}

function canvasToNatural(point: Point, fit: LabelViewportFit): Point {
  return {
    x: fit.minX + (point.x - fit.x) / fit.scale,
    y: fit.minY + (point.y - fit.y) / fit.scale,
  };
}

function currentLabelViewportFit(
  image: HTMLImageElement,
  label: GridFixtureLabel,
  width: number,
  height: number,
): LabelViewportFit {
  const baseFit = labelViewportFit(image, label, width, height);
  if (viewState.mode === 'fit') return baseFit;

  const scale = clampNumber(viewState.scale, baseFit.scale, 3);
  const center = clampViewCenter(viewState.center, scale, width, height);
  const minX = center.x - width / (2 * scale);
  const minY = center.y - height / (2 * scale);
  return {
    x: 0,
    y: 0,
    width,
    height,
    scale,
    minX,
    minY,
    maxX: minX + width / scale,
    maxY: minY + height / scale,
  };
}

function labelViewportFit(
  image: HTMLImageElement,
  label: GridFixtureLabel,
  width: number,
  height: number,
): LabelViewportFit {
  const cornerXs = label.corners.map((corner) => corner.x);
  const cornerYs = label.corners.map((corner) => corner.y);
  const padX = Math.max(80, image.naturalWidth * 0.16);
  const padY = Math.max(80, image.naturalHeight * 0.16);
  const minX = Math.min(0, ...cornerXs) - padX;
  const maxX = Math.max(image.naturalWidth, ...cornerXs) + padX;
  const minY = Math.min(0, ...cornerYs) - padY;
  const maxY = Math.max(image.naturalHeight, ...cornerYs) + padY;
  const naturalWidth = Math.max(1, maxX - minX);
  const naturalHeight = Math.max(1, maxY - minY);
  const scale = Math.min(width / naturalWidth, height / naturalHeight);
  const viewportWidth = naturalWidth * scale;
  const viewportHeight = naturalHeight * scale;

  return {
    x: (width - viewportWidth) / 2,
    y: (height - viewportHeight) / 2,
    width: viewportWidth,
    height: viewportHeight,
    scale,
    minX,
    minY,
    maxX,
    maxY,
  };
}

function clampViewCenter(center: Point, scale: number, width: number, height: number): Point {
  if (!selectedImage || !currentLabel) return center;
  const halfWidth = width / (2 * scale);
  const halfHeight = height / (2 * scale);
  const bounds = labelContentBounds(selectedImage, currentLabel);
  const overscrollX = Math.max(240, halfWidth * 0.95);
  const overscrollY = Math.max(240, halfHeight * 0.95);
  const minX = bounds.minX - overscrollX;
  const maxX = bounds.maxX + overscrollX;
  const minY = bounds.minY - overscrollY;
  const maxY = bounds.maxY + overscrollY;
  return {
    x: clampNumber(center.x, minX, maxX),
    y: clampNumber(center.y, minY, maxY),
  };
}

function labelContentBounds(image: HTMLImageElement, label: GridFixtureLabel): {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
} {
  const cornerXs = label.corners.map((corner) => corner.x);
  const cornerYs = label.corners.map((corner) => corner.y);
  return {
    minX: Math.min(0, ...cornerXs),
    maxX: Math.max(image.naturalWidth, ...cornerXs),
    minY: Math.min(0, ...cornerYs),
    maxY: Math.max(image.naturalHeight, ...cornerYs),
  };
}

function clampNumber(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, value));
}

function roundForDisplay(value: number): number {
  return Math.round(value * 100) / 100;
}

function naturalToCanvas(point: Point, fit: LabelViewportFit): Point {
  return {
    x: fit.x + (point.x - fit.minX) * fit.scale,
    y: fit.y + (point.y - fit.minY) * fit.scale,
  };
}

function keyDirection(key: string): Point | null {
  if (key === 'ArrowLeft') return { x: -1, y: 0 };
  if (key === 'ArrowRight') return { x: 1, y: 0 };
  if (key === 'ArrowUp') return { x: 0, y: -1 };
  if (key === 'ArrowDown') return { x: 0, y: 1 };
  return null;
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

function normalizeLabelFile(value: unknown): GridFixtureLabelFile {
  if (!value || typeof value !== 'object') return structuredClone(EMPTY_LABEL_FILE);
  const candidate = value as Partial<GridFixtureLabelFile>;
  return {
    version: 1,
    updatedAt: typeof candidate.updatedAt === 'string' ? candidate.updatedAt : null,
    labels: Array.isArray(candidate.labels) ? candidate.labels.map(normalizeLabel).filter(Boolean) as GridFixtureLabel[] : [],
  };
}

function normalizeLabel(value: unknown): GridFixtureLabel | null {
  if (!value || typeof value !== 'object') return null;
  const item = value as Partial<GridFixtureLabel>;
  if (!item.sourceId || !item.sourceName || !item.sourceUrl || !Array.isArray(item.corners) || item.corners.length !== 4) return null;
  return {
    sourceId: item.sourceId,
    sourceName: item.sourceName,
    sourceUrl: item.sourceUrl,
    note: item.note ?? '',
    imageWidth: Number(item.imageWidth) || 0,
    imageHeight: Number(item.imageHeight) || 0,
    corners: cloneCorners(item.corners as Point[]),
    columns: clampInteger(Number(item.columns) || 12, 1, 120),
    rows: clampInteger(Number(item.rows) || 8, 1, 120),
    benchmark: item.benchmark !== false,
    labeledAt: item.labeledAt ?? new Date().toISOString(),
  };
}

function cloneLabel(label: GridFixtureLabel): GridFixtureLabel {
  return {
    ...label,
    corners: cloneCorners(label.corners),
  };
}

function cloneCorners(corners: Point[]): [Point, Point, Point, Point] {
  return corners.slice(0, 4).map((corner) => ({
    x: Number(corner.x) || 0,
    y: Number(corner.y) || 0,
  })) as [Point, Point, Point, Point];
}

function clampInteger(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, Math.round(value)));
}

function setInputValue(selector: string, value: string): void {
  const input = document.querySelector<HTMLInputElement>(selector);
  if (input && input.value !== value) input.value = value;
}

function setStatus(message: string, type: 'neutral' | 'success' | 'warning'): void {
  statusElement.textContent = message;
  statusElement.classList.toggle('status-neutral', type === 'neutral');
  statusElement.classList.toggle('status-success', type === 'success');
  statusElement.classList.toggle('status-warning', type === 'warning');
}

function downloadLabels(): void {
  const blob = new Blob([JSON.stringify(labelFile, null, 2)], { type: 'application/json' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'map-grid-labels.json';
  link.click();
  URL.revokeObjectURL(link.href);
}
