<script setup lang="ts">
/**
 * 公共能力 · 校准数据
 * 通过本机 Modem Meta MetaCLI 备份/恢复校准数据
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  NAlert, NButton, NInput, NProgress, NRadio, NRadioGroup, NSpin, useMessage,
} from 'naive-ui'
import EaPageHead from '@/components/layout/EaPageHead.vue'
import EaCard from '@/components/layout/EaCard.vue'
import EaPill from '@/components/layout/EaPill.vue'
import { useRfCalibMetaStore } from '@/stores/tahp/rf-calib-meta'
import { pickRfCalibCalFile } from '@/api/tahp/rf-calib-meta'
import { CONFIG_ROUTE_NAME } from '@/utils/config-navigation'

const message = useMessage()
const router = useRouter()
const store = useRfCalibMetaStore()
const logBox = ref<HTMLElement | null>(null)
/** SOP 默认收起，需要时展开查看 */
const sopOpen = ref(false)
const pickingCalFile = ref(false)

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
  if (s === 'running') return '执行中'
  if (s === 'pending') return '排队'
  return '未开始'
})

/** 推荐关机插 USB / adb 方式固定 Auto Connection，禁止误改 COM */
const comPortLocked = computed(() =>
  store.connectionStrategy === 'preloader_boot' || store.connectionStrategy === 'adb_reboot_meta',
)

watch(
  () => store.connectionStrategy,
  (strategy) => {
    if (strategy === 'preloader_boot' || strategy === 'adb_reboot_meta') {
      store.comPort = 'Auto Connection'
    }
  },
)

function goModemMetaConfig() {
  router.push({ name: CONFIG_ROUTE_NAME, query: { tab: 'form' } })
}

function toggleSop() {
  sopOpen.value = !sopOpen.value
}

async function scrollLogToBottom() {
  await nextTick()
  await nextTick()
  const el = logBox.value
  if (el) el.scrollTop = el.scrollHeight
}

