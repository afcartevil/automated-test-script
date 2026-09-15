/**
 * TAHP — Gerrit 提交编排（适配流水线 gerrit 阶段）
 *
 * 走 Agent Bridge 调用 gerrit-submit Skill，按用户勾选的 git 仓逐次提交
 * （同一仓内多域改动合并为一张 CR，不再按域拆单）。
 */
import { randomBytes } from 'crypto'
import { join } from 'path'
import { logger } from '../logger'
import { getTaskStream } from './task-stream'
import {
  AgentBridgeClient,
  getAgentBridgeManager,
  type AgentBridgeChatStarted,
  type AgentBridgeOutput,
} from '../hermes/agent-bridge'
import { filterBridgeToolCallMarkupDelta } from '../hermes/run-chat/bridge-delta'
import {
  getTahpSkillsRoot,
  tahpSkillMdPath,
} from './context-injector'
import { saveAgentPromptLog } from './prompt-log'
import { humanizeAgentError } from './adapt-agent-health'
import { assertHarnessCliReady } from './harness-version-gate'
import { detectRemoteExecFlavor } from './host-tool-runtime'
import { discoverRemoteRunner, ensureAsfBridgeSession, bridgeExec } from './adapt-pipeline/harness-bridge-exec'
import {
  DEFAULT_LINUX_MAPPED_ROOT,
  fillMappedWorkspaceIfMissing,
  mapWinFilesToLinux,
} from './adapt-pipeline/mapped-workspace'
import {
  isGerritConfigured,
  writeRuntimeCredFile,
  getGerritConfig,
  DEFAULT_GERRIT_HOST,
} from './gerrit-credentials'
import { GERRIT_NOT_CONFIGURED_ERROR } from './gerrit-review'
import type { BuildContext, PipelineDomain } from './adapt-pipeline/types'

export const GERRIT_SUBMIT_SKILL_ID = 'gerrit-submit'

/** 编排层判定「提交卡住」的墙钟时间（Agent 自身超时 30min） */
export const GERRIT_SUBMIT_STALE_MS = 12 * 60 * 1000

const sharedBridgeClient = new AgentBridgeClient({ timeoutMs: 30 * 60_000 })

const BFF_BRIDGE_LOG_NOISE_RE = /正在认领|跳过幽灵 mux|已认领 ASF Bridge|ASF Bridge SSH\/齐治登录已断开|down\+up 后重试/

export function isGerritSubmitTimedOut(submitStartedAt: string | undefined, now = Date.now()): boolean {
  if (!submitStartedAt) return false
  const t0 = Date.parse(submitStartedAt)
  if (!Number.isFinite(t0)) return false
  return now - t0 > GERRIT_SUBMIT_STALE_MS
}

/** Agent 流里出现齐治登录 / SSH 掉线 / 改槽，应立即失败，不要 clarify 或 down/up */
export function isGerritSubmitStreamFatal(text: string): boolean {
  const s = String(text || '')
  if (!s.trim()) return false
  if (BFF_BRIDGE_LOG_NOISE_RE.test(s)) return false
  if (/请选择登录账号|'s password:|Permission denied, please try again|Invalid password for|登录账号列表|Password authentication/.test(s)) {
    return true
  }
  if (/BRIDGE_SSH_DISCONNECTED|OpenSSH is gone|pane_command is local shell/.test(s)) return true
  if (/There is no active session|no active session|Session ['`]agent_session\d+['`] not found/i.test(s)) return true
  if (/claim slot 1|Session \d+ 已 down|bridge down --session/i.test(s)) return true
  if (/幽灵状态/.test(s) && !/跳过幽灵/.test(s)) return true
  return false
}

export function guessGerritCommitType(files: string[]): string {
  const blob = files.join('\n').toLowerCase()
  if (/(^|[\\/])(tests?|agent-test)([-_\\/]|$)|_test\.|test\.(java|kt|c|cc|cpp|py)$/.test(blob)) {
    return 'test'
  }
  return 'func'
}

export function buildGerritCommitMessage(opts: {
  issueId?: string
  files: string[]
  repoLabel?: string
  domainLabel?: string
  domainLabels?: string[]
}): string {
  const rels = opts.files.map(f => f.replace(/\\/g, '/').replace(/^.*\//, '')).filter(Boolean)
  const sample = rels.slice(0, 4).join('、') || '适配变更'
  const type = guessGerritCommitType(opts.files)
  const subject = (opts.repoLabel || opts.domainLabel || '适配').trim()
  const domains = (opts.domainLabels ?? []).map(s => s.trim()).filter(Boolean)
  const domainHint = domains.length ? `（${domains.join('、')}）` : ''
  const desc = type === 'test'
    ? `新增测试产物 ${sample}`
    : `适配入库 ${subject}${domainHint}：更新 ${sample}`
  const suggest = domains.length
    ? `确认 ${subject} 中 ${domains.join('、')} 相关变更已入库且编译/功能不受影响`
    : `确认 ${subject} 相关变更已入库且编译/功能不受影响`
  const id = (opts.issueId || '').trim()
  return [
    `ID:${id}`,
    `DESCRIPTION:${desc}`,
    `TYPE:${type}`,
    'AFFECT_PROJECTS:ALL',
    `TEST_SUGGESTIONS:${suggest}`,
    '[是否自检]：是',
    '[是否影响其它项目]:否',
    '[是否影响其它平台]:否',
    '[是否chery-pick其它分支]:否',
  ].join('\n')
}

function bashSingleQuote(s: string): string {
  return `'${s.replace(/'/g, `'\\''`)}'`
}

