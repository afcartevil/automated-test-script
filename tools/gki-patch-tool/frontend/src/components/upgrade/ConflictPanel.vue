<template>
  <div v-if="visible" class="conflict-panel">
    <div class="conflict-panel-header">
      <span class="conflict-panel-title">
        冲突合入 ({{ items.length }} 个文件{{ autoResolve ? ' · 自动处理' : '' }})
      </span>
      <div class="conflict-batch-bar">
        <label>
          <input type="checkbox" :checked="allSelected" @change="toggleSelectAll(($event.target as HTMLInputElement).checked)" />
          全选
        </label>
        <button class="btn btn-sm" @click="batchResolve(false)">批量 AI</button>
        <button class="btn primary btn-sm" @click="batchApply">批量写回</button>
        <button class="btn btn-sm btn-accent" @click="batchResolveAndApply">一键 AI+写回</button>
      </div>
      <span class="conflict-ai-status" :style="{ color: aiStatusColor }">{{ aiStatusText }}</span>
    </div>

    <div v-if="loading" class="conflict-panel-loading">正在加载冲突详情与 AI 建议…</div>
    <div v-else-if="!items.length" class="conflict-panel-loading">无冲突文件详情</div>
    <div v-else class="conflict-panel-body">
      <div class="conflict-file-list" tabindex="0">
        <div class="conflict-file-list-head">
          <span class="conflict-file-badge">📄</span>
          <span class="conflict-file-list-summary">已选 {{ selectedCount }}/{{ pendingCount }}</span>
        </div>
        <div
          v-for="item in items"
          :key="item.conflict_path"
          class="conflict-file-item"
          :class="{ active: item.conflict_path === selectedPath, applied: item.applied }"
          :title="item.source_path || item.conflict_path"
          @click="selectFile(item.conflict_path)"
        >
          <input
            v-if="!item.applied"
            type="checkbox"
            :checked="checkedPaths.has(item.conflict_path)"
            @click.stop
            @change="toggleCheck(item.conflict_path, ($event.target as HTMLInputElement).checked)"
          />
          <span class="conflict-file-badge">{{ fileBadge(item) }}</span>
          <span class="conflict-file-label">
            <code>{{ item.source_path || item.conflict_path }}</code>
          </span>
        </div>
      </div>

      <div v-if="selectedItem" class="conflict-detail">
        <div>
          <strong>{{ selectedItem.source_path || selectedItem.conflict_path }}</strong>
          <span class="muted" style="margin-left: 8px; font-size: 11px">
            {{ selectedItem.summary || selectedItem.error || selectedItem.status || '' }}
          </span>
        </div>
        <div class="conflict-diff-title">冲突对比（Gerrit 风格 · 左合入前 / 右合入后）</div>

        <div v-if="!regions.length" class="conflict-compare-empty">
          {{ selectedItem.rej_content ? '未能解析冲突片段。' : '等待 AI 处理或暂无 .rej 片段。' }}
        </div>
        <template v-else>
          <div class="conflict-diff-legend">
            <span class="lg-del"><i></i>删除</span>
            <span class="lg-add"><i></i>新增</span>
            <span class="lg-chg"><i></i>修改</span>
          </div>
          <div class="conflict-compare">
            <div v-for="(region, idx) in regions" :key="idx" class="conflict-region">
              <div class="conflict-region-header">
                冲突 {{ region.index ?? idx + 1 }} · 约第 {{ region.start_line }}–{{ region.end_line }} 行
              </div>
              <GerritDiffView
                :rows="regionRows(region)"
                :has-merged="!!(region.merged && region.merged.trim())"
              />
            </div>
          </div>
        </template>

        <div class="conflict-rej-section">
          <div class="conflict-rej-label">{{ editorLabel }}</div>
          <textarea v-model="editorText" class="conflict-rej-editor" spellcheck="false"></textarea>
        </div>
        <div class="conflict-actions">
          <button class="btn btn-sm" @click="batchResolve(true)">重新 AI（选中）</button>
          <button class="btn primary btn-sm" @click="applyOne">写回此文件</button>
        </div>
        <p class="conflict-hint">写回后请点击「冲突已解决，继续」进入提交/编译。</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { api } from '../../api'
import { buildGerritDiffRowsFallback, remoteSshBody } from '../../utils/upgrade'
import GerritDiffView from './GerritDiffView.vue'

const props = defineProps<{
  jobId: string
  job?: Record<string, any>
  visible?: boolean
  autoResolve?: boolean
}>()

