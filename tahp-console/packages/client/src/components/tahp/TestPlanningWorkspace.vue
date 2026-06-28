<script setup lang="ts">
import { onActivated, onMounted } from 'vue'
import { NButton, NEmpty, NScrollbar, NSpin, NTag } from 'naive-ui'
import EaCard from '@/components/layout/EaCard.vue'
import TestPlanSettingsModal from '@/components/tahp/TestPlanSettingsModal.vue'
import { useTestPlanningWorkspace } from '@/composables/useTestPlanningWorkspace'
import type { ScheduleItem } from '@/api/tahp/test-planning'

function scheduleTagType(item: ScheduleItem): 'default' | 'warning' | 'success' | 'error' {
  if (item.runtimeStatus === 'completed') return 'success'
  if (item.runtimeStatus === 'running') return 'warning'
  if (item.runtimeStatus === 'no_device') return 'error'
  return item.phase === 'active' ? 'warning' : 'default'
}

const {
  loading,
  syncing,
  settingsVisible,
  sourcePath,
  nextNodes,
  scheduleItems,
  scheduleTable,
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
                <span class="item-line">
                  <strong class="item-project">{{ item.project }}</strong>
                  <span class="item-sep"> · </span>
                  <span>{{ item.node }}</span>
                  <span class="item-sep"> · </span>
                  <span>{{ item.nodeDate }}</span>
                </span>
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
            <div v-else class="schedule-table-wrap">
              <div
                v-for="(block, blockIdx) in scheduleTable"
                :key="block.triggerDate"
                class="schedule-date-block"
                :class="{ 'is-last': blockIdx === scheduleTable.length - 1 }"
              >
                <table class="schedule-table">
                  <tbody>
                    <tr v-for="(row, idx) in block.rows" :key="row.scheduleKey">
                      <td
                        v-if="idx === 0"
                        :rowspan="block.rows.length"
                        class="col-date"
                      >
                        {{ block.triggerDate }}
                      </td>
                      <td
                        v-if="row.showProject"
                        :rowspan="row.projectRowSpan"
                        class="col-project"
                      >
                        <strong>{{ row.item.project }}</strong>
                      </td>
                      <td class="col-test">{{ row.item.testTypeLabel }}</td>
                      <td class="col-status">
                        <NTag
                          size="tiny"
                          :type="scheduleTagType(row.item)"
                          :bordered="false"
                          class="status-tag"
                        >
                          {{ row.item.displayLabel }}
                        </NTag>
                        <NTag
                          v-for="tag in row.item.tags"
                          :key="`${row.scheduleKey}-${tag}`"
                          size="tiny"
                          type="error"
                          :bordered="false"
                          class="status-tag"
                        >
                          {{ tag }}
                        </NTag>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
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
}

.schedule-panel .panel-scroll {
  padding: 8px 10px;
}

.schedule-table-wrap {
  display: flex;
  flex-direction: column;
}

.schedule-date-block {
  margin-bottom: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--line);

  &.is-last {
    margin-bottom: 0;
    padding-bottom: 0;
    border-bottom: none;
  }
}

.schedule-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  line-height: 1.35;

  tbody tr {
    border-bottom: 1px dashed var(--line);

    &:last-child {
      border-bottom: none;
    }
  }

  td {
    padding: 3px 6px;
    vertical-align: middle;
  }
}

.col-date {
  width: 88px;
  font-weight: 700;
  font-size: 12px;
  text-align: center;
  vertical-align: middle;
}

.col-project {
  width: 64px;
  text-align: center;
  vertical-align: middle;

  strong {
    font-weight: 700;
  }
}

.col-test {
  text-align: left;
  padding-right: 4px;
}

.col-status {
  min-width: 80px;
  text-align: left;
  white-space: nowrap;
  vertical-align: middle;

  .status-tag + .status-tag {
    margin-left: 4px;
  }
}

.item-line {
  min-width: 0;
}

.item-project {
  font-weight: 700;
}

.item-sep {
  color: var(--muted);
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
