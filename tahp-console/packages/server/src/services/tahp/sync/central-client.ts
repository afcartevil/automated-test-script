/**
 * 中心 BFF HTTP 客户端 — 自动携带共享 token 与本机 actor 头。
 */
import { config } from '../../../config'
import { getLocalActor } from '../runtime-mode'
import type { SyncManifest, PullPayload, SubmitPayload } from './manifest'

function base(): string {
  return config.tahp.centralUrl.replace(/\/+$/, '')
}

function headers(extra?: Record<string, string>): Record<string, string> {
  return {
    'x-tahp-token': config.tahp.centralToken,
    'x-tahp-actor': getLocalActor(),
    ...extra,
  }
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = 30000): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const res = await fetch(`${base()}${path}`, { ...init, signal: controller.signal })
    const json = (await res.json().catch(() => ({}))) as { success?: boolean; data?: T; error?: string }
    if (!res.ok || json.success === false) {
      throw new Error(json.error || `中心返回 ${res.status}`)
    }
    return json.data as T
  } catch (e) {
    const err = e as Error
    if (err?.name === 'AbortError') {
      throw new Error(`连接中心超时（${Math.round(timeoutMs / 1000)}s），请确认中心已启动且 ${base()} 可达`)
    }
    throw e
  } finally {
    clearTimeout(timer)
  }
}

/** 中心验测任务行（label* 为 EA 自动执行器写回的进度标签，老中心可能不返回） */
export interface CentralVerifyTask {
  task_id: string
  test_type: string
  item_label: string
  owner: string
  project?: string
  note?: string
  status: string
  created_by: string
  created_at: string
  label?: string
  label_code?: string
  label_updated_at?: string
}

