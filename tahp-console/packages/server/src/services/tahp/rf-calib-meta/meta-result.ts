/**
 * 解析 MetaCLI stdout，判断备份/恢复是否真正执行。
 * MetaCLI 在「仅 IMEI 读取失败」时仍会 SaveToFile 写出 RF 校准 ini，但退出码非 0；
 * 对此按成功处理（IMEI 默认排除，不弹警告）。
 */
import type { RfCalibMetaMode } from './types'

export interface MetaCliActionAssessment {
  ok: boolean
  reason?: string
  /** 成功但有非致命问题（非 IMEI 默认排除场景）时的提示 */
  warning?: string
  /** 仅 IMEI 失败导致 MetaCLI 非 0 退出时，仍视为成功 */
  allowNonZeroExit?: boolean
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

/** 仅 IMEI（等非 RF 项）失败，且已写出 RF 校准数据 → 视为可用备份 */
export function isImeiOnlyBackupFailure(text: string): boolean {
  const failed = listFailedReadItems(text)
  if (failed.length === 0) return false
  if (!failed.every(n => /^IMEI\d*$/i.test(n))) return false
  const uploaded = /Upload and save calibration data start/i.test(text)
  const wrote = /Start writing the data to file|Write Category:.*Done|IniFlush Done/i.test(text)
  // 兼容旧格式 `GSM Item(14)` 与新格式 `GSM(14)`
  const rfRead = /Read Category:\s*(GSM|WCDMA|LTE|NR)(\s+Item)?\s*\(/i.test(text)
  const rfWrite = /Write Category:\s*(GSM|WCDMA|LTE|NR)(\s+Item)?\s*\([^)]*\).*Done/i.test(text)
    || /Write Category:\s*(GSM|WCDMA|LTE|NR).*item:.*Done/i.test(text)
  return uploaded && wrote && rfRead && rfWrite
}

const IMEI_SKIP_NOTE = '← 已默认跳过（不备份/不还原 IMEI）'

/** 将 MetaCLI 的 IMEI Failed / 相关 Error 标注为「默认跳过」，避免误判 */
export function annotateMetaCliLogLine(line: string): string {
  const t = line.trim()
  if (/item:\s*IMEI\d*\s+Failed/i.test(t)) {
    return `${line}  ${IMEI_SKIP_NOTE}`
  }
  if (/There are items reading from target failed/i.test(t)) {
    return `${line}  ${IMEI_SKIP_NOTE}`
  }
  if (/Backup flow failed in step1:\s*upload from target failed/i.test(t)) {
    return `${line}  ${IMEI_SKIP_NOTE}`
  }
  if (/Backup flow failed in step2:\s*save to file failed/i.test(t)) {
    return `${line}  ${IMEI_SKIP_NOTE}`
  }
  if (/Upload and save calibration data failed/i.test(t)) {
    return `${line}  ${IMEI_SKIP_NOTE}`
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
        return { ok: true, allowNonZeroExit: true }
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
        return { ok: true, allowNonZeroExit: true }
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
