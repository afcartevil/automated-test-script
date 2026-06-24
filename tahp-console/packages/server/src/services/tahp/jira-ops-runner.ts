/**
 * 通过 jira-ops Skill 脚本执行 JIRA 写操作（与 Agent 同源凭据链）
 */
import { spawnSync } from 'child_process'
import { existsSync, mkdtempSync, writeFileSync, rmSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import { tahpPaths } from './paths'
import { parseIssueKey, type JiraConfig } from './jira'

function jiraOpsRoot(): string {
  return join(tahpPaths.skillsDir, 'jira-ops')
}

function applyJiraCfgToEnv(env: NodeJS.ProcessEnv, cfg?: JiraConfig): NodeJS.ProcessEnv {
  const out = { ...env }
  if (cfg?.baseUrl) out.JIRA_SERVER = cfg.baseUrl
  if (cfg?.username) out.JIRA_USERNAME = cfg.username
  if (cfg?.password) out.JIRA_PASSWORD = cfg.password
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
    return { ok: false, error: `jira-ops 脚本不存在: ${script}` }
  }

  const tmpDir = mkdtempSync(join(tmpdir(), 'tahp-jira-comment-'))
  const commentFile = join(tmpDir, 'comment.md')
  try {
    writeFileSync(commentFile, comment, 'utf-8')
    const r = spawnSync(
      tahpPaths.python,
      ['scripts/api_jira.py', 'add-comment', '--issue', key, '--comment-file', commentFile],
      {
        cwd: root,
        encoding: 'utf-8',
        timeout: 90_000,
        env: applyJiraCfgToEnv(process.env, jiraCfg),
      },
    )
    const stdout = (r.stdout || r.stderr || '').trim()
    if (r.status !== 0) {
      return { ok: false, error: stdout.slice(0, 500) || `jira-ops 退出码 ${r.status}` }
    }
    try {
      const json = JSON.parse(stdout) as { ok?: boolean; data?: Record<string, unknown>; error?: string }
      if (json.ok === false) {
        return { ok: false, error: String(json.error || stdout).slice(0, 500) }
      }
      return { ok: true, data: json.data as Record<string, unknown> | undefined }
    } catch {
      return { ok: false, error: stdout.slice(0, 500) || 'jira-ops 返回非 JSON' }
    }
  } finally {
    try { rmSync(tmpDir, { recursive: true, force: true }) } catch { /* ignore */ }
  }
}
