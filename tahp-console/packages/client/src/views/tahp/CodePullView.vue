<script setup lang="ts">
/**
 * 公共能力 · 代码拉取
 * 双 repo init → Bridge/runner → 堡垒机 mkdir + init + repo sync -c（system 再 vendor）
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  NAlert, NButton, NEmpty, NInput, NProgress, NSpin, useMessage,
} from 'naive-ui'
import EaPageHead from '@/components/layout/EaPageHead.vue'
import EaCard from '@/components/layout/EaCard.vue'
import EaPill from '@/components/layout/EaPill.vue'
import { useCodePullStore } from '@/stores/tahp/code-pull'

const message = useMessage()
const store = useCodePullStore()
const logBox = ref<HTMLElement | null>(null)

const statusVariant = computed(() => {
  const s = store.currentRun?.status
  if (s === 'completed') return 'ok' as const
  if (s === 'failed') return 'err' as const
  if (s === 'cancelled') return 'warn' as const
  if (s === 'running' || s === 'pending') return 'info' as const
  return 'muted' as const
})

const statusLabel = computed(() => {
  const s = store.currentRun?.status
  if (s === 'completed') return '已完成'
  if (s === 'failed') return '失败'
  if (s === 'cancelled') return '已取消'
  if (s === 'running') return '拉取中'
  if (s === 'pending') return '排队'
  return '未开始'
})

const failedRepos = computed(() => store.currentRun?.failed_repos || [])

async function scrollLogToBottom() {
  await nextTick()
  await nextTick()
  const el = logBox.value
  if (el) el.scrollTop = el.scrollHeight
}

async function onStart() {
  await store.start()
  if (store.error) message.error(store.error)
  else message.success('已开始拉取')
  await scrollLogToBottom()
}

async function onCancel() {
  await store.cancel()
  message.info('已请求取消')
}

async function onOpenRun(runId: string) {
  await store.openRun(runId)
  await scrollLogToBottom()
}

watch(
  () => [store.liveLines.length, store.currentRunId, store.currentRun?.log_tail?.length] as const,
  async () => {
    await scrollLogToBottom()
  },
)

onMounted(async () => {
  await store.refreshProbe()
  await store.refreshHistory()
  const running = store.history.find(h => h.status === 'running' || h.status === 'pending')
  if (running) {
    await onOpenRun(running.run_id)
  }
})

onBeforeUnmount(() => {
  store.dispose()
})
</script>

<template>
  <div class="code-pull-page">
    <EaPageHead
      title="代码拉取"
      subtitle="在堡垒机上对 system / vendor 分别执行 repo init 与 repo sync -c -j64；自动拉起 Bridge，全程免确认"
    />

    <NAlert
      v-if="store.probe && !store.probe.available"
      type="warning"
      class="mb"
      :title="store.probe.reason || '代码拉取能力不可用'"
    >
      请确认本机已安装 harness CLI，且齐治 Bridge / remote-runner 可用。
    </NAlert>

    <div class="layout">
      <EaCard class="form-panel">
        <h3 class="section-title">新建拉取</h3>

        <label class="field-label">System · repo init 命令</label>
        <NInput
          v-model:value="store.systemRepoInit"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 6 }"
          placeholder="repo init -u ssh://… -b … -m ….xml --repo-url …"
          :disabled="store.isRunning || store.submitting"
        />

        <label class="field-label mt">Vendor · repo init 命令</label>
        <NInput
          v-model:value="store.vendorRepoInit"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 6 }"
          placeholder="repo init -u ssh://… -b … -m ….xml --repo-url …"
          :disabled="store.isRunning || store.submitting"
        />

        <p class="hint">
          目录约定：<code>/work/code/$USER/code-pull/&lt;runId&gt;/system|vendor</code>
          （Windows 对应 mapped-root 下同名相对路径）。先 system 后 vendor，各执行 init 再 <code>repo sync -c -j64</code>。全部仓库成功才算完成。
        </p>

        <div class="actions">
          <NButton
            type="primary"
            :loading="store.submitting"
            :disabled="store.isRunning || !store.canStart"
            @click="onStart"
          >
            开始拉取
          </NButton>
          <NButton
            v-if="store.isRunning"
            quaternary
            type="warning"
            @click="onCancel"
          >
            取消
          </NButton>
        </div>

        <div v-if="store.history.length" class="history">
          <h3 class="section-title">最近任务</h3>
          <button
            v-for="item in store.history"
            :key="item.run_id"
            type="button"
            class="history-item"
            :class="{ active: item.run_id === store.currentRunId }"
            @click="onOpenRun(item.run_id)"
          >
            <span class="hi-name">{{ item.project_name }}</span>
            <EaPill>{{ item.status }}</EaPill>
          </button>
        </div>
      </EaCard>

      <EaCard class="run-panel">
        <div class="run-head">
          <div>
            <h3 class="section-title">
              {{ store.currentRun?.project_name || '运行状态' }}
            </h3>
            <div class="meta">
              <EaPill :variant="statusVariant">{{ statusLabel }}</EaPill>
              <span v-if="store.currentRun?.phase" class="phase">{{ store.currentRun.phase }}</span>
              <span v-if="store.currentRun?.message" class="msg">{{ store.currentRun.message }}</span>
            </div>
          </div>
          <NSpin v-if="store.loading" size="small" />
        </div>

        <NProgress
          v-if="store.currentRun"
          type="line"
          :percentage="Math.min(100, Number(store.currentRun.progress || 0))"
          :status="store.currentRun.status === 'failed' ? 'error' : store.currentRun.status === 'completed' ? 'success' : 'default'"
          class="mb"
        />

        <NAlert
          v-if="store.currentRun?.status === 'completed' || store.currentRun?.system_path_win"
          :type="store.currentRun?.status === 'completed' ? 'success' : 'info'"
          class="mb"
          :title="store.currentRun?.status === 'completed' ? '拉取完成 — 代码路径' : '已分配目录'"
        >
          <div class="paths">
            <div><strong>System Win：</strong><code>{{ store.currentRun.system_path_win || '—' }}</code></div>
            <div><strong>System Linux：</strong><code>{{ store.currentRun.system_path_linux || '—' }}</code></div>
            <div><strong>Vendor Win：</strong><code>{{ store.currentRun.vendor_path_win || '—' }}</code></div>
            <div><strong>Vendor Linux：</strong><code>{{ store.currentRun.vendor_path_linux || '—' }}</code></div>
            <div v-if="store.currentRun.mapped_root">
              <strong>mapped_root：</strong><code>{{ store.currentRun.mapped_root }}</code>
            </div>
          </div>
        </NAlert>

        <NAlert
          v-if="store.currentRun?.error"
          type="error"
          class="mb"
          :title="store.currentRun.error"
        />

        <NAlert
          v-if="failedRepos.length"
          type="warning"
          class="mb"
          :title="`未成功拉取的仓库（${failedRepos.length}）— 任务仍计为失败`"
        >
          <ul class="failed-list">
            <li v-for="item in failedRepos" :key="`${item.scope}-${item.project}`">
              <code>{{ item.scope ? `[${item.scope}] ` : '' }}{{ item.project }}</code>
              <span class="failed-reason">{{ item.reason }}</span>
            </li>
          </ul>
        </NAlert>

        <h3 class="section-title">实时日志</h3>
        <div ref="logBox" class="log-box">
          <NEmpty v-if="!store.liveLines.length" description="开始拉取后显示 Bridge / repo init / sync 进度" />
          <pre v-else class="log-pre">{{ store.liveLines.join('\n') }}</pre>
        </div>
      </EaCard>
    </div>
  </div>
</template>

<style scoped lang="scss">
.code-pull-page {
  padding: 0 4px 24px;
}
.mb { margin-bottom: 12px; }
.mt { margin-top: 12px; }
.layout {
  display: grid;
  grid-template-columns: minmax(300px, 420px) 1fr;
  gap: 16px;
  align-items: start;
}
@media (max-width: 960px) {
  .layout { grid-template-columns: 1fr; }
}
.section-title {
  margin: 0 0 10px;
  font-size: 15px;
  font-weight: 600;
}
.field-label {
  display: block;
  margin-bottom: 6px;
  font-size: 13px;
  color: var(--ea-text-secondary, #666);
}
.hint {
  margin: 8px 0 12px;
  font-size: 12px;
  color: var(--ea-text-secondary, #888);
  line-height: 1.5;
  code {
    font-size: 11px;
  }
}
.actions {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.history {
  border-top: 1px solid var(--ea-border, #e8e8e8);
  padding-top: 12px;
}
.history-item {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 10px;
  margin-bottom: 6px;
  border: 1px solid var(--ea-border, #e8e8e8);
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  text-align: left;
  &:hover, &.active {
    border-color: var(--ea-primary, #2f6fed);
    background: rgba(47, 111, 237, 0.04);
  }
}
.hi-name {
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.run-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}
.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--ea-text-secondary, #666);
}
.paths {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  code {
    word-break: break-all;
  }
}
.failed-list {
  margin: 0;
  padding-left: 18px;
  max-height: 220px;
  overflow: auto;
  li {
    margin-bottom: 6px;
    font-size: 12px;
    line-height: 1.4;
  }
  .failed-reason {
    display: block;
    color: var(--ea-text-secondary, #666);
    margin-top: 2px;
    word-break: break-word;
  }
}
.log-box {
  height: min(56vh, 520px);
  border: 1px solid var(--ea-border, #e8e8e8);
  border-radius: 8px;
  background: #0f1419;
  color: #d7e0ea;
  padding: 10px;
  overflow: auto;
}
.log-pre {
  margin: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
