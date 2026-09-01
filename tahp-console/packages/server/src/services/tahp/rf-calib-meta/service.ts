/**
 * 射频校准参数读写编排：生成 init → 本机 MetaCLI → TaskStream 日志
 */
import { existsSync, mkdirSync, writeFileSync } from 'fs'
import { dirname } from 'path'
import { logger } from '../../logger'
import { tahpPaths } from '../paths'
import { getTaskStream } from '../task-stream'
import {
  buildMetaInitContent,
  defaultInitFilePath,
  defaultRunOutputDir,
  defaultToolLogDir,
  ensureTrailingDir,
  isExistingFile,
  resolveBackupCalPath,
  validateItemsIniPath,
} from './init-builder'
import { prepareRestoreCalFileWithoutImei, stripImeiFromCalFile } from './cal-imei-filter'
import { assessMetaCliActionFromLogs, annotateMetaCliLogLine } from './meta-result'
import { probeModemMetaCli, resolveModemMetaRoot, spawnMetaCli, MODEM_META_CONFIG_HINT } from './meta-cli'
import { listMtkComPorts, prepareMetaConnection, waitForAdbDevice } from './meta-connect-prep'
import { enterMetaViaAdbAndWaitComPort } from './meta-adb-boot'
import {
  appendRfCalibMetaLog,
  createRfCalibMetaRun,
  getRfCalibMetaRun,
  listActiveRfCalibMetaRuns,
  listRfCalibMetaRuns,
  newRfCalibMetaRunId,
  patchRfCalibMetaRun,
  saveRfCalibMetaRun,
} from './store'
import type { RfCalibMetaConnectionStrategy, RfCalibMetaProbeResult, RfCalibMetaRunRecord, RfCalibMetaStartInput } from './types'

const activeJobs = new Map<string, { cancelled: boolean }>()
let recovered = false

function emit(taskId: string, type: string, payload: Record<string, unknown> = {}) {
  getTaskStream().publish({
    type,
    task_id: taskId,
    payload: { task_id: taskId, ...payload },
    ts: Date.now(),
  })
}

function persistLog(runId: string, line: string) {
  appendRfCalibMetaLog(runId, line)
  const run = getRfCalibMetaRun(runId)
  if (run && run.log_tail.length % 20 === 0) {
    saveRfCalibMetaRun(run)
  }
}

function ensureParentDir(path: string): void {
  const dir = dirname(path)
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
}

function validateInput(input: RfCalibMetaStartInput): string | null {
  if (input.mode !== 'backup' && input.mode !== 'restore') {
    return 'mode 须为 backup 或 restore'
  }
  if (!input.itemsIniPath?.trim()) {
    return null
  }
  const itemsErr = validateItemsIniPath(input.itemsIniPath.trim())
  if (itemsErr) return itemsErr
  if (input.mode === 'restore') {
    if (!input.calFilePath?.trim()) {
      return '恢复模式须指定校准数据文件（CalibrationFilePath）'
    }
    if (!existsSync(input.calFilePath.trim())) {
      return `校准数据文件不存在: ${input.calFilePath.trim()}`
    }
  }
  return null
}

