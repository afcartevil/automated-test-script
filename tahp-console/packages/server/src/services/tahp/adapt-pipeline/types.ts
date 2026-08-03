/**
 * adapt-pipeline 类型定义（唯一真相源）
 * 契约见 .cursor/skills/adapt-pipeline/reference.md §1、§2、§4、§5、§6、§10、§11
 */

export type RunStatus =
  | 'draft' | 'running' | 'waiting_human' | 'paused'
  | 'passed' | 'failed' | 'aborted'

export type StageStatus =
  | 'pending' | 'running' | 'waiting_human' | 'done' | 'failed' | 'skipped'

export interface PipelineRun {
  run_id: string
  workflow_id: string
  workflow_version: number

  project_code: string
  campaign_id?: string
  from_os?: string
  to_os?: string

  status: RunStatus
  current_node: string | null
  iteration: number
  max_iterations: number
  created_at: string
  updated_at: string
  finished_at?: string
  abort_reason?: string

  domains: PipelineDomain[]
  build_context: BuildContext
  device_id?: string
  test_plan?: TestPlan

  stages: Record<string, StageState>
  iterations: IterationRecord[]
  artifacts: Partial<Record<ArtifactKind, ArtifactState>>
  gerrit_changes?: GerritChangeRef[]
  /** 人工审核勾选的待入库仓库（绝对路径或仓名） */
  gerrit_selected_repos?: string[]
}

export interface PipelineDomain {
  workspace_id: string
  domain_id: string
  domain_label: string
  module: string
  related_skills: string[]
  form_data: Record<string, unknown>
  incomplete_required: string[]
  enabled: boolean
  status: 'pending' | 'running' | 'done' | 'failed' | 'skipped'
  adapt_task_id?: string
  changed_files?: string[]
  error?: string
}

export interface BuildContext {
  mapped_root: string
  workspace: string
  components: string[]
  variant: string
  parallel_profile?: 'mtk' | 'qcom'
  markets?: string[]
  /** whole_device=整机 rdtool；native_module=模块编译 */
  build_kind?: 'whole_device' | 'native_module'
  /** 默认 harness-build-whole-device / harness-build-native */
  build_skill_id?: string
  /** pipeline stages，如 build,package 或 repo,build,package */
  pipeline_stages?: string
  /** native：lunch target */
  lunch?: string
  /** native：make/mmm 目标模块名 */
  native_target?: string
  /** native：分区组件，如 sys */
  native_component?: string
  /** 刷机 skill，默认 harness-device */
  flash_skill_id?: string
  /** full_rom | single_img */
  flash_mode?: 'full_rom' | 'single_img'
  /** 单镜像目标分区（可选，可从文件名推断） */
  flash_partition?: string
  /** 提交分支（可选，传给 gerrit） */
  target_branch?: string
  /**
   * Gerrit commit 模板中的 ID 字段（AR/BUG，如 TOS1501-63219）。
   * 多仓共用同一 ID；DESCRIPTION 仍按各仓实际 diff 填写。
   */
  gerrit_issue_id?: string
}

export interface TestPlan {
  mode: 'recommend' | 'fixed'
  test_type?: string
  selected_cases?: string[]
  must_test_items?: string[]
}

export interface StageState {
  key: string
  status: StageStatus
  started_at?: string
  finished_at?: string
  attempt: number
  refs: StageRefs
  progress?: Record<string, unknown>
  summary?: Record<string, unknown>
  human?: { reason: string; message: string; actions: HumanAction[] }
  error?: string
  availability?: StageAvailability
}

export interface StageRefs {
  adapt_task_ids?: string[]
  build_run_id?: string
  flash_log_path?: string
  selfcheck_report_id?: string
  selfcheck_device_id?: string
  bug_task_ids?: string[]
  gerrit_task_id?: string
  [k: string]: unknown
}

export interface HumanAction {
  id: string
  label: string
  fields?: Array<{ name: string; label: string; required?: boolean; placeholder?: string }>
  danger?: boolean
}

export interface IterationRecord {
  index: number
  started_at: string
  finished_at?: string
  verdict: 'passed' | 'failed' | 'running' | 'aborted'
  failed_case_count?: number
  triage_task_id?: string
  resumed_from?: string
  note?: string
}

export type ArtifactKind =
  | 'prereq'
  | 'source'
  | 'build'
  | 'flashed'
  | 'testresult'
  | 'triage'

export interface ArtifactState {
  kind: ArtifactKind
  produced_by: string
  produced_at: string
  fingerprint?: string
  stale: boolean
  stale_reason?: string
}

export interface GerritChangeRef {
  domain_id: string
  repo: string
  change_url?: string
  change_number?: string
  status: 'pending' | 'submitted' | 'failed' | 'blocked_conflict'
  files: string[]
  error?: string
}

export interface StageAvailability {
  available: boolean
  reason?: string
  version?: string
  detail?: Record<string, unknown>
}

