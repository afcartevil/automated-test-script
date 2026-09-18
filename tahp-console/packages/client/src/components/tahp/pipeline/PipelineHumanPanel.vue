<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useMessage } from 'naive-ui'
import type { TimelineNode } from '@/api/tahp/adapt-pipeline'
import PipelineResumePicker from './PipelineResumePicker.vue'
import type { useAdaptPipelineStore } from '@/stores/tahp/adapt-pipeline'

const props = defineProps<{
  runId: string
  nodes: TimelineNode[]
  store: ReturnType<typeof useAdaptPipelineStore>
}>()

const message = useMessage()
const resumeLoading = ref(false)

interface RepoGroup {
  repo: string
  repo_label: string
  files: string[]
  domain_ids: string[]
}

const waitingNodes = computed(() =>
  props.nodes.filter(n => n.status === 'waiting_human' && n.human),
)

function needsResumePicker(node: TimelineNode): boolean {
  return node.key === 'human_review' || node.human?.reason === 'stage_failed'
}

const selectedRepos = ref<string[]>([])

type GerritPending =
  | { kind: 'submit'; nodeKey: string; actionId: 'submit_all_repos' | 'submit_selected_repos' }
  | { kind: 'skip'; nodeKey: string }

const gerritPending = ref<GerritPending | null>(null)

watch(
  waitingNodes,
  (nodes) => {
    const gerrit = nodes.find(n => n.key === 'gerrit' && n.human?.reason === 'select_repos')
    const repos = (gerrit?.progress?.repos ?? []) as RepoGroup[]
    if (repos.length && !selectedRepos.value.length) {
      selectedRepos.value = repos.map(r => r.repo)
    }
    if (gerritPending.value && !nodes.some(n => n.key === gerritPending.value?.nodeKey)) {
      gerritPending.value = null
    }
  },
  { immediate: true },
)

watch(
  () => props.runId,
  () => {
    selectedRepos.value = []
    gerritPending.value = null
  },
)

async function ensureResumePointsLoaded() {
  if (waitingNodes.value.some(needsResumePicker)) {
    await props.store.loadResumePoints(props.runId)
  }
}

onMounted(() => {
  void ensureResumePointsLoaded()
})

watch(waitingNodes, () => {
  void ensureResumePointsLoaded()
})

function reposFor(node: TimelineNode): RepoGroup[] {
  return (node.progress?.repos ?? []) as RepoGroup[]
}

function toggleRepo(repo: string, checked: boolean) {
  if (checked) {
    if (!selectedRepos.value.includes(repo)) selectedRepos.value = [...selectedRepos.value, repo]
  } else {
    selectedRepos.value = selectedRepos.value.filter(r => r !== repo)
  }
}

function selectAllRepos(node: TimelineNode) {
  selectedRepos.value = reposFor(node).map(r => r.repo)
}

function clearRepos() {
  selectedRepos.value = []
}

function visibleActions(node: TimelineNode) {
  const actions = node.human?.actions ?? []
  return actions.filter(action => {
    if (action.id === 'abort' || action.label === '终止流水线') return false
    if (action.id === 'confirm_done' && needsResumePicker(node)) return false
    return true
  })
}

function humanMessage(node: TimelineNode): string {
  return String(node.human?.message ?? '')
    .replace(/请选择恢复点继续，或终止流水线。/g, '请在下方选择恢复点继续。')
    .replace(/通过后可选择恢复点继续/g, '通过后请在下方选择恢复点继续')
}

function fileLabel(path: string): string {
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean)
  if (parts.length <= 2) return parts.join('/') || path
  return parts.slice(-2).join('/')
}

function isPendingFor(node: TimelineNode, kind?: GerritPending['kind']): boolean {
  if (!gerritPending.value || gerritPending.value.nodeKey !== node.key) return false
  return kind ? gerritPending.value.kind === kind : true
}

function previewRepos(node: TimelineNode): RepoGroup[] {
  const all = reposFor(node)
  if (gerritPending.value?.kind === 'submit' && gerritPending.value.actionId === 'submit_selected_repos') {
    return all.filter(r => selectedRepos.value.includes(r.repo))
  }
  return all
}

function previewSummary(node: TimelineNode): string {
  const groups = previewRepos(node)
  const files = groups.reduce((n, g) => n + g.files.length, 0)
  return `${groups.length} 个仓库 · ${files} 个文件`
}

