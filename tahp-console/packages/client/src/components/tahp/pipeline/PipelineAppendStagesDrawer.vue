<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type {
  AppendableStageKey,
  AppendCandidatesResponse,
} from '@/api/tahp/adapt-pipeline'
import { listDevices, type DeviceInfo } from '@/api/tahp/device-self-check'

const props = defineProps<{
  open: boolean
  candidates: AppendCandidatesResponse | null
  busy?: boolean
  currentDeviceId?: string | null
}>()

const emit = defineEmits<{
  close: []
  confirm: [payload: {
    stages: AppendableStageKey[]
    gerrit_skip_flash?: boolean
    device_id?: string
  }]
}>()

const STAGE_META: Record<AppendableStageKey, { label: string; desc: string }> = {
  flash: {
    label: 'AI 烧录',
    desc: '基于本轮编译产物刷机。需可用设备与刷机包路径。',
  },
  selfcheck: {
    label: 'AI 自检',
    desc: '烧录后执行冒烟/自检用例，失败可转入人工门。',
  },
  gerrit: {
    label: '提交 Gerrit',
    desc: '将适配改动按仓拆分提交。可跳过烧录/自检直达。',
  },
}

const selected = ref<AppendableStageKey[]>([])
const allowGerritOnly = ref(false)
const deviceId = ref('')
const devices = ref<DeviceInfo[]>([])
const devicesLoading = ref(false)
const devicesError = ref('')

const needsDevice = computed(() =>
  selected.value.includes('flash') || selected.value.includes('selfcheck'),
)

const deviceOptions = computed(() => {
  const opts = devices.value.map(d => ({
    label: `${d.deviceId} (${d.deviceName})`,
    value: d.deviceId,
  }))
  const current = deviceId.value.trim()
  if (current && !opts.some(o => o.value === current)) {
    opts.unshift({ label: `${current}（手输/未在列表）`, value: current })
  }
  return opts
})

watch(
  () => [props.open, props.candidates, props.currentDeviceId] as const,
  ([open, candidates, current]) => {
    if (!open || !candidates) return
    selected.value = [...candidates.available]
    allowGerritOnly.value = false
    deviceId.value = String(current || candidates.artifacts.device_id || '').trim()
    void loadDevices()
  },
  { immediate: true },
)

const orderedPreview = computed(() => {
  const order: AppendableStageKey[] = ['flash', 'selfcheck', 'gerrit']
  return order.filter(k => selected.value.includes(k))
})

async function loadDevices() {
  devicesLoading.value = true
  devicesError.value = ''
  try {
    devices.value = await listDevices()
  } catch (err) {
    devicesError.value = (err as Error).message || '扫描设备失败'
    devices.value = []
  } finally {
    devicesLoading.value = false
  }
}

function toggle(key: AppendableStageKey) {
  const next = new Set(selected.value)
  if (next.has(key)) {
    next.delete(key)
    if (key === 'flash') next.delete('selfcheck')
  } else {
    next.add(key)
    if (key === 'selfcheck') next.add('flash')
  }
  const order: AppendableStageKey[] = ['flash', 'selfcheck', 'gerrit']
  selected.value = order.filter(k => next.has(k))
}

function confirm() {
  if (!selected.value.length) return
  const onlyGerrit = selected.value.length === 1 && selected.value[0] === 'gerrit'
  if (onlyGerrit && !allowGerritOnly.value) {
    window.alert('仅追加 Gerrit 时请勾选风险确认')
    return
  }
  if (onlyGerrit && !window.confirm(props.candidates?.rules.gerrit_only_risk ?? '确认仅追加 Gerrit？')) {
    return
  }
  if (needsDevice.value && !deviceId.value.trim()) {
    window.alert('追加烧录/自检前请选择或填写设备 ID')
    return
  }
  emit('confirm', {
    stages: [...selected.value],
    gerrit_skip_flash: onlyGerrit ? true : undefined,
    device_id: needsDevice.value ? deviceId.value.trim() : undefined,
  })
}
</script>

