/**
 * 代码拉取：堡垒机 tmux 跑 repo sync 的命令与解析（纯函数，便于单测）
 */
import { shellQuote, parseTmuxPollOutput, type TmuxPollSnapshot } from '../adapt-pipeline/ez-build-tmux'

export const CODE_PULL_REMOTE_DIR = '~/code/tahp-code-pull'

export function validateRepoInitCommand(raw: string, label: string): string {
  const cmd = String(raw || '').trim()
  if (!cmd) throw new Error(`请填写 ${label} 的 repo init 命令`)
  if (!/^repo\s+init\b/i.test(cmd)) {
    throw new Error(`${label} 命令必须以 repo init 开头`)
  }
  if (/[\r\n]/.test(cmd)) {
    throw new Error(`${label} 命令不能包含换行`)
  }
  return cmd
}

export function codePullRelPath(runId: string, kind: 'system' | 'vendor'): string {
  const safe = String(runId).replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 64)
  return `code-pull/${safe}/${kind}`
}

export function codePullRunRel(runId: string): string {
  const safe = String(runId).replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 64)
  return `code-pull/${safe}`
}

/**
 * Linux 侧路径。使用 $(whoami) 以便在双引号内仍可展开（勿用单引号包住）。
 */
export function codePullLinuxPath(runId: string, kind: 'system' | 'vendor'): string {
  return `/work/code/$(whoami)/${codePullRelPath(runId, kind)}`
}

/** 给 bridge-exec 用：双引号包裹，保留 $(whoami) 展开 */
export function dqLinuxPath(linuxPath: string): string {
  return `"${String(linuxPath).replace(/"/g, '\\"')}"`
}

