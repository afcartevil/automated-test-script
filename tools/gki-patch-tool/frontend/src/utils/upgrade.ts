export const RESUME_PHASE_LABELS: Record<string, string> = {
  build: '编译验证',
  build_fix: 'AI 修复编译',
  commit: '提交代码',
  applied: '合入完成',
  apply: '合入 Patch',
  prepare: '准备环境',
}

export const UPGRADE_CANCELLABLE = new Set([
  'pending',
  'running',
  'conflicts',
  'applied',
  'committed',
  'build_failed',
  'commit_failed',
  'awaiting_ssh',
  'awaiting_otp',
])

export function jobDisplayStatus(job?: Record<string, any>) {
  if (!job) return ''
  if (job.status === 'commit_failed') return 'commit_failed'
  if (job.status === 'build_failed' && job.phase === 'commit' && job.build_exit_code === 0) {
    return 'commit_failed'
  }
  return job.status || ''
}

export function effectiveUpgradeStatus(job?: Record<string, any>, prog?: Record<string, any>) {
  job = job || {}
  prog = prog || {}
  const js = job.status || ''
  const ps = prog.status || ''
  const phase = String(prog.phase || job.phase || '').trim()
  const buildExit = job.build_exit_code ?? prog.build_exit_code

  if (js === 'commit_failed' || ps === 'commit_failed') return 'commit_failed'

  // Legacy: compile succeeded (exit 0) but commit failed was stored as build_failed
  if (
    (js === 'build_failed' || ps === 'build_failed')
    && phase === 'commit'
    && buildExit === 0
  ) {
    return 'commit_failed'
  }

  // Live progress (WS / in-memory) wins when compile or build_fix is actively running
  if (
    ps === 'running'
    && ['build', 'build_fix'].includes(phase)
    && ['build_failed', 'committed', 'applied', 'cancelled'].includes(js)
  ) {
    return 'running'
  }

  const buildTiming = (prog.phase_timings || job.options?.phase_timings || {}).phases?.build
  if (buildTiming?.running && js === 'build_failed') return 'running'

  if (js && (!ps || ps === 'unknown')) return js
  return js || ps || ''
}

export function upgradeResumePhaseHint(job?: Record<string, any>) {
  const opts = (job && job.options) || {}
  const rp = opts.resume_point || {}
  let ph = (rp.phase || opts.last_active_phase || '').trim()
  if (!ph && Array.isArray(opts.progress_log)) {
    for (let i = opts.progress_log.length - 1; i >= 0; i--) {
      const p = (opts.progress_log[i].phase || '').trim()
      if (p && !['cancelled', 'resume', 'failed', 'done'].includes(p)) {
        ph = p
        break
      }
    }
  }
  if (!ph && (job?.build_log_file || job?.build_command)) ph = 'build'
  if (!ph && opts.build_fix && opts.build_fix.status === 'running') ph = 'build_fix'
  return RESUME_PHASE_LABELS[ph] || ph || '上次进度'
}

export function upgradeStatusText(status?: string) {
  const map: Record<string, string> = {
    pending: '等待',
    running: '运行中',
    conflicts: '有冲突',
    applied: '已合入',
    committed: '已提交',
    completed: '完成',
    failed: '失败',
    build_failed: '编译失败',
    commit_failed: '提交失败',
    build_fix: 'AI 修复编译',
    aborted: '已中止',
    cancelled: '已取消',
    awaiting_ssh: '待连 cqris',
    awaiting_otp: '待输入 OTP',
  }
  return map[status || ''] || status || '-'
}

export function isUpgradeTerminalStatus(status?: string) {
  return ['completed', 'failed', 'cancelled', 'aborted'].includes(status || '')
}

export async function maybePromptRemoteOtp(job?: Record<string, any>) {
  if (!job?.options?.remote || job.ssh_connected) return null
  const otp = window.prompt('请输入 6 位 OTP 动态码（2nd Password）:')
  if (!otp || otp.trim().length < 4) {
    throw new Error('未输入有效 OTP')
  }
  return { otp: otp.trim() }
}

/** 弹窗收集 cqris / 目标机账号（不含 OTP）。 */
export async function promptRemoteSshAccounts(
  cfg: Record<string, any>,
): Promise<Record<string, string>> {
  const bastionUser = window.prompt('cqris 堡垒机用户名:')?.trim() || ''
  const bastionPassword = window.prompt('cqris 堡垒机密码:') || ''
  const targetIp =
    window.prompt(`目标服务器 IP（默认 ${cfg.target_ip || '10.205.0.158'}）:`)?.trim() ||
    String(cfg.target_ip || '').trim()
  const targetUser = window.prompt('目标服务器用户名:')?.trim() || ''
  const targetPassword = window.prompt('目标服务器密码:') || ''

  if (!bastionUser || !bastionPassword || !targetUser || !targetPassword) {
    throw new Error('远程合入需要完整的 SSH 账号信息')
  }
  if (!targetIp) {
    throw new Error('请填写目标服务器 IP')
  }
  return {
    bastion_user: bastionUser,
    bastion_password: bastionPassword,
    target_ip: targetIp,
    target_user: targetUser,
    target_password: targetPassword,
  }
}

