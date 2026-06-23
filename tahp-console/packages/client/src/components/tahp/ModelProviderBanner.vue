<script setup lang="ts">
import { NAlert, NButton } from 'naive-ui'
import { useRouter } from 'vue-router'
import { useModelProviderReadiness } from '@/composables/useModelProviderReadiness'

const router = useRouter()
const { isReady, loading } = useModelProviderReadiness()

function goConfigure() {
  router.push({ name: 'hermes.models' })
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
    智能诊断、AI 适配调试、AI 自检、AI 对话等功能依赖 Hermes Agent 调用大模型。请先在「模型管理」中添加 Provider 并配置 API Key（或完成 OAuth 授权），再使用上述功能。
    <template #action>
      <NButton size="small" type="primary" @click="goConfigure">前往模型管理</NButton>
    </template>
  </NAlert>
</template>

<style scoped lang="scss">
.model-provider-banner {
  margin-bottom: 12px;
}
</style>
