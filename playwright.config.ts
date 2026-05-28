import { defineConfig, devices } from '@playwright/test';

const uiPort = Number.parseInt(process.env.RPG_MAP_PROJECTOR_UI_PORT ?? '5178', 10);
const baseURL = `http://127.0.0.1:${uiPort}`;

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  expect: { timeout: 5_000 },
  use: {
    baseURL,
    trace: 'on-first-retry',
  },
  webServer: {
    command: `npm run dev:vite -- --port ${uiPort} --strictPort`,
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
