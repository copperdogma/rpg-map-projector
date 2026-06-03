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

test('controller can blank the projector output without projecting the HUD', async ({ page }) => {
  await page.goto('/');
  const projector = await page.context().newPage();
  await projector.goto('/projector.html');

  await expect.poll(() => countBrightPixels(projector, '#projector-canvas', 40)).toBeGreaterThan(5000);

  await page.getByRole('button', { name: 'Blank', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Blank', exact: true })).toHaveClass(/selected/);
  await expect(projector.locator('#projector-root')).toHaveAttribute('data-projector-mode', 'blank');
  await expect(projector.getByText('Projector View')).not.toBeVisible();
  await expect.poll(() => countBrightPixels(projector, '#projector-canvas', 40)).toBeLessThan(20);

  await page.getByRole('button', { name: 'Alignment grid' }).click();
  await expect(projector.locator('#projector-root')).toHaveAttribute('data-projector-mode', 'alignment');
  await expect(projector.getByText('Projector View')).toBeVisible();
  await expect.poll(() => countBrightPixels(projector, '#projector-canvas', 40)).toBeGreaterThan(5000);

  await projector.close();
});

test('fixture labeler renders editable benchmark grid labels', async ({ page }) => {
  await page.goto('/labeler.html');

  await expect(page.getByRole('heading', { name: 'Grid Fixture Labeler' })).toBeVisible();
  await expect(page.locator('#labeler-canvas')).toBeVisible();
  await expect(page.locator('#label-columns')).toHaveValue('12');
  await expect(page.locator('#label-rows')).toHaveValue('8');
  await expect(page.locator('#show-label-grid')).toBeChecked();
  await expect(page.getByRole('button', { name: 'Use OpenCV Seed' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Use AI Seed' })).toBeVisible();
  await expect(page.locator('#ai-seed-mode')).toHaveValue('grid-frame');
  await expect(page.locator('#ai-seed-mode')).toContainText('Bounded image-frame grid');
  await expect(page.locator('#ai-seed-mode')).toContainText('Supported visible patch');
  await expect(page.getByText('Show AI support cells')).toBeVisible();
  await expect(page.locator('#show-ai-support')).not.toBeChecked();
  await expect(page.getByRole('button', { name: 'Fit' })).toBeVisible();
  await expect(page.getByRole('button', { name: '100%' })).toBeVisible();
  await expect(page.getByRole('button', { name: '200%' })).toBeVisible();
  await expect(page.locator('#native-readout')).toContainText(/Native \d+ x \d+/);
  await expect(page.getByText('Show virtual grid overlay')).toContainText('G');
  await expect(page.locator('.labeler-stepper').filter({ hasText: 'Columns' })).toContainText('C');
  await expect(page.locator('.labeler-stepper').filter({ hasText: 'Rows' })).toContainText('R');

  await expect.poll(() => countNonBlankPixels(page, '#labeler-canvas')).toBeGreaterThan(5000);
  await expect(page.locator('#labeler-canvas')).toHaveAttribute('data-view-mode', 'fit');
  await page.getByRole('button', { name: '100%' }).click();
  await expect(page.locator('#labeler-canvas')).toHaveAttribute('data-view-mode', 'manual');
  await expect(page.locator('#labeler-canvas')).toHaveAttribute('data-zoom-scale', '1');
  const canvasBox = await page.locator('#labeler-canvas').boundingBox();
  expect(canvasBox).not.toBeNull();
  await page.mouse.move((canvasBox?.x ?? 0) + (canvasBox?.width ?? 1) / 2, (canvasBox?.y ?? 0) + (canvasBox?.height ?? 1) / 2);
  await page.mouse.wheel(0, -200);
  await expect.poll(() => readLabelerZoomScale(page)).toBeGreaterThan(1.2);
  await page.getByRole('button', { name: 'Fit' }).click();
  await expect(page.locator('#labeler-canvas')).toHaveAttribute('data-view-mode', 'fit');

  const virtualGridPixels = await countVirtualGridPixels(page, '#labeler-canvas');
  expect(virtualGridPixels).toBeGreaterThan(1000);

  await page.locator('#show-label-grid').uncheck();
  await expect(page.locator('#labeler-canvas')).toHaveAttribute('data-grid-overlay', 'hidden');
  expect(await countVirtualGridPixels(page, '#labeler-canvas')).toBeLessThan(virtualGridPixels * 0.25);

  await page.locator('#show-label-grid').check();
  await expect(page.locator('#labeler-canvas')).toHaveAttribute('data-grid-overlay', 'visible');

  await page.keyboard.press('g');
  await expect(page.locator('#show-label-grid')).not.toBeChecked();
  await expect(page.locator('#labeler-canvas')).toHaveAttribute('data-grid-overlay', 'hidden');
  await page.keyboard.press('g');
  await expect(page.locator('#show-label-grid')).toBeChecked();
  await expect(page.locator('#labeler-canvas')).toHaveAttribute('data-grid-overlay', 'visible');

  await page.locator('#label-columns').focus();
  await page.keyboard.press('g');
  await expect(page.locator('#show-label-grid')).toBeChecked();
  await expect(page.locator('#labeler-canvas')).toHaveAttribute('data-grid-overlay', 'visible');

  await page.locator('#labeler-canvas').click();
  await page.keyboard.press('c');
  await expect(page.locator('#label-columns')).toHaveValue('13');
  await page.keyboard.press('Shift+c');
  await expect(page.locator('#label-columns')).toHaveValue('12');
  await page.keyboard.press('r');
  await expect(page.locator('#label-rows')).toHaveValue('9');
  await page.keyboard.press('Shift+r');
  await expect(page.locator('#label-rows')).toHaveValue('8');

  await page.locator('#label-rows').focus();
  await page.keyboard.press('r');
  await expect(page.locator('#label-rows')).toHaveValue('8');

  await page.locator('[data-step-field="columns"][data-step="1"]').click();
  await expect(page.locator('#label-columns')).toHaveValue('13');
  await expect(page.locator('#labeler-status')).toContainText('Unsaved changes');
});

test('fixture labeler moves whole grid edges on the locked axis', async ({ page }) => {
  await page.goto('/labeler.html');
  await expect(page.locator('#label-columns')).toHaveValue('12');
  await expect.poll(() => countNonBlankPixels(page, '#labeler-canvas')).toBeGreaterThan(5000);

  const beforeA = await readLabelCornerValues(page, 0);
  const beforeB = await readLabelCornerValues(page, 1);
  const topHandle = await labelerCanvasPointForNatural(page, {
    x: (beforeA.x + beforeB.x) / 2,
    y: (beforeA.y + beforeB.y) / 2,
  });

  await page.mouse.move(topHandle.x, topHandle.y);
  await page.mouse.down();
  await expect(page.locator('#labeler-canvas')).toHaveAttribute('data-dragging-edge', '0');
  await page.mouse.move(topHandle.x, topHandle.y + 36, { steps: 6 });
  await page.mouse.up();

  const afterA = await readLabelCornerValues(page, 0);
  const afterB = await readLabelCornerValues(page, 1);
  expect(afterA.x).toBe(beforeA.x);
  expect(afterB.x).toBe(beforeB.x);
  expect(afterA.y).toBeGreaterThan(beforeA.y);
  expect(afterB.y).toBeGreaterThan(beforeB.y);
  await expect(page.locator('#labeler-status')).toContainText('Grid edge moved');
});

test('fixture labeler seeds labels from the OpenCV gateway detector', async ({ page }) => {
  await page.route('**/__opencv-detection?**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        detected: true,
        imageWidth: 1080,
        imageHeight: 800,
        corners: [
          { x: 100, y: 110 },
          { x: 980, y: 120 },
          { x: 960, y: 690 },
          { x: 90, y: 680 },
        ],
        columns: 17,
        rows: 13,
        confidence: 0.35,
        latticeScore: 0.08,
        selectedFitKind: 'test-opencv-seed',
        detectorMessage: 'stubbed OpenCV seed',
        elapsedMs: 1234,
      }),
    });
  });

  await page.goto('/labeler.html');
  await page.getByRole('button', { name: 'Use OpenCV Seed' }).click();

  await expect(page.locator('#label-columns')).toHaveValue('17');
  await expect(page.locator('#label-rows')).toHaveValue('13');
  await expect(page.locator('#labeler-status')).toContainText('OpenCV seed applied');
  await expect(page.locator('#labeler-status')).toContainText('17 x 13');

  const corner = await readLabelCornerValues(page, 0);
  expect(corner).toEqual({ x: 100, y: 110 });
});

