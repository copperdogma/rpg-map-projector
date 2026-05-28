import { expect, test } from '@playwright/test';

test('controller renders a nonblank calibration workbench', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByRole('heading', { name: 'Calibration Projection Spike' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Open Projector View' })).toBeVisible();
  await expect(page.locator('#controller-preview')).toBeVisible();

  await expect.poll(() => countNonBlankPixels(page, '#controller-preview')).toBeGreaterThan(5000);
});

test('projector view renders the calibration pattern', async ({ page }) => {
  await page.goto('/projector.html');

  await expect(page.getByText('Projector View')).toBeVisible();
  await expect(page.locator('#projector-canvas')).toBeVisible();

  await expect.poll(() => countNonBlankPixels(page, '#projector-canvas')).toBeGreaterThan(5000);
});

test('controller source scale updates projector state storage', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('button', { name: '10 ft source' }).click();

  const storedScale = await page.evaluate(() => {
    const raw = window.localStorage.getItem('rpg-map-projector:story-001-calibration');
    return raw ? JSON.parse(raw).sourceSquareFeet : null;
  });

  expect(storedScale).toBe(10);
});

test('controller runs generated false-input grid detection and aligns projector anchors', async ({ page }) => {
  await page.goto('/');

  await page.getByRole('button', { name: 'Auto Detect Grid' }).click();
  await expect(page.locator('#detection-status')).toContainText(/confidence/i);
  await expect(page.locator('#alignment-status')).toContainText('Auto-aligned');

  const state = await page.evaluate(() => {
    const raw = window.localStorage.getItem('rpg-map-projector:story-001-calibration');
    return raw ? JSON.parse(raw) : null;
  });

  expect(state?.detectedGrid?.corners).toHaveLength(4);
  expect(state?.detectedGrid?.confidence).toBeGreaterThan(0.3);
  expect(state?.detectedGrid?.columns).toBe(12);
  expect(state?.detectedGrid?.rows).toBe(8);
  expect(meanCornerError(state?.detectedGrid?.corners ?? [], [
    { x: 120, y: 120 },
    { x: 960, y: 120 },
    { x: 960, y: 680 },
    { x: 120, y: 680 },
  ])).toBeLessThan(5);
  expect(state?.projectionAlignment?.source).toBe('detected-grid');
  expect(state?.anchors[1].physical).toEqual({ x: 12, y: 0 });
});

test('controller labels rejected detections as candidate-only and not applied', async ({ page }) => {
  await page.goto('/');

  await page.evaluate(() => {
    const raw = window.localStorage.getItem('rpg-map-projector:story-001-calibration');
    const state = raw ? JSON.parse(raw) : null;
    state.detectedGrid = {
      sourceName: 'rejected-test-frame.png',
      sourceUrl: 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" width="10" height="10"%3E%3C/svg%3E',
      imageWidth: 1000,
      imageHeight: 800,
      corners: [
        { x: 70, y: 90 },
        { x: 930, y: 80 },
        { x: 890, y: 720 },
        { x: 80, y: 710 },
      ],
      columns: 12,
      rows: 8,
      confidence: 0.34,
      latticeScore: 0.1,
      families: [
        { angleDegrees: 0, lineCount: 13, score: 100 },
        { angleDegrees: 90, lineCount: 9, score: 80 },
      ],
      detectedAt: '2026-05-27T00:00:00.000Z',
      message: 'Detected 12 x 8 grid candidate.',
    };
    state.projectionAlignment = null;
    state.projectionAlignmentIssue = 'Manual correction required: confidence is below the auto-align threshold. Projector anchors unchanged.';
    window.localStorage.setItem('rpg-map-projector:story-001-calibration', JSON.stringify(state));
  });
  await page.reload();

  await expect(page.locator('#detection-status')).toContainText('Candidate only; not applied');
  await expect(page.locator('#detection-status')).toContainText('10% lattice support');
  await expect(page.locator('#detection-status')).toHaveClass(/status-warning/);
  await expect(page.locator('#alignment-status')).toContainText('Manual correction required');
  await expect(page.getByRole('button', { name: 'Force Apply Candidate' })).toBeVisible();
});

test('controller can use a projector screenshot as a simulated camera frame', async ({ page }, testInfo) => {
  await page.goto('/');
  await page.evaluate(() => {
    const raw = window.localStorage.getItem('rpg-map-projector:story-001-calibration');
    const state = raw ? JSON.parse(raw) : null;
    state.showCalibrationPoints = false;
    state.showPhysicalGrid = false;
    state.showSourceGrid = true;
    state.brightness = 1.4;
    window.localStorage.setItem('rpg-map-projector:story-001-calibration', JSON.stringify(state));
  });

  const projector = await page.context().newPage();
  await projector.goto('/projector.html');
  await projector.addStyleTag({ content: '.projector-hud{display:none!important}' });
  const screenshotPath = testInfo.outputPath('simulated-projector-camera-frame.png');
  await projector.locator('#projector-canvas').screenshot({ path: screenshotPath });
  await projector.close();

  await page.goto('/');
  await page.locator('#image-upload').setInputFiles(screenshotPath);
  await expect(page.locator('#detection-status')).toContainText(/confidence/i);
  await expect(page.locator('#alignment-status')).toContainText('Auto-aligned');

  const state = await page.evaluate(() => {
    const raw = window.localStorage.getItem('rpg-map-projector:story-001-calibration');
    return raw ? JSON.parse(raw) : null;
  });

  expect(state?.detectedGrid?.sourceName).toBe('simulated-projector-camera-frame.png');
  expect(state?.projectionAlignment?.mode).toBe('simulated-image-fit');
  expect(state?.anchors[2].projector.x).toBeGreaterThan(state?.anchors[0].projector.x);
  expect(state?.anchors[2].projector.y).toBeGreaterThan(state?.anchors[0].projector.y);
});

async function countNonBlankPixels(page: import('@playwright/test').Page, selector: string): Promise<number> {
  return page.locator(selector).evaluate((canvas: HTMLCanvasElement) => {
    const context = canvas.getContext('2d');
    if (!context) return 0;
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let count = 0;
    for (let index = 0; index < data.length; index += 4) {
      if (data[index] !== 0 || data[index + 1] !== 0 || data[index + 2] !== 0) {
        count += 1;
      }
    }
    return count;
  });
}

function meanCornerError(actual: Array<{ x: number; y: number }>, expected: Array<{ x: number; y: number }>): number {
  return actual.reduce((sum, point, index) => (
    sum + Math.hypot(point.x - expected[index].x, point.y - expected[index].y)
  ), 0) / expected.length;
}
