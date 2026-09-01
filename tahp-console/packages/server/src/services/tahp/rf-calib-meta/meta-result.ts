/**
 * 解析 MetaCLI stdout，判断备份/恢复是否真正执行。
 * MetaCLI 在「仅 IMEI 读取失败」时仍会 SaveToFile 写出 RF 校准 ini，但退出码非 0；
 * 对此按成功（带警告）处理，避免界面误报整单失败。
 */
import type { RfCalibMetaMode } from './types'

export interface MetaCliActionAssessment {
  ok: boolean
  reason?: string
  /** 成功但有非致命问题（如 IMEI 读失败）时的提示 */
  warning?: string
}

function listFailedReadItems(text: string): string[] {
  const items: string[] = []
  const re = /item:\s*([^\r\n]+?)\s+Failed/gi
  let m: RegExpExecArray | null
  while ((m = re.exec(text)) !== null) {
    const name = m[1].trim()
    if (name && !items.includes(name)) items.push(name)
  }
  return items
}

/** 仅 IMEI（等非 RF 项）失败，且已写出校准文件 → 视为可用备份 */
export function isImeiOnlyBackupFailure(text: string): boolean {
  const failed = listFailedReadItems(text)
  if (failed.length === 0) return false
  if (!failed.every(n => /^IMEI\d*$/i.test(n))) return false
  const uploaded = /Upload and save calibration data start/i.test(text)
  const wrote = /Start writing the data to file|Write Category:.*Done|IniFlush Done/i.test(text)
  const rfOk = /Read Category:\s*(GSM|WCDMA|LTE|NR)\s+Item/i.test(text)
    && /item:.*Done/i.test(text)
  return uploaded && wrote && rfOk
}

const IMEI_IGNORE_NOTE = '← IMEI 保护导致，可忽略（RF 校准不受影响）'

/** 给 MetaCLI 因 IMEI 打出的 Error/Failed 行加注释，避免误判整单失败 */
export function annotateMetaCliLogLine(line: string): string {
  const t = line.trim()
  if (/item:\s*IMEI\d*\s+Failed/i.test(t)) {
    return `${line}  ${IMEI_IGNORE_NOTE}`
  }
  if (/There are items reading from target failed/i.test(t)) {
    return `${line}  ${IMEI_IGNORE_NOTE}`
  }
  if (/Backup flow failed in step1:\s*upload from target failed/i.test(t)) {
    return `${line}  ${IMEI_IGNORE_NOTE}`
  }
  if (/Upload and save calibration data failed/i.test(t)) {
    return `${line}  ${IMEI_IGNORE_NOTE}`
  }
  return line
}

export function assessMetaCliActionFromLogs(
  lines: string[],
  mode: RfCalibMetaMode,
): MetaCliActionAssessment {
  const text = lines.join('\n')

  if (/ModemAction section check failed/i.test(text)) {
    return {
      ok: false,
      reason: 'MetaCLI ModemAction 段校验失败。请确认 init 含 [Modem1Action1] 与 OutputCalibrationDataFilePath（须为 .ini 文件）。',
    }
  }
  if (/UpdateParemeter upload and save skip|upload and save skip/i.test(text)) {
    return {
      ok: false,
      reason: 'MetaCLI 跳过了 Upload and Save（未执行备份）。请检查 OutputCalibrationDataFilePath 是否有效。',
    }
  }

  if (mode === 'backup') {
    const connected = /Connect target success/i.test(text)
    const uploaded = /Upload and save calibration data (start|done)/i.test(text)
    if (connected && !uploaded) {
      return {
        ok: false,
        reason: 'MetaCLI 仅完成连接/断开，未执行 Upload and Save。请确认 init 段名为 [Modem1Action1]，且含 OutputCalibrationDataFilePath。',
      }
    }

    if (/Upload and save calibration data failed|Backup flow failed/i.test(text)) {
      if (isImeiOnlyBackupFailure(text)) {
        return {
          ok: true,
          warning: 'RF 校准已备份；IMEI 已默认排除（机型保护）。MetaCLI 仍可能尝试读 IMEI 并打出 Failed，可忽略。',
        }
      }
      const failed = listFailedReadItems(text)
      return {
        ok: false,
        reason: failed.length
          ? `MetaCLI 校准备份失败：读取失败项 ${failed.join(', ')}。若输出 ini 已生成可人工核验；RF 项失败需重试或检查连接。`
          : 'MetaCLI 校准备份失败（Upload and save failed）。请核对输出路径与设备 META 连接。',
      }
    }
  }

  if (mode === 'restore') {
    const connected = /Connect target success/i.test(text)
    // MetaCLI 恢复日志实际为 Write calibration file start/done + Write Category
    const restored = /Write calibration file (start|done)|Write Category:.*Done|download calibration|Load and download/i.test(text)
    if (connected && !restored) {
      return {
        ok: false,
        reason: 'MetaCLI 仅完成连接/断开，未执行恢复下载。请检查 CalibrationFilePath。',
      }
    }
    if (/Write calibration file failed|download.*failed|Restore flow failed/i.test(text)
      && !/Write calibration file done/i.test(text)) {
      const failed = listFailedReadItems(text)
      if (failed.length && failed.every(n => /^IMEI\d*$/i.test(n)) && /Write Category:.*Done/i.test(text)) {
        return {
          ok: true,
          warning: 'RF 校准已恢复；IMEI 已默认排除（机型保护）。',
        }
      }
      return {
        ok: false,
        reason: failed.length
          ? `MetaCLI 校准恢复失败：失败项 ${failed.join(', ')}`
          : 'MetaCLI 校准恢复失败。请核对 CalibrationFilePath 与设备连接。',
      }
    }
  }

  return { ok: true }
}
