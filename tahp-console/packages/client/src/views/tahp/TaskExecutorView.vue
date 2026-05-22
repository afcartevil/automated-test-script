<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import {
  NCard, NForm, NFormItem, NSelect, NInput, NButton, NTag,
  NScrollbar, useMessage, NModal, NRadioGroup, NRadioButton, NDivider,
} from 'naive-ui'
import { useTahpTasksStore } from '@/stores/tahp/tasks'
import { useTahpModulesStore } from '@/stores/tahp/modules'
import type { TahpModule, TahpDomain, ExecuteTaskRequest } from '@/api/tahp/tasks'

const route = useRoute()
const message = useMessage()
const tasksStore = useTahpTasksStore()
const modulesStore = useTahpModulesStore()

const inputMode = ref<'path' | 'content'>('path')

const form = ref<ExecuteTaskRequest>({
  document_path: '',
  module: (route.query.module as TahpModule) || 'telephony',
  domain: (route.query.domain as TahpDomain) || 'bug_analysis',
  extra_context: '',
})
const documentContent = ref('')
const submitting = ref(false)
const currentTaskId = ref<string | null>(null)
const showCorrectDialog = ref(false)
const correctFeedback = ref('')
const taskStatus = ref<string>('')

const moduleOptions = computed(() => modulesStore.modules.map(m => ({ label: m.name, value: m.name })))
const DOMAIN_OPTIONS = [
  { label: 'Bug 分析 (bug_analysis)', value: 'bug_analysis' },
  { label: '代码适配 (code_adaptation)', value: 'code_adaptation' },
  { label: '版本适配 (version_adaptation)', value: 'version_adaptation' },
  { label: '运营商移植 (carrier_porting)', value: 'carrier_porting' },
]

const stream = computed(() => currentTaskId.value ? tasksStore.getStream(currentTaskId.value) : [])

const isRunning = computed(() =>
  taskStatus.value !== '' &&
  taskStatus.value !== 'completed' &&
  taskStatus.value !== 'failed' &&
  taskStatus.value !== 'COMPLETED' &&
  taskStatus.value !== 'FAILED'
)

watch(stream, (evs) => {
  if (!evs.length) return
  const last = evs[evs.length - 1]
  if (last.type === 'task.completed') taskStatus.value = 'COMPLETED'
  else if (last.type === 'task.failed') taskStatus.value = 'FAILED'
  else if (last.type === 'task.phase') taskStatus.value = (last.payload?.phase as string) || 'running'
  else taskStatus.value = 'running'
}, { deep: true })

onMounted(async () => {
  await modulesStore.refresh()
  tasksStore.ensureSocket()
  if (route.query.module) form.value.module = route.query.module as TahpModule
  if (route.query.domain) form.value.domain = route.query.domain as TahpDomain
  if (route.query.playbook_path) {
    form.value.document_path = route.query.playbook_path as string
  }
})

async function submit() {
  const req: ExecuteTaskRequest = { ...form.value }
  if (inputMode.value === 'content') {
    if (!documentContent.value.trim()) {
      message.warning('请粘贴文档内容')
      return
    }
    req.document_path = '__inline__'
    req.document_content = documentContent.value
  } else {
    if (!req.document_path?.trim()) {
      message.warning('请填写设计文档路径')
      return
    }
  }
  submitting.value = true
  taskStatus.value = 'starting'
  try {
    const info = await tasksStore.start(req)
    const tid = info.task_id || info.taskId
    if (tid) {
      currentTaskId.value = String(tid)
      message.success(`任务已启动: ${currentTaskId.value}`)
    } else {
      message.info('任务已提交但未返回 task_id')
    }
  } catch (err) {
    message.error((err as Error).message)
    taskStatus.value = ''
  } finally {
    submitting.value = false
  }
}

