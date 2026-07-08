<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch, type ComponentPublicInstance } from 'vue'
import {
  NButton, NSpin, NEmpty, NInput, NAlert, NSpace, useMessage,
} from 'naive-ui'
import MarkdownRenderer from '@/components/hermes/chat/MarkdownRenderer.vue'
import ModelProviderBanner from '@/components/tahp/ModelProviderBanner.vue'
import BugAnalysisInteractionModal from '@/components/tahp/BugAnalysisInteractionModal.vue'
import EaCard from '@/components/layout/EaCard.vue'
import EaPill from '@/components/layout/EaPill.vue'
import { useModelProviderReadiness } from '@/composables/useModelProviderReadiness'
import { useSkillConfigTaskWatcher } from '@/composables/useSkillConfigTaskWatcher'
import {
  fetchSkillConfigList,
  startConfigureAllSkills,
  continueSkillConfig,
  respondSkillConfigApproval,
  type SkillConfigListItem,
} from '@/api/tahp/skill-config'
import { SKILL_CONFIG_CHECK_BUTTON_LABEL } from '@/utils/config-navigation'

const props = defineProps<{
  /** 从表单点击「启动skill配置检查」时递增，触发启动或恢复 */
  startToken?: number
}>()

const emit = defineEmits<{
  back: []
}>()

const message = useMessage()
const { isReady: modelProviderReady } = useModelProviderReadiness()

const loading = ref(false)
const skills = ref<SkillConfigListItem[]>([])
const activeTaskId = ref<string | null>(null)
const batchTaskStatus = ref<'running' | 'waiting_user' | 'completed' | 'failed' | null>(null)
const batchStarting = ref(false)
const chatInput = ref('')
const chatSubmitting = ref(false)
const approvalSubmitting = ref(false)

function isTaskTerminal(taskId: string): boolean {
  return tasksStore.getStream(taskId).some(e =>
    e.type === 'task.completed' || e.type === 'task.failed' || e.type === 'task.cancelled',
  )
}

const {
  tasksStore,
  pendingApproval,
  scroller,
  streamText,
  latestPhaseMessage,
  taskRunning,
  watchTaskEvents,
  scrollChatToBottom,
} = useSkillConfigTaskWatcher({
  activeTaskId,
  onSkillComplete: () => loadList(),
  onTaskEnd: (result) => {
    batchTaskStatus.value = result
    void loadList()
  },
})

function setScrollerEl(el: Element | ComponentPublicInstance | null) {
  scroller.value = el instanceof HTMLElement ? el : null
}

const chatMarkdown = computed(() =>
  activeTaskId.value ? streamText(activeTaskId.value) : '',
)

const phaseHint = computed(() =>
  activeTaskId.value ? latestPhaseMessage(activeTaskId.value) : '',
)

const showChatInput = computed(() => {
  if (!activeTaskId.value) return false
  if (batchTaskStatus.value === 'waiting_user') return true
  if (batchTaskStatus.value === 'completed' || batchTaskStatus.value === 'failed') return false
  return taskRunning.value || batchTaskStatus.value === 'running'
})

const sessionStatusLabel = computed(() => {
  if (!activeTaskId.value) return ''
  if (batchTaskStatus.value === 'waiting_user') return '等待您的输入'
  if (taskRunning.value) return 'Agent 运行中'
  if (batchTaskStatus.value === 'completed') return '检查已完成'
  if (batchTaskStatus.value === 'failed') return '检查失败'
  return '会话进行中'
})

const sessionStatusVariant = computed<'ok' | 'info' | 'warn' | 'err' | 'muted'>(() => {
  if (batchTaskStatus.value === 'waiting_user') return 'warn'
  if (taskRunning.value) return 'info'
  if (batchTaskStatus.value === 'completed') return 'ok'
  if (batchTaskStatus.value === 'failed') return 'err'
  return 'muted'
})

scrollChatToBottom(chatMarkdown)

function statusLabel(status: SkillConfigListItem['status']): string {
  switch (status) {
    case 'configured': return '配置完成'
    case 'configuring': return '配置中'
    default: return '未配置'
  }
}

function statusVariant(status: SkillConfigListItem['status']): 'ok' | 'info' | 'warn' | 'err' | 'muted' {
  switch (status) {
    case 'configured': return 'ok'
    case 'configuring': return 'info'
    default: return 'muted'
  }
}

