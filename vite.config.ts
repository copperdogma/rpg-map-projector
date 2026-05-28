import { access, mkdir, readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, type Plugin } from 'vite';

const root = dirname(fileURLToPath(import.meta.url));
const labelFilePath = resolve(root, 'input/map-grid-labels.json');

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
      },
    },
  },
});

function fixtureLabelPlugin(): Plugin {
  return {
    name: 'rpg-map-projector-fixture-labels',
    configureServer(server) {
      server.middlewares.use(async (request, response, next) => {
        if (!request.url?.startsWith('/__fixture-labels')) {
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

async function readLabelPayload(): Promise<unknown> {
  try {
    await access(labelFilePath);
    return JSON.parse(await readFile(labelFilePath, 'utf8'));
  } catch {
    return { version: 1, updatedAt: null, labels: [] };
  }
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