test('fixture labeler seeds labels from the current AI grid report', async ({ page }) => {
  await page.route('**/__ai-grid-seed?**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        detected: true,
        imageWidth: 1080,
        imageHeight: 800,
        corners: [
          { x: 120, y: 130 },
          { x: 980, y: 125 },
          { x: 970, y: 690 },
          { x: 110, y: 700 },
        ],
        columns: 21,
        rows: 11,
        modeId: 'fit-span',
        modeLabel: 'Selected dot extent (extrapolates)',
        riskLevel: 'medium',
        dotVariantId: 'dot-v05',
        decision: 'accepted-visible-lattice-geometry',
        noLabelProjectionReadinessMode: 'no-label-full-span-candidate',
        fullSpanHomographyLineWithin0_15Pct: 98.7,
        visibleMeshCells: 120,
        unsupportedCellCount: 40,
        supportOverlay: {
          vertexCount: 4,
          cellCount: 1,
          cells: [
            {
              i: 0,
              j: 0,
              corners: [
                { x: 120, y: 130 },
                { x: 160, y: 130 },
                { x: 160, y: 170 },
                { x: 120, y: 170 },
              ],
            },
          ],
        },
      }),
    });
  });

  await page.goto('/labeler.html');
  await page.locator('#ai-seed-mode').selectOption('fit-span');
  await page.getByRole('button', { name: 'Use AI Seed' }).click();

  await expect(page.locator('#label-columns')).toHaveValue('21');
  await expect(page.locator('#label-rows')).toHaveValue('11');
  await expect(page.locator('#labeler-status')).toContainText('AI seed Selected dot extent (extrapolates) dot-v05 applied');
  await expect(page.locator('#labeler-status')).toContainText('21 x 11');
  await expect(page.locator('#labeler-status')).toContainText('supported 120 cells / unsupported 40');
  await expect(page.locator('#labeler-canvas')).toHaveAttribute('data-ai-support-overlay', 'hidden');
  await page.locator('#show-ai-support').check();
  await expect(page.locator('#labeler-canvas')).toHaveAttribute('data-ai-support-overlay', 'visible');

  const corner = await readLabelCornerValues(page, 0);
  expect(corner).toEqual({ x: 120, y: 130 });
});

