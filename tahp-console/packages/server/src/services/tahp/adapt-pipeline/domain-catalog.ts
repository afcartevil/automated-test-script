/**
 * 可适配模块目录：三工作区内置域 + layout 字段覆盖
 * 与 client constants/adapt-domains 对齐（id / label / module）
 */
import { getAdaptDomainLayout } from '../adapt-layout/service'
import { normalizeSpnRelatedSkills } from '../ecc-config-form'
import {
  ADAPT_WORKSPACE_IDS,
  type AdaptWorkspaceId,
} from '../adapt-layout/types'

export interface CatalogFieldSchema {
  key: string
  label: string
  required?: boolean
  type?: string
  placeholder?: string
  options?: Array<{ label: string; value: string }>
  defaultValue?: string
}

export interface CatalogDomain {
  workspace_id: AdaptWorkspaceId
  domain_id: string
  domain_label: string
  module: string
  related_skills: string[]
  schema: CatalogFieldSchema[]
}

export interface CatalogWorkspace {
  id: AdaptWorkspaceId
  label: string
  subtitle: string
  domains: CatalogDomain[]
}

export interface DomainCatalog {
  workspaces: CatalogWorkspace[]
}

interface BuiltinDomainSeed {
  id: string
  label: string
  module: string
  related_skills?: string[]
  schema?: CatalogFieldSchema[]
}

const WORKSPACE_META: Array<{
  id: AdaptWorkspaceId
  label: string
  subtitle: string
}> = [
  {
    id: 'adapt-debug',
    label: '功能适配',
    subtitle: '将源版本的功能改动适配到目标版本',
  },
  {
    id: 'feature-adapt',
    label: '特性适配',
    subtitle: '覆盖 TP、LCM、音频、充电、Sensor、内存、调度等特性适配模块',
  },
  {
    id: 'carrier-config',
    label: '运营商配置',
    subtitle: '运营商相关配置适配，包含 CarrierConfig、ECC、APN 与 SPN',
  },
]

/** 内置域种子（与 AdaptDebug 三工作区 builtin 对齐；schema 可被 layout 覆盖） */
const BUILTIN_BY_WORKSPACE: Record<AdaptWorkspaceId, BuiltinDomainSeed[]> = {
  'adapt-debug': [
    { id: 'tp', label: 'TP触摸屏', module: 'kernel-driver', related_skills: ['tp-adapt-bringup'] },
    { id: 'vib', label: '振动马达', module: 'kernel-driver', related_skills: ['vib-adapt-lra-driver', 'vib-adapt-rotor-driver'] },
    { id: 'lcm', label: 'LCM', module: 'kernel-driver', related_skills: ['display_analyser'] },
    { id: 'fp', label: '指纹', module: 'kernel-driver', related_skills: ['drv-fp-adapt'] },
    { id: 'audio', label: '音频', module: 'kernel-driver' },
    { id: 'charging', label: '充电', module: 'kernel-driver' },
    { id: 'sensor', label: 'Sensor', module: 'kernel-driver' },
    { id: 'security', label: '安全', module: 'kernel-driver' },
    { id: 'mini-system', label: '小系统', module: 'kernel-driver' },
    { id: 'modem', label: 'Modem', module: 'telephony' },
    { id: 'comm-framework', label: '通信框架', module: 'telephony' },
  ],
  'feature-adapt': [
    { id: 'tp', label: 'TP触摸屏', module: 'kernel-driver' },
    { id: 'lcm', label: 'LCM', module: 'kernel-driver' },
    { id: 'audio', label: '音频', module: 'kernel-driver' },
    { id: 'charging', label: '充电', module: 'kernel-driver' },
    { id: 'sensor', label: 'Sensor', module: 'kernel-driver' },
    { id: 'memory', label: '内存', module: 'kernel-driver' },
    { id: 'scheduling', label: '调度', module: 'kernel-driver' },
    {
      id: 'comm-framework',
      label: '通信框架',
      module: 'telephony',
      related_skills: ['comm-framework-agent-test-for-secondWork'],
    },
  ],
  'carrier-config': [
    {
      id: 'carrierconfig-tools',
      label: 'CarrierConfig配置',
      module: 'telephony',
      related_skills: ['carrierconfig-tools', 'jira-ops'],
      schema: [
        { key: 'description', label: '描述', required: true, type: 'textarea' },
      ],
    },
    {
      id: 'ecc-config',
      label: 'ECC配置',
      module: 'telephony',
      related_skills: ['ecc-config', 'gerrit-submit'],
    },
    {
      id: 'apn-config',
      label: 'APN配置',
      module: 'telephony',
      related_skills: ['apn-config'],
    },
    {
      id: 'spn-config',
      label: 'SPN配置',
      module: 'telephony',
      related_skills: ['spn-workflow-2-2-0'],
      schema: [
        { key: 'jira_key', label: 'Jira 单号/链接', required: true, type: 'text', placeholder: '如 OS162-12345 或 Jira URL' },
        { key: 'log_path', label: '日志路径', required: true, type: 'text', placeholder: '用户提供的日志文件、目录或压缩包绝对路径' },
        { key: 'workspace_path', label: '源码 workspace', required: false, type: 'text', placeholder: '与 Jira 问题版本对应的源码根；缺省可分析但不可改码/提交' },
        {
          key: 'task_goal',
          label: '任务目标',
          required: false,
          type: 'select',
          placeholder: '默认仅分析',
          options: [
            { label: '仅分析（不改码）', value: 'analyze' },
            { label: '分析并改码（提交前确认 diff）', value: 'patch' },
            { label: '分析、改码并提交 Gerrit', value: 'submit' },
          ],
        },
        { key: 'extra_info', label: '补充信息', required: false, type: 'textarea', placeholder: '运营商、MCCMNC、平台（MTK/QCOM）、现象（状态栏/手动搜网/displayName/MVNO/云网SPN）等' },
      ],
    },
  ],
}