const emit = defineEmits<{ refresh: [] }>()

const loading = ref(false)
const state = ref<any>(null)
const selectedPath = ref('')
const checkedPaths = ref(new Set<string>())
const editorDrafts = ref<Record<string, string>>({})
const pollTimer = ref<number | null>(null)

const items = computed(() => state.value?.items || [])
const selectedItem = computed(() => items.value.find((i: any) => i.conflict_path === selectedPath.value) || items.value[0])
const pendingCount = computed(() => items.value.filter((i: any) => !i.applied).length)
const selectedCount = computed(() => checkedPaths.value.size)
const allSelected = computed(() => pendingCount.value > 0 && selectedCount.value === pendingCount.value)
const autoResolve = computed(() => props.autoResolve || state.value?.auto_resolve_conflicts)

const aiStatusText = computed(() => {
  const st = state.value?.ai_status || 'idle'
  const msg = state.value?.ai_message || ''
  if (st === 'running' || st === 'applying') return msg || (st === 'applying' ? '写回工作区…' : 'AI 处理中…')
  if (st === 'failed') return msg || 'AI 处理失败'
  if (st === 'done') return msg || 'AI 处理完成'
  return msg || st
})

const aiStatusColor = computed(() => {
  const st = state.value?.ai_status || 'idle'
  if (st === 'running' || st === 'applying') return '#2563eb'
  if (st === 'failed') return '#dc2626'
  if (st === 'done') return '#16a34a'
  return '#64748b'
})

const regions = computed(() => selectedItem.value?.conflict_regions || [])

const editorLabel = computed(() =>
  selectedItem.value?.kind === 'markers' ? '冲突合并结果（可编辑）' : '冲突 patch（.rej 内容，可编辑后写回）',
)

const editorText = computed({
  get() {
    const path = selectedItem.value?.conflict_path
    if (!path) return ''
    if (Object.prototype.hasOwnProperty.call(editorDrafts.value, path)) {
      return editorDrafts.value[path]
    }
    const sel = selectedItem.value
    if (sel?.kind === 'markers') return sel.proposed || sel.original || ''
    return sel?.rej_content || ''
  },
  set(value: string) {
    const path = selectedItem.value?.conflict_path
    if (path) editorDrafts.value[path] = value
  },
})

function fileBadge(item: any) {
  if (item.applied) return '✓'
  if (item.strategy === 'to_tag') return '📌'
  if (item.status === 'ai_done' || item.status === 'edited') return '🤖'
  if (item.status === 'failed') return '✗'
  return '…'
}

function regionRows(region: any) {
  if (region.diff_rows?.length) return region.diff_rows
  return buildGerritDiffRowsFallback(region.vendor, region.merged || region.gki || '')
}

function selectFile(path: string) {
  if (selectedItem.value?.conflict_path) {
    editorDrafts.value[selectedItem.value.conflict_path] = editorText.value
  }
  selectedPath.value = path
}

function toggleCheck(path: string, checked: boolean) {
  const next = new Set(checkedPaths.value)
  if (checked) next.add(path)
  else next.delete(path)
  checkedPaths.value = next
}

function toggleSelectAll(checked: boolean) {
  if (checked) {
    checkedPaths.value = new Set(items.value.filter((i: any) => !i.applied).map((i: any) => i.conflict_path))
  } else {
    checkedPaths.value = new Set()
  }
}

function getSelectedPaths() {
  return [...checkedPaths.value]
}

async function saveEditor(path?: string) {
  const sel = selectedItem.value
  const conflictPath = path || sel?.conflict_path
  if (!conflictPath || !sel) return
  const body: Record<string, unknown> = { conflict_path: conflictPath }
  const text = editorDrafts.value[conflictPath] ?? editorText.value
  if (sel.kind === 'markers') body.content = text
  else body.rej_content = text
  Object.assign(body, await remoteSshBody(props.job))
  await api.put(`/api/upgrade/jobs/${props.jobId}/conflicts/content`, body)
}

async function loadPanel() {
  if (!props.jobId || !props.visible) return
  loading.value = true
  try {
    const data = await api.get<any>(`/api/upgrade/jobs/${props.jobId}/conflicts`)
    state.value = data
    if (!selectedPath.value || !data.items?.find((i: any) => i.conflict_path === selectedPath.value)) {
      selectedPath.value = data.items?.[0]?.conflict_path || ''
    }
    for (const item of data.items || []) {
      if (!item.applied && !checkedPaths.value.has(item.conflict_path) && checkedPaths.value.size === 0) {
        // keep existing selection
      }
    }
    const st = data.ai_status
    if (st === 'running' || st === 'applying' || (data.auto_resolve_conflicts && props.job?.status === 'conflicts')) {
      startPoll()
    } else {
      stopPoll()
    }
  } catch (err: any) {
    state.value = { items: [], ai_message: err.message }
  } finally {
    loading.value = false
  }
}

