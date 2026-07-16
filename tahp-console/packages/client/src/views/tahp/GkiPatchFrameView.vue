<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import type { GkiPatchStatus } from '@/api/tahp/gki-patch'

const route = useRoute()

const props = defineProps<{
  status: GkiPatchStatus
  gkiPath: string
}>()

const frameSrc = computed(() => {
  const base = props.status.appBaseUrl || props.status.appUrl.replace(/\/?$/, '')
  const normalizedBase = base.endsWith('/app') ? base : `${base.replace(/\/$/, '')}/app`
  const path = props.gkiPath.startsWith('/') ? props.gkiPath : `/${props.gkiPath}`
  const params = new URLSearchParams({ embedded: '1' })
  for (const [key, value] of Object.entries(route.query)) {
    const raw = Array.isArray(value) ? value[0] : value
    if (raw == null || raw === '') continue
    params.set(key, raw)
  }
  return `${normalizedBase}${path}?${params.toString()}`
})
</script>

<template>
  <iframe
    :key="frameSrc"
    class="gki-frame"
    :src="frameSrc"
    :title="`GKI Patch ${gkiPath}`"
  />
</template>

<style scoped lang="scss">
.gki-frame {
  width: 100%;
  height: calc(100vh - 150px);
  min-height: 560px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: #fff;
}
</style>
