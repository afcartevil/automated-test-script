import { mkdtempSync, readFileSync, rmSync, writeFileSync, mkdirSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const callTahpLLMMock = vi.fn()

vi.mock('../../packages/server/src/services/tahp/llm-caller', () => ({
  callTahpLLM: (...args: unknown[]) => callTahpLLMMock(...args),
}))

vi.mock('../../packages/server/src/services/logger', () => ({
  logger: { warn: vi.fn(), info: vi.fn(), error: vi.fn() },
}))

import { applyMonkeyCheckAiReport } from '../../packages/server/src/services/tahp/monkey-tne-report'

function makeSessionDir(payload?: object): string {
  const dir = mkdtempSync(join(tmpdir(), 'monkey-check-'))
  if (payload) {
    const sub = join(dir, 'monkey_check')
    mkdirSync(sub, { recursive: true })
    writeFileSync(join(sub, 'result.json'), JSON.stringify(payload), 'utf-8')
  }
  return dir
}

describe('monkey-tne-report applyMonkeyCheckAiReport', () => {
  let workDir = ''

  beforeEach(() => {
    callTahpLLMMock.mockReset()
  })

  afterEach(() => {
    if (workDir) rmSync(workDir, { recursive: true, force: true })
    workDir = ''
  })

  it('composes summary + AI module breakdown', async () => {
    callTahpLLMMock.mockResolvedValue('["audio","display"]')
    workDir = makeSessionDir({
      version: 1,
      tne_remote_dir: '/data/TNE/0xffff',
      counts: { '0xffffff39': 2, '0xffffff04': 1 },
      native_crashes: [
        { tne_name: '0xffffff39_2026_09_21_10_00_00.tne', crash_log_found: true, excerpt: 'crash A excerpt' },
        { tne_name: '0xffffff39_2026_09_20_08_00_00.tne', crash_log_found: true, excerpt: 'crash B excerpt' },
      ],
      errors: [],
    })
    const result = { message: '原始 message' }

    await applyMonkeyCheckAiReport(workDir, result)

    expect(callTahpLLMMock).toHaveBeenCalledTimes(1)
    expect(result.message).toContain('发现 native crash 2次，KE 1次')
    expect(result.message).toContain('native crash audio 1次，display 1次')
    // 按模块贴出对应 tne log 设备侧路径
    expect(result.message).toContain('[audio] /data/TNE/0xffff/0xffffff39_2026_09_21_10_00_00.tne')
    expect(result.message).toContain('[display] /data/TNE/0xffff/0xffffff39_2026_09_20_08_00_00.tne')
    const reportTxt = readFileSync(join(workDir, 'monkey_check', 'monkey_check_report.txt'), 'utf-8')
    expect(reportTxt).toContain('audio 1次')
    expect(reportTxt).toContain('/data/TNE/0xffff/0xffffff39_2026_09_21_10_00_00.tne')
  })

  it('pastes only the latest 5 tne log paths per module when exceeding 5', async () => {
    const names = [
      '0xffffff39_2026_09_10_01_00_00.tne',
      '0xffffff39_2026_09_11_01_00_00.tne',
      '0xffffff39_2026_09_12_01_00_00.tne',
      '0xffffff39_2026_09_13_01_00_00.tne',
      '0xffffff39_2026_09_14_01_00_00.tne',
      '0xffffff39_2026_09_15_01_00_00.tne',
      '0xffffff39_2026_09_16_01_00_00.tne',
    ]
    callTahpLLMMock.mockResolvedValue('["audio","audio","audio","audio","audio","audio","audio"]')
    workDir = makeSessionDir({
      version: 1,
      tne_remote_dir: '/data/TNE/0xffff',
      counts: { '0xffffff39': 7 },
      native_crashes: names.map(tne_name => ({ tne_name, crash_log_found: true, excerpt: 'x' })),
      errors: [],
    })
    const result = { message: '' }

    await applyMonkeyCheckAiReport(workDir, result)

    expect(result.message).toContain('native crash audio 7次')
    const pathLines = result.message.split('\n').filter(l => l.includes('[audio] /data/TNE/0xffff/'))
    expect(pathLines).toHaveLength(5)
    // 只贴最近 5 份：09-12 .. 09-16，不含 09-10 / 09-11
    expect(result.message).toContain('0xffffff39_2026_09_16_01_00_00.tne')
    expect(result.message).toContain('0xffffff39_2026_09_12_01_00_00.tne')
    expect(result.message).not.toContain('0xffffff39_2026_09_11_01_00_00.tne')
    expect(result.message).not.toContain('0xffffff39_2026_09_10_01_00_00.tne')
    // 最近时间在前
    expect(pathLines[0]).toContain('09_16')
    expect(pathLines[4]).toContain('09_12')
    expect(result.message).toContain('共 7 份，仅贴出最近 5 份')
  })

  it('degrades gracefully when AI unavailable', async () => {
    callTahpLLMMock.mockRejectedValue(new Error('LLM 配置解析失败'))
    workDir = makeSessionDir({
      version: 1,
      counts: { '0xffffff39': 1 },
      native_crashes: [
        { tne_name: 'a.tne', crash_log_found: true, excerpt: 'crash A excerpt' },
      ],
      errors: [],
    })
    const result = { message: '原始 message' }

    await applyMonkeyCheckAiReport(workDir, result)

    expect(result.message).toContain('发现 native crash 1次')
    expect(result.message).toContain('AI 模块归类不可用')
  })

  it('keeps original message when result.json missing', async () => {
    workDir = makeSessionDir()
    const result = { message: '原始 message' }

    await applyMonkeyCheckAiReport(workDir, result)

    expect(callTahpLLMMock).not.toHaveBeenCalled()
    expect(result.message).toBe('原始 message')
  })

  it('reports 未发现 when counts empty', async () => {
    workDir = makeSessionDir({
      version: 1,
      counts: {},
      native_crashes: [],
      errors: [],
    })
    const result = { message: '原始 message' }

    await applyMonkeyCheckAiReport(workDir, result)

    expect(callTahpLLMMock).not.toHaveBeenCalled()
    expect(result.message).toBe('未发现 KE/NE 等异常 log')
  })
})
