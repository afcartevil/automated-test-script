<script setup lang="ts">
const props = withDefaults(defineProps<{
  variant?: 'ok' | 'info' | 'warn' | 'err' | 'muted'
}>(), { variant: 'muted' })

const cls = {
  ok: 'ea-pill-ok',
  info: 'ea-pill-info',
  warn: 'ea-pill-warn',
  err: 'ea-pill-err',
  muted: 'ea-pill-muted',
}
</script>

<template>
  <span :class="cls[variant]"><slot /></span>
</template>