export type StageVerdict =
  | { status: 'running'; progress?: Record<string, unknown> }
  | { status: 'done'; summary?: Record<string, unknown> }
  | { status: 'failed'; error: string; retryable?: boolean; produced?: ArtifactKind[] }
  | { status: 'waiting_human'; reason: string; message: string; actions: HumanAction[] }
  | { status: 'skipped'; reason: string }

export interface StageContext {
  run: Readonly<PipelineRun>
  node: Readonly<WorkflowNode>
  state: Readonly<StageState>
  patchState(patch: Partial<StageState>): void
  patchRun(patch: Partial<PipelineRun>): void
  log(line: string): void
}

export interface StageDefinition {
  key: string
  label: string
  consumes?: ArtifactKind[]
  produces?: ArtifactKind[]
  isHumanGate?: boolean
  probe?(ctx: { run: Readonly<PipelineRun> }): Promise<StageAvailability>
  start(ctx: StageContext): Promise<void>
  observe?(ctx: StageContext, ev: ObservedEvent): void | Promise<void>
  evaluate(ctx: StageContext): StageVerdict
  handleHumanAction?(ctx: StageContext, actionId: string, payload?: Record<string, unknown>): Promise<void>
  cancel?(ctx: StageContext): Promise<void>
}

export interface CapabilityStatus {
  state: 'pending' | 'running' | 'success' | 'failed' | 'cancelled'
  progress?: number
  phase?: string
  message?: string
  result?: Record<string, unknown>
  error?: string
}

export interface CapabilityEvent {
  type: 'log' | 'phase' | 'progress' | 'done'
  line?: string
  phase?: string
  progress?: number
  status?: CapabilityStatus
}

export interface ExternalCapability<TInput = unknown> {
  readonly id: string
  probe(): Promise<StageAvailability>
  start(input: TInput): Promise<{ runId: string }>
  getStatus(runId: string): Promise<CapabilityStatus>
  cancel(runId: string): Promise<void>
  subscribe?(runId: string, onEvent: (ev: CapabilityEvent) => void): () => void
}

export interface BuildCapabilityInput {
  pipelineRunId: string
  mappedRoot: string
  workspace: string
  mode: 'full' | 'incremental'
  components: string[]
  variant: string
  parallelProfile?: 'mtk' | 'qcom'
  markets?: string[]
  buildKind?: 'whole_device' | 'native_module'
  buildSkillId?: string
  pipelineStages?: string
  lunch?: string
  nativeTarget?: string
  nativeComponent?: string
}

export interface BuildCapabilityResult {
  artifactsDir?: string
  pkgPath?: string
  artifacts?: Array<{ name: string; path: string; sizeBytes?: number }>
  durationMs?: number
  failedStage?: string
  skillId?: string
}

export type NodeTarget = string | 'END' | 'ABORT'

export interface WorkflowNode {
  key: string
  enabled: boolean
  onUnavailable?: 'manual_gate' | 'skip' | 'fail'
  onDone?: NodeTarget
  onFail?: NodeTarget
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

export interface ObservedEvent {
  source: 'task-stream' | 'self-check' | 'capability'
  type: string
  correlation: { taskId?: string; deviceId?: string; runId?: string }
  payload: Record<string, unknown>
  ts: number
}

export interface PipelineEventSource {
  id: string
  subscribe(onEvent: (ev: ObservedEvent) => void): () => void
}

export interface CreateRunInput {
  project_code: string
  campaign_id?: string
  domain_ids?: string[]
  domains?: PipelineDomain[]
  build_context: BuildContext
  device_id?: string
  test_plan?: TestPlan
  max_iterations?: number
  workflow_id?: string
  from_os?: string
  to_os?: string
}

export interface RunSummary {
  run_id: string
  project_code: string
  status: RunStatus
  iteration: number
  current_node: string | null
  created_at: string
  updated_at: string
}

export interface ResourceConflict {
  kind: 'workspace' | 'device' | 'domain'
  holderRunId: string
  detail: string
}

export interface ResumePoint {
  node: string
  label: string
  safety: 'safe' | 'unsafe'
  missing?: Array<{ kind: ArtifactKind; reason: string }>
  hint?: string
}

export interface ResumeRequest {
  node: string
  scope?: 'continue' | 'restart'
  force?: boolean
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
  nodes: Array<{
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
      repos?: unknown
      queue?: string[]
      current_index?: number
      current_domain_id?: string
      repo_groups?: unknown
      changed_files?: unknown
      domains?: Array<{
        domain_id: string
        domain_label: string
        status: string
        changed_files?: string[]
        related_skills?: string[]
        error?: string
        adapt_task_id?: string
      }>
    }
    error?: string
    summary_line?: string
    unavailable_reason?: string
    human?: { reason: string; message: string; actions: HumanAction[] }
    is_loop_target?: boolean
  }>
  iterations: IterationRecord[]
  pending_human_count: number
}
