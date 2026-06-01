import './styles.css';
import {
  runnableDetectorCandidates,
  type RunnableDetectorCandidate,
} from './calibration/detectorCandidates';
import { applyHomography, solveHomography } from './calibration/homography';
import {
  buildFixtureBenchmarkReport,
  renderFixtureBenchmarkMarkdown,
  scoreFixtureBenchmarkError,
  scoreFixtureDetection,
  type FixtureBenchmarkReport,
  type FixtureBenchmarkResult,
} from './calibration/fixtureBenchmark';
import type { GridFixtureLabel, GridFixtureLabelFile } from './calibration/fixtureLabels';
import type { DetectedGrid, Point } from './calibration/types';

interface BenchmarkOverlay {
  label: GridFixtureLabel;
  detected: DetectedGrid | null;
  result: FixtureBenchmarkResult;
  image: HTMLImageElement | null;
}

interface BenchmarkWindow extends Window {
  __fixtureBenchmarkDone?: boolean;
  __fixtureBenchmarkReport?: FixtureBenchmarkReport;
  __fixtureBenchmarkMarkdown?: string;
}

interface OverlayFit {
  x: number;
  y: number;
  scale: number;
  minX: number;
  minY: number;
  width: number;
  height: number;
}

const LABEL_ENDPOINT = '/__fixture-labels';
const root = document.querySelector<HTMLDivElement>('#benchmark-root');
if (!root) throw new Error('Missing benchmark root');

root.innerHTML = `
  <main class="app-shell benchmark-shell">
    <header class="topbar">
      <div>
        <h1>Fixture Detector Benchmark</h1>
        <p>Scores calibration detector candidates against saved grid labels without tuning against the answers.</p>
      </div>
      <div class="topbar-actions">
        <a class="button" href="/">Calibration Workbench</a>
        <a class="button" href="/labeler.html">Fixture Labeler</a>
        <button class="button primary" id="run-benchmark" type="button">Run Benchmark</button>
      </div>
    </header>

    <section class="panel benchmark-summary-panel">
      <div class="panel-heading">
        <h2>Summary</h2>
        <p id="benchmark-status">Ready.</p>
      </div>
      <pre id="benchmark-summary" class="benchmark-summary">No benchmark run yet.</pre>
    </section>

    <section class="panel">
      <div class="panel-heading">
        <h2>Fixture Results</h2>
        <p>Green is saved ground truth. Orange is detector output.</p>
      </div>
      <div class="benchmark-table-wrap">
        <table class="benchmark-table">
	          <thead>
	            <tr>
	              <th>Candidate</th>
	              <th>Fixture</th>
              <th>Strict</th>
              <th>Outcome</th>
              <th>State</th>
              <th>Expected</th>
              <th>Detected</th>
              <th>Mean sq</th>
              <th>Max sq</th>
              <th>Mean px</th>
              <th>Max px</th>
              <th>Notes</th>
            </tr>
          </thead>
          <tbody id="benchmark-results"></tbody>
        </table>
      </div>
    </section>

    <section class="benchmark-overlays" id="benchmark-overlays" aria-label="Benchmark overlay artifacts"></section>
  </main>
`;

document.querySelector<HTMLButtonElement>('#run-benchmark')?.addEventListener('click', () => {
  void runBenchmark();
});

if (new URLSearchParams(window.location.search).get('run') === '1') {
  void runBenchmark();
}

async function runBenchmark(): Promise<void> {
  const status = document.querySelector<HTMLParagraphElement>('#benchmark-status');
  const summaryElement = document.querySelector<HTMLPreElement>('#benchmark-summary');
  const table = document.querySelector<HTMLTableSectionElement>('#benchmark-results');
  const overlaysElement = document.querySelector<HTMLElement>('#benchmark-overlays');
  const benchmarkWindow = window as BenchmarkWindow;
  benchmarkWindow.__fixtureBenchmarkDone = false;
  benchmarkWindow.__fixtureBenchmarkReport = undefined;
  benchmarkWindow.__fixtureBenchmarkMarkdown = undefined;

  if (!status || !summaryElement || !table || !overlaysElement) return;
  status.textContent = 'Loading labels...';
  summaryElement.textContent = 'Running...';
  table.innerHTML = '';
  overlaysElement.innerHTML = '';

  const labelFile = await loadLabelFile();
  const params = new URLSearchParams(window.location.search);
  const candidateFilter = params.get('candidate');
  const candidates = runnableDetectorCandidates({ includeControls: params.get('controls') === '1' })
    .filter((candidate) => !candidateFilter || candidate.id === candidateFilter);
  if (candidates.length === 0) {
    throw new Error(`No runnable detector candidates matched ${candidateFilter ?? 'the current filter'}.`);
  }
  const labels = labelFile.labels.filter((label) => label.benchmark);
  const overlays: BenchmarkOverlay[] = [];
  const totalRuns = labels.length * candidates.length;

  for (const [candidateIndex, candidate] of candidates.entries()) {
    for (const [labelIndex, label] of labels.entries()) {
      const runIndex = candidateIndex * labels.length + labelIndex + 1;
      status.textContent = `Running ${runIndex} of ${totalRuns}: ${candidate.name} / ${label.sourceName}`;
      const overlay = await runFixture(label, candidate);
      overlays.push(overlay);
      renderResultRow(table, overlay.result);
      renderOverlay(overlaysElement, overlay, overlays.length - 1);
    }
  }

  const report = buildFixtureBenchmarkReport(
    overlays.map((overlay) => overlay.result),
    labelFile.updatedAt,
  );
  const markdown = renderFixtureBenchmarkMarkdown(report);

  summaryElement.textContent = markdown;
  status.textContent = `Complete: ${report.candidateSummaries.length} candidate(s), ${report.summary.strictSalesPhotoSuccess}/${report.summary.salesPhotoFixtures} strict sales, ${report.summary.autoAcceptedAccurate} accepted, ${report.summary.manualCorrectionSeed} seed, ${report.summary.roughCorrectionSeed} rough seed, ${report.summary.safeRefusal} safe refusal, ${report.summary.wrongConfident} wrong confident, ${report.summary.benchmarkError} errors.`;
  benchmarkWindow.__fixtureBenchmarkReport = report;
  benchmarkWindow.__fixtureBenchmarkMarkdown = markdown;
  benchmarkWindow.__fixtureBenchmarkDone = true;
}

