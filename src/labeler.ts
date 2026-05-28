import './styles.css';
import { detectGridFromImage } from './calibration/gridDetection';
import { applyHomography, solveHomography } from './calibration/homography';
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

let labelFile: GridFixtureLabelFile = structuredClone(EMPTY_LABEL_FILE);
let selectedIndex = 0;
let selectedImage: HTMLImageElement | null = null;
let currentLabel: GridFixtureLabel | null = null;
let dragCornerIndex: number | null = null;
let dragViewportFit: LabelViewportFit | null = null;
let activeCornerIndex = 0;
let dirty = false;
let showVirtualGrid = window.localStorage.getItem(LABELER_GRID_VISIBILITY_KEY) !== 'false';

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
          <div class="button-row labeler-actions">
            <button class="button" id="seed-detector" type="button">Use Detector Seed</button>
            <button class="button" id="reset-bounds" type="button">Reset To Image Bounds</button>
          </div>
          <p class="detection-status status-neutral" id="labeler-status">Loading labels...</p>
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

  document.querySelector('#reset-bounds')?.addEventListener('click', () => {
    if (!selectedImage) return;
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
    if (index === null) return;
    dragCornerIndex = index;
    activeCornerIndex = index;
    dragViewportFit = selectedImage && currentLabel
      ? labelViewportFit(selectedImage, currentLabel, canvas.clientWidth, canvas.clientHeight)
      : null;
    updateDragState();
    canvas.setPointerCapture(event.pointerId);
    canvas.focus({ preventScroll: true });
    syncCornerButtons();
    render();
    event.preventDefault();
  });

  canvas.addEventListener('pointermove', (event) => {
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
    if (dragCornerIndex === null) return;
    dragCornerIndex = null;
    dragViewportFit = null;
    updateDragState();
    render();
  });

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
  dirty = false;
  syncControls();
  setStatus(saved ? 'Loaded saved label.' : 'No saved label yet. Drag corners and save this fixture.', saved ? 'success' : 'neutral');
  render();
}

async function seedFromDetector(): Promise<void> {
  if (!selectedImage) return;
  try {
    setStatus('Running detector seed...', 'neutral');
    const detected = await detectGridFromImage(selectedImage, currentIdentity().sourceName, currentIdentity().sourceUrl);
    currentLabel = {
      ...currentIdentity(),
      imageWidth: selectedImage.naturalWidth,
      imageHeight: selectedImage.naturalHeight,
      corners: detected.corners,
      columns: detected.columns,
      rows: detected.rows,
      benchmark: currentLabel?.benchmark ?? true,
      labeledAt: new Date().toISOString(),
    };
    markDirty('Detector seed applied. Adjust it before saving if needed.');
  } catch (error) {
    setStatus(`Detector seed failed: ${(error as Error).message}`, 'warning');
  }
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
    delete canvas.dataset.labelViewport;
    delete canvas.dataset.extrapolatedGrid;
    return;
  }

  const fit = dragViewportFit ?? labelViewportFit(selectedImage, currentLabel, width, height);
  const imageTopLeft = naturalToCanvas({ x: 0, y: 0 }, fit);
  context.drawImage(
    selectedImage,
    imageTopLeft.x,
    imageTopLeft.y,
    selectedImage.naturalWidth * fit.scale,
    selectedImage.naturalHeight * fit.scale,
  );
  drawSourceImageFrame(context, selectedImage, fit);
  canvas.dataset.gridOverlay = showVirtualGrid ? 'visible' : 'hidden';
  canvas.dataset.labelViewport = JSON.stringify(fit);
  canvas.dataset.extrapolatedGrid = isExtrapolatedLabel(currentLabel) ? 'true' : 'false';
  drawLabelGrid(context, currentLabel, fit);
  drawDragMagnifier(context, currentLabel, fit, width, height);
}

function drawLabelGrid(
  context: CanvasRenderingContext2D,
  label: GridFixtureLabel,
  fit: LabelViewportFit,
): void {
  const corners = label.corners.map((corner) => naturalToCanvas(corner, fit)) as [Point, Point, Point, Point];
  const gridToCanvas = solveHomography(
    [
      { x: 0, y: 0 },
      { x: label.columns, y: 0 },
      { x: label.columns, y: label.rows },
      { x: 0, y: label.rows },
    ],
    corners,
  );
  const project = (point: Point) => applyHomography(gridToCanvas, point);

  if (showVirtualGrid) {
    context.save();
    context.strokeStyle = 'rgba(0, 143, 100, 0.9)';
    context.lineWidth = 1.5;
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

    context.strokeStyle = 'rgba(255, 255, 255, 0.95)';
    context.lineWidth = 3;
    context.beginPath();
    corners.forEach((corner, index) => {
      if (index === 0) context.moveTo(corner.x, corner.y);
      else context.lineTo(corner.x, corner.y);
    });
    context.closePath();
    context.stroke();
    context.restore();
  }

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
  const zoom = 5;
  const zoomScale = fit.scale * zoom;
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
  const fit = labelViewportFit(selectedImage, currentLabel, rect.width, rect.height);
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

function pointerToNaturalPoint(event: PointerEvent): Point | null {
  if (!selectedImage || !currentLabel) return null;
  const rect = canvas.getBoundingClientRect();
  const fit = dragViewportFit ?? labelViewportFit(selectedImage, currentLabel, rect.width, rect.height);
  return canvasToNatural({
    x: clampNumber(event.clientX - rect.left, 0, rect.width),
    y: clampNumber(event.clientY - rect.top, 0, rect.height),
  }, fit);
}

function endCornerDrag(pointerId: number): void {
  if (dragCornerIndex === null) return;
  if (canvas.hasPointerCapture(pointerId)) {
    canvas.releasePointerCapture(pointerId);
  }
  dragCornerIndex = null;
  dragViewportFit = null;
  updateDragState();
  render();
}

function updateDragState(): void {
  if (dragCornerIndex === null) {
    delete canvas.dataset.magnifier;
    delete canvas.dataset.draggingCorner;
    return;
  }
  canvas.dataset.magnifier = 'visible';
  canvas.dataset.draggingCorner = String.fromCharCode(65 + dragCornerIndex);
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

function clampNumber(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, value));
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