export function codePullWinPath(mappedRoot: string, runId: string, kind: 'system' | 'vendor'): string {
  let root = mappedRoot.trim().replace(/\//g, '\\')
  if (/^[A-Za-z]:$/.test(root)) root = `${root}\\`
  root = root.replace(/\\+$/, '')
  const rel = codePullRelPath(runId, kind).replace(/\//g, '\\')
  return `${root}\\${rel}`
}

export function tmuxRepoSession(runId: string, kind: 'system' | 'vendor'): string {
  const short = runId.replace(/[^a-zA-Z0-9]/g, '').slice(-12)
  const tag = kind === 'system' ? 'sys' : 'vnd'
  return `cps-${tag}-${short}`
}

/** mkdir + cd + repo init（短命令，bridge-exec 同步跑） */
export function buildRepoInitCommand(linuxPath: string, repoInitCmd: string): string {
  const p = dqLinuxPath(linuxPath)
  return [
    `mkdir -p ${p}`,
    `cd ${p}`,
    repoInitCmd,
    `echo REPO_INIT_OK`,
  ].join(' && ')
}

/** 在目标目录 tmux 启动 repo sync（-c 仅当前分支；-j64 并行作业加速） */
export function buildRepoSyncTmuxStart(opts: {
  session: string
  linuxPath: string
}): string {
  const { session, linuxPath } = opts
  const p = dqLinuxPath(linuxPath)
  const logFile = `${CODE_PULL_REMOTE_DIR}/${session}.log`
  const doneFile = `${CODE_PULL_REMOTE_DIR}/${session}.done`
  // inner 里路径已双引号；再整体 shellQuote 交给 bash -lc
  const inner = [
    `cd ${p}`,
    `repo sync -c -j64 >${CODE_PULL_REMOTE_DIR}/${session}.log 2>&1`,
    `echo $? > ${CODE_PULL_REMOTE_DIR}/${session}.done`,
  ].join('; ')

  return [
    `mkdir -p ${CODE_PULL_REMOTE_DIR}`,
    `mkdir -p ${p}`,
    `command -v tmux >/dev/null || { echo 'TMUX_MISSING'; exit 127; }`,
    `command -v repo >/dev/null || { echo 'REPO_MISSING'; exit 127; }`,
    `tmux has-session -t ${shellQuote(session)} 2>/dev/null && tmux kill-session -t ${shellQuote(session)} || true`,
    `rm -f ${doneFile}`,
    `tmux new-session -d -s ${shellQuote(session)} -- bash -lc ${shellQuote(inner)}`,
    `sleep 1`,
    `tmux has-session -t ${shellQuote(session)} 2>/dev/null || { echo 'TMUX_START_FAILED'; exit 1; }`,
    `echo TMUX_STARTED:${session}`,
    `echo LOG:${logFile}`,
    `echo DONE:${doneFile}`,
  ].join(' && ')
}

export function buildRepoSyncTmuxPoll(session: string): string {
  const logFile = `${CODE_PULL_REMOTE_DIR}/${session}.log`
  const doneFile = `${CODE_PULL_REMOTE_DIR}/${session}.done`
  return [
    `echo ---POLL---`,
    `if tmux has-session -t ${shellQuote(session)} 2>/dev/null; then echo tmux=alive; else echo tmux=dead; fi`,
    `if [ -f ${doneFile} ]; then echo done_code=$(cat ${doneFile}); else echo done_code=; fi`,
    `echo ---LOG_TAIL---`,
    `tail -n 80 ${logFile} 2>/dev/null || true`,
  ].join('; ')
}

function stripKindPrefix(line: string): string {
  return line.replace(/^\[[^\]]+\]\s*/, '').trim()
}

export interface FailedRepoItem {
  project: string
  reason: string
  kind: 'fetch' | 'checkout' | 'other'
  /** system | vendor */
  scope?: string
}

/**
 * 从 repo sync 日志解析失败仓库清单（去重，按首次出现保留）。
 */
export function parseFailedReposFromLog(lines: string[]): FailedRepoItem[] {
  const byProject = new Map<string, FailedRepoItem>()

  const upsert = (project: string, reason: string, kind: FailedRepoItem['kind']) => {
    const p = project.trim()
    if (!p) return
    const prev = byProject.get(p)
    if (!prev) {
      byProject.set(p, { project: p, reason: reason.slice(0, 300), kind })
      return
    }
    // 已有 fetch，后续 checkout 信息更具体则升级
    if (prev.kind === 'fetch' && kind === 'checkout') {
      byProject.set(p, { project: p, reason: reason.slice(0, 300), kind })
    } else if (reason.length > prev.reason.length) {
      byProject.set(p, { ...prev, reason: reason.slice(0, 300) })
    }
  }

  for (const raw of lines) {
    const line = stripKindPrefix(raw)
    if (!line) continue

    let m = line.match(/error:\s*Cannot fetch\s+(\S+?)(?:\s+\(|\s+from\s+|\s*$)/i)
    if (m) {
      const reasonMatch = line.match(/Cannot fetch\s+\S+\s*(.*)$/i)
      upsert(m[1].replace(/:$/, ''), (reasonMatch?.[1] || line).trim() || 'Cannot fetch', 'fetch')
      continue
    }

    m = line.match(/error:\s*Cannot checkout\s+([^:]+):\s*(.*)$/i)
    if (m) {
      upsert(m[1].trim(), (m[2] || line).trim(), 'checkout')
      continue
    }

    m = line.match(/ManifestInvalidRevisionError:\s*(.+)$/i)
    if (m) {
      const proj = m[1].match(/in\s+(\S+)\s+not found/i)?.[1]
        || m[1].match(/in\s+(\S+)/i)?.[1]
      if (proj) upsert(proj, m[1].trim(), 'checkout')
      continue
    }

    if (/no space left on device|disk quota exceeded|ENOSPC/i.test(line)) {
      upsert('(disk)', line.slice(0, 240), 'other')
    }
  }

  return [...byProject.values()].sort((a, b) => a.project.localeCompare(b.project))
}

/**
 * 从 repo sync 日志尾提取可读失败原因（优先磁盘满 / checkout 失败）。
 * 自后向前扫描，返回第一条命中的原文（截断）。
 */
export function detectRepoSyncFailureInLog(lines: string[]): string | null {
  const cleaned = lines.map(stripKindPrefix).filter(Boolean)
  for (const line of [...cleaned].reverse()) {
    if (/no space left on device/i.test(line)) return line.slice(0, 240)
    if (/disk quota exceeded/i.test(line)) return line.slice(0, 240)
    if (/ENOSPC/i.test(line)) return line.slice(0, 240)
  }
  for (const line of [...cleaned].reverse()) {
    if (/cannot checkout/i.test(line)) return line.slice(0, 240)
    if (/error:\s*unable to write file/i.test(line)) return line.slice(0, 240)
    if (/fatal:\s*cannot create directory/i.test(line)) return line.slice(0, 240)
    if (/fatal:.*\berror\b/i.test(line)) return line.slice(0, 240)
    if (/error:\s*Exited sync due to/i.test(line)) return line.slice(0, 240)
  }
  return null
}

/** 组装面向 UI 红条的失败文案 */
export function formatRepoSyncFailure(opts: {
  kind: string
  lines: string[]
  doneCode?: number | null
  fallback: string
  failedRepos?: FailedRepoItem[]
}): string {
  const failed = opts.failedRepos?.length
    ? opts.failedRepos
    : parseFailedReposFromLog(opts.lines)
  const fromLog = detectRepoSyncFailureInLog(opts.lines)
  const prefix = `${opts.kind} repo sync 失败`
  const listHint = failed.length
    ? `；失败仓库 ${failed.length} 个：${failed.slice(0, 5).map(f => f.project).join(', ')}${failed.length > 5 ? '…' : ''}`
    : ''

  if (fromLog) {
    const hint = /no space left|disk quota|ENOSPC/i.test(fromLog)
      ? '（磁盘空间不足，请清理堡垒机 /work/code 后重试）'
      : ''
    return `${prefix}: ${fromLog}${hint}${listHint}`
  }
  if (opts.doneCode != null && opts.doneCode !== 0) {
    return `${prefix} exit=${opts.doneCode}${listHint}`
  }
  const base = opts.fallback.startsWith(opts.kind) ? opts.fallback : `${opts.kind} ${opts.fallback}`
  return `${base}${listHint}`
}

export { parseTmuxPollOutput, shellQuote }
export type { TmuxPollSnapshot }