test('fixture labeler save refreshes labeled state and reloads saved labels', async ({ page }) => {
  await page.route('**/__fixture-labels', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, path: 'test-intercepted-labels.json' }),
      });
      return;
    }
    await route.continue();
  });

  await page.goto('/labeler.html');
  await expect(page.locator('#label-columns')).toHaveValue('12');

  await page.locator('[data-step-field="columns"][data-step="1"]').click();
  await expect(page.locator('#fixture-meta')).toContainText('unsaved changes');
  await page.getByRole('button', { name: 'Save Fixture' }).click();

  await expect(page.locator('#labeler-status')).toContainText('now labeled');
  await expect(page.locator('#fixture-meta')).toContainText('labeled');
  await expect(page.locator('#fixture-meta')).not.toContainText('unsaved changes');

  await page.getByRole('button', { name: 'Next', exact: true }).click();
  await expect(page.locator('#fixture-title')).toContainText(/Local mat photo 1/);
  await page.getByRole('button', { name: 'Previous' }).click();
  await expect(page.locator('#fixture-title')).toContainText('Generated test mat');
  await expect(page.locator('#label-columns')).toHaveValue('13');
});

test('fixture labeler shows a zoom reticle while dragging a corner', async ({ page }) => {
  await page.goto('/labeler.html');
  await expect(page.locator('#label-columns')).toHaveValue('12');
  await expect.poll(() => countNonBlankPixels(page, '#labeler-canvas')).toBeGreaterThan(5000);

  const target = await defaultLabelCornerCanvasPoint(page, 0);
  await page.mouse.move(target.x, target.y);
  await page.mouse.down();
  await expect(page.locator('#labeler-canvas')).toHaveAttribute('data-magnifier', 'visible');
  await expect(page.locator('#labeler-canvas')).toHaveAttribute('data-dragging-corner', 'A');

  const reticlePixels = await countReticlePixels(page, '#labeler-canvas');
  expect(reticlePixels).toBeGreaterThan(40);

  await page.mouse.up();
  await expect(page.locator('#labeler-canvas')).not.toHaveAttribute('data-magnifier', 'visible');
});

