import { existsSync, readdirSync } from 'fs'
import { join } from 'path'
import { spawnSync } from 'child_process'
import * as hermesCli from '../hermes/hermes-cli'
import { getAgentBridgeManager } from '../hermes/agent-bridge'
import { tahpPaths, hasTahpProject } from './paths'

export type CheckState = 'ok' | 'warn' | 'err'

export interface SelfCheckItem {
  name: string
  detail: string
  state: CheckState
  label: string
}

export interface SelfCheckCategory {
  title: string
  icon: string
  items: SelfCheckItem[]
}

export interface SelfCheckResult {
  score: number
  level: string
  updated: string
  pass: number
  warn: number
  fail: number
  total: number
  categories: SelfCheckCategory[]
  history: Array<{ time: string; score: number; note: string }>
}

const historyStore: Array<{ time: string; score: number; note: string }> = []

function item(name: string, detail: string, state: CheckState): SelfCheckItem {
  const label = state === 'ok' ? '正常' : state === 'warn' ? '告警' : '失败'
  return { name, detail, state, label }
}

function countSkills(): number {
  const root = tahpPaths.skillsDir
  if (!existsSync(root)) return 0
  try {
    return readdirSync(root, { withFileTypes: true }).filter(d => d.isDirectory()).length
  } catch {
    return 0
  }
}

function countKnowledgeEntries(): number {
  const entriesDir = join(tahpPaths.knowledgeDir, '.kb-data', 'entries')
  if (!existsSync(entriesDir)) return 0
  try {
    return readdirSync(entriesDir).filter(f => f.endsWith('.json')).length
  } catch {
    return 0
  }
}

function checkPython(): SelfCheckItem {
  const py = tahpPaths.python
  const r = spawnSync(py, ['--version'], { encoding: 'utf-8', timeout: 5000 })
  if (r.status === 0) {
    const ver = (r.stdout || r.stderr || '').trim()
    return item('Python 3', `${ver} · ${py}`, 'ok')
  }
  return item('Python 3', `未找到 ${py}`, 'err')
}

function checkNode(): SelfCheckItem {
  const major = parseInt(process.versions.node.split('.')[0], 10)
  if (major >= 20) return item('Node.js', `${process.version} · >= 20`, 'ok')
  return item('Node.js', `${process.version} · 建议 >= 20`, 'warn')
}

function envConfigured(keys: string[]): boolean {
  return keys.some(k => Boolean(process.env[k]?.trim()))
}

export async function runSelfCheck(): Promise<SelfCheckResult> {
  const categories: SelfCheckCategory[] = []

  // Runtime
  const runtimeItems: SelfCheckItem[] = [
    checkNode(),
    checkPython(),
    hasTahpProject()
      ? item('TAHP 项目根', tahpPaths.projectRoot, 'ok')
      : item('TAHP 项目根', '未找到 skills/ 或 knowledge-base/', 'err'),
    existsSync(join(tahpPaths.projectRoot, 'hermes-agent-main'))
      ? item('Hermes Agent 目录', 'hermes-agent-main 已就绪', 'ok')
      : item('Hermes Agent 目录', '未找到 hermes-agent-main', 'warn'),
  ]
  categories.push({ title: '运行环境', icon: 'server', items: runtimeItems })

  // Agent & bridge
  let hermesVer = ''
  try {
    hermesVer = (await hermesCli.getVersion()).split('\n')[0].replace('Hermes Agent ', '')
  } catch {
    hermesVer = '未知'
  }
  const bridgeRunning = getAgentBridgeManager().running
  const agentItems: SelfCheckItem[] = [
    bridgeRunning
      ? item('Hermes Agent Bridge', '[agent-bridge] running · ready', 'ok')
      : item('Hermes Agent Bridge', '[agent-bridge] stopped', 'err'),
    hermesVer !== '未知'
      ? item('hermes CLI', `v${hermesVer} · 已安装`, 'ok')
      : item('hermes CLI', '无法获取版本', 'warn'),
    item('TaskStream Socket', '/tahp-run · 服务端就绪', 'ok'),
  ]
  categories.push({ title: 'Agent 与桥接', icon: 'spark', items: agentItems })

  // Skills & knowledge
  const skillCount = countSkills()
  const kbCount = countKnowledgeEntries()
  const skillKbItems: SelfCheckItem[] = [
    skillCount > 0
      ? item('Skill 索引', `${skillCount} 个 Skill · 已加载`, 'ok')
      : item('Skill 索引', '未找到 Skill 目录', 'warn'),
    existsSync(tahpPaths.knowledgeDir)
      ? item('知识库 BM25', `${kbCount} 条目 · 索引就绪`, kbCount > 0 ? 'ok' : 'warn')
      : item('知识库 BM25', 'knowledge-base/ 不存在', 'warn'),
  ]
  categories.push({ title: 'Skill 与知识库', icon: 'layers', items: skillKbItems })

  // Credentials
  const hasModelKey = envConfigured([
    'ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'DEEPSEEK_API_KEY',
    'DASHSCOPE_API_KEY', 'GOOGLE_API_KEY',
  ])
  const hasJira = envConfigured(['TAHP_JIRA_USERNAME', 'TAHP_JIRA_TOKEN', 'JIRA_USERNAME', 'JIRA_TOKEN'])
  const hasGerrit = envConfigured(['HARNESS_GERRIT_USER', 'HARNESS_GERRIT_TOKEN', 'HARNESS_QIZHI_USER'])

  const credItems: SelfCheckItem[] = [
    hasModelKey
      ? item('LLM API Key', '已在环境变量配置', 'ok')
      : item('LLM API Key', '未检测到常见 API Key 环境变量', 'warn'),
    hasJira
      ? item('JIRA 凭证', 'JIRA 相关环境变量已设置', 'ok')
      : item('JIRA 凭证', 'TAHP_JIRA_* / JIRA_* 未配置', 'warn'),
    hasGerrit
      ? item('Gerrit 凭证', 'HARNESS_GERRIT_* 已配置', 'ok')
      : item('Gerrit 凭证', 'HARNESS_GERRIT_* 未配置', 'warn'),
  ]
  categories.push({ title: '凭证与配置', icon: 'key', items: credItems })

  const allItems = categories.flatMap(c => c.items)
  const pass = allItems.filter(i => i.state === 'ok').length
  const warn = allItems.filter(i => i.state === 'warn').length
  const fail = allItems.filter(i => i.state === 'err').length
  const total = allItems.length
  const score = total > 0 ? Math.round(((pass + warn * 0.5) / total) * 100) : 0
  const level = fail > 0 ? '需修复' : warn > 0 ? '良好' : '优秀'

  const now = new Date()
  const timeStr = `${now.getFullYear()}/${now.getMonth() + 1}/${now.getDate()} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`
  const note = fail > 0
    ? `${fail} 项失败 · ${warn} 项告警`
    : warn > 0
      ? `${warn} 项告警`
      : '全部通过'

  historyStore.unshift({ time: timeStr, score, note })
  if (historyStore.length > 10) historyStore.length = 10

  return {
    score,
    level,
    updated: timeStr,
    pass,
    warn,
    fail,
    total,
    categories,
    history: [...historyStore],
  }
}