function bashLinuxRootExpr(linuxRoot?: string): string {
  const t = (linuxRoot || '').trim().replace(/\/+$/, '')
  if (!t || t.includes('$USER') || t.includes('$(whoami)')) {
    return '"/work/code/$(whoami)"'
  }
  return bashSingleQuote(t)
}

export function buildGerritProbeScript(opts: {
  relFiles: string[]
  linuxRoot?: string
  nonce: string
}): string {
  const files = opts.relFiles.map(r => r.replace(/\\/g, '/').replace(/^\/+/, '')).filter(Boolean)
  const listed = files.map(f => `  ${bashSingleQuote(f)}`).join('\n')
  return `#!/bin/bash
set +e
export GIT_PAGER=cat PAGER=cat GIT_TERMINAL_PROMPT=0
NONCE=${bashSingleQuote(opts.nonce)}
LINUX_ROOT=${bashLinuxRootExpr(opts.linuxRoot)}
echo "===PROBE_BEGIN_\${NONCE}==="
files=(
${listed}
)
seen_repos=""
for rel in "\${files[@]}"; do
  f="\$LINUX_ROOT/\$rel"
  d=\$(dirname "\$f")
  repo=""
  while [ "\$d" != / ] && [ -n "\$d" ]; do
    if [ -d "\$d/.git" ] || [ -f "\$d/.git" ]; then repo="\$d"; break; fi
    d=\$(dirname "\$d")
  done
  if [ -z "\$repo" ]; then
    echo "--- no_repo \$f"
    continue
  fi
  case " \$seen_repos " in
    *" \$repo "*) continue ;;
  esac
  seen_repos="\$seen_repos \$repo"
  echo "--- repo \$repo"
  echo "--- files"
  for rel2 in "\${files[@]}"; do
    g="\$LINUX_ROOT/\$rel2"
    case "\$g" in
      "\$repo"/*) echo "\${g#\$repo/}" ;;
    esac
  done
  echo "--- branch_head"
  git -C "\$repo" rev-parse --abbrev-ref HEAD 2>/dev/null
  git -C "\$repo" rev-parse --abbrev-ref --symbolic-full-name @{upstream} 2>/dev/null
  echo "--- status"
  git -C "\$repo" -c core.quotepath=false status --porcelain --untracked-files=all
  echo "--- hook"
  hook=no
  if [ -d "\$repo/.git" ] && { [ -x "\$repo/.git/hooks/commit-msg" ] || [ -f "\$repo/.git/hooks/commit-msg" ]; }; then
    hook=yes
  elif [ -f "\$repo/.git" ]; then
    gitdir=\$(sed -n 's/^gitdir:[[:space:]]*//p' "\$repo/.git" | head -n1)
    [ -n "\$gitdir" ] && [ -f "\$gitdir/hooks/commit-msg" ] && hook=yes
  fi
  echo "hook \$hook"
done
echo "===PROBE_END_\${NONCE}==="
`
}

