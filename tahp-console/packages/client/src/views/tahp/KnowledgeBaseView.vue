<script setup lang="ts">
import { ref, onMounted, computed, h } from 'vue'
import {
  NCard, NForm, NFormItem, NInput, NSelect, NInputNumber, NCheckbox,
  NButton, NSpace, NTag, NSpin, NEmpty, NTabs, NTabPane,
  NDataTable, NModal, NStatistic, NGrid, NGi, NDivider,
  useMessage, useDialog,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import {
  queryKnowledge,
  listKnowledgeEntries,
  addKnowledgeEntry,
  deleteKnowledgeEntry,
  getKnowledgeStats,
  importKnowledgeBatch,
  type KnowledgeQueryRequest,
  type KnowledgeResult,
  type KnowledgeEntry,
  type KnowledgeStats,
} from '@/api/tahp/knowledge'
import { useTahpModulesStore } from '@/stores/tahp/modules'

const message = useMessage()
const dialog = useDialog()
const modulesStore = useTahpModulesStore()

const activeTab = ref('query')

// ---- 检索 ----
const form = ref<KnowledgeQueryRequest>({ query: '', top_k: 5, cross_module: false })
const loading = ref(false)
const result = ref<KnowledgeResult | null>(null)

// ---- 条目管理 ----
const entriesLoading = ref(false)
const entries = ref<KnowledgeEntry[]>([])
const entriesTotal = ref(0)
const filterModule = ref('')
const showAddModal = ref(false)
const addForm = ref<KnowledgeEntry>({ title: '', content: '', module: '', tags: [], source: '' })
const adding = ref(false)

// ---- 统计 ----
const statsLoading = ref(false)
const stats = ref<KnowledgeStats | null>(null)

// ---- 批量导入 ----
const importJson = ref('')
const importing = ref(false)

const moduleOptions = computed(() => [
  { label: '(全部模块)', value: '' },
  ...modulesStore.modules.map(m => ({ label: m.name, value: m.name })),
])

const entryColumns: DataTableColumns<KnowledgeEntry> = [
  { title: '标题', key: 'title', ellipsis: { tooltip: true } },
  { title: '模块', key: 'module', width: 120 },
  { title: '来源', key: 'source', width: 180, ellipsis: { tooltip: true } },
  {
    title: '创建时间',
    key: 'created_at',
    width: 160,
    render: r => r.created_at ? new Date(r.created_at).toLocaleString() : '-',
  },
  {
    title: '操作',
    key: 'actions',
    width: 100,
    render: r => {
      const id = r.id
      if (!id) return ''
      return h(NButton, {
        size: 'small',
        type: 'error',
        ghost: true,
        onClick: () => confirmDelete(id, r.title),
      }, () => '删除')
    },
  },
]

onMounted(async () => {
  await modulesStore.refresh()
  loadStats()
})

async function doQuery() {
  if (!form.value.query?.trim()) { message.warning('请输入查询内容'); return }
  loading.value = true
  result.value = null
  try {
    const payload = { ...form.value }
    if (!payload.module) delete payload.module
    result.value = await queryKnowledge(payload)
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

async function loadEntries() {
  entriesLoading.value = true
  try {
    const res = await listKnowledgeEntries(filterModule.value || undefined)
    entries.value = res.entries || []
    entriesTotal.value = res.total || 0
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    entriesLoading.value = false
  }
}

async function loadStats() {
  statsLoading.value = true
  try {
    stats.value = await getKnowledgeStats()
  } catch {
    stats.value = null
  } finally {
    statsLoading.value = false
  }
}

function openAddModal() {
  addForm.value = { title: '', content: '', module: '', tags: [], source: '' }
  showAddModal.value = true
}

async function submitAdd() {
  if (!addForm.value.title?.trim() || !addForm.value.content?.trim()) {
    message.warning('标题和内容不能为空')
    return
  }
  adding.value = true
  try {
    await addKnowledgeEntry(addForm.value)
    message.success('知识条目已添加')
    showAddModal.value = false
    if (activeTab.value === 'manage') loadEntries()
    loadStats()
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    adding.value = false
  }
}

function confirmDelete(id: string, title: string) {
  dialog.warning({
    title: '确认删除',
    content: `删除知识条目「${title}」？此操作不可撤销。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteKnowledgeEntry(id)
        message.success('已删除')
        loadEntries()
        loadStats()
      } catch (err) {
        message.error((err as Error).message)
      }
    },
  })
}

async function doImport() {
  if (!importJson.value.trim()) { message.warning('请粘贴 JSON 数组'); return }
  let parsed: KnowledgeEntry[]
  try {
    parsed = JSON.parse(importJson.value)
    if (!Array.isArray(parsed)) throw new Error('必须是 JSON 数组')
  } catch (e) {
    message.error(`JSON 格式错误: ${(e as Error).message}`)
    return
  }
  importing.value = true
  try {
    const res = await importKnowledgeBatch(parsed)
    message.success(`成功导入 ${res.imported} 条，失败 ${res.errors} 条`)
    importJson.value = ''
    if (activeTab.value === 'manage') loadEntries()
    loadStats()
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    importing.value = false
  }
}

function onTabChange(tab: string) {
  activeTab.value = tab
  if (tab === 'manage' && !entries.value.length) loadEntries()
  if (tab === 'stats') loadStats()
}
</script>

<template>
  <div class="tahp-kb">
    <div class="page-header">
      <div>
        <h1>知识库</h1>
        <p class="subtitle">语义检索 · 条目管理 · 统计 (SQLite + ONNX 嵌入向量)</p>
      </div>
      <NButton type="primary" @click="openAddModal">
        <template #icon>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        </template>
        新增条目
      </NButton>
    </div>

    <!-- 统计卡片 -->
    <NGrid v-if="stats" :cols="3" :x-gap="16" :y-gap="12" style="margin-bottom: 16px">
      <NGi>
        <NCard :bordered="false" size="small">
          <NStatistic label="知识条目总数" :value="stats.total" />
        </NCard>
      </NGi>
      <NGi v-for="(cnt, mod) in stats.by_module" :key="mod">
        <NCard :bordered="false" size="small">
          <NStatistic :label="String(mod)" :value="cnt" />
        </NCard>
      </NGi>
    </NGrid>

    <NTabs :value="activeTab" @update:value="onTabChange">
      <!-- 检索 Tab -->
      <NTabPane name="query" tab="语义检索">
        <NCard :bordered="false" style="margin-top: 8px">
          <NForm :model="form" inline label-placement="left">
            <NFormItem label="查询" style="flex: 1; min-width: 240px">
              <NInput
                v-model:value="form.query"
                placeholder="如：RILJ 错误码 / dts 加载流程 / suspend 异常 ..."
                @keyup.enter="doQuery"
              />
            </NFormItem>
            <NFormItem label="模块">
              <NSelect v-model:value="form.module" :options="moduleOptions" style="width: 160px" clearable />
            </NFormItem>
            <NFormItem label="Top K">
              <NInputNumber v-model:value="form.top_k" :min="1" :max="50" style="width: 90px" />
            </NFormItem>
            <NFormItem>
              <NCheckbox v-model:checked="form.cross_module">跨模块</NCheckbox>
            </NFormItem>
            <NFormItem>
              <NButton type="primary" :loading="loading" @click="doQuery">搜索</NButton>
            </NFormItem>
          </NForm>
        </NCard>

        <NCard :bordered="false" style="margin-top: 12px">
          <template v-if="result">
            <NSpace style="margin-bottom: 12px">
              <NTag size="small">{{ (result.results || []).length }} 条</NTag>
              <NTag v-if="result.confidence !== undefined" size="small" type="info">
                置信度: {{ Number(result.confidence).toFixed(3) }}
              </NTag>
            </NSpace>
          </template>
          <NSpin :show="loading">
            <NEmpty v-if="!result" description="输入关键词后回车或点击搜索" />
            <NEmpty v-else-if="!result.results?.length" description="无匹配结果" />
            <div v-else class="result-list">
              <div v-for="(r, i) in result.results" :key="i" class="result-card">
                <div class="result-header">
                  <strong>{{ r.title || `结果 ${i + 1}` }}</strong>
                  <NSpace size="small">
                    <NTag v-if="r.module" size="tiny" type="info">{{ r.module }}</NTag>
                    <NTag v-if="r.score !== undefined" size="tiny">{{ Number(r.score).toFixed(3) }}</NTag>
                  </NSpace>
                </div>
                <div v-if="r.source" class="result-source">{{ r.source }}</div>
                <pre v-if="r.content" class="result-content">{{ r.content }}</pre>
              </div>
            </div>
          </NSpin>
        </NCard>
      </NTabPane>

      <!-- 条目管理 Tab -->
      <NTabPane name="manage" tab="条目管理">
        <NCard :bordered="false" style="margin-top: 8px">
          <template #header-extra>
            <NSpace>
              <NSelect
                v-model:value="filterModule"
                :options="moduleOptions"
                placeholder="筛选模块"
                style="width: 150px"
                clearable
                size="small"
                @update:value="loadEntries"
              />
              <NButton size="small" @click="loadEntries">刷新</NButton>
              <NButton size="small" type="primary" @click="openAddModal">新增</NButton>
            </NSpace>
          </template>
          <NSpin :show="entriesLoading">
            <NEmpty v-if="!entries.length && !entriesLoading" description="暂无条目，点击刷新或新增" />
            <NDataTable
              v-else
              :columns="entryColumns"
              :data="entries"
              :pagination="{ pageSize: 15 }"
              size="small"
            />
          </NSpin>
        </NCard>
      </NTabPane>

      <!-- 批量导入 Tab -->
      <NTabPane name="import" tab="批量导入">
        <NCard :bordered="false" style="margin-top: 8px">
          <p style="color: #888; font-size: 13px; margin-bottom: 12px">
            粘贴符合以下格式的 JSON 数组，每条包含 <code>title</code>、<code>content</code>（必填），
            以及可选的 <code>module</code>、<code>source</code>、<code>tags</code>。
          </p>
          <NInput
            v-model:value="importJson"
            type="textarea"
            placeholder='[{"title":"标题","content":"内容","module":"telephony","source":"来源"}]'
            :autosize="{ minRows: 10, maxRows: 20 }"
            style="font-family: monospace; font-size: 12px"
          />
          <NDivider style="margin: 12px 0" />
          <NButton type="primary" :loading="importing" @click="doImport">导入</NButton>
        </NCard>
      </NTabPane>
    </NTabs>

    <!-- 新增条目弹窗 -->
    <NModal
      v-model:show="showAddModal"
      preset="dialog"
      title="新增知识条目"
      positive-text="添加"
      negative-text="取消"
      style="width: 560px"
      @positive-click="submitAdd"
    >
      <NForm :model="addForm" label-placement="left" label-width="72">
        <NFormItem label="标题" required>
          <NInput v-model:value="addForm.title" placeholder="条目标题" />
        </NFormItem>
        <NFormItem label="模块">
          <NSelect v-model:value="addForm.module" :options="moduleOptions" clearable />
        </NFormItem>
        <NFormItem label="来源">
          <NInput v-model:value="addForm.source" placeholder="文件路径或 Jira 链接" />
        </NFormItem>
        <NFormItem label="内容" required>
          <NInput
            v-model:value="addForm.content"
            type="textarea"
            placeholder="知识内容，支持 Markdown"
            :autosize="{ minRows: 6, maxRows: 16 }"
          />
        </NFormItem>
      </NForm>
    </NModal>
  </div>
</template>

<style scoped>
.tahp-kb { padding: 24px; max-width: 1280px; margin: 0 auto; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 16px; }
.page-header h1 { margin: 0 0 4px; font-size: 22px; font-weight: 600; }
.subtitle { color: #888; margin: 0; font-size: 13px; }
.result-list { display: flex; flex-direction: column; gap: 12px; }
.result-card { padding: 12px; background: var(--n-color-modal, rgba(0,0,0,.03)); border-radius: 6px; }
.result-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.result-source { color: #888; font-size: 12px; margin-bottom: 8px; font-family: monospace; }
.result-content { margin: 0; white-space: pre-wrap; font-size: 13px; line-height: 1.6; }
code { background: rgba(0,0,0,.06); padding: 1px 4px; border-radius: 3px; font-size: 12px; }
</style>
