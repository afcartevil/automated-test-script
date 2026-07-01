import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const sendGerritReviewMessageMock = vi.fn()

const fetchRecommendCasesMock = vi.fn()

const cancelGerritReviewTaskMock = vi.fn()

vi.mock('../../packages/client/src/utils/gerrit-review-debug', () => ({
  gerritReviewDebug: vi.fn(),
  flushGerritReviewDebug: vi.fn(),
}))

vi.mock('../../packages/client/src/api/tahp/gerrit-review', () => ({
  sendGerritReviewMessage: (...args: unknown[]) => sendGerritReviewMessageMock(...args),
  fetchRecommendCases: (...args: unknown[]) => fetchRecommendCasesMock(...args),
  cancelGerritReviewTask: (...args: unknown[]) => cancelGerritReviewTaskMock(...args),
}))

vi.mock('../../packages/client/src/api/tahp/socket', () => ({
  getTahpSocket: () => ({
    connected: true,
    on: vi.fn(),
    off: vi.fn(),
    once: vi.fn(),
    connect: vi.fn(),
  }),
  waitForTahpSocketReady: vi.fn(() => Promise.resolve()),
}))

import { useGerritReviewStore } from '../../packages/client/src/stores/tahp/gerrit-review'
import { useTahpTasksStore } from '../../packages/client/src/stores/tahp/tasks'

