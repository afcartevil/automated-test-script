// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const startMock = vi.fn()
const getRunMock = vi.fn()
const listMock = vi.fn()
const cancelMock = vi.fn()

vi.mock('@/api/tahp/checklist-scmp-sync', () => ({
  startChecklistScmpSync: (...args: unknown[]) => startMock(...args),
  getChecklistScmpRun: (...args: unknown[]) => getRunMock(...args),
  listChecklistScmpRuns: (...args: unknown[]) => listMock(...args),
  cancelChecklistScmpSync: (...args: unknown[]) => cancelMock(...args),
}))

vi.mock('@/api/tahp/socket', () => ({
  waitForTahpSocketReady: () => Promise.resolve(),
  getTahpSocket: () => ({ on: vi.fn(), off: vi.fn(), connected: true }),
}))

import {
  CHECKLIST_SCMP_PLACEHOLDER,
  useChecklistScmpSyncStore,
} from '../../packages/client/src/stores/tahp/checklist-scmp-sync'

describe('useChecklistScmpSyncStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    startMock.mockReset()
    getRunMock.mockReset()
    listMock.mockReset()
    cancelMock.mockReset()
    listMock.mockResolvedValue({ active: null, items: [] })
  })

  it('requires a document title format in the placeholder', () => {
    expect(CHECKLIST_SCMP_PLACEHOLDER).toContain('项目编码')
    expect(CHECKLIST_SCMP_PLACEHOLDER).toContain('tOS')
    expect(CHECKLIST_SCMP_PLACEHOLDER).toContain('X6879-tOS17 全功能特性checklist_V2.5')
  })

  it('starts a run and tracks the returned id', async () => {
    startMock.mockResolvedValue({ run_id: 'css-1' })
    getRunMock.mockResolvedValue({
      run_id: 'css-1',
      url: 'https://transsioner.feishu.cn/wiki/abc',
      status: 'running',
      progress: 8,
      phase: 'workbook',
      message: '已读取文档',
      log_tail: ['已读取文档'],
      created_at: 't',
      updated_at: 't',
    })
    const store = useChecklistScmpSyncStore()
    store.url = 'https://transsioner.feishu.cn/wiki/abc'
    await store.start()
    expect(startMock).toHaveBeenCalledWith('https://transsioner.feishu.cn/wiki/abc')
    expect(store.currentRunId).toBe('css-1')
    expect(store.isRunning).toBe(true)
    store.stopPoll()
  })

  it('does not start without a url', async () => {
    const store = useChecklistScmpSyncStore()
    store.url = '  '
    await store.start()
    expect(startMock).not.toHaveBeenCalled()
    expect(store.error).toMatch(/飞书文档链接/)
  })
})