test('fixture labeler auto-pans when dragging a corner against the viewport edge', async ({ page }) => {
  await page.goto('/labeler.html');
  await page.getByRole('button', { name: '100%' }).click();
  await expect(page.locator('#labeler-canvas')).toHaveAttribute('data-view-mode', 'manual');

  const start = await defaultLabelCornerCanvasPoint(page, 0);
  const before = await readLabelViewport(page);
  const canvasBox = await page.locator('#labeler-canvas').boundingBox();
  expect(canvasBox).not.toBeNull();

  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move((canvasBox?.x ?? 0) - 120, (canvasBox?.y ?? 0) - 120, { steps: 8 });

  const during = await readLabelViewport(page);
  expect(during.minX).toBeLessThan(before.minX);
  expect(during.minY).toBeLessThan(before.minY);

  await page.mouse.up();
  const afterRelease = await readLabelViewport(page);
  expect(afterRelease.minX).toBeLessThan(before.minX);
  expect(afterRelease.minY).toBeLessThan(before.minY);
});

test('fixture labeler supports extrapolated off-image grid corners', async ({ page }) => {
  await page.goto('/labeler.html');
  await expect(page.locator('#label-columns')).toHaveValue('12');
  await expect.poll(() => countNonBlankPixels(page, '#labeler-canvas')).toBeGreaterThan(5000);

  const start = await defaultLabelCornerCanvasPoint(page, 0);
  const target = await labelerCanvasPointForNatural(page, { x: -80, y: -60 });
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(target.x, target.y, { steps: 8 });
  await page.mouse.up();

  const corner = await readLabelCornerValues(page, 0);
  expect(corner.x).toBeLessThan(0);
  expect(corner.y).toBeLessThan(0);
  await expect(page.locator('#labeler-canvas')).toHaveAttribute('data-extrapolated-grid', 'true');
  await expect(page.locator('#fixture-meta')).toContainText('extrapolated grid');
  await expect(page.locator('#labeler-status')).toContainText('Unsaved changes');
  expect(await countVirtualGridPixels(page, '#labeler-canvas')).toBeGreaterThan(1000);
});

