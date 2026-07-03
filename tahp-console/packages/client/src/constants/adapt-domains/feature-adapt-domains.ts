import type { AdaptDomainDef } from './types'

/** 特性适配工作区 — 内置域默认表单（与 AI适配调试 独立维护） */
export const FEATURE_ADAPT_DOMAINS: AdaptDomainDef[] = [
  {
    id: 'tp',
    label: 'TP触摸屏',
    icon: 'TP',
    color: '#388bfd',
    status: 'pending',
    relatedSkills: [
      'tp-adapt-smart-sampling',
      'tp-adapt-super-resolution',
      'fc-tp-esports',
      'fc-tp-super-resolution',
      'fc-tp-touch-master',
      'fc-vib-4d',
      'fc-vib-lra-features',
    ],
    fields: [
      {
        name: 'task_input',
        label: '任务输入',
        type: 'text',
        required: true,
        placeholder: '项目路径、平台信息及要适配/验证的 TP 特性（电竞采样率、超分、区域操作大师等）',
      },
    ],
  },
  {
    id: 'lcm',
    label: 'LCM',
    icon: 'LCM',
    color: '#58a6ff',
    status: 'pending',
    relatedSkills: ['display_analyser'],
    fields: [
      {
        name: 'task_input',
        label: '任务输入',
        type: 'text',
        required: true,
        placeholder: '项目路径与 LCM 适配任务描述（Skill 待定，暂用 display_analyser）',
      },
    ],
  },
  {
    id: 'audio',
    label: '音频',
    icon: 'AUD',
    color: '#e3b341',
    status: 'pending',
    relatedSkills: ['audio-feature-adaptation', 'audio-feature-selfcheck'],
    fields: [
      {
        name: 'task_input',
        label: '任务输入',
        type: 'text',
        required: true,
        placeholder: '升级前后 vendor 路径、升级场景及要适配/自检的音频特性',
      },
    ],
  },
  {
    id: 'charging',
    label: '充电',
    icon: 'CHG',
    color: '#f78166',
    status: 'pending',
    relatedSkills: ['pillar3-customization-input'],
    fields: [
      {
        name: 'task_input',
        label: '任务输入',
        type: 'text',
        required: true,
        placeholder: '项目路径与老/新分支信息及充电特性适配需求（Skill 待定）',
      },
    ],
  },
  {
    id: 'sensor',
    label: 'Sensor',
    icon: 'SNS',
    color: '#a371f7',
    status: 'pending',
    relatedSkills: ['sensor-feature-adaption'],
    fields: [
      {
        name: 'task_input',
        label: '任务输入',
        type: 'text',
        required: true,
        placeholder: '旧/新项目根目录路径及要迁移的 Sensor 特性说明',
      },
    ],
  },
  {
    id: 'video',
    label: 'Video',
    icon: 'VID',
    color: '#8b5cf6',
    status: 'pending',
    relatedSkills: ['VIDEO_feature_spddebug'],
    fields: [
      {
        name: 'task_input',
        label: '任务输入',
        type: 'text',
        required: true,
        placeholder: '目标仓库路径、分支及要移植的 Gerrit 提交链接或 Wiki 条目',
      },
    ],
  },
]
