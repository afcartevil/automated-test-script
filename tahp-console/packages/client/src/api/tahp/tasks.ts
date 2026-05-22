import { tahpGet, tahpPost } from './client'

export type TahpModule = 'telephony' | 'kernel-driver' | 'power-mgmt'
export type TahpDomain = 'bug_analysis' | 'code_adaptation' | 'version_adaptation' | 'carrier_porting'

export interface ExecuteTaskRequest {
  document_path: string
  module: TahpModule
  domain: TahpDomain
  constraints_extra?: string[]
  /** 内容模式：直接传入文档文本，服务端写临时文件后执行 */
  document_content?: string
  /** 补充给 Pipeline 的额外上下文说明 */
  extra_context?: string
}

export interface TaskInfo {
  task_id?: string
  taskId?: string
  status?: string
  phase?: string
  progress?: number
  module?: string
  domain?: string
  document_path?: string
  steps?: Array<{ id: string; status: string; message?: string }>
  gate_result?: { result: string; violations?: unknown[] }
  created_at?: string
  updated_at?: string
  error?: string
  [key: string]: unknown
}

export function executeTask(req: ExecuteTaskRequest): Promise<TaskInfo> {
  return tahpPost<TaskInfo>('/api/tahp/tasks', req)
}

export function getTaskStatus(taskId: string): Promise<TaskInfo> {
  return tahpGet<TaskInfo>(`/api/tahp/tasks/${encodeURIComponent(taskId)}`)
}

export interface ListTasksResp { tasks: TaskInfo[]; total?: number }
export function listTasks(includeCompleted = true): Promise<ListTasksResp> {
  const qs = includeCompleted ? '' : '?include_completed=false'
  return tahpGet<ListTasksResp>(`/api/tahp/tasks${qs}`)
}

export function correctTask(taskId: string, feedback: string): Promise<unknown> {
  return tahpPost(`/api/tahp/tasks/${encodeURIComponent(taskId)}/correct`, { feedback })
}
