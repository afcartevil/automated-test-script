<script setup lang="ts">
import { ref, computed, onMounted, shallowRef, onBeforeUnmount } from 'vue'
import { NCard, NList, NListItem, NThing, NSpin, NEmpty, NSpace, NTag, NButton, NModal, NSelect, NForm, NFormItem, useMessage } from 'naive-ui'
import * as monaco from 'monaco-editor'
import { useRouter } from 'vue-router'
import { listPipelines, getPipeline, type PipelineSummary, type PipelineDetail } from '@/api/tahp/pipelines'
import { useTahpModulesStore } from '@/stores/tahp/modules'

const message = useMessage()
const router = useRouter()
const modulesStore = useTahpModulesStore()

const pipelines = ref<PipelineSummary[]>([])
const selected = ref<string | null>(null)
const selectedDetail = ref<PipelineDetail | null>(null)
const loading = ref(false)
const loadingContent = ref(false)
const editorContainer = ref<HTMLDivElement | null>(null)
const editorInstance = shallowRef<monaco.editor.IStandaloneCodeEditor | null>(null)

const PIPELINE_DOMAIN_MAP: Record<string, string> = {
  'bug-analysis-pipeline.yaml': 'bug_analysis',
  'code-adaptation-pipeline.yaml': 'code_adaptation',
  'version-upgrade-pipeline.yaml': 'version_adaptation',
  'carrier-porting-pipeline.yaml': 'carrier_porting',
  'feature-porting-pipeline.yaml': 'code_adaptation',
  'cross-module-pipeline.yaml': 'bug_analysis',
}

const showLaunchModal = ref(false)
const launchForm = ref({ module: 'telephony', domain: 'bug_analysis' })

const DOMAIN_OPTIONS = [
  { label: 'Bug 分析 (bug_analysis)', value: 'bug_analysis' },
  { label: '代码适配 (code_adaptation)', value: 'code_adaptation' },
  { label: '版本适配 (version_adaptation)', value: 'version_adaptation' },
  { label: '运营商移植 (carrier_porting)', value: 'carrier_porting' },
]

const moduleOptions = computed(() => modulesStore.modules.map(m => ({ label: m.name, value: m.name })))

onMounted(async () => {
  initEditor()
  loading.value = true
  try {
    await modulesStore.refresh()
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
    selectedDetail.value = detail
    if (editorInstance.value) editorInstance.value.setValue(detail.content)
    const guessed = PIPELINE_DOMAIN_MAP[file]
    if (guessed) launchForm.value.domain = guessed
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    loadingContent.value = false
  }
}

function openLaunch() {
  if (!selected.value) return
  showLaunchModal.value = true
}

function confirmLaunch() {
  showLaunchModal.value = false
  router.push({
    name: 'tahp.executor',
    query: {
      module: launchForm.value.module,
      domain: launchForm.value.domain,
      playbook_path: selected.value ? `playbooks/${selected.value}` : undefined,
    },
  })
}
</script>

<template>
  <div class="tahp-playbook">
    <div class="page-header">
      <h1>Playbooks</h1>
      <p class="subtitle">查看和管理 EasyAdapter Pipeline 编排文件</p>
    </div>

    <div class="playbook-layout">
      <!-- 左侧：pipeline 列表 -->
      <NCard title="Pipeline 列表" :bordered="false" class="list-card">
        <NSpin :show="loading">
          <NEmpty v-if="!pipelines.length && !loading" description="暂无 Pipeline" />
          <NList v-else hoverable clickable>
            <NListItem
              v-for="p in pipelines"
              :key="p.file"
              :class="{ 'list-item-active': selected === p.file }"
              @click="pick(p.file)"
            >
              <NThing :title="p.name || p.file">
                <template #description>
                  <NSpace size="small">
                    <NTag size="tiny" type="info">{{ p.file }}</NTag>
                  </NSpace>
                </template>
              </NThing>
            </NListItem>
          </NList>
        </NSpin>
      </NCard>

      <!-- 右侧：编辑器 + 操作 -->
      <NCard :bordered="false" class="editor-card">
        <template #header>
          <NSpace align="center">
            <span>{{ selectedDetail?.name || selected || '选择 Pipeline' }}</span>

          </NSpace>
        </template>
        <template #header-extra>
          <NButton
            type="primary"
            size="small"
            :disabled="!selected"
            @click="openLaunch"
          >
            以此 Playbook 启动任务
          </NButton>
        </template>

        <NSpin :show="loadingContent">
          <NEmpty v-if="!selected" description="请在左侧选择一个 Pipeline" style="padding: 60px 0" />
          <div ref="editorContainer" class="editor-container" />
        </NSpin>
      </NCard>
    </div>

    <!-- 启动任务弹窗 -->
    <NModal
      v-model:show="showLaunchModal"
      preset="dialog"
      title="以此 Playbook 启动任务"
      positive-text="启动"
      negative-text="取消"
      style="width: 440px"
      @positive-click="confirmLaunch"
    >
      <p style="margin-bottom: 12px; font-size: 13px; color: #888">
        Pipeline: <code>{{ selected }}</code>
      </p>
      <NForm :model="launchForm" label-placement="left" label-width="60">
        <NFormItem label="模块">
          <NSelect v-model:value="launchForm.module" :options="moduleOptions.length ? moduleOptions : [{label:'telephony',value:'telephony'}]" />
        </NFormItem>
        <NFormItem label="域">
          <NSelect v-model:value="launchForm.domain" :options="DOMAIN_OPTIONS" />
        </NFormItem>
      </NForm>
    </NModal>
  </div>
</template>

<style scoped>
.tahp-playbook { padding: 24px; max-width: 1400px; margin: 0 auto; }
.page-header { margin-bottom: 20px; }
.page-header h1 { margin: 0 0 4px; font-size: 22px; font-weight: 600; }
.subtitle { color: #888; margin: 0; font-size: 13px; }
.playbook-layout { display: grid; grid-template-columns: 280px 1fr; gap: 16px; }
.list-card { height: calc(100vh - 180px); overflow: auto; }
.editor-card { height: calc(100vh - 180px); display: flex; flex-direction: column; }
.editor-container { height: calc(100vh - 260px); min-height: 300px; border-radius: 4px; overflow: hidden; }
.list-item-active { background: var(--n-color-hover, rgba(24,160,88,.1)) !important; }
code { background: rgba(0,0,0,.06); padding: 1px 4px; border-radius: 3px; font-size: 12px; }
</style>
