/**
 * 验测任务 API（中心 BFF 指派，经 EA 服务端代理）
 * 测试账号（test- 前缀）另有本机自动执行状态（标签/设备/报告），随 mine 响应一并返回。
 */
import { tahpGet, tahpPost } from './client'

/** 执行标签码（与中心 VERIFY_TASK_LABELS / 本机 verify-auto-run 对齐） */
export type VerifyAutoLabelCode =
  | 'waiting_device'
  | 'resolving_flash'
  | 'running'
  | 'waiting_human'
  | 'precheck_blocked'
  | 'flash_failed'
  | 'run_failed'
  | 'wait_timeout'
  | 'completed_pass'
  | 'completed_fail'
  | 'close_failed'
  | 'paused'
  | 'cancelled'

/** 标签配色（EA 卡片用 class 后缀） */
export const VERIFY_AUTO_LABEL_TONE: Record<string, 'wait' | 'run' | 'human' | 'fail' | 'done' | 'muted'> = {
  waiting_device: 'wait',
  resolving_flash: 'wait',
  running: 'run',
  waiting_human: 'human',
  precheck_blocked: 'human',
  flash_failed: 'fail',
  run_failed: 'fail',
  wait_timeout: 'fail',
  completed_pass: 'done',
  completed_fail: 'fail',
  close_failed: 'fail',
  paused: 'muted',
  cancelled: 'muted',
}

export function verifyLabelTone(code?: string): string {
  return (code && VERIFY_AUTO_LABEL_TONE[code]) || 'muted'
}

export interface VerifyTaskItem {
  task_id: string
  test_type: string
  item_label: string
  owner: string
  project?: string
  note?: string
  status: string
  created_by: string
  created_at: string
  /** 中心已存的执行标签（EA 写回） */
  label?: string
  label_code?: VerifyAutoLabelCode
  label_updated_at?: string
  /** 本机自动执行状态（仅测试账号所在机器有值） */
  auto?: VerifyAutoTaskState
}

export interface VerifyAutoTaskState {
  label: string
  label_code: VerifyAutoLabelCode
  phase: string
  device_id?: string
  run_id?: string
  waiting_since?: string
  started_at?: string
  last_error?: string
  /** 标签写回中心失败的原因（老中心无接口 / 中心不可达） */
  label_error?: string
  updated_at: string
}

export interface VerifyAutoRunSummary {
  eligible: boolean
  reason?: string
  enabled: boolean
  account?: string
  is_test_account: boolean
  active_task_id?: string
  poll_ms: number
  max_wait_device_ms: number
}

export interface MyVerifyTasksResult {
  tasks: VerifyTaskItem[]
  /** 中心不可达/未配置/未绑定（此时 tasks 为空，前端应红字提示） */
  degraded: boolean
  reason?: string
  auto_run?: VerifyAutoRunSummary
}

/** 本人在中心被指派的未完成验测任务（中心不可达时 degraded=true） */
export function fetchMyVerifyTasks(): Promise<MyVerifyTasksResult> {
  return tahpGet<MyVerifyTasksResult>('/api/tahp/verify-tasks/mine')
}

/** 本机自动执行状态（含任务明细） */
export function fetchVerifyAutoRunStatus(): Promise<VerifyAutoRunSummary> {
  return tahpGet<VerifyAutoRunSummary>('/api/tahp/verify-auto-run/status')
}

/** 暂停 / 恢复验测任务自动执行 */
export function setVerifyAutoRunEnabled(enabled: boolean): Promise<VerifyAutoRunSummary> {
  return tahpPost<VerifyAutoRunSummary>('/api/tahp/verify-auto-run/enabled', { enabled })
}

/** 取消某个验测任务的自动执行（在跑则结束测试） */
export function cancelVerifyAutoRunTask(taskId: string): Promise<VerifyAutoRunSummary> {
  return tahpPost<VerifyAutoRunSummary>(
    `/api/tahp/verify-auto-run/tasks/${encodeURIComponent(taskId)}/cancel`,
  )
}