async function runMetaCliJob(
  run: RfCalibMetaRunRecord,
  opts?: {
    prepLogs?: string[]
    adbDeviceId?: string
    initialComPort?: string
    useAdbSwitch?: boolean
    connectionStrategy?: RfCalibMetaConnectionStrategy
  },
): Promise<void> {
  const signal = { cancelled: false }
  activeJobs.set(run.run_id, signal)
  const started = Date.now()

  const logLine = (line: string, phase = 'prep') => {
    persistLog(run.run_id, line)
    emit(run.run_id, 'task.message', { level: 'stream', text: line, phase })
  }

  for (const line of opts?.prepLogs || []) {
    logLine(line, 'prep')
  }

  let comPort = opts?.initialComPort || run.com_port || 'Auto Connection'
  let metaComConnected = run.meta_com_connected === true
  let useAdbSwitch = opts?.useAdbSwitch === true
  const manualCom = comPort.trim() && comPort.trim() !== 'Auto Connection'
  const adbId = opts?.adbDeviceId || run.adb_device_id
  const strategy = opts?.connectionStrategy || run.connection_strategy || 'preloader_boot'

  if (!manualCom && !metaComConnected) {
    const existing = listMtkComPorts()
    const metaPort = existing.find(p => /meta/i.test(p.name))?.port
    if (metaPort && strategy !== 'preloader_boot') {
      comPort = metaPort
      metaComConnected = true
      logLine(`[prep] 已有 META 串口 ${metaPort}，直连模式`)
    } else if (strategy === 'adb_reboot_meta' && adbId) {
      patchRfCalibMetaRun(run.run_id, {
        status: 'running',
        phase: 'meta-boot',
        progress: 3,
        message: 'ADB reboot meta…',
      })
      emit(run.run_id, 'task.phase', {
        phase: 'meta-boot',
        progress: 3,
        message: 'ADB reboot meta…',
      })
      const boot = await enterMetaViaAdbAndWaitComPort(adbId, (line) => logLine(line, 'meta-boot'))
      if (signal.cancelled) return
      if (!boot.ok || !boot.com_port) {
        patchRfCalibMetaRun(run.run_id, {
          status: 'failed',
          error: boot.reason || '无法进入 META 模式',
          completed_at: new Date().toISOString(),
          duration_ms: Date.now() - started,
          phase: 'done',
          progress: 100,
        })
        emit(run.run_id, 'task.failed', { error: boot.reason || '无法进入 META 模式' })
        return
      }
      comPort = boot.com_port
      metaComConnected = true
    } else if (strategy === 'preloader_boot') {
      comPort = 'Auto Connection'
      metaComConnected = false
      useAdbSwitch = false
      logLine('[prep] 与 Modem Meta GUI 相同：Smart Phone + Auto Connection + EnableSwitchModemMode=1')
      logLine('[prep] MetaCLI 即将启动并等待连接；请关机后插入 USB（等同 GUI 点「连接」后再插线）')
      logLine('[prep] 日志出现 Connect status: Boot ... 为正常等待，插 USB 后应变为 success')
    } else if (strategy === 'meta_port') {
      patchRfCalibMetaRun(run.run_id, {
        status: 'failed',
        error: '未检测到 META 串口，请手动填写 COM 口',
        completed_at: new Date().toISOString(),
        duration_ms: Date.now() - started,
        phase: 'done',
        progress: 100,
      })
      emit(run.run_id, 'task.failed', { error: '未检测到 META 串口，请手动填写 COM 口' })
      return
    }
  } else if (manualCom) {
    metaComConnected = strategy === 'meta_port'
  }

  patchRfCalibMetaRun(run.run_id, {
    com_port: comPort,
    meta_com_connected: metaComConnected,
    adb_device_id: adbId,
  })

  const toolLogDir = ensureTrailingDir(defaultToolLogDir(tahpPaths.projectRoot, run.run_id))
  const initFilePath = run.init_file_path || defaultInitFilePath(tahpPaths.projectRoot, run.run_id)
  ensureParentDir(initFilePath)

  let metaCalPath = run.cal_file_path!
  logLine('[prep] 默认排除 IMEI（机型 IMEI 保护：不备份/不还原 IMEI）')
  if (run.mode === 'restore') {
    const workDir = defaultRunOutputDir(tahpPaths.projectRoot, run.run_id)
    const filtered = prepareRestoreCalFileWithoutImei(run.cal_file_path!, workDir, run.run_id)
    if (filtered.stripped) {
      metaCalPath = filtered.path
      logLine(`[prep] 恢复用临时文件已去掉 IMEI（${filtered.removed} 处）: ${metaCalPath}`)
    } else {
      logLine('[prep] 源校准文件无 IMEI 段，直接用于恢复')
    }
  }

  const initContent = buildMetaInitContent({
    mode: run.mode,
    calFilePath: metaCalPath,
    itemsIniPath: run.items_ini_path!,
    comPort,
    toolLogDir,
    useAdbSwitch,
    metaComConnected,
  })
  writeFileSync(initFilePath, initContent, 'utf-8')
  patchRfCalibMetaRun(run.run_id, { init_file_path: initFilePath })
  logLine(`[prep] Init 已生成: ${initFilePath}`)
  logLine(`[prep] 连接模式: ${metaComConnected ? `DUT in META Mode @ ${comPort}` : `Smart Phone @ ${comPort}`}`)

  if (useAdbSwitch && !metaComConnected && strategy === 'adb_reboot_meta') {
    patchRfCalibMetaRun(run.run_id, {
      status: 'running',
      phase: 'adb',
      progress: 2,
      message: '等待 ADB 设备…',
    })
    emit(run.run_id, 'task.phase', { phase: 'adb', progress: 2, message: '等待 ADB 设备…' })
    waitForAdbDevice(12000)
  }

  patchRfCalibMetaRun(run.run_id, {
    status: 'running',
    phase: 'connect',
    progress: 5,
    message: strategy === 'preloader_boot'
      ? 'MetaCLI 等待连接，请关机后插 USB…'
      : '启动 MetaCLI，等待设备连接…',
  })
  emit(run.run_id, 'task.phase', {
    phase: 'connect',
    progress: 5,
    message: strategy === 'preloader_boot'
      ? 'MetaCLI 等待连接，请关机后插 USB…'
      : '启动 MetaCLI，等待设备连接…',
  })

  try {
    const metaRoot = run.meta_root || resolveModemMetaRoot()
    if (!metaRoot) {
      throw new Error(MODEM_META_CONFIG_HINT)
    }
    const result = await spawnMetaCli({
      metaRoot,
      initFilePath: run.init_file_path!,
      cwd: metaRoot,
      onStdout: (chunk) => {
        for (const line of chunk.split(/\r?\n/)) {
          if (!line.trim()) continue
          const text = annotateMetaCliLogLine(line)
          persistLog(run.run_id, text)
          emit(run.run_id, 'task.message', { level: 'stream', text, phase: 'meta-cli' })
        }
      },
      onStderr: (chunk) => {
        for (const line of chunk.split(/\r?\n/)) {
          if (!line.trim()) continue
          const text = annotateMetaCliLogLine(`[stderr] ${line}`)
          persistLog(run.run_id, text)
          emit(run.run_id, 'task.message', { level: 'stream', text, phase: 'meta-cli' })
        }
      },
      signal,
    })

    if (signal.cancelled) {
      patchRfCalibMetaRun(run.run_id, {
        status: 'cancelled',
        error: '已取消',
        completed_at: new Date().toISOString(),
        duration_ms: Date.now() - started,
        exit_code: result.code,
      })
      emit(run.run_id, 'task.cancelled', { error: '已取消' })
      return
    }

    const outputPath = run.output_cal_path || run.cal_file_path
    const logLines = getRfCalibMetaRun(run.run_id)?.log_tail || []
    const action = assessMetaCliActionFromLogs(logLines, run.mode)
    const outputExists = !!(outputPath && isExistingFile(outputPath))

    // 默认：日志 ok 且退出码 0。仅 IMEI 失败时 MetaCLI 常返回 3，靠 warning 放行。
    let success = action.ok && (result.code === 0 || !!action.warning)
    let failReason = !action.ok
      ? action.reason
      : (success ? undefined : `MetaCLI 退出码 ${result.code ?? 'unknown'}`)
    const warning = action.warning

    if (success && run.mode === 'backup' && !outputExists) {
      success = false
      failReason = `未找到输出文件: ${outputPath}（OutputCalibrationDataFilePath 须为 .ini 文件路径，不能填目录）`
    }

    if (success && run.mode === 'backup' && outputPath && isExistingFile(outputPath)) {
      const stripped = stripImeiFromCalFile(outputPath)
      if (stripped.changed) {
        persistLog(run.run_id, `[post] 已从备份文件去掉 IMEI（${stripped.removed} 处）: ${outputPath}`)
        emit(run.run_id, 'task.message', {
          level: 'stream',
          text: `[post] 已从备份文件去掉 IMEI（${stripped.removed} 处）`,
          phase: 'post',
        })
      } else {
        persistLog(run.run_id, '[post] 备份文件不含 IMEI 段（符合默认排除）')
      }
    }

    // 收尾醒目日志：MetaCLI 常在末尾打 Error（IMEI 等），避免同事误判整单失败
    const doneBanner = (text: string) => {
      persistLog(run.run_id, text)
      emit(run.run_id, 'task.message', { level: 'stream', text, phase: 'done' })
    }
    if (success) {
      if (run.mode === 'backup') {
        doneBanner('========== 备份完成 ==========')
        doneBanner(
          warning
            ? `[done] RF 校准备份成功。${warning}`
            : '[done] RF 校准备份成功。',
        )
        if (outputPath) doneBanner(`[done] 输出文件: ${outputPath}`)
        doneBanner('[done] 若上方仍有 MetaCLI Error/IMEI Failed，可忽略；以本行「备份完成」与任务状态为准。')
      } else {
        doneBanner('========== 恢复完成 ==========')
        doneBanner(
          warning
            ? `[done] RF 校准恢复成功。${warning}`
            : '[done] RF 校准恢复成功。',
        )
        doneBanner('[done] 若上方仍有 MetaCLI Error/IMEI Failed，可忽略；以本行「恢复完成」与任务状态为准。')
      }
    } else {
      const verb = run.mode === 'backup' ? '备份' : '恢复'
      doneBanner(`========== ${verb}失败 ==========`)
      doneBanner(`[done] ${failReason || `MetaCLI 退出码 ${result.code ?? 'unknown'}`}`)
    }

    patchRfCalibMetaRun(run.run_id, {
      status: success ? 'completed' : 'failed',
      error: success ? undefined : (failReason || `MetaCLI 退出码 ${result.code ?? 'unknown'}`),
      completed_at: new Date().toISOString(),
      duration_ms: Date.now() - started,
      exit_code: result.code,
      progress: 100,
      message: success
        ? (warning || (run.mode === 'backup' ? '校准数据已备份' : '校准数据已恢复'))
        : 'MetaCLI 执行失败',
      phase: 'done',
    })

    if (success) {
      emit(run.run_id, 'task.completed', {
        mode: run.mode,
        cal_file_path: run.cal_file_path,
        output_cal_path: run.output_cal_path,
        warning,
      })
    } else {
      emit(run.run_id, 'task.failed', {
        error: failReason || `MetaCLI 退出码 ${result.code ?? 'unknown'}`,
      })
    }
  } catch (err) {
    const msg = (err as Error).message
    logger.warn({ err: msg, runId: run.run_id }, '[rf-calib-meta] MetaCLI failed')
    patchRfCalibMetaRun(run.run_id, {
      status: signal.cancelled ? 'cancelled' : 'failed',
      error: signal.cancelled ? '已取消' : msg,
      completed_at: new Date().toISOString(),
      duration_ms: Date.now() - started,
      progress: 100,
      phase: 'done',
    })
    emit(run.run_id, signal.cancelled ? 'task.cancelled' : 'task.failed', { error: msg })
  } finally {
    activeJobs.delete(run.run_id)
    const saved = getRfCalibMetaRun(run.run_id)
    if (saved) saveRfCalibMetaRun(saved)
  }
}

