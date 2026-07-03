<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'
import { NButton, useMessage } from 'naive-ui'
import ModemBaselineConfigCard from '@/components/tahp/modem-baseline/ModemBaselineConfigCard.vue'
import ModemBaselineHistoryPanel from '@/components/tahp/modem-baseline/ModemBaselineHistoryPanel.vue'
import ModemBaselineStagePanel from '@/components/tahp/modem-baseline/ModemBaselineStagePanel.vue'
import { useModemBaseline } from '@/composables/useModemBaseline'

const message = useMessage()
const {
  config,
  runs,
  selectedRun,
  selectedRunId,
  conflictFiles,
  logContent,
  loading,
  starting,
  continuing,
  refreshing,
  errorMessage,
  statusMeta,
  stageItems,
  metrics,
  initialize,
  loadDefaults,
  selectRun,
  startRun,
  continueRun,
  refreshConflicts,
  openConflictFile,
  closeEventSource,
} = useModemBaseline()

const summaryText = computed(() => statusMeta.value.summary)

function applyConfig(nextValue: typeof config.value) {
  config.value = { ...nextValue }
}

function toneClass(tone: string) {
  switch (tone) {
    case 'success':
      return 'ea-pill-ok'
    case 'warn':
      return 'ea-pill-warn'
    case 'error':
      return 'ea-pill-err'
    case 'accent':
    case 'info':
      return 'ea-pill-info'
    default:
      return 'ea-pill-muted'
  }
}

