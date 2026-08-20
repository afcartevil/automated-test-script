import { computed, ref, watch } from 'vue'
import {
  importBranchTemplates,
  continueModemBaselineRun,
  createModemPatchRule,
  createRepoProfile,
  createModemBaselineRun,
  deleteRepoProfile,
  deleteModemPatchRule,
  getModemBaselineDefaults,
  getModemBaselineLog,
  getModemBaselineRun,
  getWorkspaceProfile,
  listBranchTemplates,
  listModemBuildProjects,
  listModemPatchRules,
  listModemBaselineRuns,
  listRepoProfiles,
  openModemBaselineConflictFile,
  parseModemPatchNotice,
  precheckModemBaseline,
  refreshRepoBranches,
  refreshModemBaselineConflicts,
  recommendModemPatch,
  saveWorkspaceProfile,
  scanRepoProfiles,
  subscribeModemBaselineEvents,
  listModemBaselineNotices,
  applyModemBaselineNotice,
  dismissModemBaselineNotice,
  updateRepoProfile,
  updateModemPatchRule,
  type ModemBaselineConfig,
  type ModemBaselinePhase,
  type ModemBaselineRunMeta,
  type ModemBaselineStatus,
  type ModemExternalNotice,
  type BranchRule,
  type BranchTemplate,
  type NoticeParseResult,
  type PrecheckResult,
  type RecommendationResult,
  type RepoProfile,
  type ScannedRepoCandidate,
  type UserWorkspaceProfile,
} from '@/api/tahp/modem-baseline'
import { appendModemLogTail, takeModemLogTail } from '@/utils/modemBaselineLog'

export type StageItem = {
  key: string
  label: string
  state: 'done' | 'active' | 'pending'
}

type RecommendationApplyResult = {
  applied: boolean
  repoAction?: 'synced_selected' | 'auto_selected' | 'fallback_selected' | 'ambiguous' | 'no_match' | 'no_platform'
  candidates?: Array<{ repoId: string; label: string; platform?: string; localPath: string }>
}

export function emptyModemBaselineConfig(): ModemBaselineConfig {
  return {
    NODE_BRANCH: '',
    target_BRANCH: '',
    AP_lable: '',
    DESCRIPTION: '',
    JIRAID: '',
    work_dir: '',
    mapped_prefix: '',
    remote_prefix: '',
    build_project: undefined,
  }
}

const SELECTED_REPO_STORAGE_KEY = 'tahp_modem_patch_selected_repo'

function loadSelectedRepoId() {
  try {
    return localStorage.getItem(SELECTED_REPO_STORAGE_KEY) || ''
  } catch {
    return ''
  }
}

function saveSelectedRepoId(repoId: string) {
  try {
    if (repoId) localStorage.setItem(SELECTED_REPO_STORAGE_KEY, repoId)
    else localStorage.removeItem(SELECTED_REPO_STORAGE_KEY)
  } catch {}
}

/** 历史列表用的一行状态摘要（失败/冲突优先） */
export function getRunStatusBrief(
  status?: ModemBaselineStatus,
  error?: string,
  phase?: ModemBaselinePhase,
  conflictCount?: number,
) {
  if (status === 'conflict') {
    const n = conflictCount ?? 0
    if (error === 'bridge_not_ready') return '冲突停驻 · bridge 未就绪'
    if (error === 'orphaned_running_process') return '冲突停驻 · 进程已中断'
    return n > 0 ? `冲突停驻 · ${n} 个文件` : '冲突停驻'
  }
  if (status === 'failed') {
    if (error === 'bridge_not_ready') return 'bridge 未就绪'
    if (error === 'build_failed' || phase === 'build') return '编译失败'
    if (phase === 'resume') return '继续执行失败'
    if (phase === 'precheck') return '预检失败'
    return '执行失败'
  }
  if (status === 'running') {
    if (phase === 'build') return '自动编译中'
    if (phase === 'resume') return '继续执行中'
    if (phase === 'precheck') return '预检中'
    return '执行中'
  }
  if (status === 'success') return '已完成'
  return ''
}

export function getStatusMeta(status?: ModemBaselineStatus, error?: string, phase?: ModemBaselinePhase) {
  if (status === 'success') {
    return { label: '执行完成', tone: 'success', summary: '流程已完成，可查看日志、报告与冲突结果。' }
  }
  if (status === 'conflict') {
    const summary = error === 'bridge_not_ready'
      ? '继续执行因 ASF Bridge 未就绪中断。请确认一键配置已保存齐治凭据与 TOTP 后重试（静默 asf bridge up，无需打开 Transhell）。'
      : error === 'orphaned_running_process'
        ? '后台进程已中断，任务已恢复为待继续状态。确认冲突已处理后可再次点击继续执行。'
        : '检测到冲突，需研发手动处理后点击继续执行。'
    return { label: '等待人工处理', tone: 'warn', summary }
  }
  if (status === 'failed') {
    const summary = error === 'bridge_not_ready'
      ? 'ASF Bridge 未就绪。请确认一键配置已保存齐治凭据与 TOTP 后重试（静默 asf bridge up，无需打开 Transhell）。'
      : error === 'build_failed' || phase === 'build'
        ? '自动编译失败，请结合运行日志确认 ./tools/bld_modem.sh 执行结果。'
        : phase === 'resume'
          ? '继续执行阶段失败，请结合运行日志确认 commit、post-merge 或 push 相关步骤。'
          : '执行失败，请结合运行日志定位失败阶段。'
    return { label: '执行失败', tone: 'error', summary }
  }
  if (status === 'running') {
    if (phase === 'build') {
      return { label: '自动编译中', tone: 'info', summary: '继续执行已完成，正在执行 ./tools/bld_modem.sh，请关注实时日志。' }
    }
    if (phase === 'resume') {
      return { label: '继续执行中', tone: 'info', summary: '人工解冲突后正在继续执行 commit、post-merge 与收尾步骤，请关注实时日志。' }
    }
    if (phase === 'precheck') {
      return { label: '执行中', tone: 'info', summary: '正在进行预检，请关注实时日志。' }
    }
    return { label: '执行中', tone: 'info', summary: '正在执行预检、合并或后续处理，请关注实时日志。' }
  }
  return { label: '待启动', tone: 'muted', summary: '加载默认配置后即可启动 Modem 升级。' }
}