export async function probeRfCalibMeta(_metaRoot?: string): Promise<RfCalibMetaProbeResult> {
  // 安装目录只读一键配置表单；忽略页面/请求覆盖，避免与统一配置分叉
  const base = probeModemMetaCli()
  const prep = prepareMetaConnection()
  return {
    ...base,
    adb_devices: prep.adb_devices,
    mtk_com_ports: prep.mtk_com_ports,
    suggested_com_port: prep.suggested_com_port,
    suggested_items_ini: base.suggested_items_ini,
    connection_hint: prep.connection_hint,
  }
}

export async function startRfCalibMeta(
  input: RfCalibMetaStartInput,
): Promise<{ ok: true; run_id: string } | { ok: false; error: string }> {
  const err = validateInput(input)
  if (err) return { ok: false, error: err }

  const probe = probeModemMetaCli()
  if (!probe.available) {
    return { ok: false, error: probe.reason || 'Modem Meta MetaCLI 不可用' }
  }

  const metaRoot = probe.meta_root!
  const runId = newRfCalibMetaRunId()

  const strategy = input.connectionStrategy || 'preloader_boot'

  const prep = prepareMetaConnection({ comPort: input.comPort, connectionStrategy: strategy })
  if (!prep.ok) {
    return { ok: false, error: prep.reason || '设备连接未就绪' }
  }

  const effectiveComPort = prep.suggested_com_port || input.comPort || 'Auto Connection'
  const useAdbSwitch = strategy === 'adb_reboot_meta' && prep.adb_devices.length > 0
  const adbDeviceId = prep.adb_devices[0]

  const outputCalPath = input.mode === 'backup'
    ? resolveBackupCalPath(tahpPaths.projectRoot, runId, input.outputCalPath || input.calFilePath)
    : undefined
  const calFilePath = input.mode === 'backup'
    ? outputCalPath!
    : input.calFilePath.trim()

  const toolLogDir = ensureTrailingDir(defaultToolLogDir(tahpPaths.projectRoot, runId))
  const initFilePath = defaultInitFilePath(tahpPaths.projectRoot, runId)

  ensureParentDir(toolLogDir)
  if (input.mode === 'backup') ensureParentDir(dirname(calFilePath))

  const run = createRfCalibMetaRun({
    runId,
    label: input.label || (input.mode === 'backup' ? '备份校准数据' : '恢复校准数据'),
    mode: input.mode,
    calFilePath,
    itemsIniPath: input.itemsIniPath.trim(),
    outputCalPath: outputCalPath,
    comPort: effectiveComPort,
    metaRoot,
    initFilePath,
    adbDeviceId,
    connectionStrategy: strategy,
  })

  emit(run.run_id, 'task.started', {
    mode: run.mode,
    message: run.mode === 'backup' ? '开始备份校准数据' : '开始恢复校准数据',
  })

  void runMetaCliJob(run, {
    prepLogs: prep.logs,
    adbDeviceId,
    initialComPort: effectiveComPort,
    useAdbSwitch,
    connectionStrategy: strategy,
  })
  return { ok: true, run_id: run.run_id }
}

