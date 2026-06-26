import type { AdaptDomainDef } from './types'

/** 运营商配置工作区内置域 */
export const CARRIER_ADAPT_DOMAINS: AdaptDomainDef[] = [
  {
    id: 'carrierconfig-tools',
    label: 'CarrierConfig配置',
    icon: 'CC',
    color: '#0969da',
    status: 'active',
    module: 'telephony',
    relatedSkills: ['carrierconfig-tools', 'jira-ops'],
    interactionMode: true,
    fields: [
      {
        name: 'description',
        label: '描述',
        type: 'textarea',
        required: true,
        placeholder: 'Jira 单号/链接、运营商、mccmnc、变更 key、期望值、项目/平台信息等',
      },
    ],
  },
  {
    id: 'apn-config',
    label: 'APN配置',
    icon: 'APN',
    color: '#2da44e',
    status: 'active',
    module: 'telephony',
    relatedSkills: ['apn-edit'],
    fields: [
      {
        name: 'repo_path',
        label: '代码仓库路径',
        type: 'text',
        required: true,
        placeholder: '如 D:\\project\\main\\vendor\\mediatek\\proprietary\\modem\\apn',
      },
      {
        name: 'extra_info',
        label: '补充信息',
        type: 'textarea',
        required: false,
        placeholder: 'MCC/MNC、分支信息、目标 APN 名称、安卓版本/平台（MTK/高通）等',
      },
    ],
  },
]
