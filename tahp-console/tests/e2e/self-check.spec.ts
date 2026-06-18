import { expect, test } from '@playwright/test'
import { authenticate, mockHermesApi, TEST_ACCESS_KEY } from './fixtures'

test('self-check page renders health ring', async ({ page }) => {
  await authenticate(page, TEST_ACCESS_KEY, 'research')
  await mockHermesApi(page)

  await page.route('**/api/tahp/self-check', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          score: 96,
          level: '良好',
          updated: '2026/6/18 10:20',
          pass: 10,
          warn: 2,
          fail: 0,
          total: 12,
          categories: [
            {
              title: '运行环境',
              icon: 'server',
              items: [{ name: 'Node.js', detail: 'v20', state: 'ok', label: '正常' }],
            },
          ],
          history: [{ time: '2026/6/18 10:20', score: 96, note: '2 项告警' }],
        },
      }),
    })
  })

  await page.goto('/#/tahp/self-check')
  await expect(page.getByRole('heading', { name: 'AI 自检' })).toBeVisible()
  await expect(page.locator('.ring-val b')).toHaveText('96')
  await expect(page.getByRole('heading', { name: '运行环境' })).toBeVisible()
})
