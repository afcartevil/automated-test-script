<template>
  <div v-if="visible" class="build-fix-panel card card-pad" style="margin-top: 18px">
    <div class="build-fix-panel-header section-title">
      <div>
        <h2>编译错误 AI 修复</h2>
        <p>{{ statusText }}</p>
      </div>
    </div>

    <div v-if="loading" class="muted build-fix-empty">正在加载修复记录…</div>
    <div v-else-if="!tableRows.length" class="muted build-fix-empty">
      暂无修复记录。编译失败且启用自动修复后，将在此展示修改汇总。
    </div>
    <div v-else class="table-wrap">
      <table class="data-table build-fix-table">
        <thead>
          <tr>
            <th class="col-round">轮次</th>
            <th class="col-repo">仓库</th>
            <th class="col-file">修改文件</th>
            <th class="col-error">相关编译错误</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in tableRows" :key="row.key">
            <td class="col-round">{{ row.attempt }}</td>
            <td class="col-repo">
              <div class="build-fix-repo-name" :title="row.repoTitle">{{ row.repoLabel }}</div>
              <div v-if="row.repoRoot" class="build-fix-repo-path mono" :title="row.repoRoot">{{ row.repoRootShort }}</div>
            </td>
            <td class="col-file">
              <div class="build-fix-file-name mono" :title="row.fileFull">{{ row.fileBase }}</div>
              <div v-if="row.fileDir" class="build-fix-file-dir mono" :title="row.fileFull">{{ row.fileDir }}</div>
            </td>
            <td class="col-error">
              <ul v-if="row.errors.length" class="build-fix-error-list">
                <li v-for="(err, idx) in row.errors" :key="idx">
                  <span class="build-fix-error-loc">{{ err.loc }}</span>
                  <span class="build-fix-error-msg">{{ err.message }}</span>
                </li>
              </ul>
              <span v-else class="muted">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <details v-if="attemptSummaries.length" class="build-fix-details">
      <summary class="muted build-fix-details-summary">查看各轮摘要</summary>
      <div v-for="attempt in attemptSummaries" :key="attempt.attempt" class="build-fix-attempt">
        <div class="build-fix-attempt-head">
          <strong>第 {{ attempt.attempt }} 轮</strong>
          <span :class="attempt.applied ? 'ok-text' : 'err-text'">{{ attempt.applied ? '已写回' : '未成功' }}</span>
        </div>
        <div v-if="attempt.llm_summary" class="muted build-fix-attempt-note">{{ attempt.llm_summary }}</div>
        <div v-if="attempt.error" class="err-text build-fix-attempt-note">{{ attempt.error }}</div>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { api } from '../../api'

const props = defineProps<{
  jobId: string
  job?: Record<string, any>
  visible?: boolean
}>()

const loading = ref(false)
const data = ref<any>({ attempts: [], status: 'idle' })
const pollTimer = ref<number | null>(null)

const attempts = computed(() => data.value?.attempts || [])

const statusText = computed(() => {
  const st = data.value?.status || 'idle'
  const n = attempts.value.length
  const labels: Record<string, string> = { idle: '待命', running: '修复中…', success: '已成功', failed: '失败' }
  return `${labels[st] || st} · 共 ${n} 轮 · ${tableRows.value.length} 个文件`
})

function stripRootLabel(path: string) {
  return (path || '').replace(/^\[(?:build_workdir|target_repo)\]\s*/i, '').trim()
}

function shortenPath(path: string, max = 56) {
  const p = (path || '').replace(/\\/g, '/')
  if (p.length <= max) return p
  const parts = p.split('/')
  const tail = parts.slice(-3).join('/')
  return tail.length < max - 3 ? `…/${tail}` : `…${p.slice(-(max - 1))}`
}

function formatFileDisplay(file: any, filePath: string) {
  const rel = (file.rel_path || stripRootLabel(filePath)).replace(/\\/g, '/')
  const full = (file.path_full || file.abs_path || filePath || rel).replace(/\\/g, '/')
  const parts = rel.split('/').filter(Boolean)
  const base = parts.length ? parts[parts.length - 1] : rel
  const dir = parts.length > 1 ? parts.slice(0, -1).join('/') : ''
  return { rel, full, base, dir }
}

function lookupRepoFromJob(job: Record<string, any> | undefined, filePath: string, absPath: string) {
  const registry = job?.options?.repo_project_registry
  if (!registry || typeof registry !== 'object') return null
  const path = (absPath || filePath || '').replace(/^\[(?:build_workdir|target_repo)\]\s*/i, '').replace(/\\/g, '/').replace(/\/+$/, '')
  if (!path) return null
  let best: any = null
  let bestLen = -1
  for (const info of Object.values(registry) as any[]) {
    if (!info || typeof info !== 'object') continue
    const root = String(info.repo_root || '').replace(/\\/g, '/').replace(/\/+$/, '')
    const checkout = String(info.repo_checkout || '').replace(/\\/g, '/').replace(/^\/+/, '').replace(/\/+$/, '')
    let matched = false
    let len = 0
    if (root && (path === root || path.startsWith(root + '/'))) {
      matched = true
      len = root.length
    } else if (checkout && (path === checkout || path.startsWith(checkout + '/') || path.includes('/' + checkout + '/'))) {
      matched = true
      len = checkout.length
    }
    if (matched && len > bestLen) {
      bestLen = len
      best = info
    }
  }
  return best
}

function rootFallbackLabel(root: string) {
  if (root === 'target_repo') return '合入目标仓库'
  if (root === 'build_workdir') return '编译工作区'
  return root || '未知'
}