export function mapDomainToModule(domainId: string, moduleHint?: string): string {
  if (moduleHint?.trim()) return moduleHint.trim()
  if (
    domainId === 'modem'
    || domainId === 'comm-framework'
    || domainId === 'carrierconfig-tools'
    || domainId === 'ecc-config'
    || domainId === 'apn-config'
    || domainId === 'spn-config'
  ) {
    return 'telephony'
  }
  return 'kernel-driver'
}

export function domainCatalogKey(workspaceId: string, domainId: string): string {
  return `${workspaceId}::${domainId}`
}

export function listBuiltinSeeds(workspaceId?: AdaptWorkspaceId): BuiltinDomainSeed[] {
  if (workspaceId) return BUILTIN_BY_WORKSPACE[workspaceId] ?? []
  return ADAPT_WORKSPACE_IDS.flatMap(id => BUILTIN_BY_WORKSPACE[id] ?? [])
}

export async function getDomainCatalog(): Promise<DomainCatalog> {
  const workspaces: CatalogWorkspace[] = []

  for (const meta of WORKSPACE_META) {
    const seeds = BUILTIN_BY_WORKSPACE[meta.id] ?? []
    const domains: CatalogDomain[] = []

    for (const seed of seeds) {
      const layout = await getAdaptDomainLayout(seed.id, meta.id)
      const layoutSchema = (layout?.fields ?? []).map(f => ({
        key: f.name,
        label: f.label,
        required: f.required,
        type: f.type,
        placeholder: f.placeholder,
        options: f.options?.map(o => ({ label: o.label, value: o.value })),
        defaultValue: f.defaultValue,
      }))
      const schema = layoutSchema.length
        ? layoutSchema
        : (seed.schema ?? [])
      const related_skills = seed.id === 'spn-config'
        ? normalizeSpnRelatedSkills(
          layout?.related_skills?.length
            ? [...layout.related_skills]
            : (seed.related_skills ?? []),
        )
        : (layout?.related_skills?.length
          ? [...layout.related_skills]
          : (seed.related_skills ?? []))

      domains.push({
        workspace_id: meta.id,
        domain_id: seed.id,
        domain_label: seed.label,
        module: mapDomainToModule(seed.id, seed.module),
        related_skills,
        schema,
      })
    }

    workspaces.push({
      id: meta.id,
      label: meta.label,
      subtitle: meta.subtitle,
      domains,
    })
  }

  return { workspaces }
}
