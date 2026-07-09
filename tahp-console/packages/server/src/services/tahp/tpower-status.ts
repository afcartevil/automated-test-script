/**
 * T-Power 功耗测试硬件连接状态探测
 */
import { spawn } from 'child_process'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { join, resolve } from 'path'
import { getTahpProjectRoot } from './paths'

function projectRoot(): string {
  return getTahpProjectRoot()
}

export interface TPowerConfig {
  adbSerial?: string
  label?: string
}

export interface TPowerStatus {
  connected: boolean
  adbSerial?: string
  label?: string
  message: string
  checkedAt: string
}

function tpowerConfigPath(): string {
  return join(projectRoot(), '.tahp-config', 'tpower.json')
}

export function loadTPowerConfig(): TPowerConfig {
  if (process.env.TAHP_TPOWER_ADB_SERIAL) {
    return { adbSerial: process.env.TAHP_TPOWER_ADB_SERIAL.trim(), label: 'T-Power (env)' }
  }
  const path = tpowerConfigPath()
  if (!existsSync(path)) return {}
  try {
    const data = JSON.parse(readFileSync(path, 'utf-8')) as TPowerConfig
    return {
      adbSerial: data.adbSerial?.trim(),
      label: data.label?.trim() || 'T-Power',
    }
  } catch {
    return {}
  }
}

export function saveTPowerConfig(config: TPowerConfig): TPowerConfig {
  const dir = join(projectRoot(), '.tahp-config')
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  const cleaned: TPowerConfig = {
    adbSerial: config.adbSerial?.trim() || undefined,
    label: config.label?.trim() || 'T-Power',
  }
  writeFileSync(tpowerConfigPath(), `${JSON.stringify(cleaned, null, 2)}\n`, 'utf-8')
  return cleaned
}

async function getAdbDeviceIds(): Promise<string[]> {
  return new Promise((resolve) => {
    let proc: ReturnType<typeof spawn> | null = null
    const timeout = setTimeout(() => {
      try { proc?.kill() } catch { /* ignore */ }
      resolve([])
    }, 5000)

    try {
      proc = spawn('adb', ['devices'], {
        stdio: ['ignore', 'pipe', 'pipe'],
        shell: process.platform === 'win32',
      })
      let stdout = ''
      proc.stdout?.on('data', (chunk: Buffer) => { stdout += chunk.toString() })
      proc.on('close', () => {
        clearTimeout(timeout)
        const ids: string[] = []
        for (const line of stdout.split('\n')) {
          const trimmed = line.trim()
          if (!trimmed || trimmed.startsWith('List')) continue
          const parts = trimmed.split(/\s+/)
          if (parts.length >= 2 && parts[1] === 'device') ids.push(parts[0])
        }
        resolve(ids)
      })
      proc.on('error', () => {
        clearTimeout(timeout)
        resolve([])
      })
    } catch {
      clearTimeout(timeout)
      resolve([])
    }
  })
}

export async function probeTPowerStatus(): Promise<TPowerStatus> {
  const checkedAt = new Date().toISOString()
  const config = loadTPowerConfig()

  if (!config.adbSerial) {
    return {
      connected: false,
      message: '未配置 T-Power ADB 序列号，请在 .tahp-config/tpower.json 或 TAHP_TPOWER_ADB_SERIAL 中设置',
      checkedAt,
    }
  }

  const adbIds = await getAdbDeviceIds()
  if (!adbIds.length) {
    return {
      connected: false,
      adbSerial: config.adbSerial,
      label: config.label,
      message: 'ADB 未检测到任何设备，请确认 T-Power 已通过 USB 连接且 adb 可用',
      checkedAt,
    }
  }

  const connected = adbIds.includes(config.adbSerial)
  return {
    connected,
    adbSerial: config.adbSerial,
    label: config.label,
    message: connected
      ? `T-Power 已连接（${config.adbSerial}）`
      : `配置的 T-Power 序列号 ${config.adbSerial} 未出现在 adb devices 中（当前: ${adbIds.join(', ') || '无'}）`,
    checkedAt,
  }
}
