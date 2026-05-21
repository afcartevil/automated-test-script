<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  NCard, NForm, NFormItem, NSelect, NInput, NButton, NSpace, NTag, NSpin, NEmpty, NScrollbar, useMessage, NModal,
} from 'naive-ui'
import { useTahpTasksStore } from '@/stores/tahp/tasks'
import { useTahpModulesStore } from '@/stores/tahp/modules'
import type { TahpModule, TahpDomain, ExecuteTaskRequest } from '@/api/tahp/tasks'

const route = useRoute()
const message = useMessage()
const tasksStore = useTahpTasksStore()
const modulesStore = useTahpModulesStore()

const form = ref<ExecuteTaskRequest>({
  document_path: '',
  module: (route.query.module as TahpModule) || 'telephony',
  domain: (route.query.domain as TahpDomain) || 'bug_analysis',
})
const submitting = ref(false)
const currentTaskId = ref<string | null>(null)
const showCorrectDialog = ref(false)
const correctFeedback = ref('')

const moduleOptions = computed(() => modulesStore.modules.map(m => ({ label: m.name, value: m.name })))
const DOMAIN_OPTIONS = [
  { label: 'Bug 分析 (bug_analysis)', value: 'bug_analysis' },
  { label: '代码适配 (code_adaptation)', value: 'code_adaptation' },
  { label: '版本适配 (version_adaptation)', value: 'version_adaptation' },
  { label: '运营商移植 (carrier_porting)', value: 'carrier_porting' },
]

const stream = computed(() => currentTaskId.value ? tasksStore.getStream(currentTaskId.value) : [])

onMounted(async () => {
  await modulesStore.refresh()
  tasksStore.ensureSocket()
})

async function submit() {
  if (!form.value.document_path?.trim()) {
    message.warning('请填写设计文档路径')
    return
  }
  submitting.value = true
  try {
    const info = await tasksStore.start({ ...form.value })
    const tid = info.task_id || info.taskId
    if (tid) {
      currentTaskId.value = String(tid)
      message.success(`任务已启动: ${currentTaskId.value}`)
    } else {
      message.info('任务已提交但未返回 task_id')
    }
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    submitting.value = false
  }
}

function openCorrect() {
  if (!currentTaskId.value) return
  correctFeedback.value = ''
  showCorrectDialog.value = true
}

async function submitCorrect() {
  if (!currentTaskId.value || !correctFeedback.value.trim()) return
  try {
    await tasksStore.correct(currentTaskId.value, correctFeedback.value)
    message.success('纠偏指令已下发')
    showCorrectDialog.value = false
  } catch (err) {
    message.error((err as Error).message)
  }
}

function formatTs(ts: number): string {
  return new Date(ts).toLocaleTimeString()
}

function eventColor(type: string): 'default' | 'success' | 'error' | 'warning' | 'info' {
  if (type.endsWith('.failed')) return 'error'
  if (type.endsWith('.completed')) return 'success'
  if (type.endsWith('.correction')) return 'warning'
  return 'info'
}

watch(() => route.query, (q) => {
  if (q.module) form.value.module = q.module as TahpModule
  if (q.domain) form.value.domain = q.domain as TahpDomain
})
</script>

<template>
  <div class="tahp-executor">
    <div class="page-header">
      <h1>启动任务</h1>
      <p class="subtitle">填写设计文档与模块，启动后右侧实时显示 Pipeline 执行进度</p>
    </div>

    <div class="executor-grid">
      <NCard title="任务参数" :bordered="false" class="form-card">
        <NForm :model="form" label-placement="left" label-width="100">
          <NFormItem label="模块" required>
            <NSelect
              v-model:value="form.module"
              :options="moduleOptions"
              placeholder="选择模块"
            />
          </NFormItem>
          <NFormItem label="域" required>
            <NSelect
              v-model:value="form.domain"
              :options="DOMAIN_OPTIONS"
            />
          </NFormItem>
          <NFormItem label="设计文档" required>
            <NInput
              v-model:value="form.document_path"
              placeholder="docs/xxx.md 或绝对路径"
            />
          </NFormItem>
          <NSpace>
            <NButton
              type="primary"
              :loading="submitting"
              @click="submit"
            >
              启动 Pipeline
            </NButton>
            <NButton
              :disabled="!currentTaskId"
              @click="openCorrect"
            >
              纠偏...
            </NButton>
          </NSpace>
        </NForm>
        <div v-if="currentTaskId" class="task-id-block">
          当前 Task ID:
          <code>{{ currentTaskId }}</code>
        </div>
      </NCard>

      <NCard title="实时进度" :bordered="false" class="stream-card">
        <template #header-extra>
          <NTag v-if="currentTaskId" size="small">{{ stream.length }} 事件</NTag>
        </template>
        <NEmpty v-if="!currentTaskId" description="启动任务后将在此实时展示进度" />
        <NScrollbar v-else style="max-height: 600px">
          <div class="event-list">
            <div v-for="(ev, i) in stream" :key="i" class="event-row">
              <NTag size="tiny" :type="eventColor(ev.type)">
                {{ ev.type }}
              </NTag>
              <span class="event-ts">{{ formatTs(ev.ts) }}</span>
              <pre class="event-payload">{{ JSON.stringify(ev.payload, null, 2) }}</pre>
            </div>
            <NSpin v-if="!stream.length" size="small">
              <template #description>等待事件...</template>
            </NSpin>
          </div>
        </NScrollbar>
      </NCard>
    </div>

    <NModal
      v-model:show="showCorrectDialog"
      preset="dialog"
      title="纠偏反馈"
      positive-text="发送"
      negative-text="取消"
      @positive-click="submitCorrect"
    >
      <NInput
        v-model:value="correctFeedback"
        type="textarea"
        placeholder="描述当前执行有什么需要调整..."
        :autosize="{ minRows: 4, maxRows: 10 }"
      />
    </NModal>
  </div>
</template>

<style scoped>
.tahp-executor { padding: 24px; max-width: 1400px; margin: 0 auto; }
.page-header { margin-bottom: 24px; }
.page-header h1 { margin: 0 0 6px; font-size: 24px; }
.subtitle { color: #888; margin: 0; }
.executor-grid { display: grid; grid-template-columns: 380px 1fr; gap: 16px; }
@media (max-width: 1024px) { .executor-grid { grid-template-columns: 1fr; } }
.task-id-block { margin-top: 16px; padding: 10px; background: var(--n-color-modal); border-radius: 4px; font-size: 12px; }
.task-id-block code { background: transparent; padding: 0; }
.event-list { display: flex; flex-direction: column; gap: 10px; padding-right: 8px; }
.event-row { display: grid; grid-template-columns: 120px 80px 1fr; gap: 8px; align-items: start; padding: 8px; background: var(--n-color-modal); border-radius: 4px; }
.event-ts { color: #888; font-size: 12px; font-family: monospace; }
.event-payload { margin: 0; font-size: 12px; white-space: pre-wrap; word-break: break-all; }
</style>