export function buildGerritSubmitScript(opts: {
  relFiles: string[]
  linuxRoot?: string
  nonce: string
  message: string
  branch?: string
}): string {
  const files = opts.relFiles.map(r => r.replace(/\\/g, '/').replace(/^\/+/, '')).filter(Boolean)
  const listed = files.map(f => `  ${bashSingleQuote(f)}`).join('\n')
  const msgB64 = Buffer.from(opts.message, 'utf8').toString('base64')
  const branch = (opts.branch || '').trim()
  return `#!/bin/bash
set +e
export GIT_PAGER=cat PAGER=cat GIT_TERMINAL_PROMPT=0
NONCE=${bashSingleQuote(opts.nonce)}
LINUX_ROOT=${bashLinuxRootExpr(opts.linuxRoot)}
BRANCH=${bashSingleQuote(branch)}
MSG_B64=${bashSingleQuote(msgB64)}
echo "===SUBMIT_BEGIN_\${NONCE}==="
MSG=\$(mktemp /tmp/gerrit-msg-XXXXXX)
echo "\$MSG_B64" | base64 -d > "\$MSG" || { echo "FATAL: commit message decode failed"; exit 2; }
files=(
${listed}
)
seen_repos=""
for rel in "\${files[@]}"; do
  f="\$LINUX_ROOT/\$rel"
  d=\$(dirname "\$f")
  repo=""
  while [ "\$d" != / ] && [ -n "\$d" ]; do
    if [ -d "\$d/.git" ] || [ -f "\$d/.git" ]; then repo="\$d"; break; fi
    d=\$(dirname "\$d")
  done
  if [ -z "\$repo" ]; then
    echo "--- no_repo \$f"
    continue
  fi
  case " \$seen_repos " in
    *" \$repo "*) continue ;;
  esac
  seen_repos="\$seen_repos \$repo"
  echo "--- repo \$repo"
  rels=()
  for rel2 in "\${files[@]}"; do
    g="\$LINUX_ROOT/\$rel2"
    case "\$g" in
      "\$repo"/*) rels+=("\${g#\$repo/}") ;;
    esac
  done
  hook=no
  if [ -d "\$repo/.git" ] && [ -f "\$repo/.git/hooks/commit-msg" ]; then hook=yes
  elif [ -f "\$repo/.git" ]; then
    gitdir=\$(sed -n 's/^gitdir:[[:space:]]*//p' "\$repo/.git" | head -n1)
    [ -n "\$gitdir" ] && [ -f "\$gitdir/hooks/commit-msg" ] && hook=yes
  fi
  if [ "\$hook" != yes ]; then
    echo "FATAL: missing commit-msg hook in \$repo"
    exit 2
  fi
  git -C "\$repo" add -- "\${rels[@]}"
  br="\$BRANCH"
  if [ -z "\$br" ]; then
    mref=\$(git -C "\$repo" symbolic-ref -q refs/remotes/m/master 2>/dev/null)
    if [ -n "\$mref" ]; then
      br=\${mref#refs/remotes/}
      br=\${br#*/}
    fi
  fi
  if [ -z "\$br" ]; then
    br=\$(git -C "\$repo" rev-parse --abbrev-ref --symbolic-full-name @{upstream} 2>/dev/null | sed 's#^[^/]*/##')
  fi
  if [ -z "\$br" ] || [ "\$br" = HEAD ] || [ "\$br" = master ] || [[ "\$br" == m/* ]]; then
    br=\$(git -C "\$repo" branch -a 2>/dev/null | sed -n 's#^.*remotes/[^/]*/##p' | grep -Ev '^(HEAD|master|m/)' | head -n1)
  fi
  if [ -z "\$br" ]; then
    br=\$(git -C "\$repo" rev-parse --abbrev-ref HEAD 2>/dev/null)
  fi
  if [ -z "\$br" ] || [ "\$br" = HEAD ]; then
    echo "FATAL: cannot infer refs/for branch"
    exit 2
  fi
  if git -C "\$repo" diff --cached --quiet; then
    echo "--- nothing_staged"
    if git -C "\$repo" log -1 --format=%B 2>/dev/null | grep -q '^Change-Id:'; then
      echo "--- head_has_change_id"
    else
      echo "FATAL: no staged changes and HEAD has no Change-Id; skip push of detached base"
      exit 2
    fi
  else
    git -C "\$repo" commit -F "\$MSG" || { echo "FATAL: git commit failed"; exit 2; }
  fi
  echo "--- push --no-thin refs/for/\$br"
  # --no-thin：避免 Gerrit unpack 时报 Missing tree（thin pack 依赖远端 base object）
  push_out=\$(git -C "\$repo" push --no-thin origin "HEAD:refs/for/\$br" 2>&1)
  push_rc=\$?
  echo "\$push_out"
  url=\$(echo "\$push_out" | grep -oE 'https://gerrit[^[:space:]]+' | tail -n1 | sed 's/[.,;)]*$//')
  if [ -n "\$url" ]; then
    echo "GERRIT_CHANGE_URL: \$url"
  fi
  if [ \$push_rc -ne 0 ] && ! echo "\$push_out" | grep -qi 'no new changes'; then
    echo "FATAL: git push failed rc=\$push_rc"
    exit 2
  fi
done
rm -f "\$MSG"
echo "===SUBMIT_END_\${NONCE}==="
`
}

export function buildAsfBridgeEncodedCmd(opts: {
  session: number
  waitSec: number
  script: string
}): string {
  return `asf --json bridge cmd --session ${opts.session} --wait ${opts.waitSec} "${gerritRemoteBashCommand(opts.script)}"`
}