async function handleLoadDefaults() {
  try {
    await loadDefaults()
    message.success('已重新加载默认配置')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleStart() {
  try {
    await startRun()
    message.success('已启动 Modem 基线任务')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleContinueRun() {
  try {
    await continueRun()
    message.success('已发送继续执行请求')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleRefreshConflicts() {
  try {
    await refreshConflicts()
    message.success('已刷新冲突状态')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleOpenConflictFile(file: string) {
  try {
    await openConflictFile(file)
    message.success('已尝试打开冲突文件')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

onMounted(() => {
  void initialize()
})

onUnmounted(() => {
  closeEventSource()
})
</script>

<template>
  <div class="page page-wide modem-page">
    <div class="ea-page-head">
      <div>
        <h1>Modem基线</h1>
        <div class="sub">在 EasyAdapter 内统一承接 Modem 基线升级、冲突停驻、日志追踪与历史回看。</div>
      </div>

      <div class="ea-head-actions ea-wrap">
        <span class="ea-pill-info">真实链路</span>
        <span :class="toneClass(statusMeta.tone)">{{ statusMeta.label }}</span>
      </div>
    </div>

    <div v-if="errorMessage" class="preview-note">
      <strong>接入异常</strong>
      <span>{{ errorMessage }}</span>
    </div>

    <div class="main-grid">
      <div class="ea-stack">
        <ModemBaselineConfigCard
          :model-value="config"
          :loading="starting || loading"
          @update:model-value="applyConfig"
          @load-defaults="handleLoadDefaults"
          @start="handleStart"
        />

        <div class="ea-card">
          <div class="ea-section-title">运行提示</div>
          <div class="tips">
            <div class="tip-item">
              <span class="ea-dot-live" />
              <div>
                <strong>人工处理优先</strong>
                <p>冲突阶段只停驻提示，不做自动解冲突，保持现有工作方式不变。</p>
              </div>
            </div>
            <div class="tip-item">
              <span class="tip-chip">01</span>
              <div>
                <strong>接线说明</strong>
                <p>当前页面已接默认配置、任务启动、SSE 日志、冲突刷新、继续执行与打开冲突文件。</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="ea-stack">
        <ModemBaselineStagePanel
          v-if="selectedRun"
          :run="selectedRun"
          :items="stageItems"
          :summary="summaryText"
          :refreshing="refreshing"
          :continuing="continuing"
          @refresh-conflicts="handleRefreshConflicts"
          @continue-run="handleContinueRun"
        />

        <div v-else class="ea-card conflict-empty">暂无运行记录，填写配置后可直接启动首个基线任务。</div>

        <div class="ea-card ea-stack">
          <div class="console-head">
            <div>
              <div class="ea-section-title">实时日志</div>
              <h3>执行输出</h3>
            </div>
            <span class="ea-pill-muted">Run {{ selectedRun?.runId || '—' }}</span>
          </div>
          <div class="ea-mon-output">{{ logContent || '暂无日志输出' }}</div>
        </div>

        <div class="ea-card ea-stack">
          <div class="console-head">
            <div>
              <div class="ea-section-title">冲突工作区</div>
              <h3>待处理文件</h3>
            </div>
            <span :class="conflictFiles.length ? 'ea-pill-warn' : 'ea-pill-ok'">
              {{ conflictFiles.length ? `${conflictFiles.length} 个条目` : '当前无冲突' }}
            </span>
          </div>

          <div v-if="conflictFiles.length" class="conflict-list">
            <div v-for="file in conflictFiles" :key="file" class="conflict-item">
              <div>
                <strong>{{ file }}</strong>
                <p>研发手动处理完成后，请先点“刷新冲突”，确认清空后再继续执行。</p>
              </div>
              <div class="conflict-actions">
                <span class="ea-pill-warn">待处理</span>
                <NButton secondary size="small" @click="handleOpenConflictFile(file)">打开文件</NButton>
              </div>
            </div>
          </div>

          <div v-else class="conflict-empty">
            当前任务没有冲突文件；如果刚处理过冲突，请点击“刷新冲突”确认状态。
          </div>
        </div>
      </div>

      <div class="ea-stack">
        <div class="ea-card">
          <div class="ea-section-title">任务摘要</div>
          <div class="ea-meta-grid modem-meta-grid">
            <div
              v-for="item in metrics"
              :key="item.label"
              class="mg"
              :class="{ 'mg-wide': item.label === '工作区' }"
            >
              <div class="mg-k">{{ item.label }}</div>
              <div class="mg-v">{{ item.value }}</div>
            </div>
          </div>
        </div>

        <ModemBaselineHistoryPanel
          :runs="runs"
          :selected-run-id="selectedRunId"
          @select="selectRun"
        />
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.modem-page {
  padding-bottom: 20px;
}

.preview-note {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 16px;
  border-radius: 14px;
  background: var(--amber-bg);
  color: var(--amber-fg);
  border: 1px solid color-mix(in srgb, var(--amber-ic) 20%, transparent);
  margin-bottom: 16px;

  strong {
    font-size: 13px;
  }

  span {
    font-size: 12.5px;
  }
}

.main-grid {
  display: grid;
  grid-template-columns: minmax(320px, 0.95fr) minmax(420px, 1.2fr) minmax(300px, 0.85fr);
  gap: 16px;
  align-items: start;
}

.tips {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tip-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  padding: 14px 16px;
  border-radius: 14px;
  background: var(--bg);
  border: 1px solid var(--line);

  strong {
    display: block;
    font-size: 14px;
    color: var(--text);
  }

  p {
    margin-top: 4px;
    color: var(--muted);
    font-size: 12.5px;
  }
}

.tip-chip {
  width: 24px;
  height: 24px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 11px;
  font-weight: 800;
}

.console-head h3 {
  font-size: 18px;
  font-weight: 700;
  color: var(--head);
}

.ea-mon-output {
  height: 320px;
  min-height: 320px;
  max-height: 320px;
  overflow: auto;
}

.conflict-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.conflict-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border-radius: 14px;
  border: 1px solid var(--line);
  background: var(--bg);

  strong {
    display: block;
    font-size: 13px;
    color: var(--text);
    word-break: break-word;
    overflow-wrap: anywhere;
  }

  p {
    margin-top: 4px;
    font-size: 12px;
    color: var(--muted);
  }

  > div:first-child {
    flex: 1;
    min-width: 0;
  }
}

.conflict-empty {
  padding: 18px;
  border-radius: 14px;
  border: 1px dashed var(--line-strong);
  background: var(--bg);
  color: var(--muted);
  font-size: 13px;
}

.modem-meta-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));

  .mg {
    min-width: 0;
  }

  .mg-wide {
    grid-column: 1 / -1;
  }

  .mg-k {
    font-size: 12px;
    margin-bottom: 6px;
  }

  .mg-v {
    font-size: 15px;
    line-height: 1.5;
    word-break: break-word;
    overflow-wrap: anywhere;
    white-space: normal;
  }
}

@media (max-width: 1200px) {
  .main-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .preview-note,
  .conflict-item,
  .conflict-actions {
    flex-direction: column;
    align-items: flex-start;
  }
}

.conflict-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 0 0 auto;
  justify-content: flex-end;
  min-width: 128px;
}
</style>
