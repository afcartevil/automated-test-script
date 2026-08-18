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

const PATH_FIELD_RE = /path|file|dir|dts|firmware|root|project|固件|路径|目录/i

function isPathLikeField(name: string, label?: string): boolean {
  return PATH_FIELD_RE.test(name) || (label ? PATH_FIELD_RE.test(label) : false)
}

function looksLikeFilesystemPath(value: string): boolean {
  const v = value.trim()
  if (!v) return false
  if (/^[A-Za-z]:[\\/]/.test(v)) return true
  if (v.startsWith('/') || v.startsWith('\\\\')) return true
  return false
}

type CentralDomain = Awaited<ReturnType<typeof centralClient.resolveAdaptPrereqs>>['domains'][number]

export interface InvalidPathEntry {
  domain_id: string
  workspace_id?: string
  field: string
  value: string
}

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

/**
 * 用户勾选域优先；中心仅预填 form_data / incomplete。
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
      result.push({
        workspace_id: d.workspace_id,
        domain_id: d.domain_id,
        domain_label: labelForDomain(d.domain_id),
        module: mapDomainToModule(d.domain_id),
        related_skills: layout?.related_skills?.length
          ? [...layout.related_skills]
          : [],
        form_data: { ...d.form_data },
        incomplete_required: [...d.incomplete_required],
        enabled: true,
        status: 'pending',
      })
    }
    return result
  }

  const result: PipelineDomain[] = []
  for (const p of preset) {
    const key = domainCatalogKey(p.workspace_id, p.domain_id)
    const central = centralByKey.get(key)
    const layout = await getAdaptDomainLayout(p.domain_id, p.workspace_id)
    const form_data = mergeFormData(central?.form_data, p.form_data)
    const incomplete_required = computeIncomplete(
      form_data,
      layout?.fields ?? [],
      central?.incomplete_required ?? p.incomplete_required ?? [],
    )

    result.push({
      workspace_id: p.workspace_id,
      domain_id: p.domain_id,
      domain_label: p.domain_label || labelForDomain(p.domain_id),
      module: mapDomainToModule(p.domain_id, p.module),
      related_skills: layout?.related_skills?.length
        ? [...layout.related_skills]
        : (p.related_skills ?? []),
      form_data,
      incomplete_required,
      enabled: p.enabled,
      status: 'pending',
    })
  }
  return result
}

export function collectInvalidPaths(
  domains: PipelineDomain[],
  mappedRoot: string,
  fieldDefs: Map<string, AdaptLayoutFieldDef[]>,
): InvalidPathEntry[] {
  const invalid: InvalidPathEntry[] = []
  const root = mappedRoot.trim().replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()
  if (!root) return invalid

  for (const domain of domains) {
    if (!domain.enabled) continue
    const fields = fieldDefs.get(domainCatalogKey(domain.workspace_id, domain.domain_id))
      ?? fieldDefs.get(domain.domain_id)
      ?? []
    const pathNames = new Set(
      fields.filter(f => isPathLikeField(f.name, f.label)).map(f => f.name),
    )

    for (const [field, raw] of Object.entries(domain.form_data)) {
      if (raw === undefined || raw === null) continue
      const value = String(raw).trim()
      if (!value) continue
      if (!pathNames.has(field) && !looksLikeFilesystemPath(value)) continue

      const normalized = value.replace(/\\/g, '/').toLowerCase()
      if (normalized === root || normalized.startsWith(`${root}/`)) continue

      invalid.push({
        domain_id: domain.domain_id,
        workspace_id: domain.workspace_id,
        field,
        value,
      })
    }
  }
  return invalid
}

async function loadFieldDefs(domains: PipelineDomain[]): Promise<Map<string, AdaptLayoutFieldDef[]>> {
  const map = new Map<string, AdaptLayoutFieldDef[]>()
  for (const d of domains) {
    const layout = await getAdaptDomainLayout(d.domain_id, d.workspace_id)
    map.set(domainCatalogKey(d.workspace_id, d.domain_id), layout?.fields ?? [])
    // 兼容旧测试 / 调用方仅按 domain_id 查
    if (!map.has(d.domain_id)) {
      map.set(d.domain_id, layout?.fields ?? [])
    }
  }
  return map
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
    const fieldDefs = await loadFieldDefs(domains)
    const invalid_paths = collectInvalidPaths(domains, run.build_context.mapped_root, fieldDefs)

    ctx.patchRun({
      domains,
      from_os: data.from_os,
      to_os: data.to_os,
    })
    ctx.patchState({
      progress: { invalid_paths },
      summary: { domain_count: domains.length, campaign_id: data.campaign_id },
    })
  },
  evaluate(ctx: StageContext) {
    const invalid = ctx.state.progress?.invalid_paths as InvalidPathEntry[] | undefined
    if (invalid?.length) {
      const lines = invalid.map(e => `${e.domain_id}.${e.field}: ${e.value}`)
      return {
        status: 'waiting_human' as const,
        reason: 'invalid_paths',
        message: `以下路径不在映射盘 ${ctx.run.build_context.mapped_root} 下：\n${lines.join('\n')}`,
        actions: [{ id: 'confirm_done', label: '已修正，继续' }],
      }
    }

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
