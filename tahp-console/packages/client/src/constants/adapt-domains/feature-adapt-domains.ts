import type { AdaptDomainDef, AdaptFieldDef } from './types'
import { ADAPT_DEBUG_DOMAINS } from './adapt-debug-domains'
import {
  FEATURE_CHECKLIST_AUDIO,
  FEATURE_CHECKLIST_CHARGING,
  FEATURE_CHECKLIST_LCM,
  FEATURE_CHECKLIST_MEMORY,
  FEATURE_CHECKLIST_SCHEDULING,
  FEATURE_CHECKLIST_SENSOR,
  FEATURE_CHECKLIST_TP,
} from './feature-checklist-defaults'

function checklistField(label = '特性清单', defaultValue = ''): AdaptFieldDef {
  return {
    name: 'feature_checklist',
    label,
    type: 'checklist',
    required: false,
    defaultValue,
    placeholder: '每行一条：特性名称<Tab>特性编码（SF-…）',
  }
}

const lcmBaseFields = ADAPT_DEBUG_DOMAINS.find(d => d.id === 'lcm')?.fields ?? []

/** 特性适配工作区 — 内置域默认表单（与 AI适配调试 独立维护） */
export const FEATURE_ADAPT_DOMAINS: AdaptDomainDef[] = [
  {
    id: 'tp',
    label: 'TP触摸屏',
    icon: 'TP',
    color: '#388bfd',
    status: 'active',
    relatedSkills: [
      'tp-adapt-smart-sampling',
      'tp-adapt-super-resolution',
      'fc-tp-esports',
      'fc-tp-super-resolution',
      'fc-tp-touch-master',
      'fc-vib-4d',
      'fc-vib-lra-features',
      'tones-scmp',
    ],
    fields: [
      {
        name: 'repo_path',
        label: '代码仓库路径',
        type: 'text',
        required: true,
        placeholder: '项目代码仓库绝对路径',
      },
      checklistField('特性清单', FEATURE_CHECKLIST_TP),
      {
        name: 'user_notes',
        label: '补充说明',
        type: 'text',
        required: false,
        placeholder: '可选：适配范围、参考项目、风险项等',
      },
    ],
  },
  {
    id: 'lcm',
    label: 'LCM',
    icon: 'LCM',
    color: '#58a6ff',
    status: 'pending',
    relatedSkills: ['display_analyser', 'tones-scmp'],
    fields: [
      ...lcmBaseFields.map(f => ({ ...f })),
      checklistField('特性清单', FEATURE_CHECKLIST_LCM),
    ],
  },
  {
    id: 'audio',
    label: '音频',
    icon: 'AUD',
    color: '#e3b341',
    status: 'pending',
    relatedSkills: ['audio-feature-adaptation', 'audio-feature-selfcheck', 'tones-scmp'],
    fields: [
      {
        name: 'vnd_path_old',
        label: '升级前的vnd侧绝对路径',
        type: 'text',
        required: true,
        placeholder: '升级前 vendor 目录绝对路径',
      },
      {
        name: 'vnd_path_new',
        label: '升级后的vnd侧绝对路径',
        type: 'text',
        required: true,
        placeholder: '升级后 vendor 目录绝对路径',
      },
      {
        name: 'build_option',
        label: '编译选项',
        type: 'text',
        required: true,
        placeholder: '从 SPUG 查找，如 x6885_h8923_m1',
      },
      checklistField('特性清单', FEATURE_CHECKLIST_AUDIO),
      {
        name: 'adsp_support',
        label: '是否支持ADSP',
        type: 'select',
        required: true,
        placeholder: '请选择',
        options: [
          { label: '是', value: 'yes' },
          { label: '否', value: 'no' },
        ],
      },
      {
        name: 'user_notes',
        label: '补充说明',
        type: 'text',
        required: false,
        placeholder: '可选：升级场景、声学配置说明等',
      },
    ],
  },
  {
    id: 'charging',
    label: '充电',
    icon: 'CHG',
    color: '#f78166',
    status: 'pending',
    relatedSkills: [
      'mtk-adapt-pillar3-router',
      'mtk-adapt-template-feature-factory-mode',
      'mtk-adapt-template-feature-kpoc-charging',
      'mtk-adapt-template-feature-placeholder',
      'transsion-sunmao40-customization-features-adapt',
      'tones-scmp',
    ],
    fields: [
      {
        name: 'repo_path',
        label: '代码仓库路径',
        type: 'text',
        required: true,
        placeholder: '项目代码仓库绝对路径',
      },
      checklistField('特性清单', FEATURE_CHECKLIST_CHARGING),
      {
        name: 'user_notes',
        label: '补充说明',
        type: 'text',
        required: false,
        placeholder: '可选：老升新/绿场、Pillar 范围、特性编码筛选说明等',
      },
    ],
  },
  {
    id: 'sensor',
    label: 'Sensor',
    icon: 'SNS',
    color: '#a371f7',
    status: 'pending',
    relatedSkills: ['sensor-feature-adaption', 'tones-scmp'],
    fields: [
      {
        name: 'repo_path',
        label: '代码仓库路径',
        type: 'text',
        required: true,
        placeholder: '旧/新项目根目录或代码仓库绝对路径',
      },
      checklistField('特性清单', FEATURE_CHECKLIST_SENSOR),
      {
        name: 'user_notes',
        label: '补充说明',
        type: 'text',
        required: false,
        placeholder: '可选：要迁移的 Sensor 特性范围说明',
      },
    ],
  },
  {
    id: 'memory',
    label: '内存',
    icon: 'MEM',
    color: '#3fb950',
    status: 'pending',
    relatedSkills: ['spd-memory-feature-check', 'spd-shared', 'tones-scmp'],
    fields: [
      {
        name: 'repo_path',
        label: '代码仓库路径',
        type: 'text',
        required: true,
        placeholder: '项目代码仓库绝对路径',
      },
      checklistField('特性清单', FEATURE_CHECKLIST_MEMORY),
      {
        name: 'user_notes',
        label: '补充说明',
        type: 'text',
        required: false,
        placeholder: '可选：机型/内核版本、巡检范围、风险项等',
      },
    ],
  },
  {
    id: 'scheduling',
    label: '调度',
    icon: 'SCH',
    color: '#ffa657',
    status: 'pending',
    relatedSkills: ['spd-cpu-feature-check', 'spd-shared', 'tones-scmp'],
    fields: [
      {
        name: 'repo_path',
        label: '代码仓库路径',
        type: 'text',
        required: true,
        placeholder: '项目代码仓库绝对路径',
      },
      checklistField('特性清单', FEATURE_CHECKLIST_SCHEDULING),
      {
        name: 'user_notes',
        label: '补充说明',
        type: 'text',
        required: false,
        placeholder: '可选：机型/TOS 版本、巡检范围、风险项等',
      },
    ],
  },
]
