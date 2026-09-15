import Router from '@koa/router'
import {
  createModemBaselineRun,
  createModemPatchRepo,
  createModemPatchRule,
  continueModemBaselineRun,
  deleteModemPatchRepo,
  deleteModemPatchRule,
  getModemBaselineDefaults,
  getModemPatchWorkspaceProfile,
  listModemBaselineRuns,
  listModemBuildProjects,
  listModemPatchBranchTemplates,
  listModemPatchRepos,
  listModemPatchRules,
  importModemPatchBranchTemplatesFromExcel,
  openModemBaselineConflictFile,
  parseModemPatchNotice,
  precheckModemPatchConfig,
  readModemBaselineLogTail,
  readModemBaselineRun,
  recommendModemPatchConfig,
  refreshModemBaselineConflicts,
  registerModemBaselineSseClient,
  scheduleAutoExtractBranchTemplatesForRepo,
  saveModemPatchWorkspaceProfile,
  scanModemPatchRepos,
  scanModemPatchReposMulti,
  stopModemBaselineRun,
  updateModemPatchRepo,
  updateModemPatchRule,
  unregisterModemBaselineSseClient,
} from '../../services/tahp/modem-baseline'
import {
  isModemNoticePlatformTasksComplete,
  listModemBaselineNotices,
  updateModemBaselineNoticePlatformTask,
  updateModemBaselineNoticeStatus,
} from '../../services/tahp/modem-baseline-notices'

export const tahpModemBaselineRoutes = new Router({ prefix: '/api/tahp/modem-baseline' })

function resolveOwner(ctx: any) {
  const owner = String(ctx.get('x-tahp-owner') || '').trim()
  return owner || undefined
}

tahpModemBaselineRoutes.get('/defaults', async (ctx) => {
  try {
    ctx.body = { success: true, data: getModemBaselineDefaults() }
  } catch (error) {
    ctx.status = 500
    ctx.body = { success: false, error: (error as Error).message }
  }
})

