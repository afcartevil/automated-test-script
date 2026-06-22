/**
 * TAHP — AI Bug 分析 Pinia store.
 *
 * 职责：
 *   - 管理任务/事件流（与 /tahp-run socket 共享，复用 tasksStore 已有的事件订阅模式）
 *   - 提供 selectedTaskId、selectedJobId 切换
 *   - 提供单条 LLM 拼接文本 + 阶段 + skill 使用清单
 */
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { getTahpSocket, type TahpEvent } from '@/api/tahp/socket'
import {
  listBugTasks, listBugJobs, getBugTask,
  type BugTask, type BugJob,
} from '@/api/tahp/bug-analysis'

interface StreamEntry {
  type: string
  payload: Record<string, unknown>
  ts: number
}

/**
 * Skill 调用记录（Agent 模式）：合并 task.skill_use + task.tool_completed
 * source = 'tool_call'   表示 Agent 真实调用了对应 tool/skill
 * source = 'text_marker' 表示 Agent 文本里出现了 <skill_use /> 标记（兼容）
 */
export interface SkillCallRecord {
  skill_id: string
  source: 'tool_call' | 'text_marker'
  tool_call_id?: string | number
  args?: string
  purpose?: string
  started_ts: number
  completed_ts?: number
  error?: boolean
}

/** Agent TAHP_STAGE 结构化阶段详情（由 BFF 解析后推送） */
export interface StageDetailRecord {
  stage_id: string
  step_id: string
  phase: string
  status: 'running' | 'success' | 'failed'
  skill_used?: string
  message?: string
  detail_lines?: string[]
  fields?: Record<string, string>
  ts: number
}

const STAGE_MARKER_STRIP_RE = /=== TAHP_STAGE:(fetch_jira|download_logs|match_skills|analyze|generate_report) ===\r?\n[\s\S]*?=== END_TAHP_STAGE ===/g

function stripStageMarkers(text: string): string {
  return text.replace(STAGE_MARKER_STRIP_RE, '')
}

