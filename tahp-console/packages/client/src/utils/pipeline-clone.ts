import type {
  BuildContext,
  PathParams,
  PipelineDomainInput,
  PipelineRunRecord,
  TestPlan,
  TestPlanMode,
} from '@/api/tahp/adapt-pipeline'
import {
  DEFAULT_ADAPT_WORKSPACE,
  isAdaptWorkspaceId,
  type AdaptWorkspaceId,
} from '@/constants/adapt-domains'

export const TEST_PLAN_MODES: TestPlanMode[] = ['smoke', 'pipeline_adapt', 'recommend', 'fixed']

export interface WizardCloneSeed {
  source_run_id: string
  project_code: string
  campaign_id?: string
  from_os?: string
  to_os?: string
  old_vendor_root: string
  new_vendor_root: string
  new_system_root: string
  path_params?: PathParams
  workspaces: AdaptWorkspaceId[]
  domains: PipelineDomainInput[]
  build_context: BuildContext
  device_id?: string
  test_plan?: TestPlan
  max_iterations: number
}

export function isCloneableRunId(runId: string): boolean {
  return Boolean(runId) && !runId.startsWith('__')
}

export function domainCloneKey(workspaceId: string, domainId: string): string {
  return `${workspaceId}::${domainId}`
}

export function stringifyFormData(form: Record<string, unknown> | undefined): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [key, value] of Object.entries(form ?? {})) {
    out[key] = value == null ? '' : String(value)
  }
  return out
}

export function workspacesFromCloneDomains(
  domains: Array<{ workspace_id: string; enabled?: boolean }>,
): AdaptWorkspaceId[] {
  const picked: AdaptWorkspaceId[] = []
  const append = (id: string) => {
    if (!isAdaptWorkspaceId(id) || picked.includes(id)) return
    picked.push(id)
  }
  for (const domain of domains) {
    if (domain.enabled) append(domain.workspace_id)
  }
  if (!picked.length) {
    for (const domain of domains) append(domain.workspace_id)
  }
  return picked.length ? picked : [DEFAULT_ADAPT_WORKSPACE]
}

export function resolveClonedTestPlanMode(mode: string | undefined): TestPlanMode {
  return TEST_PLAN_MODES.includes(mode as TestPlanMode) ? mode as TestPlanMode : 'smoke'
}

export function clonePathParams(pathParams: PathParams | undefined): PathParams | undefined {
  if (!pathParams) return undefined
  return {
    inputs: { ...pathParams.inputs },
    fields: pathParams.fields.map(field => ({ ...field })),
    parsed_at: pathParams.parsed_at,
  }
}

export function buildWizardCloneSeed(run: PipelineRunRecord): WizardCloneSeed {
  const pathParams = clonePathParams(run.path_params)
  const buildContext: BuildContext = {
    ...(run.build_context ?? {
      mapped_root: '',
      workspace: '',
      variant: 'userdebug',
    }),
  }
  if (buildContext.build_targets) {
    buildContext.build_targets = [...buildContext.build_targets]
  }
  const domains = (run.domains ?? []).map(domain => ({
    ...domain,
    related_skills: [...(domain.related_skills ?? [])],
    incomplete_required: [...(domain.incomplete_required ?? [])],
    form_data: { ...(domain.form_data ?? {}) },
  }))
  return {
    source_run_id: run.run_id,
    project_code: run.project_code,
    campaign_id: run.campaign_id,
    from_os: run.from_os,
    to_os: run.to_os,
    old_vendor_root: pathParams?.inputs.OLD_VENDOR_ROOT ?? '',
    new_vendor_root: pathParams?.inputs.NEW_VENDOR_ROOT ?? String(buildContext.vendor_path ?? ''),
    new_system_root: pathParams?.inputs.NEW_SYSTEM_ROOT ?? String(buildContext.system_path ?? ''),
    path_params: pathParams,
    workspaces: workspacesFromCloneDomains(domains),
    domains,
    build_context: buildContext,
    device_id: run.device_id,
    test_plan: run.test_plan ? { ...run.test_plan } : undefined,
    max_iterations: run.max_iterations > 0 ? run.max_iterations : 3,
  }
}

export interface CloneOverlayDomain {
  workspace_id: string
  domain_id: string
  domain_label: string
  module: string
  related_skills: string[]
  enabled: boolean
  form_data: Record<string, string>
  incomplete_required: string[]
}

export function overlayCloneDomains<T extends CloneOverlayDomain>(
  catalog: T[],
  cloned: PipelineDomainInput[],
  makeExtra: (src: PipelineDomainInput, formData: Record<string, string>) => T,
): T[] {
  const byKey = new Map(catalog.map(domain => [domainCloneKey(domain.workspace_id, domain.domain_id), domain]))
  const clonedKeys = new Set<string>()

  for (const src of cloned) {
    const key = domainCloneKey(src.workspace_id, src.domain_id)
    clonedKeys.add(key)
    const formData = stringifyFormData(src.form_data)
    const existing = byKey.get(key)
    if (existing) {
      existing.enabled = src.enabled
      existing.form_data = { ...existing.form_data, ...formData }
      existing.incomplete_required = [...(src.incomplete_required ?? [])]
    } else {
      const extra = makeExtra(src, formData)
      catalog.push(extra)
      byKey.set(key, extra)
    }
  }

  for (const domain of catalog) {
    if (!clonedKeys.has(domainCloneKey(domain.workspace_id, domain.domain_id))) {
      domain.enabled = false
    }
  }
  return catalog
}
