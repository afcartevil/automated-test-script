/**
 * 智能诊断收尾：按 jira-dup-judge Skill 尝试把当前单置重。
 * 提示词模板固定，规则在 Skill 内，BFF 只负责投递 Agent。
 */
import { buildFullTahpSystemContext, tahpSkillMdRelativePath } from './context-injector'

export const JIRA_DUP_JUDGE_SKILL_ID = 'jira-dup-judge'

const DEFAULT_JIRA_BASE = 'http://jira.transsion.com'

export function jiraDupJudgeSessionId(taskId: string): string {
  return `tahp-bug-dup-${taskId}`
}

/** 拼出 /browse/KEY 形式的 URL（与用户提示词模板一致）。 */
export function resolveJiraBrowseUrl(jiraUrl: string | undefined, jiraKey: string): string {
  const key = (jiraKey || '').trim()
  const url = (jiraUrl || '').trim()
  if (url && /\/browse\//i.test(url)) {
    const cleaned = url.replace(/[?#].*$/, '').replace(/\/+$/, '')
    return cleaned
  }
  const base = (process.env.TAHP_JIRA_BASE_URL || DEFAULT_JIRA_BASE).replace(/\/+$/, '')
  return `${base}/browse/${key}`
}

export function buildJiraDupJudgePrompt(jiraUrl: string): string {
  return `把 ${jiraUrl} 按 jira-dup-judge 置重。`
}

export function buildJiraDupJudgeInstructions(userMessage: string): string {
  const skillPath = tahpSkillMdRelativePath(JIRA_DUP_JUDGE_SKILL_ID)
  const jiraOpsPath = tahpSkillMdRelativePath('jira-ops')
  const sop = [
    '你正在执行 Jira 置重，不是故障分析，不要输出 9 节分析报告。',
    `1. 必须先 Read \`${skillPath}\` 全文，以及同目录 \`config/constraints.yaml\`、\`config/schemes.yaml\`。`,
    '2. 严格按 SKILL.md 强制流程 Step 1～7 执行。找不到合法主单 → 不置重、不改单。',
    `3. Jira 读写只用 jira-ops（\`${jiraOpsPath}\`）。禁止 batch-mark-duplicate，禁止裸调 mark-duplicate。`,
    '4. 置重必须用 skill 内 \`scripts/apply_duplicate.py\`。',
    '5. 完成后用中文汇报：是否置重、主单 Key、或未置重原因（含硬约束失败）。',
  ].join('\n')
  const tahpCtx = buildFullTahpSystemContext(userMessage, {
    scenario: 'jira_dup_judge',
    preferredSkillIds: [JIRA_DUP_JUDGE_SKILL_ID, 'jira-ops'],
  })
  return [sop, tahpCtx].filter(part => part.trim().length > 0).join('\n\n')
}
