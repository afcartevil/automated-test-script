/**

 * 通过 ADB 重启进 META，并等待 Windows 出现 MTK META 串口。

 */

import { execFileSync } from 'child_process'

import { isAdbRecoveryMode, listMtkComPorts, type MtkComPortInfo } from './meta-connect-prep'



export interface EnterMetaViaAdbResult {

  ok: boolean

  com_port?: string

  /** true → DUT in META Mode 直连；false → Smart Phone Auto Boot */

  meta_direct?: boolean

  preloader_port?: string

  reason?: string

  logs: string[]

}



export interface MtkFactoryPortResult {

  preloaderPort?: string

  metaPort?: string

  /** ADB 显示 recovery/sideload，或仅有 META 口但无 PreLoader 且疑似误进 Recovery */

  recoverySuspected: boolean

}



function sleep(ms: number): Promise<void> {

  return new Promise(resolve => setTimeout(resolve, ms))

}



export function rebootMetaViaAdb(deviceId?: string): { ok: boolean; output: string } {

  const args = deviceId ? ['-s', deviceId, 'reboot', 'meta'] : ['reboot', 'meta']

  try {

    const out = execFileSync('adb', args, {

      encoding: 'utf-8',

      timeout: 20000,

      windowsHide: true,

    })

    return { ok: true, output: out || 'adb reboot meta sent' }

  } catch (err) {

    const e = err as { stdout?: string; stderr?: string; message?: string }

    return {

      ok: false,

      output: [e.stdout, e.stderr, e.message].filter(Boolean).join('\n'),

    }

  }

}



/** MediaTek USB Port（META），排除 PreLoader 口 */

export function pickMetaUsbPort(ports: MtkComPortInfo[]): string | undefined {

  const usb = ports.find(p => /usb port/i.test(p.name) && !/preloader/i.test(p.name))

  if (usb) return usb.port

  const meta = ports.find(p => /\bmeta\b/i.test(p.name) && !/preloader/i.test(p.name))

  if (meta) return meta.port

  return undefined

}



function pickPreloaderPort(ports: MtkComPortInfo[]): string | undefined {

  const preloader = ports.find(p => /preloader|bootrom|brom/i.test(p.name))

  if (preloader) return preloader.port

  const vcom = ports.find(p => /mediatek.*vcom|usb vcom/i.test(p.name) && !/preloader/i.test(p.name))

  if (vcom) return vcom.port

  return undefined

}



function pickMetaPort(ports: MtkComPortInfo[]): string | undefined {

  const direct = pickMetaUsbPort(ports)

  if (direct) return direct

  const meta = ports.find(p => /meta/i.test(p.name))

  if (meta) return meta.port

  const mtk = ports.find(p => /mediatek|vcom|mdlog/i.test(p.name) && !/preloader/i.test(p.name))

  if (mtk) return mtk.port

  if (ports.length === 1) return ports[0].port

  return undefined

}



/** 等待 PreLoader 或 META 口；仅见 META 口时不再空等 120s */

export async function waitForMtkFactoryPort(opts?: {

  timeoutMs?: number

  pollMs?: number

  metaOnlyStablePolls?: number

  onPoll?: (ports: MtkComPortInfo[]) => void

}): Promise<MtkFactoryPortResult | undefined> {

  const timeoutMs = opts?.timeoutMs ?? 120_000

  const pollMs = opts?.pollMs ?? 2500

  const metaOnlyStablePolls = opts?.metaOnlyStablePolls ?? 3

  const deadline = Date.now() + timeoutMs

  let metaOnlyStreak = 0



  while (Date.now() < deadline) {

    const ports = listMtkComPorts()

    opts?.onPoll?.(ports)



    const preloaderPort = pickPreloaderPort(ports)

    const metaPort = pickMetaUsbPort(ports)



    if (preloaderPort) {

      return { preloaderPort, metaPort, recoverySuspected: false }

    }



    if (metaPort && ports.every(p => p.port === metaPort || !pickPreloaderPort([p]))) {

      metaOnlyStreak++

      if (metaOnlyStreak >= metaOnlyStablePolls) {

        return { metaPort, recoverySuspected: isAdbRecoveryMode() }

      }

    } else {

      metaOnlyStreak = 0

    }



    await sleep(pollMs)

  }

  return undefined

}



export async function waitForPreloaderComPort(opts?: {

  timeoutMs?: number

  pollMs?: number

  onPoll?: (ports: MtkComPortInfo[]) => void

}): Promise<string | undefined> {

  const r = await waitForMtkFactoryPort(opts)

  return r?.preloaderPort

}



