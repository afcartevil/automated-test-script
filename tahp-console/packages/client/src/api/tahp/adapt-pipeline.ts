import { tahpDelete, tahpGet, tahpPost, tahpPut } from './client'

export type RunStatus =
  | 'draft' | 'running' | 'waiting_human' | 'paused'
  | 'passed' | 'failed' | 'aborted'

export type StageStatus =
  | 'pending' | 'running' | 'waiting_human' | 'done' | 'failed' | 'skipped'

export interface RunSummary {
  run_id: string
  project_code: string
  status: RunStatus
  iteration: number
  current_node: string | null
  created_at: string
  updated_at: string
}

export interface HumanActionField {
  name: string
  label: string
  required?: boolean
  placeholder?: string
}

export interface HumanAction {
  id: string
  label: string
  fields?: HumanActionField[]
  danger?: boolean
}

export interface AdaptDomainProgress {
  domain_id: string
  domain_label: string
  status: string
  changed_files?: string[]
  related_skills?: string[]
  error?: string
  adapt_task_id?: string
}

export interface TimelineNode {
  key: string
  label: string
  status: StageStatus
  enabled: boolean
  duration_ms?: number
  progress?: {
    percent?: number
    text?: string
    changes?: unknown
    state?: string
    phase?: string
    message?: string
    error?: string
    result?: unknown
    pkg_path?: string
    pkgPath?: string
    artifacts_dir?: string
    flash_mode?: string
    flash_skill_id?: string
    repos?: Array<{
      repo: string
      repo_label: string
      files: string[]
      domain_ids: string[]
    }>
    queue?: string[]
    current_index?: number
    current_domain_id?: string
    domains?: AdaptDomainProgress[]
  }
  error?: string
  summary_line?: string
  unavailable_reason?: string
  human?: { reason: string; message: string; actions: HumanAction[] }
  is_loop_target?: boolean
}

export interface IterationRecord {
  index: number
  started_at: string
  finished_at?: string
  verdict: 'running' | 'passed' | 'failed' | 'aborted'
  resumed_from?: string
  note?: string
}

export interface TimelineView {
  run_id: string
  project_code: string
  status: RunStatus
  iteration: number
  max_iterations: number
  current_node: string | null
  started_at: string
  duration_ms: number
  build_context?: BuildContext
  device_id?: string
  from_os?: string
  to_os?: string
  nodes: TimelineNode[]
  iterations: IterationRecord[]
  pending_human_count: number
}

export interface ResumePoint {
  node: string
  label: string
  safety: 'safe' | 'unsafe'
  missing?: Array<{ kind: string; reason: string }>
  hint?: string
}

export interface ResumePointsResponse {
  points: ResumePoint[]
  recommended: string | null
}

export interface HumanActionRequest {
  node: string
  action_id: string
  payload?: Record<string, unknown>
}

export interface ResumeRequest {
  node: string
  scope?: 'continue' | 'restart'
  force?: boolean
}

export interface BuildContext {
  mapped_root: string
  workspace: string
  /** @deprecated harness 组件列表；ez-build 用 build_targets */
  components?: string[]
  variant: string
  project?: string
  build_flag?: string
  system_path?: string
  vendor_path?: string
  build_targets?: string[]
  need_pack?: boolean
  parallel_profile?: 'mtk' | 'qcom'
  markets?: string[]
  build_kind?: 'whole_device' | 'native_module'
  build_skill_id?: string
  pipeline_stages?: string
  lunch?: string
  native_target?: string
  native_component?: string
  flash_skill_id?: string
  flash_mode?: 'full_rom' | 'single_img'
  target_branch?: string
  /** Gerrit commit 模板 ID（AR/BUG），多仓共用 */
  gerrit_issue_id?: string
}

export interface TestPlan {
  /** smoke=仅冒烟用例；recommend=按适配域推荐；fixed=手工/预选固定用例 */
  mode: 'smoke' | 'recommend' | 'fixed'
  test_type?: string
  selected_cases?: string[]
  must_test_items?: string[]
}

export interface PipelineDomainInput {
  workspace_id: string
  domain_id: string
  domain_label: string
  module: string
  related_skills: string[]
  form_data: Record<string, unknown>
  incomplete_required: string[]
  enabled: boolean
  status?: 'pending' | 'running' | 'done' | 'failed' | 'skipped'
}

export interface CreateRunInput {
  project_code: string
  campaign_id?: string
  domain_ids?: string[]
  domains?: PipelineDomainInput[]
  build_context: BuildContext
  device_id?: string
  test_plan?: TestPlan
  max_iterations?: number
  workflow_id?: string
  from_os?: string
  to_os?: string
}

