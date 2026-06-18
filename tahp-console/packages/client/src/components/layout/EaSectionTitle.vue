<script setup lang="ts">
defineProps<{ title?: string }>()
</script>

<template>
  <div class="ea-section-title">
    <slot>{{ title }}</slot>
  </div>
</template>
