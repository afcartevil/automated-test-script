import { expect, test } from '@playwright/test'
import { authenticate, mockHermesApi, TEST_ACCESS_KEY } from './fixtures'

function mockDeviceSelfCheckApi(page: import('@playwright/test').Page) {
  const pipelinePayload = {
    stages: [
      { key: 'test', label: '自动测试', status: 'idle' },
      { key: 'review', label: '人工复核测试报告', status: 'idle' },
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

function mockVerifyTasksApi(page: import('@playwright/test').Page) {
  const tasksPayload = [
    {
      task_id: 'vt_e2e_1',
      test_type: 'monkey',
      item_label: 'monkey测试',
      owner: 'test.user',
      project: 'LJ9',
      status: 'pending',
      created_by: 'admin',
      created_at: '2026-09-07T02:30:00.000Z',
    },
    {
      task_id: 'vt_e2e_2',
      test_type: 'week',
      item_label: '周版本测试',
      owner: 'test.user',
      project: 'X6885',
      status: 'pending',
      created_by: 'auto-plan',
      created_at: '2026-09-06T09:00:00.000Z',
    },
  ]

  return page.route('**/api/tahp/verify-tasks/mine**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ success: true, data: tasksPayload }),
    })
  })
}

test('self-check page renders tabs and workspaces', async ({ page }) => {
  await authenticate(page, TEST_ACCESS_KEY, 'research')
  await mockHermesApi(page)
  await mockDeviceSelfCheckApi(page)
  await mockVerifyTasksApi(page)

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
  await expect(page.getByRole('heading', { name: '质量验测', level: 1 })).toBeVisible()
  await expect(page.getByText('今日自动化流程')).not.toBeVisible()
  await expect(page.getByRole('button', { name: '总览' })).toBeVisible()
  await expect(page.getByRole('button', { name: '自动规划' })).not.toBeVisible()
  await expect(page.getByRole('button', { name: '测试执行' })).toBeVisible()
  await expect(page.getByRole('button', { name: '评审补全' })).toBeVisible()
  await expect(page.getByRole('button', { name: '测试报告' })).toBeVisible()
  await expect(page.getByText('流程状态').first()).toBeVisible()
  const reviewCardHead = page.locator('.review-card-head')
  await expect(reviewCardHead).not.toBeVisible()

  // 总览「验测任务」卡片：项目 / 测试项 / 指派时间 / 指派账号
  await expect(page.getByText('验测任务').first()).toBeVisible()
  await expect(page.getByText('LJ9').first()).toBeVisible()
  await expect(page.getByText(/monkey测试 · 指派于 .* · admin/).first()).toBeVisible()
  await expect(page.getByText(/周版本测试 · 指派于 .* · auto-plan/).first()).toBeVisible()

  await page.getByRole('button', { name: '评审补全' }).click()
  await expect(page.getByText('Gerrit 链接 → 启动识别「必测项」 → 从用例库推荐测试用例（带覆盖度评分）→ 覆盖不足时 AI 生成用例')).toBeVisible()
  await expect(page.getByText('Code Review 对话')).toBeVisible()
  await expect(page.getByText('必须测试')).toBeVisible()
})

test('self-check shows warning when gerrit is not configured', async ({ page }) => {
  await authenticate(page, TEST_ACCESS_KEY, 'research')
  await mockHermesApi(page)
  await mockDeviceSelfCheckApi(page)
  await mockVerifyTasksApi(page)

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
  await page.getByRole('button', { name: '评审补全' }).click()
  await expect(
    page.getByText('gerrit账号未设置，无法进行code review，请在设置中完善gerrit账号'),
  ).toBeVisible()
  await expect(page.getByRole('link', { name: '去设置' })).toHaveAttribute(
    'href',
    /#\/tahp\/config\?tab=form/,
  )
})
