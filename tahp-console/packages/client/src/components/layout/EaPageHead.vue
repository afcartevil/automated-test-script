<script setup lang="ts">
defineProps<{
  title: string
  subtitle?: string
}>()
</script>

<template>
  <div class="ea-page-head">
    <div>
      <slot name="breadcrumb" />
      <h1>{{ title }}</h1>
      <div v-if="subtitle" class="sub">{{ subtitle }}</div>
    </div>
    <div v-if="$slots.actions" class="ea-head-actions">
      <slot name="actions" />
    </div>
  </div>
</template>
