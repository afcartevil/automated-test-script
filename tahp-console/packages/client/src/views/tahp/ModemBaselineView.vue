<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const tabs = [
  { name: 'tahp.modem-baseline.workbench', label: '工作台' },
  { name: 'tahp.modem-baseline.settings', label: '配置中心' },
]

const activeName = computed(() => route.name?.toString() || 'tahp.modem-baseline.workbench')

function nav(name: string) {
  router.push({ name })
}
</script>

<template>
  <div class="page page-wide modem-page">
    <div class="ea-page-head">
      <div>
        <h1>Modem基线</h1>
        <div class="sub">Modem基线升级、Modem Patch自动化合入，自动编译烧录验证。</div>
      </div>

      <div class="ea-head-actions ea-wrap">
        <span class="ea-pill-info">真实链路</span>
        <span class="ea-pill-muted">工作台 + 配置中心</span>
      </div>
    </div>

    <div class="subnav">
      <button
        v-for="item in tabs"
        :key="item.name"
        type="button"
        class="subnav-btn"
        :class="{ active: activeName === item.name }"
        @click="nav(item.name)"
      >
        {{ item.label }}
      </button>
    </div>

    <router-view />
  </div>
</template>

<style scoped lang="scss">
.modem-page {
  padding-bottom: 20px;
}

.subnav {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.subnav-btn {
  padding: 10px 16px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface);
  color: var(--muted);
  cursor: pointer;
  font: inherit;
  font-weight: 600;
  transition: color 0.18s, border-color 0.18s, background 0.18s;

  &:hover {
    color: var(--text);
    border-color: var(--line-strong);
  }

  &.active {
    color: var(--accent);
    border-color: color-mix(in srgb, var(--accent) 40%, var(--line));
    background: var(--accent-soft);
  }
}
</style>