async function dispatchAction(nodeKey: string, actionId: string) {
  if (nodeKey === 'gerrit' && actionId === 'submit_selected_repos') {
    await props.store.submitHumanAction(props.runId, nodeKey, actionId, {
      selected_repos: selectedRepos.value,
    })
    return
  }
  await props.store.submitHumanAction(props.runId, nodeKey, actionId)
}

async function onAction(nodeKey: string, actionId: string) {
  if (nodeKey === 'gerrit' && (actionId === 'submit_all_repos' || actionId === 'submit_selected_repos')) {
    gerritPending.value = { kind: 'submit', nodeKey, actionId }
    return
  }
  if (nodeKey === 'gerrit' && actionId === 'skip') {
    gerritPending.value = { kind: 'skip', nodeKey }
    return
  }
  await dispatchAction(nodeKey, actionId)
}

async function confirmGerritPending(node: TimelineNode) {
  const pending = gerritPending.value
  if (!pending || pending.nodeKey !== node.key) return
  const actionId = pending.kind === 'skip' ? 'skip' : pending.actionId
  gerritPending.value = null
  await dispatchAction(pending.nodeKey, actionId)
}

function cancelGerritPending() {
  gerritPending.value = null
}

async function onResume(
  node: string,
  scope: 'continue' | 'restart',
  force: boolean,
  deviceId?: string,
) {
  await props.store.resumeRun(props.runId, node, scope, force, deviceId)
}

async function handleReloadResume() {
  if (resumeLoading.value) return
  resumeLoading.value = true
  try {
    await props.store.loadResumePoints(props.runId)
    message.success('恢复点已刷新')
  } catch (err) {
    message.error((err as Error).message || '刷新恢复点失败')
  } finally {
    resumeLoading.value = false
  }
}

const currentDeviceId = computed(() => props.store.selectedTimeline?.device_id ?? null)
</script>

<template>
  <div class="human-panel">
    <h3>人工介入</h3>
    <p v-if="waitingNodes.length === 0" class="empty">当前无需人工介入</p>
    <div v-for="node in waitingNodes" :key="node.key" class="task">
      <strong>⚠ {{ node.label }}</strong>
      <p>{{ humanMessage(node) }}</p>

      <div v-if="node.key === 'gerrit' && node.human?.reason === 'select_repos'" class="repo-box">
        <div class="repo-toolbar">
          <button type="button" class="btn-soft" :disabled="isPendingFor(node)" @click="selectAllRepos(node)">全选</button>
          <button type="button" class="btn-soft" :disabled="isPendingFor(node)" @click="clearRepos">清空</button>
          <span class="hint">已选 {{ selectedRepos.length }} / {{ reposFor(node).length }}</span>
        </div>
        <label v-for="r in reposFor(node)" :key="r.repo" class="repo-row">
          <input
            type="checkbox"
            :checked="selectedRepos.includes(r.repo)"
            :disabled="isPendingFor(node)"
            @change="toggleRepo(r.repo, ($event.target as HTMLInputElement).checked)"
          >
          <span class="repo-main">
            <strong class="repo-label">{{ r.repo_label }}</strong>
            <span class="repo-path" :title="r.repo">{{ r.repo }}</span>
            <span class="meta">{{ r.files.length }} 文件 · 域 {{ r.domain_ids.join(', ') || '—' }}</span>
            <ul v-if="r.files.length" class="file-list">
              <li v-for="f in r.files" :key="f" :title="f">{{ fileLabel(f) }}</li>
            </ul>
          </span>
        </label>
        <p v-if="!reposFor(node).length" class="hint">暂无按仓库分组的变更（请确认适配阶段返回了文件绝对路径）</p>
      </div>

      <div v-if="isPendingFor(node, 'submit')" class="confirm-box">
        <strong>确认提交到 Gerrit？</strong>
        <p>将按仓合提 {{ previewSummary(node) }}。同一仓内多域改动合并为一张 CR。</p>
        <div v-for="r in previewRepos(node)" :key="r.repo" class="preview-repo">
          <strong>{{ r.repo_label }}</strong>
          <span class="meta">{{ r.files.length }} 文件 · 域 {{ r.domain_ids.join(', ') || '—' }}</span>
          <ul class="file-list">
            <li v-for="f in r.files" :key="f" :title="f">{{ fileLabel(f) }}</li>
          </ul>
        </div>
        <p v-if="!previewRepos(node).length" class="hint">当前没有可提交的文件</p>
        <div class="actions">
          <button type="button" class="btn-soft" :disabled="store.actionBusy" @click="cancelGerritPending">返回修改</button>
          <button
            type="button"
            class="btn-soft"
            :disabled="store.actionBusy || !previewRepos(node).length"
            @click="confirmGerritPending(node)"
          >确认提交</button>
        </div>
      </div>
      <div v-else-if="isPendingFor(node, 'skip')" class="confirm-box confirm-skip">
        <strong>确认跳过 Gerrit 提交？</strong>
        <p>本次运行将不入库。工作区里的适配改动仍会保留。</p>
        <div class="actions">
          <button type="button" class="btn-soft" :disabled="store.actionBusy" @click="cancelGerritPending">取消</button>
          <button type="button" class="btn-danger" :disabled="store.actionBusy" @click="confirmGerritPending(node)">确认跳过</button>
        </div>
      </div>
      <div v-else-if="visibleActions(node).length" class="actions">
        <button
          v-for="action in visibleActions(node)"
          :key="action.id"
          type="button"
          :class="action.danger ? 'btn-danger' : 'btn-soft'"
          :disabled="store.actionBusy || (action.id === 'submit_selected_repos' && !selectedRepos.length)"
          @click="onAction(node.key, action.id)"
        >
          {{ action.label }}
        </button>
      </div>
      <PipelineResumePicker
        v-if="needsResumePicker(node)"
        :data="store.resumePoints"
        :busy="store.actionBusy"
        :reloading="resumeLoading"
        :current-device-id="currentDeviceId"
        @reload="handleReloadResume"
        @submit="onResume"
      />
    </div>
  </div>
