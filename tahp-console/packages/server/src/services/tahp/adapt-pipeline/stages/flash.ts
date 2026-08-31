import { existsSync } from 'node:fs'
import { registerStageForTest } from '../registry'
import type { StageContext, StageDefinition, StageVerdict } from '../types'
import {
  validateFlashPkgPath,
} from '../../flash-artifact-resolver'
import {
  runDeviceFlash,
  waitForAdbDevice,
  type DeviceFlashResult,
} from '../../device-flash'
import {
  classifyFlashArtifacts,
  type FlashArtifactClassification,
} from '../flash-artifact-classify'
import {
  probeHarnessFlash,
  runHarnessFlash,
} from '../harness-flash-capability'
import { defaultFlashSkillId } from '../harness-skill-registry'

let flashPromise: Promise<DeviceFlashResult> | null = null
let harnessBusy = false

function collectBuildArtifacts(ctx: StageContext) {
  const buildSummary = ctx.run.stages.build?.summary as Record<string, unknown> | undefined
  const buildProgress = ctx.run.stages.build?.progress as Record<string, unknown> | undefined
  const buildResult = (buildProgress?.result ?? {}) as Record<string, unknown>
  const artifactsDir = (buildSummary?.artifacts_dir
    ?? buildResult.artifactsDir
    ?? buildResult.artifacts_dir) as string | undefined
  const preferredPkg = (buildSummary?.pkg_path
    ?? buildResult.pkgPath
    ?? buildResult.pkg_path) as string | undefined
  const artifacts = (buildSummary?.artifacts ?? buildResult.artifacts) as
    | Array<{ name?: string; path: string }>
    | undefined
  const resolved = preferredPkg || undefined
  const humanPkg = ctx.state.progress?.human_pkg_path as string | undefined
  const contextPkg = String(ctx.run.build_context?.flash_pkg_path ?? '').trim() || undefined
  const humanImg = ctx.state.progress?.human_img_path as string | undefined
  const humanPartition = ctx.state.progress?.human_partition as string | undefined
  return {
    pkgPath: humanPkg || resolved || contextPkg,
    artifactsDir,
    artifacts,
    humanImg,
    partitionHint: humanPartition || (ctx.run.build_context as { flash_partition?: string } | undefined)?.flash_partition,
  }
}

function classifyFromCtx(ctx: StageContext): FlashArtifactClassification {
  const c = collectBuildArtifacts(ctx)
  if (c.humanImg) {
    return classifyFlashArtifacts({
      pkgPath: c.humanImg,
      partitionHint: c.partitionHint,
    })
  }
  return classifyFlashArtifacts({
    pkgPath: c.pkgPath,
    artifactsDir: c.artifactsDir,
    artifacts: c.artifacts,
    partitionHint: c.partitionHint,
  })
}

async function markSuccess(ctx: StageContext, pkgPath: string, via: string, returnCode = 0) {
  const deviceId = ctx.run.device_id
  ctx.log(`刷机完成（${via}），等待设备重启…`)
  ctx.patchState({ progress: { state: 'waiting_boot', phase: 'reboot', via, pkg_path: pkgPath } })
  if (deviceId) {
    try {
      await waitForAdbDevice(deviceId, 120_000)
      ctx.patchState({
        progress: { state: 'success', via },
        summary: { pkgPath, returnCode, via },
      })
      ctx.log('设备已就绪')
      return
    } catch {
      ctx.log('设备重启等待超时，但刷机本身成功')
    }
  }
  ctx.patchState({
    progress: { state: 'success', via },
    summary: { pkgPath, returnCode, via, rebootTimeout: true },
  })
}

function resolveFlashSkillId(ctx: StageContext): string {
  return ctx.run.build_context?.flash_skill_id?.trim() || defaultFlashSkillId()
}

async function runDeviceUpdateFlash(
  ctx: StageContext,
  pkgPath: string,
  deviceId: string,
  phase: string,
  priorHarnessError?: string,
): Promise<boolean> {
  let deviceUpdateAvailable = false
  try {
    const { resolveDeviceUpdateExe } = await import('../../device-flash')
    deviceUpdateAvailable = existsSync(resolveDeviceUpdateExe())
  } catch { /* ignore */ }

  if (!deviceUpdateAvailable) {
    const harnessPart = priorHarnessError
      ? `harness 失败: ${priorHarnessError}；`
      : ''
    ctx.patchState({
      progress: {
        state: 'failed',
        error: `${harnessPart}device_update 不可用`,
        via: priorHarnessError ? resolveFlashSkillId(ctx) : 'device_update',
      },
    })
    return false
  }

  ctx.patchState({
    progress: {
      state: 'flashing',
      phase,
      pkg_path: pkgPath,
      message: priorHarnessError ? 'harness 失败，降级 device_update' : 'device_update 刷写整包',
      harness_error: priorHarnessError,
      text: pkgPath,
    },
  })
  const logPrefix = priorHarnessError ? 'harness 刷机失败，降级 device_update' : '开始刷机(device_update)'
  ctx.log(`${logPrefix}: ${pkgPath} → ${deviceId}`)

  flashPromise = runDeviceFlash([deviceId], { pkgPath }, line => ctx.log(line))
  try {
    const result = await flashPromise
    flashPromise = null
    if (result.success) {
      await markSuccess(ctx, pkgPath, 'device_update', result.returnCode)
      return true
    }
    const flashSkillId = resolveFlashSkillId(ctx)
    const err = priorHarnessError
      ? `harness (${flashSkillId}) 与 device_update 均失败: ${result.error ?? `exit ${result.returnCode}`}`
      : (result.error ?? `device_update 失败 (exit ${result.returnCode})`)
    ctx.patchState({
      progress: {
        state: 'failed',
        error: err,
        via: 'device_update',
      },
    })
    return false
  } catch (err) {
    flashPromise = null
    ctx.patchState({
      progress: { state: 'failed', error: String(err) },
    })
    return false
  }
}

