/**
 * 编译阶段固定产物契约：Agent 必须落盘或打印可解析的 JSON。
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { dirname, join } from 'path'

export const BUILD_RESULT_SCHEMA_VERSION = 1

export interface BuildArtifactEntry {
  name: string
  path: string
  sizeBytes?: number
}

export interface BuildResultContract {
  schema_version: number
  status: 'pass' | 'fail'
  artifacts_dir?: string
  pkg_path?: string
  artifacts?: BuildArtifactEntry[]
  failed_stage?: string
  error?: string
  duration_ms?: number
  skill_id?: string
  notes?: string
}

const RESULT_FENCE_RE = /```(?:json)?\s*TAHP_BUILD_RESULT\s*([\s\S]*?)```/i
const RESULT_INLINE_RE = /TAHP_BUILD_RESULT\s*[:=]\s*(\{[\s\S]*\})/i

export function buildResultFilePath(runDir: string): string {
  return join(runDir, 'build-result.json')
}

export function ensureDir(path: string): void {
  if (!existsSync(path)) mkdirSync(path, { recursive: true })
}

export function writeBuildResult(filePath: string, result: BuildResultContract): void {
  ensureDir(dirname(filePath))
  writeFileSync(filePath, `${JSON.stringify(result, null, 2)}\n`, 'utf-8')
}

export function readBuildResultFile(filePath: string): BuildResultContract | null {
  if (!existsSync(filePath)) return null
  try {
    const raw = JSON.parse(readFileSync(filePath, 'utf-8')) as BuildResultContract
    if (!raw || (raw.status !== 'pass' && raw.status !== 'fail')) return null
    return normalizeBuildResult(raw)
  } catch {
    return null
  }
}

export function normalizeBuildResult(raw: Partial<BuildResultContract>): BuildResultContract {
  return {
    schema_version: Number(raw.schema_version) || BUILD_RESULT_SCHEMA_VERSION,
    status: raw.status === 'pass' ? 'pass' : 'fail',
    artifacts_dir: raw.artifacts_dir ? String(raw.artifacts_dir) : undefined,
    pkg_path: raw.pkg_path ? String(raw.pkg_path) : undefined,
    artifacts: Array.isArray(raw.artifacts) ? raw.artifacts : undefined,
    failed_stage: raw.failed_stage ? String(raw.failed_stage) : undefined,
    error: raw.error ? String(raw.error) : undefined,
    duration_ms: typeof raw.duration_ms === 'number' ? raw.duration_ms : undefined,
    skill_id: raw.skill_id ? String(raw.skill_id) : undefined,
    notes: raw.notes ? String(raw.notes) : undefined,
  }
}

export function parseBuildResultFromText(text: string): BuildResultContract | null {
  const fence = text.match(RESULT_FENCE_RE)
  const rawJson = fence?.[1] ?? text.match(RESULT_INLINE_RE)?.[1]
  if (!rawJson) return null
  try {
    const parsed = JSON.parse(rawJson.trim()) as Partial<BuildResultContract>
    return normalizeBuildResult(parsed)
  } catch {
    return null
  }
}

export function buildResultPromptBlock(resultPath: string): string {
  return `
# 编译结果输出（强制）
编译真正结束后，你必须同时做两件事：
1. 把结果写入文件：\`${resultPath}\`
2. 在最终回复中用如下 fenced block 再打印一遍（便于流水线兜底解析）

\`\`\`json
TAHP_BUILD_RESULT
{
  "schema_version": ${BUILD_RESULT_SCHEMA_VERSION},
  "status": "pass",
  "artifacts_dir": "<刷机包/镜像所在目录的绝对路径>",
  "pkg_path": "<可选：完整包或主镜像绝对路径>",
  "artifacts": [{ "name": "super.img", "path": "<绝对路径>" }],
  "skill_id": "<使用的 skill id>",
  "duration_ms": 0,
  "notes": "可选说明"
}
\`\`\`

失败时 \`status\` 必须为 \`"fail"\`，并填写 \`error\` / \`failed_stage\`。
没有产物路径时不得写 \`"pass"\`。

**结束回合前自检**：若尚未写入上述结果文件，禁止结束；禁止以「已提交后台 / 等待完成通知」作为最终回复。
`.trim()
}

/** 检测 Agent 是否以「后台等待」口吻结束而未交结果 */
export function looksLikeBackgroundWaitWithoutResult(text: string): boolean {
  const t = text.trim()
  if (!t) return false
  return /等待完成|提交后台|后台编译|等待通知|等待完成通知|正在并行编译中/.test(t)
    && !/TAHP_BUILD_RESULT/.test(t)
}
