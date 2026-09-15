<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { TimelineNode } from '@/api/tahp/adapt-pipeline'
import PipelineResumePicker from './PipelineResumePicker.vue'
import type { useAdaptPipelineStore } from '@/stores/tahp/adapt-pipeline'

const props = defineProps<{
  runId: string
  nodes: TimelineNode[]
  store: ReturnType<typeof useAdaptPipelineStore>
}>()

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

watch(
  waitingNodes,
  (nodes) => {
    const gerrit = nodes.find(n => n.key === 'gerrit' && n.human?.reason === 'select_repos')
    const repos = (gerrit?.progress?.repos ?? []) as RepoGroup[]
    if (repos.length && !selectedRepos.value.length) {
      selectedRepos.value = repos.map(r => r.repo)
    }
  },
  { immediate: true },
)

watch(
  () => props.runId,
  () => { selectedRepos.value = [] },
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

async function onAction(nodeKey: string, actionId: string) {
  if (nodeKey === 'gerrit' && actionId === 'submit_selected_repos') {
    await props.store.submitHumanAction(props.runId, nodeKey, actionId, {
      selected_repos: selectedRepos.value,
    })
    return
  }
  await props.store.submitHumanAction(props.runId, nodeKey, actionId)
}

async function onResume(
  node: string,
  scope: 'continue' | 'restart',
  force: boolean,
  deviceId?: string,
) {
  await props.store.resumeRun(props.runId, node, scope, force, deviceId)
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
          <button type="button" class="btn-soft" @click="selectAllRepos(node)">全选</button>
          <button type="button" class="btn-soft" @click="clearRepos">清空</button>
          <span class="hint">已选 {{ selectedRepos.length }} / {{ reposFor(node).length }}</span>
        </div>
        <label v-for="r in reposFor(node)" :key="r.repo" class="repo-row">
          <input
            type="checkbox"
            :checked="selectedRepos.includes(r.repo)"
            @change="toggleRepo(r.repo, ($event.target as HTMLInputElement).checked)"
          >
          <span class="repo-main">
            <strong class="repo-label">{{ r.repo_label }}</strong>
            <span class="repo-path" :title="r.repo">{{ r.repo }}</span>
            <span class="meta">{{ r.files.length }} 文件 · 域 {{ r.domain_ids.join(', ') || '—' }}</span>
          </span>
        </label>
        <p v-if="!reposFor(node).length" class="hint">暂无按仓库分组的变更（请确认适配阶段返回了文件绝对路径）</p>
      </div>

      <div v-if="visibleActions(node).length" class="actions">
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
        :current-device-id="currentDeviceId"
        @reload="store.loadResumePoints(runId)"
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
