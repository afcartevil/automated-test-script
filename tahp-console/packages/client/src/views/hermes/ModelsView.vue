<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NSpin } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import ProvidersPanel from '@/components/hermes/models/ProvidersPanel.vue'
import ProviderFormModal from '@/components/hermes/models/ProviderFormModal.vue'
import { useModelsStore } from '@/stores/hermes/models'
import { checkCopilotToken } from '@/api/hermes/copilot-auth'
import EaPageHead from '@/components/layout/EaPageHead.vue'

const { t } = useI18n()
const modelsStore = useModelsStore()
const showModal = ref(false)

onMounted(async () => {
  // 先 invalidate 后端 copilot 缓存（gh logout / VS Code 退出后下一次 list 立刻反映），
  // 再拉 providers 与 appStore 的模型显示名配置。check-token 失败不阻断。
  try { await checkCopilotToken() } catch { /* ignore */ }
  await modelsStore.fetchProviders()
})

function openCreateModal() {
  showModal.value = true
}

function handleModalClose() {
  showModal.value = false
}

async function handleSaved() {
  await modelsStore.fetchProviders()
  handleModalClose()
}
</script>

<template>
  <div class="page models-view">
    <EaPageHead :title="t('models.title')">
      <template #actions>
        <button type="button" class="ea-btn-primary ea-btn-sm" @click="openCreateModal">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          {{ t('models.addProvider') }}
        </button>
      </template>
    </EaPageHead>

    <div class="models-content">
      <NSpin :show="modelsStore.loading && modelsStore.providers.length === 0">
        <ProvidersPanel />
      </NSpin>
    </div>

    <ProviderFormModal
      v-if="showModal"
      @close="handleModalClose"
      @saved="handleSaved"
    />
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.models-view {
  height: calc(100 * var(--vh));
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.models-content {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
</style>
