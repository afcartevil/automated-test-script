import { describe, expect, it } from 'vitest'
import {
  buildBugActivityLog,
  formatBugActivityLine,
  lastBugActivityHint,
  shouldSuppressBugInteractionModal,
} from '../../packages/client/src/utils/bug-analysis-activity'

describe('bug-analysis-activity', () => {
  it('formats tool and phase events', () => {
    const line = formatBugActivityLine({
      type: 'task.skill_use',
      ts: Date.UTC(2026, 0, 1, 8, 30, 5),
      payload: { skill_id: 'jira-ops', message: 'get-issue OS162-1' },
    })
    expect(line).toMatch(/调用 jira-ops/)
    expect(line).toMatch(/\[\d{2}:\d{2}:\d{2}\]/)
  })

  it('builds chronological activity log', () => {
    const log = buildBugActivityLog([
      {
        type: 'task.phase',
        ts: 1,
        payload: { phase: 'ANALYZING', message: 'Agent 执行中' },
      },
      {
        type: 'task.skill_use',
        ts: 2,
        payload: { skill_id: 'Bash', message: 'python scripts/api_jira.py' },
      },
    ])
    expect(log).toContain('分析中')
    expect(log).toContain('Bash')
  })

  it('returns last activity hint', () => {
    const hint = lastBugActivityHint([
      { type: 'task.phase', ts: 1, payload: { phase: 'PREPARING', message: '准备' } },
      { type: 'task.message', ts: 2, payload: { level: 'activity', text: '正在调用工具 Read' } },
    ])
    expect(hint).toBe('正在调用工具 Read')
  })

  it('suppresses approval and LogInsight LLM key modals', () => {
    expect(shouldSuppressBugInteractionModal({
      type: 'task.approval_requested',
      payload: { command: 'rm -rf /tmp' },
    })).toBe(true)
    expect(shouldSuppressBugInteractionModal({
      type: 'task.user_input_requested',
      payload: {
        title: 'LogInsight LLM API Key',
        fields: [{ name: 'llm_api_key', label: 'API Key' }],
      },
    })).toBe(true)
    expect(shouldSuppressBugInteractionModal({
      type: 'task.user_input_requested',
      payload: {
        title: '日志保存目录',
        fields: [{ name: 'log_dir', label: '日志目录' }],
      },
    })).toBe(false)
  })

  it('does not print waiting-for-approval in activity log', () => {
    const log = buildBugActivityLog([
      {
        type: 'task.approval_requested',
        ts: 1,
        payload: { command: 'dangerous' },
      },
      {
        type: 'task.approval_resolved',
        ts: 2,
        payload: { message: '危险命令已由智能诊断后台自动同意一次' },
      },
    ])
    expect(log).not.toContain('等待命令确认')
    expect(log).toContain('已由智能诊断后台自动同意一次')
  })

  it('shows live download progress in the activity log', () => {
    const line = formatBugActivityLine({
      type: 'task.message',
      ts: Date.UTC(2026, 8, 1, 6, 52, 0),
      payload: {
        level: 'activity',
        text: '下载进度: 24.1% (1.65 GB/6.84 GB) 速度: 870.3 KB/s 剩余: 1h 42m',
      },
    })
    expect(line).toContain('下载进度: 24.1%')
  })
})
