/**
 * 烧录 harness 路径：Agent + 用户目录 harness skill
 * - 整包：build_context.flash_skill_id（默认本机 asf-device / harness-device）
 * - 单镜像：harness-flash-single-img（用户目录优先，工程 skills 回退）
 */
import { existsSync } from 'fs'
import { randomBytes } from 'crypto'
import { join } from 'path'
import { logger } from '../../logger'
import {
  AgentBridgeClient,
  getAgentBridgeManager,
  type AgentBridgeChatStarted,
  type AgentBridgeOutput,
} from '../../hermes/agent-bridge'
import { filterBridgeToolCallMarkupDelta } from '../../hermes/run-chat/bridge-delta'
import { assertHarnessCliReady } from '../harness-version-gate'
import { humanizeAgentError } from '../adapt-agent-health'
import { tahpPaths } from '../paths'
import {
  defaultFlashSkillId,
  resolveUserHarnessSkillPath,
} from './harness-skill-registry'

const bridgeClient = new AgentBridgeClient({ timeoutMs: 2 * 60 * 60_000 })

export type HarnessFlashMode = 'full_rom' | 'single_img'

export interface HarnessFlashInput {
  pipelineRunId: string
  mode: HarnessFlashMode
  deviceId: string
  /** 整包刷机 skill（默认本机 asf-device / harness-device） */
  flashSkillId?: string
  /** 整包：ROM 目录/zip/scatter */
  romPath?: string
  /** 单镜像源路径 */
  imgPath?: string
  partition?: string
  variant?: string
}

export interface HarnessFlashResult {
  success: boolean
  error?: string
  skillId: string
  logs: string[]
}

function resolveSingleImgSkillPath(skillId: string): string | null {
  return resolveUserHarnessSkillPath(skillId)
    ?? (existsSync(join(tahpPaths.skillsDir, skillId, 'SKILL.md'))
      ? join(tahpPaths.skillsDir, skillId, 'SKILL.md')
      : null)
}

function resolveFlashSkill(
  mode: HarnessFlashMode,
  flashSkillId?: string,
): { skillId: string; skillPath: string } {
  if (mode === 'single_img') {
    const skillId = 'harness-flash-single-img'
    const skillPath = resolveSingleImgSkillPath(skillId)
    if (!skillPath) {
      throw new Error(`未找到单镜像刷机 Skill：${skillId}`)
    }
    return { skillId, skillPath }
  }
  const skillId = flashSkillId?.trim() || defaultFlashSkillId()
  const skillPath = resolveUserHarnessSkillPath(skillId)
  if (!skillPath) {
    throw new Error(
      `未找到刷机 Skill：${skillId}（请在用户 skill 目录安装，例如执行 asf install 或 harness install）`,
    )
  }
  return { skillId, skillPath }
}

function buildInstructions(input: HarnessFlashInput, skillId: string, skillPath: string): string {
  if (input.mode === 'single_img') {
    return `
你是 TAHP 适配流水线的单镜像刷机助手。必须严格按 Skill 执行。

# Skill
- Skill ID: \`${skillId}\`
- Skill 路径: \`${skillPath}\`
- 先 Read 该 SKILL.md，再按其中步骤执行（staging → dry-run → flash → 清理）

# 参数
- sn: ${input.deviceId}
- img_path: ${input.imgPath}
- partition: ${input.partition}

# 纪律
1. 不要跑 plugin route flash
2. 不要直接拼 fastboot/adb
3. 信息齐全后自动执行，不要向用户确认
4. 结束后在回复中用如下块报告结果：

\`\`\`json
TAHP_FLASH_RESULT
{"status":"pass","skill_id":"${skillId}"}
\`\`\`
失败时 status 为 fail，并填 error。
`.trim()
  }

  return `
你是 TAHP 适配流水线的整包刷机助手。必须严格按 Skill 执行。

# Skill
- Skill ID: \`${skillId}\`
- Skill 路径: \`${skillPath}\`
- 先 Read 该 SKILL.md，再执行 harness device flash

# 参数
- sn: ${input.deviceId}
- rom-path: ${input.romPath}
- variant: ${input.variant ?? ''}

# 纪律
1. 先 dry-run，再正式刷入
2. 默认 --backend auto
3. 不要直接拼 fastboot/adb/SP Flash Tool
4. 结束后报告：

\`\`\`json
TAHP_FLASH_RESULT
{"status":"pass","skill_id":"${skillId}"}
\`\`\`
失败时 status 为 fail，并填 error。
`.trim()
}

const FLASH_RESULT_RE = /```(?:json)?\s*TAHP_FLASH_RESULT\s*([\s\S]*?)```/i

