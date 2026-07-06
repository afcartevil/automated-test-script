<script setup lang="ts">
import { NButton } from 'naive-ui'

const props = defineProps<{
  onlyErrors: boolean
  onlyConflicts: boolean
}>()

const emit = defineEmits<{
  'update:onlyErrors': [value: boolean]
  'update:onlyConflicts': [value: boolean]
  'jump-latest': []
}>()
</script>

<template>
  <div class="bar">
    <div class="bar-left">
      <NButton
        secondary
        size="small"
        :type="onlyErrors ? 'primary' : 'default'"
        @click="$emit('update:onlyErrors', !onlyErrors)"
      >
        只看错误
      </NButton>
      <NButton
        secondary
        size="small"
        :type="onlyConflicts ? 'primary' : 'default'"
        @click="$emit('update:onlyConflicts', !onlyConflicts)"
      >
        只看冲突
      </NButton>
    </div>
    <div class="bar-right">
      <NButton secondary size="small" @click="$emit('jump-latest')">跳到最新</NButton>
    </div>
  </div>
</template>

<style scoped lang="scss">
.bar {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.bar-left,
.bar-right {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
