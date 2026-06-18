import { expect, test } from '@playwright/test'
import { authenticate, mockHermesApi, TEST_ACCESS_KEY } from './fixtures'

const MAIN_ROUTES = [
  { path: '/#/tahp/dashboard', heading: /AI 适配调试|模型选择/ },
  { path: '/#/tahp/adapt-debug', heading: /AI 适配调试/ },
  { path: '/#/tahp/bug-analysis', heading: /智能诊断/ },
  { path: '/#/tahp/self-check', heading: /AI 自检/ },
  { path: '/#/tahp/reports', heading: /任务报告|报告/ },
  { path: '/#/tahp/knowledge', heading: /知识库/ },
  { path: '/#/hermes/skills', heading: /Skills/ },
  { path: '/#/hermes/chat', heading: /AI 对话|对话/ },
]

test.describe('V26 nav smoke', () => {
  test.beforeEach(async ({ page }) => {
    await authenticate(page, TEST_ACCESS_KEY, 'research')
    await mockHermesApi(page)
  })

  for (const route of MAIN_ROUTES) {
    test(`loads ${route.path}`, async ({ page }) => {
      const errors: string[] = []
      page.on('pageerror', (err) => errors.push(err.message))

      await page.goto(route.path)
      await expect(page.locator('.ck-shell')).toBeVisible()
      await expect(page.getByRole('heading', { name: route.heading }).first()).toBeVisible({ timeout: 15000 })
      expect(errors).toEqual([])
    })
  }

  test('navigates via top tabs', async ({ page }) => {
    await page.goto('/#/tahp/dashboard')
    await page.locator('.ck-tab', { hasText: '智能诊断' }).click()
    await expect(page).toHaveURL(/#\/tahp\/bug-analysis/)
    await expect(page.getByRole('heading', { name: /智能诊断/ })).toBeVisible()
  })
})
