/**
 * monkey结果检查 — Node 侧 AI 富化。
 *
 * Python 用例（cases/monkey_check/tne/case1.py）完成 TNE 采集/解压后，
 * 把类型计数与各 native crash 的 android_crash_log 摘要写入
 * <会话resultDir>/monkey_check/result.json。
 * 本模块读取 result.json，用 callTahpLLM 对每条 crash 做模块归类，
 * 合成最终汇报文本（写回 caseResult.message）并落盘报告产物。
 *
 * 约束：该用例「始终 pass 仅汇报」——本模块任何失败只降级 message，绝不抛出。
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import { callTahpLLM } from './llm-caller'
import { logger } from '../logger'

const MONKEY_CHECK_DIR = 'monkey_check'
/** 单次最多参与 AI 归类的 crash 条数（超出部分不归类） */
const MAX_AI_CRASHES = 20
/** 每个模块最多贴出的 tne log 路径数（超出按时间取最近 N 份） */
const MAX_MODULE_TNE_PATHS = 5

interface MonkeyCheckCrash {
  tne_name: string
  crash_log_found: boolean
  excerpt: string
  excerpt_truncated?: boolean
  crash_log_path?: string
  decompress_error?: string
}

interface MonkeyCheckResultJson {
  version?: number
  tne_remote_dir?: string
  counts?: Record<string, number>
  native_crashes?: MonkeyCheckCrash[]
  errors?: string[]
}

const TNE_TYPE_LABELS: Record<string, string> = {
  '0xffffff39': 'native crash',
  '0xffffff04': 'KE',
  '0xffffff0d': 'HWT',
  '0xffffff0c': 'HANG',
  '0xffffff12': 'OOM',
  '0xffffff15': 'OCP_REBOOT',
}

function formatCounts(counts: Record<string, number>): string {
  const parts: string[] = []
  for (const [prefix, label] of Object.entries(TNE_TYPE_LABELS)) {
    const n = counts[prefix] ?? 0
    if (n > 0) parts.push(`${label} ${n}次`)
  }
  for (const [prefix, n] of Object.entries(counts)) {
    if (!(prefix in TNE_TYPE_LABELS) && n > 0) parts.push(`${prefix} ${n}次`)
  }
  return parts.join('，')
}

/** 从 LLM 输出中提取首个 JSON 数组 */
function extractJsonArray(raw: string): unknown[] | null {
  const text = String(raw || '')
  const start = text.indexOf('[')
  const end = text.lastIndexOf(']')
  if (start < 0 || end <= start) return null
  try {
    const parsed = JSON.parse(text.slice(start, end + 1))
    return Array.isArray(parsed) ? parsed : null
  } catch {
    return null
  }
}

/** 从 tne 文件名解析时间戳（0xffffff39_2026_09_22_10_00_00.tne）；无法解析时返回 0（排最后） */
function parseTneTime(tneName: string): number {
  const m = /_(\d{4})_(\d{2})_(\d{2})_(\d{2})_(\d{2})_(\d{2})(?:\.|$)/.exec(tneName)
  if (!m) return 0
  return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5]), Number(m[6]))
}

/** 调用 LLM 对每条 android_crash_log 摘要归类模块；失败抛错由调用方降级 */
async function classifyCrashModules(crashes: MonkeyCheckCrash[]): Promise<string[]> {
  const excerpts = crashes
    .map((c, i) => `【crash ${i + 1}】\n${c.excerpt}`)
    .join('\n\n')
  const system = '你是安卓 native crash 分析专家。根据用户提供的 android_crash_log 摘要，判断每条 crash 归属的模块（如 audio、display、camera、wifi、bt、gps、modem、sensor、system_server、surfaceflinger、kernel 等，取最贴切的一个，用小写英文单词或简短英文短语）。严格输出 JSON 数组，元素个数与输入条数一致，不要输出任何解释，例如 ["audio","display"]。'
  const user = `以下是 ${crashes.length} 条 android_crash_log 摘要，请逐条归类模块：\n\n${excerpts}`

  for (let attempt = 0; attempt < 2; attempt++) {
    const retryHint = attempt > 0 ? '\n\n上次输出无效，请严格输出 JSON 数组。' : ''
    const raw = await callTahpLLM(system, user + retryHint, { maxTokens: 1024 })
    const arr = extractJsonArray(raw)
    if (arr && arr.length === crashes.length && arr.every(x => typeof x === 'string' && String(x).trim())) {
      return arr.map(x => String(x).trim())
    }
  }
  throw new Error('LLM 返回内容无法解析为模块数组')
}

