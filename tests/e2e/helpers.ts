import { expect, type Page } from '@playwright/test';
import { createHash } from 'node:crypto';

export const API_BASE = process.env.E2E_API_BASE_URL ?? 'http://127.0.0.1:5173/api/v1';
export const PASSWORD = 'Playwright!42';

export const uniqueEmail = (prefix: string) =>
  `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}@example.test`;

export const authHeaders = (token: string) => ({ Authorization: `Bearer ${token}` });

export const sha256 = (content: Buffer | Uint8Array) => createHash('sha256').update(content).digest('hex');

export async function loginViaApi(page: Page, email: string, password = PASSWORD) {
  const login = await page.request.post(`${API_BASE}/auth/login`, {
    data: { email, password },
  });
  if (!login.ok()) throw new Error(await login.text());
  const token = (await login.json()).access_token as string;
  expect(token).toBeTruthy();

  await page.addInitScript(({ accessToken }) => {
    window.localStorage.setItem('meddatahub.access_token', accessToken);
  }, { accessToken: token });
  await page.goto('/');
  await expect(page.getByTestId('home-hero')).toBeVisible();
  return { email, token };
}

export async function registerViaApi(page: Page, prefix: string) {
  const email = uniqueEmail(prefix);
  const register = await page.request.post(`${API_BASE}/auth/register`, {
    data: {
      email,
      password: PASSWORD,
      full_name: 'Playwright Researcher',
      organisation: 'Fictional Test Organisation',
      title: 'Researcher',
    },
  });
  expect(register.status(), await register.text()).toBe(201);

  const login = await page.request.post(`${API_BASE}/auth/login`, {
    data: { email, password: PASSWORD },
  });
  if (!login.ok()) throw new Error(await login.text());
  const token = (await login.json()).access_token as string;
  expect(token).toBeTruthy();

  await page.addInitScript(({ accessToken }) => {
    window.localStorage.setItem('meddatahub.access_token', accessToken);
  }, { accessToken: token });
  await page.goto('/reports');
  await expect(page.getByRole('heading', { name: 'Research Reports' })).toBeVisible();
  return { email, token };
}

export async function findEtlJob(page: Page, token: string, datasetId: string): Promise<string> {
  const response = await page.request.get(`${API_BASE}/etl/jobs`, { headers: authHeaders(token) });
  expect(response.status(), await response.text()).toBe(200);
  const jobs = (await response.json()) as Array<{ id: string; datasetId: string }>;
  const job = jobs.find((item) => item.datasetId === datasetId);
  expect(job, `ETL job for dataset ${datasetId}`).toBeTruthy();
  return job!.id;
}

export async function completeEtlJob(page: Page, token: string, jobId: string) {
  const profileResponse = await page.request.post(`${API_BASE}/etl/jobs/${jobId}/profile`, {
    headers: authHeaders(token),
  });
  expect(profileResponse.status(), await profileResponse.text()).toBe(200);
  const profile = (await profileResponse.json()) as {
    mappings: Array<{ source: string; target?: string | null; proposedTarget?: string | null }>;
  };
  const decisions = profile.mappings.map((item) => {
    const target = item.target || item.proposedTarget || '';
    return {
      source: item.source,
      decision: target ? 'Approved' : 'Unmapped',
      target,
      note: 'Fictional browser verification decision',
    };
  });
  const mappingsResponse = await page.request.post(`${API_BASE}/etl/jobs/${jobId}/mappings`, {
    headers: authHeaders(token),
    data: decisions,
  });
  expect(mappingsResponse.status(), await mappingsResponse.text()).toBe(200);
  const approveResponse = await page.request.post(`${API_BASE}/etl/jobs/${jobId}/approve`, {
    headers: authHeaders(token),
    data: {},
  });
  expect(approveResponse.status(), await approveResponse.text()).toBe(200);
  const runResponse = await page.request.post(`${API_BASE}/etl/jobs/${jobId}/run`, {
    headers: authHeaders(token),
    data: { task: 'Synthetic classification' },
  });
  expect(runResponse.status(), await runResponse.text()).toBe(200);
}

export async function uploadFictionalCsv(page: Page, token: string) {
  const rows = Array.from({ length: 12 }, (_, index) =>
    `P${String(index + 1).padStart(3, '0')},${30 + index},${index % 2 === 0 ? 'stable' : 'review'}`,
  ).join('\n');
  const content = Buffer.from(`patient_id,Age,Outcome\n${rows}\n`, 'utf8');
  const response = await page.request.post(`${API_BASE}/synthmed/upload`, {
    headers: authHeaders(token),
    multipart: {
      dataset_name: 'Playwright fictional cohort',
      description: 'Fictional data for browser verification',
      file: {
        name: 'playwright-cohort.csv',
        mimeType: 'text/csv',
        buffer: content,
      },
    },
  });
  expect(response.status(), await response.text()).toBe(201);
  const body = (await response.json()) as { dataset: { id: string } };
  expect(body.dataset.id).toBeTruthy();
  return body.dataset.id;
}
