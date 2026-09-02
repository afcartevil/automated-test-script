import { getAdaptDomainLayout } from '../../adapt-layout/service'
import type { AdaptLayoutFieldDef } from '../../adapt-layout/types'
import { centralClient } from '../../sync/central-client'
import { isCentralConfigured } from '../../runtime-mode'
import {
  domainCatalogKey,
  mapDomainToModule,
} from '../domain-catalog'
import { registerStageForTest } from '../registry'
import type { PipelineDomain, StageContext, StageDefinition } from '../types'
import { discoverRemoteRunner } from '../harness-bridge-exec'
import { fillMappedWorkspaceIfMissing } from '../mapped-workspace'

const DOMAIN_LABELS: Record<string, string> = {
  tp: 'TP触摸屏',
  vib: '振动马达',
  lcm: 'LCM',
  fp: '指纹',
  charging: '充电',
  sensor: 'Sensor',
  memory: '内存',
  scheduling: '调度',
  modem: 'Modem',
  'comm-framework': '通信框架',
  audio: '音频',
  security: '安全',
  'mini-system': '小系统',
  'carrierconfig-tools': 'CarrierConfig配置',
  'ecc-config': 'ECC配置',
  'apn-config': 'APN配置',
  'spn-config': 'SPN配置',
}

function labelForDomain(domainId: string): string {
  return DOMAIN_LABELS[domainId] ?? domainId
}

type CentralDomain = Awaited<ReturnType<typeof centralClient.resolveAdaptPrereqs>>['domains'][number]

function mergeFormData(
  central: Record<string, unknown> | undefined,
  preset: Record<string, unknown> | undefined,
): Record<string, unknown> {
  const merged: Record<string, unknown> = { ...(central ?? {}) }
  for (const [key, raw] of Object.entries(preset ?? {})) {
    const value = raw === undefined || raw === null ? '' : String(raw)
    if (value.trim()) {
      merged[key] = raw
    } else if (!(key in merged)) {
      merged[key] = raw
    }
  }
  return merged
}

function computeIncomplete(
  formData: Record<string, unknown>,
  fields: AdaptLayoutFieldDef[],
  fallback: string[],
): string[] {
  if (!fields.length) return [...fallback]
  const missing: string[] = []
  for (const field of fields) {
    if (!field.required) continue
    const val = String(formData[field.name] ?? '').trim()
    if (!val) missing.push(field.name)
  }
  return missing
}

function schemaToLayoutFields(schema: unknown): AdaptLayoutFieldDef[] {
  if (!Array.isArray(schema)) return []
  const fields: AdaptLayoutFieldDef[] = []
  for (const raw of schema) {
    if (!raw || typeof raw !== 'object') continue
    const rec = raw as Record<string, unknown>
    const name = String(rec.key || rec.name || '').trim()
    if (!name) continue
    fields.push({
      name,
      label: String(rec.label || name),
      type: 'text',
      required: rec.required === true,
    })
  }
  return fields
}

function pickFormDataForFields(
  raw: Record<string, unknown> | undefined,
  schema: unknown,
): Record<string, unknown> {
  if (!raw) return {}
  const schemaNames = schemaToLayoutFields(schema).map(field => field.name)
  if (!schemaNames.length) return { ...raw }
  const allowed = new Set(schemaNames)
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(raw)) {
    if (allowed.has(key)) out[key] = value
  }
  return out
}

/**
 * 用户勾选域优先；中心预填 form_data / incomplete，并覆盖 related_skills（有则用之）。
 * 无 preset 时回落为中心域列表（兼容旧调用）。
 */
