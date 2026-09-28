import { expect, test } from '@playwright/test'
import { authenticate, mockHermesApi, TEST_ACCESS_KEY } from './fixtures'

const MAIN_ROUTES = [
  { path: '/#/tahp/dashboard', heading: /AI 适配流水线|模型选择/ },
  { path: '/#/tahp/adapt-debug', heading: /单项适配/ },
  { path: '/#/tahp/bug-analysis', heading: /Bug 分析/ },
  { path: '/#/tahp/self-check', heading: /质量验测/ },
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
    // 「智能诊断」位于顶栏「公共能力」下拉中，而非独立 Tab
    await page.locator('.ck-tab', { hasText: '公共能力' }).click()
    await page.locator('.n-dropdown-menu').getByText('智能诊断', { exact: true }).click()
    await expect(page).toHaveURL(/#\/tahp\/bug-analysis/)
    // 智能诊断页无页头，空态标题为「开始你的第一条 Bug 分析」
    await expect(page.getByRole('heading', { name: /Bug 分析/ })).toBeVisible()
  })
})
