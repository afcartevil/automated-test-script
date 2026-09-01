/**
 * MetaCLI 运行前连接准备：ADB 检测、MTK COM 口扫描、进 META 前置提示。
 * 目标：用户仅在 EasyAdapter 点备份，无需先开 Modem Meta GUI。
 */
import { execFileSync, spawnSync } from 'child_process'
import type { RfCalibMetaConnectionStrategy } from './types'

export interface MtkComPortInfo {
  port: string
  name: string
}

export interface MetaConnectPrepResult {
  ok: boolean
  reason?: string
  adb_devices: string[]
  mtk_com_ports: MtkComPortInfo[]
  suggested_com_port?: string
  connection_hint: string
  logs: string[]
}

const MTK_PORT_RE = /mediatek|preloader|brom|meta|vcom|mdlog|bootrom/i

export interface AdbDeviceState {
  id: string
  state: string
}

function runAdbDeviceStates(): AdbDeviceState[] {
  try {
    const out = execFileSync('adb', ['devices'], {
      encoding: 'utf-8',
      timeout: 8000,
      windowsHide: true,
    })
    const rows: AdbDeviceState[] = []
    for (const line of out.split(/\r?\n/)) {
      const m = /^([^\s]+)\s+(\S+)\s*$/.exec(line.trim())
      if (m?.[1] && m[1] !== 'List' && m[2]) {
        rows.push({ id: m[1], state: m[2] })
      }
    }
    return rows
  } catch {
    return []
  }
}

function runAdbDevices(): string[] {
  return runAdbDeviceStates()
    .filter(d => d.state === 'device')
    .map(d => d.id)
}

/** ADB 显示 recovery/sideload 时，手机不在 META */
export function isAdbRecoveryMode(): boolean {
  return runAdbDeviceStates().some(d => /recovery|sideload/i.test(d.state))
}

/** Windows：扫描疑似 MTK Preloader / META 串口（含 PnP 友好名） */
export function listMtkComPorts(): MtkComPortInfo[] {
  if (process.platform !== 'win32') return []
  const ports = new Map<string, string>()
  const add = (port: string, name: string) => {
    const p = port.trim().toUpperCase()
    if (!/^COM\d+$/.test(p)) return
    ports.set(p, name.trim())
  }
  try {
    const ps1 = "Get-CimInstance Win32_SerialPort | ForEach-Object { $_.DeviceID + '|' + $_.Name }"
    const out1 = execFileSync('powershell.exe', ['-NoProfile', '-Command', ps1], {
      encoding: 'utf-8', timeout: 12000, windowsHide: true,
    })
    for (const line of out1.split(/\r?\n/)) {
      if (!line.includes('|')) continue
      const [deviceId, ...nameParts] = line.split('|')
      add(deviceId, nameParts.join('|'))
    }
  } catch { /* ignore */ }
  try {
    const ps2 = "Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match 'COM\\d+' } | ForEach-Object { if ($_.Name -match '\\(COM(\\d+)\\)') { 'COM' + $matches[1] + '|' + $_.Name } }"
    const out2 = execFileSync('powershell.exe', ['-NoProfile', '-Command', ps2], {
      encoding: 'utf-8', timeout: 12000, windowsHide: true,
    })
    for (const line of out2.split(/\r?\n/)) {
      if (!line.includes('|')) continue
      const [deviceId, ...nameParts] = line.split('|')
      add(deviceId, nameParts.join('|'))
    }
  } catch { /* ignore */ }
  const out: MtkComPortInfo[] = []
  for (const [port, name] of ports.entries()) {
    if (MTK_PORT_RE.test(name) || MTK_PORT_RE.test(port)) {
      out.push({ port, name })
    }
  }
  return out.sort((a, b) => a.port.localeCompare(b.port, undefined, { numeric: true }))
}

function pickSuggestedComPort(
  explicit?: string,
  mtkPorts: MtkComPortInfo[] = [],
): string | undefined {
  const manual = explicit?.trim()
  if (manual && manual !== 'Auto Connection') return manual
  const usb = mtkPorts.find(p => /usb port/i.test(p.name) && !/preloader/i.test(p.name))
  if (usb) return usb.port
  const meta = mtkPorts.find(p => /\bmeta\b/i.test(p.name) && !/preloader/i.test(p.name))
  if (meta) return meta.port
  const anyMeta = mtkPorts.find(p => /meta/i.test(p.name))
  if (anyMeta) return anyMeta.port
  if (mtkPorts.length === 1) return mtkPorts[0].port
  return undefined
}

