<script setup lang="ts">
export type FeatureHeroIcon = 'play' | 'shield' | 'stethoscope' | 'calendar' | 'code'

defineProps<{
  title: string
  summary: string
  tone: string
  icon?: FeatureHeroIcon
}>()

const emit = defineEmits<{
  click: []
}>()
</script>

<template>
  <button
    type="button"
    class="ea-hm-card hm-hero"
    :class="tone"
    @click="emit('click')"
  >
    <span class="hm-icon hm-icon-lg">
      <svg
        v-if="icon === 'play' || !icon"
        width="30"
        height="30"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <polygon points="5 3 19 12 5 21 5 3" />
      </svg>
      <svg
        v-else-if="icon === 'stethoscope'"
        width="30"
        height="30"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <path d="M12 9c-1.6-.6-3.2-.9-4-.9C5 8.1 3 10 3 12s2 3.9 5 3.9c.8 0 2.4-.3 4-.9" />
        <path d="M12 9c1.6-.6 3.2-.9 4-.9 3 0 5 1.9 5 3.9s-2 3.9-5 3.9c-.8 0-2.4-.3-4-.9" />
        <path d="M12 3v18" />
      </svg>
      <svg
        v-else-if="icon === 'calendar'"
        width="30"
        height="30"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
        <line x1="16" y1="2" x2="16" y2="6" />
        <line x1="8" y1="2" x2="8" y2="6" />
        <line x1="3" y1="10" x2="21" y2="10" />
      </svg>
      <svg
        v-else-if="icon === 'code'"
        width="30"
        height="30"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <polyline points="16 18 22 12 16 6" />
        <polyline points="8 6 2 12 8 18" />
      </svg>
      <svg
        v-else
        width="30"
        height="30"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    </span>
    <h2>{{ title }}</h2>
    <p>{{ summary }}</p>
  </button>
</template>

<style scoped lang="scss">
.hm-icon {
  width: 50px;
  height: 50px;
  border-radius: 15px;
  display: grid;
  place-items: center;
  background: rgba(255, 255, 255, 0.72);
}

.hm-icon-lg {
  width: 58px;
  height: 58px;
  border-radius: 17px;
}

.hm-hero {
  padding: 28px;
  width: 100%;
}

.hm-hero h2 {
  font-size: 26px;
  font-weight: 800;
  letter-spacing: -0.02em;
  margin: 16px 0 6px;
}

.hm-hero p {
  font-size: 15px;
  opacity: 0.85;
  line-height: 1.5;
  margin: 0;
}
</style>