async function onStart() {
  await store.start()
  if (store.error) message.error(store.error)
  else message.success(store.mode === 'backup' ? '已开始备份' : '已开始恢复')
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

async function onRefreshProbe() {
  await store.refreshProbe()
}

async function onPickCalFile() {
  if (pickingCalFile.value || store.isRunning || store.submitting) return
  pickingCalFile.value = true
  try {
    const result = await pickRfCalibCalFile()
    if (result.path) {
      store.calFilePath = result.path
      message.success('已选择校准文件')
    } else if (result.error) {
      message.error(result.error)
    }
  } catch (err) {
    message.error((err as Error).message || '选择校准文件失败')
  } finally {
    pickingCalFile.value = false
  }
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
  <div class="rf-calib-page">
    <EaPageHead
      title="校准数据"
      subtitle="与 Modem Meta GUI 相同：点开始后 MetaCLI 等待连接，关机插 USB 即进校准模式"
    />

    <EaCard class="sop-card mb">
      <div class="sop-head">
        <div>
          <h3 class="section-title sop-title">校准数据操作 SOP</h3>
          <p class="sop-sub">按下列步骤操作即可；与 Modem Meta GUI「读写校准数据」等价，无需再开 GUI。</p>
        </div>
        <NButton size="small" quaternary @click="toggleSop">
          {{ sopOpen ? '收起' : '展开' }}
        </NButton>
      </div>

      <div v-show="sopOpen" class="sop-body">
        <section class="sop-section">
          <h4>一、前置准备（首次）</h4>
          <ol>
            <li>本机已安装 Modem Meta（目录内可见 <code>META.exe</code>、<code>bin</code>、<code>configs</code> 等）。</li>
            <li>
              打开
              <NButton text type="primary" @click="goModemMetaConfig">配置 → 一键配置 → Modem 工具</NButton>
              ，填写 <strong>Modem Meta</strong> 为 <strong>META.exe 所在目录</strong> 并保存。
            </li>
            <li>示例路径：
              <code>D:\Tool\MTK\ModemMeta_v10.2412.0.02_transsion_20240428\ModemMeta_v10.2412.0.02_transsion_20240428</code>
              （不要填到某个 .exe 文件）。
            </li>
            <li>回到本页，确认顶部显示「Modem Meta 已配置」。</li>
          </ol>
        </section>

        <section class="sop-section">
          <h4>二、备份</h4>
          <ol>
            <li>模式选 <strong>备份</strong>；进 META 选 <strong>Modem Meta 连接方式（推荐）</strong>。</li>
            <li>COM 口保持 <code>Auto Connection</code>；输出文件可留空。</li>
            <li>点 <strong>开始备份</strong> → <strong>手机关机</strong> → <strong>插入 USB</strong>。</li>
            <li>日志出现 <code>Connect status: Boot ...</code> 表示 MetaCLI 正在等待，插 USB 连接后会变为 success。</li>
            <li>成功标志：任务 <strong>已完成</strong>，日志末尾有 <code>========== 备份完成 ==========</code>。</li>
          </ol>
        </section>

        <section class="sop-section">
          <h4>三、恢复</h4>
          <ol>
            <li>模式选 <strong>恢复</strong>，填写待写入的校准数据 <code>.ini</code> 路径。</li>
            <li>
              <strong>校准文件从哪来：</strong>
              若本机参数已丢失，可将<strong>其它同配置机器</strong>备份导出后写入恢复；
              也可从制造资料目录获取对应配置的校准数据：
              <code>\\sh-nas\Dcc\03.项目文件\01.项目文件\01.PCBA项目\制造资料\射频校准文件</code>
            </li>
            <li>进 META 选推荐方式 → 点 <strong>开始恢复</strong> → 关机 → 插 USB。</li>
            <li>成功标志：任务 <strong>已完成</strong>，日志末尾有 <code>========== 恢复完成 ==========</code>，且含 <code>Write calibration file done</code>。</li>
          </ol>
        </section>

        <section class="sop-section">
          <h4>四、结果判定（重要）</h4>
          <ul>
            <li><strong>以任务状态 + 末尾「备份/恢复完成」为准</strong>，不要只看 MetaCLI 中间的 Error。</li>
            <li>IMEI 默认不备份/不还原；日志里相关 Failed 会标注「已默认跳过」，任务仍显示 <strong>执行完成</strong>（无警告）。</li>
            <li>勿同时按 Vol+ 与 Vol-（会进 Recovery，不是校准 META）。</li>
          </ul>
        </section>
      </div>
    </EaCard>

    <NAlert
      v-if="store.probe && !store.probe.available"
      type="warning"
      class="mb"
      :title="store.probe.needs_config ? '请先配置 Modem Meta' : (store.probe.reason || 'MetaCLI 不可用')"
    >
      <p>{{ store.probe.reason || '请先完成工具配置。' }}</p>
      <NButton size="small" type="warning" class="mt-btn" @click="goModemMetaConfig">
        前往一键配置
      </NButton>
    </NAlert>

    <NAlert
      v-else-if="store.probe?.available && store.probe.meta_root"
      type="success"
      class="mb compact-alert"
      title="Modem Meta 已配置"
    >
      安装目录：<code>{{ store.probe.meta_root }}</code>
      （来自「配置 → 一键配置 → Modem 工具」）
      <NButton size="tiny" quaternary class="mt-btn-inline" @click="onRefreshProbe">重新检测</NButton>
    </NAlert>

    <div class="layout">
      <EaCard class="form-panel">
        <h3 class="section-title">操作</h3>

        <NRadioGroup v-model:value="store.mode" class="mode-group">
          <NRadio value="backup">备份（Upload → Save）</NRadio>
          <NRadio value="restore">恢复（Load → Download）</NRadio>
        </NRadioGroup>

        <label class="field-label mt">进 META 方式</label>
        <NRadioGroup v-model:value="store.connectionStrategy" class="mode-group">
          <NRadio value="preloader_boot">Modem Meta 连接方式（推荐 · 关机插 USB）</NRadio>
          <NRadio value="meta_port">已在 META · 手动/自动 COM</NRadio>
          <NRadio value="adb_reboot_meta">adb reboot meta（仅部分工程版）</NRadio>
        </NRadioGroup>

        <label v-if="store.mode === 'restore'" class="field-label mt">校准数据文件（CalibrationFilePath）</label>
        <div v-if="store.mode === 'restore'" class="path-pick-row">
          <NInput
            v-model:value="store.calFilePath"
            placeholder="请选择待写入设备的校准数据 .ini 文件"
            readonly
            :disabled="store.isRunning || store.submitting"
          />
          <NButton
            :loading="pickingCalFile"
            :disabled="store.isRunning || store.submitting"
            @click="onPickCalFile"
          >
            选择文件
          </NButton>
        </div>
        <p v-if="store.mode === 'restore'" class="field-hint">
          通过本机文件对话框选择；须为完整路径的校准数据 <code>.ini</code>（非目录）。
        </p>

        <label v-if="store.mode === 'backup'" class="field-label mt">输出文件（可选）</label>
        <NInput
          v-if="store.mode === 'backup'"
          v-model:value="store.outputCalPath"
          placeholder="须为 .ini 文件路径，如 D:\backup\calibration_data.ini；留空则写到工程 reports/rf-calib-meta/<任务ID>/"
          :disabled="store.isRunning || store.submitting"
        />
        <p v-if="store.mode === 'backup'" class="field-hint">
          勿填目录。留空时默认输出到 <code>reports/rf-calib-meta/</code>（勿依赖隐藏目录 <code>.tahp-config</code>，MetaCLI 常写失败）。
        </p>

        <label class="field-label mt">COM 口</label>
        <NInput
          v-model:value="store.comPort"
          :placeholder="comPortLocked ? 'Auto Connection' : '如 COM25，或留空自动检测'"
          :disabled="store.isRunning || store.submitting || comPortLocked"
          :readonly="comPortLocked"
        />
        <p v-if="comPortLocked" class="field-hint">
          当前进 META 方式使用 Auto Connection，COM 口已锁定，避免误改导致连接失败。
          仅「已在 META」时可手动填写 COM。
        </p>

        <p class="hint">
          推荐流程：点「开始」→ 关机 → 插 USB。详见上方 SOP。IMEI 默认排除，不计入警告。
        </p>

        <NAlert
          v-if="store.connectionStrategy === 'preloader_boot'"
          type="info"
          class="mb compact-alert"
          title="操作顺序（与 Modem Meta GUI 相同）"
        >
          ① 点「开始备份/恢复」→ ② 手机关机 → ③ 插入 USB。
          日志出现 <code>Connect status: Boot ...</code> 表示 MetaCLI 正在等待，插 USB 后连接后会变为 success。
        </NAlert>

        <div class="actions">
          <NButton
            type="primary"
            :loading="store.submitting"
            :disabled="store.isRunning || !store.canStart"
            @click="onStart"
          >
            {{ store.mode === 'backup' ? '开始备份' : '开始恢复' }}
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
            <span class="hi-name">{{ item.label }} · {{ item.mode }}</span>
            <EaPill>{{ item.status }}</EaPill>
          </button>
        </div>
      </EaCard>

      <EaCard class="run-panel">
        <div class="run-head">
          <div>
            <h3 class="section-title">
              {{ store.currentRun?.label || '运行状态' }}
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
          v-if="store.currentRun?.status === 'completed'"
          type="success"
          class="mb"
          title="执行完成"
        >
          <div class="paths">
            <div v-if="store.currentRun.output_cal_path || store.currentRun.cal_file_path">
              <strong>校准文件：</strong>
              <code>{{ store.currentRun.output_cal_path || store.currentRun.cal_file_path }}</code>
            </div>
            <div v-if="store.currentRun.init_file_path">
              <strong>Init 文件：</strong><code>{{ store.currentRun.init_file_path }}</code>
            </div>
          </div>
        </NAlert>

        <NAlert
          v-if="store.currentRun?.error"
          type="error"
          class="mb"
          :title="store.currentRun.error"
        />

        <div class="log-panel">
          <div class="log-chrome">
            <span class="log-dots" aria-hidden="true">
              <i /><i /><i />
            </span>
            <span class="log-chrome-title">MetaCLI</span>
            <span class="log-chrome-meta">
              {{ store.liveLines.length ? `${store.liveLines.length} 行` : '待命' }}
            </span>
          </div>
          <div ref="logBox" class="log-box" :class="{ 'is-empty': !store.liveLines.length }">
            <div v-if="!store.liveLines.length" class="log-idle">
              <div class="log-idle-glyph" aria-hidden="true">
                <svg viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <rect x="6" y="10" width="36" height="28" rx="4" stroke="currentColor" stroke-width="1.5" opacity="0.55" />
                  <path d="M12 20h10M12 26h18M12 32h14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" opacity="0.4" />
                  <circle cx="36" cy="18" r="5.5" fill="currentColor" opacity="0.12" />
                  <path d="M34.2 18h3.6M36 16.2v3.6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />
                </svg>
              </div>
              <p class="log-idle-title">等待任务开始</p>
              <p class="log-idle-desc">点「开始备份/恢复」后，此处实时显示 MetaCLI 连接与读写日志</p>
              <ul class="log-idle-hints">
                <li>Connect status: Boot … → 正在等待插 USB</li>
                <li>Connect target success → 已连上，开始读写</li>
              </ul>
            </div>
            <pre v-else class="log-pre">{{ store.liveLines.join('\n') }}</pre>
          </div>
        </div>
      </EaCard>
    </div>
  </div>
</template>

<style scoped lang="scss">
.rf-calib-page {
  padding: 0 4px 24px;
}
.mb { margin-bottom: 12px; }
.mt { margin-top: 12px; }
.mt-btn { margin-top: 8px; }
.mt-btn-inline { margin-left: 8px; vertical-align: middle; }
.sop-card {
  border: 1px solid color-mix(in srgb, var(--ea-primary, #2f6fed) 28%, var(--ea-border, #e8e8e8));
  background: color-mix(in srgb, var(--ea-primary, #2f6fed) 4%, transparent);
}
.sop-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.sop-title { margin-bottom: 4px; }
.sop-sub {
  margin: 0;
  font-size: 12px;
  color: var(--ea-text-secondary, #666);
  line-height: 1.45;
}
.sop-body {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--ea-border, #e8e8e8);
}
.sop-section {
  margin-bottom: 14px;
  &:last-child { margin-bottom: 0; }
  h4 {
    margin: 0 0 6px;
    font-size: 13px;
    font-weight: 600;
  }
  ol, ul {
    margin: 0;
    padding-left: 1.25rem;
    font-size: 13px;
    line-height: 1.65;
    color: var(--ea-text, #333);
  }
  code {
    font-size: 11px;
    word-break: break-all;
  }
}
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
.field-hint {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--ea-text-secondary, #888);
  line-height: 1.45;
}
.path-pick-row {
  display: flex;
  gap: 8px;
  align-items: center;
  :deep(.n-input) { flex: 1; min-width: 0; }
  .n-button { flex-shrink: 0; }
}
.mode-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}
.hint {
  margin: 8px 0 12px;
  font-size: 12px;
  color: var(--ea-text-secondary, #888);
  line-height: 1.5;
  code { font-size: 11px; }
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
  code { word-break: break-all; }
}
.warn-line { margin: 0 0 8px; }
.log-panel {
  margin-top: 4px;
  border: 1px solid color-mix(in srgb, #5b7c99 35%, var(--ea-border, #e8e8e8));
  border-radius: 10px;
  overflow: hidden;
  background: #0b1220;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}
.log-chrome {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: linear-gradient(180deg, #182233 0%, #121a27 100%);
  border-bottom: 1px solid rgba(120, 150, 180, 0.18);
}
.log-dots {
  display: inline-flex;
  gap: 5px;
  i {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    display: block;
    &:nth-child(1) { background: #ff5f57; }
    &:nth-child(2) { background: #febc2e; }
    &:nth-child(3) { background: #28c840; }
  }
}
.log-chrome-title {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: #c8d6e5;
}
.log-chrome-meta {
  margin-left: auto;
  font-size: 11px;
  color: #7f92a8;
  font-variant-numeric: tabular-nums;
}
.log-box {
  height: min(52vh, 480px);
  color: #d7e0ea;
  padding: 12px 14px;
  overflow: auto;
  background:
    radial-gradient(120% 80% at 50% -10%, rgba(56, 120, 180, 0.14), transparent 55%),
    linear-gradient(180deg, #0e1624 0%, #0b1220 100%);
  &.is-empty {
    display: flex;
    align-items: center;
    justify-content: center;
  }
}
.log-idle {
  max-width: 360px;
  text-align: center;
  padding: 12px 8px 20px;
}
.log-idle-glyph {
  width: 52px;
  height: 52px;
  margin: 0 auto 12px;
  color: #7eb6e8;
  opacity: 0.9;
  svg { width: 100%; height: 100%; display: block; }
}
.log-idle-title {
  margin: 0 0 6px;
  font-size: 14px;
  font-weight: 600;
  color: #e8eef6;
  letter-spacing: 0.02em;
}
.log-idle-desc {
  margin: 0 0 14px;
  font-size: 12px;
  line-height: 1.55;
  color: #8fa3b8;
}
.log-idle-hints {
  margin: 0;
  padding: 10px 12px;
  list-style: none;
  text-align: left;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(126, 182, 232, 0.12);
  li {
    position: relative;
    padding-left: 12px;
    font-size: 11px;
    line-height: 1.6;
    color: #9db0c4;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 0.55em;
      width: 5px;
      height: 5px;
      border-radius: 50%;
      background: #4d8fbf;
    }
    & + li { margin-top: 4px; }
  }
}
.compact-alert { margin-top: 8px; }
.log-pre {
  margin: 0;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