export const centralClient = {
  async ping(): Promise<{ pong: boolean; drafts_pending?: number }> {
    return request('/api/tahp/sync/ping', { headers: headers() })
  },

  async manifest(): Promise<SyncManifest> {
    return request('/api/tahp/sync/manifest', { headers: headers() })
  },

  async pull(since?: string): Promise<PullPayload> {
    const qs = since ? `?since=${encodeURIComponent(since)}` : ''
    return request(`/api/tahp/sync/pull${qs}`, { headers: headers() }, 120_000)
  },

  async submit(payload: SubmitPayload): Promise<{ id: string; action?: string }> {
    return request('/api/tahp/sync/submit', {
      method: 'POST',
      headers: headers({ 'content-type': 'application/json' }),
      body: JSON.stringify(payload),
    })
  },

  async downloadSkillPackage(id: string, packageUrl?: string): Promise<Buffer> {
    let url: string
    if (packageUrl?.startsWith('http')) url = packageUrl
    else if (packageUrl?.startsWith('/')) url = `${base()}${packageUrl}`
    else url = `${base()}/api/tahp/sync/skill/${encodeURIComponent(id)}/package`
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), 120_000)
    try {
      const res = await fetch(url, { headers: headers(), signal: controller.signal })
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(`下载 skill 包失败 ${res.status}: ${text}`)
      }
      const ab = await res.arrayBuffer()
      return Buffer.from(ab)
    } finally {
      clearTimeout(timer)
    }
  },

  async uploadSkillPackage(
    id: string,
    archive_b64: string,
    opts?: { message?: string; local_hash?: string },
  ): Promise<{
    id?: string
    hash: string
    files?: Array<{ rel_path: string }>
    file_count?: number
    submit_id?: string
    status?: string
  }> {
    return request(
      `/api/tahp/sync/skill/${encodeURIComponent(id)}/package/submit`,
      {
        method: 'POST',
        headers: headers({ 'content-type': 'application/json' }),
        body: JSON.stringify({
          archive_b64,
          message: opts?.message,
          local_hash: opts?.local_hash,
        }),
      },
      120_000,
    )
  },

  async latestSkillSubmission(id: string): Promise<{
    submit_id: string
    skill_id: string
    status: string
    hash: string
    comment?: string
    submitted_at?: string
    reviewed_at?: string
  } | null> {
    return request(`/api/tahp/sync/skill/${encodeURIComponent(id)}/submission/latest`, {
      headers: headers(),
    })
  },

  async requestSkillDelete(
    id: string,
    opts?: { message?: string },
  ): Promise<{
    id: string
    submit_id: string
    status: string
    kind: string
    published_hash?: string | null
  }> {
    return request(`/api/tahp/sync/skill/${encodeURIComponent(id)}/delete/submit`, {
      method: 'POST',
      headers: headers({ 'content-type': 'application/json' }),
      body: JSON.stringify({ message: opts?.message }),
    })
  },

  async latestSkillDeletion(id: string): Promise<{
    submit_id: string
    skill_id: string
    kind: string
    status: string
    message?: string
    published_hash?: string | null
    comment?: string
    submitted_at?: string
    reviewed_at?: string
  } | null> {
    return request(`/api/tahp/sync/skill/${encodeURIComponent(id)}/deletion/latest`, {
      headers: headers(),
    })
  },

  async skillHistory(id: string, limit = 50): Promise<{
    id: string
    commits: Array<{
      sha: string
      short_sha: string
      title: string
      author_name: string
      author_email: string
      committed_at: string
      message: string
      web_url?: string
    }>
  }> {
    return request(
      `/api/tahp/sync/skill/${encodeURIComponent(id)}/history?limit=${encodeURIComponent(String(limit))}`,
      { headers: headers() },
    )
  },

  async skillBundles(): Promise<{
    version: number
    bundles: Array<{ id: string; label: string; description?: string; skill_ids: string[]; updated_at: string }>
    auto_rules: Array<{ id: string; label?: string; func_type?: string; module?: string; id_prefix?: string }>
    updated_at: string
  }> {
    return request('/api/tahp/sync/skill-bundles', { headers: headers() })
  },

  /** 适配前置：项目列表（供 Console 下拉） */
  async listAdaptPrereqProjects(): Promise<Array<{
    code: string
    name: string
    product_line?: string
    active_campaign_id?: string | null
    active_publication_id?: string
    active_publication_sequence?: number
    updated_at: string
  }>> {
    return request('/api/tahp/sync/adapt-prereqs/projects', { headers: headers() })
  },

  /** 适配前置：整项目/战役 resolve（含 schema + form_data） */
  async resolveAdaptPrereqs(opts: {
    project_code: string
    campaign_id?: string
    workspace_id?: string
    domain_id?: string
  }): Promise<{
    project_code: string
    campaign_id: string
    publication_id?: string
    from_os: string
    to_os: string
    domains: Array<{
      workspace_id: string
      domain_id: string
      revision: number
      schema: Array<Record<string, unknown>>
      form_data: Record<string, unknown>
      stale_fields: string[]
      incomplete_required: string[]
      updated_at?: string
      updated_by?: string
      line_layout_revision?: number
      layout_stale?: boolean
      related_skills?: string[]
    }>
    line_id?: string
    layout_stale?: boolean
  }> {
    const qs = new URLSearchParams()
    qs.set('project_code', opts.project_code)
    if (opts.campaign_id) qs.set('campaign_id', opts.campaign_id)
    if (opts.workspace_id) qs.set('workspace_id', opts.workspace_id)
    if (opts.domain_id) qs.set('domain_id', opts.domain_id)
    return request(`/api/tahp/sync/adapt-prereqs/resolve?${qs}`, { headers: headers() })
  },

  async fetchPublishedLineLayouts(): Promise<{ lines: Array<{
    line_id: string
    from_os: string
    to_os: string
    domains: Array<{
      workspace_id: string
      domain_id: string
      revision: number
      fields: Array<Record<string, unknown>>
      related_skills: string[]
      interaction_mode?: boolean
      updated_at?: string
    }>
  }> }> {
    return request('/api/tahp/sync/adapt-layouts/lines/published', { headers: headers() })
  },

  /** 质量看板：上报连通性 */
  async qualityPing(): Promise<{ pong: boolean; actor?: string; runs_total?: number }> {
    return request('/api/tahp/sync/quality/ping', { headers: headers() })
  },

  /**
   * 质量看板：上报一次或多次执行结果（幂等 run_id）。
   * 对应中心 POST /api/tahp/sync/quality/runs
   */
  async uploadQualityRun(
    run: QualityRunPayload | { runs: QualityRunPayload[] },
  ): Promise<{ results: Array<{ run_id?: string; action?: string; ok: boolean; error?: string }> }> {
    return request('/api/tahp/sync/quality/runs', {
      method: 'POST',
      headers: headers({ 'content-type': 'application/json' }),
      body: JSON.stringify(run),
    })
  },

  /** EA 绑定 Jira：中心校验 myself 后开通/刷新账户。body 含密码，勿复用到其它 sync 接口。 */
  async jiraBind(input: {
    username: string
    password: string
    jira_base_url?: string
  }): Promise<{
    token: string
    user: { username: string; role: string; auth_source?: string; display_name?: string }
    ticket: string
    consume_path: string
  }> {
    return request('/api/tahp/auth/jira-bind', {
      method: 'POST',
      headers: headers({ 'content-type': 'application/json' }),
      body: JSON.stringify({
        username: input.username,
        password: input.password,
        jira_base_url: input.jira_base_url,
      }),
    }, 20_000)
  },

  /** 已有中心 session 时签发一次性网页 ticket */
  async issueAuthTicket(sessionToken: string, next = '/'): Promise<{ ticket: string; consume_path: string }> {
    return request('/api/tahp/auth/ticket', {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${sessionToken}`,
      },
      body: JSON.stringify({ next }),
    })
  },

  async myTaskPackages(sessionToken: string): Promise<Array<{
    package_id: string
    project_code: string
    campaign_id?: string
    domain_id: string
    domain_label?: string
    title: string
    kind: string
    unread: boolean
    unread_count: number
    notice_type?: string
    next?: string
    version_type?: string
    variant?: string
    node_rule_id?: string
    resolved_version?: string
  }>> {
    return request('/api/tahp/tasks/my-packages', {
      headers: { authorization: `Bearer ${sessionToken}` },
    })
  },

  /** 本人在中心被指派的未完成验测任务（总览「验测任务」卡片数据源） */
  async verifyMine(sessionToken: string): Promise<CentralVerifyTask[]> {
    return request('/api/tahp/tasks/verify/mine?view=open', {
      headers: { authorization: `Bearer ${sessionToken}` },
    })
  },

  /**
   * 写回验测任务执行标签（等待设备 / 验测执行中 …）。
   * 老中心无此接口（404）时抛错，由调用方静默降级为仅本地显示。
   */
  async labelVerifyTask(
    sessionToken: string,
    taskId: string,
    body: { label_code: string; label?: string },
  ): Promise<CentralVerifyTask> {
    return request(`/api/tahp/tasks/verify/mine/${encodeURIComponent(taskId)}/label`, {
      method: 'POST',
      headers: { authorization: `Bearer ${sessionToken}`, 'content-type': 'application/json' },
      body: JSON.stringify(body),
    })
  },

  /** 关单并关联本人验测报告；可同一次写入终态标签 */
  async completeVerifyTask(
    sessionToken: string,
    taskId: string,
    body: { run_id?: string; label_code?: string; label?: string } = {},
  ): Promise<CentralVerifyTask> {
    return request(`/api/tahp/tasks/verify/mine/${encodeURIComponent(taskId)}/complete`, {
      method: 'POST',
      headers: { authorization: `Bearer ${sessionToken}`, 'content-type': 'application/json' },
      body: JSON.stringify(body),
    })
  },

  async applyCandidates(sessionToken: string, runId: string): Promise<{
    run: { run_id: string; project_code: string; campaign_id?: string; status?: string; dimension?: string; domain_id?: string }
    packages: Array<{
      package_id: string
      title: string
      domain_label: string
      pending_items: Array<{ line_id: string; item_id: string; title: string }>
    }>
    domain_unspecified?: boolean
    campaign_unspecified?: boolean
  }> {
    return request(`/api/tahp/tasks/apply-candidates?run_id=${encodeURIComponent(runId)}`, {
      headers: { authorization: `Bearer ${sessionToken}` },
    })
  },

  async applyTaskRun(sessionToken: string, packageId: string, body: {
    run_id: string
    line_ids: string[]
    also_pass: boolean
  }): Promise<{ updated: number }> {
    return request(`/api/tahp/tasks/packages/${encodeURIComponent(packageId)}/apply-run`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${sessionToken}`,
      },
      body: JSON.stringify(body),
    })
  },

  /** 定时任务「项目节点信息表」在线取数回传：对应中心 POST /api/tahp/sync/verify-plan/nodes */
  async reportVerifyPlanNodes(body: {
    request_id: string
    source_name?: string
    projects?: Array<{ name: string; status?: string; nodes: Record<string, string | null> }>
    error?: string
  }): Promise<{ projects?: number; ignored?: string }> {
    return request('/api/tahp/sync/verify-plan/nodes', {
      method: 'POST',
      headers: headers({ 'content-type': 'application/json' }),
      body: JSON.stringify(body),
    })
  },

  /** 效能看板：上报一条带项目的 session 用量。同 client_id + session_id 由中心覆盖。 */
  async uploadEfficiencySession(body: EfficiencySessionPayload): Promise<{ ok: boolean }> {
    return request('/api/tahp/sync/efficiency/sessions', {
      method: 'POST',
      headers: headers({ 'content-type': 'application/json' }),
      body: JSON.stringify(body),
    })
  },
}

export interface EfficiencySessionPayload {
  client_id: string
  session_id: string
  actor: string
  project_code: string
  model: string
  provider: string
  input_tokens: number
  output_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  reasoning_tokens: number
  estimated_cost_usd: number
  actual_cost_usd: number | null
  started_at: string
}

/** 与 easyadapter_bff quality-store IngestRunInput 对齐 */
export interface QualityRunPayload {
  run_id: string
  dimension: string
  project_code?: string
  campaign_id?: string
  workspace_id?: string
  domain_id?: string
  owner?: string
  device?: { id?: string; name?: string }
  /** 被测软件版本（self-check 报告 version 字段） */
  version?: string
  status?: string
  started_at?: string
  ended_at?: string
  metrics?: Record<string, number>
  issues?: Array<{
    key: string
    title: string
    module?: string
    owner?: string
    severity?: string
    status?: string
    message?: string
  }>
  artifacts?: Array<{ type: string; name: string; ref?: string; inline?: boolean }>
  ai_summary?: string
  source?: { tool?: string; version?: string; host?: string }
  schema_version?: number
  current_node?: string
  parent_run_id?: string
  headline?: string
  extra?: Record<string, unknown>
}
