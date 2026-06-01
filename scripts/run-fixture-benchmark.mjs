#!/usr/bin/env node

import { chromium } from '@playwright/test';
import { spawn } from 'node:child_process';
import { mkdir, writeFile } from 'node:fs/promises';
import { dirname, join, resolve } from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';
import { resolveLocalDevPorts } from './local-dev-ports.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const runtime = resolveLocalDevPorts('rpg-map-projector', ROOT);
const PORT = Number.parseInt(process.env.RPG_MAP_PROJECTOR_UI_PORT ?? String(runtime.ports.ui), 10);
const HOST = process.env.RPG_MAP_PROJECTOR_UI_HOST ?? '127.0.0.1';
const BASE_URL = `http://${HOST}:${PORT}`;
const OUT_DIR = resolve(ROOT, process.env.FIXTURE_BENCHMARK_OUT_DIR ?? 'test-results/story-002-fixture-benchmark');
const QUERY = process.env.FIXTURE_BENCHMARK_QUERY ?? 'run=1';

let server = null;

try {
  await ensureServer();
  await runBenchmark();
} finally {
  if (server) server.kill('SIGTERM');
}

async function runBenchmark() {
  await mkdir(join(OUT_DIR, 'overlays'), { recursive: true });

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  try {
    await page.goto(`${BASE_URL}/benchmark.html?${QUERY}`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => window.__fixtureBenchmarkDone === true, null, { timeout: 90_000 });

    const report = await page.evaluate(() => window.__fixtureBenchmarkReport);
    const markdown = await page.evaluate(() => window.__fixtureBenchmarkMarkdown);
    if (!report || !markdown) throw new Error('Benchmark page did not expose a report.');

    await writeFile(join(OUT_DIR, 'report.json'), `${JSON.stringify(report, null, 2)}\n`, 'utf8');
    await writeFile(join(OUT_DIR, 'report.md'), markdown, 'utf8');
    await page.screenshot({ path: join(OUT_DIR, 'benchmark-page.png'), fullPage: true });

    const overlays = page.locator('canvas[data-overlay-index]');
    const count = await overlays.count();
    for (let index = 0; index < count; index += 1) {
      const canvas = overlays.nth(index);
      const sourceId = await canvas.getAttribute('data-source-id');
      await canvas.screenshot({
        path: join(OUT_DIR, 'overlays', `${String(index + 1).padStart(2, '0')}-${slugify(sourceId ?? `fixture-${index + 1}`)}.png`),
      });
    }

    printSummary(report);
  } finally {
    await browser.close();
  }
}

async function ensureServer() {
  if (await isHealthy()) return;

  server = spawn(
    localBin('vite'),
    ['--host', HOST, '--port', String(PORT), '--strictPort'],
    {
      cwd: ROOT,
      env: {
        ...process.env,
        RPG_MAP_PROJECTOR_UI_PORT: String(PORT),
        FRONTEND_PORT: String(PORT),
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    },
  );

  server.stdout.on('data', (chunk) => process.stdout.write(chunk));
  server.stderr.on('data', (chunk) => process.stderr.write(chunk));

  const started = Date.now();
  while (Date.now() - started < 30_000) {
    if (await isHealthy()) return;
    await sleep(250);
  }

  throw new Error(`Timed out waiting for ${BASE_URL}`);
}

async function isHealthy() {
  try {
    const response = await fetch(`${BASE_URL}/benchmark.html`);
    return response.ok && (await response.text()).includes('Fixture Benchmark');
  } catch {
    return false;
  }
}

function printSummary(report) {
  const { summary } = report;
  console.log(`Fixture benchmark wrote ${OUT_DIR}`);
  if (Array.isArray(report.candidateSummaries)) {
    for (const candidate of report.candidateSummaries) {
      console.log(`  candidate: ${candidate.candidateName}`);
      console.log(`    total: ${candidate.total}`);
      console.log(`    strict sales-photo successes: ${candidate.strictSalesPhotoSuccess}/${candidate.salesPhotoFixtures}`);
      console.log(`    auto-accepted accurate: ${candidate.autoAcceptedAccurate}`);
      console.log(`    manual correction seeds: ${candidate.manualCorrectionSeed}`);
      console.log(`    rough correction seeds: ${candidate.roughCorrectionSeed}`);
      console.log(`    safe refusals: ${candidate.safeRefusal}`);
      console.log(`    wrong confident: ${candidate.wrongConfident}`);
      console.log(`    benchmark errors: ${candidate.benchmarkError}`);
    }
  }
  console.log(`  total: ${summary.total}`);
  console.log(`  strict sales-photo successes: ${summary.strictSalesPhotoSuccess}/${summary.salesPhotoFixtures}`);
  console.log(`  auto-accepted accurate: ${summary.autoAcceptedAccurate}`);
  console.log(`  manual correction seeds: ${summary.manualCorrectionSeed}`);
  console.log(`  rough correction seeds: ${summary.roughCorrectionSeed}`);
  console.log(`  safe refusals: ${summary.safeRefusal}`);
  console.log(`  wrong confident: ${summary.wrongConfident}`);
  console.log(`  benchmark errors: ${summary.benchmarkError}`);
  console.log(`  recommendation: ${report.recommendation}`);
}

function localBin(name) {
  const suffix = process.platform === 'win32' ? '.cmd' : '';
  return join(ROOT, 'node_modules', '.bin', `${name}${suffix}`);
}

function sleep(ms) {
  return new Promise((resolveSleep) => {
    setTimeout(resolveSleep, ms);
  });
}

function slugify(value) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '')
    .slice(0, 80);
}
