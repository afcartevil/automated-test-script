import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import {
  AGENT_INSTRUCTIONS_BASE,
  formatLogDownloadProgressActivity,
} from '../../packages/server/src/services/tahp/bug-analysis'

describe('bug analysis log download timeout', () => {
  it('requires waiting for jira-ops download process exit instead of a 300s wall clock', () => {
    expect(AGENT_INSTRUCTIONS_BASE).toMatch(/禁止用固定墙钟（如 300s）/)
    expect(AGENT_INSTRUCTIONS_BASE).toMatch(/prepare-logs/)
    expect(AGENT_INSTRUCTIONS_BASE).toMatch(/进程退出并给出 JSON/)
  })
})

describe('bug analysis log download progress activity', () => {
  it('keeps jira-ops download progress lines for the UI log', () => {
    expect(formatLogDownloadProgressActivity(
      '下载进度: 24.1% (1.65 GB/6.84 GB) 速度: 870.3 KB/s 剩余: 1h 42m',
    )).toContain('24.1%')
    expect(formatLogDownloadProgressActivity('开始流式下载...')).toBe('开始流式下载...')
    expect(formatLogDownloadProgressActivity('ls -la /tmp')).toBeNull()
    expect(formatLogDownloadProgressActivity('')).toBeNull()
  })

  it('forwards tool.output from the Hermes bridge', () => {
    const src = readFileSync(
      resolve('packages/server/src/services/hermes/agent-bridge/hermes_bridge.py'),
      'utf8',
    )
    expect(src).toContain('"event": "tool.output"')
  })
})