describe('useGerritReviewStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    sendGerritReviewMessageMock.mockReset()
    fetchRecommendCasesMock.mockReset()
    fetchRecommendCasesMock.mockResolvedValue({ recommended_cases: [], source: 'rule' })
    cancelGerritReviewTaskMock.mockReset()
    cancelGerritReviewTaskMock.mockResolvedValue({ ok: true, action: 'interrupted_running' })
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

  it('fetches recommended cases when completion payload has empty recommended_cases', async () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    fetchRecommendCasesMock.mockResolvedValueOnce({
      recommended_cases: [
        {
          caseKey: 'week/driver/14',
          caseName: 'USB功能正常充电',
          moduleLabel: '驱动',
          score: 2,
          reasons: ['必须测试:USB'],
        },
      ],
      source: 'rule',
    })

    gerrit.activeTaskId = 'task-gerrit-fetch'
    gerrit.runningTaskId = 'task-gerrit-fetch'
    gerrit.chatMessages = [
      { id: 'u1', role: 'user', content: '测试建议' },
      { id: 'a1', role: 'assistant', content: '', streaming: true, taskId: 'task-gerrit-fetch' },
    ]
    tasks.taskStreams = {
      'task-gerrit-fetch': [
        {
          type: 'task.completed',
          payload: {
            llm_response: '### 4. 测试建议\n#### ### P0 - 必须测试\n1. USB 插拔验证 SAR 校准',
            p0_items: [],
            recommended_cases: [],
          },
          ts: 1,
        },
      ],
    }

    gerrit.processStreamEvents('task-gerrit-fetch')
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(gerrit.isRunning).toBe(false)
    expect(gerrit.serverP0Items.length).toBeGreaterThan(0)
    expect(fetchRecommendCasesMock).toHaveBeenCalled()
    expect(gerrit.recommendedCases).toHaveLength(1)
    expect(gerrit.recommendedCases[0]?.caseKey).toBe('week/driver/14')
  })

  it('uses stream text when completion payload omits llm_response', async () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    fetchRecommendCasesMock.mockResolvedValueOnce({
      recommended_cases: [
        {
          caseKey: 'week/driver/14',
          caseName: 'USB功能正常充电',
          moduleLabel: '驱动',
          score: 1,
          reasons: ['必须测试:USB'],
        },
      ],
      source: 'rule',
    })

    gerrit.activeTaskId = 'task-gerrit-stream'
    gerrit.runningTaskId = 'task-gerrit-stream'
    gerrit.chatMessages = [
      { id: 'u1', role: 'user', content: 'review' },
      { id: 'a1', role: 'assistant', content: '', streaming: true, taskId: 'task-gerrit-stream' },
    ]
    tasks.taskStreams = {
      'task-gerrit-stream': [
        {
          type: 'task.message',
          payload: { level: 'stream', text: '### P0 - 必须测试\n1. USB 插拔' },
          ts: 1,
        },
        {
          type: 'task.completed',
          payload: { p0_items: [], recommended_cases: [] },
          ts: 2,
        },
      ],
    }

    gerrit.processStreamEvents('task-gerrit-stream')
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(gerrit.isRunning).toBe(false)
    expect(gerrit.serverP0Items).toEqual(['USB 插拔'])
    expect(gerrit.recommendedCases).toHaveLength(1)
  })

  it('clears stuck running state after remount when task already completed', () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    gerrit.activeTaskId = 'task-gerrit-done'
    gerrit.runningTaskId = 'task-gerrit-done'
    gerrit.finalizedTaskIds = ['task-gerrit-done']
    gerrit.chatMessages = [
      { id: 'u1', role: 'user', content: 'review' },
      { id: 'a1', role: 'assistant', content: '# done', taskId: 'task-gerrit-done' },
    ]
    tasks.taskStreams = {
      'task-gerrit-done': [
        { type: 'task.completed', payload: { llm_response: '# done' }, ts: 1 },
      ],
    }

    gerrit.reconcileActiveTask()

    expect(gerrit.isRunning).toBe(false)
    expect(gerrit.runningTaskId).toBeNull()
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
            recommend_source: 'llm',
            recommended_cases: [
              {
                caseKey: 'week/driver/14',
                caseName: 'USB功能正常充电',
                moduleLabel: '驱动',
                score: 4,
                reasons: ['P0 要求验证 USB 插拔稳定性'],
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
    expect(gerrit.recommendSource).toBe('llm')
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

  it('clears running state when finalized task still has streaming flag', () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    gerrit.activeTaskId = 'task-gerrit-stuck-stream'
    gerrit.runningTaskId = 'task-gerrit-stuck-stream'
    gerrit.finalizedTaskIds = ['task-gerrit-stuck-stream']
    gerrit.chatMessages = [
      { id: 'u1', role: 'user', content: 'review' },
      {
        id: 'a1',
        role: 'assistant',
        content: '',
        streaming: true,
        taskId: 'task-gerrit-stuck-stream',
      },
    ]
    tasks.taskStreams = {
      'task-gerrit-stuck-stream': [
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

    gerrit.processStreamEvents('task-gerrit-stuck-stream')

    expect(gerrit.isRunning).toBe(false)
    expect(gerrit.chatMessages.find(m => m.taskId === 'task-gerrit-stuck-stream')?.streaming).toBe(false)
  })

  it('stops pending send before task id is assigned', async () => {
    const gerrit = useGerritReviewStore()

    sendGerritReviewMessageMock.mockImplementation(() => new Promise(() => {}))
    const sendPromise = gerrit.sendMessage('https://gerrit.example/+/pending')
    await Promise.resolve()

    expect(gerrit.isRunning).toBe(true)
    await gerrit.stopReview()

    expect(gerrit.isRunning).toBe(false)
    expect(gerrit.chatMessages.some(m => m.streaming)).toBe(false)
    expect(cancelGerritReviewTaskMock).not.toHaveBeenCalled()
    void sendPromise
  })

  it('stops running review via cancel API and task.cancelled event', async () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    gerrit.activeTaskId = 'task-gerrit-stop'
    gerrit.runningTaskId = 'task-gerrit-stop'
    gerrit.chatMessages = [
      { id: 'u1', role: 'user', content: 'review' },
      { id: 'a1', role: 'assistant', content: '', streaming: true, taskId: 'task-gerrit-stop' },
    ]

    const stopPromise = gerrit.stopReview()
    tasks.taskStreams = {
      'task-gerrit-stop': [
        {
          type: 'task.cancelled',
          payload: { message: '评审已被用户停止' },
          ts: 1,
        },
      ],
    }
    gerrit.processStreamEvents('task-gerrit-stop')
    await stopPromise

    expect(cancelGerritReviewTaskMock).toHaveBeenCalledWith('task-gerrit-stop')
    expect(gerrit.isRunning).toBe(false)
    expect(gerrit.chatMessages.find(m => m.taskId === 'task-gerrit-stop')?.streaming).toBe(false)
    expect(gerrit.chatMessages.find(m => m.taskId === 'task-gerrit-stop')?.content).toContain('评审已被用户停止')
  })

  it('stops running review optimistically before task.cancelled arrives', async () => {
    const gerrit = useGerritReviewStore()

    gerrit.activeTaskId = 'task-gerrit-stop-fast'
    gerrit.runningTaskId = 'task-gerrit-stop-fast'
    gerrit.chatMessages = [
      { id: 'u1', role: 'user', content: 'review' },
      { id: 'a1', role: 'assistant', content: '', streaming: true, taskId: 'task-gerrit-stop-fast' },
    ]

    await gerrit.stopReview()

    expect(cancelGerritReviewTaskMock).toHaveBeenCalledWith('task-gerrit-stop-fast')
    expect(gerrit.isRunning).toBe(false)
    expect(gerrit.chatMessages.find(m => m.taskId === 'task-gerrit-stop-fast')?.streaming).toBe(false)
    expect(gerrit.chatMessages.find(m => m.taskId === 'task-gerrit-stop-fast')?.content).toContain('评审已被用户停止')
  })

  it('does not replay cancelled events onto new pending assistant bubble', () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    gerrit.activeTaskId = null
    gerrit.runningTaskId = 'pending'
    gerrit.finalizedTaskIds = ['task-gerrit-old']
    gerrit.chatMessages = [
      { id: 'u1', role: 'user', content: 'first' },
      { id: 'a-old', role: 'assistant', content: '**评审已被用户停止**', taskId: 'task-gerrit-old' },
      { id: 'a-new', role: 'assistant', content: '', streaming: true },
    ]
    tasks.taskStreams = {
      'task-gerrit-old': [
        {
          type: 'task.message',
          payload: { level: 'warn', text: '已请求停止评审，等待 Agent 结束…' },
          ts: 1,
        },
        {
          type: 'task.cancelled',
          payload: { message: '评审已被用户停止' },
          ts: 2,
        },
      ],
    }

    gerrit.processStreamEvents('task-gerrit-old')

    const pending = gerrit.chatMessages.find(m => m.id === 'a-new')
    expect(pending?.content).toBe('')
    expect(pending?.streaming).toBe(true)
  })

  it('sendMessage after cancelled review starts fresh task without stop text', async () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    gerrit.sessionId = 'sess-1'
    gerrit.activeTaskId = 'task-gerrit-old'
    gerrit.finalizedTaskIds = ['task-gerrit-old']
    gerrit.chatMessages = [
      { id: 'u1', role: 'user', content: 'first' },
      { id: 'a1', role: 'assistant', content: '**评审已被用户停止**', taskId: 'task-gerrit-old' },
    ]
    tasks.taskStreams = {
      'task-gerrit-old': [
        {
          type: 'task.message',
          payload: { level: 'warn', text: '已请求停止评审，等待 Agent 结束…' },
          ts: 1,
        },
        {
          type: 'task.cancelled',
          payload: { message: '评审已被用户停止' },
          ts: 2,
        },
      ],
    }

    sendGerritReviewMessageMock.mockResolvedValueOnce({
      session_id: 'sess-1',
      task_id: 'task-gerrit-new',
      status: 'running',
    })

    await gerrit.sendMessage('https://gerrit.example/+/2')

    const latestAssistant = [...gerrit.chatMessages].reverse().find(m => m.role === 'assistant')
    expect(latestAssistant?.taskId).toBe('task-gerrit-new')
    expect(latestAssistant?.content).not.toContain('评审已被用户停止')
    expect(latestAssistant?.content).not.toContain('已请求停止评审')
    expect(gerrit.activeTaskId).toBe('task-gerrit-new')
  })

  it('third consecutive review clears running state and applies latest insight', async () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    const completeTask = (taskId: string, p0: string, cases: Array<Record<string, unknown>>) => {
      tasks.taskStreams = {
        ...tasks.taskStreams,
        [taskId]: [
          {
            type: 'task.completed',
            payload: {
              llm_response: `### P0 - 必须测试\n1. ${p0}`,
              p0_items: [p0],
              recommended_cases: cases,
            },
            ts: Date.now(),
          },
        ],
      }
      gerrit.processStreamEvents(taskId)
    }

    gerrit.sessionId = 'sess-multi'
    sendGerritReviewMessageMock
      .mockResolvedValueOnce({ session_id: 'sess-multi', task_id: 'task-r1', status: 'running' })
      .mockResolvedValueOnce({ session_id: 'sess-multi', task_id: 'task-r2', status: 'running' })
      .mockResolvedValueOnce({ session_id: 'sess-multi', task_id: 'task-r3', status: 'running' })

    await gerrit.sendMessage('https://gerrit.example/+/1')
    completeTask('task-r1', '充电插拔', [{
      caseKey: 'week/driver/1',
      caseName: 'case-1',
      moduleLabel: '驱动',
      score: 1,
      reasons: [],
    }])
    expect(gerrit.isRunning).toBe(false)
    expect(gerrit.serverP0Items).toEqual(['充电插拔'])

    await gerrit.sendMessage('https://gerrit.example/+/2')
    completeTask('task-r2', 'USB 枚举', [{
      caseKey: 'week/driver/14',
      caseName: 'USB功能正常充电',
      moduleLabel: '驱动',
      score: 2,
      reasons: [],
    }])
    expect(gerrit.isRunning).toBe(false)
    expect(gerrit.serverP0Items).toEqual(['USB 枚举'])

    await gerrit.sendMessage('https://gerrit.example/+/3')
    completeTask('task-r3', 'SAR 校准', [{
      caseKey: 'week/driver/20',
      caseName: 'SAR传感器',
      moduleLabel: '驱动',
      score: 3,
      reasons: [],
    }])

    expect(gerrit.isRunning).toBe(false)
    expect(gerrit.sending).toBe(false)
    expect(gerrit.runningTaskId).toBeNull()
    expect(gerrit.serverP0Items).toEqual(['SAR 校准'])
    expect(gerrit.recommendedCases).toHaveLength(1)
    expect(gerrit.recommendedCases[0]?.caseKey).toBe('week/driver/20')
    expect(gerrit.chatMessages.filter(m => m.streaming)).toHaveLength(0)
  })

  it('does not apply stale insight when an older task is synchronized during a new review', async () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    gerrit.sessionId = 'sess-1'
    gerrit.activeTaskId = 'task-new'
    gerrit.runningTaskId = 'task-new'
    gerrit.chatMessages = [
      { id: 'u1', role: 'user', content: 'first' },
      { id: 'a-old', role: 'assistant', content: '', streaming: true, taskId: 'task-old' },
      { id: 'u2', role: 'user', content: 'second' },
      { id: 'a-new', role: 'assistant', content: '', streaming: true, taskId: 'task-new' },
    ]
    gerrit.finalizedTaskIds = []
    tasks.taskStreams = {
      'task-old': [
        {
          type: 'task.completed',
          payload: {
            llm_response: '### P0 - 必须测试\n1. OLD',
            p0_items: ['OLD'],
            recommended_cases: [{
              caseKey: 'week/driver/1',
              caseName: 'old-case',
              moduleLabel: '驱动',
              score: 1,
              reasons: [],
            }],
          },
          ts: 1,
        },
      ],
      'task-new': [],
    }

    gerrit.processStreamEvents('task-old')

    expect(gerrit.serverP0Items).not.toEqual(['OLD'])
    expect(gerrit.recommendedCases[0]?.caseKey).not.toBe('week/driver/1')
    expect(gerrit.isRunning).toBe(true)
  })

  it('does not clear pending running state when syncing an unrelated finalized task', async () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    gerrit.sessionId = 'sess-1'
    gerrit.activeTaskId = null
    gerrit.runningTaskId = 'pending'
    gerrit.sending = true
    gerrit.chatMessages = [
      { id: 'u1', role: 'user', content: 'first' },
      { id: 'a-old', role: 'assistant', content: '', streaming: true, taskId: 'task-old' },
      { id: 'a-new', role: 'assistant', content: '', streaming: true },
    ]
    gerrit.finalizedTaskIds = ['task-old']
    tasks.taskStreams = {
      'task-old': [
        { type: 'task.completed', payload: { llm_response: '# old' }, ts: 1 },
      ],
    }

    gerrit.init()
    tasks.taskStreams = {
      ...tasks.taskStreams,
      'task-old': [
        { type: 'task.completed', payload: { llm_response: '# old' }, ts: 1 },
      ],
    }

    expect(gerrit.runningTaskId).toBe('pending')
    expect(gerrit.sending).toBe(true)
  })

  it('isRunning is false when task completed but runningTaskId was not cleared', () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    gerrit.activeTaskId = 'task-gerrit-stale-run'
    gerrit.runningTaskId = 'task-gerrit-stale-run'
    gerrit.chatMessages = [
      { id: 'u1', role: 'user', content: 'review' },
      { id: 'a1', role: 'assistant', content: '# done', taskId: 'task-gerrit-stale-run' },
    ]
    tasks.taskStreams = {
      'task-gerrit-stale-run': [
        { type: 'task.completed', payload: { llm_response: '# done', p0_items: ['USB 插拔'] }, ts: 1 },
      ],
    }

    expect(gerrit.isRunning).toBe(false)
  })

  it('isServerRecommending is true during RECOMMENDING phase before completion', () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    gerrit.activeTaskId = 'task-gerrit-rec-phase'
    gerrit.runningTaskId = 'task-gerrit-rec-phase'
    tasks.taskStreams = {
      'task-gerrit-rec-phase': [
        { type: 'task.phase', payload: { phase: 'RECOMMENDING', message: '正在推荐测试用例…' }, ts: 1 },
      ],
    }

    expect(gerrit.isServerRecommending).toBe(true)
  })

  it('loads recommended cases when terminal exists but runningTaskId stuck', async () => {
    const gerrit = useGerritReviewStore()
    const tasks = useTahpTasksStore()

    fetchRecommendCasesMock.mockResolvedValueOnce({
      recommended_cases: [
        {
          caseKey: 'week/driver/14',
          caseName: 'USB功能正常充电',
          moduleLabel: '驱动',
          score: 2,
          reasons: ['USB'],
        },
      ],
      source: 'llm',
    })

    gerrit.activeTaskId = 'task-gerrit-rec-stuck'
    gerrit.runningTaskId = 'task-gerrit-rec-stuck'
    gerrit.serverP0Items = ['USB 插拔']
    gerrit.chatMessages = [
      { id: 'u1', role: 'user', content: 'review' },
      { id: 'a1', role: 'assistant', content: '# done', taskId: 'task-gerrit-rec-stuck' },
    ]
    tasks.taskStreams = {
      'task-gerrit-rec-stuck': [
        {
          type: 'task.completed',
          payload: {
            llm_response: '### P0 - 必须测试\n1. USB 插拔',
            p0_items: ['USB 插拔'],
            recommended_cases: [],
          },
          ts: 1,
        },
      ],
    }

    expect(gerrit.isRunning).toBe(false)
    await gerrit.ensureRecommendedCases()

    expect(fetchRecommendCasesMock).toHaveBeenCalled()
    expect(gerrit.recommendedCases).toHaveLength(1)
  })
})
