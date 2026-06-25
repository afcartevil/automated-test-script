import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const sendGerritReviewMessageMock = vi.fn()

const fetchRecommendCasesMock = vi.fn()

vi.mock('../../packages/client/src/api/tahp/gerrit-review', () => ({
  sendGerritReviewMessage: (...args: unknown[]) => sendGerritReviewMessageMock(...args),
  fetchRecommendCases: (...args: unknown[]) => fetchRecommendCasesMock(...args),
}))

vi.mock('../../packages/client/src/api/client', () => ({
  request: vi.fn(),
  getApiKey: vi.fn(() => 'test-key'),
  hasApiKey: vi.fn(() => true),
  setApiKey: vi.fn(),
}))

import { useGerritReviewStore } from '../../packages/client/src/stores/tahp/gerrit-review'
import { useTahpTasksStore } from '../../packages/client/src/stores/tahp/tasks'

describe('useGerritReviewStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sendGerritReviewMessageMock.mockReset()
    fetchRecommendCasesMock.mockReset()
    fetchRecommendCasesMock.mockResolvedValue({ recommended_cases: [] })
  })

  it('restores in-progress task and streaming bubble after remount', () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    gerrit.sessionId = 'sess-1'
    gerrit.activeTaskId = 'task-gerrit-1'
    gerrit.taskStatus = 'running'
    gerrit.chatMessages = [
      { id: 'u1', role: 'user', content: 'https://gerrit.example/+/1' },
    ]
    tasks.taskStreams = {
      'task-gerrit-1': [
        { type: 'task.started', payload: { message: 'started' }, ts: 1 },
        { type: 'task.phase', payload: { message: '执行中' }, ts: 2 },
      ],
    }

    gerrit.reconcileActiveTask()

    expect(gerrit.chatMessages.some(m => m.streaming && m.taskId === 'task-gerrit-1')).toBe(true)
    expect(gerrit.isRunning).toBe(true)
  })

  it('finalizes assistant message when task completed while away', () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    gerrit.activeTaskId = 'task-gerrit-2'
    gerrit.chatMessages = [
      { id: 'u1', role: 'user', content: 'review' },
      { id: 'a1', role: 'assistant', content: '', streaming: true, taskId: 'task-gerrit-2' },
    ]
    tasks.taskStreams = {
      'task-gerrit-2': [
        {
          type: 'task.completed',
          payload: {
            llm_response: '## 5. 测试建议\n\n### P0 - 必须测试\n1. **充电** - 插拔',
            p0_items: ['**充电** - 插拔'],
            p0_raw_section: '1. **充电** - 插拔',
          },
          ts: 3,
        },
      ],
    }

    gerrit.processStreamEvents('task-gerrit-2')

    expect(gerrit.isFinalized('task-gerrit-2')).toBe(true)
    expect(gerrit.chatMessages.find(m => m.taskId === 'task-gerrit-2')?.streaming).toBe(false)
    expect(gerrit.serverP0Items).toEqual(['**充电** - 插拔'])
    expect(gerrit.isRunning).toBe(false)
  })

  it('allows starting a second review after the first one completed', async () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    gerrit.sessionId = 'sess-1'
    gerrit.activeTaskId = 'task-gerrit-1'
    gerrit.runningTaskId = 'task-gerrit-1'
    gerrit.taskStatus = 'running'
    gerrit.chatMessages = [
      { id: 'u1', role: 'user', content: 'https://gerrit.example/+/1' },
      { id: 'a1', role: 'assistant', content: '', streaming: true, taskId: 'task-gerrit-1' },
    ]
    tasks.taskStreams = {
      'task-gerrit-1': [
        {
          type: 'task.completed',
          payload: { llm_response: '# report 1', p0_items: ['item-1'] },
          ts: 1,
        },
      ],
    }

    gerrit.processStreamEvents('task-gerrit-1')
    expect(gerrit.isRunning).toBe(false)
    expect(gerrit.chatMessages.find(m => m.taskId === 'task-gerrit-1')?.streaming).toBe(false)

    sendGerritReviewMessageMock.mockResolvedValueOnce({
      session_id: 'sess-1',
      task_id: 'task-gerrit-2',
      status: 'running',
    })

    await gerrit.sendMessage('https://gerrit.example/+/2')

    expect(sendGerritReviewMessageMock).toHaveBeenCalledTimes(1)
    expect(gerrit.activeTaskId).toBe('task-gerrit-2')
    expect(gerrit.runningTaskId).toBe('task-gerrit-2')
    expect(gerrit.chatMessages.filter(m => m.role === 'user')).toHaveLength(2)
    expect(gerrit.chatMessages.some(m => m.streaming && m.taskId === 'task-gerrit-2')).toBe(true)
  })

  it('extracts P0 client-side when server sends empty p0_items', () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    gerrit.activeTaskId = 'task-gerrit-p0'
    tasks.taskStreams = {
      'task-gerrit-p0': [
        {
          type: 'task.completed',
          payload: {
            llm_response: '### 4. 测试建议\n**P0 - 必须测试**\n* item one\n* item two\n\n**P1 - 强烈建议**\n* other',
            p0_items: [],
          },
          ts: 1,
        },
      ],
    }

    gerrit.processStreamEvents('task-gerrit-p0')

    expect(gerrit.serverP0Items).toEqual(['item one', 'item two'])
    expect(gerrit.p0Result().items).toHaveLength(2)
  })

  it('loads recommended cases from completion payload', async () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    gerrit.activeTaskId = 'task-gerrit-rec'
    tasks.taskStreams = {
      'task-gerrit-rec': [
        {
          type: 'task.completed',
          payload: {
            llm_response: '**模块**: USB\n### P0 - 必须测试\n1. USB 插拔',
            modules: ['USB'],
            modules_display: 'USB',
            p0_items: ['USB 插拔'],
            recommended_cases: [
              {
                caseKey: 'week/driver/14',
                caseName: 'USB功能正常充电',
                moduleLabel: '驱动',
                score: 4,
                reasons: ['模块:USB'],
              },
            ],
          },
          ts: 1,
        },
      ],
    }

    gerrit.processStreamEvents('task-gerrit-rec')
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(gerrit.serverModulesDisplay).toBe('USB')
    expect(gerrit.recommendedCases).toHaveLength(1)
    expect(gerrit.recommendedCases[0]?.checked).toBe(true)
    expect(gerrit.checkedRecommendedCases[0]?.caseKey).toBe('week/driver/14')
  })

  it('second review clears running state and applies AI test insight after completion', async () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    gerrit.sessionId = 'sess-1'
    gerrit.activeTaskId = 'task-gerrit-1'
    gerrit.finalizedTaskIds = ['task-gerrit-1']
    gerrit.chatMessages = [
      { id: 'u1', role: 'user', content: 'https://gerrit.example/+/1' },
      { id: 'a1', role: 'assistant', content: '# report 1', taskId: 'task-gerrit-1' },
    ]
    tasks.taskStreams = {
      'task-gerrit-1': [
        { type: 'task.completed', payload: { llm_response: '# report 1', p0_items: ['item-1'] }, ts: 1 },
      ],
    }

    sendGerritReviewMessageMock.mockResolvedValueOnce({
      session_id: 'sess-1',
      task_id: 'task-gerrit-2',
      status: 'running',
    })

    const sendPromise = gerrit.sendMessage('https://gerrit.example/+/2')
    tasks.taskStreams = {
      ...tasks.taskStreams,
      'task-gerrit-2': [
        { type: 'task.message', payload: { level: 'stream', text: '# report 2' }, ts: 2 },
        {
          type: 'task.completed',
          payload: {
            llm_response: '### P0 - 必须测试\n1. USB 插拔',
            p0_items: ['USB 插拔'],
            recommended_cases: [
              {
                caseKey: 'week/driver/14',
                caseName: 'USB功能正常充电',
                moduleLabel: '驱动',
                score: 1,
                reasons: ['必须测试:USB'],
              },
            ],
          },
          ts: 3,
        },
      ],
    }
    gerrit.processStreamEvents('task-gerrit-2')
    await sendPromise

    expect(gerrit.isRunning).toBe(false)
    expect(gerrit.sending).toBe(false)
    expect(gerrit.serverP0Items).toEqual(['USB 插拔'])
    expect(gerrit.recommendedCases).toHaveLength(1)
    expect(gerrit.chatMessages.filter(m => m.streaming)).toHaveLength(0)
  })

  it('finalizes the latest streaming bubble when an older assistant is still streaming', () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    gerrit.activeTaskId = 'task-gerrit-2'
    gerrit.runningTaskId = 'task-gerrit-2'
    gerrit.chatMessages = [
      { id: 'u1', role: 'user', content: 'first' },
      { id: 'a1', role: 'assistant', content: '', streaming: true, taskId: 'task-gerrit-1' },
      { id: 'u2', role: 'user', content: 'second' },
      { id: 'a2', role: 'assistant', content: '', streaming: true, taskId: 'task-gerrit-2' },
    ]
    tasks.taskStreams = {
      'task-gerrit-2': [
        {
          type: 'task.completed',
          payload: {
            llm_response: '### P0 - 必须测试\n1. USB 插拔',
            p0_items: ['USB 插拔'],
          },
          ts: 1,
        },
      ],
    }

    gerrit.processStreamEvents('task-gerrit-2')

    expect(gerrit.isRunning).toBe(false)
    expect(gerrit.serverP0Items).toEqual(['USB 插拔'])
    expect(gerrit.chatMessages.find(m => m.taskId === 'task-gerrit-2')?.streaming).toBe(false)
    expect(gerrit.chatMessages.find(m => m.taskId === 'task-gerrit-2')?.content).toContain('USB 插拔')
    expect(gerrit.chatMessages.find(m => m.taskId === 'task-gerrit-1')?.streaming).toBe(false)
  })

  it('recovers stuck running state before next send when completion event exists', async () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    gerrit.activeTaskId = 'task-gerrit-stuck'
    gerrit.runningTaskId = 'task-gerrit-stuck'
    gerrit.taskStatus = 'running'
    gerrit.chatMessages = [
      { id: 'u1', role: 'user', content: 'review' },
      { id: 'a1', role: 'assistant', content: '', streaming: true, taskId: 'task-gerrit-stuck' },
    ]
    tasks.taskStreams = {
      'task-gerrit-stuck': [
        { type: 'task.message', payload: { level: 'stream', text: '# report stuck' }, ts: 1 },
        { type: 'task.completed', payload: { llm_response: '# report stuck' }, ts: 2 },
      ],
    }

    sendGerritReviewMessageMock.mockResolvedValueOnce({
      session_id: 'sess-2',
      task_id: 'task-gerrit-next',
      status: 'running',
    })

    await gerrit.sendMessage('https://gerrit.example/+/next')

    expect(gerrit.isFinalized('task-gerrit-stuck')).toBe(true)
    expect(gerrit.chatMessages.find(m => m.taskId === 'task-gerrit-stuck')?.streaming).toBe(false)
    expect(gerrit.activeTaskId).toBe('task-gerrit-next')
  })
})
