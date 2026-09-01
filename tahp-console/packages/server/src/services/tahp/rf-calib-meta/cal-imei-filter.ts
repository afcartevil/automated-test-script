/**
 * 校准 ini 中剥离 IMEI 相关段/键。
 * 传音等机型有 IMEI 保护，META 下读写 IMEI 会失败或被拒绝；
 * 备份/恢复默认不处理 IMEI（RF 校准数据与 IMEI 无关）。
 */
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { dirname, join } from 'path'

const IMEI_SECTION_RE = /^\s*\[([^\]]*IMEI[^\]]*)\]\s*$/i
const IMEI_KEY_RE = /^\s*IMEI\d*\s*=/i

/** 从校准 ini 文本中移除 IMEI 段及 IMEI/IMEI2… 键行 */
export function stripImeiFromCalIniText(content: string): { text: string; removed: number } {
  const lines = content.split(/\r?\n/)
  const out: string[] = []
  let inImeiSection = false
  let removed = 0

  for (const line of lines) {
    if (IMEI_SECTION_RE.test(line)) {
      inImeiSection = true
      removed += 1
      continue
    }
    if (inImeiSection) {
      if (/^\s*\[/.test(line)) {
        inImeiSection = false
      } else {
        removed += 1
        continue
      }
    }
    if (IMEI_KEY_RE.test(line)) {
      removed += 1
      continue
    }
    out.push(line)
  }

  return { text: out.join('\n'), removed }
}

/** 就地剥离；若无需改动返回 false */
export function stripImeiFromCalFile(filePath: string): { changed: boolean; removed: number } {
  if (!existsSync(filePath)) return { changed: false, removed: 0 }
  const raw = readFileSync(filePath, 'utf-8')
  const { text, removed } = stripImeiFromCalIniText(raw)
  if (removed === 0) return { changed: false, removed: 0 }
  writeFileSync(filePath, text, 'utf-8')
  return { changed: true, removed }
}

/**
 * 恢复前生成无 IMEI 的临时校准文件，避免 MetaCLI Download 写 IMEI。
 * 返回临时路径（可能与源相同若无需剥离）。
 */
export function prepareRestoreCalFileWithoutImei(
  sourcePath: string,
  workDir: string,
  runId: string,
): { path: string; stripped: boolean; removed: number } {
  if (!existsSync(sourcePath)) {
    return { path: sourcePath, stripped: false, removed: 0 }
  }
  const raw = readFileSync(sourcePath, 'utf-8')
  const { text, removed } = stripImeiFromCalIniText(raw)
  if (removed === 0) {
    return { path: sourcePath, stripped: false, removed: 0 }
  }
  if (!existsSync(workDir)) mkdirSync(workDir, { recursive: true })
  const dest = join(workDir, `${runId}-no-imei.ini`)
  writeFileSync(dest, text, 'utf-8')
  return { path: dest, stripped: true, removed }
}

/** 测试用：复制后剥离 */
export function copyAndStripImei(src: string, dest: string): number {
  const dir = dirname(dest)
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  copyFileSync(src, dest)
  return stripImeiFromCalFile(dest).removed
}
