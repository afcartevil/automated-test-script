<script setup lang="ts">
import { ref, onMounted, shallowRef, onBeforeUnmount } from 'vue'
import { NCard, NSpace, NButton, NSpin, NEmpty, NList, NListItem, NThing, NTag, NBreadcrumb, NBreadcrumbItem, useMessage } from 'naive-ui'
import * as monaco from 'monaco-editor'
import { listReports, readReport, type ReportEntry } from '@/api/tahp/reports'

const message = useMessage()
const cwd = ref('')
const entries = ref<ReportEntry[]>([])
const loading = ref(false)
const selectedFile = ref<string | null>(null)
const loadingContent = ref(false)
const editorContainer = ref<HTMLDivElement | null>(null)
const editorInstance = shallowRef<monaco.editor.IStandaloneCodeEditor | null>(null)

onMounted(async () => { initEditor(); await reload() })
onBeforeUnmount(() => { if (editorInstance.value) editorInstance.value.dispose() })

function initEditor() {
  if (!editorContainer.value) return
  editorInstance.value = monaco.editor.create(editorContainer.value, {
    value: '', language: 'plaintext', theme: 'vs-dark',
    readOnly: true, automaticLayout: true, minimap: { enabled: false },
    fontSize: 12, scrollBeyondLastLine: false, wordWrap: 'on',
  })
}

async function reload() {
  loading.value = true
  try { entries.value = await listReports(cwd.value) }
  catch (err) { message.error((err as Error).message) }
  finally { loading.value = false }
}

async function open(entry: ReportEntry) {
  if (entry.type === 'dir') { cwd.value = entry.path; await reload(); return }
  selectedFile.value = entry.path
  loadingContent.value = true
  try {
    const data = await readReport(entry.path)
    const ext = entry.name.split('.').pop()?.toLowerCase() || ''
    const lang = ext === 'json' || ext === 'jsonl' ? 'json' : ext === 'md' ? 'markdown' : ext === 'yaml' || ext === 'yml' ? 'yaml' : 'plaintext'
    if (editorInstance.value) {
      monaco.editor.setModelLanguage(editorInstance.value.getModel()!, lang)
      editorInstance.value.setValue(data.content)
    }
  } catch (err) { message.error((err as Error).message) }
  finally { loadingContent.value = false }
}

function up() {
  if (!cwd.value) return
  const parts = cwd.value.split('/').filter(Boolean)
  parts.pop()
  cwd.value = parts.join('/')
  reload()
}

function goRoot() { cwd.value = ''; reload() }
</script>

<template>
  <div class="tahp-reports">
    <div class="page-header">
      <h1>报告</h1>
      <p class="subtitle">浏览 reports/ 目录下的评测、门禁、trace 等产物</p>
    </div>
    <div class="layout">
      <NCard title="目录" :bordered="false" class="side">
        <template #header-extra>
          <NSpace>
            <NButton size="tiny" @click="reload">刷新</NButton>
            <NButton size="tiny" :disabled="!cwd" @click="up">..上级</NButton>
          </NSpace>
        </template>
        <NBreadcrumb v-if="cwd">
          <NBreadcrumbItem @click="goRoot">reports</NBreadcrumbItem>
          <NBreadcrumbItem>{{ cwd }}</NBreadcrumbItem>
        </NBreadcrumb>
        <NSpin :show="loading">
          <NEmpty v-if="!entries.length" description="reports/ 为空或不存在" />
          <NList v-else>
            <NListItem
              v-for="e in entries"
              :key="e.path"
              class="list-item"
              :class="{ active: selectedFile === e.path }"
              @click="open(e)"
            >
              <NThing>
                <template #header>
                  {{ e.type === 'dir' ? '📁' : '📄' }} {{ e.name }}
                </template>
                <template #description>
                  <NSpace>
                    <NTag v-if="e.size !== undefined" size="tiny">{{ e.size }} B</NTag>
                    <NTag v-if="e.mtime" size="tiny" type="info">
                      {{ new Date(e.mtime).toLocaleString() }}
                    </NTag>
                  </NSpace>
                </template>
              </NThing>
            </NListItem>
          </NList>
        </NSpin>
      </NCard>
      <NCard
        :title="selectedFile || '请在左侧选择文件'"
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
.tahp-reports { padding: 24px; max-width: 1400px; margin: 0 auto; }
.page-header { margin-bottom: 16px; }
.page-header h1 { margin: 0 0 6px; font-size: 24px; }
.subtitle { color: #888; margin: 0; }
.layout { display: grid; grid-template-columns: 360px 1fr; gap: 16px; }
@media (max-width: 1024px) { .layout { grid-template-columns: 1fr; } }
.list-item { cursor: pointer; padding: 8px; border-radius: 6px; }
.list-item:hover { background: var(--n-action-color); }
.list-item.active { background: var(--n-primary-color-suppl); }
.editor-host { height: calc(100vh - 240px); min-height: 480px; }
</style>