export const useBugAnalysisStore = defineStore('tahp-bug-analysis', () => {
  const tasks = ref<Record<string, BugTask>>({})
  const jobs = ref<Record<string, BugJob>>({})
  const streams = ref<Record<string, StreamEntry[]>>({})
  const skillCalls = ref<Record<string, SkillCallRecord[]>>({})
  const stageDetails = ref<Record<string, Record<string, StageDetailRecord>>>({})
  const selectedTaskId = ref<string | null>(null)
  const selectedJobId = ref<string | null>(null)
  const loading = ref(false)
  const lastError = ref<string | null>(null)

  let socketBound = false

  function ensureSocket() {
    if (socketBound) return
    const s = getTahpSocket()
    const handler = (ev: TahpEvent) => {
      const tid = ev.task_id
      if (!tid) return

      // Append to stream
      const arr = streams.value[tid] ? [...streams.value[tid]] : []
      arr.push({ type: ev.type, payload: ev.payload, ts: ev.ts })
      if (arr.length > 800) arr.splice(0, arr.length - 800)
      streams.value = { ...streams.value, [tid]: arr }

      // Update task state (single tasks)
      if (tasks.value[tid]) {
        const t = { ...tasks.value[tid] }
        switch (ev.type) {
          case 'task.started':
            t.status = 'running'
            t.started_at = new Date(ev.ts).toISOString()
            if (ev.payload?.jira_key) t.jira_key = String(ev.payload.jira_key)
            if (ev.payload?.jira_url) t.jira_url = String(ev.payload.jira_url)
            if (ev.payload?.module) t.module = ev.payload.module as BugTask['module']
            break
          case 'task.phase':
            t.phase = ev.payload?.phase as string
            if (typeof ev.payload?.progress === 'number') t.progress = ev.payload.progress as number
            break
          case 'task.stage_detail': {
            const stepId = String(ev.payload?.step_id || '')
            if (!stepId) break
            const statusRaw = String(ev.payload?.status || 'running')
            const status: StageDetailRecord['status'] = statusRaw === 'failed'
              ? 'failed'
              : statusRaw === 'success' ? 'success' : 'running'
            const rec: StageDetailRecord = {
              stage_id: String(ev.payload?.stage_id || ''),
              step_id: stepId,
              phase: String(ev.payload?.phase || ''),
              status,
              skill_used: typeof ev.payload?.skill_used === 'string' ? ev.payload.skill_used : undefined,
              message: typeof ev.payload?.message === 'string' ? ev.payload.message : undefined,
              detail_lines: Array.isArray(ev.payload?.detail_lines)
                ? (ev.payload.detail_lines as string[])
                : undefined,
              fields: (ev.payload?.fields as Record<string, string>) || undefined,
              ts: ev.ts,
            }
            const bucket = { ...(stageDetails.value[tid] || {}) }
            bucket[stepId] = rec
            stageDetails.value = { ...stageDetails.value, [tid]: bucket }
            if (stepId === 'fetch-jira' && rec.fields?.issue_summary) {
              t.title = rec.fields.issue_summary
            }
            break
          }
          case 'task.skill_use':
            if (typeof ev.payload?.skill_id === 'string') {
              const list = t.skills_used || []
              if (!list.includes(ev.payload.skill_id)) {
                t.skills_used = [...list, ev.payload.skill_id]
              }
              const sk: SkillCallRecord = {
                skill_id: ev.payload.skill_id,
                source: (ev.payload.source === 'tool_call' ? 'tool_call' : 'text_marker'),
                tool_call_id: ev.payload.tool_call_id as string | number | undefined,
                args: typeof ev.payload.args === 'string' ? ev.payload.args : undefined,
                purpose: typeof ev.payload.purpose === 'string' ? ev.payload.purpose : undefined,
                started_ts: ev.ts,
              }
              const arr = skillCalls.value[tid] ? [...skillCalls.value[tid]] : []
              arr.push(sk)
              skillCalls.value = { ...skillCalls.value, [tid]: arr }
            }
            break
          case 'task.tool_completed':
            if (typeof ev.payload?.skill_id === 'string') {
              const arr = skillCalls.value[tid] ? [...skillCalls.value[tid]] : []
              // 反向查找最近一次同名且未完成的 tool_call 记录回填完成态
              for (let i = arr.length - 1; i >= 0; i -= 1) {
                if (arr[i].skill_id === ev.payload.skill_id && arr[i].source === 'tool_call' && !arr[i].completed_ts) {
                  arr[i] = { ...arr[i], completed_ts: ev.ts, error: ev.payload.error === true }
                  break
                }
              }
              skillCalls.value = { ...skillCalls.value, [tid]: arr }
            }
            break
          case 'task.completed':
            t.status = 'completed'
            t.phase = 'COMPLETED'
            t.progress = 100
            t.completed_at = new Date(ev.ts).toISOString()
            if (Array.isArray(ev.payload?.skills_used)) {
              t.skills_used = ev.payload.skills_used as string[]
            }
            break
          case 'task.failed':
            t.status = 'failed'
            t.phase = 'FAILED'
            t.completed_at = new Date(ev.ts).toISOString()
            t.error = ev.payload?.error as string
            break
          case 'task.cancelled':
            t.status = 'cancelled'
            t.phase = 'CANCELLED'
            t.completed_at = new Date(ev.ts).toISOString()
            t.error = ev.payload?.error as string
            break
        }
        tasks.value = { ...tasks.value, [tid]: t }
      }

      // Update job state when batch
      if (jobs.value[tid]) {
        const j = { ...jobs.value[tid] }
        if (ev.type === 'task.phase') {
          j.status = 'running'
        }
        if (ev.type === 'task.completed') {
          j.status = (ev.payload?.status as BugJob['status']) || 'completed'
          if (typeof ev.payload?.completed === 'number') j.completed = ev.payload.completed as number
          if (typeof ev.payload?.failed === 'number') j.failed = ev.payload.failed as number
        }
        jobs.value = { ...jobs.value, [tid]: j }
      }
    }
    const events = [
      'task.started', 'task.phase', 'task.step', 'task.message', 'task.stage_detail',
      'task.completed', 'task.failed', 'task.cancelled', 'task.skill_use', 'task.tool_completed', 'task.progress',
    ]
    events.forEach(e => s.on(e, handler))
    socketBound = true
  }

  async function refresh() {
    loading.value = true
    lastError.value = null
    try {
      const [t, j] = await Promise.all([listBugTasks(), listBugJobs()])
      const tmap: Record<string, BugTask> = {}
      for (const it of t) tmap[it.task_id] = it
      tasks.value = tmap
      const jmap: Record<string, BugJob> = {}
      for (const it of j) jmap[it.job_id] = it
      jobs.value = jmap
    } catch (err) {
      lastError.value = (err as Error).message
    } finally {
      loading.value = false
    }
  }

  async function refreshTask(taskId: string) {
    try {
      const t = await getBugTask(taskId)
      tasks.value = { ...tasks.value, [taskId]: t }
    } catch {
      // ignore
    }
  }

  function registerTask(t: BugTask) {
    if (!streams.value[t.task_id]) streams.value = { ...streams.value, [t.task_id]: [] }
    tasks.value = { ...tasks.value, [t.task_id]: t }
  }

  function registerJob(j: BugJob) {
    if (!streams.value[j.job_id]) streams.value = { ...streams.value, [j.job_id]: [] }
    jobs.value = { ...jobs.value, [j.job_id]: j }
  }

  function stream(taskId: string): StreamEntry[] {
    return streams.value[taskId] || []
  }

  function skillCallList(taskId: string): SkillCallRecord[] {
    return skillCalls.value[taskId] || []
  }

  function llmText(taskId: string): string {
    const raw = stream(taskId)
      .filter(e => e.type === 'task.message' && (e.payload as any)?.level === 'stream')
      .map(e => String((e.payload as any)?.text ?? ''))
      .join('')
    return stripStageMarkers(raw)
  }

  function stageDetailMap(taskId: string): Record<string, StageDetailRecord> {
    return stageDetails.value[taskId] || {}
  }

  function reasoningText(taskId: string): string {
    return stream(taskId)
      .filter(e => e.type === 'task.message' && (e.payload as any)?.level === 'reasoning')
      .map(e => String((e.payload as any)?.text ?? ''))
      .join('')
  }

  function structuredEvents(taskId: string): StreamEntry[] {
    return stream(taskId).filter(e => e.type !== 'task.message' || (e.payload as any)?.level !== 'stream')
  }

  function selectTask(taskId: string | null) {
    selectedTaskId.value = taskId
  }

  function selectJob(jobId: string | null) {
    selectedJobId.value = jobId
  }

  const recentTasks = computed(() =>
    Object.values(tasks.value).sort((a, b) => b.started_at.localeCompare(a.started_at)),
  )

  const recentJobs = computed(() =>
    Object.values(jobs.value).sort((a, b) => b.started_at.localeCompare(a.started_at)),
  )

  return {
    tasks, jobs, streams, skillCalls, stageDetails, selectedTaskId, selectedJobId, loading, lastError,
    recentTasks, recentJobs,
    ensureSocket, refresh, refreshTask, registerTask, registerJob,
    stream, skillCallList, llmText, reasoningText, stageDetailMap, structuredEvents, selectTask, selectJob,
  }
})
