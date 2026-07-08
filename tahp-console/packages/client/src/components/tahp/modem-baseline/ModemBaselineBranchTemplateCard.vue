<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { NButton, NEmpty, NInput, NPagination, NTag } from 'naive-ui'
import type { BranchTemplate } from '@/api/tahp/modem-baseline'

const props = defineProps<{
  templates: BranchTemplate[]
  loading?: boolean
  importing?: boolean
}>()

const emit = defineEmits<{
  import: [filePath: string]
}>()

const filePath = ref('D:\\Software\\EasyAdapter\\tOS15.1.2+15.1.3分支.xlsx')
const page = ref(1)
const pageSize = 6

type TemplateGroup = {
  platform: string
  sourceSheets: string[]
  trunkItems: Array<{ nodeBranch: string; trunkBranch: string }>
  mpItems: Array<{ templateId: string; tos: string; mpNodeBranch: string; mpBranch: string }>
}

function compareTos(left: string, right: string) {
  const parse = (value: string) => String(value || '')
    .replace(/^tOS/i, '')
    .split('.')
    .map(part => Number(part) || 0)
  const leftParts = parse(left)
  const rightParts = parse(right)
  const max = Math.max(leftParts.length, rightParts.length)
  for (let i = 0; i < max; i += 1) {
    const diff = (leftParts[i] ?? 0) - (rightParts[i] ?? 0)
    if (diff !== 0) return diff
  }
  return String(left).localeCompare(String(right))
}

const groupedTemplates = computed<TemplateGroup[]>(() => {
  const groups = new Map<string, TemplateGroup>()
  for (const item of props.templates) {
    const key = item.platform.trim()
    if (!key) continue
    const current = groups.get(key) || {
      platform: item.platform,
      sourceSheets: [],
      trunkItems: [],
      mpItems: [],
    }
    if (item.sourceSheet && !current.sourceSheets.includes(item.sourceSheet)) {
      current.sourceSheets.push(item.sourceSheet)
    }
    if (!current.trunkItems.some(entry => entry.nodeBranch === item.nodeBranch && entry.trunkBranch === item.trunkBranch)) {
      current.trunkItems.push({
        nodeBranch: item.nodeBranch,
        trunkBranch: item.trunkBranch,
      })
    }
    if (!current.mpItems.some(entry => entry.tos === item.tos && entry.mpNodeBranch === item.mpNodeBranch && entry.mpBranch === item.mpBranch)) {
      current.mpItems.push({
        templateId: item.templateId,
        tos: item.tos,
        mpNodeBranch: item.mpNodeBranch,
        mpBranch: item.mpBranch,
      })
    }
    groups.set(key, current)
  }

  return Array.from(groups.values())
    .map(group => ({
      ...group,
      sourceSheets: group.sourceSheets.sort((left, right) => compareTos(left, right)),
      mpItems: [...group.mpItems].sort((left, right) => compareTos(left.tos, right.tos)),
    }))
    .sort((left, right) => left.platform.localeCompare(right.platform))
})

const total = computed(() => groupedTemplates.value.length)
const versionCount = computed(() => new Set(props.templates.map(item => item.tos)).size)
const pagedTemplates = computed(() => {
  const start = (page.value - 1) * pageSize
  return groupedTemplates.value.slice(start, start + pageSize)
})

watch(total, (value) => {
  const pageCount = Math.max(1, Math.ceil(value / pageSize))
  if (page.value > pageCount) page.value = pageCount
})

function submitImport() {
  const value = filePath.value.trim()
  if (!value) return
  emit('import', value)
}
</script>

<template>
  <div class="ea-card ea-stack">
    <div class="list-head">
      <div>
        <div class="ea-section-title">分支模板</div>
        <h3>版本与分支关系</h3>
        <p>从本地 Excel 导入 tOS 版本、平台、主干分支和 MP 分支，供工作台一键回填。</p>
      </div>
      <span class="ea-pill-info">{{ groupedTemplates.length }} 平台 / {{ templates.length }} 条</span>
    </div>

    <div class="import-box ea-stack">
      <div class="ea-field">
        <label>Excel 路径</label>
        <NInput
          v-model:value="filePath"
          placeholder="例如 D:\Software\EasyAdapter\tOS15.1.2+15.1.3分支.xlsx"
        />
      </div>
      <div class="import-actions">
        <NButton type="primary" :loading="importing" @click="submitImport">导入 Excel</NButton>
      </div>
    </div>

    <div class="summary-grid">
      <div class="summary-item">
        <span class="ea-pill-muted">版本数</span>
        <strong>{{ versionCount }}</strong>
        <p>按 sheet 中的 tOS 版本拆分维护。</p>
      </div>
      <div class="summary-item">
        <span class="ea-pill-muted">默认规则</span>
        <strong>主干 master / MP 去掉 _mp</strong>
        <p>未显式提供节点分支时，按默认规则自动补齐。</p>
      </div>
    </div>

    <NEmpty
      v-if="!templates.length && !loading"
      description="当前还没有分支模板，导入 Excel 后可在工作台直接回填分支。"
    />

    <div v-else class="template-list">
      <div v-for="item in pagedTemplates" :key="item.platform" class="template-item">
        <div class="template-head">
          <div class="template-title">
            <strong>{{ item.platform }}</strong>
          </div>
          <span class="ea-pill-muted">{{ item.sourceSheets.join(' / ') || 'Excel' }}</span>
        </div>
        <div class="branch-stack">
          <div v-for="trunk in item.trunkItems" :key="`${trunk.nodeBranch}-${trunk.trunkBranch}`" class="branch-row">
            <div class="branch-labels">
              <span class="ea-pill-muted">主干</span>
            </div>
            <p>{{ trunk.nodeBranch }} -> {{ trunk.trunkBranch }}</p>
          </div>
          <div v-for="mp in item.mpItems" :key="mp.templateId" class="branch-row">
            <div class="branch-labels">
              <NTag size="small" type="info" round>{{ mp.tos }}</NTag>
              <span class="ea-pill-muted">MP</span>
            </div>
            <p>{{ mp.mpNodeBranch }} -> {{ mp.mpBranch }}</p>
          </div>
        </div>
      </div>
    </div>

    <div v-if="templates.length > pageSize" class="pagination-wrap">
      <NPagination v-model:page="page" :page-size="pageSize" :item-count="total" />
    </div>
  </div>
</template>

<style scoped lang="scss">
.list-head,
.template-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.list-head {
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

.import-box,
.summary-item,
.template-item {
  padding: 14px 16px;
  border-radius: 14px;
  background: var(--bg);
  border: 1px solid var(--line);
}

.import-actions,
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
}

.summary-grid,
.branch-stack {
  display: grid;
  gap: 12px;
}

.summary-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.summary-item strong {
  display: block;
  margin-top: 8px;
  font-size: 16px;
  color: var(--text);
}

.summary-item p,
.branch-row p {
  margin-top: 6px;
  font-size: 12px;
  color: var(--muted);
  word-break: break-word;
}

.template-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.template-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;

  strong {
    font-size: 15px;
    color: var(--text);
  }
}

.branch-stack {
  margin-top: 12px;
}

.branch-row {
  padding: 12px 14px;
  border-radius: 12px;
  background: color-mix(in srgb, var(--bg) 82%, white);
  border: 1px solid color-mix(in srgb, var(--line) 85%, white);
}

.branch-labels {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 720px) {
  .list-head,
  .template-head {
    flex-direction: column;
    align-items: stretch;
  }

  .summary-grid,
  .branch-stack {
    grid-template-columns: 1fr;
  }
}
</style>