function attachBatchTask(taskId: string, status?: 'running' | 'waiting_user') {
  activeTaskId.value = taskId
  batchTaskStatus.value = status ?? 'running'
  tasksStore.ensureSocket()
  tasksStore.trackTask(taskId)
}

async function loadList() {
  loading.value = true
  try {
    const data = await fetchSkillConfigList()
    skills.value = data.skills
    if (data.batch_task?.task_id) {
      attachBatchTask(data.batch_task.task_id, data.batch_task.status)
    }
  } catch (err) {
    message.error((err as Error).message || '加载失败')
  } finally {
    loading.value = false
  }
}

let pollTimer: ReturnType<typeof setInterval> | null = null
let listPollTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  tasksStore.ensureSocket()
  await loadList()
  pollTimer = watchTaskEvents()
  listPollTimer = setInterval(() => {
    if (activeTaskId.value) void loadList()
  }, 3000)
})

watch(
  () => props.startToken,
  async (token) => {
    if (!token) return
    await loadList()
    await startBatchIfNeeded()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (listPollTimer) clearInterval(listPollTimer)
})

async function startBatchIfNeeded() {
  if (activeTaskId.value) {
    if (!isTaskTerminal(activeTaskId.value)) return
    activeTaskId.value = null
    batchTaskStatus.value = null
  }
  if (!modelProviderReady.value) {
    message.warning('请先在「配置 → 模型管理」中配置模型 Provider')
    return
  }
  batchStarting.value = true
  try {
    const data = await startConfigureAllSkills()
    attachBatchTask(data.task_id, 'running')
    chatInput.value = ''
    await loadList()
    message.info('已启动 Skill 配置检查')
  } catch (err) {
    const msg = (err as Error).message || '启动失败'
    if (msg.includes('任务进行中')) {
      await loadList()
      if (activeTaskId.value) {
        message.info('已恢复进行中的 Skill 配置检查会话')
      } else {
        message.warning(msg)
      }
    } else {
      message.error(msg)
    }
  } finally {
    batchStarting.value = false
  }
}

async function onSendChat() {
  const tid = activeTaskId.value
  const text = chatInput.value.trim()
  if (!tid || !text) return
  chatSubmitting.value = true
  try {
    await continueSkillConfig(tid, text)
    chatInput.value = ''
    batchTaskStatus.value = 'running'
  } catch (err) {
    message.error((err as Error).message || '发送失败')
  } finally {
    chatSubmitting.value = false
  }
}

async function onApproval(choice: string) {
  const tid = activeTaskId.value
  const ap = pendingApproval.value
  if (!tid || !ap) return
  approvalSubmitting.value = true
  try {
    await respondSkillConfigApproval(tid, { approval_id: ap.approval_id, choice })
    pendingApproval.value = null
  } catch (err) {
    message.error((err as Error).message || '审批失败')
  } finally {
    approvalSubmitting.value = false
  }
}
</script>

