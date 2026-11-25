import { expect, test } from '@playwright/test';
import { PASSWORD, uniqueEmail } from './helpers';

test('registers and signs in through the browser using real APIs', async ({ page }) => {
  const email = uniqueEmail('playwright-auth');
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Sign in to the repository' })).toBeVisible();
  await page.getByRole('button', { name: /Register as a contributor/ }).click();
  await expect(page.getByRole('heading', { name: 'Create a contributor account' })).toBeVisible();

  await page.locator('#register-name').fill('Playwright Browser Tester');
  await page.locator('#register-email').fill(email);
  await page.locator('#register-org').fill('Fictional Test Organisation');
  await page.locator('#register-title').fill('Researcher');
  await page.locator('#register-password').fill(PASSWORD);
  await page.locator('#register-confirm').fill(PASSWORD);
  await page.getByRole('button', { name: 'Create account' }).click();

  await expect
    .poll(async () => page.evaluate(() => window.localStorage.getItem('meddatahub.access_token')))
    .toBeTruthy();
  await expect(page.getByRole('link', { name: 'Research Reports' })).toBeVisible();
});
