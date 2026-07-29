import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { join } from 'path'
import { logger } from '../../logger'
import { tahpPaths } from '../paths'
import { getStage } from './registry'
import type { NodeTarget, WorkflowDefinition, WorkflowNode } from './types'

export const DEFAULT_WORKFLOW: WorkflowDefinition = {
  id: 'adapt-default',
  version: 1,
  label: '标准适配流水线',
  maxIterations: 3,
  nodes: [
    { key: 'prereq', enabled: true, onUnavailable: 'fail' },
    { key: 'adapt', enabled: true, onUnavailable: 'fail' },
    { key: 'build', enabled: true, onUnavailable: 'manual_gate', onFail: 'human_review' },
    { key: 'flash', enabled: true, onUnavailable: 'manual_gate', onFail: 'human_review' },
    { key: 'selfcheck', enabled: true, onUnavailable: 'manual_gate', onDone: 'gerrit', onFail: 'triage' },
    { key: 'triage', enabled: true, onUnavailable: 'skip', onDone: 'human_review', onFail: 'human_review' },
    { key: 'human_review', enabled: true, onUnavailable: 'fail', onDone: 'build', onDoneEffect: 'increment_iteration' },
    { key: 'gerrit', enabled: true, onUnavailable: 'manual_gate', onDone: 'END', onFail: 'human_review' },
  ],
}

export type ValidateWorkflowResult =
  | { ok: true }
  | { ok: false; errors: string[] }

function workflowConfigDir(): string {
  if (process.env.TAHP_ADAPT_PIPELINE_DIR) {
    return process.env.TAHP_ADAPT_PIPELINE_DIR
  }
  return join(tahpPaths.projectRoot, '.tahp-config', 'adapt-pipeline')
}

export function workflowConfigPath(): string {
  return join(workflowConfigDir(), 'workflow.json')
}

export function getEnabledNodes(workflow: WorkflowDefinition): WorkflowNode[] {
  return workflow.nodes.filter(n => n.enabled)
}

export function resolveDefaultOnDone(workflow: WorkflowDefinition, nodeKey: string): NodeTarget {
  const enabled = getEnabledNodes(workflow)
  const idx = enabled.findIndex(n => n.key === nodeKey)
  if (idx < 0) return 'ABORT'
  const next = enabled[idx + 1]
  return next ? next.key : 'END'
}

function nodeIndexMap(workflow: WorkflowDefinition): Map<string, number> {
  const map = new Map<string, number>()
  workflow.nodes.forEach((n, i) => map.set(n.key, i))
  return map
}

function isValidTarget(target: NodeTarget, nodeKeys: Set<string>): boolean {
  return target === 'END' || target === 'ABORT' || nodeKeys.has(target)
}

function collectEdges(workflow: WorkflowDefinition): Array<{ from: string; to: NodeTarget; kind: 'onDone' | 'onFail' }> {
  const edges: Array<{ from: string; to: NodeTarget; kind: 'onDone' | 'onFail' }> = []
  for (const node of workflow.nodes) {
    if (!node.enabled) continue
    const onDone = node.onDone ?? resolveDefaultOnDone(workflow, node.key)
    edges.push({ from: node.key, to: onDone, kind: 'onDone' })
    const onFail = node.onFail ?? 'ABORT'
    edges.push({ from: node.key, to: onFail, kind: 'onFail' })
  }
  return edges
}

function canReachEnd(workflow: WorkflowDefinition): boolean {
  const enabled = getEnabledNodes(workflow)
  if (enabled.length === 0) return false

  const adj = new Map<string, NodeTarget[]>()
  for (const edge of collectEdges(workflow)) {
    if (!adj.has(edge.from)) adj.set(edge.from, [])
    adj.get(edge.from)!.push(edge.to)
  }

  const start = enabled[0].key
  const stack = [start]
  const seen = new Set<string>()

  while (stack.length > 0) {
    const cur = stack.pop()!
    if (seen.has(cur)) continue
    seen.add(cur)
    for (const to of adj.get(cur) ?? []) {
      if (to === 'END') return true
      if (to !== 'ABORT' && !seen.has(to)) stack.push(to)
    }
  }
  return false
}

