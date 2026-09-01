/**
 * 生成 Modem Meta MetaCLI init 文件（INI）。
 * 键名对齐 Modem META User Manual §9 / MetaCLI settingfileparser：
 * - 段名格式 Modem%1Action%2 → [Modem1Action1]（MD 序号 + Action 序号），非 [ModemAction]/[Modem1Action]
 * - OutputCalibrationDataFilePath：从目标上传并保存校准数据（备份）
 * - CalibrationFilePath：下载校准文件到目标（恢复）
 * - DB = Load from target：Load DB
 * - 不写 IniFilePath（易误填大校准文件；MetaCLI 用默认项集即可）
 */
import { dirname, join } from 'path'
import { existsSync, readFileSync, statSync } from 'fs'
import type { RfCalibMetaMode } from './types'

export interface BuildMetaInitInput {
  mode: RfCalibMetaMode
  calFilePath: string
  itemsIniPath: string
  comPort?: string
  toolLogDir: string
  /** true：Android 开机 + ADB，MetaCLI 自动切 META（推荐，无需开 GUI） */
  useAdbSwitch?: boolean
  /** 已通过 ADB reboot meta 拿到 META 口时，直连 DUT in META Mode */
  metaComConnected?: boolean
}

/** MetaCLI 路径用正斜杠，避免 INI 反斜杠转义 */
export function normalizeMetaCliIniPath(p: string): string {
  return p.replace(/\\/g, '/').trim()
}

export function modemActionSectionName(mdIndex = 1, actionIndex = 1): string {
  return `Modem${mdIndex}Action${actionIndex}`
}

export function buildMetaInitContent(input: BuildMetaInitInput): string {
  const calPath = normalizeMetaCliIniPath(input.calFilePath)
  const logDir = normalizeMetaCliIniPath(input.toolLogDir)
  const comPort = (input.comPort || 'Auto Connection').trim()
  const metaDirect = input.metaComConnected === true && comPort !== 'Auto Connection'
  const section = modemActionSectionName(1, 1)

  const lines = metaDirect
    ? [
      '[Connection]',
      'PlatformType = DUT in META Mode',
      'ComPortType = USB',
      `ComPort = ${comPort}`,
      'EnableADBService = 0',
      'EnableSwitchModemMode = 1',
      'ActiveMD = 1',
      'ChannelType = 0',
      'ServiceType = 1',
      '',
      `[${section}]`,
    ]
    : (() => {
      const adbSwitch = input.useAdbSwitch === true
      return [
        '[Connection]',
        'PlatformType = Smart Phone',
        'ComPortType = USB',
        `ComPort = ${comPort}`,
        `EnableADBService = ${adbSwitch ? 1 : 0}`,
        'EnableSwitchModemMode = 1',
        'ActiveMD = 1',
        'ChannelType = 0',
        'ServiceType = 1',
        '',
        `[${section}]`,
      ]
    })()

  lines.push('DB = Load from target')
  if (input.mode === 'backup') {
    lines.push(`OutputCalibrationDataFilePath = ${calPath}`)
  } else {
    lines.push(`CalibrationFilePath = ${calPath}`)
  }
  // 有意不写 IniFilePath：避免用户把校准大文件误填进来
  void input.itemsIniPath
  lines.push('')
  lines.push('[Disconnection]')
  lines.push('AfterDisconnect = Shutdown')
  lines.push('')
  lines.push('[DebugMode]')
  lines.push(`ToolLogPath = ${logDir}`)

  return `${lines.join('\r\n')}\r\n`
}

/**
 * MetaCLI 写出的校准文件 / ToolLog 目录。
 * 注意：不要放在 `.tahp-config` 下——MetaCLI 对含点号隐藏目录的路径常写失败
 *（日志仍显示 Write Category Done，但 step2 save to file failed，磁盘无文件）。
 * 任务元数据（runs/inits）仍可放在 `.tahp-config`，由 Node 读写。
 */
export function defaultRunOutputDir(projectRoot: string, runId: string): string {
  return join(projectRoot, 'reports', 'rf-calib-meta', runId)
}

export function defaultToolLogDir(projectRoot: string, runId: string): string {
  return join(projectRoot, 'reports', 'rf-calib-meta', runId, 'meta-logs')
}

export function defaultInitFilePath(projectRoot: string, runId: string): string {
  return join(projectRoot, '.tahp-config', 'rf-calib-meta', 'inits', `${runId}.ini`)
}

export function resolveBackupCalPath(
  projectRoot: string,
  runId: string,
  explicit?: string,
): string {
  if (explicit?.trim()) {
    const p = explicit.trim().replace(/\//g, '\\')
    try {
      if (existsSync(p) && statSync(p).isDirectory()) {
        return join(p, 'calibration_data.ini')
      }
    } catch { /* ignore */ }
    if (!/\.[a-z0-9]+$/i.test(p)) {
      return join(p, 'calibration_data.ini')
    }
    return p
  }
  return join(defaultRunOutputDir(projectRoot, runId), 'calibration_data.ini')
}

/** 校验 IniFilePath：小模板 ini；排除误填的校准数据大文件（可选字段时由调用方跳过） */
export function validateItemsIniPath(itemsIniPath: string): string | null {
  const p = itemsIniPath.trim()
  if (!p) return '请填写 IniFilePath（Modem Meta GUI 上次打开的 ini，通常很小）'
  if (!existsSync(p)) return `IniFilePath 不存在: ${p}`
  try {
    const st = statSync(p)
    if (st.isDirectory()) {
      return 'IniFilePath 不能是目录。请填 Modem Meta GUI「Update Parameter / Read Write Cal Data」里 Import 用的那个小 ini（非备份输出大文件）'
    }
    if (st.size > 2 * 1024 * 1024) {
      return `IniFilePath 文件过大（约 ${Math.round(st.size / 1024 / 1024)}MB），这是「校准数据备份文件」，不是 MetaCLI 的 IniFilePath。备份输出应填在「输出文件」栏。`
    }
    const head = readFileSync(p, 'utf-8').slice(0, 8192)
    const looksLikeCalData = /\[RF SELF CALIBRATION\]|\[MMRF AFC control\]|RX TYPE1 CAL DATA/i.test(head)
    if (looksLikeCalData) {
      return 'IniFilePath 内容是校准数据（含 RF 校准段），不是 GUI Import 用的小 ini。IniFilePath 与备份输出文件是两个不同路径。'
    }
  } catch {
    /* 读取失败时不阻断，交给 MetaCLI */
  }
  return null
}

export function isExistingFile(path: string): boolean {
  try {
    return existsSync(path) && statSync(path).isFile()
  } catch {
    return false
  }
}

export function ensureTrailingDir(path: string): string {
  const p = path.replace(/\//g, '\\').trim()
  return p.endsWith('\\') ? p : `${p}\\`
}

export function parentDir(path: string): string {
  return dirname(path.replace(/\//g, '\\'))
}