function startPoll() {
  if (pollTimer.value) return
  pollTimer.value = window.setInterval(() => {
    loadPanel()
    emit('refresh')
  }, 3000)
}

function stopPoll() {
  if (pollTimer.value) {
    clearInterval(pollTimer.value)
    pollTimer.value = null
  }
}

async function batchResolve(force: boolean) {
  const paths = getSelectedPaths()
  if (!paths.length) {
    alert('请先勾选要处理的冲突文件')
    return
  }
  try {
    const body: Record<string, unknown> = { paths, ...(await remoteSshBody(props.job)) }
    if (force) body.force = true
    await api.post(`/api/upgrade/jobs/${props.jobId}/conflicts/resolve`, body)
    await loadPanel()
    startPoll()
  } catch (err: any) {
    alert(`批量 AI 失败: ${err.message}`)
  }
}

async function batchApply() {
  const paths = getSelectedPaths().filter((p) => {
    const it = items.value.find((i: any) => i.conflict_path === p)
    return it && it.proposed && !it.applied
  })
  if (!paths.length) {
    alert('所选文件中没有可写回的（需先有 AI 建议或手动编辑内容）')
    return
  }
  if (!confirm(`确认写回 ${paths.length} 个文件到工作区？`)) return
  try {
    await saveEditor()
    const body = { paths, ...(await remoteSshBody(props.job)) }
    const resp = await api.post<any>(`/api/upgrade/jobs/${props.jobId}/conflicts/apply`, body)
    await loadPanel()
    emit('refresh')
    alert(`已写回 ${resp.applied_count || 0} 个文件`)
  } catch (err: any) {
    alert(`批量写回失败: ${err.message}`)
  }
}

async function batchResolveAndApply() {
  const paths = getSelectedPaths()
  if (!paths.length) {
    alert('请先勾选要处理的冲突文件')
    return
  }
  const pending = paths.filter((p) => {
    const it = items.value.find((i: any) => i.conflict_path === p)
    return it && !it.applied && (!it.proposed || it.status === 'pending' || it.status === 'failed')
  })
  const msg = pending.length
    ? `将对 ${paths.length} 个文件执行：AI 合入 → 自动写回（${pending.length} 个待 AI）`
    : `将对 ${paths.length} 个已有建议的文件直接写回`
  if (!confirm(`${msg}，继续？`)) return
  try {
    await saveEditor()
    const body = { paths, auto_apply: true, ...(await remoteSshBody(props.job)) }
    await api.post(`/api/upgrade/jobs/${props.jobId}/conflicts/resolve`, body)
    await loadPanel()
    startPoll()
  } catch (err: any) {
    alert(`一键处理失败: ${err.message}`)
  }
}

async function applyOne() {
  const path = selectedItem.value?.conflict_path
  if (!path) return
  try {
    await saveEditor(path)
    const body = { paths: [path], ...(await remoteSshBody(props.job)) }
    await api.post(`/api/upgrade/jobs/${props.jobId}/conflicts/apply`, body)
    await loadPanel()
    emit('refresh')
    alert(`已写回: ${path}`)
  } catch (err: any) {
    alert(`写回失败: ${err.message}`)
  }
}

watch(
  () => [props.jobId, props.visible],
  () => {
    checkedPaths.value = new Set()
    editorDrafts.value = {}
    loadPanel()
  },
  { immediate: true },
)

onBeforeUnmount(stopPoll)

defineExpose({ reload: loadPanel })
</script>

<style scoped>
.conflict-panel-title { font-weight: 600; font-size: 13px; }
.conflict-ai-status { font-size: 12px; }
.conflict-panel-loading { padding: 12px; font-size: 12px; color: var(--muted); }
.conflict-diff-title { font-size: 12px; font-weight: 600; color: #334155; }
.conflict-hint { font-size: 11px; color: var(--muted); margin: 0; }
.btn-accent { background: var(--primary); color: #fff; border: 1px solid var(--primary); }
.btn-accent:hover { background: var(--primary-strong); }
</style>