export interface CreateRunResponse {
  run_id: string
  domains: PipelineDomainInput[]
  workflow: WorkflowDefinition
}

export interface PrereqResolveData {
  project_code: string
  campaign_id: string
  from_os: string
  to_os: string
  domains: Array<{
    workspace_id: string
    domain_id: string
    revision: number
    schema: Array<{ key: string; label: string; type?: string; required?: boolean }>
    form_data: Record<string, unknown>
    stale_fields: string[]
    incomplete_required: string[]
  }>
}

export function fetchPipelineRuns(params?: {
  status?: string
  limit?: number
  offset?: number
}): Promise<{ items: RunSummary[]; total: number }> {
  const q = new URLSearchParams()
  if (params?.status) q.set('status', params.status)
  if (params?.limit != null) q.set('limit', String(params.limit))
  if (params?.offset != null) q.set('offset', String(params.offset))
  const qs = q.toString()
  return tahpGet(`/api/tahp/adapt-pipeline/runs${qs ? `?${qs}` : ''}`)
}

export function fetchPipelineTimeline(runId: string): Promise<TimelineView> {
  return tahpGet(`/api/tahp/adapt-pipeline/runs/${encodeURIComponent(runId)}/timeline`)
}

export function fetchPipelineLogs(runId: string, nodeKey: string, tail = 500): Promise<{ lines: string[] }> {
  return tahpGet(
    `/api/tahp/adapt-pipeline/runs/${encodeURIComponent(runId)}/logs/${encodeURIComponent(nodeKey)}?tail=${tail}`,
  )
}

export function fetchResumePoints(runId: string): Promise<ResumePointsResponse> {
  return tahpGet(`/api/tahp/adapt-pipeline/runs/${encodeURIComponent(runId)}/resume-points`)
}

export function submitPipelineHumanAction(runId: string, input: HumanActionRequest): Promise<{ ok: boolean }> {
  return tahpPost(`/api/tahp/adapt-pipeline/runs/${encodeURIComponent(runId)}/human-action`, input)
}

export function resumePipelineRun(runId: string, input: ResumeRequest): Promise<{ ok: boolean; iteration: number }> {
  return tahpPost(`/api/tahp/adapt-pipeline/runs/${encodeURIComponent(runId)}/resume`, input)
}

export function createPipelineRun(input: CreateRunInput): Promise<CreateRunResponse> {
  return tahpPost('/api/tahp/adapt-pipeline/runs', input)
}

export function startPipelineRun(runId: string): Promise<{ ok: boolean }> {
  return tahpPost(`/api/tahp/adapt-pipeline/runs/${encodeURIComponent(runId)}/start`)
}

export function pausePipelineRun(runId: string): Promise<{ ok: boolean }> {
  return tahpPost(`/api/tahp/adapt-pipeline/runs/${encodeURIComponent(runId)}/pause`)
}

export function abortPipelineRun(runId: string, reason?: string): Promise<{ ok: boolean }> {
  return tahpPost(`/api/tahp/adapt-pipeline/runs/${encodeURIComponent(runId)}/abort`, reason ? { reason } : undefined)
}

export function discardPipelineDraftRun(runId: string): Promise<{ ok: boolean }> {
  return tahpDelete(`/api/tahp/adapt-pipeline/runs/${encodeURIComponent(runId)}`)
}

export function fetchPipelinePrereqs(projectCode: string, campaignId?: string): Promise<PrereqResolveData> {
  const qs = campaignId ? `?campaign_id=${encodeURIComponent(campaignId)}` : ''
  return tahpGet(`/api/tahp/adapt-pipeline/prereqs/${encodeURIComponent(projectCode)}${qs}`)
}

export interface DomainCatalogField {
  key: string
  label: string
  required?: boolean
  type?: string
  placeholder?: string
  options?: Array<{ label: string; value: string }>
  defaultValue?: string
}

export interface DomainCatalogDomain {
  workspace_id: string
  domain_id: string
  domain_label: string
  module: string
  related_skills: string[]
  schema: DomainCatalogField[]
}

export interface DomainCatalogWorkspace {
  id: string
  label: string
  subtitle: string
  domains: DomainCatalogDomain[]
}

export interface DomainCatalog {
  workspaces: DomainCatalogWorkspace[]
}

export function fetchDomainCatalog(): Promise<DomainCatalog> {
  return tahpGet('/api/tahp/adapt-pipeline/domain-catalog')
}