</template>

<style scoped lang="scss">
.human-panel {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.human-panel h3 {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--faint);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.task {
  border-radius: 12px;
  border: 1px solid var(--line);
  border-left: 3px solid var(--warn);
  background: var(--surface);
  padding: 12px;
  margin-bottom: 10px;
  min-width: 0;
  overflow-wrap: anywhere;
}
.task p {
  margin: 6px 0 10px;
  color: var(--text);
  line-height: 1.45;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.actions {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.repo-box {
  margin: 0 0 12px;
  padding: 10px;
  border-radius: 10px;
  background: var(--bg);
  border: 1px solid var(--line);
  min-width: 0;
  max-width: 100%;
  overflow: hidden;
}
.repo-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.repo-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 6px 0;
  border-bottom: 1px solid var(--line);
  cursor: pointer;
  min-width: 0;
  input { margin-top: 3px; flex-shrink: 0; }
}
.repo-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
  .repo-label {
    font-size: 13px;
    overflow-wrap: anywhere;
    word-break: break-word;
  }
  .repo-path {
    font-size: 11.5px;
    color: var(--muted);
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    overflow-wrap: anywhere;
    word-break: break-all;
    line-height: 1.35;
  }
  .meta { font-size: 12px; color: var(--muted); }
}
.file-list {
  margin: 4px 0 0;
  padding: 0;
  max-height: 140px;
  overflow: auto;
  list-style: none;
  li {
    font-size: 12px;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    color: var(--muted);
    overflow-wrap: anywhere;
    word-break: break-all;
    line-height: 1.4;
  }
}
.confirm-box {
  margin: 0 0 12px;
  padding: 10px;
  border-radius: 10px;
  background: var(--bg);
  border: 1px solid var(--line);
  strong { display: block; margin-bottom: 4px; }
  p { margin: 0 0 8px; }
  .actions { margin-bottom: 0; }
}
.confirm-skip {
  border-color: color-mix(in srgb, var(--err) 40%, var(--line));
}
.preview-repo {
  margin: 8px 0;
  min-width: 0;
  strong { font-size: 13px; }
  .meta { display: block; font-size: 12px; color: var(--muted); }
}
.hint { font-size: 12px; color: var(--muted); margin: 0; }
.empty { color: var(--faint); margin: 0; font-size: 13px; }
.btn-soft, .btn-danger {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 6px 12px;
  background: var(--bg);
  cursor: pointer;
  font-size: 13px;
}
.btn-danger {
  border-color: color-mix(in srgb, var(--err) 40%, var(--line));
  color: var(--err);
}
</style>