function reset() {
  currentTaskId.value = null
  taskStatus.value = ''
  form.value.document_path = ''
  documentContent.value = ''
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

function formatPayload(payload: Record<string, unknown>): string {
  const msg = payload?.message || payload?.content || payload?.text
  if (typeof msg === 'string') return msg
  return JSON.stringify(payload, null, 2)
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
      <p class="subtitle">配置模块与文档，启动后右侧实时展示 Pipeline 执行进度</p>
    </div>

    <div class="executor-grid">
      <!-- 左侧：表单 -->
      <NCard title="任务参数" :bordered="false" class="form-card">
        <NForm :model="form" label-placement="left" label-width="90">
          <NFormItem label="模块" required>
            <NSelect
              v-model:value="form.module"
              :options="moduleOptions"
              placeholder="选择模块"
            />
          </NFormItem>
          <NFormItem label="域" required>
            <NSelect v-model:value="form.domain" :options="DOMAIN_OPTIONS" />
          </NFormItem>

          <NDivider style="margin: 12px 0 8px" />

          <NFormItem label="文档来源">
            <NRadioGroup v-model:value="inputMode" size="small">
              <NRadioButton value="path">文件路径</NRadioButton>
              <NRadioButton value="content">直接粘贴</NRadioButton>
            </NRadioGroup>
          </NFormItem>

          <NFormItem v-if="inputMode === 'path'" label="文件路径" required>
            <NInput
              v-model:value="form.document_path"
              placeholder="如 docs/telephony/bug-report.md 或绝对路径"
              clearable
            />
          </NFormItem>

          <NFormItem v-else label="文档内容" required>
            <NInput
              v-model:value="documentContent"
              type="textarea"
              placeholder="在此粘贴设计文档、Bug 报告或需求描述..."
              :autosize="{ minRows: 8, maxRows: 20 }"
            />
          </NFormItem>

          <NFormItem label="附加说明">
            <NInput
              v-model:value="form.extra_context"
              placeholder="可选：补充说明或特殊要求"
              clearable
            />
          </NFormItem>
        </NForm>

        <div style="margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap;">
          <NButton type="primary" :loading="submitting" :disabled="!!currentTaskId && isRunning" @click="submit">
            {{ submitting ? '提交中...' : '启动任务' }}
          </NButton>
          <NButton :disabled="!currentTaskId" @click="reset">重置</NButton>
          <NButton
            type="warning"
            :disabled="!currentTaskId || !isRunning"
            @click="openCorrect"
          >
            发送纠偏
          </NButton>
        </div>

        <!-- 当前任务状态 -->
        <div v-if="currentTaskId" style="margin-top: 16px; padding: 10px; background: rgba(0,0,0,.04); border-radius: 6px; font-size: 13px;">
          <div style="display: flex; align-items: center; gap: 8px;">
            <span style="color: #888;">Task ID:</span>
            <code style="font-size: 11px; word-break: break-all;">{{ currentTaskId }}</code>
          </div>
          <div style="margin-top: 6px; display: flex; align-items: center; gap: 8px;">
            <span style="color: #888;">状态:</span>
            <NTag
              size="small"
              :type="taskStatus === 'COMPLETED' ? 'success' : taskStatus === 'FAILED' ? 'error' : 'info'"
            >
              {{ taskStatus || '-' }}
            </NTag>
          </div>
        </div>
      </NCard>

      <!-- 右侧：实时事件流 -->
      <NCard title="执行事件流" :bordered="false" class="stream-card">
        <template #header-extra>
          <NTag size="small">{{ stream.length }} 个事件</NTag>
        </template>

        <div v-if="!currentTaskId" class="empty-stream">
          <p style="color: #888; text-align: center; padding: 60px 0;">启动任务后，实时事件将在此显示</p>
        </div>

        <NScrollbar v-else style="max-height: calc(100vh - 260px);">
          <div class="event-list">
            <div
              v-for="(ev, i) in stream"
              :key="i"
              class="event-row"
              :class="`ev-${eventColor(ev.type)}`"
            >
              <div class="ev-header">
                <NTag size="tiny" :type="eventColor(ev.type)">{{ ev.type }}</NTag>
                <span class="ev-ts">{{ formatTs(ev.ts) }}</span>
              </div>
              <pre class="ev-body">{{ formatPayload(ev.payload) }}</pre>
            </div>
          </div>
        </NScrollbar>
      </NCard>
    </div>

    <!-- 纠偏弹窗 -->
    <NModal
      v-model:show="showCorrectDialog"
      preset="dialog"
      title="发送纠偏指令"
      positive-text="发送"
      negative-text="取消"
      @positive-click="submitCorrect"
    >
      <div style="margin-bottom: 8px; font-size: 13px; color: #888;">
        Task: <code>{{ currentTaskId }}</code>
      </div>
      <NInput
        v-model:value="correctFeedback"
        type="textarea"
        placeholder="描述需要调整的内容..."
        :autosize="{ minRows: 4, maxRows: 10 }"
      />
    </NModal>
  </div>
</template>

<style scoped>
.tahp-executor { padding: 24px; max-width: 1400px; margin: 0 auto; }
.page-header { margin-bottom: 20px; }
.page-header h1 { margin: 0 0 4px; font-size: 22px; font-weight: 600; }
.subtitle { color: #888; margin: 0; font-size: 13px; }
.executor-grid { display: grid; grid-template-columns: 420px 1fr; gap: 16px; }
.form-card { height: fit-content; }
.stream-card { height: calc(100vh - 160px); }
.event-list { display: flex; flex-direction: column; gap: 6px; padding-right: 8px; }
.event-row { padding: 8px 10px; border-radius: 5px; background: var(--n-color-modal,rgba(0,0,0,.03)); border-left: 3px solid transparent; }
.event-row.ev-success { border-left-color: #18a058; }
.event-row.ev-error { border-left-color: #d03050; background: rgba(208,48,80,.05); }
.event-row.ev-warning { border-left-color: #f0a020; }
.event-row.ev-info { border-left-color: #2080f0; }
.ev-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.ev-ts { color: #999; font-size: 11px; font-family: monospace; }
.ev-body { margin: 0; font-size: 12px; white-space: pre-wrap; word-break: break-all; color: var(--n-text-color,#333); line-height: 1.5; }
code { background: rgba(0,0,0,.06); padding: 1px 4px; border-radius: 3px; font-size: 11px; }
</style>
