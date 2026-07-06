<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NSpin } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import ProvidersPanel from '@/components/hermes/models/ProvidersPanel.vue'
import ProviderFormModal from '@/components/hermes/models/ProviderFormModal.vue'
import { useModelsStore } from '@/stores/hermes/models'
import { checkCopilotToken } from '@/api/hermes/copilot-auth'

const { t } = useI18n()
const modelsStore = useModelsStore()
const showModal = ref(false)

onMounted(async () => {
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
  <div class="config-models-panel">
    <div class="models-toolbar">
      <button type="button" class="ea-btn-primary ea-btn-sm" @click="openCreateModal">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        {{ t('models.addProvider') }}
      </button>
    </div>

    <NSpin :show="modelsStore.loading && modelsStore.providers.length === 0">
      <ProvidersPanel />
    </NSpin>

    <ProviderFormModal
      v-if="showModal"
      @close="handleModalClose"
      @saved="handleSaved"
    />
  </div>
</template>

<style scoped lang="scss">
.config-models-panel {
  max-width: 960px;
}

.models-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 14px;
}
</style>
