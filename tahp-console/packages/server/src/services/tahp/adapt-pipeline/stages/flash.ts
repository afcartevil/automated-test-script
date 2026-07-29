import { registerStageForTest } from '../registry'
import type { StageContext, StageDefinition, StageVerdict } from '../types'
import {
  resolveFlashPkgPath,
  validateFlashPkgPath,
} from '../../flash-artifact-resolver'
import {
  runDeviceFlash,
  waitForAdbDevice,
  type DeviceFlashResult,
} from '../../device-flash'

let flashPromise: Promise<DeviceFlashResult> | null = null

export const flashStageDefinition: StageDefinition = {
  key: 'flash',
  label: '烧录',
  consumes: ['build'],
  produces: ['flashed'],

  async probe() {
    try {
      const { resolveDeviceUpdateExe } = await import('../../device-flash')
      const exe = resolveDeviceUpdateExe()
      const { existsSync } = await import('node:fs')
      if (!existsSync(exe)) {
        return { available: false, reason: `device_update 不存在: ${exe}` }
      }
      return { available: true }
    } catch {
      return { available: false, reason: '刷机工具检测失败' }
    }
  },

  async start(ctx: StageContext) {
    const buildSummary = ctx.run.stages.build?.summary as Record<string, unknown> | undefined
    const artifactsDir = buildSummary?.artifacts_dir as string | undefined
    const mappedRoot = ctx.run.build_context?.mapped_root

    let pkgPath = resolveFlashPkgPath(artifactsDir, mappedRoot)

    // Check if human provided a path via action payload
    const humanPkg = ctx.state.progress?.human_pkg_path as string | undefined
    if (humanPkg) pkgPath = humanPkg

    if (!pkgPath) {
      ctx.patchState({
        progress: { state: 'waiting_pkg', message: '无法自动定位刷机包，请手工选择' },
      })
      return
    }

    const validation = validateFlashPkgPath(pkgPath)
    if (!validation.valid) {
      ctx.patchState({
        progress: { state: 'waiting_pkg', message: validation.reason },
      })
      return
    }

    const deviceId = ctx.run.device_id
    if (!deviceId) {
      ctx.patchState({
        progress: { state: 'error', error: '未配置设备 ID' },
      })
      return
    }

    ctx.patchState({
      progress: { state: 'flashing', phase: 'flash', pkgPath },
    })
    ctx.log(`开始刷机: ${pkgPath} → ${deviceId}`)

    flashPromise = runDeviceFlash([deviceId], { pkgPath }, (line) => ctx.log(line))
    try {
      const result = await flashPromise
      flashPromise = null

      if (result.success) {
        ctx.log('刷机完成，等待设备重启…')
        ctx.patchState({ progress: { state: 'waiting_boot', phase: 'reboot' } })
        try {
          await waitForAdbDevice(deviceId, 120_000)
          ctx.patchState({
            progress: { state: 'success' },
            summary: { pkgPath, returnCode: result.returnCode },
          })
          ctx.log('设备已就绪')
        } catch {
          ctx.patchState({
            progress: { state: 'success' },
            summary: { pkgPath, returnCode: result.returnCode, rebootTimeout: true },
          })
          ctx.log('设备重启等待超时，但刷机本身成功')
        }
      } else {
        ctx.patchState({
          progress: {
            state: 'failed',
            error: result.error ?? `刷机失败 (exit ${result.returnCode})`,
          },
        })
      }
    } catch (err) {
      flashPromise = null
      ctx.patchState({
        progress: { state: 'failed', error: String(err) },
      })
    }
  },

  evaluate(ctx: StageContext): StageVerdict {
    const p = ctx.state.progress as Record<string, unknown> | undefined
    const state = p?.state as string | undefined

    if (state === 'waiting_pkg') {
      return {
        status: 'waiting_human',
        reason: 'flash_pkg_missing',
        message: String(p?.message ?? '请手工选择刷机包路径'),
        actions: [
          { id: 'provide_pkg', label: '指定刷机包路径', fields: [
            { name: 'pkg_path', label: '刷机包路径', required: true, placeholder: 'Z:\\out\\...' },
          ]},
          { id: 'skip', label: '跳过烧录', danger: true },
        ],
      }
    }

    if (state === 'success') {
      return { status: 'done', summary: (p?.summary ?? {}) as Record<string, unknown> }
    }

    if (state === 'failed' || state === 'error') {
      return {
        status: 'failed',
        error: String(p?.error ?? '烧录失败'),
        retryable: true,
      }
    }

    return {
      status: 'running',
      progress: { text: String(p?.phase ?? '准备中') },
    }
  },

  async handleHumanAction(ctx: StageContext, actionId: string, payload?: Record<string, unknown>) {
    if (actionId === 'provide_pkg') {
      const pkgPath = payload?.pkg_path as string | undefined
      if (pkgPath) {
        ctx.patchState({ progress: { human_pkg_path: pkgPath } })
      }
    }
  },

  async cancel() {
    const { stopActiveFlash } = await import('../../device-flash')
    stopActiveFlash()
    flashPromise = null
  },
}

export function installFlashStage(): void {
  registerStageForTest(flashStageDefinition)
}

installFlashStage()
