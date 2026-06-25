import { expect, test } from '@playwright/test'
import { authenticate, mockHermesApi, TEST_ACCESS_KEY } from './fixtures'

function mockDeviceSelfCheckApi(page: import('@playwright/test').Page) {
  return page.route('**/api/tahp/device-self-check/**', async (route) => {
    const url = route.request().url()
    if (url.includes('/module-conditions')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: {} }),
      })
      return
    }
    if (url.includes('/devices/refresh')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: [] }),
      })
      return
    }
    if (url.endsWith('/devices') || url.includes('/devices?')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: [] }),
      })
      return
    }
    await route.continue()
  })
}

function mockTestPlanningApi(page: import('@playwright/test').Page) {
  const nodesPayload = {
    updatedAt: '2026-06-24T08:00:00.000Z',
    sourcePath: 'docs/升级项目关键信息表.xlsx',
    projects: [],
    nextNodes: [
      {
        project: 'X6885',
        node: 'STR4A',
        nodeDate: '2026/07/07',
        display: 'X6885 STR4A 2026/07/07',
      },
    ],
  }
  const schedulePayload = {
    updatedAt: '2026-06-24T08:00:00.000Z',
    rules: [{ node: 'STR4A', offsetDays: -10, testName: 'GMS测试' }],
    items: [
      {
        project: 'X6885',
        node: 'STR4A',
        nodeDate: '2026/07/07',
        triggerDate: '2026/06/27',
        testName: 'GMS测试',
        status: 'upcoming',
        display: 'X6885 STR4A 2026/06/27 GMS测试',
      },
    ],
  }

  return page.route('**/api/tahp/test-planning/**', async (route) => {
    const url = route.request().url()
    if (url.includes('/nodes/sync')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: nodesPayload }),
      })
      return
    }
    if (url.includes('/nodes')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: nodesPayload }),
      })
      return
    }
    if (url.includes('/rules')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: { version: 1, rules: schedulePayload.rules } }),
      })
      return
    }
    if (url.includes('/schedule')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: schedulePayload }),
      })
      return
    }
    await route.continue()
  })
}

test('self-check page renders device and gerrit review workspaces', async ({ page }) => {
  await authenticate(page, TEST_ACCESS_KEY, 'research')
  await mockHermesApi(page)
  await mockDeviceSelfCheckApi(page)
  await mockTestPlanningApi(page)

  await page.route('**/api/tahp/gerrit-config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          host: 'https://gerrit.transsion.com',
          user: 'test.user',
          configured: true,
          passwordSet: true,
        },
      }),
    })
  })

  await page.route('**/api/tahp/gerrit-review/chat', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          session_id: 'sess-gerrit-test',
          task_id: 'task-gerrit-test',
          status: 'running',
        },
      }),
    })
  })

  await page.goto('/#/tahp/self-check')
  await expect(page.getByRole('heading', { name: 'AI 自检' })).toBeVisible()
  await expect(page.getByText('多设备并行自动化测试')).toBeVisible()
  await expect(page.getByText('Gerrit Code Review')).toBeVisible()
  await expect(page.getByText('Code Review 对话')).toBeVisible()
  await expect(page.getByText('AI 测试建议')).toBeVisible()
  await expect(page.getByText('必须测试')).toBeVisible()
  await expect(page.getByText('推荐测试用例')).toBeVisible()
  await expect(page.getByText('模块：')).toBeVisible()
  await expect(page.getByText('AI测试自规划')).toBeVisible()
  await expect(page.getByText('项目节点')).toBeVisible()
  await expect(page.getByText('测试规划')).toBeVisible()
  await expect(page.getByText('X6885 STR4A 2026/07/07')).toBeVisible()
  await expect(page.getByText('X6885 STR4A 2026/06/27 GMS测试')).toBeVisible()
})

test('self-check shows warning when gerrit is not configured', async ({ page }) => {
  await authenticate(page, TEST_ACCESS_KEY, 'research')
  await mockHermesApi(page)
  await mockDeviceSelfCheckApi(page)
  await mockTestPlanningApi(page)

  await page.route('**/api/tahp/gerrit-config', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          host: 'https://gerrit.transsion.com',
          user: '',
          configured: false,
          passwordSet: false,
        },
      }),
    })
  })

  await page.goto('/#/tahp/self-check')
  await expect(
    page.getByText('gerrit账号未设置，无法进行code review，请在设置中完善gerrit账号'),
  ).toBeVisible()
})