test('fixture benchmark page renders the detector benchmark surface', async ({ page }) => {
  await page.goto('/benchmark.html');

  await expect(page.getByRole('heading', { name: 'Fixture Detector Benchmark' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Run Benchmark' })).toBeVisible();
  await expect(page.locator('#benchmark-summary')).toContainText('No benchmark run yet');
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

test('controller captures a selected live camera frame for grid detection evidence', async ({ page }) => {
  await page.addInitScript(() => {
    function drawTestMat(canvas: HTMLCanvasElement): void {
      canvas.width = 1080;
      canvas.height = 800;
      const context = canvas.getContext('2d');
      if (!context) return;
      context.fillStyle = '#f3efe5';
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.fillStyle = '#f8f4ea';
      context.strokeStyle = '#6a6659';
      context.lineWidth = 4;
      context.fillRect(120, 120, 840, 560);
      context.strokeRect(120, 120, 840, 560);
      context.strokeStyle = '#8f9a8a';
      context.lineWidth = 2;
      for (let x = 120; x <= 960; x += 70) {
        context.beginPath();
        context.moveTo(x, 120);
        context.lineTo(x, 680);
        context.stroke();
      }
      for (let y = 120; y <= 680; y += 70) {
        context.beginPath();
        context.moveTo(120, y);
        context.lineTo(960, y);
        context.stroke();
      }
    }

    const fakeCanvas = document.createElement('canvas');
    drawTestMat(fakeCanvas);
    window.setInterval(() => {
      drawTestMat(fakeCanvas);
    }, 50);
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        enumerateDevices: async () => [
          {
            deviceId: 'iphone-camera',
            groupId: 'continuity-camera',
            kind: 'videoinput',
            label: "Cam's iPhone Camera",
            toJSON: () => ({}),
          },
        ],
        getUserMedia: async () => fakeCanvas.captureStream(10),
      },
    });
  });

  await page.goto('/');
  await expect(page.locator('#camera-device')).toContainText("Cam's iPhone Camera");
  await page.locator('#camera-device').selectOption('iphone-camera');
  await page.getByRole('button', { name: 'Start Camera' }).click();
  await expect(page.getByRole('button', { name: 'Stop Camera' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Capture & Detect Frame' })).toBeEnabled();

  await page.getByRole('button', { name: 'Capture & Detect Frame' }).click();
  await expect(page.locator('#preview-mode')).toContainText('Captured camera frame');
  await expect(page.locator('#detection-status')).toContainText(/camera-frame-/);
  await expect(page.locator('#camera-evidence')).toContainText("Cam's iPhone Camera");
  await expect(page.locator('#camera-evidence')).toContainText('1080 x 800');

  const state = await page.evaluate(() => {
    const raw = window.localStorage.getItem('rpg-map-projector:story-001-calibration');
    return raw ? JSON.parse(raw) : null;
  });

  expect(state?.detectedGrid?.sourceName).toMatch(/^camera-frame-/);
  expect(state?.detectedGrid?.sourceUrl).toMatch(/^data:image\/jpeg/);
  expect(state?.evidence?.camera?.deviceLabel).toBe("Cam's iPhone Camera");
  expect(state?.evidence?.camera?.streamWidth).toBe(1080);
  expect(state?.evidence?.camera?.streamHeight).toBe(800);
  expect(state?.evidence?.camera?.capturedFrameName).toMatch(/^camera-frame-/);
});

test('controller exposes configured network cameras in the selector and captures one as evidence', async ({ page }) => {
  await page.route('**/__network-cameras', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        cameras: [
          {
            id: 'esp32s3-test',
            label: 'ESP32-S3 Wi-Fi Camera',
            baseUrl: 'http://esp32s3.test',
          },
        ],
      }),
    });
  });
  await page.route('**/__network-camera-capture**', async (route) => {
    await route.fulfill({
      contentType: 'image/svg+xml',
      body: `
        <svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480">
          <rect width="640" height="480" fill="#d8d1c3"/>
          <rect x="80" y="90" width="480" height="280" fill="#6f7f84"/>
          <rect x="120" y="150" width="170" height="120" fill="#9e5a3f"/>
          <rect x="340" y="130" width="150" height="190" fill="#334c66"/>
        </svg>
      `,
    });
  });

  await page.goto('/');
  await expect(page.locator('#camera-device')).toContainText('ESP32-S3 Wi-Fi Camera');
  await page.locator('#camera-device').selectOption('network:esp32s3-test');
  await page.getByRole('button', { name: 'Start Camera' }).click();
  await expect(page.getByRole('button', { name: 'Stop Camera' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Capture & Detect Frame' })).toBeEnabled();

  await page.getByRole('button', { name: 'Capture & Detect Frame' }).click();
  await expect(page.locator('#preview-mode')).toContainText('Captured camera frame');
  await expect(page.locator('#camera-evidence')).toContainText('ESP32-S3 Wi-Fi Camera');

  const state = await page.evaluate(() => {
    const raw = window.localStorage.getItem('rpg-map-projector:story-001-calibration');
    return raw ? JSON.parse(raw) : null;
  });

  expect(state?.evidence?.camera?.deviceLabel).toBe('ESP32-S3 Wi-Fi Camera');
  expect(state?.evidence?.camera?.streamWidth).toBe(640);
  expect(state?.evidence?.camera?.streamHeight).toBe(480);
  expect(state?.evidence?.camera?.capturedFrameName).toMatch(/^camera-frame-/);
});

test('controller blanks projector for clean mat camera capture then restores alignment grid', async ({ page }) => {
  await page.addInitScript(() => {
    function drawTestMat(canvas: HTMLCanvasElement): void {
      canvas.width = 1080;
      canvas.height = 800;
      const context = canvas.getContext('2d');
      if (!context) return;
      context.fillStyle = '#f3efe5';
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.fillStyle = '#f8f4ea';
      context.strokeStyle = '#6a6659';
      context.lineWidth = 4;
      context.fillRect(120, 120, 840, 560);
      context.strokeRect(120, 120, 840, 560);
      context.strokeStyle = '#8f9a8a';
      context.lineWidth = 2;
      for (let x = 120; x <= 960; x += 70) {
        context.beginPath();
        context.moveTo(x, 120);
        context.lineTo(x, 680);
        context.stroke();
      }
      for (let y = 120; y <= 680; y += 70) {
        context.beginPath();
        context.moveTo(120, y);
        context.lineTo(960, y);
        context.stroke();
      }
    }

    const fakeCanvas = document.createElement('canvas');
    drawTestMat(fakeCanvas);
    window.setInterval(() => {
      drawTestMat(fakeCanvas);
    }, 50);
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        enumerateDevices: async () => [
          {
            deviceId: 'iphone-camera',
            groupId: 'continuity-camera',
            kind: 'videoinput',
            label: "Cam's iPhone Camera",
            toJSON: () => ({}),
          },
        ],
        getUserMedia: async () => fakeCanvas.captureStream(10),
      },
    });
  });

  await page.goto('/');
  await page.locator('#camera-device').selectOption('iphone-camera');
  await page.getByRole('button', { name: 'Start Camera' }).click();
  await expect(page.getByRole('button', { name: 'Blank & Capture Mat' })).toBeEnabled();

  await page.getByRole('button', { name: 'Blank & Capture Mat' }).click();
  await expect(page.locator('#preview-mode')).toContainText('Captured camera frame');
  await expect(page.locator('#detection-status')).toContainText(/clean-mat-frame-/);

  const state = await page.evaluate(() => {
    const raw = window.localStorage.getItem('rpg-map-projector:story-001-calibration');
    return raw ? JSON.parse(raw) : null;
  });

  expect(state?.projectorMode).toBe('alignment');
  expect(state?.detectedGrid?.sourceName).toMatch(/^clean-mat-frame-/);
  expect(state?.evidence?.camera?.capturedFrameName).toMatch(/^clean-mat-frame-/);
});

