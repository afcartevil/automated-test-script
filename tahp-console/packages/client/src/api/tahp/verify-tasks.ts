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

/** 本人在中心被指派的未完成验测任务（中心不可达时服务端降级为空列表） */
export function fetchMyVerifyTasks(): Promise<VerifyTaskItem[]> {
  return tahpGet<VerifyTaskItem[]>('/api/tahp/verify-tasks/mine')
}