export async function enterMetaViaPreloaderWait(

  onLog?: (line: string) => void,

): Promise<EnterMetaViaAdbResult> {

  const logs: string[] = []

  const log = (line: string) => {

    logs.push(line)

    onLog?.(line)

  }



  log('[preloader] 传音/MTK 进 META：请先完全关机')

  log('[preloader] 点击开始后插 USB。产线常用：仅按住 Vol+ 再插线')

  log('[preloader] 警告：同时按 Vol+ 与 Vol- 会进 Recovery，Recovery ≠ META，MetaCLI 无法校准')

  log('[preloader] 按键以 Modem Meta 图形界面 / RF 产线规范为准')

  log('[preloader] 等待 PreLoader 或 META USB 口（最多 120s）…')



  const detected = await waitForMtkFactoryPort({

    timeoutMs: 120_000,

    pollMs: 2500,

    onPoll: (ports) => {

      if (ports.length) {

        log(`[preloader] 扫描: ${ports.map(p => `${p.port}(${p.name})`).join(', ')}`)

      }

    },

  })



  if (!detected) {

    const reason = '未检测到 PreLoader / META 串口。请确认：① 已完全关机 ② 勿按 Vol± 进 Recovery ③ 按产线规范按键（常见为仅 Vol+）④ MTK USB 驱动已安装。'

    log(`[preloader] ${reason}`)

    return { ok: false, reason, logs }

  }



  if (detected.recoverySuspected) {

    const reason = 'ADB 显示手机在 Recovery（非 META）。Recovery 常由同时按 Vol+ 与 Vol- 触发。请长按电源关机后，改用仅 Vol+ 插 USB，或按 RF 产线规范进 META。'

    log(`[preloader] ${reason}`)

    return { ok: false, reason, logs }

  }



  const { preloaderPort, metaPort } = detected



  if (preloaderPort) {

    log(`[preloader] 检测到 PreLoader ${preloaderPort}`)

    let resolvedMeta = metaPort || pickMetaUsbPort(listMtkComPorts())

    if (!resolvedMeta) {

      log('[preloader] 等待 META USB 口（MediaTek USB Port，非 PreLoader）…')

      const deadline = Date.now() + 60_000

      while (Date.now() < deadline) {

        await sleep(2500)

        const ports = listMtkComPorts()

        if (ports.length) {

          log(`[preloader] 扫描: ${ports.map(p => `${p.port}(${p.name})`).join(', ')}`)

        }

        resolvedMeta = pickMetaUsbPort(ports)

        if (resolvedMeta) break

      }

    }

    if (resolvedMeta) {

      log(`[preloader] 使用 META 口 ${resolvedMeta} 直连（DUT in META Mode）`)

      return {

        ok: true,

        com_port: resolvedMeta,

        meta_direct: true,

        preloader_port: preloaderPort,

        logs,

      }

    }

    log('[preloader] 未见 META 口，MetaCLI 使用 Auto Connection 从 Preloader Boot')

    return {

      ok: true,

      com_port: 'Auto Connection',

      meta_direct: false,

      preloader_port: preloaderPort,

      logs,

    }

  }



  if (metaPort) {

    log(`[preloader] 仅见 META 口 ${metaPort}（无 PreLoader）`)

    log('[preloader] 若手机屏幕是 Recovery 菜单，请关机重试；META 模式通常无 Android/Recovery 界面')

    log(`[preloader] 尝试 META 直连 ${metaPort}（DUT in META Mode）`)

    return {

      ok: true,

      com_port: metaPort,

      meta_direct: true,

      logs,

    }

  }



  const reason = '检测到 MTK 口但无法判定 PreLoader / META，请手动选择「已在 META」并填写 COM 口。'

  log(`[preloader] ${reason}`)

  return { ok: false, reason, logs }

}



export async function waitForMetaComPort(opts?: {

  timeoutMs?: number

  pollMs?: number

  onPoll?: (ports: MtkComPortInfo[]) => void

}): Promise<string | undefined> {

  const timeoutMs = opts?.timeoutMs ?? 90_000

  const pollMs = opts?.pollMs ?? 2000

  const deadline = Date.now() + timeoutMs

  while (Date.now() < deadline) {

    const ports = listMtkComPorts()

    opts?.onPoll?.(ports)

    const picked = pickMetaPort(ports)

    if (picked) return picked

    await sleep(pollMs)

  }

  return undefined

}



/**

 * Android 已 ADB 连接但无 META 口：adb reboot meta → 等 COM → 供 MetaCLI 以 DUT in META Mode 直连。

 */

export async function enterMetaViaAdbAndWaitComPort(

  deviceId: string,

  onLog?: (line: string) => void,

): Promise<EnterMetaViaAdbResult> {

  const logs: string[] = []

  const log = (line: string) => {

    logs.push(line)

    onLog?.(line)

  }



  log(`[meta-boot] 通过 ADB 重启到 META: adb -s ${deviceId} reboot meta`)

  log('[meta-boot] 注意：传音量产机通常不支持 adb reboot meta，若重启后仍进 Android，请改用「Preloader 进 META」模式')

  const reboot = rebootMetaViaAdb(deviceId)

  if (!reboot.ok) {

    const reason = `adb reboot meta 失败: ${reboot.output || '未知错误'}。请确认工程版/工厂版支持该命令，或手动进 META 后填写 COM 口。`

    log(`[meta-boot] ${reason}`)

    return { ok: false, reason, logs }

  }

  log('[meta-boot] 已发送 reboot meta，等待手机重启并枚举 META USB 口（约 30–90s）…')



  const comPort = await waitForMetaComPort({

    timeoutMs: 90_000,

    pollMs: 2500,

    onPoll: (ports) => {

      if (ports.length) {

        log(`[meta-boot] 扫描串口: ${ports.map(p => `${p.port}(${p.name})`).join(', ')}`)

      }

    },

  })



  if (!comPort) {

    const reason = 'reboot meta 后未检测到 MTK META 串口。请在设备管理器确认 MediaTek USB Port / META VCOM 是否出现，并手动填写 COM 口。'

    log(`[meta-boot] ${reason}`)

    return { ok: false, reason, logs }

  }



  log(`[meta-boot] 检测到 META 口 ${comPort}，MetaCLI 将以 DUT in META Mode 直连（跳过 BROM Boot）`)

  return { ok: true, com_port: comPort, meta_direct: true, logs }

}


