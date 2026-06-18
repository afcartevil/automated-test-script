/**
 * Agent 运行健康检查：模型额度/API 错误友好化、空跑检测。
 */

const QUOTA_PATTERNS = [
  /insufficient.*quota/i,
  /quota.*exceeded/i,
  /balance.*insufficient/i,
  /余额不足/,
  /额度不足/,
  /无可用额度/,
  /exceeded.*limit/i,
  /rate.?limit/i,
  /too many requests/i,
  /429/,
  /402/,
  /billing/i,
  /credit/i,
  /out of credits/i,
  /api[_ ]?key.*invalid/i,
  /invalid.*api[_ ]?key/i,
  /authentication.*fail/i,
  /unauthorized/i,
  /401/,
  /permission denied/i,
  /model.*not found/i,
  /does not exist/i,
  /无权限/,
  /鉴权失败/,
]

/** 将 Bridge / 模型原始错误转为用户可操作的提示 */
export function humanizeAgentError(raw: string): string {
  const text = raw.trim()
  if (!text) return 'Agent 运行出错，请检查模型配置与网络连接'

  if (QUOTA_PATTERNS.some(re => re.test(text))) {
    return [
      '当前大模型不可用（常见原因：额度不足、余额耗尽、API Key 无效或触发限流）。',
      '请在控制台「模型管理」切换其他模型或检查 Provider 配置后重试。',
      `原始信息：${truncate(text, 280)}`,
    ].join('\n')
  }

  return text
}

function truncate(s: string, max: number): string {
  return s.length <= max ? s : `${s.slice(0, max)}…`
}

/** 从 Agent 输出文本中嗅探模型侧错误 */
export function detectModelErrorInText(text: string): string | undefined {
  const t = text.trim()
  if (!t) return undefined
  if (QUOTA_PATTERNS.some(re => re.test(t))) {
    return humanizeAgentError(t)
  }
  return undefined
}

export interface AgentRunHealthInput {
  fullResponse: string
  toolsUsedCount: number
  durationMs: number
  bridgeError?: string | null
}

/**
 * 空跑 / 假完成检测：Bridge 快速返回但无工具、几乎无正文。
 * 返回应展示给用户的错误文案；健康则返回 undefined。
 */
export function detectUnhealthyAgentRun(input: AgentRunHealthInput): string | undefined {
  if (input.bridgeError?.trim()) {
    return humanizeAgentError(input.bridgeError)
  }

  const textErr = detectModelErrorInText(input.fullResponse)
  if (textErr) return textErr

  const textLen = input.fullResponse.trim().length
  const noTools = input.toolsUsedCount === 0
  const tooFast = input.durationMs < 20_000
  const almostEmpty = textLen < 120

  if (noTools && almostEmpty && tooFast) {
    return [
      'Agent 未执行任何工具且几乎无有效输出（疑似大模型未正常响应）。',
      '常见原因：① 当前模型额度/余额不足 ② API Key 无效或过期 ③ 模型名称配置错误 ④ Agent Bridge 被其他任务占用。',
      '请在「模型管理」切换可用模型后重试；若仍失败，查看 ~/.hermes-web-ui/logs/bridge.log。',
    ].join('\n')
  }

  return undefined
}
