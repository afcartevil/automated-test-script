/**
 * 通过 jira-ops Skill 脚本执行 JIRA 写操作（与 Agent 同源凭据链）
 */
import { existsSync } from 'fs'
import { join } from 'path'
import { tahpPaths } from './paths'
import { parseIssueKey, type JiraConfig } from './jira'
import { applyJiraUserConfigToEnv, resolveJiraConfig } from './jira-user-config'
import {
  spawnPythonScript,
  spawnOutputText,
  formatPythonSpawnError,
  extractJsonErrorMessage,
} from './python-spawn'

function jiraOpsRoot(): string {
  return join(tahpPaths.skillsDir, 'jira-ops')
}

function applyJiraCfgToEnv(env: NodeJS.ProcessEnv, cfg: JiraConfig): NodeJS.ProcessEnv {
  const out = applyJiraUserConfigToEnv(env)
  if (cfg.baseUrl) out.JIRA_SERVER = cfg.baseUrl
  if (cfg.username) out.JIRA_USERNAME = cfg.username
  if (cfg.password) out.JIRA_PASSWORD = cfg.password
  return out
}

export function runJiraOpsAddComment(
  issueRef: string,
  comment: string,
  jiraCfg?: JiraConfig,
): { ok: boolean; error?: string; data?: Record<string, unknown> } {
  const key = parseIssueKey(issueRef) || issueRef.trim().toUpperCase()
  if (!key) return { ok: false, error: `无法解析 JIRA Key: ${issueRef}` }
  if (!comment.trim()) return { ok: false, error: '评论内容不能为空' }

  const root = jiraOpsRoot()
  const script = join(root, 'scripts', 'api_jira.py')
  if (!existsSync(script)) {
    return {
      ok: false,
      error: `jira-ops 脚本不存在: ${script}（当前 TAHP 工程根: ${tahpPaths.projectRoot}。请确认 TAHP_PROJECT_ROOT 指向 git clone 根目录，并重启服务）`,
    }
  }

  const env = applyJiraCfgToEnv(process.env, resolveJiraConfig(jiraCfg))
  const r = spawnPythonScript({
    cwd: root,
    args: ['scripts/api_jira.py', 'add-comment', '--issue', key, '--comment', comment],
    env,
    timeout: 90_000,
    preferJsonOutput: true,
  })
  const stdout = spawnOutputText(r)

  try {
    const json = JSON.parse(stdout) as { ok?: boolean; data?: Record<string, unknown>; error?: unknown }
    if (json.ok === false) {
      return { ok: false, error: extractJsonErrorMessage(stdout) || stdout.slice(0, 500) || 'jira-ops 返回失败' }
    }
    if (json.ok === true) {
      return { ok: true, data: json.data as Record<string, unknown> | undefined }
    }
  } catch {
    // 非 JSON：走下方 spawn 错误格式化
  }

  if (r.status === null || (r.status !== 0 && !stdout)) {
    return { ok: false, error: formatPythonSpawnError('jira-ops', r, stdout) }
  }
  return { ok: false, error: formatPythonSpawnError('jira-ops', r, stdout) }
}
