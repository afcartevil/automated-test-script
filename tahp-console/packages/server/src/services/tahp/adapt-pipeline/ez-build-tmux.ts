import { existsSync, mkdirSync, copyFileSync, rmSync, writeFileSync } from 'fs'
import { join } from 'path'

export const EA_BUILD_DIR = '~/code/ea-build'
/** Windows 映射盘上的 ea-build（默认 Z:，运行时以 Samba 根 + 配置盘符为准） */
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

export function buildDeployCommand(scriptB64: string, linuxDir = EA_BUILD_DIR): string {
  return [
    `mkdir -p ${linuxDir}`,
    `echo ${shellQuote(scriptB64)} | base64 -d > ${linuxDir}/ez-build.sh`,
    `chmod +x ${linuxDir}/ez-build.sh`,
    `wc -c ${linuxDir}/ez-build.sh`,
  ].join(' && ')
}

export function buildEzBuildChmodCommand(linuxDir: string): string {
  const dir = String(linuxDir || '').replace(/\/+$/, '')
  const sh = `${dir}/ez-build.sh`
  return `chmod +x ${shellQuote(sh)} && wc -c ${sh}`
}

/** 在映射盘创建 ea-build 并写入 ez-build.sh（避免齐治传脚本） */
export function copyEzBuildScriptToMappedEaBuild(script: string, destDir: string): string {
  const dir = String(destDir || '').trim()
  if (!dir) throw new Error('ea-build 映射盘目录为空')
  if (!existsSync(dir)) {
    try {
      mkdirSync(dir, { recursive: true })
    } catch (err) {
      throw new Error(`无法创建 ${dir}，请确认映射盘已挂载：${(err as Error).message}`)
    }
  }
  const dest = join(dir, 'ez-build.sh')
  writeFileSync(dest, String(script ?? '').replace(/\r\n/g, '\n').replace(/\r/g, '\n'), 'utf-8')
  if (!existsSync(dest)) throw new Error(`写入后未找到 ${dest}`)
  return dest
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
export function buildConfDeployCommands(confB64: string, chunkSize = 4000, linuxDir = EA_BUILD_DIR): string[] {
  const destB64 = `${linuxDir}/conf.json.b64`
  const dest = `${linuxDir}/conf.json`
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
  eaBuildDir?: string
}): string {
  const session = opts.session
  const dir = opts.eaBuildDir || EA_BUILD_DIR
  const doneFile = `${dir}/${session}.done`
  const logFile = `${dir}/${session}.log`
  const argv = buildEzBuildArgv(opts)
  const inner = [
    `cd ${dir}`,
    `${argv} >${session}.log 2>&1`,
    `echo $? > ${session}.done`,
  ].join('; ')

  return [
    `mkdir -p ${dir}`,
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

export function buildTmuxPollCommand(session: string, eaBuildDir = EA_BUILD_DIR): string {
  const logFile = `${eaBuildDir}/${session}.log`
  const doneFile = `${eaBuildDir}/${session}.done`
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

/**
 * 停掉堡垒机 tmux 编译：先 Ctrl+C 触发 ez-build.sh 的 INT trap（杀子进程），
 * 再杀进程组 / session，最后按会话日志名扫残留，避免留下第二份 ninja/make。
 */
export function buildTmuxKillCommand(session: string): string {
  const s = shellQuote(session)
  const logPat = shellQuote(`${session}.log`)
  return [
    `if tmux has-session -t ${s} 2>/dev/null; then`,
    `  tmux send-keys -t ${s} C-c || true`,
    `  sleep 2`,
    `  pane_pid=$(tmux list-panes -t ${s} -F '#{pane_pid}' 2>/dev/null | head -n1)`,
    `  if [ -n "$pane_pid" ]; then`,
    `    pgid=$(ps -o pgid= -p "$pane_pid" 2>/dev/null | tr -d ' ')`,
    `    if [ -n "$pgid" ]; then kill -TERM -"$pgid" 2>/dev/null || true; sleep 1; kill -KILL -"$pgid" 2>/dev/null || true; fi`,
    `  fi`,
    `  tmux kill-session -t ${s} || true`,
    `fi`,
    `pkill -TERM -f ${logPat} 2>/dev/null || true`,
    `sleep 1`,
    `pkill -KILL -f ${logPat} 2>/dev/null || true`,
    `true`,
  ].join('\n')
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