export function buildStageItems(status?: ModemBaselineStatus, error?: string, phase?: ModemBaselinePhase): StageItem[] {
  const steps = [
    { key: 'precheck', label: '准备环境' },
    { key: 'merge', label: '合并补丁' },
    { key: 'conflict', label: '冲突停驻' },
    { key: 'resume', label: '继续执行' },
    { key: 'build', label: '自动编译' },
    { key: 'archive', label: '结果归档' },
  ] as const

  const activeKey = status === 'success'
    ? 'archive'
    : status === 'conflict'
      ? 'conflict'
      : phase === 'build'
        ? 'build'
        : phase === 'resume'
          ? 'resume'
          : phase === 'archive'
            ? 'archive'
            : phase === 'precheck'
              ? 'precheck'
              : 'merge'

  const activeIndex = steps.findIndex(item => item.key === activeKey)

  if (status === 'success') {
    return steps.map((item, index) => ({
      ...item,
      state: index < activeIndex ? 'done' : item.key === 'archive' ? 'active' : 'done',
    }))
  }

  if (status === 'conflict') {
    return steps.map((item, index) => ({
      ...item,
      state: index < activeIndex ? 'done' : index === activeIndex ? 'active' : 'pending',
    }))
  }

  if (status === 'failed') {
    const failedKey = error === 'bridge_not_ready'
      ? 'precheck'
      : error === 'build_failed'
        ? 'build'
        : activeKey
    const failedIndex = steps.findIndex(item => item.key === failedKey)
    return steps.map((item, index) => ({
      ...item,
      state: index < failedIndex ? 'done' : index === failedIndex ? 'active' : 'pending',
    }))
  }

  if (status === 'running') {
    return steps.map((item, index) => ({
      ...item,
      state: index < activeIndex ? 'done' : index === activeIndex ? 'active' : 'pending',
    }))
  }

  return steps.map((item, index) => ({
    ...item,
    state: index === 0 ? 'active' : 'pending',
  }))
}

function withString(value?: string) {
  return value?.trim() || '—'
}

function normalizePlatformToken(text?: string) {
  const compact = String(text ?? '').trim().toUpperCase().replace(/[-_\s]+/g, '')
  if (!compact) return ''

  let matched = compact.match(/^(GEN\d+)R(\d+)([STUVW])$/)
  if (matched) {
    const [, family, release, suffix] = matched
    return `${family}R${release}${suffix}`
  }

  matched = compact.match(/^(GEN\d+)([STUVW])R(\d+)$/)
  if (matched) {
    const [, family, suffix, release] = matched
    return `${family}R${release}${suffix}`
  }

  matched = compact.match(/^(GEN\d+)R(\d+)$/)
  if (matched) {
    const [, family, release] = matched
    return `${family}R${release}`
  }

  matched = compact.match(/^(GEN\d+)([STUVW])$/)
  if (matched) {
    const [, family, suffix] = matched
    return `${family}${suffix}`
  }

  matched = compact.match(/^(GEN\d+)$/)
  if (matched) {
    return matched[1]
  }

  return compact
}

type ParsedPlatformToken = {
  normalized: string
  family: string
  release: number | null
  suffix: string
  bucket: string
}

function parsePlatformToken(text?: string): ParsedPlatformToken | null {
  const normalized = normalizePlatformToken(text)
  if (!normalized) return null
  const matched = normalized.match(/^(GEN\d+)(?:R(\d+))?([STUVW])?$/)
  if (!matched) return null
  const family = matched[1]
  const release = matched[2] ? Number(matched[2]) : null
  const suffix = matched[3] ?? ''
  return {
    normalized,
    family,
    release: Number.isFinite(release) ? release : null,
    suffix,
    bucket: `${family}${suffix}`,
  }
}

function comparePlatformCandidate(left: ParsedPlatformToken, right: ParsedPlatformToken) {
  const leftRelease = left.release ?? 1
  const rightRelease = right.release ?? 1
  if (leftRelease !== rightRelease) return leftRelease - rightRelease
  return left.normalized.localeCompare(right.normalized)
}

