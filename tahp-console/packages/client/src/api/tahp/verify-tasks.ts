/**
 * 验测任务 API（中心 BFF 指派，经 EA 服务端代理）
 */
import { tahpGet } from './client'

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
}

export interface MyVerifyTasksResult {
  tasks: VerifyTaskItem[]
  /** 中心不可达/未配置/未绑定（此时 tasks 为空，前端应红字提示） */
  degraded: boolean
  reason?: string
}

/** 本人在中心被指派的未完成验测任务（中心不可达时 degraded=true） */
export function fetchMyVerifyTasks(): Promise<MyVerifyTasksResult> {
  return tahpGet<MyVerifyTasksResult>('/api/tahp/verify-tasks/mine')
}
