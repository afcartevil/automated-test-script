<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { NButton, useMessage } from 'naive-ui'
import ModemBaselineRepoListCard from '@/components/tahp/modem-baseline/ModemBaselineRepoListCard.vue'
import ModemBaselineRulesDrawer from '@/components/tahp/modem-baseline/ModemBaselineRulesDrawer.vue'
import ModemBaselineWorkspaceCard from '@/components/tahp/modem-baseline/ModemBaselineWorkspaceCard.vue'
import { useModemBaseline } from '@/composables/useModemBaseline'

const message = useMessage()
const rulesDrawerOpen = ref(false)
const {
  workspaceProfile,
  repoProfiles,
  selectedRepoId,
  scanResults,
  scanWarnings,
  rules,
  loading,
  savingWorkspace,
  savingRepo,
  scanningRepos,
  removingRepo,
  updatingRepo,
  savingRule,
  deletingRule,
  initialize,
  saveWorkspace,
  saveRepo,
  removeRepo,
  updateRepo,
  scanRepos,
  chooseRepo,
  clearSelectedRepo,
  createRule,
  updateRule,
  removeRule,
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

async function handleScanRepos(root: string) {
  try {
    const result = await scanRepos(root)
    message.success(`扫描完成，共发现 ${result.items.length} 个 Git 仓库`)
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleRemoveRepo(repoId: string) {
  try {
    await removeRepo(repoId)
    message.success('已删除仓库配置')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleCreateRule(input: any) {
  try {
    await createRule(input)
    message.success('已新增规则')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleUpdateRule(ruleId: string, input: any) {
  try {
    await updateRule(ruleId, input)
    message.success('已保存规则')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleRemoveRule(ruleId: string) {
  try {
    await removeRule(ruleId)
    message.success('已删除规则')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

async function handleUpdateRepo(repoId: string, value: {
  localPath: string
  platform: string
  label: string
}) {
  try {
    await updateRepo(repoId, value)
    message.success('已更新仓库配置')
  } catch (error) {
    message.error(String((error as Error)?.message ?? error))
  }
}

onMounted(() => {
  void initialize()
})
</script>

<template>
  <div class="settings-grid">
    <div class="ea-stack">
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
        @choose-repo="chooseRepo"
        @clear-repo="clearSelectedRepo"
        @remove-repo="handleRemoveRepo"
      />

      <ModemBaselineRepoListCard
        :repos="repoProfiles"
        :selected-repo-id="selectedRepoId"
        :updating="updatingRepo"
        :removing="removingRepo"
        @choose="chooseRepo"
        @update="handleUpdateRepo"
        @remove="handleRemoveRepo"
      />
    </div>

    <div class="ea-stack">
      <div class="ea-card ea-stack">
        <div class="console-head">
          <div>
            <div class="ea-section-title">规则配置</div>
            <h3>推荐规则</h3>
            <p>规则属于低频配置项，只在接入新平台、补充分支模板或修正规则时需要维护。</p>
          </div>
          <NButton type="primary" :loading="loading" @click="rulesDrawerOpen = true">管理规则</NButton>
        </div>

        <div class="rule-summary">
          <div class="rule-summary__item">
            <span class="ea-pill-info">总规则数</span>
            <strong>{{ rules.length }}</strong>
            <p>包含默认规则与当前用户自定义规则。</p>
          </div>
          <div class="rule-summary__item">
            <span class="ea-pill-muted">说明</span>
            <strong>按用户隔离</strong>
            <p>工作区 / 仓库 / 规则都按 Owner 落盘，避免同机多人串配置。</p>
          </div>
        </div>

        <div class="tips">
          <div class="tip-item">
            <span class="tip-chip">01</span>
            <div>
              <strong>首次接入先配置</strong>
              <p>先填 Owner 和 roots，远端路径会自动按 `/work/&lt;owner&gt;/code` 生成，本地盘符也会从首条根目录自动识别，再登记常用仓库。</p>
            </div>
          </div>
          <div class="tip-item">
            <span class="tip-chip">02</span>
            <div>
              <strong>扫描只做候选</strong>
              <p>系统不会自动把扫描结果写入仓库列表，需要你明确导入或手工保存。</p>
            </div>
          </div>
          <div class="tip-item">
            <span class="tip-chip">03</span>
            <div>
              <strong>推荐规则可逐步补齐</strong>
              <p>工作台生成推荐时会优先命中规则；未命中时仍允许手动调整执行参数。</p>
            </div>
          </div>
        </div>
      </div>
    </div>

    <ModemBaselineRulesDrawer
      v-model:show="rulesDrawerOpen"
      :rules="rules"
      :saving="savingRule"
      :deleting="deletingRule"
      @create="handleCreateRule"
      @update="handleUpdateRule"
      @remove="handleRemoveRule"
    />
  </div>
</template>

<style scoped lang="scss">
.settings-grid {
  display: grid;
  grid-template-columns: minmax(380px, 1.1fr) minmax(340px, 0.9fr);
  gap: 16px;
  align-items: start;
}

.console-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;

  h3 {
    font-size: 18px;
    font-weight: 700;
    color: var(--head);
  }

  p {
    margin-top: 4px;
    font-size: 13px;
    color: var(--muted);
  }
}

.rule-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.rule-summary__item,
.tip-item {
  padding: 14px 16px;
  border-radius: 14px;
  background: var(--bg);
  border: 1px solid var(--line);
}

.rule-summary__item strong,
.tip-item strong {
  display: block;
  margin-top: 10px;
  font-size: 16px;
  color: var(--text);
}

.rule-summary__item p,
.tip-item p {
  margin-top: 6px;
  font-size: 12px;
  color: var(--muted);
}

.tips {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tip-item {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.tip-chip {
  width: 24px;
  height: 24px;
  border-radius: 8px;
  display: grid;
  place-items: center;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 11px;
  font-weight: 800;
  flex: 0 0 auto;
}

@media (max-width: 1200px) {
  .settings-grid {
    grid-template-columns: 1fr;
  }
}
</style>