/** 给 asf bridge cmd / BFF bridgeExec 用的一行：UTF-8 脚本 base64，远端再解码 */
export function gerritRemoteBashCommand(script: string): string {
  const b64 = Buffer.from(script, 'utf8').toString('base64').replace(/\s+/g, '')
  return `echo '${b64}' | base64 -d | bash`
}

export function extractGerritScriptFatal(text: string): string | undefined {
  const m = String(text || '').match(/^FATAL:.*$/m)
  return m?.[0]
}

export interface GerritRepoSubmitInput {
  runId: string
  projectCode: string
  repo: string
  repoLabel: string
  files: string[]
  domainIds: string[]
  domainLabels: string[]
  buildContext: BuildContext
}

/** @deprecated 按仓提交后不再按域拆 CR；保留给旧调用方 */
export interface GerritDomainSubmitInput {
  runId: string
  projectCode: string
  domain: PipelineDomain
  buildContext: BuildContext
}

export interface GerritSubmitTaskCtx {
  taskId: string
  runId: string
  repo: string
  domainId?: string
  startedAt: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
  llmResponse?: string
  changeUrl?: string
  changeNumber?: string
  changeId?: string
  alreadySubmitted?: boolean
  error?: string
  completedAt?: string
}

const taskCtx = new Map<string, GerritSubmitTaskCtx>()
const taskRuntime = new Map<string, { sessionId: string; interruptRequested: boolean }>()

function genTaskId(): string {
  return `task-gerrit-submit-${Date.now()}-${randomBytes(3).toString('hex')}`
}

function agentSessionIdForTask(taskId: string): string {
  return `tahp-gerrit-submit-${taskId}`
}

function emit(taskId: string, type: string, payload: Record<string, unknown>) {
  getTaskStream().publish({
    type,
    task_id: taskId,
    payload: { task_id: taskId, ...payload },
    ts: Date.now(),
  })
}

export interface GerritSubmitParseResult {
  changeUrl?: string
  changeNumber?: string
  changeId?: string
  /** push 返回 no new changes：本地 commit 已是 CR 当前 patch set，等价于已提交 */
  alreadySubmitted?: boolean
}

function stripUrlTail(url: string): string {
  return url.replace(/[.,;)\]]+$/g, '')
}

/**
 * SUBMIT 曾用 `tr -d '.,;'` 清尾标点，会把主机名里的点一起删掉：
 * `gerrit.transsion.com` → `gerrittranssioncom`。解析与展示时补回。
 */
export function normalizeGerritChangeUrl(raw: string): string {
  const u = stripUrlTail(String(raw || '').trim())
  return u.replace(
    /^(https?:\/\/)gerrit(-cq)?transsioncom(?=\/|$)/i,
    (_m, proto: string, cq?: string) => `${proto}gerrit${cq || ''}.transsion.com`,
  )
}

/**
 * 从 Agent 输出解析 Gerrit CR 信息。
 *
 * Agent 正文常复述历史 CR 链接（补读远端 pane 时也会带出上一次任务的输出），
 * 因此优先取 skill 约定的 `GERRIT_CHANGE_URL:` 回报行，其次取**最后**一个 URL。
 */
