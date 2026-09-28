<script setup lang="ts">
import { NAlert, NButton } from 'naive-ui'
import { useRouter } from 'vue-router'
import { useModelProviderReadiness } from '@/composables/useModelProviderReadiness'

const router = useRouter()
const { isReady, loading } = useModelProviderReadiness()

import { CONFIG_ROUTE_NAME } from '@/utils/config-navigation'

function goConfigure() {
  router.push({ name: CONFIG_ROUTE_NAME, query: { tab: 'models' } })
}
</script>

<template>
  <NAlert
    v-if="!loading && !isReady"
    type="warning"
    :show-icon="true"
    class="model-provider-banner"
  >
    <template #header>尚未配置模型 Provider</template>
    智能诊断、单项适配、质量验测、AI 对话等功能依赖 Hermes Agent 调用大模型。请先在「配置 → 模型管理」中添加 Provider 并配置 API Key（或完成 OAuth 授权），再使用上述功能。
    <div class="model-provider-banner__actions">
      <NButton size="small" type="primary" @click="goConfigure">前往配置</NButton>
    </div>
  </NAlert>
</template>

<style scoped lang="scss">
.model-provider-banner {
  margin-bottom: 12px;
}

.model-provider-banner__actions {
  margin-top: 10px;
}
</style>
