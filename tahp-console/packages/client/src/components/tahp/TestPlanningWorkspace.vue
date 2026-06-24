<script setup lang="ts">
import { onActivated, onMounted } from 'vue'
import { NButton, NEmpty, NScrollbar, NSpin, NTag } from 'naive-ui'
import EaCard from '@/components/layout/EaCard.vue'
import TestPlanSettingsModal from '@/components/tahp/TestPlanSettingsModal.vue'
import { useTestPlanningWorkspace } from '@/composables/useTestPlanningWorkspace'

const {
  loading,
  syncing,
  settingsVisible,
  sourcePath,
  nextNodes,
  scheduleItems,
  rules,
  hasSyncedData,
  hasRules,
  updatedAtLabel,
  handleSync,
  handleRulesSaved,
  restoreWorkspace,
} = useTestPlanningWorkspace()

onMounted(restoreWorkspace)
onActivated(restoreWorkspace)
</script>

<template>
  <div class="test-planning-workspace-root">
    <EaCard class="planning-card">
      <div class="planning-card-head">
        <h3>AI测试自规划</h3>
        <p v-if="hasSyncedData" class="meta ea-muted">
          最近更新：{{ updatedAtLabel }}
          <span v-if="sourcePath"> · {{ sourcePath }}</span>
        </p>
        <p v-else class="meta ea-muted">
          尚未同步项目节点，请点击左侧「更新」从项目信息表读取「升级中」项目。
        </p>
      </div>

      <div class="planning-workspace">
        <div class="panel nodes-panel">
          <div class="panel-title-row">
            <div class="panel-title">项目节点</div>
            <NButton size="tiny" type="primary" :loading="syncing" @click="handleSync">
              更新
            </NButton>
          </div>

          <NScrollbar class="panel-scroll">
            <div v-if="loading && !nextNodes.length" class="panel-loading">
              <NSpin size="small" />
              <span class="ea-muted">加载中…</span>
            </div>
            <NEmpty
              v-else-if="!nextNodes.length"
              description="暂无「升级中」项目的待来节点"
              size="small"
            />
            <ul v-else class="item-list">
              <li v-for="item in nextNodes" :key="`${item.project}-${item.node}`">
                {{ item.display }}
              </li>
            </ul>
          </NScrollbar>
        </div>

        <div class="panel schedule-panel">
          <div class="panel-title-row">
            <div class="panel-title">测试规划</div>
            <NButton size="tiny" tertiary @click="settingsVisible = true">设置</NButton>
          </div>

          <NScrollbar class="panel-scroll">
            <div v-if="loading && !scheduleItems.length" class="panel-loading">
              <NSpin size="small" />
              <span class="ea-muted">加载中…</span>
            </div>
            <NEmpty
              v-else-if="!hasRules"
              description="请先配置节点测试规则"
              size="small"
            />
            <NEmpty
              v-else-if="!scheduleItems.length"
              description="当前无待执行测试项"
              size="small"
            />
            <ul v-else class="item-list">
              <li v-for="item in scheduleItems" :key="`${item.project}-${item.node}-${item.triggerDate}-${item.testName}`">
                <NTag
                  size="small"
                  :type="item.status === 'active' ? 'warning' : 'default'"
                  :bordered="false"
                  class="status-tag"
                >
                  {{ item.status === 'active' ? '进行中' : '即将开始' }}
                </NTag>
                <span>{{ item.display }}</span>
              </li>
            </ul>
          </NScrollbar>
        </div>
      </div>
    </EaCard>

    <TestPlanSettingsModal
      v-model:show="settingsVisible"
      :rules="rules"
      @saved="handleRulesSaved"
    />
  </div>
</template>

<style scoped lang="scss">
.test-planning-workspace-root {
  margin-top: 24px;
}

.planning-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 16px 18px;
}

.planning-card-head {
  margin-bottom: 12px;

  h3 {
    margin: 0 0 6px;
    font-size: 15px;
    font-weight: 700;
  }

  .meta {
    margin: 0;
    font-size: 12px;
    line-height: 1.5;
  }
}

.planning-workspace {
  height: calc(50vh - 40px);
  min-height: 360px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  min-height: 0;
}

.panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--bg);
  overflow: hidden;
}

.panel-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
}

.panel-title {
  font-size: 13px;
  font-weight: 700;
}

.panel-scroll {
  flex: 1;
  min-height: 0;
  padding: 12px 14px;
}

.panel-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 4px;
}

.item-list {
  margin: 0;
  padding-left: 0;
  list-style: none;

  li {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    margin-bottom: 10px;
    font-size: 13px;
    line-height: 1.55;
    word-break: break-word;
  }
}

.status-tag {
  flex-shrink: 0;
  margin-top: 2px;
}

@media (max-width: 900px) {
  .planning-workspace {
    grid-template-columns: 1fr;
    height: auto;
    min-height: 520px;
  }

  .panel {
    min-height: 280px;
  }
}
</style>
