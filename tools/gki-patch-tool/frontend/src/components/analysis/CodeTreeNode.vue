<template>
  <div v-if="node">
    <template v-if="node.type === 'dir' && node.children?.length">
      <div
        class="code-tree-row"
        :style="{ paddingLeft: `${depth * 14}px` }"
        @click="expanded = !expanded"
      >
        <span class="code-tree-toggle">{{ expanded ? '▼' : '▶' }}</span>
        <span class="code-tree-dir">📁 {{ node.name }}</span>
        <span class="code-tree-count">({{ node.patch_count || 0 }})</span>
      </div>
      <div v-show="expanded">
        <CodeTreeNode
          v-for="(child, index) in node.children"
          :key="`${child.path || child.name}-${index}`"
          :node="child"
          :depth="depth + 1"
        />
      </div>
    </template>

    <div v-else-if="isFileNode" class="code-tree-node code-tree-file-node">
      <div
        class="code-tree-row code-tree-file-row clickable"
        :style="{ paddingLeft: `${depth * 14}px` }"
        @mouseenter="onFileHover"
        @mouseleave="onFileLeave"
        @click.stop="toggleFileDetail"
      >
        <span class="code-tree-toggle">{{ fileOpen ? '▼' : '▶' }}</span>
        <span class="code-tree-file">📄 {{ node.name }}</span>
        <span class="code-tree-count">({{ node.patch_count || 0 }})</span>
      </div>
      <div v-if="fileOpen" class="code-tree-file-detail">
        <div v-if="fileLoading" class="code-tree-loading">加载 diff…</div>
        <div v-else-if="fileError" class="code-tree-empty">{{ fileError }}</div>
        <div v-else-if="!fileBlocks.length" class="code-tree-empty">无关联 patch</div>
        <div
          v-for="block in fileBlocks"
          :key="block.patch.full_sha || block.patch.sha"
          class="code-tree-patch-block"
          @mouseenter="(e) => onPatchHover(block.patch, e)"
          @mouseleave="onFileLeave"
        >
          <div class="code-tree-patch-head">
            <span class="pill" :class="block.patch.llm_analyzed ? 'llm-badge' : 'script-badge'">
              {{ block.patch.llm_analyzed ? 'LLM' : '脚本' }}
            </span>
            <button type="button" class="sha-link" @click.stop="jumpToPatch(block.patch)">
              {{ shortId(block.patch.sha || block.patch.full_sha, 12) }}
            </button>
            <span class="patch-head-title">{{ (block.patch.title || '').slice(0, 80) }}</span>
            <span class="patch-head-score">{{ formatPatchScore(block.patch.score) }}</span>
            <span v-if="block.patch.crash_risk" class="patch-head-crash">死机 {{ block.patch.crash_risk }}</span>
          </div>
          <div
            v-if="block.patch.key_risk"
            class="patch-head-risk"
            :class="keyRiskTone(block.patch.key_risk) === 'none' ? 'patch-head-risk-none' : 'patch-head-risk-warn'"
          >
            {{ formatKeyRiskLabel(block.patch.key_risk) }}
          </div>
          <pre v-if="block.diffHtml" class="code-tree-diff" v-html="block.diffHtml"></pre>
          <div v-else-if="block.diffNote" class="code-tree-empty">{{ block.diffNote }}</div>
        </div>
      </div>
    </div>

    <template v-else-if="node.name === '/'">
      <CodeTreeNode
        v-for="(child, index) in node.children || []"
        :key="`${child.path || child.name}-${index}`"
        :node="child"
        :depth="0"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { api, shortId } from '../../api'
import { usePatchPopover, type PatchBrief } from '../../composables/usePatchPopover'
import { colorizeDiff, formatKeyRiskLabel, formatPatchScore, keyRiskTone } from '../../utils/analysisDisplay'

const props = withDefaults(
  defineProps<{
    node: any
    depth?: number
  }>(),
  { depth: 0 },
)

const expanded = ref(props.depth < 1)
const fileOpen = ref(false)
const fileLoading = ref(false)
const fileError = ref('')
const fileBlocks = ref<
  Array<{ patch: PatchBrief; diffHtml: string; diffNote: string }>
>([])

const { showPatches, scheduleHide } = usePatchPopover()
const jumpToPatchFn = inject<(sha: string) => void>('jumpToPatch', () => {})

const isFileNode = computed(() => {
  if (!props.node?.name || props.node.name === '/') return false
  if (props.node.type === 'file') return true
  return !props.node.children?.length && props.node.name !== '…'
})

const filePatches = computed<PatchBrief[]>(() => {
  const list = props.node?.patches
  return Array.isArray(list) ? list : []
})

function onFileHover(event: MouseEvent) {
  if (!filePatches.value.length) return
  showPatches(filePatches.value, event.clientX, event.clientY)
}

function onPatchHover(patch: PatchBrief, event: MouseEvent) {
  showPatches([patch], event.clientX, event.clientY)
}

function onFileLeave() {
  scheduleHide()
}

async function toggleFileDetail() {
  if (!filePatches.value.length) return
  if (fileOpen.value) {
    fileOpen.value = false
    return
  }
  fileOpen.value = true
  if (fileBlocks.value.length) return

  fileLoading.value = true
  fileError.value = ''
  const path = props.node.path || props.node.name || ''
  try {
    fileBlocks.value = await Promise.all(
      filePatches.value.map(async (patch) => {
        const sha = patch.full_sha || patch.sha || ''
        let diffHtml = ''
        let diffNote = ''
        try {
          const data = await api.get<any>(
            `/api/patches/${encodeURIComponent(sha)}/file-diff?path=${encodeURIComponent(path)}`,
          )
          if (data.found && data.text) {
            diffHtml = colorizeDiff(data.text)
            if (data.truncated) {
              diffNote = '（完整 diff 已截断，详见 patch 详情）'
            }
          } else {
            diffNote = '该文件 diff 未收录或路径不匹配'
          }
        } catch {
          diffNote = 'diff 加载失败'
        }
        return { patch, diffHtml, diffNote }
      }),
    )
  } catch (err: any) {
    fileError.value = err.message || String(err)
  } finally {
    fileLoading.value = false
  }
}

function jumpToPatch(patch: PatchBrief) {
  const sha = patch.full_sha || patch.sha || ''
  if (sha) jumpToPatchFn(sha)
}
</script>
