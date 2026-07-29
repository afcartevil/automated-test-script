<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { ResumePoint, ResumePointsResponse } from '@/api/tahp/adapt-pipeline'

const props = defineProps<{
  data: ResumePointsResponse | null
  busy?: boolean
}>()

const emit = defineEmits<{
  reload: []
  submit: [node: string, scope: 'continue' | 'restart', force: boolean]
}>()

const selectedNode = ref<string>('')
const scope = ref<'continue' | 'restart'>('continue')

const recommendedNode = computed(() => props.data?.recommended ?? '')

onMounted(() => {
  if (recommendedNode.value) selectedNode.value = recommendedNode.value
})

const selectedPoint = computed(() =>
  props.data?.points.find(p => p.node === selectedNode.value) ?? null,
)

function choose(point: ResumePoint) {
  selectedNode.value = point.node
}

function submit() {
  if (!selectedNode.value) return
  const unsafe = selectedPoint.value?.safety === 'unsafe'
  if (unsafe && !window.confirm(`该恢复点不安全：${selectedPoint.value?.hint ?? ''}\n确认继续？`)) return
  emit('submit', selectedNode.value, scope.value, unsafe)
}
</script>

<template>
  <div class="resume-picker">
    <div class="head">
      <strong>恢复点选择</strong>
      <button type="button" class="link-btn" @click="emit('reload')">刷新</button>
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
        />
        <span>{{ point.label }}</span>
        <em v-if="data.recommended === point.node" class="badge">推荐</em>
        <small v-if="point.hint">{{ point.hint }}</small>
      </label>

      <div class="scope">
        <label><input v-model="scope" type="radio" value="continue" /> 增量续跑</label>
        <label><input v-model="scope" type="radio" value="restart" /> 全部重来</label>
      </div>

      <button
        type="button"
        class="ea-btn-primary"
        :disabled="!selectedNode || busy"
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
.empty { color: var(--faint); }
.link-btn {
  border: none;
  background: transparent;
  color: var(--accent);
  cursor: pointer;
}
</style>
