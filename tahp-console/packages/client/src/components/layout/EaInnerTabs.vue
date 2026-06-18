<script setup lang="ts">
const props = defineProps<{
  tabs: { key: string; label: string; disabled?: boolean }[]
  modelValue: string
}>()

const emit = defineEmits<{ 'update:modelValue': [key: string] }>()

function select(key: string, disabled?: boolean) {
  if (disabled) return
  emit('update:modelValue', key)
}
</script>

<template>
  <div class="ea-itabs">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      type="button"
      class="ea-itab"
      :class="{ active: modelValue === tab.key, disabled: tab.disabled }"
      @click="select(tab.key, tab.disabled)"
    >
      {{ tab.label }}
    </button>
  </div>
</template>
