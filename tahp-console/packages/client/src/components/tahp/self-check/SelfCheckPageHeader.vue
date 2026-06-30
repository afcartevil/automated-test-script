<script setup lang="ts">
import EaInnerTabs from '@/components/layout/EaInnerTabs.vue'

defineProps<{
  tabs: readonly { key: string; label: string }[]
}>()

const activeTab = defineModel<string>('activeTab', { required: true })
</script>

<template>
  <header class="self-check-page-header">
    <div class="header-main">
      <div class="header-title">
        <h1>AI 自检</h1>
        <p class="header-sub ea-muted">
          项目节点驱动，自动烧录、自动测试、AI Review，测试报告人工复核
        </p>
      </div>
      <EaInnerTabs
        v-model="activeTab"
        :tabs="[...tabs]"
        class="header-tabs"
        align="end"
      />
    </div>
  </header>
</template>

<style scoped lang="scss">
.self-check-page-header {
  margin-bottom: 16px;
}

.header-main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.header-title {
  flex: 1 1 280px;
  min-width: 0;

  h1 {
    margin: 0 0 6px;
    font-size: 22px;
    font-weight: 800;
    letter-spacing: -0.02em;
  }
}

.header-sub {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  max-width: 640px;
}

.header-tabs {
  flex-shrink: 0;
  margin-top: 2px;
}

.header-tabs :deep(.ea-itabs) {
  margin-bottom: 0;
  border-bottom: none;
}

@media (max-width: 720px) {
  .header-tabs {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>