export function getRfCalibMetaRunDetail(runId: string): RfCalibMetaRunRecord | undefined {
  return getRfCalibMetaRun(runId)
}

export function listRfCalibMetaRunSummaries(limit = 50) {
  return listRfCalibMetaRuns(limit)
}

export async function cancelRfCalibMeta(runId: string): Promise<{ ok: boolean; error?: string }> {
  const run = getRfCalibMetaRun(runId)
  if (!run) return { ok: false, error: '任务不存在' }
  if (run.status !== 'running' && run.status !== 'pending') {
    return { ok: false, error: `任务已结束（${run.status}）` }
  }
  const job = activeJobs.get(runId)
  if (job) job.cancelled = true
  return { ok: true }
}

export function recoverRfCalibMetaRuns(): void {
  if (recovered) return
  recovered = true
  for (const run of listActiveRfCalibMetaRuns()) {
    patchRfCalibMetaRun(run.run_id, {
      status: 'failed',
      error: '服务重启导致 MetaCLI 任务中断，请重新开始',
      completed_at: new Date().toISOString(),
      message: 'lost_after_restart',
    })
    emit(run.run_id, 'task.failed', {
      error: '服务重启导致 MetaCLI 任务中断，请重新开始',
    })
  }
}

export function resetRfCalibMetaServiceForTest(): void {
  recovered = false
  activeJobs.clear()
}