function findRepoCandidatesByPlatform(repos: RepoProfile[], platformText?: string) {
  const requested = parsePlatformToken(platformText)
  if (!requested) return { requested: null, exact: [], bucket: [] as Array<RepoProfile & { normalizedPlatform: string }> }

  const bucket = repos
    .map((repo) => {
      const parsed = parsePlatformToken(repo.platform || repo.label)
      if (!parsed || parsed.bucket !== requested.bucket) return null
      return {
        ...repo,
        normalizedPlatform: parsed.normalized,
        parsedPlatform: parsed,
      }
    })
    .filter((item): item is RepoProfile & { normalizedPlatform: string; parsedPlatform: ParsedPlatformToken } => Boolean(item))
    .sort((left, right) => comparePlatformCandidate(left.parsedPlatform, right.parsedPlatform))

  const exact = bucket.filter(item => item.normalizedPlatform === requested.normalized)
  return { requested, exact, bucket }
}

function resolveRepoByPlatform(repos: RepoProfile[], platformText?: string) {
  const candidates = findRepoCandidatesByPlatform(repos, platformText)
  const { requested, exact, bucket } = candidates
  if (!requested) return { ...candidates, matched: null as (RepoProfile & { normalizedPlatform: string }) | null, status: 'no_platform' as const }
  if (exact.length === 1) return { ...candidates, matched: exact[0], status: 'exact' as const }
  if (exact.length > 1) return { ...candidates, matched: null, status: 'ambiguous' as const }
  if (requested.release !== null) return { ...candidates, matched: null, status: 'no_match' as const }
  if (bucket.length === 1) return { ...candidates, matched: bucket[0], status: 'single' as const }

  const defaultCandidates = bucket.filter(item => (item.parsedPlatform.release ?? 1) === 1)
  if (defaultCandidates.length === 1) {
    return { ...candidates, matched: defaultCandidates[0], status: 'default_release' as const }
  }

  const minRelease = bucket.reduce((min, item) => Math.min(min, item.parsedPlatform.release ?? 1), Number.POSITIVE_INFINITY)
  const lowestRelease = bucket.filter(item => (item.parsedPlatform.release ?? 1) === minRelease)
  if (lowestRelease.length === 1) {
    return { ...candidates, matched: lowestRelease[0], status: 'lowest_release' as const }
  }

  return { ...candidates, matched: null, status: bucket.length ? 'ambiguous' as const : 'no_match' as const }
}