test('controller keeps failed live camera captures available for manual grid seeding', async ({ page }) => {
  await page.addInitScript(() => {
    const fakeCanvas = document.createElement('canvas');
    fakeCanvas.width = 1280;
    fakeCanvas.height = 720;
    function drawBlankFrame(): void {
      const context = fakeCanvas.getContext('2d');
      if (!context) return;
      context.fillStyle = '#151714';
      context.fillRect(0, 0, fakeCanvas.width, fakeCanvas.height);
      context.fillStyle = '#c7baa1';
      context.fillRect(0, fakeCanvas.height * 0.55, fakeCanvas.width, fakeCanvas.height * 0.45);
    }
    drawBlankFrame();
    window.setInterval(drawBlankFrame, 50);
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {
        enumerateDevices: async () => [
          {
            deviceId: 'iphone-camera',
            groupId: 'continuity-camera',
            kind: 'videoinput',
            label: "Cam's iPhone Camera",
            toJSON: () => ({}),
          },
        ],
        getUserMedia: async () => fakeCanvas.captureStream(10),
      },
    });
  });

  await page.goto('/');
  await page.locator('#camera-device').selectOption('iphone-camera');
  await page.getByRole('button', { name: 'Start Camera' }).click();
  await expect(page.getByRole('button', { name: 'Capture & Detect Frame' })).toBeEnabled();
  await page.getByRole('button', { name: 'Capture & Detect Frame' }).click();

  await expect(page.locator('#preview-mode')).toContainText('Captured camera frame');
  await expect(page.locator('#detection-status')).toContainText('Detection failed');
  await expect(page.getByRole('button', { name: 'Manual Seed Handles' })).toBeEnabled();

  await page.getByRole('button', { name: 'Manual Seed Handles' }).click();
  await expect(page.locator('#detection-status')).toContainText('Manual seed handles placed');
  await expect(page.locator('#alignment-status')).toContainText('Manual correction required');

  const state = await page.evaluate(() => {
    const raw = window.localStorage.getItem('rpg-map-projector:story-001-calibration');
    return raw ? JSON.parse(raw) : null;
  });

  expect(state?.detectedGrid?.sourceName).toMatch(/^camera-frame-/);
  expect(state?.detectedGrid?.confidence).toBe(0.2);
  expect(state?.detectedGrid?.columns).toBe(12);
  expect(state?.detectedGrid?.rows).toBe(8);
  expect(state?.detectedGrid?.corners?.[0].y).toBeGreaterThan(350);
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

async function countBrightPixels(
  page: import('@playwright/test').Page,
  selector: string,
  threshold: number,
): Promise<number> {
  return page.locator(selector).evaluate((canvas: HTMLCanvasElement, minimumLuma) => {
    const context = canvas.getContext('2d');
    if (!context) return 0;
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let count = 0;
    for (let index = 0; index < data.length; index += 4) {
      const luma = (data[index] * 0.2126) + (data[index + 1] * 0.7152) + (data[index + 2] * 0.0722);
      if (luma >= minimumLuma) count += 1;
    }
    return count;
  }, threshold);
}