async function runFixture(
  label: GridFixtureLabel,
  candidate: RunnableDetectorCandidate,
): Promise<BenchmarkOverlay> {
  let image: HTMLImageElement | null = null;
  let detected: DetectedGrid | null = null;
  let errorMessage: string | null = null;
  const candidateRef = {
    candidateId: candidate.id,
    candidateName: candidate.name,
    candidateCategory: candidate.category,
    candidateRuntime: candidate.runtime,
    usesGroundTruth: candidate.usesGroundTruth,
  };

  try {
    image = await loadImage(label.sourceUrl);
  } catch (error) {
    return {
      label,
      detected,
      image,
      result: scoreFixtureBenchmarkError(label, (error as Error).message, candidateRef),
    };
  }

  try {
    detected = await candidate.run({
      image,
      fixture: label,
      label: candidate.usesGroundTruth ? label : undefined,
    });
  } catch (error) {
    errorMessage = (error as Error).message;
  }

  return {
    label,
    detected,
    image,
    result: scoreFixtureDetection(label, detected, errorMessage, candidateRef),
  };
}

async function loadLabelFile(): Promise<GridFixtureLabelFile> {
  const response = await fetch(LABEL_ENDPOINT);
  if (!response.ok) throw new Error(`Could not load labels: ${response.status}`);
  return response.json() as Promise<GridFixtureLabelFile>;
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

function renderResultRow(table: HTMLTableSectionElement, result: FixtureBenchmarkResult): void {
  const notes = [
    result.extrapolatedGroundTruth ? 'extrapolated truth' : '',
    result.errorMessage ?? '',
    ...result.autoAlignIssues,
  ].filter(Boolean).join('; ') || '-';
  const row = document.createElement('tr');
  row.dataset.outcome = result.outcome;
  row.innerHTML = `
    <td>${escapeHtml(result.candidateName)}</td>
    <td>${escapeHtml(result.sourceName)}</td>
    <td>${result.strictGeometrySuccess ? 'yes' : 'no'}</td>
    <td><span class="benchmark-pill">${escapeHtml(result.outcome)}</span></td>
    <td>${escapeHtml(result.applicationState)}</td>
    <td>${result.expectedColumns}x${result.expectedRows}</td>
    <td>${result.detectedColumns === null || result.detectedRows === null ? '-' : `${result.detectedColumns}x${result.detectedRows}`}</td>
    <td>${formatMetric(result.meanCornerErrorSquares)}</td>
    <td>${formatMetric(result.maxCornerErrorSquares)}</td>
    <td>${formatMetric(result.meanCornerErrorPixels)}</td>
    <td>${formatMetric(result.maxCornerErrorPixels)}</td>
    <td>${escapeHtml(notes)}</td>
  `;
  table.append(row);
}

function renderOverlay(parent: HTMLElement, overlay: BenchmarkOverlay, index: number): void {
  const card = document.createElement('article');
  card.className = 'benchmark-overlay-card';
  const title = document.createElement('h3');
  title.textContent = overlay.label.sourceName;
  const meta = document.createElement('p');
  meta.textContent = `${overlay.result.candidateName} | ${overlay.result.outcome} | ${overlay.result.applicationState}`;
  const canvas = document.createElement('canvas');
  canvas.width = 720;
  canvas.height = 520;
  canvas.dataset.overlayIndex = String(index);
  canvas.dataset.sourceId = overlay.label.sourceId;
  canvas.dataset.candidateId = overlay.result.candidateId;
  drawOverlayCanvas(canvas, overlay);
  card.append(title, meta, canvas);
  parent.append(card);
}

function drawOverlayCanvas(canvas: HTMLCanvasElement, overlay: BenchmarkOverlay): void {
  const context = canvas.getContext('2d');
  if (!context) return;
  context.fillStyle = '#151714';
  context.fillRect(0, 0, canvas.width, canvas.height);

  const fit = overlayFit(canvas, overlay.label, overlay.detected);
  if (overlay.image) {
    const imageTopLeft = toCanvas({ x: 0, y: 0 }, fit);
    context.drawImage(
      overlay.image,
      imageTopLeft.x,
      imageTopLeft.y,
      overlay.label.imageWidth * fit.scale,
      overlay.label.imageHeight * fit.scale,
    );
  }

  context.save();
  context.strokeStyle = 'rgba(255, 255, 255, 0.45)';
  context.lineWidth = 1;
  const imageTopLeft = toCanvas({ x: 0, y: 0 }, fit);
  context.strokeRect(imageTopLeft.x, imageTopLeft.y, overlay.label.imageWidth * fit.scale, overlay.label.imageHeight * fit.scale);
  context.restore();

  drawGrid(context, overlay.label.corners, overlay.label.columns, overlay.label.rows, fit, {
    line: 'rgba(0, 143, 100, 0.9)',
    outline: 'rgba(255, 255, 255, 0.96)',
  });

  if (overlay.detected) {
    drawGrid(context, overlay.detected.corners, overlay.detected.columns, overlay.detected.rows, fit, {
      line: 'rgba(255, 127, 46, 0.75)',
      outline: 'rgba(255, 127, 46, 0.95)',
    });
  }
}

function drawGrid(
  context: CanvasRenderingContext2D,
  corners: [Point, Point, Point, Point],
  columns: number,
  rows: number,
  fit: OverlayFit,
  styles: { line: string; outline: string },
): void {
  const canvasCorners = corners.map((corner) => toCanvas(corner, fit)) as [Point, Point, Point, Point];
  const gridToCanvas = solveHomography(
    [
      { x: 0, y: 0 },
      { x: columns, y: 0 },
      { x: columns, y: rows },
      { x: 0, y: rows },
    ],
    canvasCorners,
  );
  const project = (point: Point) => applyHomography(gridToCanvas, point);

  context.save();
  context.strokeStyle = styles.line;
  context.lineWidth = 1;
  for (let column = 0; column <= columns; column += 1) {
    const top = project({ x: column, y: 0 });
    const bottom = project({ x: column, y: rows });
    context.beginPath();
    context.moveTo(top.x, top.y);
    context.lineTo(bottom.x, bottom.y);
    context.stroke();
  }
  for (let row = 0; row <= rows; row += 1) {
    const left = project({ x: 0, y: row });
    const right = project({ x: columns, y: row });
    context.beginPath();
    context.moveTo(left.x, left.y);
    context.lineTo(right.x, right.y);
    context.stroke();
  }

  context.strokeStyle = styles.outline;
  context.lineWidth = 3;
  context.beginPath();
  canvasCorners.forEach((corner, index) => {
    if (index === 0) context.moveTo(corner.x, corner.y);
    else context.lineTo(corner.x, corner.y);
  });
  context.closePath();
  context.stroke();
  context.restore();
}

function overlayFit(
  canvas: HTMLCanvasElement,
  label: GridFixtureLabel,
  detected: DetectedGrid | null,
): OverlayFit {
  const points = [
    { x: 0, y: 0 },
    { x: label.imageWidth, y: label.imageHeight },
    ...label.corners,
    ...(detected?.corners ?? []),
  ];
  const padX = Math.max(80, label.imageWidth * 0.08);
  const padY = Math.max(80, label.imageHeight * 0.08);
  const minX = Math.min(...points.map((point) => point.x)) - padX;
  const maxX = Math.max(...points.map((point) => point.x)) + padX;
  const minY = Math.min(...points.map((point) => point.y)) - padY;
  const maxY = Math.max(...points.map((point) => point.y)) + padY;
  const naturalWidth = Math.max(1, maxX - minX);
  const naturalHeight = Math.max(1, maxY - minY);
  const scale = Math.min(canvas.width / naturalWidth, canvas.height / naturalHeight);
  const width = naturalWidth * scale;
  const height = naturalHeight * scale;

  return {
    x: (canvas.width - width) / 2,
    y: (canvas.height - height) / 2,
    scale,
    minX,
    minY,
    width,
    height,
  };
}

function toCanvas(point: Point, fit: OverlayFit): Point {
  return {
    x: fit.x + (point.x - fit.minX) * fit.scale,
    y: fit.y + (point.y - fit.minY) * fit.scale,
  };
}

function formatMetric(value: number | null): string {
  return value === null ? '-' : String(value);
}

function escapeHtml(value: string): string {
  const span = document.createElement('span');
  span.textContent = value;
  return span.innerHTML;
}