<template>
  <div v-if="open" class="mask" @click.self="emit('close')">
    <aside class="drawer" role="dialog" aria-label="追加后续阶段">
      <header class="head">
        <div>
          <h3>追加后续阶段</h3>
          <p>在当前已完成运行上继续编排。已完成节点不会重跑，将复用本轮编译产物。</p>
        </div>
        <button type="button" class="icon-btn" aria-label="关闭" @click="emit('close')">×</button>
      </header>

      <div class="body">
        <div v-if="!candidates" class="empty">正在加载可追加阶段…</div>
        <template v-else>
          <div class="context">
            <strong>可追加 {{ candidates.available.length }} 个阶段</strong>
            <div v-if="candidates.artifacts.has_build">
              编译产物可用
              <span v-if="candidates.artifacts.pkg_path">· {{ candidates.artifacts.pkg_path }}</span>
            </div>
            <div v-else class="warn">未检测到可用编译产物，烧录阶段可能需要手工补路径</div>
            <div v-if="candidates.artifacts.device_id">已绑定设备：{{ candidates.artifacts.device_id }}</div>
            <div v-else class="muted">尚未绑定设备；追加烧录/自检时须在下方填写</div>
          </div>

          <label
            v-for="key in candidates.available"
            :key="key"
            class="option"
            :class="{ selected: selected.includes(key) }"
          >
            <input
              type="checkbox"
              :checked="selected.includes(key)"
              @change="toggle(key)"
            >
            <div>
              <div class="name">
                {{ STAGE_META[key].label }}
                <span class="tag">{{ key }}</span>
              </div>
              <div class="desc">{{ STAGE_META[key].desc }}</div>
            </div>
          </label>

          <label v-if="candidates.available.includes('gerrit')" class="risk">
            <input v-model="allowGerritOnly" type="checkbox">
            允许跳过烧录/自检，仅追加 Gerrit（需自行承担未验证风险）
          </label>

          <div v-if="needsDevice" class="device-box">
            <div class="device-head">
              <strong>目标设备</strong>
              <button type="button" class="link-btn" :disabled="devicesLoading" @click="loadDevices">
                {{ devicesLoading ? '扫描中…' : '刷新设备' }}
              </button>
            </div>
            <select v-model="deviceId" class="device-select">
              <option value="">
                {{ devicesLoading ? '正在扫描 ADB 设备…' : (devices.length ? '选择烧录/自检设备' : '未检测到设备，请手输') }}
              </option>
              <option v-for="opt in deviceOptions" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
            <input
              v-model="deviceId"
              type="text"
              class="device-input"
              placeholder="或手输设备 serial（adb devices）"
            >
            <p v-if="devicesError" class="device-err">{{ devicesError }}</p>
            <p class="device-hint">追加烧录/自检必须绑定设备 ID，将写入本 run。</p>
          </div>

          <div class="preview">
            <div class="label">确认后的执行顺序</div>
            <div class="chips">
              <template v-for="(key, idx) in orderedPreview" :key="key">
                <span v-if="idx > 0" class="arrow">→</span>
                <span class="chip">{{ STAGE_META[key].label }}</span>
              </template>
              <span v-if="!orderedPreview.length" class="muted">尚未选择</span>
            </div>
          </div>
        </template>
      </div>

      <footer class="foot">
        <div class="tip">不会修改「流程编排」全局默认；仅影响本 run。</div>
        <div class="actions">
          <button type="button" class="btn secondary" @click="emit('close')">取消</button>
          <button
            type="button"
            class="btn primary"
            :disabled="!selected.length || busy || (needsDevice && !deviceId.trim())"
            @click="confirm"
          >
            {{ busy ? '提交中…' : '确认并继续运行' }}
          </button>
        </div>
      </footer>
    </aside>
  </div>
