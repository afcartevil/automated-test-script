import { expect, test } from '@playwright/test'
import { authenticate, mockHermesApi, TEST_ACCESS_KEY } from './fixtures'

function mockDeviceSelfCheckApi(page: import('@playwright/test').Page) {
  const pipelinePayload = {
    stages: [
      { key: 'sync', label: '项目节点同步', status: 'done', hint: '1 个项目' },
      { key: 'flash', label: '版本拉取/烧录', status: 'idle' },
      { key: 'test', label: '自动测试', status: 'queued' },
      { key: 'review', label: '人工 Review', status: 'idle' },
    ],
    updatedAt: '2026-06-24T08:00:00.000Z',
    runningTests: 0,
    pendingManual: 0,
    pendingReports: 0,
  }

  return page.route('**/api/tahp/device-self-check/**', async (route) => {
    const url = route.request().url()
    if (url.includes('/pipeline')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: pipelinePayload }),
      })
      return
    }
    if (url.includes('/reports')) {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ success: true, data: [] }),
      })
      return
    }
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
    sourcePath: 'temp_milestone_info/升级项目关键信息表.xlsx',
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
    rules: [{ node: 'STR4A', offsetDays: -10, testType: 'monkey' }],
    items: [
      {
        scheduleKey: 'X6885|STR4A|2026/06/27|monkey',
        project: 'X6885',
        node: 'STR4A',
        nodeDate: '2026/07/07',
        triggerDate: '2026/06/27',
        testType: 'monkey',
        testTypeLabel: 'monkey测试',
        phase: 'upcoming',
        runtimeStatus: 'no_device',
        displayLabel: '即将开始',
        tags: ['无设备'],
        display: 'X6885 STR4A 2026/06/27 monkey测试',
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

test('self-check page renders tabs and workspaces', async ({ page }) => {
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

  await page.route('**/api/tahp/reports/tasks', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: [] }),
    })
  })

  await page.goto('/#/tahp/self-check')
  await expect(page.getByRole('heading', { name: 'AI 自检', level: 1 })).toBeVisible()
  await expect(page.getByText('今日自动化流程')).not.toBeVisible()
  await expect(page.getByRole('button', { name: '总览' })).toBeVisible()
  await expect(page.getByRole('button', { name: '项目规划' })).toBeVisible()
  await expect(page.getByRole('button', { name: '设备执行' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'AI用例' })).toBeVisible()
  await expect(page.getByRole('button', { name: '测试报告' })).toBeVisible()
  await expect(page.getByText('项目规划').first()).toBeVisible()
  await expect(page.getByText('流程状态').first()).toBeVisible()
  const reviewCardHead = page.locator('.review-card-head')
  await expect(reviewCardHead).not.toBeVisible()

  await page.getByRole('button', { name: 'AI用例' }).click()
  await expect(page.getByText('输入gerrit链接，AI生成测试用例&AI推荐测试用例')).toBeVisible()
  await expect(page.getByText('Code Review 对话')).toBeVisible()
  await expect(page.getByText('必须测试')).toBeVisible()

  await page.getByRole('button', { name: '项目规划' }).click()
  await expect(page.getByText('AI测试自规划')).toBeVisible()
  await expect(page.getByText('项目节点')).toBeVisible()
  const nodesPanel = page.locator('.nodes-panel .item-list li').first()
  await expect(nodesPanel).toContainText('X6885')
  await expect(nodesPanel).toContainText('STR4A')
  await expect(nodesPanel).toContainText('2026/07/07')

  await expect(page.getByText('无设备')).toBeVisible()

  const schedulePanel = page.locator('.schedule-panel .schedule-table').first()
  await expect(schedulePanel.locator('.col-date')).toContainText('2026/06/27')
  await expect(schedulePanel.locator('.col-project')).toContainText('X6885')
  await expect(schedulePanel.locator('.col-test')).toContainText('monkey测试')
  await expect(schedulePanel.locator('.col-status')).toContainText('即将开始')
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

  await page.route('**/api/tahp/reports/tasks', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: [] }),
    })
  })

  await page.goto('/#/tahp/self-check')
  await page.getByRole('button', { name: 'AI用例' }).click()
  await expect(
    page.getByText('gerrit账号未设置，无法进行code review，请在设置中完善gerrit账号'),
  ).toBeVisible()
  await expect(page.getByRole('link', { name: '去设置' })).toHaveAttribute(
    'href',
    /#\/tahp\/config\?tab=form/,
  )
})
