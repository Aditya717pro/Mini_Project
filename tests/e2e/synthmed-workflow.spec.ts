import { expect, test, type Page } from '@playwright/test';
import { API_BASE, authHeaders, loginViaApi } from './helpers';

const DIRECT_CSV = Buffer.from(
  'Age,Gender,Outcome\n34,Female,stable\n41,Male,review\n38,Female,stable\n',
  'utf8',
);

function idsFromAcknowledgementUrl(url: string) {
  const parsed = new URL(url);
  return {
    datasetId: parsed.searchParams.get('datasetId') || '',
    jobId: parsed.searchParams.get('jobId') || '',
  };
}

async function fillUploadMetadata(page: Page, title: string) {
  await page.locator('#title').fill(title);
  await page.locator('#description').fill('Fictional synthetic cohort used only for browser verification.');
  await page.locator('#ageRange').fill('18-90 years');
  await page.locator('#geography').fill('England');
  await page.getByRole('button', { name: 'Phenotype clustering' }).click();
  await page.locator('input[type="checkbox"]').last().check();
}

test('homepage exposes exactly two governed entry points and keeps analytics', async ({ page }) => {
  await loginViaApi(page, 'contributor@meddatahub.local');

  await expect(page.getByTestId('home-primary-options').locator('a')).toHaveCount(2);
  await expect(page.getByTestId('home-synthetic-card')).toContainText('SYNTHETIC');
  await expect(page.getByTestId('home-synthetic-card')).toContainText(
    'Generate synthetic medical datasets from new datasets or existing repository datasets.',
  );
  await expect(page.getByTestId('home-upload-card')).toContainText('UPLOAD TO REPOSITORY');
  await expect(page.getByTestId('home-upload-card')).toContainText(
    'Upload, extract, transform, validate and store datasets in My Repository.',
  );
  await expect(page.getByTestId('home-generate-card')).toHaveCount(0);
  await expect(page.getByTestId('home-repository-card')).toHaveCount(0);
  await expect(page.getByTestId('home-generated-card')).toHaveCount(0);
  await expect(page.getByText('Available Datasets')).toBeVisible();
  await expect(page.getByText('Active ETL Pipelines')).toBeVisible();
});

test('direct file upload creates a real shared ETL job', async ({ page }) => {
  test.setTimeout(180_000);
  const { token } = await loginViaApi(page, 'contributor@meddatahub.local');

  await page.getByTestId('home-upload-card').click();
  await expect(page).toHaveURL(/\/upload$/);
  await page.locator('input[type="file"]').setInputFiles({
    name: 'playwright-direct.csv',
    mimeType: 'text/csv',
    buffer: DIRECT_CSV,
  });
  await expect(page.locator('.file-card')).toContainText('3 rows');
  await fillUploadMetadata(page, 'Fictional direct upload cohort');
  await page.getByRole('button', { name: 'Upload to Repository' }).last().click();

  await expect(page.getByTestId('auto-etl-panel')).toBeVisible();
  await expect(page.getByTestId('auto-etl-step-uploading')).toContainText('Completed');
  await page.waitForURL(/\/(\?|&)uploaded=1/, { timeout: 120_000 });
  await expect(page.getByTestId('home-upload-acknowledgement')).toBeVisible();
  await expect(page.getByTestId('home-upload-acknowledgement')).toContainText('Dataset uploaded successfully');

  const { datasetId, jobId } = idsFromAcknowledgementUrl(page.url());
  expect(datasetId).toBeTruthy();
  expect(jobId).toBeTruthy();

  const jobResponse = await page.request.get(`${API_BASE}/etl/jobs/${jobId}`, { headers: authHeaders(token) });
  expect(jobResponse.status(), await jobResponse.text()).toBe(200);
  expect((await jobResponse.json()).status).toBe('Completed');

  const detailResponse = await page.request.get(`${API_BASE}/datasets/${datasetId}`, { headers: authHeaders(token) });
  expect(detailResponse.status(), await detailResponse.text()).toBe(200);
  expect((await detailResponse.json()).origin).toBe('Original');

  await page.goto('/repository');
  await expect(page.getByTestId(`repo-generate-${datasetId}`)).toBeVisible();
  await page.getByTestId(`repo-generate-${datasetId}`).click();
  await expect(page).toHaveURL(new RegExp(`/synthmed/generate\\?datasetId=${datasetId}(?!.*versionId=)`));
});