async function normalizeDomains(
  centralDomains: CentralDomain[],
  run: import('../types').PipelineRun,
): Promise<PipelineDomain[]> {
  const preset = run.domains
  const centralByKey = new Map(
    centralDomains.map(d => [domainCatalogKey(d.workspace_id, d.domain_id), d]),
  )

  if (!preset.length) {
    const result: PipelineDomain[] = []
    for (const d of centralDomains) {
      const layout = await getAdaptDomainLayout(d.domain_id, d.workspace_id)
      const snapshotFields = schemaToLayoutFields(d.schema)
      const layout_fields = snapshotFields.length ? snapshotFields : (layout?.fields ?? [])
      const form_data = pickFormDataForFields(d.form_data as Record<string, unknown>, d.schema)
      result.push({
        workspace_id: d.workspace_id,
        domain_id: d.domain_id,
        domain_label: labelForDomain(d.domain_id),
        module: mapDomainToModule(d.domain_id),
        related_skills: d.related_skills?.length
          ? [...d.related_skills]
          : layout?.related_skills?.length
            ? [...layout.related_skills]
            : [],
        form_data,
        incomplete_required: snapshotFields.length
          ? computeIncomplete(form_data, snapshotFields, d.incomplete_required)
          : [...d.incomplete_required],
        enabled: true,
        status: 'pending',
        layout_fields,
      })
    }
    return result
  }

  const result: PipelineDomain[] = []
  for (const p of preset) {
    const key = domainCatalogKey(p.workspace_id, p.domain_id)
    const central = centralByKey.get(key)
    const layout = await getAdaptDomainLayout(p.domain_id, p.workspace_id)
    const snapshotFields = schemaToLayoutFields(central?.schema)
    const layout_fields = snapshotFields.length ? snapshotFields : (layout?.fields ?? [])
    const merged = mergeFormData(central?.form_data, p.form_data)
    const form_data = pickFormDataForFields(merged, central?.schema)
    const incomplete_required = computeIncomplete(
      form_data,
      layout_fields,
      central?.incomplete_required ?? p.incomplete_required ?? [],
    )

    result.push({
      workspace_id: p.workspace_id,
      domain_id: p.domain_id,
      domain_label: p.domain_label || labelForDomain(p.domain_id),
      module: mapDomainToModule(p.domain_id, p.module),
      related_skills: central?.related_skills?.length
        ? [...central.related_skills]
        : layout?.related_skills?.length
          ? [...layout.related_skills]
          : (p.related_skills ?? []),
      form_data,
      incomplete_required,
      enabled: p.enabled,
      status: 'pending',
      layout_fields,
    })
  }
  return result
}

export const prereqStageDefinition: StageDefinition = {
  key: 'prereq',
  label: '前置信息',
  produces: ['prereq'],
  async probe() {
    if (!isCentralConfigured()) {
      return {
        available: false,
        reason: '未配置中心连接（TAHP_CENTRAL_URL / TAHP_CENTRAL_TOKEN），请先在设置中配置',
      }
    }
    return { available: true }
  },
  async start(ctx: StageContext) {
    const run = ctx.run
    const data = await centralClient.resolveAdaptPrereqs({
      project_code: run.project_code,
      campaign_id: run.campaign_id,
    })
    const domains = await normalizeDomains(data.domains, run)

    ctx.patchRun({
      domains,
      from_os: data.from_os,
      to_os: data.to_os,
    })
    try {
      const prev = ctx.run.build_context
      if (!prev?.mapped_root?.trim() || !prev.linux_root?.trim()) {
        const disc = prev?.mapped_root?.trim() ? null : discoverRemoteRunner()
        const next = fillMappedWorkspaceIfMissing(prev, disc)
        if (next.mapped_root !== (prev?.mapped_root ?? '') || next.linux_root !== prev?.linux_root) {
          ctx.patchRun({ build_context: next })
        }
      }
    } catch {
      /* mapped_root 为编译/Gerrit 加速项，前置失败不阻断 */
    }
    ctx.patchState({
      progress: {},
      summary: { domain_count: domains.length, campaign_id: data.campaign_id },
    })
  },
  evaluate(ctx: StageContext) {
    const incomplete = ctx.run.domains.filter(d => d.enabled && d.incomplete_required.length > 0)
    if (incomplete.length > 0) {
      const lines = incomplete.flatMap(d =>
        d.incomplete_required.map(f => `${d.domain_id}.${f}`),
      )
      return {
        status: 'waiting_human' as const,
        reason: 'incomplete_required',
        message: `仍有必填项未填写：${lines.join('、')}`,
        actions: [{ id: 'confirm_done', label: '已补填，继续' }],
      }
    }

    return {
      status: 'done' as const,
      summary: {
        domain_count: ctx.run.domains.filter(d => d.enabled).length,
        from_os: ctx.run.from_os,
        to_os: ctx.run.to_os,
      },
    }
  },
}

export function installPrereqStage(): void {
  registerStageForTest(prereqStageDefinition)
}

installPrereqStage()
