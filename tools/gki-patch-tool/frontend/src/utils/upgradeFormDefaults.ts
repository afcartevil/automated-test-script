const STORAGE_KEY = 'gki_upgrade_form_v1'

/** Fields restored on next visit (tags are filled per task). */
export const UPGRADE_PERSIST_KEYS = [
  'target_repo_dir',
  'commit_message',
  'build_workdir',
  'build_command',
  'remote_temp_dir',
  'local_repo_mount',
  'auto_commit',
  'auto_resolve_conflicts',
  'auto_build',
  'auto_fix_build_errors',
] as const

export type UpgradePersistKey = (typeof UPGRADE_PERSIST_KEYS)[number]

export function loadUpgradeFormDefaults(): Partial<Record<UpgradePersistKey, unknown>> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return {}
    const data = JSON.parse(raw)
    return data && typeof data === 'object' ? data : {}
  } catch {
    return {}
  }
}

export function saveUpgradeFormDefaults(form: Record<string, unknown>) {
  try {
    const out: Record<string, unknown> = {}
    for (const key of UPGRADE_PERSIST_KEYS) {
      if (form[key] !== undefined && form[key] !== '') {
        out[key] = form[key]
      }
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(out))
    // legacy keys used elsewhere
    if (form.target_repo_dir) localStorage.setItem('gki_last_target_repo', String(form.target_repo_dir))
    if (form.remote_temp_dir) localStorage.setItem('gki_last_remote_temp_dir', String(form.remote_temp_dir))
    if (form.local_repo_mount) localStorage.setItem('gki_last_local_repo_mount', String(form.local_repo_mount))
    if (form.commit_message) localStorage.setItem('gki_last_commit_message', String(form.commit_message))
  } catch {
    // ignore
  }
}

export function clearUpgradeFormDefaults() {
  try {
    localStorage.removeItem(STORAGE_KEY)
    localStorage.removeItem('gki_last_target_repo')
    localStorage.removeItem('gki_last_remote_temp_dir')
    localStorage.removeItem('gki_last_local_repo_mount')
    localStorage.removeItem('gki_last_commit_message')
  } catch {
    // ignore
  }
}

export function createEmptyUpgradeForm() {
  return {
    from_tag: '',
    to_tag: '',
    target_repo_dir: '',
    analysis_task_id: '',
    commit_message: '',
    build_workdir: '',
    build_command: '',
    remote_temp_dir: '',
    local_repo_mount: '',
    auto_commit: false,
    auto_resolve_conflicts: false,
    auto_build: false,
    auto_fix_build_errors: false,
    remote: true,
  }
}

export function applyUpgradeFormDefaults(form: Record<string, any>) {
  const saved = loadUpgradeFormDefaults()
  for (const key of UPGRADE_PERSIST_KEYS) {
    if (saved[key] !== undefined && saved[key] !== null && saved[key] !== '') {
      form[key] = saved[key]
    }
  }
  form.remote = true
}

export type UpgradePreset = 'full-auto' | 'manual' | 'custom'

export function applyUpgradePreset(form: Record<string, any>, preset: UpgradePreset) {
  if (preset === 'full-auto') {
    form.auto_commit = true
    form.auto_build = true
    form.auto_resolve_conflicts = true
    form.auto_fix_build_errors = true
    return
  }
  if (preset === 'manual') {
    form.auto_commit = false
    form.auto_build = false
    form.auto_resolve_conflicts = false
    form.auto_fix_build_errors = false
    return
  }
}

/** GET /api/upgrade/jobs/:id 返回 `{ job, progress }`；列表项则是任务本身。 */
export function unwrapUpgradeJob(data: Record<string, any> | null | undefined): Record<string, any> | null {
  if (!data || typeof data !== 'object') return null
  if (data.job && typeof data.job === 'object' && !Array.isArray(data.job)) return data.job
  return data
}

export function jobToUpgradeForm(job: Record<string, any>) {
  const opts = job.options || {}
  return {
    from_tag: job.from_tag || '',
    to_tag: job.to_tag || '',
    target_repo_dir: job.target_repo_dir || '',
    build_workdir: job.build_workdir || '',
    build_command: job.build_command || '',
    remote_temp_dir: job.remote_temp_dir || opts.remote_temp_dir || '',
    local_repo_mount: job.local_repo_mount || opts.local_repo_mount || '',
    remote: true,
    auto_commit: !!opts.auto_commit,
    auto_resolve_conflicts: !!opts.auto_resolve_conflicts,
    auto_build: !!opts.auto_build,
    auto_fix_build_errors: !!opts.auto_fix_build_errors,
    commit_message: opts.commit_message || '',
    analysis_task_id: job.analysis_task_id || '',
  }
}
