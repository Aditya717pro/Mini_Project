import { expect, test } from '@playwright/test';
import { API_BASE, authHeaders, registerViaApi, sha256, uploadFictionalCsv } from './helpers';

test('generates and downloads a dataset profile PDF from a persisted source', async ({ page }) => {
  const { token } = await registerViaApi(page, 'playwright-report');
  const sourceId = await uploadFictionalCsv(page, token);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'Research Reports' })).toBeVisible();

  await page.getByRole('combobox', { name: 'Core dataset' }).selectOption(sourceId);
  await page.getByRole('button', { name: 'Generate Dataset Profile PDF' }).click();

  await page.waitForURL(/\/reports\/[^/]+$/);
  const reportId = page.url().split('/').pop() ?? '';
  expect(reportId).toBeTruthy();
  await expect(page.getByText('Completed', { exact: true }).first()).toBeVisible();

  const detailResponse = await page.request.get(`${API_BASE}/reports/${reportId}`, {
    headers: authHeaders(token),
  });
  expect(detailResponse.status(), await detailResponse.text()).toBe(200);
  const detail = (await detailResponse.json()) as { fileChecksum: string; status: string };
  expect(detail.status).toBe('Completed');

  const pdfResponse = await page.request.get(`${API_BASE}/reports/${reportId}/download`, {
    headers: authHeaders(token),
  });
  expect(pdfResponse.status(), await pdfResponse.text()).toBe(200);
  const pdf = Buffer.from(await pdfResponse.body());
  expect(pdf.subarray(0, 5).toString()).toBe('%PDF-');
  expect(pdf.includes(Buffer.from('%%EOF'))).toBe(true);
  expect(sha256(pdf)).toBe(detail.fileChecksum);
  expect(pdf.includes(Buffer.from('P001'))).toBe(false);
  expect(pdf.includes(Buffer.from('patient_id'))).toBe(false);

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('button', { name: 'Download PDF' }).click(),
  ]);
  expect(download.suggestedFilename()).toBe(`${reportId}.pdf`);
});