async function defaultLabelCornerCanvasPoint(
  page: import('@playwright/test').Page,
  cornerIndex: number,
): Promise<{ x: number; y: number }> {
  return page.locator('#labeler-canvas').evaluate((canvas: HTMLCanvasElement, index) => {
    const rect = canvas.getBoundingClientRect();
    const fit = JSON.parse(canvas.dataset.labelViewport ?? '{}') as {
      x: number;
      y: number;
      minX: number;
      minY: number;
      scale: number;
    };
    const row = document.querySelectorAll('.labeler-corner-row')[index as number];
    const values = Array.from(row?.querySelectorAll('span') ?? []).map((span) => span.textContent ?? '');
    const corner = {
      x: Number(values[0]?.replace(/[^0-9.-]/g, '')) || 0,
      y: Number(values[1]?.replace(/[^0-9.-]/g, '')) || 0,
    };
    return {
      x: rect.left + fit.x + (corner.x - fit.minX) * fit.scale,
      y: rect.top + fit.y + (corner.y - fit.minY) * fit.scale,
    };
  }, cornerIndex);
}

async function labelerCanvasPointForNatural(
  page: import('@playwright/test').Page,
  naturalPoint: { x: number; y: number },
): Promise<{ x: number; y: number }> {
  return page.locator('#labeler-canvas').evaluate((canvas: HTMLCanvasElement, point) => {
    const rect = canvas.getBoundingClientRect();
    const fit = JSON.parse(canvas.dataset.labelViewport ?? '{}') as {
      x: number;
      y: number;
      minX: number;
      minY: number;
      scale: number;
    };
    return {
      x: rect.left + fit.x + (point.x - fit.minX) * fit.scale,
      y: rect.top + fit.y + (point.y - fit.minY) * fit.scale,
    };
  }, naturalPoint);
}

async function readLabelerZoomScale(page: import('@playwright/test').Page): Promise<number> {
  return page.locator('#labeler-canvas').evaluate((canvas: HTMLCanvasElement) => (
    Number(canvas.dataset.zoomScale) || 0
  ));
}

async function readLabelViewport(page: import('@playwright/test').Page): Promise<{
  minX: number;
  minY: number;
}> {
  return page.locator('#labeler-canvas').evaluate((canvas: HTMLCanvasElement) => {
    const fit = JSON.parse(canvas.dataset.labelViewport ?? '{}') as {
      minX?: number;
      minY?: number;
    };
    return {
      minX: Number(fit.minX) || 0,
      minY: Number(fit.minY) || 0,
    };
  });
}

async function readLabelCornerValues(
  page: import('@playwright/test').Page,
  cornerIndex: number,
): Promise<{ x: number; y: number }> {
  return page.locator('#corner-table').evaluate((table: HTMLDivElement, index) => {
    const row = table.querySelectorAll('.labeler-corner-row')[index as number];
    const values = Array.from(row?.querySelectorAll('span') ?? []).map((span) => span.textContent ?? '');
    return {
      x: Number(values[0]?.replace(/[^0-9.-]/g, '')),
      y: Number(values[1]?.replace(/[^0-9.-]/g, '')),
    };
  }, cornerIndex);
}

async function countReticlePixels(page: import('@playwright/test').Page, selector: string): Promise<number> {
  return page.locator(selector).evaluate((canvas: HTMLCanvasElement) => {
    const context = canvas.getContext('2d');
    if (!context) return 0;
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let count = 0;
    for (let index = 0; index < data.length; index += 4) {
      const red = data[index];
      const green = data[index + 1];
      const blue = data[index + 2];
      if (red > 200 && green > 70 && green < 150 && blue < 100) count += 1;
    }
    return count;
  });
}

async function countVirtualGridPixels(page: import('@playwright/test').Page, selector: string): Promise<number> {
  return page.locator(selector).evaluate((canvas: HTMLCanvasElement) => {
    const context = canvas.getContext('2d');
    if (!context) return 0;
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let count = 0;
    for (let index = 0; index < data.length; index += 4) {
      const red = data[index];
      const green = data[index + 1];
      const blue = data[index + 2];
      if (red < 50 && green > 90 && blue > 55 && blue < 150) count += 1;
    }
    return count;
  });
}

function meanCornerError(actual: Array<{ x: number; y: number }>, expected: Array<{ x: number; y: number }>): number {
  return actual.reduce((sum, point, index) => (
    sum + Math.hypot(point.x - expected[index].x, point.y - expected[index].y)
  ), 0) / expected.length;
}