async function handleListBuildProjects(ctx: any) {
  try {
    const body = (ctx.request.body || {}) as {
      work_dir?: string
      workDir?: string
      mapped_prefix?: string
      remote_prefix?: string
    }
    const query = ctx.query || {}
    ctx.body = {
      success: true,
      data: await listModemBuildProjects({
        work_dir: body.work_dir || body.workDir || query.work_dir || query.workDir,
        mapped_prefix: body.mapped_prefix || query.mapped_prefix,
        remote_prefix: body.remote_prefix || query.remote_prefix,
      }),
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'work_dir_required' ? 400 : 500
    ctx.body = { success: false, error: message }
  }
}

// GET/POST 双挂载，避免前后端方法不一致导致 404
tahpModemBaselineRoutes.get('/build-projects', handleListBuildProjects)
tahpModemBaselineRoutes.post('/build-projects', handleListBuildProjects)

tahpModemBaselineRoutes.get('/workspace-profile', async (ctx) => {
  ctx.body = { success: true, data: getModemPatchWorkspaceProfile(resolveOwner(ctx)) }
})

tahpModemBaselineRoutes.put('/workspace-profile', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as { mappedPrefix?: string; remotePrefix?: string; roots?: string[] }
    ctx.body = {
      success: true,
      data: saveModemPatchWorkspaceProfile({
        mappedPrefix: body.mappedPrefix,
        remotePrefix: body.remotePrefix,
        roots: Array.isArray(body.roots) ? body.roots : [],
      }, resolveOwner(ctx)),
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'invalid_workspace_profile' ? 400 : 500
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.get('/repos', async (ctx) => {
  ctx.body = { success: true, data: { items: listModemPatchRepos(resolveOwner(ctx)) } }
})

tahpModemBaselineRoutes.post('/repos', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as {
      label?: string
      localPath?: string
      projectName?: string
      platform?: string
      vendor?: string
    }
    const owner = resolveOwner(ctx)
    const repo = createModemPatchRepo(body, owner)
    scheduleAutoExtractBranchTemplatesForRepo(repo.repoId, owner)
    ctx.body = { success: true, data: listModemPatchRepos(owner).find(item => item.repoId === repo.repoId) ?? repo }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'invalid_repo_profile' || message === 'workspace_profile_not_found'
      ? 400
      : message === 'repo_path_not_found'
        ? 404
        : 500
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.put('/repos/:repoId', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as {
      label?: string
      localPath?: string
      platform?: string
      branches?: unknown
    }
    ctx.body = {
      success: true,
      data: updateModemPatchRepo(ctx.params.repoId, {
        label: body.label,
        localPath: body.localPath,
        platform: body.platform,
        branches: (body as any).branches,
      }, resolveOwner(ctx)),
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'invalid_repo_profile'
      || message === 'repo_branches_trunk_required'
      || message === 'repo_branches_mp_required'
      ? 400
      : message === 'repo_not_found' || message === 'repo_path_not_found'
        ? 404
        : 500
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.post('/repos/:repoId/refresh-branches', async (ctx) => {
  try {
    const owner = resolveOwner(ctx)
    scheduleAutoExtractBranchTemplatesForRepo(ctx.params.repoId, owner)
    ctx.body = {
      success: true,
      data: listModemPatchRepos(owner).find(item => item.repoId === ctx.params.repoId) ?? null,
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'repo_not_found' ? 404 : 400
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.delete('/repos/:repoId', async (ctx) => {
  try {
    ctx.body = { success: true, data: deleteModemPatchRepo(ctx.params.repoId, resolveOwner(ctx)) }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'repo_not_found' ? 404 : 400
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.post('/repos/scan', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as { root?: string; roots?: unknown }
    const roots = Array.isArray(body.roots)
      ? body.roots.map(item => String(item ?? '')).filter(Boolean)
      : (body.root ? [String(body.root)] : [])
    ctx.body = { success: true, data: scanModemPatchReposMulti(roots, resolveOwner(ctx)) }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'invalid_scan_root' || message === 'workspace_profile_not_found'
      ? 400
      : message === 'scan_root_not_found'
        ? 404
        : 500
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.get('/rules', async (ctx) => {
  ctx.body = { success: true, data: { items: listModemPatchRules(resolveOwner(ctx)) } }
})

tahpModemBaselineRoutes.get('/branch-templates', async (ctx) => {
  ctx.body = { success: true, data: { items: listModemPatchBranchTemplates(resolveOwner(ctx)) } }
})

tahpModemBaselineRoutes.post('/branch-templates/import', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as { filePath?: string }
    ctx.body = {
      success: true,
      data: importModemPatchBranchTemplatesFromExcel(String(body.filePath ?? ''), resolveOwner(ctx)),
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'invalid_branch_template_file' || message.startsWith('branch_template_missing_columns')
      || message.startsWith('branch_template_invalid_row') || message === 'branch_template_empty'
      ? 400
      : message === 'branch_template_file_not_found'
        ? 404
        : message === 'branch_template_file_busy'
          ? 409
          : 500
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.post('/rules', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as Record<string, unknown>
    ctx.body = { success: true, data: createModemPatchRule(body as any, resolveOwner(ctx)) }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'invalid_rule' ? 400 : 500
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.put('/rules/:ruleId', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as Record<string, unknown>
    ctx.body = { success: true, data: updateModemPatchRule(ctx.params.ruleId, body as any, resolveOwner(ctx)) }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'rule_not_found' ? 404 : 400
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.delete('/rules/:ruleId', async (ctx) => {
  try {
    ctx.body = { success: true, data: deleteModemPatchRule(ctx.params.ruleId, resolveOwner(ctx)) }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'rule_not_found' ? 404 : 400
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.get('/notices', async (ctx) => {
  const statusRaw = String(ctx.query.status || 'pending').trim()
  const status = (statusRaw === 'all' || statusRaw === 'pending' || statusRaw === 'applied' || statusRaw === 'dismissed')
    ? statusRaw
    : 'pending'
  ctx.body = { success: true, data: { items: listModemBaselineNotices({ status }) } }
})

tahpModemBaselineRoutes.post('/notices/:noticeId/apply', async (ctx) => {
  try {
    ctx.body = {
      success: true,
      data: updateModemBaselineNoticeStatus(ctx.params.noticeId, 'applied'),
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'notice_not_found' ? 404 : 400
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.post('/notices/:noticeId/dismiss', async (ctx) => {
  try {
    ctx.body = {
      success: true,
      data: updateModemBaselineNoticeStatus(ctx.params.noticeId, 'dismissed'),
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'notice_not_found' ? 404 : 400
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.post('/notices/:noticeId/platform-tasks/:platform/status', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as { status?: string; runId?: string }
    const status = String(body.status ?? '').trim() as 'pending' | 'in_progress' | 'done' | 'failed' | 'skipped'
    const allowed: string[] = ['pending', 'in_progress', 'done', 'failed', 'skipped']
    if (!allowed.includes(status)) {
      ctx.status = 400
      ctx.body = { success: false, error: 'invalid_platform_task_status' }
      return
    }
    ctx.body = {
      success: true,
      data: updateModemBaselineNoticePlatformTask(
        ctx.params.noticeId,
        decodeURIComponent(ctx.params.platform),
        { status, runId: body.runId ? String(body.runId) : undefined },
      ),
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'notice_not_found' || message === 'platform_task_not_found' ? 404 : 400
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.get('/notices/:noticeId/platform-tasks/complete', async (ctx) => {
  try {
    const items = listModemBaselineNotices({ status: 'all' })
    const notice = items.find(item => item.noticeId === ctx.params.noticeId)
    if (!notice) {
      ctx.status = 404
      ctx.body = { success: false, error: 'notice_not_found' }
      return
    }
    ctx.body = { success: true, data: { complete: isModemNoticePlatformTasksComplete(notice) } }
  } catch (error) {
    ctx.status = 400
    ctx.body = { success: false, error: (error as Error).message }
  }
})

tahpModemBaselineRoutes.post('/parse-notice', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as { text?: string }
    ctx.body = { success: true, data: parseModemPatchNotice(String(body.text ?? '')) }
  } catch (error) {
    ctx.status = 400
    ctx.body = { success: false, error: (error as Error).message }
  }
})

tahpModemBaselineRoutes.post('/recommend', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as {
      noticeText?: string
      repoId?: string
      config?: unknown
      platform?: string
      tosVersion?: string
      targetMode?: 'trunk' | 'mp'
    }
    ctx.body = {
      success: true,
      data: recommendModemPatchConfig({
        noticeText: body.noticeText ? String(body.noticeText) : undefined,
        repoId: body.repoId ? String(body.repoId) : undefined,
        config: (body.config || {}) as any,
        platform: body.platform ? String(body.platform) : undefined,
        tosVersion: body.tosVersion ? String(body.tosVersion) : undefined,
        targetMode: body.targetMode === 'trunk' || body.targetMode === 'mp' ? body.targetMode : undefined,
      }, resolveOwner(ctx)),
    }
  } catch (error) {
    ctx.status = 400
    ctx.body = { success: false, error: (error as Error).message }
  }
})

tahpModemBaselineRoutes.post('/precheck', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as { config?: unknown; repoId?: string }
    ctx.body = {
      success: true,
      data: await precheckModemPatchConfig({
        config: (body.config || {}) as Record<string, unknown>,
        repoId: body.repoId ? String(body.repoId) : undefined,
      }, resolveOwner(ctx)),
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = 400
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.get('/runs', async (ctx) => {
  ctx.body = { success: true, data: listModemBaselineRuns() }
})

tahpModemBaselineRoutes.get('/runs/:runId', async (ctx) => {
  const meta = readModemBaselineRun(ctx.params.runId)
  if (!meta) {
    ctx.status = 404
    ctx.body = { success: false, error: 'not_found' }
    return
  }
  ctx.body = { success: true, data: meta }
})

tahpModemBaselineRoutes.get('/runs/:runId/log', async (ctx) => {
  const meta = readModemBaselineRun(ctx.params.runId)
  if (!meta?.logPath) {
    ctx.status = 404
    ctx.body = { success: false, error: 'not_found' }
    return
  }
  const query = ctx.query as Record<string, string | string[] | undefined>
  const rawLines = Array.isArray(query.tailLines) ? query.tailLines[0] : query.tailLines
  const rawBytes = Array.isArray(query.maxBytes) ? query.maxBytes[0] : query.maxBytes
  const view = readModemBaselineLogTail(ctx.params.runId, {
    maxLines: rawLines ? Number(rawLines) : undefined,
    maxBytes: rawBytes ? Number(rawBytes) : undefined,
  })
  ctx.body = { success: true, data: view }
})

tahpModemBaselineRoutes.get('/runs/:runId/events', async (ctx) => {
  try {
    const runId = ctx.params.runId
    ctx.set({
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
    })
    ctx.status = 200
    ctx.respond = false

    const res = ctx.res as any
    registerModemBaselineSseClient(runId, res)

    const keepAlive = setInterval(() => {
      try {
        res.write(': keepalive\n\n')
      } catch {
        clearInterval(keepAlive)
        unregisterModemBaselineSseClient(runId, res)
      }
    }, 15000)

    ctx.req.on('close', () => {
      clearInterval(keepAlive)
      unregisterModemBaselineSseClient(runId, res)
    })
  } catch (error) {
    ctx.status = 404
    ctx.body = { success: false, error: (error as Error).message }
  }
})

tahpModemBaselineRoutes.post('/runs', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as {
      config?: unknown
      noticeId?: string
      platform?: string
    }
    const config = (body.config || {}) as Record<string, unknown>
    const payload = { ...config, noticeId: body.noticeId, platform: body.platform }
    ctx.body = { success: true, data: createModemBaselineRun(payload) }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'invalid_config' ? 400 : 500
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.post('/runs/:runId/stop', async (ctx) => {
  try {
    ctx.body = {
      success: true,
      data: stopModemBaselineRun(ctx.params.runId),
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'not_found'
      ? 404
      : message === 'not_running'
        ? 400
        : 500
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.post('/runs/:runId/continue', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as { build_project?: string }
    ctx.body = {
      success: true,
      data: continueModemBaselineRun(ctx.params.runId, { build_project: body.build_project }),
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'not_found'
      ? 404
      : message === 'running'
        ? 409
        : 400
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.post('/runs/:runId/refresh-conflicts', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as { autoStageResolved?: boolean }
    ctx.body = {
      success: true,
      data: await refreshModemBaselineConflicts(ctx.params.runId, body.autoStageResolved !== false),
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'not_found' ? 404 : 400
    ctx.body = { success: false, error: message }
  }
})

tahpModemBaselineRoutes.post('/runs/:runId/open-conflict-file', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as { file?: string }
    ctx.body = {
      success: true,
      data: openModemBaselineConflictFile(ctx.params.runId, body.file || ''),
    }
  } catch (error) {
    const message = (error as Error).message
    ctx.status = message === 'not_found' || message === 'file_not_found'
      ? 404
      : 400
    ctx.body = { success: false, error: message }
  }
})