test('repository source generation and generated upload share the ETL path', async ({ page }) => {
  test.setTimeout(300_000);
  const { token } = await loginViaApi(page, 'contributor@meddatahub.local');

  await page.getByTestId('home-synthetic-card').click();
  await expect(page).toHaveURL(/\/synthmed$/);
  await expect(page.getByTestId('synthmed-source-methods')).toBeVisible();
  await expect(page.getByTestId('synthmed-source-repository')).toBeVisible();
  await expect(page.getByTestId('synthmed-source-upload')).toBeVisible();
  await expect(page.getByTestId('synthmed-stepper')).toBeVisible();

  const sourceLink = page.locator('[data-testid^="select-dataset-"]').first();
  await expect(sourceLink).toBeVisible({ timeout: 20_000 });
  const sourceTestId = await sourceLink.getAttribute('data-testid');
  const sourceId = sourceTestId?.replace('select-dataset-', '') ?? '';
  expect(sourceId).toBeTruthy();
  await sourceLink.click();

  await expect(page).toHaveURL(new RegExp(`/synthmed/generate\\?datasetId=${sourceId}(?!.*versionId=)`));
  await expect(page.getByTestId('generate-source-summary')).toBeVisible();
  await expect(page.getByText('Ready to prepare')).toBeVisible();
  await page.locator('#synthmed-generation-epochs').fill('1');
  await page.locator('#synthmed-generation-records').fill('1');
  await page.getByRole('button', { name: /Start CTGAN generation/ }).click();

  await page.waitForURL(/\/synthmed\/generated\/[0-9a-f-]+$/, { timeout: 240_000 });
  const generatedId = page.url().split('/').pop() ?? '';
  expect(generatedId).toBeTruthy();
  await expect(page.getByTestId('generation-success')).toBeVisible();
  await expect(page.getByTestId('generated-primary-actions').locator('button')).toHaveCount(3);
  await expect(page.getByTestId('generated-preview-action')).toContainText('PREVIEW');
  await expect(page.getByTestId('generated-download-action')).toContainText('DOWNLOAD');
  await expect(page.getByTestId('generated-upload-action')).toContainText('UPLOAD');
  await expect(page.getByTestId('generation-success')).toContainText('Not registered');

  await page.getByRole('link', { name: 'All generated datasets' }).click();
  await expect(page).toHaveURL(/\/synthmed\/generated$/);
  const generatedRow = page.getByTestId(`generated-row-${generatedId}`);
  await expect(generatedRow).toBeVisible();
  await expect(generatedRow).toContainText('CTGAN');
  await expect(generatedRow).toContainText('Not registered');
  await expect(page.getByTestId(`generated-row-upload-${generatedId}`)).toBeVisible();

  await page.getByTestId(`generated-row-upload-${generatedId}`).click();
  await expect(page).toHaveURL(new RegExp(`/upload\\?generatedId=${generatedId}`));
  await expect(page.getByTestId('upload-generated-banner')).toBeVisible();
  await expect(page.getByTestId('upload-generated-banner')).toContainText(generatedId);
  await expect(page.locator('input[type="file"]')).toHaveCount(0);
  await fillUploadMetadata(page, 'Fictional generated upload cohort');
  await page.getByRole('button', { name: 'Upload to Repository' }).last().click();

  await expect(page.getByTestId('auto-etl-panel')).toBeVisible();
  await expect(page.getByTestId('auto-etl-step-uploading')).toContainText('Completed');
  await page.waitForURL(/\/(\?|&)uploaded=1/, { timeout: 120_000 });
  await expect(page.getByTestId('home-upload-acknowledgement')).toBeVisible();

  const { datasetId: repositoryDatasetId } = idsFromAcknowledgementUrl(page.url());
  expect(repositoryDatasetId).toBeTruthy();

  const detailResponse = await page.request.get(`${API_BASE}/datasets/${repositoryDatasetId}`, {
    headers: authHeaders(token),
  });
  expect(detailResponse.status(), await detailResponse.text()).toBe(200);
  const detail = (await detailResponse.json()) as {
    origin: string;
    sourceGeneratedDatasetId: string | null;
    generationModel: string | null;
    provenance: { ingestionPath?: string; storage?: string };
  };
  expect(detail.origin).toBe('Synthetic');
  expect(detail.sourceGeneratedDatasetId).toBe(generatedId);
  expect(detail.generationModel).toBe('CTGAN');
  expect(detail.provenance.ingestionPath).toBe('shared-etl');
  expect(detail.provenance.storage).toBe('independent-copy');

  const generatedResponse = await page.request.get(`${API_BASE}/synthmed/generated`, {
    headers: authHeaders(token),
  });
  expect(generatedResponse.status(), await generatedResponse.text()).toBe(200);
  const generatedRows = (await generatedResponse.json()) as Array<{
    id: string;
    repositoryRegistrationStatus: string;
    repositoryDatasetId: string | null;
  }>;
  const generatedApiRow = generatedRows.find((row) => row.id === generatedId);
  expect(generatedApiRow).toBeTruthy();
  expect(generatedApiRow?.repositoryRegistrationStatus).toBe('In Repository ETL');
  expect(generatedApiRow?.repositoryDatasetId).toBe(repositoryDatasetId);

  await page.goto(`/synthmed/generated/${generatedId}`);
  await expect(page.getByTestId('generated-upload-action')).toBeDisabled();
  await expect(page.getByTestId('generated-registered-action')).toBeVisible();

  const versionsResponse = await page.request.get(`${API_BASE}/datasets/${repositoryDatasetId}/versions`, {
    headers: authHeaders(token),
  });
  expect(versionsResponse.status(), await versionsResponse.text()).toBe(200);
  const versions = (await versionsResponse.json()) as { versions?: Array<{ id: string }> };
  const versionId = versions.versions?.[0]?.id ?? '';
  expect(versionId).toBeTruthy();

  await page.goto(`/datasets/${repositoryDatasetId}/versions/${versionId}`);
  await expect(page.getByTestId(`version-generate-${versionId}`)).toBeVisible();
  await page.getByTestId(`version-generate-${versionId}`).click();
  await expect(page).toHaveURL(
    new RegExp(`/synthmed/generate\\?datasetId=${repositoryDatasetId}&versionId=${versionId}`),
  );
  await expect(page.getByTestId('generate-source-summary')).toBeVisible();
});