export interface HarnessSkillMeta {
  id: string
  kind: 'build' | 'flash'
  label: string
  description: string
  path: string
  root: string
}

export function fetchHarnessSkills(kind?: 'build' | 'flash'): Promise<{
  roots: string[]
  items: HarnessSkillMeta[]
}> {
  const qs = kind ? `?kind=${encodeURIComponent(kind)}` : ''
  return tahpGet(`/api/tahp/adapt-pipeline/harness-skills${qs}`)
}

export interface WorkspaceBuildOptions {
  mapped_root: string
  workspace: string
  components: string[]
  markets: string[]
  recommended_components: string[]
  recommended_markets: string[]
  market_presets?: string[]
  platform?: string
  project_name?: string
  source: 'harness_status' | 'pack_json' | 'fallback'
  warning?: string
}

export function fetchWorkspaceBuildOptions(
  mappedRoot: string,
  workspace: string,
): Promise<WorkspaceBuildOptions> {
  const qs = new URLSearchParams({
    mapped_root: mappedRoot,
    workspace,
  })
  return tahpGet(`/api/tahp/adapt-pipeline/workspace-build-options?${qs}`)
}

export function runStatusLabel(status: RunStatus): string {
  switch (status) {
    case 'draft': return '草稿'
    case 'running': return '运行中'
    case 'waiting_human': return '待人工处理'
    case 'paused': return '已暂停'
    case 'passed': return '已完成'
    case 'failed': return '失败'
    case 'aborted': return '已终止'
    default: return status
  }
}

export function formatDurationMs(ms: number): string {
  if (ms < 60_000) return `${Math.max(1, Math.round(ms / 1000))}秒`
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}分${Math.floor((ms % 60_000) / 1000)}秒`
  const h = Math.floor(ms / 3_600_000)
  const m = Math.floor((ms % 3_600_000) / 60_000)
  return `${h}小时${m}分`
}

export type OnUnavailablePolicy = 'manual_gate' | 'skip' | 'fail'

export interface WorkflowNode {
  key: string
  enabled: boolean
  onUnavailable?: OnUnavailablePolicy
  onDone?: string
  onFail?: string
  onDoneEffect?: 'increment_iteration'
  params?: Record<string, unknown>
  maxAttempts?: number
}

export interface WorkflowDefinition {
  id: string
  version: number
  label: string
  maxIterations: number
  nodes: WorkflowNode[]
}

export interface StageAvailability {
  available: boolean
  reason?: string
  version?: string
  detail?: Record<string, unknown>
}

export interface WorkflowNodeView {
  key: string
  label: string
  availability: StageAvailability
}

export interface CapabilityItem {
  key: string
  label: string
  availability: StageAvailability
}

export interface WorkflowResponse {
  workflow: WorkflowDefinition
  nodes: WorkflowNodeView[]
}

export const DEFAULT_WORKFLOW: WorkflowDefinition = {
  id: 'adapt-default',
  version: 1,
  label: '标准适配流水线',
  maxIterations: 3,
  nodes: [
    { key: 'prereq', enabled: true, onUnavailable: 'fail' },
    { key: 'adapt', enabled: true, onUnavailable: 'fail' },
    { key: 'build', enabled: true, onUnavailable: 'manual_gate', onFail: 'human_review' },
    { key: 'flash', enabled: true, onUnavailable: 'manual_gate', onFail: 'human_review' },
    { key: 'selfcheck', enabled: true, onUnavailable: 'manual_gate', onDone: 'gerrit', onFail: 'triage' },
    { key: 'triage', enabled: true, onUnavailable: 'skip', onDone: 'human_review', onFail: 'human_review' },
    { key: 'human_review', enabled: true, onUnavailable: 'fail', onDone: 'build', onDoneEffect: 'increment_iteration' },
    { key: 'gerrit', enabled: true, onUnavailable: 'manual_gate', onDone: 'END', onFail: 'human_review' },
  ],
}

export function fetchWorkflow(): Promise<WorkflowResponse> {
  return tahpGet('/api/tahp/adapt-pipeline/workflow')
}

export function saveWorkflow(workflow: WorkflowDefinition): Promise<{ workflow: WorkflowDefinition }> {
  return tahpPut('/api/tahp/adapt-pipeline/workflow', workflow)
}

export function fetchCapabilities(): Promise<CapabilityItem[]> {
  return tahpGet('/api/tahp/adapt-pipeline/capabilities')
}
