import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mkdtempSync, writeFileSync, rmSync, existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { buildFailureBundle } from '../../packages/server/src/services/tahp/selfcheck-failure-bundle'

let reportDir: string

beforeEach(() => {
  reportDir = mkdtempSync(join(tmpdir(), 'bundle-test-'))
})

afterEach(() => {
  rmSync(reportDir, { recursive: true, force: true })
})

describe('buildFailureBundle', () => {
  it('returns null when no detail.json', async () => {
    const result = await buildFailureBundle(reportDir)
    expect(result).toBeNull()
  })

  it('returns null when no failed cases', async () => {
    writeFileSync(
      join(reportDir, 'detail.json'),
      JSON.stringify({ failedCaseItems: [] }),
    )
    const result = await buildFailureBundle(reportDir)
    expect(result).toBeNull()
  })

  it('creates bundle with failed cases', async () => {
    const failedCases = [
      { caseKey: 'week/tdd/1', caseName: '拨号测试', module: 'tdd', status: '失败', message: '超时' },
      { caseKey: 'week/tdd/2', caseName: 'SMS 测试', module: 'tdd', status: '失败', message: '无信号' },
    ]
    writeFileSync(
      join(reportDir, 'detail.json'),
      JSON.stringify({ failedCaseItems: failedCases }),
    )

    const result = await buildFailureBundle(reportDir)
    expect(result).not.toBeNull()
    expect(result!.dir).toContain('failure-bundle')
    expect(result!.description).toContain('拨号测试')
    expect(result!.description).toContain('2 条失败用例')

    const bundledCases = JSON.parse(readFileSync(join(result!.dir, 'failed-cases.json'), 'utf-8'))
    expect(bundledCases).toHaveLength(2)
    expect(bundledCases[0].caseKey).toBe('week/tdd/1')

    expect(existsSync(join(result!.dir, 'README.md'))).toBe(true)
  })

  it('copies log files if present', async () => {
    writeFileSync(
      join(reportDir, 'detail.json'),
      JSON.stringify({ failedCaseItems: [{ caseKey: 'a', caseName: 'a', module: 'a', status: '失败', message: 'x' }] }),
    )
    writeFileSync(join(reportDir, 'logcat.txt'), 'log content')

    const result = await buildFailureBundle(reportDir)
    expect(result).not.toBeNull()
    expect(existsSync(join(result!.dir, 'logcat.txt'))).toBe(true)
    expect(readFileSync(join(result!.dir, 'logcat.txt'), 'utf-8')).toBe('log content')
  })
})
