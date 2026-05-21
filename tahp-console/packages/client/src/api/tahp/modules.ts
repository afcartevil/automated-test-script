import { tahpGet } from './client'

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

export function listModules(): Promise<ModuleInfo[]> {
  return tahpGet<ModuleInfo[]>('/api/tahp/modules')
}

export function getModule(name: string): Promise<ModuleInfo> {
  return tahpGet<ModuleInfo>(`/api/tahp/modules/${encodeURIComponent(name)}`)
}
