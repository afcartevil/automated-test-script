import { existsSync, mkdirSync, copyFileSync, rmSync } from 'fs'
import { join } from 'path'

export const EA_BUILD_DIR = '~/code/ea-build'
/** Windows 映射盘上的同一目录（Z: = 用户工作盘） */
export const EA_BUILD_WIN_DIR = 'Z:\\ea-build'

export interface TmuxPollSnapshot {
  alive: boolean
  /** 输出里有独立一行 tmux=alive|dead（齐治登录界面等垃圾输出则为 false） */
  recognized: boolean
  doneCode: number | null
  logTail: string
  lines: string[]
}

export function tmuxStartConfirmed(output: string, session: string): boolean {
  const name = String(session || '').trim()
  if (!name) return false
  return String(output || '').includes(`TMUX_STARTED:${name}`)
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

/** 把共享盘 conf.json 拷到映射盘 ea-build，避免齐治分块传输 */
export function copyConfJsonToMappedEaBuild(srcPath: string, destDir = EA_BUILD_WIN_DIR): string {
  const src = String(srcPath || '').trim()
  if (!src || !existsSync(src)) throw new Error(`conf.json 源不存在: ${src}`)
  if (!existsSync(destDir)) {
    try {
      mkdirSync(destDir, { recursive: true })
    } catch (err) {
      throw new Error(`无法创建 ${destDir}，请确认 Z: 已映射：${(err as Error).message}`)
    }
  }
  const dest = join(destDir, 'conf.json')
  copyFileSync(src, dest)
  try { rmSync(join(destDir, 'conf.json.b64'), { force: true }) } catch { /* leftover chunk file */ }
  if (!existsSync(dest)) throw new Error(`拷贝后未找到 ${dest}`)
  return dest
}

/** @deprecated 仅保留单测；生产改为 copyConfJsonToMappedEaBuild */
export function buildConfDeployCommands(confB64: string, chunkSize = 4000): string[] {
  const destB64 = `${EA_BUILD_DIR}/conf.json.b64`
  const dest = `${EA_BUILD_DIR}/conf.json`
  const cmds = [
    `mkdir -p ${EA_BUILD_DIR} && rm -f ${destB64} ${dest}`,
  ]
  for (let i = 0; i < confB64.length; i += chunkSize) {
    cmds.push(`printf %s ${shellQuote(confB64.slice(i, i + chunkSize))} >> ${destB64}`)
  }
  cmds.push(`base64 -d ${destB64} > ${dest} && rm -f ${destB64} && wc -c ${dest}`)
  return cmds
}

export function buildEzBuildArgv(input: {
  project: string
  variant: string
  buildFlag: string
  targetRaw: string
  systemLinux: string
  vendorLinux: string
  trsysLinux?: string
  sysVersion?: string
}): string {
  const argv = [
    'bash ./ez-build.sh',
    shellQuote(input.project),
    shellQuote(input.variant),
    shellQuote(input.buildFlag),
    shellQuote(input.targetRaw),
    input.systemLinux?.trim() ? input.systemLinux : "''",
    input.vendorLinux,
    input.trsysLinux?.trim() ? input.trsysLinux : "''",
  ]
  const sysVersion = String(input.sysVersion ?? '').trim()
  if (sysVersion) argv.push(shellQuote(sysVersion))
  return argv.join(' ')
}

export function buildTmuxStartCommand(opts: {
  session: string
  project: string
  variant: string
  buildFlag: string
  targetRaw: string
  systemLinux: string
  vendorLinux: string
  trsysLinux?: string
  sysVersion?: string
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
  // 避免双引号内再套 '[:space:]'：经 Windows PowerShell -File 转发时会被拆成 harness 未知参数。
  // $(cat …) 本身会去掉尾部换行；parseTmuxPollOutput 再 trim 空白。
  return [
    `echo ---POLL---`,
    `if tmux has-session -t ${shellQuote(session)} 2>/dev/null; then echo tmux=alive; else echo tmux=dead; fi`,
    `if [ -f ${doneFile} ]; then echo done_code=$(cat ${doneFile}); else echo done_code=; fi`,
    `echo ---LOG_TAIL---`,
    `tail -n 50 ${logFile} 2>/dev/null || true`,
  ].join('; ')
}

export function buildTmuxKillCommand(session: string): string {
  return `tmux has-session -t ${shellQuote(session)} 2>/dev/null && tmux kill-session -t ${shellQuote(session)} || true`
}

export function parseTmuxPollOutput(raw: string): TmuxPollSnapshot {
  const text = String(raw || '')
  const alive = /(?:^|\n)tmux=alive(?:\n|$)/.test(text)
  const recognized = /(?:^|\n)tmux=(?:alive|dead)(?:\n|$)/.test(text)
  const doneMatch = text.match(/(?:^|\n)done_code=([^\n\r]*)/)
  let doneCode: number | null = null
  if (doneMatch) {
    const rawCode = String(doneMatch[1] ?? '').replace(/\s+/g, '')
    if (rawCode !== '') {
      doneCode = Number(rawCode)
      if (!Number.isFinite(doneCode)) doneCode = null
    }
  }
  const tailIdx = text.indexOf('---LOG_TAIL---')
  const logTail = tailIdx >= 0 ? text.slice(tailIdx + '---LOG_TAIL---'.length).trim() : ''
  const lines = logTail
    .split(/\r?\n/)
    .map(l => l.replace(/\u001b\[[0-9;]*m/g, '').trim())
    .filter(Boolean)
  return { alive, recognized, doneCode, logTail, lines }
}

export function detectBuildFailureInLog(lines: string[]): string | null {
  for (const line of [...lines].reverse()) {
    if (/project dir not found/i.test(line)) return line
    if (/\[ERROR\].*pack failed/i.test(line)) return line
    if (/\[ERROR\].*skip pack/i.test(line)) return line
    if (/\[ERROR\].*some compile targets failed/i.test(line)) return line
    if (/\[ERROR\].*pipe_main not found/i.test(line)) return line
    if (/\[ERROR\].*conf\.json not found/i.test(line)) return line
    if (/\[ERROR\].*trsys dir missing/i.test(line)) return line
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
