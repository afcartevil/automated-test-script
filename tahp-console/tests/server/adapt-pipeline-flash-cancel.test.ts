import { existsSync, mkdtempSync, rmSync, writeFileSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  failCurrentStageToHuman,
  resetOrchestratorForTest,
  startRun,
  submitHumanAction,
} from '../../packages/server/src/services/tahp/adapt-pipeline/orchestrator'
import { resetRegistryForTest } from '../../packages/server/src/services/tahp/adapt-pipeline/registry'
import {
  createRun,
  getRun,
  resetStoreForTest,
} from '../../packages/server/src/services/tahp/adapt-pipeline/store'
import { resetSourcesForTest } from '../../packages/server/src/services/tahp/adapt-pipeline/sources'
import { installFlashStage } from '../../packages/server/src/services/tahp/adapt-pipeline/stages/flash'
import { setWorkflowOverrideForTest } from '../../packages/server/src/services/tahp/adapt-pipeline/workflow'
import * as deviceFlash from '../../packages/server/src/services/tahp/device-flash'
import * as harnessFlash from '../../packages/server/src/services/tahp/adapt-pipeline/harness-flash-capability'

describe('flash fail-current-stage', () => {
  let tempDir = ''

  beforeEach(() => {
    tempDir = mkdtempSync(join(tmpdir(), 'ap-flash-cancel-'))
    process.env.TAHP_ADAPT_PIPELINE_DIR = tempDir
    resetRegistryForTest()
    resetStoreForTest()
    resetOrchestratorForTest()
    resetSourcesForTest()
    setWorkflowOverrideForTest({
      id: 'flash-only',
      version: 1,
      label: 'flash-only',
      maxIterations: 1,
      nodes: [{ key: 'flash', enabled: true, onDone: 'END' }],
    })
    installFlashStage()
    vi.spyOn(harnessFlash, 'probeHarnessFlash').mockResolvedValue({
      available: false,
      reason: 'test',
    })
    vi.spyOn(harnessFlash, 'cancelHarnessFlash').mockResolvedValue()
    vi.spyOn(deviceFlash, 'runDeviceFlash').mockReturnValue(new Promise(() => {}))
    vi.spyOn(deviceFlash, 'stopActiveFlash').mockReturnValue(true)
    vi.spyOn(deviceFlash, 'resolveDeviceUpdateExe').mockReturnValue(join(tempDir, 'device_update.exe'))
    writeFileSync(join(tempDir, 'device_update.exe'), 'x')
  })

  afterEach(() => {
    vi.restoreAllMocks()
    resetOrchestratorForTest()
    resetRegistryForTest()
    resetStoreForTest()
    resetSourcesForTest()
    setWorkflowOverrideForTest(null)
    delete process.env.TAHP_ADAPT_PIPELINE_DIR
    if (tempDir && existsSync(tempDir)) rmSync(tempDir, { recursive: true, force: true })
  })

  it('startRun returns while device_update is still running; stop parks without abort', async () => {
    const pkg = join(tempDir, 'rom.zip')
    writeFileSync(pkg, 'rom')
    const run = createRun({
      project_code: 'KM9',
      device_id: 'SN1',
      build_context: {
        mapped_root: '',
        workspace: '',
        variant: 'userdebug',
        flash_pkg_path: pkg,
      },
    })

    const started = Date.now()
    await startRun(run.run_id)
    await new Promise<void>(resolve => setImmediate(resolve))
    expect(Date.now() - started).toBeLessThan(2000)
    expect(getRun(run.run_id)?.status).toBe('running')
    expect(getRun(run.run_id)?.current_node).toBe('flash')
    expect(deviceFlash.runDeviceFlash).toHaveBeenCalled()

    await failCurrentStageToHuman(run.run_id)
    expect(deviceFlash.stopActiveFlash).toHaveBeenCalled()
    const updated = getRun(run.run_id)!
    expect(updated.status).toBe('waiting_human')
    expect(updated.stages.flash?.human?.reason).toBe('stage_failed')
    expect(updated.abort_reason).toBeUndefined()
  })

  it('provide_pkg after waiting_artifact still launches device_update', async () => {
    const run = createRun({
      project_code: 'KM9',
      device_id: 'SN1',
      build_context: {
        mapped_root: '',
        workspace: '',
        variant: 'userdebug',
      },
    })
    await startRun(run.run_id)
    expect(getRun(run.run_id)?.stages.flash?.status).toBe('waiting_human')

    const pkg = join(tempDir, 'rom.zip')
    writeFileSync(pkg, 'rom')
    await submitHumanAction(run.run_id, 'flash', 'provide_pkg', { pkg_path: pkg })
    await new Promise<void>(resolve => setImmediate(resolve))
    expect(deviceFlash.runDeviceFlash).toHaveBeenCalled()
    expect(getRun(run.run_id)?.status).toBe('running')
  })
})
