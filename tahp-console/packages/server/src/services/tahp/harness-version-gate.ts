/**
 * Harness CLI 版本门禁：不满足 `.tahp/harness-requirement.json` 时拦截业务并引导配置检查。
 */
import { execFileSync } from 'child_process'
import { existsSync, readFileSync } from 'fs'
import { join } from 'path'
import { tahpPaths } from './paths'

export interface HarnessRequirement {
  minimum_cli: string
  channel?: string
  sop_doc?: string
  config_guidance?: string
}

export interface HarnessVersionGateResult {
  ok: boolean
  current: string | null
  required: string
  channel: string
  sopDoc: string
  userMessage: string
  /** 供 Agent 系统提示注入 */
  agentDirective: string
}

const DEFAULT_MINIMUM = '1.3.1'
const DEFAULT_SOP = 'docs/agent-npx-cli-sop.md'
const DEFAULT_GUIDANCE =
  '请打开「配置 → 一键配置表单」确认 harness 工具项后，点击「启动skill配置检查」，完成清单中的「Transsion Harness 安装」。'

export function harnessRequirementPath(): string {
  return join(tahpPaths.projectRoot, '.tahp', 'harness-requirement.json')
}

export function readHarnessRequirement(): HarnessRequirement {
  const p = harnessRequirementPath()
  if (!existsSync(p)) {
    return { minimum_cli: DEFAULT_MINIMUM, sop_doc: DEFAULT_SOP, config_guidance: DEFAULT_GUIDANCE }
  }
  try {
    const raw = JSON.parse(readFileSync(p, 'utf-8')) as Record<string, unknown>
    const minimum = typeof raw.minimum_cli === 'string' && raw.minimum_cli.trim()
      ? raw.minimum_cli.trim()
      : DEFAULT_MINIMUM
    return {
      minimum_cli: minimum,
      channel: typeof raw.channel === 'string' ? raw.channel : 'stable',
      sop_doc: typeof raw.sop_doc === 'string' ? raw.sop_doc : DEFAULT_SOP,
      config_guidance: typeof raw.config_guidance === 'string' ? raw.config_guidance : DEFAULT_GUIDANCE,
    }
  } catch {
    return { minimum_cli: DEFAULT_MINIMUM, sop_doc: DEFAULT_SOP, config_guidance: DEFAULT_GUIDANCE }
  }
}

/** 简易 semver 比较：a >= b */
export function semverGte(a: string, b: string): boolean {
  const pa = parseSemver(a)
  const pb = parseSemver(b)
  if (!pa || !pb) return false
  for (let i = 0; i < 3; i++) {
    if (pa[i] > pb[i]) return true
    if (pa[i] < pb[i]) return false
  }
  return true
}

function parseSemver(v: string): [number, number, number] | null {
  const m = String(v).trim().replace(/^v/i, '').match(/^(\d+)\.(\d+)\.(\d+)/)
  if (!m) return null
  return [Number(m[1]), Number(m[2]), Number(m[3])]
}

function probeHarnessCurrentVersion(): string | null {
  try {
    const out = execFileSync('harness', ['--json', 'version', 'check'], {
      encoding: 'utf-8',
      timeout: 20_000,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    const json = JSON.parse(out) as { current?: string; status?: string }
    if (typeof json.current === 'string' && json.current.trim()) return json.current.trim()
  } catch {
    /* fall through */
  }
  try {
    const out = execFileSync('harness', ['--version'], {
      encoding: 'utf-8',
      timeout: 10_000,
      windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    const m = String(out).match(/(\d+\.\d+\.\d+)/)
    if (m) return m[1]
  } catch {
    /* missing */
  }
  return null
}

function buildMessages(req: HarnessRequirement, current: string | null, ok: boolean): {
  userMessage: string
  agentDirective: string
} {
  const guidance = req.config_guidance || DEFAULT_GUIDANCE
  const sop = req.sop_doc || DEFAULT_SOP
  if (ok) {
    return {
      userMessage: `Harness CLI ${current} 满足最低要求 ${req.minimum_cli}。`,
      agentDirective: [
        '# Harness 版本门禁',
        `- 当前 CLI \`${current}\` ≥ 要求 \`${req.minimum_cli}\`，可继续使用 harness 能力。`,
        `- 官方 Skill 仅在本机客户端 skills 目录；SOP：\`${sop}\`。`,
      ].join('\n'),
    }
  }
  const cur = current ? `当前 \`${current}\`` : '当前未检测到可用的 `harness` CLI'
  const userMessage =
    `Harness 未就绪或版本过低（${cur}，要求 ≥ \`${req.minimum_cli}\`）。${guidance}`
  const agentDirective = [
    '# Harness 版本门禁（未通过 — 禁止继续业务）',
    `- ${cur}；要求 ≥ \`${req.minimum_cli}\`（见工程 \`.tahp/harness-requirement.json\`）。`,
    `- **立即停止**依赖 harness CLI / 官方 harness-* skill 的业务步骤。`,
    `- 引导用户：${guidance}`,
    `- SOP 相对工程根：\`${sop}\`（由「Transsion Harness 安装」配置项执行）。`,
    '- 不要手写共享盘 UNC 旧安装流程；不要在工程 `skills/` 下找官方 harness skill 副本。',
  ].join('\n')
  return { userMessage, agentDirective }
}

/** 检查本机 harness CLI 是否满足工程声明的最低版本 */
export function checkHarnessCliRequirement(opts?: {
  /** 测试注入当前版本 */
  currentOverride?: string | null
  skipProbe?: boolean
}): HarnessVersionGateResult {
  const req = readHarnessRequirement()
  const current = opts?.skipProbe
    ? (opts.currentOverride ?? null)
    : (opts?.currentOverride !== undefined ? opts.currentOverride : probeHarnessCurrentVersion())
  const ok = !!current && semverGte(current, req.minimum_cli)
  const { userMessage, agentDirective } = buildMessages(req, current, ok)
  return {
    ok,
    current,
    required: req.minimum_cli,
    channel: req.channel || 'stable',
    sopDoc: req.sop_doc || DEFAULT_SOP,
    userMessage,
    agentDirective,
  }
}

/**
 * 不满足则抛错（供 modem-baseline / gerrit-submit 等硬拦截）。
 * `transsion-harness-install` 安装流程本身不要调用此函数。
 */
export function assertHarnessCliReady(): void {
  const r = checkHarnessCliRequirement()
  if (!r.ok) throw new Error(r.userMessage)
}