</template>

<style scoped lang="scss">
.mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.28);
  z-index: 80;
  display: grid;
  justify-items: end;
}
.drawer {
  width: min(420px, 100%);
  height: 100%;
  background: var(--surface, #fff);
  box-shadow: -12px 0 40px rgba(15, 23, 42, 0.12);
  display: grid;
  grid-template-rows: auto 1fr auto;
}
.head {
  padding: 18px 18px 12px;
  border-bottom: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  gap: 12px;
  h3 { margin: 0; font-size: 16px; font-weight: 800; }
  p { margin: 6px 0 0; font-size: 12px; color: var(--muted); line-height: 1.55; }
}
.icon-btn {
  border: none;
  background: var(--surface-2, #f1f5f9);
  width: 28px;
  height: 28px;
  border-radius: 8px;
  color: #475569;
  font-size: 16px;
  cursor: pointer;
}
.body {
  padding: 16px 18px;
  overflow: auto;
  display: grid;
  gap: 12px;
  align-content: start;
}
.context {
  background: var(--surface-2, #f8fafc);
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 12px;
  display: grid;
  gap: 4px;
  font-size: 12px;
  color: var(--muted);
  strong { color: var(--text); font-size: 13px; }
}
.warn { color: var(--warn, #b45309); }
.muted { color: var(--faint, #9aa3b2); }
.empty { font-size: 13px; color: var(--muted); padding: 20px 0; }
.option {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 12px;
  display: grid;
  grid-template-columns: 22px 1fr;
  gap: 10px;
  cursor: pointer;
  &.selected {
    border-color: color-mix(in srgb, var(--accent, #5256d4) 45%, transparent);
    background: color-mix(in srgb, var(--accent, #5256d4) 6%, #fff);
  }
  input { margin-top: 3px; }
}
.name {
  font-size: 13px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
}
.tag {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 8px;
  border-radius: 999px;
  background: #eef2f7;
  color: #64748b;
}
.desc {
  margin-top: 4px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.5;
}
.risk {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.45;
}
.device-box {
  display: grid;
  gap: 8px;
  padding: 10px;
  border-radius: 10px;
  border: 1px solid color-mix(in srgb, var(--accent, #5256d4) 28%, transparent);
  background: color-mix(in srgb, var(--accent, #5256d4) 6%, #fff);
}
.device-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}
.device-select,
.device-input {
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 13px;
  font-family: inherit;
  background: #fff;
}
.device-hint {
  margin: 0;
  font-size: 11px;
  color: var(--muted);
  line-height: 1.4;
}
.device-err {
  margin: 0;
  font-size: 11px;
  color: var(--error, #d33b3b);
}
.link-btn {
  border: none;
  background: transparent;
  color: var(--accent, #5256d4);
  cursor: pointer;
  font-size: 12px;
  &:disabled { opacity: 0.55; cursor: not-allowed; }
}
.preview {
  border-top: 1px dashed var(--line);
  padding-top: 12px;
  display: grid;
  gap: 8px;
  .label { font-size: 12px; color: var(--muted); font-weight: 700; }
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.chip {
  font-size: 11px;
  padding: 4px 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--accent, #5256d4) 10%, #fff);
  color: var(--accent, #5256d4);
  font-weight: 650;
}
.arrow { color: var(--faint); font-size: 12px; }
.foot {
  padding: 14px 18px;
  border-top: 1px solid var(--line);
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}
.tip { font-size: 11px; color: var(--faint); line-height: 1.4; }
.actions { display: flex; gap: 8px; }
.btn {
  border: none;
  border-radius: 8px;
  padding: 8px 14px;
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  &.secondary {
    background: var(--surface-2, #f1f5f9);
    color: #334155;
  }
  &.primary {
    background: var(--accent, #5256d4);
    color: #fff;
  }
  &:disabled { opacity: 0.55; cursor: not-allowed; }
}
</style>