export function useModemBaseline() {
  const config = ref<ModemBaselineConfig>(emptyModemBaselineConfig())
  const toolRoot = ref('')
  const workspaceProfile = ref<UserWorkspaceProfile | null>(null)
  const repoProfiles = ref<RepoProfile[]>([])
  const branchTemplates = ref<BranchTemplate[]>([])
  const selectedRepoId = ref(loadSelectedRepoId())
  const selectedTosVersion = ref('')
  const selectedBranchTemplateId = ref('')
  const selectedBranchTarget = ref<'trunk' | 'mp'>('trunk')
  const rules = ref<BranchRule[]>([])
  const noticeText = ref('')
  const noticeParsed = ref<NoticeParseResult | null>(null)
  const recommendation = ref<RecommendationResult | null>(null)
  const scanResults = ref<ScannedRepoCandidate[]>([])
  const scanWarnings = ref<string[]>([])
  const buildProjects = ref<string[]>([])
  const buildProjectsWarning = ref('')
  const loadingBuildProjects = ref(false)
  const precheck = ref<PrecheckResult | null>(null)
  const runs = ref<ModemBaselineRunMeta[]>([])
  const selectedRunId = ref('')
  const logContent = ref('')
  const loading = ref(false)
  const starting = ref(false)
  const prechecking = ref(false)
  const parsingNotice = ref(false)
  const loadingRules = ref(false)
  const loadingBranchTemplates = ref(false)
  const savingRule = ref(false)
  const deletingRule = ref(false)
  const recommending = ref(false)
  const savingWorkspace = ref(false)
  const savingRepo = ref(false)
  const scanningRepos = ref(false)
  const importingBranchTemplates = ref(false)
  const removingRepo = ref(false)
  const updatingRepo = ref(false)
  const refreshingRepoBranches = ref(false)
  const continuing = ref(false)
  const refreshing = ref(false)
  const repoRefreshTimer = ref<number | null>(null)
  const repoHadRunning = ref(false)
  const errorMessage = ref('')
  const eventSource = ref<EventSource | null>(null)
  const pendingNotices = ref<ModemExternalNotice[]>([])
  const loadingNotices = ref(false)
  const applyingNoticeId = ref('')
  const confirmingNoticeId = ref('')
  const dismissingNoticeId = ref('')
  /** Session-local: filled into form but still awaiting「确认完成」. */
  const filledNoticeIds = ref<string[]>([])
  const noticesPollTimer = ref<number | null>(null)

  const selectedRepo = computed(() => repoProfiles.value.find(item => item.repoId === selectedRepoId.value) ?? null)
  const selectedBranchTemplate = computed(
    () => branchTemplates.value.find(item => item.templateId === selectedBranchTemplateId.value) ?? null,
  )
  const selectedRun = computed(() => {
    if (!selectedRunId.value) return null
    return runs.value.find(item => item.runId === selectedRunId.value) ?? null
  })
  const statusMeta = computed(() => getStatusMeta(selectedRun.value?.status, selectedRun.value?.error, selectedRun.value?.phase))
  const stageItems = computed(() => buildStageItems(selectedRun.value?.status, selectedRun.value?.error, selectedRun.value?.phase))
  const conflictFiles = computed(() => selectedRun.value?.conflictFiles ?? [])

  const metrics = computed(() => [
    { label: '当前任务', value: selectedRun.value?.runId ?? '—' },
    { label: '当前状态', value: statusMeta.value.label },
    { label: '冲突文件', value: `${conflictFiles.value.length}` },
    { label: '工作区', value: withString(selectedRun.value?.config.work_dir || config.value.work_dir) },
  ])

  function applyWorkspaceProfileToConfig(profile: UserWorkspaceProfile | null) {
    if (!profile) return
    if (!config.value.mapped_prefix) {
      config.value = { ...config.value, mapped_prefix: profile.mappedPrefix }
    }
    if (!config.value.remote_prefix) {
      config.value = { ...config.value, remote_prefix: profile.remotePrefix }
    }
  }

  function applyRepoToConfig(repo: RepoProfile | null) {
    if (!repo) return
    config.value = {
      ...config.value,
      work_dir: repo.localPath,
      mapped_prefix: repo.mappedPrefix,
      remote_prefix: repo.remotePrefix,
    }
    precheck.value = null
  }

  async function loadBuildProjects(workDir = config.value.work_dir) {
    const dir = String(workDir ?? '').trim()
    if (!dir) {
      buildProjects.value = []
      buildProjectsWarning.value = '请先填写工作区目录'
      if (config.value.build_project) {
        config.value = { ...config.value, build_project: undefined }
      }
      return
    }
    loadingBuildProjects.value = true
    buildProjectsWarning.value = ''
    try {
      const data = await listModemBuildProjects({
        work_dir: dir,
        mapped_prefix: config.value.mapped_prefix,
        remote_prefix: config.value.remote_prefix,
      })
      buildProjects.value = data.items
      buildProjectsWarning.value = data.items.length
        ? (data.source === 'remote' ? `已从远端识别：${data.remoteProjectsDir}` : '')
        : (data.warning || `未找到项目目录：${data.projectsDir} / ${data.remoteProjectsDir}`)
      const selected = config.value.build_project
      if (selected && !data.items.includes(selected)) {
        config.value = { ...config.value, build_project: data.items[0] }
      } else if (!selected && data.items.length) {
        config.value = { ...config.value, build_project: data.items[0] }
      }
    } catch (error) {
      buildProjects.value = []
      buildProjectsWarning.value = String((error as Error)?.message ?? error)
    } finally {
      loadingBuildProjects.value = false
    }
  }

  let buildProjectsTimer: ReturnType<typeof setTimeout> | null = null
  watch(
    () => [config.value.work_dir, config.value.mapped_prefix, config.value.remote_prefix] as const,
    () => {
      if (buildProjectsTimer) clearTimeout(buildProjectsTimer)
      buildProjectsTimer = setTimeout(() => {
        void loadBuildProjects(config.value.work_dir)
      }, 400)
    },
  )

  function normalizeBranchTemplatePlatform(text?: string) {
    return normalizePlatformToken(String(text ?? '').replace(/\s*\([^)]*\)\s*$/, ''))
  }

  function normalizeTosVersion(text?: string) {
    return String(text ?? '').trim().replace(/^tos/i, 'tOS')
  }

  function pickRepoBranchFallback(
    repo: RepoProfile | null,
    input: { targetMode?: 'trunk' | 'mp'; tosVersion?: string },
  ) {
    if (!repo?.branches) return null
    const targetMode = input.targetMode
    if (targetMode === 'mp') {
      const tos = normalizeTosVersion(input.tosVersion || selectedTosVersion.value)
      if (!tos) return null
      const mp = Array.isArray(repo.branches.mp) ? repo.branches.mp : []
      const match = mp.find(item => normalizeTosVersion(item.tos) === tos) ?? null
      if (!match) return null
      const nodeBranch = String(match.mpNodeBranch ?? '').trim()
      const targetBranch = String(match.mpBranch ?? '').trim()
      if (!nodeBranch && !targetBranch) return null
      return { nodeBranch, targetBranch }
    }
    const trunk = repo.branches.trunk
    if (!trunk) return null
    const nodeBranch = String(trunk.nodeBranch ?? '').trim()
    const targetBranch = String(trunk.trunkBranch ?? '').trim()
    if (!nodeBranch && !targetBranch) return null
    return { nodeBranch, targetBranch }
  }

  function matchBranchTemplates(tosVersion?: string, platform?: string) {
    const tos = String(tosVersion ?? '').trim()
    const resolved = resolveRepoByPlatform(repoProfiles.value, platform)
    const platformToken = normalizeBranchTemplatePlatform(resolved.matched?.platform || platform)
    return branchTemplates.value.filter((item) => {
      if (tos && item.tos !== tos) return false
      if (!platformToken) return true
      return normalizeBranchTemplatePlatform(item.platform) === platformToken
    })
  }

  function syncBranchTemplateFromNotice() {
    const tos = noticeParsed.value?.tosVersion
    const platform = noticeParsed.value?.platform
    const targetMode = noticeParsed.value?.targetMode
    if (tos) selectedTosVersion.value = tos
    if (targetMode === 'mp' || targetMode === 'trunk') {
      selectedBranchTarget.value = targetMode
    }
    if (!tos && !platform) return
    const matches = matchBranchTemplates(tos, platform)
    if (matches.length === 1) {
      selectedBranchTemplateId.value = matches[0].templateId
    }
  }

  function closeEventSource() {
    eventSource.value?.close()
    eventSource.value = null
  }

  function stopNoticesPolling() {
    if (noticesPollTimer.value != null) {
      window.clearInterval(noticesPollTimer.value)
      noticesPollTimer.value = null
    }
  }

  function startNoticesPolling() {
    stopNoticesPolling()
    noticesPollTimer.value = window.setInterval(() => {
      void reloadPendingNotices().catch(() => {})
    }, 30_000)
  }

  function disposeModemBaseline() {
    closeEventSource()
    stopNoticesPolling()
  }

  async function reloadPendingNotices() {
    loadingNotices.value = true
    try {
      const result = await listModemBaselineNotices('pending')
      pendingNotices.value = result.items || []
    } finally {
      loadingNotices.value = false
    }
  }

  /** Fill form only — keep notice in pending until operator confirms done. */
  async function applyExternalNotice(noticeId: string) {
    const notice = pendingNotices.value.find(item => item.noticeId === noticeId)
    if (!notice) throw new Error('notice_not_found')
    applyingNoticeId.value = noticeId
    try {
      noticeText.value = notice.text
      await requestRecommend()
      const apply = applyRecommendation()
      if (!filledNoticeIds.value.includes(noticeId)) {
        filledNoticeIds.value = [...filledNoticeIds.value, noticeId]
      }
      return apply
    } finally {
      applyingNoticeId.value = ''
    }
  }

  /** Manual ack: remove from pending inbox. */
  async function confirmExternalNotice(noticeId: string) {
    confirmingNoticeId.value = noticeId
    try {
      await applyModemBaselineNotice(noticeId)
      filledNoticeIds.value = filledNoticeIds.value.filter(id => id !== noticeId)
      await reloadPendingNotices()
    } finally {
      confirmingNoticeId.value = ''
    }
  }

  async function dismissExternalNotice(noticeId: string) {
    dismissingNoticeId.value = noticeId
    try {
      await dismissModemBaselineNotice(noticeId)
      filledNoticeIds.value = filledNoticeIds.value.filter(id => id !== noticeId)
      await reloadPendingNotices()
    } finally {
      dismissingNoticeId.value = ''
    }
  }

  function mergeRun(nextRun: ModemBaselineRunMeta) {
    const index = runs.value.findIndex(item => item.runId === nextRun.runId)
    if (index >= 0) {
      runs.value.splice(index, 1, nextRun)
      return
    }
    runs.value.unshift(nextRun)
  }

  async function reloadRun(runId: string) {
    const nextRun = await getModemBaselineRun(runId)
    mergeRun(nextRun)
  }

  async function reloadRuns() {
    const nextRuns = await listModemBaselineRuns()
    runs.value = nextRuns
    if (selectedRunId.value && !nextRuns.find(item => item.runId === selectedRunId.value)) {
      selectedRunId.value = ''
      logContent.value = ''
      closeEventSource()
    }
  }

  async function loadDefaults() {
    const data = await getModemBaselineDefaults()
    config.value = {
      ...data.config,
      work_dir: selectedRepo.value?.localPath || '',
      mapped_prefix: workspaceProfile.value?.mappedPrefix || String(data.config.mapped_prefix ?? '').trim(),
      remote_prefix: workspaceProfile.value?.remotePrefix || String(data.config.remote_prefix ?? '').trim(),
      build_project: undefined,
    }
    toolRoot.value = data.toolRoot
    applyWorkspaceProfileToConfig(workspaceProfile.value)
    precheck.value = null
    await loadBuildProjects(config.value.work_dir)
  }

  async function loadRules() {
    loadingRules.value = true
    try {
      const data = await listModemPatchRules()
      rules.value = data.items
    } finally {
      loadingRules.value = false
    }
  }

  async function loadBranchTemplateList() {
    loadingBranchTemplates.value = true
    try {
      const data = await listBranchTemplates()
      branchTemplates.value = data.items
      if (selectedBranchTemplateId.value && !data.items.find(item => item.templateId === selectedBranchTemplateId.value)) {
        selectedBranchTemplateId.value = ''
      }
      if (!selectedTosVersion.value && data.items.length) {
        selectedTosVersion.value = data.items[0].tos
      }
      if (!selectedBranchTemplateId.value && data.items.length) {
        selectedBranchTemplateId.value = data.items[0].templateId
      }
      syncBranchTemplateFromNotice()
    } finally {
      loadingBranchTemplates.value = false
    }
  }

  async function loadWorkspace() {
    workspaceProfile.value = await getWorkspaceProfile()
    applyWorkspaceProfileToConfig(workspaceProfile.value)
  }

  async function reloadRepoProfiles() {
    const data = await listRepoProfiles()
    repoProfiles.value = data.items
    if (selectedRepoId.value && !data.items.find(item => item.repoId === selectedRepoId.value)) {
      selectedRepoId.value = ''
      saveSelectedRepoId('')
    }
    if (selectedRepoId.value) {
      applyRepoToConfig(data.items.find(item => item.repoId === selectedRepoId.value) ?? null)
    }

    const hasRunning = data.items.some(item => item.branchTemplateStatus === 'running')
    if (repoHadRunning.value && !hasRunning) {
      repoHadRunning.value = false
      loadBranchTemplateList().catch(() => {})
    } else if (hasRunning) {
      repoHadRunning.value = true
    }
    if (repoRefreshTimer.value !== null) {
      window.clearTimeout(repoRefreshTimer.value)
      repoRefreshTimer.value = null
    }
    if (hasRunning) {
      repoRefreshTimer.value = window.setTimeout(() => {
        repoRefreshTimer.value = null
        reloadRepoProfiles().catch(() => {})
      }, 2000)
    }
  }

  async function loadLog(runId: string) {
    const data = await getModemBaselineLog(runId)
    logContent.value = takeModemLogTail(data.content || '')
  }

  function subscribe(runId: string) {
    closeEventSource()
    const source = subscribeModemBaselineEvents(runId)

    source.addEventListener('status', async (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent).data) as {
          status?: ModemBaselineStatus
          phase?: ModemBaselinePhase
          reportPath?: string
          error?: string
        }
        const current = runs.value.find(item => item.runId === runId)
        if (current) {
          mergeRun({
            ...current,
            status: payload.status ?? current.status,
            phase: payload.phase ?? current.phase,
            reportPath: payload.reportPath ?? current.reportPath,
            error: payload.error ?? current.error,
          })
        }
        if (payload.status && payload.status !== 'running') {
          await reloadRun(runId)
        }
      } catch {}
    })

    source.addEventListener('log', (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent).data) as { line?: string; full?: boolean }
        if (!payload.line) return
        if (payload.full || !logContent.value) {
          logContent.value = takeModemLogTail(payload.line)
        } else {
          logContent.value = appendModemLogTail(logContent.value, payload.line)
        }
      } catch {}
    })

    source.addEventListener('conflicts', (event) => {
      try {
        const payload = JSON.parse((event as MessageEvent).data) as { files?: string[] }
        const current = runs.value.find(item => item.runId === runId)
        if (!current) return
        mergeRun({
          ...current,
          conflictFiles: payload.files ?? [],
          status: (payload.files?.length ?? 0) > 0 ? 'conflict' : current.status,
        })
      } catch {}
    })

    source.onerror = () => {
      if (source.readyState === EventSource.CLOSED) {
        closeEventSource()
      }
    }

    eventSource.value = source
  }

  async function selectRun(runId: string) {
    selectedRunId.value = runId
    await Promise.all([
      reloadRun(runId).catch(() => {}),
      loadLog(runId).catch(() => {
        logContent.value = ''
      }),
    ])
    subscribe(runId)
  }

  async function initialize() {
    loading.value = true
    errorMessage.value = ''
    try {
      await loadWorkspace().catch(() => {
        workspaceProfile.value = null
      })
      await loadDefaults()
      await reloadRepoProfiles().catch(() => {
        repoProfiles.value = []
      })
      await loadBranchTemplateList().catch(() => {
        branchTemplates.value = []
      })
      await loadRules().catch(() => {
        rules.value = []
      })
      await reloadPendingNotices().catch(() => {
        pendingNotices.value = []
      })
      startNoticesPolling()
    } catch (error) {
      errorMessage.value = String((error as Error)?.message ?? error)
    }

    try {
      await reloadRuns()
    } finally {
      loading.value = false
    }
  }

  async function startRun() {
    starting.value = true
    try {
      const cfg = config.value
      const missingFields: string[] = []
      if (!cfg.NODE_BRANCH?.trim()) missingFields.push('NODE_BRANCH')
      if (!cfg.target_BRANCH?.trim()) missingFields.push('target_BRANCH')
      if (!cfg.JIRAID?.trim()) missingFields.push('JIRAID')
      if (!cfg.work_dir?.trim()) missingFields.push('work_dir')
      if (missingFields.length) {
        throw new Error(`缺少必要配置字段：${missingFields.join('、')}`)
      }
      const result = await createModemBaselineRun(config.value)
      await reloadRuns()
      await selectRun(result.runId)
    } finally {
      starting.value = false
    }
  }

  async function continueRun() {
    if (!selectedRun.value) return
    continuing.value = true
    try {
      await continueModemBaselineRun(selectedRun.value.runId, {
        build_project: config.value.build_project,
      })
      await reloadRun(selectedRun.value.runId)
      subscribe(selectedRun.value.runId)
    } finally {
      continuing.value = false
    }
  }

  async function refreshConflicts() {
    if (!selectedRun.value) return
    refreshing.value = true
    try {
      await refreshModemBaselineConflicts(selectedRun.value.runId)
      await reloadRun(selectedRun.value.runId)
    } finally {
      refreshing.value = false
    }
  }

  async function openConflictFile(file: string) {
    if (!selectedRun.value) return
    await openModemBaselineConflictFile(selectedRun.value.runId, file)
  }

  async function parseNotice(text?: string) {
    parsingNotice.value = true
    try {
      const next = await parseModemPatchNotice(text ?? noticeText.value)
      noticeParsed.value = next
      syncBranchTemplateFromNotice()
      return next
    } finally {
      parsingNotice.value = false
    }
  }

  async function requestRecommend() {
    recommending.value = true
    try {
      if (noticeText.value.trim()) {
        await parseNotice(noticeText.value)
      }
      const result = await recommendModemPatch({
        noticeText: noticeText.value.trim() || undefined,
        repoId: selectedRepoId.value || undefined,
        config: config.value,
      })
      recommendation.value = result
      return result
    } finally {
      recommending.value = false
    }
  }

  function applyRecommendation(): RecommendationApplyResult {
    if (!recommendation.value) return { applied: false }

    const currentRepo = selectedRepo.value
    const platform = normalizePlatformToken(noticeParsed.value?.platform || '')
    let repoAction: RecommendationApplyResult['repoAction']
    if (platform) {
      const resolved = resolveRepoByPlatform(repoProfiles.value, platform)
      const candidates = (resolved.exact.length ? resolved.exact : resolved.bucket).map(repo => ({
        repoId: repo.repoId,
        label: repo.label,
        platform: repo.platform,
        localPath: repo.localPath,
      }))

      if (!candidates.length) {
        if (resolved.requested?.release !== null) {
          return { applied: true, repoAction: 'no_match' }
        }
        if (currentRepo) {
          applyRepoToConfig(currentRepo)
          repoAction = 'fallback_selected'
        } else {
          return { applied: true, repoAction: 'no_match' }
        }
      } else if (resolved.matched) {
        chooseRepo(resolved.matched.repoId)
        repoAction = currentRepo && selectedRepo.value?.repoId === currentRepo.repoId
          ? 'synced_selected'
          : 'auto_selected'
      } else {
        return { applied: true, repoAction: 'ambiguous', candidates }
      }
    } else if (currentRepo) {
      applyRepoToConfig(currentRepo)
      repoAction = 'synced_selected'
    } else {
      return { applied: true, repoAction: 'no_platform' }
    }

    const next: ModemBaselineConfig = { ...config.value }
    const repo = selectedRepo.value
    const targetMode = recommendation.value.targetMode ?? noticeParsed.value?.targetMode
    const fallback = pickRepoBranchFallback(repo, {
      targetMode,
      tosVersion: noticeParsed.value?.tosVersion,
    })
    if (fallback?.nodeBranch) next.NODE_BRANCH = fallback.nodeBranch
    else if (recommendation.value.nodeBranch) next.NODE_BRANCH = recommendation.value.nodeBranch
    if (fallback?.targetBranch) next.target_BRANCH = fallback.targetBranch
    else if (recommendation.value.targetBranch) next.target_BRANCH = recommendation.value.targetBranch
    if (recommendation.value.apLabel) next.AP_lable = recommendation.value.apLabel
    config.value = next
    precheck.value = null

    return { applied: true, repoAction }
  }

  async function createRule(input: Partial<BranchRule>) {
    savingRule.value = true
    try {
      const rule = await createModemPatchRule(input)
      await loadRules()
      return rule
    } finally {
      savingRule.value = false
    }
  }

  async function importBranchTemplateFile(filePath: string) {
    importingBranchTemplates.value = true
    try {
      const result = await importBranchTemplates(filePath)
      branchTemplates.value = result.items
      await reloadRepoProfiles()
      if (result.items.length) {
        selectedTosVersion.value = result.items[0].tos
      }
      if (result.items.length) {
        selectedBranchTemplateId.value = result.items[0].templateId
      }
      syncBranchTemplateFromNotice()
      return result
    } finally {
      importingBranchTemplates.value = false
    }
  }

  async function updateRule(ruleId: string, input: Partial<BranchRule>) {
    savingRule.value = true
    try {
      const rule = await updateModemPatchRule(ruleId, input)
      await loadRules()
      return rule
    } finally {
      savingRule.value = false
    }
  }

  async function removeRule(ruleId: string) {
    deletingRule.value = true
    try {
      await deleteModemPatchRule(ruleId)
      await loadRules()
    } finally {
      deletingRule.value = false
    }
  }

  async function saveWorkspace(input: { mappedPrefix: string; remotePrefix: string; roots: string[] }) {
    savingWorkspace.value = true
    try {
      workspaceProfile.value = await saveWorkspaceProfile(input)
      applyWorkspaceProfileToConfig(workspaceProfile.value)
      precheck.value = null
      return workspaceProfile.value
    } finally {
      savingWorkspace.value = false
    }
  }

  async function saveRepo(input: {
    label: string
    localPath: string
    projectName?: string
    platform?: string
    vendor?: string
  }) {
    savingRepo.value = true
    try {
      const repo = await createRepoProfile(input)
      await reloadRepoProfiles()
      selectedRepoId.value = repo.repoId
      saveSelectedRepoId(repo.repoId)
      applyRepoToConfig(repo)
      return repo
    } finally {
      savingRepo.value = false
    }
  }

  async function removeRepo(repoId: string) {
    removingRepo.value = true
    try {
      await deleteRepoProfile(repoId)
      if (selectedRepoId.value === repoId) selectedRepoId.value = ''
      if (selectedRepoId.value === '') saveSelectedRepoId('')
      await reloadRepoProfiles()
      precheck.value = null
    } finally {
      removingRepo.value = false
    }
  }

  async function updateRepo(repoId: string, input: {
    label: string
    localPath: string
    platform: string
    branches?: RepoProfile['branches']
  }) {
    updatingRepo.value = true
    try {
      const repo = await updateRepoProfile(repoId, input)
      await reloadRepoProfiles()
      if (selectedRepoId.value === repoId) {
        applyRepoToConfig(repo)
      }
      return repo
    } finally {
      updatingRepo.value = false
    }
  }

  async function refreshRepoBranchTemplates(repoId?: string) {
    const targets = repoId
      ? [repoId]
      : repoProfiles.value.map(item => item.repoId)
    refreshingRepoBranches.value = true
    try {
      for (const id of targets) {
        await refreshRepoBranches(id)
      }
      await reloadRepoProfiles()
    } finally {
      refreshingRepoBranches.value = false
    }
  }

  async function scanRepos(roots: string[]) {
    scanningRepos.value = true
    try {
      const result = await scanRepoProfiles(roots)
      scanResults.value = result.items
      scanWarnings.value = result.warnings
      return result
    } finally {
      scanningRepos.value = false
    }
  }

  function chooseRepo(repoId: string) {
    selectedRepoId.value = repoId
    saveSelectedRepoId(repoId)
    applyRepoToConfig(repoProfiles.value.find(item => item.repoId === repoId) ?? null)
  }

  function chooseBranchTemplate(templateId: string) {
    selectedBranchTemplateId.value = templateId
    const template = branchTemplates.value.find(item => item.templateId === templateId)
    if (template) {
      selectedTosVersion.value = template.tos
    }
  }

  function chooseTosVersion(tos: string) {
    selectedTosVersion.value = tos
    const firstMatch = branchTemplates.value.find(item => item.tos === tos)
    if (firstMatch) {
      selectedBranchTemplateId.value = firstMatch.templateId
    }
  }

  function applyBranchTemplate(templateId = selectedBranchTemplateId.value, target = selectedBranchTarget.value) {
    const template = branchTemplates.value.find(item => item.templateId === templateId)
    if (!template) {
      return { applied: false }
    }
    config.value = {
      ...config.value,
      NODE_BRANCH: target === 'mp' ? template.mpNodeBranch : template.nodeBranch,
      target_BRANCH: target === 'mp' ? template.mpBranch : template.trunkBranch,
    }
    selectedBranchTemplateId.value = template.templateId
    selectedBranchTarget.value = target
    precheck.value = null
    return { applied: true, template }
  }

  function clearSelectedRepo() {
    selectedRepoId.value = ''
    saveSelectedRepoId('')
    precheck.value = null
  }

  async function runPrecheck() {
    prechecking.value = true
    try {
      precheck.value = await precheckModemBaseline(config.value, selectedRepoId.value || undefined)
      return precheck.value
    } finally {
      prechecking.value = false
    }
  }

  return {
    config,
    toolRoot,
    workspaceProfile,
    repoProfiles,
    branchTemplates,
    selectedRepoId,
    selectedRepo,
    selectedTosVersion,
    selectedBranchTemplateId,
    selectedBranchTemplate,
    selectedBranchTarget,
    rules,
    noticeText,
    noticeParsed,
    recommendation,
    scanResults,
    scanWarnings,
    buildProjects,
    buildProjectsWarning,
    loadingBuildProjects,
    precheck,
    runs,
    selectedRun,
    selectedRunId,
    conflictFiles,
    logContent,
    loading,
    starting,
    prechecking,
    parsingNotice,
    loadingRules,
    loadingBranchTemplates,
    savingRule,
    deletingRule,
    recommending,
    savingWorkspace,
    savingRepo,
    scanningRepos,
    importingBranchTemplates,
    removingRepo,
    updatingRepo,
    refreshingRepoBranches,
    continuing,
    refreshing,
    errorMessage,
    pendingNotices,
    loadingNotices,
    applyingNoticeId,
    confirmingNoticeId,
    dismissingNoticeId,
    filledNoticeIds,
    statusMeta,
    stageItems,
    metrics,
    initialize,
    loadDefaults,
    loadRules,
    loadBranchTemplateList,
    parseNotice,
    requestRecommend,
    applyRecommendation,
    reloadPendingNotices,
    applyExternalNotice,
    confirmExternalNotice,
    dismissExternalNotice,
    importBranchTemplateFile,
    createRule,
    updateRule,
    removeRule,
    saveWorkspace,
    saveRepo,
    removeRepo,
    updateRepo,
    refreshRepoBranchTemplates,
    scanRepos,
    chooseRepo,
    chooseTosVersion,
    chooseBranchTemplate,
    applyBranchTemplate,
    clearSelectedRepo,
    loadBuildProjects,
    runPrecheck,
    reloadRuns,
    selectRun,
    startRun,
    continueRun,
    refreshConflicts,
    openConflictFile,
    closeEventSource,
    disposeModemBaseline,
  }
}
