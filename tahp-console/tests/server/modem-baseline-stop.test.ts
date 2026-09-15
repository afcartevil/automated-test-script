import fs from 'fs'
import path from 'path'
import { afterEach, describe, expect, it } from 'vitest'
import { config as serverConfig } from '../../packages/server/src/config'
import {
  describeModemRunFailure,
  readModemBaselineRun,
  stopModemBaselineRun,
} from '../../packages/server/src/services/tahp/modem-baseline'

const createdRunDirs: string[] = []

function writeFakeRunningMeta(runId: string, status: 'running' | 'failed' | 'success' = 'running') {
  const runDir = path.resolve(serverConfig.dataDir, 'modem-baseline', 'runs', runId)
  const logDir = path.resolve(runDir, 'logs')
  fs.mkdirSync(logDir, { recursive: true })
  createdRunDirs.push(runDir)
  const logPath = path.resolve(logDir, 'runtime.log.txt')
  fs.writeFileSync(logPath, '', 'utf-8')
  const meta = {
    runId,
    status,
    mode: 'stop_after_merge',
    phase: 'merge',
    createdAt: new Date().toISOString(),
    startedAt: new Date().toISOString(),
    config: {
      NODE_BRANCH: 'master',
      target_BRANCH: 'PRODUCT_U_u0mp1rc_NR17_common',
      AP_lable: 'V1.0',
      JIRAID: 'AR-TEST',
      work_dir: 'Z:\\fake',
    },
    logPath,
  }
  fs.writeFileSync(path.resolve(runDir, 'meta.json'), JSON.stringify(meta, null, 2), 'utf-8')
  return meta
}

afterEach(() => {
  while (createdRunDirs.length) {
    const dir = createdRunDirs.pop()
    if (!dir) continue
    fs.rmSync(dir, { recursive: true, force: true })
  }
})

describe('stopModemBaselineRun', () => {
  it('marks running run as failed with stopped_by_user', () => {
    const runId = `stop-test-${Date.now()}-a`
    writeFakeRunningMeta(runId, 'running')
    const result = stopModemBaselineRun(runId)
    expect(result.status).toBe('failed')
    expect(result.error).toBe('stopped_by_user')
    const meta = readModemBaselineRun(runId)
    expect(meta?.status).toBe('failed')
    expect(meta?.error).toBe('stopped_by_user')
    expect(meta?.finishedAt).toBeTruthy()
    const log = fs.readFileSync(meta!.logPath!, 'utf-8')
    expect(log).toContain('stopped_by_user')
  })

  it('throws not_running for non-running runs', () => {
    const runId = `stop-test-${Date.now()}-b`
    writeFakeRunningMeta(runId, 'failed')
    expect(() => stopModemBaselineRun(runId)).toThrow('not_running')
  })

  it('throws not_found for missing runs', () => {
    expect(() => stopModemBaselineRun('missing-run-id-xyz')).toThrow('not_found')
  })
})

describe('describeModemRunFailure stopped_by_user', () => {
  it('returns human-readable stop message', () => {
    expect(describeModemRunFailure('stopped_by_user')).toMatch(/手动停止/)
  })
})
