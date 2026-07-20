/**
 * AI 自检 — 手动新增 NL 手机 UI 自动化用例（方案 A：callTahpLLM → 固定动作 schema → Python 执行器）
 */
import { callTahpLLM } from './llm-caller'
import { logger } from '../logger'
import {
  loadDurableAiGeneratedConfig,
  loadDurableCaseInfo,
  mirrorAiGeneratedCasesToRuntime,
  saveDurableAiGeneratedConfig,
  saveDurableCaseInfo,
  writeDurableCasePlan,
  writeDurableCasePython,
} from './ai-generated-case-store'
import {
  AI_GENERATED_MODULE,
  AI_GENERATED_MODULE_LABEL,
  AI_GENERATED_TEST_TYPE,
} from './gerrit-ai-generated-cases'

const ALLOWED_OPS = new Set([
  'wake',
  'home',
  'back',
  'shell',
  'tap_text',
  'tap_desc',
  'tap_rid',
  'swipe',
  'wait',
  'wait_until',
  'dial_keys',
  'assert_text',
  'assert_desc',
  'screenshot',
  'uidump',
])

const DIAL_KEYS_ALLOWED = /^[0-9*#+]+$/
const DIAL_KEYS_MAX_LEN = 32
const TAP_RID_ALLOWED = /^[A-Za-z0-9._:/-]+$/
const TAP_RID_MAX_LEN = 128

const WAIT_UNTIL_CONDITIONS = new Set([
  'text_present',
  'text_gone',
  'desc_present',
  'desc_gone',
  'clickable',
])

const SHELL_PREFIX_WHITELIST = [
  'am start',
  'am force-stop',
  'input keyevent',
  'input tap',
  'input swipe',
  'input text',
  'uiautomator',
  'settings put',
  'settings get',
  'cmd statusbar',
  'monkey',
]

const SHELL_FORBIDDEN = /\b(rm\s|reboot|dd\s|mkfs|format|shutdown|poweroff|su\s|chmod\s|chown\s|pm\s+uninstall|pm\s+clear\s)/i

const NL_UI_CASE_PY_TEMPLATE = `def run(category=None, case_index=None, device_info=None, **context):
    from utils.nl_ui.executor import run_plan_for_case
    return run_plan_for_case(case_index, device_info, context)
`

export interface NlUiActionPlan {
  executable: boolean
  reason?: string
  steps: Array<Record<string, unknown>>
}

export interface CreatedNlUiCase {
  caseKey: string
  caseIndex: number
  caseName: string
  moduleLabel: string
  execMode: 'nl_ui'
  nlDescription: string
  expectedResult: string
  plan: NlUiActionPlan
}

interface AiCaseConfigEntry {
  caseIndex: number
  caseName: string
  mode: string
  canReuse: boolean
  execMode?: 'manual' | 'nl_ui'
}

interface AiGeneratedCaseConfig {
  testType: string
  module: string
  moduleLabel: string
  conditions: { dutSimCount: number; auxRequired: number; auxSimCount: number }
  defaultCaseMode: string
  cases: AiCaseConfigEntry[]
}

function loadAiConfig(): AiGeneratedCaseConfig {
  return loadDurableAiGeneratedConfig()
}

function saveAiConfig(config: AiGeneratedCaseConfig): void {
  saveDurableAiGeneratedConfig(config)
}

function loadCaseInfo(): Array<Record<string, unknown>> {
  return loadDurableCaseInfo()
}

function saveCaseInfo(info: Array<Record<string, unknown>>): void {
  saveDurableCaseInfo(info)
}

function nextCaseIndex(config: AiGeneratedCaseConfig): number {
  if (!config.cases.length) return 1
  return Math.max(...config.cases.map(c => c.caseIndex)) + 1
}

function extractJsonObject(text: string): Record<string, unknown> | null {
  const trimmed = text.trim()
  const fenceMatch = trimmed.match(/```(?:json)?\s*([\s\S]*?)```/i)
  const candidate = fenceMatch ? fenceMatch[1].trim() : trimmed
  const start = candidate.indexOf('{')
  const end = candidate.lastIndexOf('}')
  if (start < 0 || end <= start) return null
  try {
    const parsed = JSON.parse(candidate.slice(start, end + 1))
    return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : null
  } catch {
    return null
  }
}

function validateShellCmd(cmd: string): string | null {
  const normalized = cmd.trim()
  if (!normalized) return 'shell 命令不能为空'
  if (SHELL_FORBIDDEN.test(normalized)) return `禁止的 shell 命令: ${normalized}`
  const lower = normalized.toLowerCase()
  if (!SHELL_PREFIX_WHITELIST.some(prefix => lower.startsWith(prefix))) {
    return `shell 命令不在白名单: ${normalized}`
  }
  return null
}

export function validateNlUiPlan(raw: unknown): { ok: true; plan: NlUiActionPlan } | { ok: false; error: string } {
  if (!raw || typeof raw !== 'object') {
    return { ok: false, error: '动作计划必须是 JSON 对象' }
  }
  const obj = raw as Record<string, unknown>
  if (obj.executable === false) {
    return {
      ok: false,
      error: String(obj.reason || '该用例无法使用手机 UI 自动化执行'),
    }
  }
  if (!Array.isArray(obj.steps) || obj.steps.length === 0) {
    return { ok: false, error: '动作计划缺少 steps' }
  }
  const steps: Array<Record<string, unknown>> = []
  for (let i = 0; i < obj.steps.length; i++) {
    const step = obj.steps[i]
    if (!step || typeof step !== 'object') {
      return { ok: false, error: `第 ${i + 1} 步格式无效` }
    }
    const record = step as Record<string, unknown>
    const op = String(record.op || '').trim()
    if (!ALLOWED_OPS.has(op)) {
      return { ok: false, error: `第 ${i + 1} 步含不支持的操作: ${op || '(空)'}` }
    }
    if (record.optional != null) {
      record.optional = Boolean(record.optional)
    }
    if (op === 'shell') {
      const cmd = String(record.cmd || '')
      const err = validateShellCmd(cmd)
      if (err) return { ok: false, error: `第 ${i + 1} 步: ${err}` }
      if (/input\s+text/i.test(cmd) && /[*#]/.test(cmd)) {
        return {
          ok: false,
          error: `第 ${i + 1} 步禁止用 input text 输入含 */# 的工程码，请改用 dial_keys`,
        }
      }
    }
    if ((op === 'tap_text' || op === 'assert_text') && !String(record.text || '').trim()) {
      return { ok: false, error: `第 ${i + 1} 步缺少 text` }
    }
    if ((op === 'tap_desc' || op === 'assert_desc') && !String(record.desc || record['content-desc'] || '').trim()) {
      return { ok: false, error: `第 ${i + 1} 步缺少 desc/content-desc` }
    }
    if (op === 'tap_rid') {
      const rid = String(record.rid || record['resource-id'] || record.resourceId || '').trim()
      if (!rid) {
        return { ok: false, error: `第 ${i + 1} 步 tap_rid 缺少 rid` }
      }
      if (rid.length > TAP_RID_MAX_LEN) {
        return { ok: false, error: `第 ${i + 1} 步 tap_rid 过长（最多 ${TAP_RID_MAX_LEN}）` }
      }
      if (!TAP_RID_ALLOWED.test(rid)) {
        return { ok: false, error: `第 ${i + 1} 步 tap_rid 含不支持字符` }
      }
      record.rid = rid
    }
    if (op === 'wait') {
      const seconds = Number(record.seconds ?? record.ms ? Number(record.ms) / 1000 : 1)
      if (!Number.isFinite(seconds) || seconds < 0 || seconds > 120) {
        return { ok: false, error: `第 ${i + 1} 步 wait 时长无效` }
      }
      record.seconds = seconds
    }
    if (op === 'wait_until') {
      const condition = String(record.condition || '').trim()
      if (!WAIT_UNTIL_CONDITIONS.has(condition)) {
        return {
          ok: false,
          error: `第 ${i + 1} 步 wait_until.condition 无效，允许: ${[...WAIT_UNTIL_CONDITIONS].join(', ')}`,
        }
      }
      record.condition = condition
      if ((condition === 'text_present' || condition === 'text_gone' || condition === 'clickable')
        && !String(record.text || '').trim()) {
        return { ok: false, error: `第 ${i + 1} 步 wait_until 缺少 text` }
      }
      if ((condition === 'desc_present' || condition === 'desc_gone')
        && !String(record.desc || record['content-desc'] || '').trim()) {
        return { ok: false, error: `第 ${i + 1} 步 wait_until 缺少 desc` }
      }
      const timeout = Number(record.timeout ?? record.seconds ?? 30)
      if (!Number.isFinite(timeout) || timeout <= 0 || timeout > 300) {
        return { ok: false, error: `第 ${i + 1} 步 wait_until.timeout 无效（1-300s）` }
      }
      record.timeout = timeout
      const poll = Number(record.poll ?? 0.5)
      if (!Number.isFinite(poll) || poll <= 0 || poll > 10) {
        return { ok: false, error: `第 ${i + 1} 步 wait_until.poll 无效` }
      }
      record.poll = poll
    }
    if (op === 'dial_keys') {
      const keys = String(record.keys || record.text || '').trim()
      if (!keys) {
        return { ok: false, error: `第 ${i + 1} 步 dial_keys 缺少 keys` }
      }
      if (keys.length > DIAL_KEYS_MAX_LEN) {
        return { ok: false, error: `第 ${i + 1} 步 dial_keys 过长（最多 ${DIAL_KEYS_MAX_LEN}）` }
      }
      if (!DIAL_KEYS_ALLOWED.test(keys)) {
        return { ok: false, error: `第 ${i + 1} 步 dial_keys 仅支持 0-9 * # +` }
      }
      record.keys = keys
    }
    if (op === 'swipe') {
      const direction = String(record.direction || 'up').toLowerCase()
      if (!['up', 'down', 'left', 'right'].includes(direction)) {
        return { ok: false, error: `第 ${i + 1} 步 swipe 方向无效` }
      }
      record.direction = direction
    }
    steps.push(record)
  }
  const hasAssert = steps.some(s => {
    const op = String(s.op)
    return op === 'assert_text' || op === 'assert_desc'
  })
  if (!hasAssert) {
    return { ok: false, error: '动作计划必须包含至少一步 UI 断言（assert_text 或 assert_desc）' }
  }
  return {
    ok: true,
    plan: { executable: true, reason: String(obj.reason || ''), steps },
  }
}

function buildPlanningPrompt(caseName: string, nlDescription: string, expectedResult?: string): { system: string; user: string } {
  const system = `你是 TAHP AI 自检平台的 Android UI 自动化规划助手。根据用户自然语言描述，输出 JSON 动作计划。

必须遵守：
1. 只输出一个 JSON 对象，不要 markdown 包裹外的解释。
2. 若无法用 adb/uiautomator/界面层级文案完成验证，设置 executable=false 并在 reason 说明原因（如：需插拔 SIM、双机对测、外设、需人工主观评价等）。
3. 可执行时 executable=true，steps 为白名单操作数组。
4. 允许的 op：wake, home, back, shell, tap_text, tap_desc, tap_rid, swipe, wait, wait_until, dial_keys, assert_text, assert_desc, screenshot, uidump
5. shell 仅允许：am start, am force-stop, input keyevent/tap/swipe/text, uiautomator, settings put/get, cmd statusbar, monkey
6. 必须包含至少一步 assert_text 或 assert_desc 验证期望 UI 状态。
7. 打开系统设置常用：{"op":"shell","cmd":"am start -a android.settings.SETTINGS"}
8. tap_text 可带 scroll:true 表示找不到时下滑查找。同文案存在标题与按钮时，执行器会优先点击可点按钮。
9. 可选步骤：对「可能出现也可能不出现」的弹窗/控件，使用 optional:true。找不到控件时跳过，不失败。示例：{"op":"tap_text","text":"确认","optional":true}
10. 等待条件：用 wait_until，不要用复杂分支。
    - 等待文案出现：{"op":"wait_until","condition":"text_present","text":"通过","timeout":30}
    - 等待按钮可点：{"op":"wait_until","condition":"clickable","text":"校准","timeout":30}
    - condition 允许：text_present, text_gone, desc_present, desc_gone, clickable
11. 颜色无法通过 UI 层级判断：不要因「绿色/红色」拒绝用例。用 assert_text 校验文案「通过」或「失败」即可。
12. 「如果出现弹窗则点确认」应规划为 optional 点击，不要判定为不可执行。
13. 工程码 / 拨号盘「模拟点击输入」（含 * #，如 *#888#、*#*#4636#*#*）：
    - 必须用 dial_keys 逐键点击拨号盘，禁止用 shell input text。
    - 示例：先打开拨号盘 {"op":"shell","cmd":"am start -a android.intent.action.DIAL"}，再 {"op":"wait_until","condition":"text_present","text":"1","timeout":10}，再 {"op":"dial_keys","keys":"*#888#"}
    - 禁止：{"op":"shell","cmd":"input text \\"*#888#\\""}
14. 点击「按钮」且描述要求「可点击后再点」时：先 wait_until clickable，再 tap_text。示例：
    {"op":"wait_until","condition":"clickable","text":"校准","timeout":30},
    {"op":"tap_text","text":"校准"}
15. 拨号盘输入号码后，若拨号按钮只有图标、无 text/content-desc，但用户提供了 resource-id / ui id，必须用 tap_rid：
    - 示例：{"op":"shell","cmd":"am start -a android.intent.action.DIAL"}
    - 示例：{"op":"dial_keys","keys":"18676785952"}
    - 示例：{"op":"tap_rid","rid":"dialpad_floating_action_button"}
    - 禁止：因拨号按钮无文字就判定不可执行；也禁止用 tap_text 点纯图标按钮

输出 schema:
{
  "executable": true,
  "reason": "",
  "steps": [
    { "op": "wake" },
    { "op": "shell", "cmd": "am start -a android.intent.action.DIAL" },
    { "op": "wait_until", "condition": "text_present", "text": "1", "timeout": 10 },
    { "op": "dial_keys", "keys": "18676785952" },
    { "op": "tap_rid", "rid": "dialpad_floating_action_button" },
    { "op": "assert_text", "text": "通话中", "present": true }
  ]
}`

  const user = `# 用例名称
${caseName}

# 自然语言执行描述
${nlDescription}

# 期望结果
${expectedResult?.trim() || '（未提供，请从描述推断可验证的 UI 断言）'}`

  return { system, user }
}

async function planNlUiActions(
  caseName: string,
  nlDescription: string,
  expectedResult?: string,
): Promise<NlUiActionPlan> {
  const { system, user } = buildPlanningPrompt(caseName, nlDescription, expectedResult)
  let lastError = 'LLM 未返回有效动作计划'

  for (let attempt = 0; attempt < 2; attempt++) {
    const retryHint = attempt > 0
      ? '\n\n上次输出无效，请严格输出符合 schema 的 JSON，executable=false 时 steps 可为空数组。'
      : ''
    const raw = await callTahpLLM(system, user + retryHint, { maxTokens: 4096 })
    const parsed = extractJsonObject(raw)
    if (!parsed) {
      lastError = 'LLM 返回内容无法解析为 JSON'
      continue
    }
    const validation = validateNlUiPlan(parsed)
    if (validation.ok) return validation.plan
    lastError = validation.error
    if (parsed.executable === false) {
      throw new Error(String(parsed.reason || lastError))
    }
  }

  throw new Error(`不可用手机 UI 自动化执行：${lastError}`)
}

export async function createManualNlUiCase(payload: {
  caseName: string
  nlDescription: string
  expectedResult?: string
}): Promise<CreatedNlUiCase> {
  const caseName = String(payload.caseName || '').trim()
  const nlDescription = String(payload.nlDescription || '').trim()
  const expectedResult = String(payload.expectedResult || '').trim()

  if (!caseName) throw new Error('用例名称不能为空')
  if (!nlDescription || nlDescription.length < 8) {
    throw new Error('自然语言执行描述过短，请描述具体操作步骤与验证点')
  }

  const plan = await planNlUiActions(caseName, nlDescription, expectedResult)
  const config = loadAiConfig()
  const caseIndex = nextCaseIndex(config)
  const caseKey = `${AI_GENERATED_TEST_TYPE}/${AI_GENERATED_MODULE}/${caseIndex}`

  config.cases.push({
    caseIndex,
    caseName,
    mode: 'solo',
    canReuse: false,
    execMode: 'nl_ui',
  })
  saveAiConfig(config)

  const caseInfo = loadCaseInfo()
  while (caseInfo.length < caseIndex) caseInfo.push({})
  caseInfo[caseIndex - 1] = {
    用例名: caseName,
    前置条件: '连接测试机，保持设备在线且屏幕可交互',
    测试步骤: nlDescription,
    期望结果: expectedResult || '界面符合自然语言描述的预期',
    execMode: 'nl_ui',
    nlDescription,
  }
  saveCaseInfo(caseInfo)

  writeDurableCasePlan(caseIndex, plan)
  writeDurableCasePython(caseIndex, NL_UI_CASE_PY_TEMPLATE)
  mirrorAiGeneratedCasesToRuntime()

  logger.info({ caseKey, stepCount: plan.steps.length }, '[ai-nl-ui-cases] created manual NL UI case')

  return {
    caseKey,
    caseIndex,
    caseName,
    moduleLabel: AI_GENERATED_MODULE_LABEL,
    execMode: 'nl_ui',
    nlDescription,
    expectedResult: expectedResult || '界面符合自然语言描述的预期',
    plan,
  }
}

function parseAiGeneratedCaseKey(caseKey: string): number | null {
  const match = String(caseKey || '').trim().match(/^ai_generated\/generated\/(\d+)$/)
  if (!match) return null
  const caseIndex = Number(match[1])
  return Number.isInteger(caseIndex) && caseIndex > 0 ? caseIndex : null
}

export async function updateManualNlUiCase(payload: {
  caseKey: string
  caseName: string
  nlDescription: string
  expectedResult?: string
}): Promise<CreatedNlUiCase> {
  const caseKey = String(payload.caseKey || '').trim()
  const caseName = String(payload.caseName || '').trim()
  const nlDescription = String(payload.nlDescription || '').trim()
  const expectedResult = String(payload.expectedResult || '').trim()

  const caseIndex = parseAiGeneratedCaseKey(caseKey)
  if (caseIndex == null) {
    throw new Error('用例 key 无效，仅支持修改 AI 用例')
  }
  if (!caseName) throw new Error('用例名称不能为空')
  if (!nlDescription || nlDescription.length < 8) {
    throw new Error('自然语言执行描述过短，请描述具体操作步骤与验证点')
  }

  const config = loadAiConfig()
  const entry = config.cases.find(c => c.caseIndex === caseIndex)
  if (!entry) {
    throw new Error(`用例不存在：${caseKey}`)
  }

  const plan = await planNlUiActions(caseName, nlDescription, expectedResult)

  entry.caseName = caseName
  entry.mode = 'solo'
  entry.canReuse = false
  entry.execMode = 'nl_ui'
  saveAiConfig(config)

  const caseInfo = loadCaseInfo()
  while (caseInfo.length < caseIndex) caseInfo.push({})
  caseInfo[caseIndex - 1] = {
    用例名: caseName,
    前置条件: '连接测试机，保持设备在线且屏幕可交互',
    测试步骤: nlDescription,
    期望结果: expectedResult || '界面符合自然语言描述的预期',
    execMode: 'nl_ui',
    nlDescription,
  }
  saveCaseInfo(caseInfo)

  writeDurableCasePlan(caseIndex, plan)
  writeDurableCasePython(caseIndex, NL_UI_CASE_PY_TEMPLATE)
  mirrorAiGeneratedCasesToRuntime()

  logger.info({ caseKey, stepCount: plan.steps.length }, '[ai-nl-ui-cases] updated manual NL UI case')

  return {
    caseKey,
    caseIndex,
    caseName,
    moduleLabel: AI_GENERATED_MODULE_LABEL,
    execMode: 'nl_ui',
    nlDescription,
    expectedResult: expectedResult || '界面符合自然语言描述的预期',
    plan,
  }
}
