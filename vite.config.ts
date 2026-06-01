import { execFile } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { access, mkdir, readdir, readFile, stat, writeFile } from 'node:fs/promises';
import { dirname, relative, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, type Plugin } from 'vite';

const root = dirname(fileURLToPath(import.meta.url));
const labelFilePath = resolve(root, 'input/map-grid-labels.json');
const fixtureImageDir = resolve(root, 'input/map-pix');
const opencvBenchmarkScriptPath = resolve(root, 'scripts/opencv-fixture-benchmark.py');
const aiGridReportPath = resolve(root, 'test-results/ai-dot-lattice-fit-risk-aware-summary-v1/report.json');
const aiGridHybridReportPath = resolve(root, 'test-results/ai-grid-hybrid-prompt-ensemble-summary-v1/report.json');
const aiGridParallelDir = resolve(root, 'test-results/ai-grid-parallel-current');
const AI_GRID_SEED_MODES = ['grid-frame', 'supported', 'fit-span', 'manual-span-diagnostic', 'label-sized-diagnostic'] as const;
const MIN_IMAGE_FRAME_BAND_OVERLAP = 0.10;

type AiGridSeedModeId = typeof AI_GRID_SEED_MODES[number];

export default defineConfig({
  plugins: [fixtureLabelPlugin()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: false,
  },
  build: {
    rollupOptions: {
      input: {
        main: resolve(root, 'index.html'),
        projector: resolve(root, 'projector.html'),
        labeler: resolve(root, 'labeler.html'),
        benchmark: resolve(root, 'benchmark.html'),
      },
    },
  },
});

