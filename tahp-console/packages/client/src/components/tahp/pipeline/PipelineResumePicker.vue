<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { ResumePoint, ResumePointsResponse } from '@/api/tahp/adapt-pipeline'
import { listDevices, type DeviceInfo } from '@/api/tahp/device-self-check'

const props = withDefaults(defineProps<{
  data: ResumePointsResponse | null
  busy?: boolean
  reloading?: boolean
  /** 当前 run 已绑定的设备，用于预填 */
  currentDeviceId?: string | null
}>(), {
  busy: false,
  reloading: false,
})

const emit = defineEmits<{
  reload: []
  submit: [node: string, scope: 'continue' | 'restart', force: boolean, deviceId?: string]
}>()

const selectedNode = ref<string>('')
const scope = ref<'continue' | 'restart'>('continue')
const deviceId = ref('')
const devices = ref<DeviceInfo[]>([])
const devicesLoading = ref(false)
const devicesError = ref('')

const recommendedNode = computed(() => props.data?.recommended ?? '')

const needsDevice = computed(() =>
  selectedNode.value === 'flash' || selectedNode.value === 'selfcheck',
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

onMounted(() => {
  if (recommendedNode.value) selectedNode.value = recommendedNode.value
  if (props.currentDeviceId) deviceId.value = props.currentDeviceId
  void loadDevices()
})

watch(
  () => props.currentDeviceId,
  (id) => {
    if (id && !deviceId.value.trim()) deviceId.value = id
  },
)

watch(recommendedNode, (node) => {
  if (node && !selectedNode.value) selectedNode.value = node
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

const selectedPoint = computed(() =>
  props.data?.points.find(p => p.node === selectedNode.value) ?? null,
)

function choose(point: ResumePoint) {
  selectedNode.value = point.node
}

function submit() {
  if (!selectedNode.value) return
  if (needsDevice.value && !deviceId.value.trim()) {
    window.alert('续跑烧录/自检前请选择或填写设备 ID')
    return
  }
  const unsafe = selectedPoint.value?.safety === 'unsafe'
  if (unsafe && !window.confirm(`该恢复点不安全：${selectedPoint.value?.hint ?? ''}\n确认继续？`)) return
  emit(
    'submit',
    selectedNode.value,
    scope.value,
    unsafe,
    needsDevice.value ? deviceId.value.trim() : undefined,
  )
}
</script>

<template>
  <div class="resume-picker">
    <div class="head">
      <strong>恢复点选择</strong>
      <button
        type="button"
        class="link-btn"
        :disabled="reloading"
        @click="emit('reload')"
      >
        {{ reloading ? '刷新中…' : '刷新' }}
      </button>
    </div>

    <div v-if="!data" class="empty">点击刷新后加载恢复点</div>
    <template v-else>
      <label
        v-for="point in data.points"
        :key="point.node"
        class="point"
        :class="{ unsafe: point.safety === 'unsafe', active: selectedNode === point.node }"
      >
        <input
          type="radio"
          name="resume-node"
          :value="point.node"
          :checked="selectedNode === point.node"
          @change="choose(point)"
        >
        <span>{{ point.label }}</span>
        <em v-if="data.recommended === point.node" class="badge">推荐</em>
        <small v-if="point.hint">{{ point.hint }}</small>
      </label>

      <div class="scope">
        <label><input v-model="scope" type="radio" value="continue"> 增量续跑</label>
        <label><input v-model="scope" type="radio" value="restart"> 全部重来</label>
      </div>

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
        <p class="device-hint">续跑烧录/自检必须绑定设备 ID，将写入本 run。</p>
      </div>

      <button
        type="button"
        class="ea-btn-primary"
        :disabled="!selectedNode || busy || (needsDevice && !deviceId.trim())"
        @click="submit"
      >
        {{ busy ? '提交中…' : '继续' }}
      </button>
    </template>
  </div>
</template>

<style scoped lang="scss">
.resume-picker {
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 10px;
  background: var(--bg);
}
.head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.point {
  display: grid;
  grid-template-columns: 16px 1fr auto;
  gap: 8px;
  align-items: center;
  padding: 6px 4px;
  border-radius: 8px;
}
.point small {
  grid-column: 2 / -1;
  color: var(--muted);
}
.point.unsafe span { color: var(--warn); }
.point.active { background: var(--surface); }
.badge {
  color: var(--accent);
  font-size: 11px;
}
.scope {
  display: flex;
  gap: 12px;
  margin: 8px 0 12px;
  color: var(--muted);
  font-size: 12px;
}
.device-box {
  display: grid;
  gap: 8px;
  margin: 0 0 12px;
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
.empty { color: var(--faint); }
.link-btn {
  border: none;
  background: transparent;
  color: var(--accent);
  cursor: pointer;
  &:disabled { opacity: 0.55; cursor: not-allowed; }
}
</style>
