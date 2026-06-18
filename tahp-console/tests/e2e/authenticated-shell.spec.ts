import { expect, test } from '@playwright/test'
import { authenticate, mockHermesApi, TEST_ACCESS_KEY } from './fixtures'

test('renders V26 shell and navigates to models via system menu', async ({ page }) => {
  await authenticate(page, TEST_ACCESS_KEY, 'research')
  await mockHermesApi(page)

  await page.goto('/#/tahp/dashboard')

  await expect(page.locator('.ck-shell')).toBeVisible()
  await expect(page.locator('.ck-brand')).toContainText('EasyAdapter')

  await page.locator('.ck-tab', { hasText: '报告' }).click()
  await expect(page).toHaveURL(/#\/tahp\/reports/)

  await page.locator('.ck-sys-btn').first().click()
  await page.getByText('模型管理', { exact: true }).click()
  await expect(page).toHaveURL(/#\/hermes\/models/)
  await expect(page.getByRole('heading', { name: /模型|Models/i }).first()).toBeVisible()
})
