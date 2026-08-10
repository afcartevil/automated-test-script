/**
 * ez-build 远端 tmux 启动 / 轮询命令与解析（纯函数，便于单测）
 */

export const EA_BUILD_DIR = '~/code/ea-build'

export interface TmuxPollSnapshot {
  alive: boolean
  doneCode: number | null
  logTail: string
  lines: string[]
}

export function shellQuote(s: string): string {
  return `'${String(s).replace(/'/g, `'\"'\"'`)}'`
}

export function tmuxSessionName(runId: string, project: string): string {
  const safe = String(project).replace(/[^a-zA-Z0-9_-]/g, '_').slice(0, 32)
  const short = runId.replace(/^build-/, '').replace(/[^a-zA-Z0-9]/g, '').slice(-10)
  return `ezb-${safe}-${short}`
}

export function buildDeployCommand(scriptB64: string): string {
  return [
    `mkdir -p ${EA_BUILD_DIR}`,
    `echo ${shellQuote(scriptB64)} | base64 -d > ${EA_BUILD_DIR}/ez-build.sh`,
    `chmod +x ${EA_BUILD_DIR}/ez-build.sh`,
    `wc -c ${EA_BUILD_DIR}/ez-build.sh`,
  ].join(' && ')
}

export function buildEzBuildArgv(input: {
  project: string
  variant: string
  buildFlag: string
  targetRaw: string
  systemLinux: string
  vendorLinux: string
}): string {
  return [
    'bash ./ez-build.sh',
    shellQuote(input.project),
    shellQuote(input.variant),
    shellQuote(input.buildFlag),
    shellQuote(input.targetRaw),
    input.systemLinux,
    input.vendorLinux,
  ].join(' ')
}

export function buildTmuxStartCommand(opts: {
  session: string
  project: string
  variant: string
  buildFlag: string
  targetRaw: string
  systemLinux: string
  vendorLinux: string
}): string {
  const session = opts.session
  const doneFile = `${EA_BUILD_DIR}/${session}.done`
  const logFile = `${EA_BUILD_DIR}/${session}.log`
  const argv = buildEzBuildArgv(opts)
  const inner = [
    `cd ${EA_BUILD_DIR}`,
    `${argv} >${session}.log 2>&1`,
    `echo $? > ${session}.done`,
  ].join('; ')

  return [
    `mkdir -p ${EA_BUILD_DIR}`,
    `command -v tmux >/dev/null || { echo 'TMUX_MISSING'; exit 127; }`,
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

export function buildTmuxPollCommand(session: string): string {
  const logFile = `${EA_BUILD_DIR}/${session}.log`
  const doneFile = `${EA_BUILD_DIR}/${session}.done`
  return [
    `echo '---POLL---'`,
    `if tmux has-session -t ${shellQuote(session)} 2>/dev/null; then echo 'tmux=alive'; else echo 'tmux=dead'; fi`,
    `if [ -f ${doneFile} ]; then echo "done_code=$(cat ${doneFile} | tr -d '[:space:]')"; else echo 'done_code='; fi`,
    `echo '---LOG_TAIL---'`,
    `tail -n 50 ${logFile} 2>/dev/null || true`,
  ].join('; ')
}

export function buildTmuxKillCommand(session: string): string {
  return `tmux has-session -t ${shellQuote(session)} 2>/dev/null && tmux kill-session -t ${shellQuote(session)} || true`
}

export function parseTmuxPollOutput(raw: string): TmuxPollSnapshot {
  const text = String(raw || '')
  const alive = /(?:^|\n)tmux=alive(?:\n|$)/.test(text)
  const doneMatch = text.match(/(?:^|\n)done_code=([0-9]*)(?:\n|$)/)
  let doneCode: number | null = null
  if (doneMatch && doneMatch[1] !== '') {
    doneCode = Number(doneMatch[1])
    if (!Number.isFinite(doneCode)) doneCode = null
  }
  const tailIdx = text.indexOf('---LOG_TAIL---')
  const logTail = tailIdx >= 0 ? text.slice(tailIdx + '---LOG_TAIL---'.length).trim() : ''
  const lines = logTail
    .split(/\r?\n/)
    .map(l => l.replace(/\u001b\[[0-9;]*m/g, '').trim())
    .filter(Boolean)
  return { alive, doneCode, logTail, lines }
}

export function detectBuildFailureInLog(lines: string[]): string | null {
  for (const line of [...lines].reverse()) {
    if (/project dir not found/i.test(line)) return line
    if (/\[ERROR\].*pack failed/i.test(line)) return line
    if (/\[ERROR\].*skip pack/i.test(line)) return line
    if (/\[ERROR\].*some compile targets failed/i.test(line)) return line
    if (/\[ERROR\].*not found/i.test(line)) return line
    if (/\[ERROR\].*invalid build_/i.test(line)) return line
    if (/finished: status=FAILED/i.test(line)) return line
  }
  return null
}

export function detectBuildSuccessInLog(lines: string[], needPack: boolean): boolean {
  const joined = lines.join('\n')
  if (needPack) return /pack success/i.test(joined)
  return /all requested compile targets succeeded/i.test(joined)
    || (/all compile targets succeeded/i.test(joined) && !/skip pack/i.test(joined))
}