/** 创建远程升级任务前解析 SSH 账号（与 legacy GKI升级 一致）。 */
export async function resolveRemoteSshForStart(
  fetchConfig: () => Promise<Record<string, any>>,
): Promise<Record<string, string> | null> {
  const cfg = await fetchConfig()
  if (cfg.credentials_configured) return null
  return promptRemoteSshAccounts(cfg)
}

/**
 * 远程任务操作前解析 SSH 凭据。
 * 已保存到 local yaml 时只需 OTP；否则先收集账号（可选保存）再要 OTP。
 */
export async function resolveRemoteSshPayload(
  job?: Record<string, any>,
  fetchConfig?: () => Promise<Record<string, any>>,
): Promise<Record<string, string> | null> {
  if (!job?.options?.remote || job.ssh_connected) return null

  const loadConfig =
    fetchConfig ||
    (async () => {
      const { api } = await import('../api')
      return api.get<any>('/api/upgrade/ssh-config')
    })

  const cfg = await loadConfig()
  let accounts: Record<string, string> | null = null

  if (!cfg.credentials_configured) {
    const save = window.confirm(
      '未检测到已保存的远程 SSH 账号。\n\n' +
        '点击「确定」填写账号（将保存到系统设置数据库）；\n' +
        '点击「取消」可前往「系统设置 → 远程 SSH」填写后重试。',
    )
    if (!save) {
      throw new Error('缺少 cqris 用户名：请先在「系统设置」保存远程 SSH 账号，或在本弹窗中填写')
    }
    accounts = await promptRemoteSshAccounts(cfg)
    const { api } = await import('../api')
    await api.put('/api/upgrade/ssh-credentials', accounts)
  }

  const otp = window.prompt('请输入 6 位 OTP 动态码（2nd Password）:')?.trim() || ''
  if (otp.length < 4) {
    throw new Error('未输入有效 OTP')
  }

  return accounts ? { ...accounts, otp } : { otp }
}

/** 连接 cqris 前确保本地已保存 SSH 账号（后端重启后内存凭据会丢失）。 */
export async function ensureRemoteSshSaved(
  fetchConfig: () => Promise<Record<string, any>>,
  saveCredentials: (body: Record<string, string>) => Promise<unknown>,
): Promise<void> {
  const cfg = await fetchConfig()
  if (cfg.credentials_configured) return

  const save = window.confirm(
    '连接 cqris 前需要保存 SSH 账号。\n\n' +
      '点击「确定」填写并保存到本地；\n' +
      '点击「取消」请前往「系统设置 → 远程 SSH」配置。',
  )
  if (!save) {
    throw new Error('缺少 cqris 用户名：请先在「系统设置」保存远程 SSH 账号')
  }
  const accounts = await promptRemoteSshAccounts(cfg)
  await saveCredentials(accounts)
}

export async function remoteSshBody(
  job?: Record<string, any>,
  fetchConfig?: () => Promise<Record<string, any>>,
) {
  const payload = await resolveRemoteSshPayload(job, fetchConfig)
  return payload ? { remote_ssh: payload } : {}
}

export function buildGerritDiffRowsFallback(before: string, after: string) {
  const oldL = (before || '').split('\n').filter((_, i, a) => i < a.length - 1 || a[i] !== '')
  const newL = (after || '').split('\n').filter((_, i, a) => i < a.length - 1 || a[i] !== '')
  if (!oldL.length && !newL.length) return []
  const rows = []
  const max = Math.max(oldL.length, newL.length)
  for (let i = 0; i < max; i++) {
    const ol = oldL[i]
    const nl = newL[i]
    let lcls = 'ctx'
    let rcls = 'ctx'
    if (ol === undefined) {
      lcls = 'empty'
      rcls = 'add'
    } else if (nl === undefined) {
      lcls = 'del'
      rcls = 'empty'
    } else if (ol !== nl) {
      lcls = 'chg'
      rcls = 'chg'
    }
    rows.push({
      left: { num: ol !== undefined ? i + 1 : null, text: ol || '', cls: lcls },
      right: { num: nl !== undefined ? i + 1 : null, text: nl || '', cls: rcls },
    })
  }
  return rows
}

export type GerritSubmissionRow = {
  repo_key?: string
  repo_label?: string
  repo_root?: string
  commit_sha?: string
  pushed?: boolean
  push_cmd?: string
  review_branch?: string
  gerrit_url?: string
  gerrit_urls?: string[]
  push_error?: string
  paths?: string[]
}

export function gerritSubmissionsForJob(
  job?: Record<string, any>,
  progress?: Record<string, any>,
): GerritSubmissionRow[] {
  const fromProgress = progress?.gerrit_submissions
  if (Array.isArray(fromProgress) && fromProgress.length) {
    return fromProgress.filter((row) => row && typeof row === 'object')
  }
  const fromJob = job?.options?.gerrit_submissions
  if (Array.isArray(fromJob) && fromJob.length) {
    return fromJob.filter((row) => row && typeof row === 'object')
  }
  return []
}
