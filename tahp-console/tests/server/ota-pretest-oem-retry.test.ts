import { describe, expect, it, vi } from 'vitest'
import {
  runOemUnlockWithRetry,
  type OemUnlockRetryDeps,
} from '../../packages/server/src/services/tahp/ota-pretest'

function makeDeps(overrides: Partial<OemUnlockRetryDeps> = {}) {
  const logs: string[] = []
  const sleeps: number[] = []
  const runUnlock = overrides.runUnlock ?? vi.fn(async () => {})
  const isUnlocked = overrides.isUnlocked ?? vi.fn(async () => false)
  const deps: OemUnlockRetryDeps = {
    runUnlock,
    isUnlocked,
    onLog: line => { logs.push(line) },
    maxAttempts: overrides.maxAttempts ?? 3,
    retryDelayMs: overrides.retryDelayMs ?? 30_000,
    sleep: async (ms) => { sleeps.push(ms) },
  }
  return { deps, logs, sleeps, runUnlock, isUnlocked }
}

describe('ota-pretest runOemUnlockWithRetry', () => {
  it('首次成功：不重试、不复查解锁状态', async () => {
    const { deps, runUnlock, isUnlocked, sleeps } = makeDeps()
    await runOemUnlockWithRetry(deps)
    expect(runUnlock).toHaveBeenCalledTimes(1)
    expect(isUnlocked).not.toHaveBeenCalled()
    expect(sleeps).toHaveLength(0)
  })

  it('前两次失败第三次成功：共 3 次尝试，重试前等待并复查', async () => {
    let calls = 0
    const { deps, runUnlock, isUnlocked, sleeps, logs } = makeDeps({
      runUnlock: vi.fn(async () => {
        calls += 1
        if (calls < 3) throw new Error('前置操作失败，退出码 1')
      }),
    })
    await runOemUnlockWithRetry(deps)
    expect(runUnlock).toHaveBeenCalledTimes(3)
    expect(isUnlocked).toHaveBeenCalledTimes(2)
    expect(sleeps).toEqual([30_000, 30_000])
    expect(logs.some(l => l.includes('第 2/3 次尝试'))).toBe(true)
    expect(logs.some(l => l.includes('第 3/3 次尝试'))).toBe(true)
  })

  it('全部失败：抛出最后一次错误', async () => {
    const { deps, runUnlock } = makeDeps({
      runUnlock: vi.fn(async () => { throw new Error('前置操作失败，退出码 1') }),
    })
    await expect(runOemUnlockWithRetry(deps)).rejects.toThrow('前置操作失败，退出码 1')
    expect(runUnlock).toHaveBeenCalledTimes(3)
  })

  it('重试前复查已解锁：跳过后续尝试（服务器实际已解锁但响应解析失败）', async () => {
    let calls = 0
    const { deps, runUnlock, logs } = makeDeps({
      runUnlock: vi.fn(async () => {
        calls += 1
        if (calls === 1) throw new Error('OEM Unlock failed: no valid response')
      }),
      isUnlocked: vi.fn(async () => true),
    })
    await runOemUnlockWithRetry(deps)
    expect(runUnlock).toHaveBeenCalledTimes(1)
    expect(logs.some(l => l.includes('复查设备已解锁，跳过重试'))).toBe(true)
  })

  it('maxAttempts=1：失败不重试', async () => {
    const { deps, runUnlock, sleeps } = makeDeps({
      maxAttempts: 1,
      runUnlock: vi.fn(async () => { throw new Error('exit 1') }),
    })
    await expect(runOemUnlockWithRetry(deps)).rejects.toThrow('exit 1')
    expect(runUnlock).toHaveBeenCalledTimes(1)
    expect(sleeps).toHaveLength(0)
  })
})