function errorsForFile(attempt: any, file: any, filePath: string) {
  const norm = stripRootLabel(filePath).replace(/\\/g, '/')
  const abs = (file.abs_path || '').replace(/\\/g, '/')
  const hits = (attempt.errors || []).filter((e: any) => {
    const ef = (e.file || '').replace(/\\/g, '/')
    if (!ef) return false
    return (
      norm.endsWith(ef)
      || ef.endsWith(norm)
      || norm.includes(ef)
      || (abs && (abs.endsWith(ef) || ef.endsWith(abs) || abs.includes(ef)))
    )
  })
  const seen = new Set<string>()
  const out: { loc: string; message: string }[] = []
  for (const e of hits) {
    const loc = `${e.file || '?'}:${e.line || '?'}`
    const message = (e.message || '').trim()
    const key = `${loc}|${message}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push({ loc, message })
    if (out.length >= 4) break
  }
  return out
}

const tableRows = computed(() => {
  const rows: any[] = []
  const seen = new Set<string>()
  for (const attempt of attempts.value) {
    for (const file of attempt.files_changed || []) {
      const key = `${attempt.attempt}:${file.abs_path || file.path}`
      if (!key || seen.has(key)) continue
      seen.add(key)
      const filePath = stripRootLabel(file.path || file.abs_path || '')
      const fileDisplay = formatFileDisplay(file, filePath)
      const saved = lookupRepoFromJob(props.job, file.path || filePath, file.abs_path || '')
      const repoProject = file.repo_project || saved?.repo_project || ''
      const repoCheckout = file.repo_checkout || saved?.repo_checkout || ''
      const repoRoot = file.repo_root || saved?.repo_root || file.repo_manifest_root || saved?.repo_manifest_root || ''
      const repoLabel = repoProject || (repoCheckout ? repoCheckout.replace(/\\/g, '/').split('/').pop() : '') || rootFallbackLabel(file.root)
      const repoTitle = repoProject
        ? [repoProject, repoCheckout && `checkout: ${repoCheckout}`, repoRoot].filter(Boolean).join('\n')
        : repoRoot || rootFallbackLabel(file.root)
      rows.push({
        key,
        attempt: attempt.attempt,
        repoLabel,
        repoTitle,
        repoRoot,
        repoRootShort: repoRoot ? shortenPath(repoRoot, 48) : '',
        filePath: fileDisplay.rel,
        fileFull: fileDisplay.full,
        fileBase: fileDisplay.base,
        fileDir: fileDisplay.dir,
        errors: errorsForFile(attempt, file, file.path || filePath),
      })
    }
  }
  return rows.sort((a, b) => a.attempt - b.attempt || a.filePath.localeCompare(b.filePath))
})

const attemptSummaries = computed(() =>
  attempts.value.map((a: any) => ({
    attempt: a.attempt,
    applied: a.applied,
    llm_summary: a.llm_summary,
    error: a.error,
  })),
)

async function loadPanel() {
  if (!props.jobId || !props.visible) return
  loading.value = !attempts.value.length
  try {
    const resp = await api.get<any>(`/api/upgrade/jobs/${props.jobId}/build-fixes`)
    data.value = resp
    if (resp.status === 'running') startPoll()
    else stopPoll()
  } catch (err: any) {
    data.value = { attempts: [], status: 'failed', error: err.message }
  } finally {
    loading.value = false
  }
}

function startPoll() {
  if (pollTimer.value) return
  pollTimer.value = window.setInterval(loadPanel, 3000)
}

function stopPoll() {
  if (pollTimer.value) {
    clearInterval(pollTimer.value)
    pollTimer.value = null
  }
}

watch(
  () => [props.jobId, props.visible],
  () => loadPanel(),
  { immediate: true },
)

onBeforeUnmount(stopPoll)

defineExpose({ reload: loadPanel })
</script>

<style scoped>
.build-fix-empty {
  padding: 10px 0;
  font-size: 12px;
}

.build-fix-table {
  font-size: 12px;
  table-layout: fixed;
  width: 100%;
}

.build-fix-table th,
.build-fix-table td {
  vertical-align: top;
  padding: 8px 10px;
}

.col-round {
  width: 52px;
}

.col-repo {
  width: 22%;
}

.col-file {
  width: 34%;
  min-width: 180px;
}

.build-fix-file-name {
  font-weight: 600;
  color: #1e293b;
  word-break: break-all;
  line-height: 1.35;
}

.build-fix-file-dir {
  margin-top: 3px;
  font-size: 11px;
  color: #64748b;
  word-break: break-all;
  line-height: 1.35;
}

.col-error {
  width: auto;
}

.build-fix-repo-name {
  font-weight: 700;
  color: #1e293b;
  word-break: break-word;
}

.build-fix-repo-path {
  margin-top: 3px;
  font-size: 11px;
  color: #64748b;
  word-break: break-all;
}

.build-fix-error-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 6px;
}

.build-fix-error-list li {
  padding: 6px 8px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #fafbfc;
}

.build-fix-error-loc {
  display: block;
  margin-bottom: 2px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  color: #475569;
}

.build-fix-error-msg {
  display: block;
  font-size: 11px;
  line-height: 1.45;
  color: #334155;
  word-break: break-word;
}

.build-fix-details {
  margin-top: 12px;
}

.build-fix-details-summary {
  cursor: pointer;
  font-size: 12px;
}

.build-fix-attempt {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px dashed #e2e8f0;
}

.build-fix-attempt-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 4px;
}

.build-fix-attempt-note {
  font-size: 12px;
}

.ok-text {
  color: #16a34a;
  font-weight: 600;
}

.err-text {
  color: #dc2626;
}

.table-wrap {
  overflow-x: auto;
}
</style>