async function runHarnessFullRomFlash(
  ctx: StageContext,
  pkgPath: string,
  deviceId: string,
  flashSkillId: string,
): Promise<{ success: boolean; error?: string }> {
  ctx.patchState({
    progress: {
      state: 'flashing',
      phase: 'harness',
      skill_id: flashSkillId,
      pkg_path: pkgPath,
      message: `${flashSkillId} 刷写整包`,
      text: pkgPath,
    },
  })
  ctx.log(`开始刷机(harness): skill=${flashSkillId} ${pkgPath} → ${deviceId}`)
  harnessBusy = true
  try {
    const result = await runHarnessFlash({
      pipelineRunId: ctx.run.run_id,
      mode: 'full_rom',
      deviceId,
      romPath: pkgPath,
      variant: ctx.run.build_context?.variant,
      flashSkillId,
    }, line => ctx.log(line))
    return { success: result.success, error: result.error }
  } finally {
    harnessBusy = false
  }
}

export const flashStageDefinition: StageDefinition = {
  key: 'flash',
  label: '烧录',
  consumes: ['build'],
  produces: ['flashed'],

  async probe({ run }) {
    const flashSkillId = run.build_context?.flash_skill_id?.trim() || defaultFlashSkillId()
    const harness = await probeHarnessFlash(flashSkillId)
    if (harness.available) return { available: true }
    try {
      const { resolveDeviceUpdateExe } = await import('../../device-flash')
      const exe = resolveDeviceUpdateExe()
      if (existsSync(exe)) return { available: true }
    } catch { /* fall through */ }
    return {
      available: false,
      reason: harness.reason ?? 'harness 刷机与 device_update 均不可用',
    }
  },

  async start(ctx: StageContext) {
    const manualPkg = String(ctx.run.build_context?.flash_pkg_path ?? '').trim()
    const buildState = ctx.run.stages.build
    if (!manualPkg && (buildState?.status === 'failed' || buildState?.status === 'skipped')) {
      ctx.patchState({
        progress: { state: 'error', error: '编译未成功，跳过自动烧录' },
      })
      return
    }

    const buildKind = ctx.run.build_context?.build_kind ?? 'whole_device'
    let classified = classifyFromCtx(ctx)

    // 模块编译：仅完整 ROM 或单镜像可继续；否则暂停并可跳 Gerrit
    if (classified.kind === 'none') {
      ctx.patchState({
        progress: {
          state: 'waiting_artifact',
          build_kind: buildKind,
          message: buildKind === 'native_module'
            ? '模块编译未产出完整刷机包或单个 .img，流程已暂停。可跳转 Gerrit，或手工指定包/镜像。'
            : '未识别到可刷产物，请手工指定刷机包或单镜像。',
          text: '无刷机产物',
        },
      })
      ctx.log(String((ctx.state.progress as Record<string, unknown>)?.message))
      return
    }

    if (classified.kind === 'single_img' && !classified.partition) {
      ctx.patchState({
        progress: {
          state: 'waiting_partition',
          img_path: classified.imgPath,
          message: classified.reason || '请指定单镜像目标分区',
          text: '待指定分区',
        },
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

    // —— 单镜像：固定 harness-flash-single-img ——
    if (classified.kind === 'single_img') {
      ctx.patchState({
        progress: {
          state: 'flashing',
          phase: 'harness_single_img',
          img_path: classified.imgPath,
          partition: classified.partition,
          message: `harness-flash-single-img → ${classified.partition}`,
          text: classified.imgPath,
        },
      })
      ctx.log(`单镜像刷机: ${classified.imgPath} → ${classified.partition} @ ${deviceId}`)
      harnessBusy = true
      const result = await runHarnessFlash({
        pipelineRunId: ctx.run.run_id,
        mode: 'single_img',
        deviceId,
        imgPath: classified.imgPath,
        partition: classified.partition,
        variant: ctx.run.build_context?.variant,
      }, line => ctx.log(line))
      harnessBusy = false
      if (result.success) {
        await markSuccess(ctx, classified.imgPath!, 'harness-flash-single-img')
      } else {
        ctx.patchState({
          progress: {
            state: 'failed',
            error: result.error ?? '单镜像刷机失败',
            via: 'harness-flash-single-img',
          },
        })
      }
      return
    }

    // —— 完整包：先 harness（flash_skill_id），失败再降级 device_update ——
    const pkgPath = classified.pkgPath!
    const validation = validateFlashPkgPath(pkgPath)
    if (!validation.valid) {
      ctx.patchState({
        progress: {
          state: 'waiting_artifact',
          message: validation.reason,
          text: validation.reason,
        },
      })
      return
    }

    const flashSkillId = resolveFlashSkillId(ctx)
    const harnessProbe = await probeHarnessFlash(flashSkillId)

    if (harnessProbe.available) {
      try {
        const harnessResult = await runHarnessFullRomFlash(ctx, pkgPath, deviceId, flashSkillId)
        if (harnessResult.success) {
          await markSuccess(ctx, pkgPath, flashSkillId)
          return
        }
        ctx.log(`harness 刷机失败: ${harnessResult.error ?? 'unknown'}，降级 device_update…`)
        await runDeviceUpdateFlash(
          ctx,
          pkgPath,
          deviceId,
          'device_update_fallback',
          harnessResult.error,
        )
      } catch (err) {
        harnessBusy = false
        ctx.patchState({
          progress: { state: 'failed', error: String(err) },
        })
      }
      return
    }

    ctx.log(`harness 不可用 (${harnessProbe.reason ?? 'unknown'})，使用 device_update`)
    try {
      await runDeviceUpdateFlash(ctx, pkgPath, deviceId, 'device_update')
    } catch (err) {
      ctx.patchState({
        progress: { state: 'failed', error: String(err) },
      })
    }
  },

  evaluate(ctx: StageContext): StageVerdict {
    const p = ctx.state.progress as Record<string, unknown> | undefined
    const state = p?.state as string | undefined

    if (state === 'waiting_artifact') {
      return {
        status: 'waiting_human',
        reason: 'no_flashable_artifact',
        message: String(p?.message ?? '无可刷产物'),
        actions: [
          {
            id: 'provide_pkg',
            label: '指定完整刷机包',
            fields: [{ name: 'pkg_path', label: '刷机包路径', required: true, placeholder: 'Z:\\out\\...' }],
          },
          {
            id: 'provide_single_img',
            label: '指定单镜像+分区',
            fields: [
              { name: 'img_path', label: '镜像路径(.img)', required: true },
              { name: 'partition', label: '目标分区(如 boot)', required: true },
            ],
          },
          { id: 'go_gerrit', label: '跳过烧录，前往 Gerrit' },
          { id: 'skip', label: '跳过烧录（进入下一节点）', danger: true },
        ],
      }
    }

    if (state === 'waiting_partition') {
      return {
        status: 'waiting_human',
        reason: 'need_partition',
        message: String(p?.message ?? '请指定分区'),
        actions: [
          {
            id: 'provide_single_img',
            label: '确认分区并刷入',
            fields: [
              { name: 'img_path', label: '镜像路径', required: false, placeholder: String(p?.img_path ?? '') },
              { name: 'partition', label: '目标分区', required: true },
            ],
          },
          { id: 'go_gerrit', label: '跳过烧录，前往 Gerrit' },
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
      progress: {
        ...(p ?? {}),
        text: String(p?.message ?? p?.text ?? p?.phase ?? '烧录中'),
      },
    }
  },

  async handleHumanAction(ctx: StageContext, actionId: string, payload?: Record<string, unknown>) {
    if (actionId === 'provide_pkg') {
      const pkgPath = payload?.pkg_path as string | undefined
      if (pkgPath) {
        ctx.patchState({
          progress: {
            human_pkg_path: pkgPath,
            human_img_path: undefined,
            human_partition: undefined,
          },
        })
        await flashStageDefinition.start!(ctx)
      }
      return
    }
    if (actionId === 'provide_single_img') {
      const imgPath = (payload?.img_path as string | undefined)?.trim()
        || (ctx.state.progress?.img_path as string | undefined)
      const partition = (payload?.partition as string | undefined)?.trim()
      ctx.patchState({
        progress: {
          human_img_path: imgPath,
          human_partition: partition,
          human_pkg_path: undefined,
          img_path: imgPath,
        },
      })
      await flashStageDefinition.start!(ctx)
    }
  },

  async cancel() {
    const { stopActiveFlash } = await import('../../device-flash')
    stopActiveFlash()
    flashPromise = null
    harnessBusy = false
  },
}

export function installFlashStage(): void {
  registerStageForTest(flashStageDefinition)
}

installFlashStage()
