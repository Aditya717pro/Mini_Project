import { defineConfig, devices } from '@playwright/test';
import { mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const rootDir = fileURLToPath(new URL('.', import.meta.url));
const backendDir = join(rootDir, 'backend');
const isWindows = process.platform === 'win32';
const python = join(backendDir, '.venv', isWindows ? 'Scripts' : 'bin', isWindows ? 'python.exe' : 'python');
const quote = (value: string) => JSON.stringify(value);
const apiPort = process.env.E2E_API_PORT ?? '8000';
const webPort = process.env.E2E_WEB_PORT ?? '5173';
const runDir = join(tmpdir(), 'meddatahub-playwright', `run-${Date.now()}-${process.pid}`);
const databasePath = join(runDir, 'meddatahub.db').replace(/\\/g, '/');
const rawDir = join(runDir, 'storage', 'raw');
const processedDir = join(runDir, 'storage', 'processed');
const synthmedDir = join(runDir, 'storage', 'synthmed');

mkdirSync(rawDir, { recursive: true });
mkdirSync(processedDir, { recursive: true });
mkdirSync(synthmedDir, { recursive: true });

const backendEnv: Record<string, string> = Object.fromEntries(
  Object.entries(process.env)
    .filter((entry): entry is [string, string] => entry[1] !== undefined)
    .map(([key, value]) => [key, value]),
);
Object.assign(backendEnv, {
  DATABASE_URL: `sqlite:///${databasePath}`,
  RAW_STORAGE_DIR: rawDir.replace(/\\/g, '/'),
  PROCESSED_STORAGE_DIR: processedDir.replace(/\\/g, '/'),
  SYNTHMED_STORAGE_DIR: synthmedDir.replace(/\\/g, '/'),
  ENVIRONMENT: 'test',
  SYNTHMED_GENERATION_INLINE: 'true',
  SYNTHMED_STALE_JOB_RECOVERY_ENABLED: 'false',
  CORS_ORIGINS: `http://localhost:${webPort},http://127.0.0.1:${webPort}`,
  SEED_ADMIN_PASSWORD: 'Playwright!42',
  SEED_CONTRIBUTOR_PASSWORD: 'Playwright!42',
  SEED_RESEARCHER_PASSWORD: 'Playwright!42',
});

export default defineConfig({
  testDir: join(rootDir, 'tests', 'e2e'),
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  reporter: [['list']],
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: [
    {
      command: [
        `${quote(python)} -m alembic upgrade head`,
        `${quote(python)} -m app.seed`,
        `${quote(python)} -m uvicorn app.main:app --host 127.0.0.1 --port ${apiPort} --no-access-log`,
      ].join(' && '),
      cwd: backendDir,
      env: backendEnv,
      url: `http://127.0.0.1:${apiPort}/docs`,
      reuseExistingServer: false,
      timeout: 180_000,
    },
    {
      command: `npm --prefix frontend run dev -- --host 127.0.0.1 --port ${webPort} --strictPort`,
      cwd: rootDir,
      url: `http://127.0.0.1:${webPort}`,
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