export function parseGerritSubmitResult(text: string): GerritSubmitParseResult {
  const result: GerritSubmitParseResult = {}

  const reported = [...text.matchAll(/GERRIT_CHANGE_URL:\s*(\S+)/gi)].pop()
  if (reported) {
    result.changeUrl = normalizeGerritChangeUrl(reported[1])
  } else {
    const urls = [...text.matchAll(/https?:\/\/gerrit[^\s)>'"`\]]+/gi)]
    const last = urls[urls.length - 1]
    if (last) result.changeUrl = normalizeGerritChangeUrl(last[0])
  }

  if (result.changeUrl) {
    const numFromUrl = result.changeUrl.match(/\/(\d+)\/?$/)
    if (numFromUrl) result.changeNumber = numFromUrl[1]
  }

  const changeIdMatch = text.match(/Change-Id:\s*(I[0-9a-f]+)/i)
  if (changeIdMatch) result.changeId = changeIdMatch[1]

  if (!result.changeNumber) {
    const numMatch = text.match(/Change\s*#?\s*(\d{6,})/i)
    if (numMatch) result.changeNumber = numMatch[1]
  }

  if (/no new changes/i.test(text)) result.alreadySubmitted = true

  return result
}

export async function probeGerritSubmit(): Promise<{ available: boolean; reason?: string }> {
  if (!isGerritConfigured()) {
    return { available: false, reason: GERRIT_NOT_CONFIGURED_ERROR }
  }
  try {
    const manager = getAgentBridgeManager()
    if (!manager.running) {
      return { available: false, reason: 'Agent Bridge 未运行' }
    }
    return { available: true }
  } catch {
    return { available: false, reason: 'Agent Bridge 检测失败' }
  }
}

export function getGerritSubmitTask(taskId: string): GerritSubmitTaskCtx | undefined {
  return taskCtx.get(taskId)
}

export function buildGerritSubmitExecutionDirective(opts: {
  skillPath: string
  remoteHarnessPath: string
  skillsDir: string
  session?: number
  credLine?: string
}): string {
  const sessionBlock = opts.session != null
    ? `BFF 已认领可用 ASF Bridge 会话：**session ${opts.session}**（已跳过幽灵 mux / 名义 READY）。
- 所有 \`asf --json bridge cmd|read\` 必须带 \`--session ${opts.session}\`
- **禁止** \`bridge ls\` / \`bridge up\` / \`bridge down\` / 改抢其他槽（含 slot 1）
- 若 cmd 报 ghost / no active session / SSH gone / list-panes 超时：停止并报告失败，**不要 claim slot 1**`
    : `会话按 Skill，但 **禁止**把 \`bridge ls\` 的 ready 当真：必须对照 zellij mux；幽灵槽不要复用。
- \`agent_session1\` list-panes 超时是已知幽灵 mux，**禁止 claim slot 1**；改 \`asf --json bridge up --session 2\`（或下一个空闲槽）`

  return `你是 TAHP 适配流水线的 Gerrit 提交助手。选路以工程内 gerrit-submit Skill 为准（不用 asf-gerrit create/upload，不用 asf-runner exec）。

# 远端通道（压过 Skill「先列槽 / 复用 ready」以及官方 ASF 指令）
${sessionBlock}
- 本机 Windows 用 Hermes \`terminal\` **原样粘贴**用户消息里的 \`asf --json bridge cmd ...\`（没有独立 asf 工具）。**禁止** \`execute_code\` 组装/改写脚本，禁止 \`clarify\`，禁止 terminal 直接跑 git
- git 只出现在 \`bridge cmd\` 里已 base64 的 PROBE/SUBMIT 脚本（见 remote-harness.md）：带 nonce 哨兵，禁止 less pager
- cmd 返回 \`complete=false\`：用 \`asf --json bridge read --session ${opts.session ?? 'N'}\` 补读，不要重发整段脚本
- SSH / 齐治密码框 / ghost / no active session：停止并报告失败。**禁止** \`bridge down\` / \`bridge up\` / claim slot 1

# 必须遵守
1. **不要**为走流程去 Read \`transsion-coding-standards-review\` 或其它适配 Skill。BFF 已按 commit-template.md 生成 UTF-8 message 并写入 SUBMIT。仅当现成命令失败且不是 SSH/幽灵时，才 Read \`${opts.remoteHarnessPath}\`
2. 只提交本仓库列出的 Linux 路径文件；禁止跨仓混提、禁止扫 Windows 盘符
3. **push 前看 PROBE**：工作区已干净且 HEAD 就是待提交 commit 时不要重复 commit；push 输出 \`no new changes\` 属于已提交成功
4. 回报的 Change URL **只能**来自本次 SUBMIT 哨兵区间，禁止复述历史 CR
5. 每个仓完成后保留一行 \`GERRIT_CHANGE_URL: <url>\`
${opts.credLine ? `\n${opts.credLine}\n` : ''}
# 工程 Skill 根目录
\`${opts.skillsDir}\`
`
}

function buildInstructions(
  _input: GerritRepoSubmitInput,
  cred?: { credFilePath: string; host: string },
  session?: number,
): string {
  const skillPath = tahpSkillMdPath(GERRIT_SUBMIT_SKILL_ID)
  const skillsDir = getTahpSkillsRoot()
  const remoteHarnessPath = join(skillsDir, GERRIT_SUBMIT_SKILL_ID, 'remote-harness.md')
  const gerritHost = cred?.host || getGerritConfig()?.host || DEFAULT_GERRIT_HOST
  const credLine = cred?.credFilePath
    ? `Gerrit 凭证文件：${cred.credFilePath}；Host: ${gerritHost}`
    : ''

  return buildGerritSubmitExecutionDirective({
    skillPath,
    remoteHarnessPath,
    skillsDir,
    session,
    credLine,
  })
}

export function buildGerritSubmitUserMessage(
  input: GerritRepoSubmitInput,
  opts: {
    linuxFiles: Array<{ win: string; linux: string; rel: string }>
    commitMessage: string
    probeCmd?: string
    submitCmd?: string
    session?: number
  },
): string {
  const branch = input.buildContext.target_branch?.trim()
  const issueId = input.buildContext.gerrit_issue_id?.trim()
  const fileLines = opts.linuxFiles.length
    ? opts.linuxFiles.map(f => `- Linux: ${f.linux}\n  Windows: ${f.win}`).join('\n')
    : '（无文件列表）'
  const cmds = [
    opts.probeCmd ? `### 1. PROBE（只发这一条，等哨兵结束）\n\`${opts.probeCmd}\`` : '',
    opts.submitCmd
      ? `### 2. SUBMIT（PROBE 显示本仓库文件有变更或未 push 时发这一条；不要改 base64）\n\`${opts.submitCmd}\``
      : '',
  ].filter(Boolean).join('\n\n')
  const domains = input.domainLabels.length
    ? input.domainLabels.map((l, i) => `${l} (${input.domainIds[i] || l})`).join('、')
    : (input.domainIds.join('、') || '—')

  return [
    '# Gerrit 提交任务',
    '',
    `项目：${input.projectCode}`,
    `仓库：${input.repoLabel} (${input.repo})`,
    `涉及域：${domains}`,
    branch ? `目标分支：${branch}（SUBMIT 脚本已写入）` : '目标分支：未指定（SUBMIT 脚本按远端 upstream / remotes 推断）',
    issueId
      ? `提交 ID（commit 模板 ID 字段，多仓共用）：${issueId}`
      : '提交 ID：未指定（模板 ID 行可为空，不要因此失败）',
    `Linux 映射根：${input.buildContext.linux_root?.trim() || DEFAULT_LINUX_MAPPED_ROOT}`,
    input.buildContext.mapped_root?.trim()
      ? `Windows 映射根：${input.buildContext.mapped_root}`
      : '',
    '',
    '## 本仓库变更文件（已换算，禁止再扫 Z:\\ / UNC）',
    fileLines,
    '',
    '## commit message（SUBMIT 已内嵌 UTF-8 base64，禁止 execute_code 重写）',
    '```',
    opts.commitMessage,
    '```',
    '',
    '## 直接执行',
    cmds || '（无现成 asf 命令：按 Skill PROBE → SUBMIT，且必须 --json bridge cmd）',
    opts.session != null
      ? `\nASF Bridge 会话已由 BFF 认领：session ${opts.session}。禁止 ls/up/down/改槽。`
      : '',
    '',
    '不要 clarify，不要认领槽，不要用 Windows git。',
  ].filter(line => line !== '').join('\n')
}

async function runAgentChat(
  sessionId: string,
  instructions: string,
  userMessage: string,
  onLog: (line: string) => void,
  shouldAbort?: () => string | undefined,
): Promise<string> {
  const manager = getAgentBridgeManager()
  if (!manager.running) {
    throw new Error('Agent Bridge 未运行。请确认 hermes-agent-main 已初始化。')
  }

  const started: AgentBridgeChatStarted = await sharedBridgeClient.chat(
    sessionId,
    userMessage,
    undefined,
    instructions,
    'default',
  )

  const markupState: { bridgePendingToolCallMarkup?: string } = {}
  let fullResponse = ''
  let lastChunk: AgentBridgeOutput | null = null

  for await (const chunk of sharedBridgeClient.streamOutput(started.run_id, { intervalMs: 250 })) {
    const abort = shouldAbort?.()
    if (abort) throw new Error(abort)
    lastChunk = chunk
    for (const ev of chunk.events || []) {
      if (ev.event === 'tool.started' || ev.event === 'tool.completed') {
        const name = String(ev.tool_name || 'tool')
        onLog(`[tool] ${name}`)
      }
    }
    if (chunk.delta) {
      const cleaned = filterBridgeToolCallMarkupDelta(markupState, chunk.delta)
      if (cleaned) {
        fullResponse += cleaned
        onLog(cleaned.trim())
      }
    }
    if (chunk.done) {
      if (chunk.status === 'error') throw new Error(humanizeAgentError(chunk.error || 'Agent 出错'))
      if (chunk.status === 'interrupted') throw new Error('Agent 运行被中断')
      break
    }
  }

  if (!lastChunk?.done) throw new Error('Agent 流式输出意外终止')
  if (lastChunk.error) throw new Error(humanizeAgentError(lastChunk.error))
  return fullResponse
}

export function startGerritRepoSubmit(
  input: GerritRepoSubmitInput,
): { ok: true; taskId: string } | { ok: false; error: string } {
  try {
    assertHarnessCliReady()
  } catch (err) {
    return { ok: false, error: (err as Error).message }
  }

  const files = input.files ?? []
  if (!files.length) {
    return { ok: false, error: `仓库 ${input.repoLabel || input.repo} 无变更文件` }
  }

  const taskId = genTaskId()
  const now = new Date().toISOString()
  taskCtx.set(taskId, {
    taskId,
    runId: input.runId,
    repo: input.repo,
    domainId: input.domainIds[0],
    startedAt: now,
    status: 'running',
  })

  emit(taskId, 'task.started', {
    run_id: input.runId,
    repo: input.repo,
    repo_label: input.repoLabel,
    domain_id: input.domainIds[0],
    domain_ids: input.domainIds,
    skill: GERRIT_SUBMIT_SKILL_ID,
    message: `开始提交仓库 ${input.repoLabel}`,
  })

  setImmediate(() => {
    runGerritSubmitTask(taskId, input).catch(err => {
      logger.error({ err, taskId }, '[gerrit-submit] unhandled')
    })
  })

  return { ok: true, taskId }
}

/** @deprecated 使用 startGerritRepoSubmit；按仓合提后不再按域拆 CR */
export function startGerritDomainSubmit(
  input: GerritDomainSubmitInput,
): { ok: true; taskId: string } | { ok: false; error: string } {
  return startGerritRepoSubmit({
    runId: input.runId,
    projectCode: input.projectCode,
    repo: input.domain.domain_id,
    repoLabel: input.domain.domain_label,
    files: input.domain.changed_files ?? [],
    domainIds: [input.domain.domain_id],
    domainLabels: [input.domain.domain_label],
    buildContext: input.buildContext,
  })
}

export function cancelGerritSubmitTask(taskId: string): void {
  const rt = taskRuntime.get(taskId)
  if (rt) rt.interruptRequested = true
  const ctx = taskCtx.get(taskId)
  if (ctx && (ctx.status === 'running' || ctx.status === 'pending')) {
    ctx.status = 'cancelled'
    ctx.error = ctx.error || '已取消'
    ctx.completedAt = new Date().toISOString()
  }
  sharedBridgeClient.destroy(agentSessionIdForTask(taskId)).catch(() => {})
}

async function runGerritSubmitTask(taskId: string, input: GerritRepoSubmitInput): Promise<void> {
  const ctx = taskCtx.get(taskId)
  if (!ctx) return

  const agentSessionId = agentSessionIdForTask(taskId)
  taskRuntime.set(taskId, { sessionId: agentSessionId, interruptRequested: false })

  try {
    const credFilePath = writeRuntimeCredFile()
    const cfg = getGerritConfig()
    let sessionPinned = false
    const onLog = (line: string) => {
      if (line) emit(taskId, 'task.message', { level: 'stream', text: line })
    }

    let disc: Record<string, unknown> | null = null
    try {
      disc = discoverRemoteRunner()
    } catch { /* 映射盘 discover 失败时仍可用盘符换算 */ }
    const buildContext = fillMappedWorkspaceIfMissing(input.buildContext, disc)
    input = { ...input, buildContext }

    const linuxFiles = mapWinFilesToLinux(input.files ?? [], {
      mappedRoot: buildContext.mapped_root,
      linuxRoot: buildContext.linux_root,
    })
    if (!linuxFiles.length) {
      throw new Error(`仓库 ${input.repoLabel || input.repo} 无可用 Linux 路径`)
    }
    onLog(`mapped_root=${buildContext.mapped_root || '(空)'} linux_root=${buildContext.linux_root || DEFAULT_LINUX_MAPPED_ROOT}`)
    for (const f of linuxFiles) onLog(`file ${f.linux}`)

    const nonce = randomBytes(4).toString('hex')
    const commitMessage = buildGerritCommitMessage({
      issueId: buildContext.gerrit_issue_id,
      files: linuxFiles.map(f => f.rel),
      repoLabel: input.repoLabel,
      domainLabels: input.domainLabels,
    })
    const probeScript = buildGerritProbeScript({
      relFiles: linuxFiles.map(f => f.rel),
      linuxRoot: buildContext.linux_root,
      nonce,
    })
    const submitScript = buildGerritSubmitScript({
      relFiles: linuxFiles.map(f => f.rel),
      linuxRoot: buildContext.linux_root,
      nonce,
      message: commitMessage,
      branch: buildContext.target_branch,
    })

    let bridgeSession: number | undefined
    const flavor = detectRemoteExecFlavor()
    if (flavor === 'asf-bridge') {
      onLog('正在认领可用 ASF Bridge 会话（跳过幽灵槽）…')
      bridgeSession = await ensureAsfBridgeSession({ onLog })
      sessionPinned = true
      onLog(`已认领 ASF Bridge session ${bridgeSession}，Agent 不得改槽`)
    } else if (flavor === 'unavailable') {
      throw new Error('本机 CLI 无 asf bridge cmd，无法在 Linux 构建机执行 git')
    }

    const probeCmd = bridgeSession != null
      ? buildAsfBridgeEncodedCmd({ session: bridgeSession, waitSec: 60, script: probeScript })
      : undefined
    const submitCmd = bridgeSession != null
      ? buildAsfBridgeEncodedCmd({ session: bridgeSession, waitSec: 180, script: submitScript })
      : undefined

    const userMessage = buildGerritSubmitUserMessage(input, {
      linuxFiles,
      commitMessage,
      probeCmd,
      submitCmd,
      session: bridgeSession,
    })
    const instructions = buildInstructions(input, {
      credFilePath,
      host: cfg?.host || DEFAULT_GERRIT_HOST,
    }, bridgeSession)
    saveAgentPromptLog(taskId, 'gerrit-submit', instructions, userMessage)

    const signal = {
      get cancelled() {
        return taskRuntime.get(taskId)?.interruptRequested === true
      },
    }
    const onBridgeChunk = (chunk: string) => {
      const text = String(chunk || '').trim()
      if (text) onLog(text.slice(0, 2000))
    }

    let fullResponse = ''
    if (flavor === 'asf-bridge' || flavor === 'legacy-bridge-exec') {
      onLog('BFF 直接执行 PROBE（不经 Agent terminal / execute_code）…')
      const probeRes = await bridgeExec(gerritRemoteBashCommand(probeScript), {
        timeoutSec: 90,
        onStdout: onBridgeChunk,
        onStderr: onBridgeChunk,
        signal,
      })
      const probeOut = `${probeRes.output || ''}\n${probeRes.error || ''}`
      fullResponse += probeOut
      onLog(probeOut.slice(0, 1500))
      const probeFatal = extractGerritScriptFatal(probeOut)
      if (probeFatal) throw new Error(probeFatal)
      if (String(probeRes.status).toLowerCase() === 'error' && isGerritSubmitStreamFatal(probeOut)) {
        throw new Error('ASF Bridge 会话已断开（齐治/SSH），请重试提交，不要在登录框输入')
      }

      onLog('BFF 直接执行 SUBMIT…')
      const submitRes = await bridgeExec(gerritRemoteBashCommand(submitScript), {
        timeoutSec: 300,
        onStdout: onBridgeChunk,
        onStderr: onBridgeChunk,
        signal,
      })
      const submitOut = `${submitRes.output || ''}\n${submitRes.error || ''}`
      fullResponse += `\n${submitOut}`
      onLog(submitOut.slice(0, 2000))
      const submitFatal = extractGerritScriptFatal(submitOut)
      if (submitFatal) throw new Error(submitFatal)
      if (isGerritSubmitStreamFatal(submitOut)) {
        throw new Error('ASF Bridge 会话已断开（齐治/SSH），请重试提交，不要在登录框输入')
      }
    }

    let parsed = parseGerritSubmitResult(fullResponse)
    const needAgent = !parsed.changeUrl && !parsed.alreadySubmitted
    if (needAgent) {
      onLog('BFF 未解析到 Change URL，回退 Agent 处理突发情况…')
      const agentText = await runAgentChat(
        agentSessionId,
        instructions,
        `${userMessage}\n\n## BFF 已执行输出（先看这里，不要重发 PROBE）\n${fullResponse.slice(-8000)}`,
        (line) => {
          onLog(line)
          if (sessionPinned && isGerritSubmitStreamFatal(line)) {
            const rt = taskRuntime.get(taskId)
            if (rt) rt.interruptRequested = true
          }
        },
        () => {
          const rt = taskRuntime.get(taskId)
          if (rt?.interruptRequested) {
            return 'ASF Bridge 会话已断开（齐治/SSH），请重试提交，不要在登录框输入'
          }
          return undefined
        },
      )
      fullResponse += `\n${agentText}`
      parsed = parseGerritSubmitResult(fullResponse)
    }

    if (!parsed.changeUrl && !parsed.alreadySubmitted) {
      throw new Error('Gerrit 提交未回报 Change URL（PROBE/SUBMIT 可能未完成）')
    }
    ctx.llmResponse = fullResponse
    ctx.changeUrl = parsed.changeUrl
    ctx.changeNumber = parsed.changeNumber
    ctx.changeId = parsed.changeId
    ctx.alreadySubmitted = parsed.alreadySubmitted
    ctx.status = 'completed'
    ctx.completedAt = new Date().toISOString()

    emit(taskId, 'task.completed', {
      run_id: input.runId,
      repo: input.repo,
      repo_label: input.repoLabel,
      domain_id: input.domainIds[0],
      domain_ids: input.domainIds,
      change_url: parsed.changeUrl,
      change_number: parsed.changeNumber,
      change_id: parsed.changeId,
      already_submitted: parsed.alreadySubmitted === true,
      response: fullResponse,
    })
  } catch (err) {
    const msg = humanizeAgentError((err as Error).message)
    ctx.status = 'failed'
    ctx.error = msg
    ctx.completedAt = new Date().toISOString()
    emit(taskId, 'task.failed', {
      error: msg,
      message: msg,
      repo: input.repo,
      domain_id: input.domainIds[0],
    })
  } finally {
    taskRuntime.delete(taskId)
    sharedBridgeClient.destroy(agentSessionId).catch(() => {})
  }
}