<template>
  <div class="config-batch-panel">
    <div class="batch-toolbar">
      <NButton class="batch-back-btn" @click="emit('back')">
        ← 返回一键配置表单
      </NButton>
      <EaPill v-if="sessionStatusLabel" :variant="sessionStatusVariant">
        {{ sessionStatusLabel }}
      </EaPill>
    </div>

    <NAlert type="info" :show-icon="true" class="batch-session-hint">
      <template #header>会话在后台保持</template>
      返回「一键配置表单」不会中断当前 Skill 配置检查。再次进入本页可继续查看进展与对话；左侧「配置进展」会随 Skill 完成自动刷新。
    </NAlert>

    <NAlert type="default" :show-icon="false" class="batch-hint">
      Agent 将依据已保存的一键配置表单，依次检查并完成配置清单中各 Skill 的环境与凭据配置。
    </NAlert>

    <ModelProviderBanner style="margin-bottom: 12px" />

    <div class="batch-layout">
      <EaCard class="batch-list-panel">
        <div class="panel-title-row">
          <span class="panel-title">配置进展</span>
          <span v-if="activeTaskId && taskRunning" class="panel-live ea-muted">自动刷新</span>
        </div>
        <NSpin :show="loading && !skills.length">
          <div v-if="skills.length" class="skill-list">
            <div
              v-for="s in skills"
              :key="s.id"
              class="skill-row"
              :class="{ configuring: s.status === 'configuring' }"
            >
              <div class="skill-row-main">
                <strong>{{ s.label }}</strong>
                <span class="skill-id">{{ s.id }}</span>
              </div>
              <EaPill :variant="statusVariant(s.status)">{{ statusLabel(s.status) }}</EaPill>
            </div>
          </div>
          <NEmpty v-else description="清单为空" size="small" />
        </NSpin>
      </EaCard>

      <EaCard class="batch-chat-panel">
        <div class="panel-title-row">
          <span class="panel-title">Agent 配置向导</span>
          <span v-if="activeTaskId" class="task-id ea-muted">{{ activeTaskId }}</span>
        </div>

        <div v-if="!activeTaskId && batchStarting" class="chat-placeholder">
          <NSpin size="small" />
          <span class="ea-muted">正在启动 {{ SKILL_CONFIG_CHECK_BUTTON_LABEL }}...</span>
        </div>
        <div v-else-if="!activeTaskId" class="chat-placeholder ea-muted">
          未检测到活动会话，请返回表单重新点击「{{ SKILL_CONFIG_CHECK_BUTTON_LABEL }}」。
        </div>
        <template v-else>
          <div :ref="setScrollerEl" class="chat-stream">
            <MarkdownRenderer v-if="chatMarkdown" :content="chatMarkdown" />
            <div v-else class="chat-waiting">
              <NSpin size="small" />
              <span>{{ phaseHint || 'Agent 正在处理，请稍候...' }}</span>
            </div>
          </div>
          <div v-if="showChatInput" class="chat-input-row">
            <NInput
              v-model:value="chatInput"
              type="textarea"
              placeholder="按 Agent 提示回复配置项（KEY=VALUE 或说明文字）..."
              :autosize="{ minRows: 3, maxRows: 8 }"
              :disabled="chatSubmitting"
              @keydown.ctrl.enter="onSendChat"
            />
            <NSpace justify="end">
              <NButton
                type="primary"
                :loading="chatSubmitting"
                :disabled="!chatInput.trim()"
                @click="onSendChat"
              >
                发送
              </NButton>
            </NSpace>
          </div>
          <NAlert
            v-else-if="batchTaskStatus === 'completed'"
            type="success"
            :show-icon="false"
            style="margin-top: 8px"
          >
            Skill 配置检查已完成。可返回表单修改配置，或前往「常用 Skill 配置」查看单项详情。
          </NAlert>
        </template>
      </EaCard>
    </div>

    <BugAnalysisInteractionModal
      :approval="pendingApproval"
      :user-input="null"
      :submitting="approvalSubmitting"
      @approval="onApproval"
    />
  </div>
</template>

<style scoped lang="scss">
.config-batch-panel {
  max-width: 1280px;
}

.batch-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.batch-back-btn {
  font-weight: 700;
  border: 1px solid var(--line-strong, var(--border));
  background: var(--surface);
  box-shadow: var(--shadow, 0 1px 3px rgba(0, 0, 0, 0.06));

  &:hover {
    border-color: var(--accent);
    color: var(--accent);
  }
}

.batch-session-hint {
  margin-bottom: 10px;
}

.batch-hint {
  margin-bottom: 14px;
}

.batch-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 14px;
  align-items: start;
}

.panel-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 12px;
}

.panel-title {
  font-size: 13px;
  font-weight: 700;
}

.panel-live {
  font-size: 11px;
}

.task-id {
  font-size: 10px;
  font-family: ui-monospace, monospace;
  max-width: 180px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.skill-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.skill-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);

  &.configuring {
    border-color: var(--primary);
    background: color-mix(in srgb, var(--primary) 6%, var(--surface));
  }
}

.skill-row-main {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;

  strong { font-size: 13px; }
  .skill-id {
    font-size: 11px;
    color: var(--muted);
    font-family: ui-monospace, monospace;
  }
}

.chat-placeholder,
.chat-waiting {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 32px;
  text-align: center;
  font-size: 13px;
  min-height: 200px;
}

.chat-stream {
  min-height: 320px;
  max-height: 480px;
  overflow-y: auto;
  padding: 12px;
  margin-bottom: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-2);
}

.chat-input-row {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

@media (max-width: 900px) {
  .batch-layout {
    grid-template-columns: 1fr;
  }
}
</style>
