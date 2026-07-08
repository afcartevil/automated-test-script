<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, type ComponentPublicInstance } from 'vue'
import {
  NButton, NSpin, NEmpty, NInput, NAlert, NSpace, NScrollbar, useMessage,
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
  fetchSkillPreview,
  startSkillConfig,
  continueSkillConfig,
  respondSkillConfigApproval,
  type SkillConfigListItem,
  type SkillConfigPreview,
} from '@/api/tahp/skill-config'

const message = useMessage()
const { isReady: modelProviderReady } = useModelProviderReadiness()

const loading = ref(false)
const manifestPath = ref('')
const skills = ref<SkillConfigListItem[]>([])
const selectedId = ref<string | null>(null)
const preview = ref<SkillConfigPreview | null>(null)
const previewLoading = ref(false)

const activeTaskId = ref<string | null>(null)
const chatInput = ref('')
const chatSubmitting = ref(false)
const starting = ref(false)
const approvalSubmitting = ref(false)

const selectedSkill = computed(() =>
  skills.value.find(s => s.id === selectedId.value) || null,
)

const isConfiguring = computed(() =>
  selectedSkill.value?.status === 'configuring' || !!activeTaskId.value,
)

const {
  tasksStore,
  pendingApproval,
  scroller,
  streamText,
  watchTaskEvents,
  scrollChatToBottom,
} = useSkillConfigTaskWatcher({
  activeTaskId,
  onSkillComplete: () => loadList(),
  onTaskEnd: () => loadList(),
})

function setScrollerEl(el: Element | ComponentPublicInstance | null) {
  scroller.value = el instanceof HTMLElement ? el : null
}

const chatMarkdown = computed(() =>
  activeTaskId.value ? streamText(activeTaskId.value) : '',
)

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

async function loadList() {
  loading.value = true
  try {
    const data = await fetchSkillConfigList()
    manifestPath.value = data.manifest_path
    skills.value = data.skills
    if (!selectedId.value && data.skills.length) {
      selectedId.value = data.skills[0].id
    }
  } catch (err) {
    message.error((err as Error).message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function loadPreview(skillId: string) {
  previewLoading.value = true
  try {
    preview.value = await fetchSkillPreview(skillId)
  } catch {
    preview.value = null
  } finally {
    previewLoading.value = false
  }
}

watch(selectedId, (id) => {
  if (id) loadPreview(id)
})

watch(selectedSkill, (s) => {
  if (s?.active_task_id) {
    activeTaskId.value = s.active_task_id
    tasksStore.trackTask(s.active_task_id)
  }
})

let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(async () => {
  await loadList()
  pollTimer = watchTaskEvents()
})

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer)
})

async function onStart(force: boolean) {
  if (!selectedId.value) return
  if (!modelProviderReady.value) {
    message.warning('请先在「配置 → 模型管理」中配置模型 Provider')
    return
  }
  starting.value = true
  try {
    tasksStore.ensureSocket()
    const data = await startSkillConfig(selectedId.value, force)
    activeTaskId.value = data.task_id
    tasksStore.trackTask(data.task_id)
    chatInput.value = ''
    await loadList()
    message.info(force ? '已启动重新配置' : '已启动配置向导')
  } catch (err) {
    message.error((err as Error).message || '启动失败')
  } finally {
    starting.value = false
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
  <div class="config-skill-panel">
    <ModelProviderBanner style="margin-bottom: 12px" />

    <NAlert type="info" :show-icon="false" style="margin-bottom: 14px">
      Skill 清单配置文件：<code>{{ manifestPath || '.tahp/required-skills.json' }}</code>
      （位于 TAHP 工程根目录，可自行增删条目）
    </NAlert>

    <div class="sc-layout">
      <EaCard class="sc-list-panel">
        <div class="panel-title">配置清单</div>
        <NSpin :show="loading">
          <div v-if="skills.length" class="skill-list">
            <button
              v-for="s in skills"
              :key="s.id"
              type="button"
              class="skill-row"
              :class="{ active: selectedId === s.id }"
              @click="selectedId = s.id"
            >
              <div class="skill-row-main">
                <strong>{{ s.label }}</strong>
                <span class="skill-id">{{ s.id }}</span>
              </div>
              <EaPill :variant="statusVariant(s.status)">{{ statusLabel(s.status) }}</EaPill>
            </button>
          </div>
          <NEmpty v-else description="清单为空" size="small" />
        </NSpin>
      </EaCard>

      <div class="sc-main">
        <EaCard v-if="selectedSkill" class="sc-preview-panel">
          <div class="panel-head">
            <div>
              <h3>{{ selectedSkill.label }}</h3>
              <p class="ea-muted">{{ selectedSkill.description }}</p>
            </div>
            <NSpace>
              <NButton
                type="primary"
                size="small"
                :loading="starting"
                :disabled="isConfiguring"
                @click="onStart(false)"
              >
                开始配置
              </NButton>
              <NButton
                size="small"
                :loading="starting"
                :disabled="isConfiguring"
                @click="onStart(true)"
              >
                重新配置
              </NButton>
            </NSpace>
          </div>
          <NSpin :show="previewLoading">
            <NScrollbar style="max-height: 280px">
              <MarkdownRenderer v-if="preview?.skill_md" :content="preview.skill_md" />
              <NEmpty v-else size="small" description="无法加载 SKILL.md" />
            </NScrollbar>
          </NSpin>
        </EaCard>

        <EaCard class="sc-chat-panel">
          <div class="panel-title">Agent 配置向导</div>
          <div v-if="!activeTaskId" class="chat-placeholder ea-muted">
            点击「开始配置」或「重新配置」后，Agent 将在此引导配置并持久化。
          </div>
          <template v-else>
            <div :ref="setScrollerEl" class="chat-stream">
              <MarkdownRenderer v-if="chatMarkdown" :content="chatMarkdown" />
              <div v-else class="ea-muted">等待 Agent 输出...</div>
            </div>
            <div class="chat-input-row">
              <NInput
                v-model:value="chatInput"
                type="textarea"
                placeholder="按 Agent 提示回复配置项（KEY=VALUE 或说明文字）..."
                :autosize="{ minRows: 2, maxRows: 6 }"
                :disabled="chatSubmitting"
                @keydown.ctrl.enter="onSendChat"
              />
              <NButton
                type="primary"
                :loading="chatSubmitting"
                :disabled="!chatInput.trim()"
                @click="onSendChat"
              >
                发送
              </NButton>
            </div>
          </template>
        </EaCard>
      </div>
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
.config-skill-panel {
  max-width: 1280px;
}

.sc-layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 14px;
  align-items: start;
}

.panel-title {
  font-size: 13px;
  font-weight: 700;
  margin-bottom: 12px;
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
  width: 100%;
  text-align: left;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface);
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;

  &:hover, &.active {
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

.sc-main {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;

  h3 {
    margin: 0 0 4px;
    font-size: 16px;
  }
  p { margin: 0; font-size: 12.5px; }
}

.chat-placeholder {
  padding: 24px;
  text-align: center;
  font-size: 13px;
}

.chat-stream {
  max-height: 360px;
  overflow-y: auto;
  padding: 8px 4px;
  margin-bottom: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--surface-2);
}

.chat-input-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

@media (max-width: 900px) {
  .sc-layout {
    grid-template-columns: 1fr;
  }
}
</style>