function fixtureLabelPlugin(): Plugin {
  return {
    name: 'rpg-map-projector-fixture-labels',
    configureServer(server) {
      server.middlewares.use(async (request, response, next) => {
        const requestUrl = new URL(request.url ?? '/', 'http://127.0.0.1');
        if (requestUrl.pathname === '/__opencv-detection') {
          await handleOpenCvDetectionRequest(requestUrl, response);
          return;
        }

        if (requestUrl.pathname === '/__ai-grid-seed') {
          await handleAiGridSeedRequest(requestUrl, response);
          return;
        }

        if (requestUrl.pathname !== '/__fixture-labels') {
          next();
          return;
        }

        try {
          if (request.method === 'GET') {
            const payload = await readLabelPayload();
            sendJson(response, 200, payload);
            return;
          }

          if (request.method === 'POST') {
            const body = await readRequestBody(request);
            const payload = JSON.parse(body);
            if (!isLabelPayload(payload)) {
              sendText(response, 400, 'Invalid fixture label payload.');
              return;
            }
            await mkdir(dirname(labelFilePath), { recursive: true });
            await writeFile(labelFilePath, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
            sendJson(response, 200, { ok: true, path: labelFilePath });
            return;
          }

          sendText(response, 405, 'Method not allowed.');
        } catch (error) {
          sendText(response, 500, (error as Error).message);
        }
      });
    },
  };
}

async function handleAiGridSeedRequest(
  requestUrl: URL,
  response: import('node:http').ServerResponse,
): Promise<void> {
  const sourceId = requestUrl.searchParams.get('sourceId') ?? '';
  if (!sourceId) {
    sendJson(response, 200, { detected: false, errorMessage: 'Missing sourceId.' });
    return;
  }

  try {
    const result = await readCurrentAiGridResult(sourceId);
    if (!result || typeof result !== 'object') {
      sendJson(response, 200, { detected: false, errorMessage: `No AI grid result found for ${sourceId}.` });
      return;
    }

    const label = findLabelPayload(await readLabelPayload(), sourceId);
    if (!label) {
      sendJson(response, 200, { detected: false, errorMessage: `No fixture label dimensions found for ${sourceId}.` });
      return;
    }

    const requestedMode = parseAiGridSeedMode(requestUrl.searchParams.get('mode'));
    const resultRecord = result as Record<string, unknown>;
    if (resultRecord.__seedKind === 'line-graph') {
      sendJson(response, 200, buildAiLineGraphSeedPayload(resultRecord, label, requestedMode));
      return;
    }
    sendJson(response, 200, buildAiGridSeedPayload(resultRecord, label, requestedMode));
  } catch (error) {
    sendText(response, 500, (error as Error).message);
  }
}

async function readCurrentAiGridResult(sourceId: string): Promise<Record<string, unknown> | null> {
  const hybridResult = await readHybridAiGridResult(sourceId);
  if (hybridResult) return hybridResult;
  const summaryResult = await readSummaryAiGridResult(sourceId);
  if (summaryResult) return summaryResult;
  return readLatestParallelAiGridResult(sourceId);
}

async function readHybridAiGridResult(sourceId: string): Promise<Record<string, unknown> | null> {
  try {
    const report = JSON.parse(await readFile(aiGridHybridReportPath, 'utf8'));
    const result = Array.isArray(report.results)
      ? report.results.find((item: unknown) => (
          item
          && typeof item === 'object'
          && (item as { sourceId?: unknown }).sourceId === sourceId
        ))
      : null;
    if (!result || typeof result !== 'object') return null;
    const hybrid = result as Record<string, unknown>;
    if (hybrid.selectedBranch === 'dot-consensus') {
      return readSummaryAiGridResult(sourceId);
    }
    if (hybrid.selectedBranch !== 'line-graph') return null;
    return readHybridLineGraphResult(sourceId, hybrid);
  } catch {
    return null;
  }
}

async function readHybridLineGraphResult(
  sourceId: string,
  hybrid: Record<string, unknown>,
): Promise<Record<string, unknown> | null> {
  const outDir = typeof hybrid.lineGraphReportOutDir === 'string' ? hybrid.lineGraphReportOutDir : '';
  if (!outDir) return null;
  try {
    const reportPath = resolveRepoPath(`${outDir}/report.json`);
    const report = JSON.parse(await readFile(reportPath, 'utf8'));
    const result = Array.isArray(report.results)
      ? report.results.find((item: unknown) => (
          item
          && typeof item === 'object'
          && (item as { sourceId?: unknown }).sourceId === sourceId
        ))
      : null;
    if (!result || typeof result !== 'object') return null;
    const selected = (result as Record<string, unknown>).selected;
    if (!selected || typeof selected !== 'object') return null;
    return {
      __seedKind: 'line-graph',
      hybridResult: hybrid,
      lineGraphResult: selected,
    };
  } catch {
    return null;
  }
}

async function readSummaryAiGridResult(sourceId: string): Promise<Record<string, unknown> | null> {
  try {
    const report = JSON.parse(await readFile(aiGridReportPath, 'utf8'));
    const result = Array.isArray(report.results)
      ? report.results.find((item: unknown) => (
          item
          && typeof item === 'object'
          && (item as { sourceId?: unknown }).sourceId === sourceId
        ))
      : null;
    return result && typeof result === 'object' ? result as Record<string, unknown> : null;
  } catch {
    return null;
  }
}

async function readLatestParallelAiGridResult(sourceId: string): Promise<Record<string, unknown> | null> {
  const reportPaths = await collectParallelReportPaths(aiGridParallelDir);
  let best: { mtimeMs: number; result: Record<string, unknown> } | null = null;
  for (const reportPath of reportPaths) {
    try {
      const report = JSON.parse(await readFile(reportPath, 'utf8'));
      if (report.sourceId !== sourceId || !report.selectedDetail || typeof report.selectedDetail !== 'object') continue;
      const reportStat = await stat(reportPath);
      if (!best || reportStat.mtimeMs > best.mtimeMs) {
        best = { mtimeMs: reportStat.mtimeMs, result: report.selectedDetail as Record<string, unknown> };
      }
    } catch {
      // Ignore incomplete live-run reports while the runner is writing artifacts.
    }
  }
  return best?.result ?? null;
}

async function collectParallelReportPaths(dir: string): Promise<string[]> {
  try {
    const entries = await readdir(dir, { withFileTypes: true });
    const paths = await Promise.all(entries.map(async (entry) => {
      const path = resolve(dir, entry.name);
      if (entry.isDirectory()) return collectParallelReportPaths(path);
      return entry.isFile() && entry.name === 'parallel-report.json' ? [path] : [];
    }));
    return paths.flat();
  } catch {
    return [];
  }
}

async function handleOpenCvDetectionRequest(
  requestUrl: URL,
  response: import('node:http').ServerResponse,
): Promise<void> {
  const sourceUrl = requestUrl.searchParams.get('sourceUrl') ?? '';
  if (!sourceUrl.startsWith('/input/map-pix/')) {
    sendText(response, 400, 'OpenCV detection only supports local fixture images under /input/map-pix/.');
    return;
  }

  try {
    const imagePath = resolveLocalFixturePath(sourceUrl);
    await access(imagePath);
    const payload = await runOpenCvDetection(imagePath);
    sendJson(response, 200, payload);
  } catch (error) {
    sendText(response, 500, (error as Error).message);
  }
}

function resolveLocalFixturePath(sourceUrl: string): string {
  const decodedPath = decodeURIComponent(sourceUrl).replace(/^\/+/, '');
  const imagePath = resolve(root, decodedPath);
  const relativePath = relative(fixtureImageDir, imagePath);
  if (relativePath.startsWith('..') || relativePath.includes(`..${sep}`) || relativePath === '') {
    throw new Error('Fixture image path is outside input/map-pix/.');
  }
  return imagePath;
}

function runOpenCvDetection(imagePath: string): Promise<unknown> {
  const args = [
    'run',
    '--python',
    '3.12',
    '--with',
    'opencv-python-headless',
    '--with',
    'pillow',
    '--with',
    'numpy',
    'python',
    opencvBenchmarkScriptPath,
    '--detect-image',
    imagePath,
    '--max-image-side',
    '1600',
  ];

  return new Promise((resolvePayload, reject) => {
    execFile('uv', args, { cwd: root, maxBuffer: 10 * 1024 * 1024, timeout: 120_000 }, (error, stdout, stderr) => {
      if (error) {
        reject(new Error(stderr.trim() || stdout.trim() || error.message));
        return;
      }

      try {
        resolvePayload(JSON.parse(stdout));
      } catch (parseError) {
        reject(new Error(`OpenCV detector returned invalid JSON: ${(parseError as Error).message}`));
      }
    });
  });
}

function parseAiGridSeedMode(value: string | null): AiGridSeedModeId {
  return AI_GRID_SEED_MODES.includes(value as AiGridSeedModeId)
    ? value as AiGridSeedModeId
    : 'grid-frame';
}

function buildAiGridSeedPayload(
  result: Record<string, unknown>,
  label: Record<string, unknown>,
  requestedMode: AiGridSeedModeId,
): unknown {
  const fit = requireRecord(result.fit, 'AI grid result has no selected fit.');
  const homography = requireHomography(fit.homography);
  const observedMesh = requireRecord(result.observedMesh, 'AI grid result has no observed mesh.');
  const vertices = requireMeshVertices(observedMesh.vertices);
  const cells = requireMeshCells(observedMesh.cells);
  const lineImage = typeof result.lineImage === 'string' ? result.lineImage : '';
  const lineDimensions = readImageDimensionsSync(resolveRepoPath(lineImage));
  const imageWidth = requireNumber(label.imageWidth, 'Fixture label is missing imageWidth.');
  const imageHeight = requireNumber(label.imageHeight, 'Fixture label is missing imageHeight.');
  const scaleX = imageWidth / Math.max(1, lineDimensions.width);
  const scaleY = imageHeight / Math.max(1, lineDimensions.height);
  const projection = result.projectionModelComparison && typeof result.projectionModelComparison === 'object'
    ? result.projectionModelComparison as Record<string, unknown>
    : {};
  const readiness = projection.projectionReadiness && typeof projection.projectionReadiness === 'object'
    ? projection.projectionReadiness as Record<string, unknown>
    : {};
  const noLabelReadiness = projection.noLabelProjectionReadiness && typeof projection.noLabelProjectionReadiness === 'object'
    ? projection.noLabelProjectionReadiness as Record<string, unknown>
    : {};
  const metadata = {
    dotVariantId: result.dotVariantId,
    decision: result.decision,
    projectionReadinessMode: readiness.mode,
    noLabelProjectionReadinessMode: noLabelReadiness.mode,
    fullSpanHomographyLineWithin0_15Pct: projection.fullSpanHomographyLineWithin0_15Pct,
    observedEdgeHomographyLineWithin0_15Pct: projection.observedEdgeHomographyLineWithin0_15Pct,
    visibleMeshLineWithin0_15Pct: projection.visibleMeshLineWithin0_15Pct,
    visibleMeshCells: projection.visibleMeshCells,
    unsupportedCellCount: projection.unsupportedCellCount,
    visibleMeshCellDensity: projection.visibleMeshCellDensity,
  };
  const supportedBounds = meshCoordinateBounds(vertices);
  const fitBounds = readCoordinateBounds(fit.coordinateBounds)
    ?? expandBoundsToLineSpan(
      supportedBounds,
      readPositiveInteger(fit.spanI),
      readPositiveInteger(fit.spanJ),
    );
  const frameBounds = boundsForImageFrame(homography, lineDimensions.width, lineDimensions.height, fitBounds);
  const manualSeed = result.manualSeedVariant && typeof result.manualSeedVariant === 'object'
    ? result.manualSeedVariant as Record<string, unknown>
    : null;
  const manualSeedDetail = result.manualSeedDetail && typeof result.manualSeedDetail === 'object'
    ? result.manualSeedDetail as Record<string, unknown>
    : null;
  const manualFit = manualSeedDetail?.fit && typeof manualSeedDetail.fit === 'object'
    ? manualSeedDetail.fit as Record<string, unknown>
    : null;
  const manualHomography = manualFit?.homography ? requireHomography(manualFit.homography) : homography;
  const manualObservedMesh = manualSeedDetail?.observedMesh && typeof manualSeedDetail.observedMesh === 'object'
    ? manualSeedDetail.observedMesh as Record<string, unknown>
    : null;
  const manualVertices = manualObservedMesh?.vertices ? requireMeshVertices(manualObservedMesh.vertices) : vertices;
  const manualCells = manualObservedMesh?.cells ? requireMeshCells(manualObservedMesh.cells) : cells;
  const manualBounds = manualSeed
    ? readCoordinateBounds(manualFit?.coordinateBounds)
      ?? readCoordinateBounds(manualSeed.coordinateBounds)
      ?? expandBoundsToLineSpan(
          meshCoordinateBounds(manualVertices),
          readPositiveInteger(manualSeed.spanI),
          readPositiveInteger(manualSeed.spanJ),
        )
    : null;
  const labelSizedBounds = boundsForCellSpanAroundCenter(supportedBounds, readPositiveInteger(label.columns), readPositiveInteger(label.rows));
  const modes = [
    buildSeedMode({
      modeId: 'grid-frame',
      modeLabel: 'Bounded image-frame grid',
      riskLevel: 'review',
      explanation: 'Uses the detected lattice as an alignment frame and extrapolates it across the source image, capped at 100 x 100 cells and trimmed so whole off-image rows/columns are not kept.',
      homography,
      bounds: frameBounds,
      scaleX,
      scaleY,
      metadata: frameMetadata(metadata, frameBounds),
    }),
    buildSeedMode({
      modeId: 'supported',
      modeLabel: 'Supported visible patch',
      riskLevel: 'low',
      explanation: 'Tight rectangle around observed inlier mesh cells, with source-image foreground trimming in the labeler. Safest, but often smaller than the mat.',
      homography,
      bounds: supportedBounds,
      scaleX,
      scaleY,
      metadata,
    }),
    buildSeedMode({
      modeId: 'fit-span',
      modeLabel: 'Selected dot extent (extrapolates)',
      riskLevel: 'medium',
      explanation: 'Uses the selected dot lattice coordinate bounds. This is a useful upper bound for the selected fit, but can include inferred/occluded regions.',
      homography,
      bounds: fitBounds,
      scaleX,
      scaleY,
      metadata,
    }),
    ...(manualBounds
      ? [buildSeedMode({
          modeId: 'manual-span-diagnostic',
          modeLabel: 'Wider manual span (diagnostic)',
          riskLevel: 'review',
          explanation: 'Uses the lower-confidence manual-seed variant geometry. Good for review, not autonomous projection.',
          homography: manualHomography,
          bounds: manualBounds,
          scaleX,
          scaleY,
          metadata: {
            ...metadata,
            dotVariantId: manualSeed?.dotVariantId ?? metadata.dotVariantId,
            decision: manualSeed?.decision ?? metadata.decision,
          },
        })]
      : []),
    buildSeedMode({
      modeId: 'label-sized-diagnostic',
      modeLabel: 'Label-sized diagnostic (uses labels)',
      riskLevel: 'diagnostic',
      explanation: 'Uses saved fixture row/column counts to show whether the lattice itself aligns at the human-labelled extent. Not available at runtime.',
      homography,
      bounds: labelSizedBounds,
      scaleX,
      scaleY,
      metadata,
    }),
  ];
  const selectedMode = modes.find((mode) => mode.modeId === requestedMode) ?? modes[0];
  const selectedSupportOverlay = selectedMode.modeId === 'manual-span-diagnostic'
    ? buildSupportOverlay(manualVertices, manualCells, scaleX, scaleY)
    : buildSupportOverlay(vertices, cells, scaleX, scaleY);

  return {
    ...selectedMode,
    detected: true,
    sourceId: result.sourceId,
    imageWidth,
    imageHeight,
    selectedModeId: selectedMode.modeId,
    modes,
    supportOverlay: selectedSupportOverlay,
  };
}

function buildAiLineGraphSeedPayload(
  result: Record<string, unknown>,
  label: Record<string, unknown>,
  requestedMode: AiGridSeedModeId,
): unknown {
  const hybrid = requireRecord(result.hybridResult, 'AI hybrid result is missing.');
  const line = requireRecord(result.lineGraphResult, 'AI line-graph result is missing.');
  const seed = requireRecord(line.labelerSeed, 'AI line-graph result has no labeler seed.');
  const imageWidth = requireNumber(label.imageWidth, 'Fixture label is missing imageWidth.');
  const imageHeight = requireNumber(label.imageHeight, 'Fixture label is missing imageHeight.');
  const seedWidth = requireNumber(seed.imageWidth, 'AI line-graph seed is missing imageWidth.');
  const seedHeight = requireNumber(seed.imageHeight, 'AI line-graph seed is missing imageHeight.');
  const scaleX = imageWidth / Math.max(1, seedWidth);
  const scaleY = imageHeight / Math.max(1, seedHeight);
  const gridBounds = readCoordinateBounds(seed.gridBounds) ?? {
    minI: 0,
    maxI: readPositiveInteger(seed.columns) ?? 1,
    minJ: 0,
    maxJ: readPositiveInteger(seed.rows) ?? 1,
  };
  const homography = flatHomographyToMatrix(requireFlatHomography(seed.gridHomography));
  const frameBounds = boundsForImageFrame(homography, seedWidth, seedHeight, gridBounds);
  const metadata = {
    dotVariantId: typeof hybrid.linePromptId === 'string' ? hybrid.linePromptId : undefined,
    decision: line.decision,
    projectionReadinessMode: 'observed-grid-graph',
    noLabelProjectionReadinessMode: 'no-label-observed-line-graph',
    visibleMeshLineWithin0_15Pct: line.selectedLineWithin0_15Pct,
    visibleMeshCells: line.completeCells,
    unsupportedCellCount: typeof line.possibleCells === 'number' && typeof line.completeCells === 'number'
      ? Math.max(0, line.possibleCells - line.completeCells)
      : undefined,
    visibleMeshCellDensity: typeof line.completeCellDensityPct === 'number'
      ? line.completeCellDensityPct / 100
      : undefined,
  };
  const modes = [
    buildSeedMode({
      modeId: 'grid-frame',
      modeLabel: `Bounded image-frame grid (${String(hybrid.linePromptId ?? 'line prompt')})`,
      riskLevel: 'review',
      explanation: 'Uses the final hybrid line graph as an alignment frame and extrapolates it across the source image, capped at 100 x 100 cells and trimmed so whole off-image rows/columns are not kept.',
      homography,
      bounds: frameBounds,
      scaleX,
      scaleY,
      metadata: {
        ...frameMetadata(metadata, frameBounds),
        projectionReadinessMode: 'bounded-image-frame-grid',
        noLabelProjectionReadinessMode: 'no-label-bounded-image-frame-grid',
      },
    }),
    buildSeedMode({
      modeId: 'supported',
      modeLabel: `Final hybrid line graph (${String(hybrid.linePromptId ?? 'line prompt')})`,
      riskLevel: 'review',
      explanation: 'Final report-only hybrid selected an observed line-graph patch. This is the directly supported graph island, not the bounded extrapolated frame.',
      homography,
      bounds: gridBounds,
      scaleX,
      scaleY,
      metadata,
    }),
    buildSeedMode({
      modeId: 'label-sized-diagnostic',
      modeLabel: 'Label-sized diagnostic (uses labels)',
      riskLevel: 'diagnostic',
      explanation: 'Uses saved fixture row/column counts to show whether the lattice itself aligns at the human-labelled extent. Not available at runtime.',
      homography,
      bounds: boundsForCellSpanAroundCenter(gridBounds, readPositiveInteger(label.columns), readPositiveInteger(label.rows)),
      scaleX,
      scaleY,
      metadata,
    }),
  ];
  const selectedMode = modes.find((mode) => mode.modeId === requestedMode) ?? modes[0];
  return {
    ...selectedMode,
    detected: true,
    sourceId: hybrid.sourceId,
    imageWidth,
    imageHeight,
    selectedModeId: selectedMode.modeId,
    modes,
    supportOverlay: scaleLineGraphSupportOverlay(seed.supportOverlay, scaleX, scaleY),
  };
}

function buildSeedMode({
  modeId,
  modeLabel,
  riskLevel,
  explanation,
  homography,
  bounds,
  scaleX,
  scaleY,
  metadata,
}: {
  modeId: AiGridSeedModeId;
  modeLabel: string;
  riskLevel: string;
  explanation: string;
  homography: number[][];
  bounds: GridCoordinateBounds;
  scaleX: number;
  scaleY: number;
  metadata: Record<string, unknown>;
}): Record<string, unknown> {
  return {
    modeId,
    modeLabel,
    riskLevel,
    explanation,
    corners: boundsToCorners(homography, bounds, scaleX, scaleY),
    columns: Math.max(1, bounds.maxI - bounds.minI),
    rows: Math.max(1, bounds.maxJ - bounds.minJ),
    gridBounds: bounds,
    gridHomography: scaleHomography(homography, scaleX, scaleY),
    ...metadata,
  };
}

function requireRecord(value: unknown, message: string): Record<string, unknown> {
  if (!value || typeof value !== 'object') throw new Error(message);
  return value as Record<string, unknown>;
}

function requireNumber(value: unknown, message: string): number {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(message);
  return value;
}

function requireHomography(value: unknown): number[][] {
  if (!Array.isArray(value) || value.length !== 3) throw new Error('AI grid result has no homography.');
  return value.map((row) => {
    if (!Array.isArray(row) || row.length !== 3) throw new Error('AI grid homography is invalid.');
    return row.map((cell) => requireNumber(cell, 'AI grid homography contains a non-number.'));
  });
}

function requireMeshVertices(value: unknown): Array<[number, number, number, number]> {
  if (!Array.isArray(value) || value.length === 0) throw new Error('AI grid observed mesh has no vertices.');
  return value.map((vertex) => {
    if (!Array.isArray(vertex) || vertex.length < 4) throw new Error('AI grid observed mesh vertex is invalid.');
    return [
      Math.round(requireNumber(vertex[0], 'AI grid observed mesh coordinate is invalid.')),
      Math.round(requireNumber(vertex[1], 'AI grid observed mesh coordinate is invalid.')),
      requireNumber(vertex[2], 'AI grid observed mesh point is invalid.'),
      requireNumber(vertex[3], 'AI grid observed mesh point is invalid.'),
    ];
  });
}

function requireMeshCells(value: unknown): Array<[number, number]> {
  if (!Array.isArray(value)) return [];
  return value.flatMap((cell) => {
    if (!Array.isArray(cell) || cell.length < 2) return [];
    return [[
      Math.round(requireNumber(cell[0], 'AI grid observed mesh cell coordinate is invalid.')),
      Math.round(requireNumber(cell[1], 'AI grid observed mesh cell coordinate is invalid.')),
    ] as [number, number]];
  });
}

interface GridCoordinateBounds {
  minI: number;
  maxI: number;
  minJ: number;
  maxJ: number;
}

function frameMetadata(
  metadata: Record<string, unknown>,
  bounds: GridCoordinateBounds,
): Record<string, unknown> {
  const visibleMeshCells = typeof metadata.visibleMeshCells === 'number' ? metadata.visibleMeshCells : 0;
  const frameCellCount = gridCellCount(bounds);
  return {
    ...metadata,
    projectionReadinessMode: 'bounded-image-frame-grid',
    noLabelProjectionReadinessMode: 'no-label-bounded-image-frame-grid',
    unsupportedCellCount: Math.max(0, frameCellCount - visibleMeshCells),
    visibleMeshCellDensity: frameCellCount > 0 ? visibleMeshCells / frameCellCount : undefined,
  };
}

function gridCellCount(bounds: GridCoordinateBounds): number {
  return Math.max(0, bounds.maxI - bounds.minI) * Math.max(0, bounds.maxJ - bounds.minJ);
}

function meshCoordinateBounds(vertices: Array<[number, number, number, number]>): GridCoordinateBounds {
  return {
    minI: Math.min(...vertices.map((vertex) => vertex[0])),
    maxI: Math.max(...vertices.map((vertex) => vertex[0])),
    minJ: Math.min(...vertices.map((vertex) => vertex[1])),
    maxJ: Math.max(...vertices.map((vertex) => vertex[1])),
  };
}

function expandBoundsToLineSpan(
  bounds: GridCoordinateBounds,
  spanI: number | null,
  spanJ: number | null,
): GridCoordinateBounds {
  if (!spanI || !spanJ) return bounds;
  const i = expandAxisToLineSpan(bounds.minI, bounds.maxI, spanI);
  const j = expandAxisToLineSpan(bounds.minJ, bounds.maxJ, spanJ);
  return {
    minI: i.min,
    maxI: i.max,
    minJ: j.min,
    maxJ: j.max,
  };
}

function readCoordinateBounds(value: unknown): GridCoordinateBounds | null {
  if (!value || typeof value !== 'object') return null;
  const bounds = value as Partial<GridCoordinateBounds>;
  if (
    typeof bounds.minI !== 'number'
    || typeof bounds.maxI !== 'number'
    || typeof bounds.minJ !== 'number'
    || typeof bounds.maxJ !== 'number'
  ) {
    return null;
  }
  return {
    minI: Math.round(bounds.minI),
    maxI: Math.round(bounds.maxI),
    minJ: Math.round(bounds.minJ),
    maxJ: Math.round(bounds.maxJ),
  };
}

function expandAxisToLineSpan(
  minValue: number,
  maxValue: number,
  lineSpan: number,
): { min: number; max: number } {
  const currentLineSpan = maxValue - minValue + 1;
  const extra = Math.max(0, lineSpan - currentLineSpan);
  const before = Math.floor(extra / 2);
  const after = extra - before;
  return {
    min: minValue - before,
    max: maxValue + after,
  };
}

function boundsForCellSpanAroundCenter(
  bounds: GridCoordinateBounds,
  columns: number | null,
  rows: number | null,
): GridCoordinateBounds {
  if (!columns || !rows) return bounds;
  const centerI = (bounds.minI + bounds.maxI) / 2;
  const centerJ = (bounds.minJ + bounds.maxJ) / 2;
  return {
    minI: Math.round(centerI - columns / 2),
    maxI: Math.round(centerI - columns / 2) + columns,
    minJ: Math.round(centerJ - rows / 2),
    maxJ: Math.round(centerJ - rows / 2) + rows,
  };
}

function readPositiveInteger(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0
    ? Math.round(value)
    : null;
}

function boundsToCorners(
  homography: number[][],
  bounds: GridCoordinateBounds,
  scaleX: number,
  scaleY: number,
): PointPayload[] {
  return [
    projectHomography(homography, bounds.minI, bounds.minJ),
    projectHomography(homography, bounds.maxI, bounds.minJ),
    projectHomography(homography, bounds.maxI, bounds.maxJ),
    projectHomography(homography, bounds.minI, bounds.maxJ),
  ].map((point) => ({
    x: point.x * scaleX,
    y: point.y * scaleY,
  }));
}

function boundsForImageFrame(
  homography: number[][],
  imageWidth: number,
  imageHeight: number,
  baseBounds: GridCoordinateBounds,
): GridCoordinateBounds {
  const inverse = invertHomography(homography);
  const imagePoints = [
    { x: 0, y: 0 },
    { x: imageWidth, y: 0 },
    { x: imageWidth, y: imageHeight },
    { x: 0, y: imageHeight },
    { x: imageWidth / 2, y: 0 },
    { x: imageWidth, y: imageHeight / 2 },
    { x: imageWidth / 2, y: imageHeight },
    { x: 0, y: imageHeight / 2 },
    { x: imageWidth / 2, y: imageHeight / 2 },
  ];
  const gridPoints = imagePoints.map((point) => projectHomography(inverse, point.x, point.y));
  gridPoints.push({
    x: (baseBounds.minI + baseBounds.maxI) / 2,
    y: (baseBounds.minJ + baseBounds.maxJ) / 2,
  });
  const rawBounds = {
    minI: Math.floor(Math.min(...gridPoints.map((point) => point.x))) - 1,
    maxI: Math.ceil(Math.max(...gridPoints.map((point) => point.x))) + 1,
    minJ: Math.floor(Math.min(...gridPoints.map((point) => point.y))) - 1,
    maxJ: Math.ceil(Math.max(...gridPoints.map((point) => point.y))) + 1,
  };
  return trimBoundsToImageOverlap(
    capBoundsSpan(rawBounds, baseBounds, 100),
    homography,
    imageWidth,
    imageHeight,
  );
}

function capBoundsSpan(
  bounds: GridCoordinateBounds,
  baseBounds: GridCoordinateBounds,
  maxSpan: number,
): GridCoordinateBounds {
  const i = capAxisSpan(bounds.minI, bounds.maxI, (baseBounds.minI + baseBounds.maxI) / 2, maxSpan);
  const j = capAxisSpan(bounds.minJ, bounds.maxJ, (baseBounds.minJ + baseBounds.maxJ) / 2, maxSpan);
  return {
    minI: i.min,
    maxI: i.max,
    minJ: j.min,
    maxJ: j.max,
  };
}

function capAxisSpan(
  minValue: number,
  maxValue: number,
  center: number,
  maxSpan: number,
): { min: number; max: number } {
  if (maxValue - minValue <= maxSpan) return { min: minValue, max: maxValue };
  const min = Math.floor(center - maxSpan / 2);
  return { min, max: min + maxSpan };
}

function trimBoundsToImageOverlap(
  bounds: GridCoordinateBounds,
  homography: number[][],
  imageWidth: number,
  imageHeight: number,
): GridCoordinateBounds {
  const next = { ...bounds };
  for (let iteration = 0; iteration < 240; iteration += 1) {
    let changed = false;
    if (next.maxI - next.minI > 1 && axisBandImageOverlap(homography, next, 'i', next.minI, imageWidth, imageHeight) < MIN_IMAGE_FRAME_BAND_OVERLAP) {
      next.minI += 1;
      changed = true;
    }
    if (next.maxI - next.minI > 1 && axisBandImageOverlap(homography, next, 'i', next.maxI - 1, imageWidth, imageHeight) < MIN_IMAGE_FRAME_BAND_OVERLAP) {
      next.maxI -= 1;
      changed = true;
    }
    if (next.maxJ - next.minJ > 1 && axisBandImageOverlap(homography, next, 'j', next.minJ, imageWidth, imageHeight) < MIN_IMAGE_FRAME_BAND_OVERLAP) {
      next.minJ += 1;
      changed = true;
    }
    if (next.maxJ - next.minJ > 1 && axisBandImageOverlap(homography, next, 'j', next.maxJ - 1, imageWidth, imageHeight) < MIN_IMAGE_FRAME_BAND_OVERLAP) {
      next.maxJ -= 1;
      changed = true;
    }
    if (!changed) return next;
  }
  return next;
}

function axisBandImageOverlap(
  homography: number[][],
  bounds: GridCoordinateBounds,
  axis: 'i' | 'j',
  index: number,
  imageWidth: number,
  imageHeight: number,
): number {
  const otherMin = axis === 'i' ? bounds.minJ : bounds.minI;
  const otherMax = axis === 'i' ? bounds.maxJ : bounds.maxI;
  const span = Math.max(1, otherMax - otherMin);
  const steps = Math.min(120, Math.max(8, Math.ceil(span * 3)));
  let inside = 0;
  let total = 0;
  for (let step = 0; step <= steps; step += 1) {
    const t = otherMin + (span * step) / steps;
    for (const offset of [0.2, 0.5, 0.8]) {
      const x = axis === 'i' ? index + offset : t;
      const y = axis === 'i' ? t : index + offset;
      total += 1;
      try {
        if (isImagePoint(projectHomography(homography, x, y), imageWidth, imageHeight)) inside += 1;
      } catch {
        // Treat samples at or beyond the projective horizon as off-image.
      }
    }
  }
  return total > 0 ? inside / total : 0;
}

function isImagePoint(point: { x: number; y: number }, imageWidth: number, imageHeight: number): boolean {
  return point.x >= 0 && point.x <= imageWidth && point.y >= 0 && point.y <= imageHeight;
}

function scaleHomography(homography: number[][], scaleX: number, scaleY: number): number[] {
  return [
    homography[0][0] * scaleX,
    homography[0][1] * scaleX,
    homography[0][2] * scaleX,
    homography[1][0] * scaleY,
    homography[1][1] * scaleY,
    homography[1][2] * scaleY,
    homography[2][0],
    homography[2][1],
    homography[2][2],
  ];
}

function projectHomography(homography: number[][], x: number, y: number): { x: number; y: number } {
  const denominator = homography[2][0] * x + homography[2][1] * y + homography[2][2];
  if (!Number.isFinite(denominator) || Math.abs(denominator) < 1e-9) {
    throw new Error('AI grid homography projects a corner to infinity.');
  }
  return {
    x: (homography[0][0] * x + homography[0][1] * y + homography[0][2]) / denominator,
    y: (homography[1][0] * x + homography[1][1] * y + homography[1][2]) / denominator,
  };
}

function invertHomography(homography: number[][]): number[][] {
  const [[a, b, c], [d, e, f], [g, h, i]] = homography;
  const determinant =
    a * (e * i - f * h)
    - b * (d * i - f * g)
    + c * (d * h - e * g);
  if (!Number.isFinite(determinant) || Math.abs(determinant) < 1e-9) {
    throw new Error('AI grid homography is not invertible.');
  }
  return [
    [(e * i - f * h) / determinant, (c * h - b * i) / determinant, (b * f - c * e) / determinant],
    [(f * g - d * i) / determinant, (a * i - c * g) / determinant, (c * d - a * f) / determinant],
    [(d * h - e * g) / determinant, (b * g - a * h) / determinant, (a * e - b * d) / determinant],
  ];
}

interface PointPayload {
  x: number;
  y: number;
}

function requirePointPayloads(value: unknown, message: string): PointPayload[] {
  if (!Array.isArray(value)) throw new Error(message);
  return value.map((item) => {
    if (!item || typeof item !== 'object') throw new Error(message);
    const point = item as Partial<PointPayload>;
    return {
      x: requireNumber(point.x, message),
      y: requireNumber(point.y, message),
    };
  });
}

function scalePointPayload(point: PointPayload, scaleX: number, scaleY: number): PointPayload {
  return {
    x: point.x * scaleX,
    y: point.y * scaleY,
  };
}

function requireFlatHomography(value: unknown): number[] {
  if (!Array.isArray(value) || value.length !== 9) {
    throw new Error('AI line-graph seed homography is invalid.');
  }
  return value.map((item) => requireNumber(item, 'AI line-graph seed homography is invalid.'));
}

function flatHomographyToMatrix(homography: number[]): number[][] {
  return [
    [homography[0], homography[1], homography[2]],
    [homography[3], homography[4], homography[5]],
    [homography[6], homography[7], homography[8]],
  ];
}

function scaleFlatHomography(homography: number[], scaleX: number, scaleY: number): number[] {
  return [
    homography[0] * scaleX,
    homography[1] * scaleX,
    homography[2] * scaleX,
    homography[3] * scaleY,
    homography[4] * scaleY,
    homography[5] * scaleY,
    homography[6],
    homography[7],
    homography[8],
  ];
}

function buildSupportOverlay(
  vertices: Array<[number, number, number, number]>,
  cells: Array<[number, number]>,
  scaleX: number,
  scaleY: number,
): unknown {
  const vertexMap = new Map<string, PointPayload>();
  for (const [i, j, x, y] of vertices) {
    vertexMap.set(coordinateKey(i, j), { x: x * scaleX, y: y * scaleY });
  }
  const supportCells = cells.flatMap(([i, j]) => {
    const corners = [
      vertexMap.get(coordinateKey(i, j)),
      vertexMap.get(coordinateKey(i + 1, j)),
      vertexMap.get(coordinateKey(i + 1, j + 1)),
      vertexMap.get(coordinateKey(i, j + 1)),
    ];
    if (corners.some((corner) => !corner)) return [];
    return [{
      i,
      j,
      corners: corners as [PointPayload, PointPayload, PointPayload, PointPayload],
    }];
  });

  return {
    vertexCount: vertices.length,
    cellCount: supportCells.length,
    cells: supportCells,
  };
}

function scaleLineGraphSupportOverlay(value: unknown, scaleX: number, scaleY: number): unknown {
  if (!value || typeof value !== 'object') return undefined;
  const overlay = value as {
    vertexCount?: unknown;
    cellCount?: unknown;
    cells?: unknown;
  };
  const cells = Array.isArray(overlay.cells)
    ? overlay.cells.flatMap((cell) => {
        if (!cell || typeof cell !== 'object') return [];
        const item = cell as { i?: unknown; j?: unknown; corners?: unknown };
        const corners = requirePointPayloads(item.corners, 'AI line-graph support cell is invalid.')
          .map((point) => scalePointPayload(point, scaleX, scaleY));
        if (corners.length !== 4) return [];
        return [{
          i: Math.round(requireNumber(item.i, 'AI line-graph support cell coordinate is invalid.')),
          j: Math.round(requireNumber(item.j, 'AI line-graph support cell coordinate is invalid.')),
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

function coordinateKey(i: number, j: number): string {
  return `${i},${j}`;
}

function readImageDimensionsSync(path: string): { width: number; height: number } {
  const buffer = readFileSync(path);
  const pngSignature = '89504e470d0a1a0a';
  if (buffer.length >= 24 && buffer.subarray(0, 8).toString('hex') === pngSignature) {
    return {
      width: buffer.readUInt32BE(16),
      height: buffer.readUInt32BE(20),
    };
  }
  if (buffer.length >= 4 && buffer[0] === 0xff && buffer[1] === 0xd8) return readJpegDimensions(path, buffer);
  throw new Error(`Expected a PNG or JPEG AI grid image at ${path}.`);
}

function readJpegDimensions(path: string, buffer: Buffer): { width: number; height: number } {
  let offset = 2;
  while (offset + 9 < buffer.length) {
    while (offset < buffer.length && buffer[offset] === 0xff) offset += 1;
    const marker = buffer[offset];
    offset += 1;
    if (marker === 0xd8 || marker === 0xd9) continue;
    if (offset + 2 > buffer.length) break;
    const segmentLength = buffer.readUInt16BE(offset);
    if (segmentLength < 2 || offset + segmentLength > buffer.length) break;
    if (
      marker === 0xc0
      || marker === 0xc1
      || marker === 0xc2
      || marker === 0xc3
      || marker === 0xc5
      || marker === 0xc6
      || marker === 0xc7
      || marker === 0xc9
      || marker === 0xca
      || marker === 0xcb
      || marker === 0xcd
      || marker === 0xce
      || marker === 0xcf
    ) {
      return {
        height: buffer.readUInt16BE(offset + 3),
        width: buffer.readUInt16BE(offset + 5),
      };
    }
    offset += segmentLength;
  }
  throw new Error(`Could not read JPEG dimensions for ${path}.`);
}

function resolveRepoPath(value: string): string {
  if (!value) throw new Error('AI grid report is missing lineImage.');
  const path = resolve(root, value);
  const relativePath = relative(root, path);
  if (relativePath.startsWith('..') || relativePath.includes(`..${sep}`) || relativePath === '') {
    throw new Error('AI grid report path is outside the repo.');
  }
  return path;
}

async function readLabelPayload(): Promise<unknown> {
  try {
    await access(labelFilePath);
    return JSON.parse(await readFile(labelFilePath, 'utf8'));
  } catch {
    return { version: 1, updatedAt: null, labels: [] };
  }
}

function findLabelPayload(value: unknown, sourceId: string): Record<string, unknown> | null {
  if (!value || typeof value !== 'object') return null;
  const labels = (value as { labels?: unknown }).labels;
  if (!Array.isArray(labels)) return null;
  const label = labels.find((item) => (
    item
    && typeof item === 'object'
    && (item as { sourceId?: unknown }).sourceId === sourceId
  ));
  return label && typeof label === 'object' ? label as Record<string, unknown> : null;
}

function readRequestBody(request: import('node:http').IncomingMessage): Promise<string> {
  return new Promise((resolveBody, reject) => {
    let body = '';
    request.setEncoding('utf8');
    request.on('data', (chunk) => {
      body += chunk;
      if (body.length > 1_000_000) {
        reject(new Error('Fixture label payload is too large.'));
        request.destroy();
      }
    });
    request.on('end', () => resolveBody(body));
    request.on('error', reject);
  });
}

function isLabelPayload(value: unknown): boolean {
  if (!value || typeof value !== 'object') return false;
  const payload = value as { version?: unknown; labels?: unknown };
  return payload.version === 1 && Array.isArray(payload.labels);
}

function sendJson(response: import('node:http').ServerResponse, statusCode: number, payload: unknown): void {
  response.statusCode = statusCode;
  response.setHeader('Content-Type', 'application/json; charset=utf-8');
  response.end(JSON.stringify(payload));
}

function sendText(response: import('node:http').ServerResponse, statusCode: number, text: string): void {
  response.statusCode = statusCode;
  response.setHeader('Content-Type', 'text/plain; charset=utf-8');
  response.end(text);
}