export function prepareMetaConnection(opts?: {
  comPort?: string
  connectionStrategy?: RfCalibMetaConnectionStrategy
}): MetaConnectPrepResult {
  const strategy = opts?.connectionStrategy || 'preloader_boot'
  const logs: string[] = []
  const adbDevices = runAdbDevices()
  const mtkComPorts = listMtkComPorts()
  const suggested = pickSuggestedComPort(opts?.comPort, mtkComPorts)

  logs.push(`[prep] 连接策略: ${strategy}`)
  logs.push(`[prep] ADB 设备: ${adbDevices.length ? adbDevices.join(', ') : '无'}`)
  if (mtkComPorts.length) {
    logs.push(`[prep] 检测到 MTK 串口: ${mtkComPorts.map(p => `${p.port}(${p.name})`).join(', ')}`)
  } else {
    logs.push('[prep] 未检测到 MTK Preloader/META 串口')
  }

  const hasAdb = adbDevices.length > 0
  const hasMtkPort = mtkComPorts.length > 0
  const manualCom = opts?.comPort?.trim() && opts.comPort.trim() !== 'Auto Connection'

  if (manualCom) {
    logs.push(`[prep] 使用指定 COM: ${opts!.comPort!.trim()}`)
    return {
      ok: true,
      adb_devices: adbDevices,
      mtk_com_ports: mtkComPorts,
      suggested_com_port: opts!.comPort!.trim(),
      connection_hint: '已指定 COM 口，MetaCLI 将直接连接',
      logs,
    }
  }

  if (strategy === 'meta_port') {
    if (hasMtkPort && suggested) {
      logs.push(`[prep] 已在 META / 检测到串口 ${suggested}`)
      return {
        ok: true,
        adb_devices: adbDevices,
        mtk_com_ports: mtkComPorts,
        suggested_com_port: suggested,
        connection_hint: `使用 META 口 ${suggested}`,
        logs,
      }
    }
    const reason = '「已在 META」模式须设备已进入 META 并在页面填写 COM 口，或插入后自动检测到 MediaTek 口。'
    logs.push(`[prep] 失败: ${reason}`)
    return { ok: false, reason, adb_devices: adbDevices, mtk_com_ports: mtkComPorts, connection_hint: reason, logs }
  }

  if (strategy === 'preloader_boot') {
    if (hasAdb) {
      logs.push('[prep] 提示: 检测到 ADB 在线；产线进 META 请先完全关机再插 USB')
    }
    logs.push('[prep] 与 Modem Meta GUI 相同：Smart Phone + Auto Connection（ComPort=Auto Connection）')
    logs.push('[prep] 点「开始备份」后 MetaCLI 立即启动并等待；请关机后插入 USB')
    return {
      ok: true,
      adb_devices: adbDevices,
      mtk_com_ports: mtkComPorts,
      suggested_com_port: 'Auto Connection',
      connection_hint: '等同 Modem Meta 点「连接」→ 关机 → 插 USB',
      logs,
    }
  }

  // adb_reboot_meta
  if (!hasAdb) {
    const reason = '「adb reboot meta」模式需要 Android 已 ADB 连接；传音量产机通常不支持该命令，请改用 Preloader 模式。'
    logs.push(`[prep] 失败: ${reason}`)
    return { ok: false, reason, adb_devices: adbDevices, mtk_com_ports: mtkComPorts, connection_hint: reason, logs }
  }
  logs.push('[prep] 将尝试 adb reboot meta（仅部分工程版有效）')
  return {
    ok: true,
    adb_devices: adbDevices,
    mtk_com_ports: mtkComPorts,
    suggested_com_port: 'Auto Connection',
    connection_hint: 'adb reboot meta（量产机常无效）',
    logs,
  }
}

/** 等待 ADB 设备（短超时），便于刚插线后立即点备份 */
export function waitForAdbDevice(timeoutMs = 15000): boolean {
  try {
    const r = spawnSync('adb', ['wait-for-device'], {
      encoding: 'utf-8',
      timeout: timeoutMs,
      windowsHide: true,
    })
    return r.status === 0
  } catch {
    return false
  }
}
