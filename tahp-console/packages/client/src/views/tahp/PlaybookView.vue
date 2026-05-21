<script setup lang="ts">
import { ref, onMounted, shallowRef, onBeforeUnmount } from 'vue'
import { NCard, NList, NListItem, NThing, NSpin, NEmpty, NSpace, NTag, useMessage } from 'naive-ui'
import * as monaco from 'monaco-editor'
import { listPipelines, getPipeline, type PipelineSummary } from '@/api/tahp/pipelines'

const message = useMessage()
const pipelines = ref<PipelineSummary[]>([])
const selected = ref<string | null>(null)
const loading = ref(false)
const loadingContent = ref(false)
const editorContainer = ref<HTMLDivElement | null>(null)
const editorInstance = shallowRef<monaco.editor.IStandaloneCodeEditor | null>(null)

onMounted(async () => {
  initEditor()
  loading.value = true
  try {
    pipelines.value = await listPipelines()
    if (pipelines.value.length) await pick(pipelines.value[0].file)
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => { if (editorInstance.value) editorInstance.value.dispose() })

function initEditor() {
  if (!editorContainer.value) return
  editorInstance.value = monaco.editor.create(editorContainer.value, {
    value: '',
    language: 'yaml',
    theme: 'vs-dark',
    readOnly: true,
    automaticLayout: true,
    minimap: { enabled: false },
    fontSize: 13,
    scrollBeyondLastLine: false,
  })
}

async function pick(file: string) {
  selected.value = file
  loadingContent.value = true
  try {
    const detail = await getPipeline(file)
    if (editorInstance.value) editorInstance.value.setValue(detail.content)
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    loadingContent.value = false
  }
}
</script>

<template>
  <div class="tahp-playbook">
    <div class="page-header">
      <h1>Playbooks</h1>
      <p class="subtitle">查看 TAHP Pipeline 执行编排 (只读)</p>
    </div>
    <div class="layout">
      <NCard title="Pipeline 列表" :bordered="false" class="side">
        <NSpin :show="loading">
          <NEmpty v-if="!pipelines.length" description="无 pipeline" />
          <NList v-else>
            <NListItem
              v-for="p in pipelines"
              :key="p.file"
              class="list-item"
              :class="{ active: selected === p.file }"
              @click="pick(p.file)"
            >
              <NThing :title="p.name">
                <template #description>
                  <NSpace>
                    <NTag size="tiny">{{ p.file }}</NTag>
                    <NTag size="tiny" type="info">{{ p.size }} B</NTag>
                  </NSpace>
                </template>
              </NThing>
            </NListItem>
          </NList>
        </NSpin>
      </NCard>
      <NCard
        :title="selected || '请选择 Pipeline'"
        :bordered="false"
        class="main"
        content-style="padding: 0"
      >
        <NSpin :show="loadingContent">
          <div ref="editorContainer" class="editor-host" />
        </NSpin>
      </NCard>
    </div>
  </div>
</template>

<style scoped>
.tahp-playbook { padding: 24px; max-width: 1400px; margin: 0 auto; }
.page-header { margin-bottom: 16px; }
.page-header h1 { margin: 0 0 6px; font-size: 24px; }
.subtitle { color: #888; margin: 0; }
.layout { display: grid; grid-template-columns: 320px 1fr; gap: 16px; }
@media (max-width: 1024px) { .layout { grid-template-columns: 1fr; } }
.list-item { cursor: pointer; padding: 8px; border-radius: 6px; }
.list-item:hover { background: var(--n-action-color); }
.list-item.active { background: var(--n-primary-color-suppl); }
.editor-host { height: calc(100vh - 240px); min-height: 480px; }
</style>