export function validateWorkflow(workflow: WorkflowDefinition): ValidateWorkflowResult {
  const errors: string[] = []

  if (!workflow.nodes?.length) {
    errors.push('workflow.nodes 不能为空')
    return { ok: false, errors }
  }

  const keys = workflow.nodes.map(n => n.key)
  const keySet = new Set(keys)
  if (keySet.size !== keys.length) {
    errors.push('workflow.nodes 中存在重复的 key')
  }

  for (const node of workflow.nodes) {
    if (!getStage(node.key)) {
      errors.push(`未注册的阶段: ${node.key}`)
    }
  }

  for (const node of workflow.nodes) {
    const targets: Array<{ label: string; target: NodeTarget | undefined }> = [
      { label: 'onDone', target: node.onDone },
      { label: 'onFail', target: node.onFail },
    ]
    for (const { label, target } of targets) {
      if (target === undefined) continue
      if (!isValidTarget(target, keySet)) {
        errors.push(`节点 ${node.key} 的 ${label} 目标无效: ${target}`)
      }
    }
  }

  if (workflow.maxIterations < 1) {
    errors.push('maxIterations 必须 >= 1')
  }

  if (!canReachEnd(workflow)) {
    errors.push('不存在从首个 enabled 节点到达 END 的路径')
  }

  const idxMap = nodeIndexMap(workflow)
  for (const edge of collectEdges(workflow)) {
    if (edge.to === 'END' || edge.to === 'ABORT') continue
    const fromIdx = idxMap.get(edge.from)
    const toIdx = idxMap.get(edge.to)
    if (fromIdx === undefined || toIdx === undefined) continue
    if (toIdx >= fromIdx) continue

    const node = workflow.nodes.find(n => n.key === edge.from)
    const targetStage = getStage(edge.to)

    if (edge.kind === 'onDone') {
      if (node?.onDoneEffect !== 'increment_iteration') {
        errors.push(
          `回环边 ${edge.from} → ${edge.to} 必须声明 onDoneEffect: 'increment_iteration'`,
        )
      }
      if (!node || !getStage(edge.from)?.isHumanGate) {
        errors.push(`回环边 ${edge.from} → ${edge.to} 的源节点必须设置 isHumanGate: true`)
      }
    } else if (!targetStage?.isHumanGate) {
      // onFail 回退只能进人工门，禁止 selfcheck → build 类无人值守自转
      errors.push(`回环边 ${edge.from} → ${edge.to} 的 onFail 目标必须是人工门节点`)
    }
  }

  return errors.length ? { ok: false, errors } : { ok: true }
}

let workflowOverrideForTest: WorkflowDefinition | null = null

/** 仅测试：覆盖 loadWorkflow 返回值 */
export function setWorkflowOverrideForTest(wf: WorkflowDefinition | null): void {
  workflowOverrideForTest = wf
}

export function saveWorkflow(workflow: WorkflowDefinition): ValidateWorkflowResult {
  const result = validateWorkflow(workflow)
  if (!result.ok) return result
  const path = workflowConfigPath()
  const dir = workflowConfigDir()
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  writeFileSync(path, `${JSON.stringify(workflow, null, 2)}\n`, 'utf-8')
  return { ok: true }
}

export function loadWorkflow(): WorkflowDefinition {
  if (workflowOverrideForTest) {
    return workflowOverrideForTest
  }
  const path = workflowConfigPath()
  if (!existsSync(path)) {
    return DEFAULT_WORKFLOW
  }
  try {
    const raw = readFileSync(path, 'utf-8')
    const parsed = JSON.parse(raw) as WorkflowDefinition
    const result = validateWorkflow(parsed)
    if (result.ok) {
      return parsed
    }
    logger.warn({ errors: result.errors }, '[adapt-pipeline] workflow.json 校验失败，回落默认流程')
  } catch (err) {
    logger.warn({ err }, '[adapt-pipeline] 读取 workflow.json 失败，回落默认流程')
  }
  return DEFAULT_WORKFLOW
}
