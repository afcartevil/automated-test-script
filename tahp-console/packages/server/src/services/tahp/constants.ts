/** TAHP 业务模块静态定义（替代原 constraints/ 目录扫描） */
export interface TahpModuleInfo {
  name: string
  display_name: string
  domains: string[]
}

export const TAHP_MODULES: TahpModuleInfo[] = [
  {
    name: 'telephony',
    display_name: '通信',
    domains: ['bug_analysis', 'code_adaptation', 'version_adaptation', 'carrier_porting'],
  },
  {
    name: 'kernel-driver',
    display_name: '内核驱动',
    domains: ['bug_analysis', 'code_adaptation'],
  },
  {
    name: 'power-mgmt',
    display_name: '功耗管理',
    domains: ['bug_analysis'],
  },
  {
    name: 'shared',
    display_name: '共享',
    domains: ['code_adaptation'],
  },
]
