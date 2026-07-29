<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { NButton, NInput, NModal, useMessage } from 'naive-ui'
import ModemBaselineRepoListCard from '@/components/tahp/modem-baseline/ModemBaselineRepoListCard.vue'
import ModemBaselineWorkspaceCard from '@/components/tahp/modem-baseline/ModemBaselineWorkspaceCard.vue'
import type { RepoProfile } from '@/api/tahp/modem-baseline'
import { useModemBaseline } from '@/composables/useModemBaseline'

const message = useMessage()
const manualRepoModalOpen = ref(false)
const manualRepoForm = reactive({
  localPath: '',
  platform: '',
})
const {
  workspaceProfile,
  repoProfiles,
  selectedRepoId,
  scanResults,
  scanWarnings,
  savingWorkspace,
  savingRepo,
  scanningRepos,
  removingRepo,
  updatingRepo,
  refreshingRepoBranches,
  initialize,
  saveWorkspace,
  saveRepo,
  removeRepo,
  updateRepo,
  refreshRepoBranchTemplates,
  scanRepos,
  chooseRepo,
} = useModemBaseline()

async function handleSaveWorkspace(value: { mappedPrefix: string; remotePrefix: string; roots: string[] }) {
  try {
    await saveWorkspace(value)
    message.success('已保存工作区配置')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleSaveRepo(value: {
  localPath: string
  platform: string
  label: string
}) {
  try {
    await saveRepo(value)
    message.success('已保存仓库配置')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleScanRepos(roots: string[]) {
  try {
    const result = await scanRepos(roots)
    message.success(`扫描完成，共发现 ${result.items.length} 个 Git 仓库`)
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

function openManualRepoModal() {
  manualRepoModalOpen.value = true
}

function closeManualRepoModal() {
  manualRepoModalOpen.value = false
}

watch(
  () => savingRepo.value,
  (value, previous) => {
    if (previous && !value && manualRepoModalOpen.value) {
      manualRepoForm.localPath = ''
      manualRepoForm.platform = ''
      manualRepoModalOpen.value = false
    }
  },
)

async function submitManualRepo() {
  const localPath = manualRepoForm.localPath.trim()
  const platform = manualRepoForm.platform.trim()
  if (!localPath || !platform) return
  await handleSaveRepo({
    localPath,
    platform,
    label: platform,
  })
}

async function handleRemoveRepo(repoId: string) {
  try {
    await removeRepo(repoId)
    message.success('已删除仓库配置')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleUpdateRepo(repoId: string, value: {
  localPath: string
  platform: string
  label: string
  branches?: RepoProfile['branches']
}) {
  try {
    await updateRepo(repoId, value)
    message.success('已更新仓库配置')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleRefreshBranches(repoId?: string) {
  try {
    await refreshRepoBranchTemplates(repoId)
    message.success(repoId ? '已触发仓库分支刷新' : '已触发全部仓库分支刷新')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

onMounted(() => {
  void initialize()
})
</script>

<template>
  <div class="settings-page">
    <div class="settings-grid">
      <div class="settings-left">
        <ModemBaselineWorkspaceCard
          :workspace-profile="workspaceProfile"
          :repos="repoProfiles"
          :selected-repo-id="selectedRepoId"
          :scan-results="scanResults"
          :scan-warnings="scanWarnings"
          :saving-workspace="savingWorkspace"
          :saving-repo="savingRepo"
          :scanning-repos="scanningRepos"
          :removing-repo="removingRepo"
          @save-workspace="handleSaveWorkspace"
          @save-repo="handleSaveRepo"
          @scan-repos="handleScanRepos"
          @open-manual-add="openManualRepoModal"
          @remove-repo="handleRemoveRepo"
        />
      </div>

      <div class="settings-right">
        <ModemBaselineRepoListCard
          class="repo-list-panel"
          fill-height
          :repos="repoProfiles"
          :selected-repo-id="selectedRepoId"
          :updating="updatingRepo"
          :removing="removingRepo"
          :refreshing-branches="refreshingRepoBranches"
          @choose="chooseRepo"
          @update="handleUpdateRepo"
          @remove="handleRemoveRepo"
          @refresh-branches="handleRefreshBranches"
        />
      </div>
    </div>

    <NModal v-model:show="manualRepoModalOpen" preset="card" title="手动新增Modem仓库" class="repo-manual-modal">
      <div class="ea-stack">
        <div class="ea-field">
          <label>本地路径</label>
          <NInput v-model:value="manualRepoForm.localPath" placeholder="例如 Z:\mtk\modem\t\GEN95\repo" />
        </div>
        <div class="ea-field">
          <label>平台</label>
          <NInput v-model:value="manualRepoForm.platform" placeholder="例如 GEN95W / GEN99U / GEN99-R2U" />
        </div>
        <div class="modal-actions">
          <NButton secondary @click="closeManualRepoModal">取消</NButton>
          <NButton
            type="primary"
            :loading="savingRepo"
            :disabled="!manualRepoForm.localPath.trim() || !manualRepoForm.platform.trim()"
            @click="submitManualRepo"
          >
            保存仓库
          </NButton>
        </div>
      </div>
    </NModal>
  </div>
</template>

<style scoped lang="scss">
.settings-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
}

.settings-grid {
  display: grid;
  grid-template-columns: minmax(380px, 1.05fr) minmax(360px, 0.95fr);
  gap: 16px;
  align-items: stretch;
  flex: 1;
  min-height: 0;
}

.settings-left,
.settings-right {
  min-width: 0;
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.settings-left > :deep(.workspace-panel),
.settings-right > :deep(.repo-list-panel) {
  flex: 1 1 auto;
  min-height: 0;
  height: 100%;
}

.repo-manual-modal {
  width: min(560px, calc(100vw - 32px));
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 1200px) {
  .settings-page,
  .settings-grid {
    height: auto;
    min-height: 0;
    overflow: visible;
  }

  .settings-grid {
    grid-template-columns: 1fr;
  }

  .settings-left,
  .settings-right {
    height: auto;
  }

  .settings-left > :deep(.workspace-panel),
  .settings-right > :deep(.repo-list-panel) {
    height: auto;
    min-height: 420px;
  }
}
</style>