/**
 * 读取 Python 用例的 result.json 并合成最终汇报，写回 result.message。
 * resultDir 为会话结果目录（getSessionResultDir）。任何异常都被吞掉并保留原始 message。
 */
export async function applyMonkeyCheckAiReport(
  resultDir: string,
  result: { message: string },
): Promise<void> {
  try {
    const dir = join(resultDir, MONKEY_CHECK_DIR)
    const resultPath = join(dir, 'result.json')
    if (!existsSync(resultPath)) return

    const payload = JSON.parse(readFileSync(resultPath, 'utf-8')) as MonkeyCheckResultJson
    const counts = payload.counts ?? {}
    const allCrashes = payload.native_crashes ?? []
    const crashes = allCrashes.filter(c => c.crash_log_found && c.excerpt)

    const summary = formatCounts(counts)
    const lines: string[] = [summary ? `发现 ${summary}` : '未发现 KE/NE 等异常 log']

    if (allCrashes.length > 0) {
      if (crashes.length > 0) {
        try {
          const aiCrashes = crashes.slice(0, MAX_AI_CRASHES)
          const modules = await classifyCrashModules(aiCrashes)
          const agg = new Map<string, number>()
          const moduleTnes = new Map<string, { name: string; time: number }[]>()
          for (let i = 0; i < modules.length; i++) {
            const m = modules[i]
            agg.set(m, (agg.get(m) ?? 0) + 1)
            const list = moduleTnes.get(m) ?? []
            list.push({ name: aiCrashes[i].tne_name, time: parseTneTime(aiCrashes[i].tne_name) })
            moduleTnes.set(m, list)
          }
          const detail = [...agg.entries()].map(([m, n]) => `${m} ${n}次`).join('，')
          const truncated = crashes.length > MAX_AI_CRASHES ? `（仅前 ${MAX_AI_CRASHES} 条参与归类）` : ''
          lines.push(`native crash ${detail}${truncated}`)
          // 按模块贴出对应 tne log 路径；同模块超过 5 份时只贴最近时间的 5 份
          const remoteDir = String(payload.tne_remote_dir || '').replace(/\/+$/, '')
          for (const [m, list] of moduleTnes) {
            const sorted = [...list].sort((a, b) => b.time - a.time)
            for (const item of sorted.slice(0, MAX_MODULE_TNE_PATHS)) {
              lines.push(`  [${m}] ${remoteDir ? `${remoteDir}/` : ''}${item.name}`)
            }
            if (sorted.length > MAX_MODULE_TNE_PATHS) {
              lines.push(`  [${m}] 共 ${sorted.length} 份，仅贴出最近 ${MAX_MODULE_TNE_PATHS} 份`)
            }
          }
        } catch (e: any) {
          lines.push(`native crash ${crashes.length}次（AI 模块归类不可用：${e?.message || '未知原因'}）`)
        }
      } else {
        lines.push('native crash 解压内容中未找到 android_crash_log，无法归类模块')
      }
      const failed = allCrashes.filter(c => c.decompress_error).length
      if (failed > 0) lines.push(`另有 ${failed} 条 native crash 拉取/解压失败（详见产物目录）`)
    }

    const text = lines.join('\n')
    result.message = text
    try {
      mkdirSync(dir, { recursive: true })
      writeFileSync(join(dir, 'monkey_check_report.txt'), `${text}\n`, 'utf-8')
    } catch {
      // 报告产物写入失败不影响用例结果
    }
  } catch (e: any) {
    logger.warn({ err: e?.message }, '[monkey-check] AI 富化失败，保留原始汇报')
  }
}
