export type TahpModule = 'telephony' | 'kernel-driver' | 'power-mgmt' | 'shared'

export interface ModuleDomain {
  domain: string
  file: string
}

export interface ModuleInfo {
  name: string
  displayName?: string
  owner?: string
  hasModuleYaml: boolean
  domains: ModuleDomain[]
}

const RAW = [
  { name: 'telephony', displayName: '通信', domains: ['bug_analysis', 'code_adaptation', 'version_adaptation', 'carrier_porting'] },
  { name: 'kernel-driver', displayName: '内核驱动', domains: ['bug_analysis', 'code_adaptation'] },
  { name: 'power-mgmt', displayName: '功耗管理', domains: ['bug_analysis'] },
  { name: 'shared', displayName: '共享', domains: ['code_adaptation'] },
] as const

export const TAHP_MODULES: ModuleInfo[] = RAW.map(m => ({
  name: m.name,
  displayName: m.displayName,
  hasModuleYaml: false,
  domains: m.domains.map(domain => ({ domain, file: '' })),
}))
