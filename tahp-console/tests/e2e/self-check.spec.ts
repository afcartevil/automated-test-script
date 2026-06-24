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

test('self-check page renders device and gerrit review workspaces', async ({ page }) => {
  await authenticate(page, TEST_ACCESS_KEY, 'research')
  await mockHermesApi(page)
  await mockDeviceSelfCheckApi(page)

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
  await expect(page.getByText('P0 - 必须测试')).toBeVisible()
})

test('self-check shows warning when gerrit is not configured', async ({ page }) => {
  await authenticate(page, TEST_ACCESS_KEY, 'research')
  await mockHermesApi(page)
  await mockDeviceSelfCheckApi(page)

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
