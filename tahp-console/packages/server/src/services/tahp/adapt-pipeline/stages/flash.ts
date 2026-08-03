import { existsSync } from 'node:fs'
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
import {
  classifyFlashArtifacts,
  type FlashArtifactClassification,
} from '../flash-artifact-classify'
import {
  probeHarnessFlash,
  runHarnessFlash,
} from '../harness-flash-capability'

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
  const mappedRoot = ctx.run.build_context?.mapped_root
  const resolved = preferredPkg || resolveFlashPkgPath(artifactsDir, mappedRoot) || undefined
  const humanPkg = ctx.state.progress?.human_pkg_path as string | undefined
  const humanImg = ctx.state.progress?.human_img_path as string | undefined
  const humanPartition = ctx.state.progress?.human_partition as string | undefined
  return {
    pkgPath: humanPkg || resolved,
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

export const flashStageDefinition: StageDefinition = {
  key: 'flash',
  label: '烧录',
  consumes: ['build'],
  produces: ['flashed'],

  async probe() {
    try {
      const { resolveDeviceUpdateExe } = await import('../../device-flash')
      const exe = resolveDeviceUpdateExe()
      if (existsSync(exe)) return { available: true }
    } catch { /* fall through */ }
    const harness = await probeHarnessFlash()
    if (harness.available) return { available: true }
    return {
      available: false,
      reason: harness.reason ?? 'device_update 与 harness 刷机均不可用',
    }
  },

  async start(ctx: StageContext) {
    const buildState = ctx.run.stages.build
    if (buildState?.status === 'failed' || buildState?.status === 'skipped') {
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

    // —— 完整包：先 device_update，失败再降级 harness-device ——
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

    ctx.patchState({
      progress: {
        state: 'flashing',
        phase: 'device_update',
        pkg_path: pkgPath,
        message: 'device_update 刷写整包',
        text: pkgPath,
      },
    })
    ctx.log(`开始刷机(device_update): ${pkgPath} → ${deviceId}`)

    flashPromise = runDeviceFlash([deviceId], { pkgPath }, line => ctx.log(line))
    try {
      const result = await flashPromise
      flashPromise = null
      if (result.success) {
        await markSuccess(ctx, pkgPath, 'device_update', result.returnCode)
        return
      }

      ctx.log(`device_update 失败 (exit ${result.returnCode})，降级 harness-device…`)
      ctx.patchState({
        progress: {
          state: 'flashing',
          phase: 'harness_fallback',
          pkg_path: pkgPath,
          message: 'device_update 失败，降级 harness-device',
          device_update_error: result.error ?? `exit ${result.returnCode}`,
          text: pkgPath,
        },
      })

      const harnessOk = await probeHarnessFlash()
      if (!harnessOk.available) {
        ctx.patchState({
          progress: {
            state: 'failed',
            error: `device_update 失败且 harness 不可用: ${harnessOk.reason ?? result.error}`,
            via: 'device_update',
          },
        })
        return
      }

      harnessBusy = true
      const harnessResult = await runHarnessFlash({
        pipelineRunId: ctx.run.run_id,
        mode: 'full_rom',
        deviceId,
        romPath: pkgPath,
        variant: ctx.run.build_context?.variant,
      }, line => ctx.log(line))
      harnessBusy = false

      if (harnessResult.success) {
        await markSuccess(ctx, pkgPath, 'harness-device')
      } else {
        ctx.patchState({
          progress: {
            state: 'failed',
            error: harnessResult.error
              ?? `device_update 与 harness-device 均失败`,
            via: 'harness-device',
          },
        })
      }
    } catch (err) {
      flashPromise = null
      harnessBusy = false
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