function parseFlashResult(text: string): { status: 'pass' | 'fail'; error?: string } | null {
  const m = text.match(FLASH_RESULT_RE)
  if (!m?.[1]) {
    if (/TAHP_FLASH_RESULT[\s\S]*?"status"\s*:\s*"pass"/i.test(text)) {
      return { status: 'pass' }
    }
    if (/TAHP_FLASH_RESULT[\s\S]*?"status"\s*:\s*"fail"/i.test(text)) {
      return { status: 'fail', error: 'harness 刷机失败' }
    }
    return null
  }
  try {
    const raw = JSON.parse(m[1].trim()) as { status?: string; error?: string }
    if (raw.status === 'pass') return { status: 'pass' }
    return { status: 'fail', error: raw.error || 'harness 刷机失败' }
  } catch {
    return null
  }
}

export async function probeHarnessFlash(
  skillId?: string,
): Promise<{ available: boolean; reason?: string }> {
  const id = skillId?.trim() || defaultFlashSkillId()
  try {
    assertHarnessCliReady()
  } catch (err) {
    return { available: false, reason: (err as Error).message }
  }
  if (!getAgentBridgeManager().running) {
    return { available: false, reason: 'Agent Bridge 未就绪' }
  }
  if (!resolveUserHarnessSkillPath(id)) {
    return {
      available: false,
      reason: `未找到刷机 Skill：${id}（请在用户 skill 目录安装）`,
    }
  }
  return { available: true }
}

export async function runHarnessFlash(
  input: HarnessFlashInput,
  onLog?: (line: string) => void,
): Promise<HarnessFlashResult> {
  const logs: string[] = []
  const log = (line: string) => {
    logs.push(line)
    onLog?.(line)
  }

  let skillId = ''
  try {
    const resolved = resolveFlashSkill(input.mode, input.flashSkillId)
    skillId = resolved.skillId
    if (input.mode === 'single_img') {
      if (!input.imgPath) throw new Error('单镜像刷机缺少 imgPath')
      if (!input.partition) throw new Error('单镜像刷机缺少 partition')
      if (!existsSync(resolved.skillPath)) {
        throw new Error(`未找到单镜像 Skill：${skillId}`)
      }
    } else if (!input.romPath) {
      throw new Error('整包刷机缺少 romPath')
    }

    assertHarnessCliReady()
    const manager = getAgentBridgeManager()
    if (!manager.running) throw new Error('Agent Bridge 未运行')

    const sessionId = `tahp-pipeline-flash-${Date.now()}-${randomBytes(2).toString('hex')}`
    const instructions = buildInstructions(input, resolved.skillId, resolved.skillPath)
    const userMessage = input.mode === 'single_img'
      ? `# 单镜像刷机\nsn=${input.deviceId}\nimg=${input.imgPath}\npartition=${input.partition}`
      : `# 整包刷机\nsn=${input.deviceId}\nrom-path=${input.romPath}\nvariant=${input.variant ?? ''}\nskill=${resolved.skillId}`

    log(`启动 harness 刷机 Agent skill=${resolved.skillId}`)
    const started: AgentBridgeChatStarted = await bridgeClient.chat(
      sessionId,
      userMessage,
      undefined,
      instructions,
      'default',
    )

    const markupState: { bridgePendingToolCallMarkup?: string } = {}
    let full = ''

    for await (const chunk of bridgeClient.streamOutput(started.run_id, { intervalMs: 500 })) {
      const out = chunk as AgentBridgeOutput
      if (out.delta) {
        const cleaned = filterBridgeToolCallMarkupDelta(markupState, out.delta)
        if (cleaned) {
          full += cleaned
          const line = cleaned.trim()
          if (line) log(line.slice(0, 500))
        }
      }
      if (out.done) {
        if (out.status === 'error') throw new Error(humanizeAgentError(out.error || 'Agent 出错'))
        if (out.status === 'interrupted') throw new Error('刷机 Agent 被中断')
        break
      }
    }

    const parsed = parseFlashResult(full)
    if (parsed?.status === 'pass') {
      return { success: true, skillId, logs }
    }
    if (parsed?.status === 'fail') {
      return { success: false, skillId, logs, error: parsed.error }
    }
    if (/刷机完成|flash.*success|"status"\s*:\s*"ok"/i.test(full)) {
      return { success: true, skillId, logs }
    }
    return { success: false, skillId, logs, error: '未解析到 TAHP_FLASH_RESULT，视为失败' }
  } catch (err) {
    const message = (err as Error).message
    logger.warn({ err: message, skillId }, '[harness-flash] failed')
    log(message)
    return { success: false, skillId: skillId || 'unknown', logs, error: message }
  }
}
