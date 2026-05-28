<script setup lang="ts">
import { ref, onMounted, computed, h, reactive } from 'vue'
import {
  NCard, NForm, NFormItem, NInput, NSelect, NDataTable, NModal, NDrawer, NButton,
  NSpace, NTag, NSpin, NEmpty, NTabs, NTabPane, NStatistic, NGrid, NGi,
  NSlider, NCheckbox, NDatePicker, NProgressBar, NDivider, NIcon, NPopconfirm,
  useMessage, useDialog,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { useTahpModulesStore } from '@/stores/tahp/modules'

const message = useMessage()
const dialog = useDialog()
const modulesStore = useTahpModulesStore()

// ─── Types ────────────────────────────────────────────────────────────────────
interface KnowledgeEntry {
  id?: string
  content: string
  category: string
  module: string
  func_type: string
  keywords: string[]
  confidence_score: number
  source_file?: string
  source_page?: number
  source_section?: string
  source_url?: string
  applicable_versions?: string[]
  created_at?: string
  updated_at?: string
  expires_at?: string
  status?: 'pending_review' | 'approved' | 'rejected' | 'archived'
  is_verified?: boolean
  validation_date?: string
  maintenance_owner?: string
  last_used_in_task?: string
  usage_count?: number
}

interface SkillDraft {
  id?: string
  skill_id: string
  skill_name: string
  domain_label: string
  module: string
  func_type: string
  content: string
  generated_from_entries: string[]
  generated_at?: string
  generated_by?: string
  status?: 'draft' | 'reviewing' | 'approved' | 'rejected'
  reviewed_by?: string
  reviewed_at?: string
  review_notes?: string
  activated_at?: string
  activated_skill_path?: string
}

interface KnowledgeStats {
  total_entries: number
  approved_entries: number
  pending_entries: number
  archived_entries: number
  by_module: Record<string, number>
  by_func_type: Record<string, number>
  by_status: Record<string, number>
  total_skill_drafts: number
  draft_skill_drafts: number
  approved_skill_drafts: number
  total_usage_count: number
  average_confidence: number
}

// ─── API Functions (Inline) ────────────────────────────────────────────────────
async function listKnowledgeEntries(query: Record<string, any> = {}): Promise<{entries: KnowledgeEntry[], total: number}> {
  const qs = new URLSearchParams()
  if (query.module) qs.append('module', query.module)
  if (query.func_type) qs.append('func_type', query.func_type)
  if (query.status) qs.append('status', query.status)
  if (query.sort_by) qs.append('sort_by', query.sort_by)
  if (query.sort_order) qs.append('sort_order', query.sort_order)
  if (query.limit) qs.append('limit', String(query.limit))
  if (query.offset) qs.append('offset', String(query.offset))

  const response = await fetch(`/api/tahp/knowledge/entries${qs.size ? '?' + qs : ''}`)
  const result = await response.json()
  if (!result.success) throw new Error(result.error)
  return { entries: result.data.entries, total: result.data.total }
}

async function getKnowledgeEntry(entryId: string): Promise<KnowledgeEntry> {
  const response = await fetch(`/api/tahp/knowledge/entries/${encodeURIComponent(entryId)}`)
  const result = await response.json()
  if (!result.success) throw new Error(result.error)
  return result.data
}

async function createKnowledgeEntry(entry: KnowledgeEntry): Promise<{id: string}> {
  const response = await fetch('/api/tahp/knowledge/entries', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(entry),
  })
  const result = await response.json()
  if (!result.success) throw new Error(result.error)
  return { id: result.data.id }
}

async function updateKnowledgeEntry(entryId: string, updates: Partial<KnowledgeEntry>): Promise<KnowledgeEntry> {
  const response = await fetch(`/api/tahp/knowledge/entries/${encodeURIComponent(entryId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  })
  const result = await response.json()
  if (!result.success) throw new Error(result.error)
  return result.data
}

async function deleteKnowledgeEntry(entryId: string): Promise<void> {
  const response = await fetch(`/api/tahp/knowledge/entries/${encodeURIComponent(entryId)}`, {
    method: 'DELETE',
  })
  const result = await response.json()
  if (!result.success) throw new Error(result.error)
}

async function searchKnowledge(query: string, module?: string, limit: number = 10): Promise<{results: KnowledgeEntry[], total: number}> {
  const response = await fetch('/api/tahp/knowledge/search/semantic', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, module, limit }),
  })
  const result = await response.json()
  if (!result.success) throw new Error(result.error)
  return { results: result.data.results, total: result.data.total }
}

async function getKnowledgeStats(): Promise<KnowledgeStats> {
  const response = await fetch('/api/tahp/knowledge/stats')
  const result = await response.json()
  if (!result.success) throw new Error(result.error)
  return result.data
}

async function listSkillDrafts(status?: string, limit: number = 20, offset: number = 0): Promise<{drafts: SkillDraft[], total: number}> {
  const qs = new URLSearchParams()
  if (status) qs.append('status', status)
  qs.append('limit', String(limit))
  qs.append('offset', String(offset))

  const response = await fetch(`/api/tahp/knowledge/skill-drafts${qs.size ? '?' + qs : ''}`)
  const result = await response.json()
  if (!result.success) throw new Error(result.error)
  return { drafts: result.data.drafts, total: result.data.total }
}

async function createSkillDraft(draft: Partial<SkillDraft>): Promise<SkillDraft> {
  const response = await fetch('/api/tahp/knowledge/skill-drafts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(draft),
  })
  const result = await response.json()
  if (!result.success) throw new Error(result.error)
  return result.data
}

async function reviewSkillDraft(draftId: string, action: 'approve' | 'reject', reviewNotes?: string): Promise<SkillDraft> {
  const response = await fetch(`/api/tahp/knowledge/skill-drafts/${encodeURIComponent(draftId)}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, review_notes: reviewNotes }),
  })
  const result = await response.json()
  if (!result.success) throw new Error(result.error)
  return result.data
}

async function recordFeedback(entryId: string, taskId: string, useful: boolean, rating?: number): Promise<KnowledgeEntry> {
  const response = await fetch(`/api/tahp/knowledge/entries/${encodeURIComponent(entryId)}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_id: taskId, feedback: useful, useful, rating }),
  })
  const result = await response.json()
  if (!result.success) throw new Error(result.error)
  return result.data
}

// ─── State ────────────────────────────────────────────────────────────────────
const activeTab = ref('dashboard')

// Dashboard
const statsLoading = ref(false)
const stats = ref<KnowledgeStats | null>(null)

// Entries Tab
const entriesLoading = ref(false)
const entries = ref<KnowledgeEntry[]>([])
const entriesTotal = ref(0)
const currentPage = ref(1)
const pageSize = ref(15)

const filterModule = ref('')
const filterFuncType = ref('')
const filterStatus = ref('')
const searchKeyword = ref('')

// Entry Modal
const showEntryModal = ref(false)
const editingEntry = ref<KnowledgeEntry | null>(null)
const formEntry = reactive<KnowledgeEntry>({
  content: '',
  category: '',
  module: '',
  func_type: '',
  keywords: [],
  confidence_score: 0.8,
  status: 'pending_review',
  is_verified: false,
  usage_count: 0,
})

// Entry Drawer
const showEntryDrawer = ref(false)
const viewingEntry = ref<KnowledgeEntry | null>(null)

// Skill Drafts Tab
const skillDraftsLoading = ref(false)
const skillDrafts = ref<SkillDraft[]>([])
const skillDraftsTotal = ref(0)
const draftPage = ref(1)
const draftPageSize = ref(10)

// Draft Review Drawer
const showDraftReviewDrawer = ref(false)
const reviewingDraft = ref<SkillDraft | null>(null)
const reviewAction = ref<'approve' | 'reject'>('approve')
const reviewNotes = ref('')

// Analytics Tab
const analyticsLoading = ref(false)
const topUsedEntries = ref<(KnowledgeEntry & {_rank?: number})[]>([])
const pendingEntries = ref<KnowledgeEntry[]>([])
const expiredEntries = ref<KnowledgeEntry[]>([])

// Constants
const moduleOptions = computed(() => [
  { label: '(全部模块)', value: '' },
  { label: '通信', value: 'telephony' },
  { label: '驱动', value: 'kernel-driver' },
  { label: '功耗管理', value: 'power-mgmt' },
  { label: '共享', value: 'shared' },
  { label: '自定义', value: 'custom' },
])

const funcTypeOptions = [
  { label: '(全部类型)', value: '' },
  { label: 'Bug分析', value: 'bug_analysis' },
  { label: '代码适配', value: 'code_adaptation' },
  { label: '版本适配', value: 'version_adaptation' },
  { label: '运营商移植', value: 'carrier_porting' },
  { label: 'AI自检', value: 'ai_self_check' },
]

const statusOptions = [
  { label: '(全部状态)', value: '' },
  { label: '待审核', value: 'pending_review' },
  { label: '已批准', value: 'approved' },
  { label: '已拒绝', value: 'rejected' },
  { label: '已归档', value: 'archived' },
]

const categoryOptions = [
  { label: '最佳实践', value: 'best_practice' },
  { label: '故障排查', value: 'troubleshooting' },
  { label: '性能优化', value: 'performance' },
  { label: '安全建议', value: 'security' },
  { label: '设计模式', value: 'design_pattern' },
  { label: '其他', value: 'other' },
]

// ─── Computed ────────────────────────────────────────────────────────────────
const entryColumns: DataTableColumns<KnowledgeEntry> = [
  { title: 'ID', key: 'id', width: 120, ellipsis: { tooltip: true } },
  {
    title: '内容摘要',
    key: 'content',
    width: 220,
    ellipsis: { tooltip: true },
    render: (row) => row.content?.slice(0, 100) + (row.content && row.content.length > 100 ? '...' : '')
  },
  { title: '分类', key: 'category', width: 100 },
  {
    title: '模块 / 业务类型',
    key: 'module',
    width: 180,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(NTag, { size: 'small', type: 'info' }, { default: () => row.module }),
        h(NTag, { size: 'small', type: 'warning' }, { default: () => row.func_type }),
      ]
    })
  },
  {
    title: '来源',
    key: 'source_file',
    width: 150,
    ellipsis: { tooltip: true },
    render: (row) => row.source_file || '-'
  },
  {
    title: '置信度',
    key: 'confidence_score',
    width: 120,
    render: (row) => h(NProgressBar, {
      percentage: row.confidence_score * 100,
      type: row.confidence_score >= 0.8 ? 'success' : row.confidence_score >= 0.6 ? 'warning' : 'error',
      height: 20,
    }, { default: () => (row.confidence_score * 100).toFixed(0) + '%' })
  },
  {
    title: '状态',
    key: 'status',
    width: 100,
    render: (row) => {
      const statusMap: Record<string, any> = {
        'pending_review': { type: 'info', label: '待审核' },
        'approved': { type: 'success', label: '已批准' },
        'rejected': { type: 'error', label: '已拒绝' },
        'archived': { type: 'default', label: '已归档' },
      }
      const status = statusMap[row.status || 'pending_review']
      return h(NTag, { type: status.type, size: 'small' }, { default: () => status.label })
    }
  },
  {
    title: '验证',
    key: 'is_verified',
    width: 80,
    render: (row) => row.is_verified ? h(NTag, { type: 'success', size: 'small' }, { default: () => '已验证' }) : h(NTag, { type: 'default', size: 'small' }, { default: () => '未验证' })
  },
  {
    title: '使用次数',
    key: 'usage_count',
    width: 80,
    align: 'center',
  },
  {
    title: '创建时间',
    key: 'created_at',
    width: 160,
    render: (row) => row.created_at ? new Date(row.created_at).toLocaleString('zh-CN') : '-'
  },
  {
    title: '操作',
    key: 'actions',
    width: 140,
    fixed: 'right',
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(NButton, {
          size: 'small',
          type: 'primary',
          ghost: true,
          onClick: () => openViewEntry(row),
        }, { default: () => '查看' }),
        h(NButton, {
          size: 'small',
          type: 'info',
          ghost: true,
          onClick: () => openEditEntry(row),
        }, { default: () => '编辑' }),
        h(NPopconfirm, {
          onPositiveClick: () => confirmDelete(row),
          positiveText: '确认',
          negativeText: '取消',
          title: '确认删除？',
        }, {
          default: () => h(NButton, {
            size: 'small',
            type: 'error',
            ghost: true,
          }, { default: () => '删除' })
        })
      ]
    })
  },
]

const skillDraftColumns: DataTableColumns<SkillDraft> = [
  { title: 'Skill ID', key: 'skill_id', width: 120, ellipsis: { tooltip: true } },
  { title: 'Skill 名称', key: 'skill_name', width: 140 },
  {
    title: '分类',
    key: 'module',
    width: 140,
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(NTag, { size: 'small', type: 'info' }, { default: () => row.module }),
        h(NTag, { size: 'small', type: 'warning' }, { default: () => row.func_type }),
      ]
    })
  },
  {
    title: '来源条目',
    key: 'generated_from_entries',
    width: 160,
    ellipsis: { tooltip: true },
    render: (row) => row.generated_from_entries?.length ? h(NTag, { size: 'small' }, { default: () => `${row.generated_from_entries.length} 条` }) : '-'
  },
  {
    title: '状态',
    key: 'status',
    width: 100,
    render: (row) => {
      const statusMap: Record<string, any> = {
        'draft': { type: 'default', label: '草稿' },
        'reviewing': { type: 'info', label: '审核中' },
        'approved': { type: 'success', label: '已批准' },
        'rejected': { type: 'error', label: '已拒绝' },
      }
      const status = statusMap[row.status || 'draft']
      return h(NTag, { type: status.type, size: 'small' }, { default: () => status.label })
    }
  },
  {
    title: '生成时间',
    key: 'generated_at',
    width: 160,
    render: (row) => row.generated_at ? new Date(row.generated_at).toLocaleString('zh-CN') : '-'
  },
  {
    title: '操作',
    key: 'actions',
    width: 140,
    fixed: 'right',
    render: (row) => h(NSpace, { size: 'small' }, {
      default: () => [
        h(NButton, {
          size: 'small',
          type: 'primary',
          ghost: true,
          onClick: () => openReviewDraft(row),
        }, { default: () => '审核' }),
      ]
    })
  },
]

// ─── Hooks ────────────────────────────────────────────────────────────────────
onMounted(async () => {
  await modulesStore.refresh()
  await loadStats()
  await loadEntries()
  await loadSkillDrafts()
})

// ─── Methods ────────────────────────────────────────────────────────────────
async function loadStats() {
  statsLoading.value = true
  try {
    stats.value = await getKnowledgeStats()
  } catch (err) {
    message.error(`统计加载失败: ${(err as Error).message}`)
  } finally {
    statsLoading.value = false
  }
}

async function loadEntries() {
  entriesLoading.value = true
  try {
    const offset = (currentPage.value - 1) * pageSize.value
    const result = await listKnowledgeEntries({
      module: filterModule.value || undefined,
      func_type: filterFuncType.value || undefined,
      status: filterStatus.value || undefined,
      limit: pageSize.value,
      offset,
    })
    entries.value = result.entries
    entriesTotal.value = result.total
  } catch (err) {
    message.error(`条目加载失败: ${(err as Error).message}`)
  } finally {
    entriesLoading.value = false
  }
}

async function loadSkillDrafts() {
  skillDraftsLoading.value = true
  try {
    const offset = (draftPage.value - 1) * draftPageSize.value
    const result = await listSkillDrafts('draft', draftPageSize.value, offset)
    skillDrafts.value = result.drafts
    skillDraftsTotal.value = result.total
  } catch (err) {
    message.error(`Skill草稿加载失败: ${(err as Error).message}`)
  } finally {
    skillDraftsLoading.value = false
  }
}

async function loadAnalytics() {
  analyticsLoading.value = true
  try {
    const allResult = await listKnowledgeEntries({ limit: 1000 })
    const allEntries = allResult.entries

    // 按使用次数排序，取前10
    topUsedEntries.value = allEntries
      .filter(e => (e.usage_count || 0) > 0)
      .sort((a, b) => (b.usage_count || 0) - (a.usage_count || 0))
      .slice(0, 10)
      .map((e, i) => ({ ...e, _rank: i + 1 }))

    // 待审核条目
    pendingEntries.value = allEntries.filter(e => e.status === 'pending_review')

    // 即将过期条目（expires_at < 30天）
    const thirtyDaysLater = new Date()
    thirtyDaysLater.setDate(thirtyDaysLater.getDate() + 30)
    expiredEntries.value = allEntries.filter(e => {
      if (!e.expires_at) return false
      return new Date(e.expires_at) < thirtyDaysLater && new Date(e.expires_at) > new Date()
    })
  } catch (err) {
    message.error(`分析加载失败: ${(err as Error).message}`)
  } finally {
    analyticsLoading.value = false
  }
}

async function searchEntries() {
  if (!searchKeyword.value.trim()) {
    message.warning('请输入搜索关键词')
    return
  }

  entriesLoading.value = true
  try {
    const result = await searchKnowledge(searchKeyword.value, filterModule.value || undefined, 100)
    entries.value = result.results
    entriesTotal.value = result.total
    currentPage.value = 1
  } catch (err) {
    message.error(`搜索失败: ${(err as Error).message}`)
  } finally {
    entriesLoading.value = false
  }
}

function openEditEntry(entry?: KnowledgeEntry) {
  if (entry) {
    editingEntry.value = entry
    Object.assign(formEntry, entry)
  } else {
    editingEntry.value = null
    Object.assign(formEntry, {
      content: '',
      category: '',
      module: '',
      func_type: '',
      keywords: [],
      confidence_score: 0.8,
      status: 'pending_review',
      is_verified: false,
      usage_count: 0,
    })
  }
  showEntryModal.value = true
}

async function submitEntry() {
  if (!formEntry.content?.trim()) {
    message.warning('内容不能为空')
    return
  }
  if (!formEntry.category) {
    message.warning('请选择分类')
    return
  }
  if (!formEntry.module) {
    message.warning('请选择模块')
    return
  }
  if (!formEntry.func_type) {
    message.warning('请选择业务类型')
    return
  }

  try {
    if (editingEntry.value?.id) {
      await updateKnowledgeEntry(editingEntry.value.id, formEntry)
      message.success('条目已更新')
    } else {
      await createKnowledgeEntry(formEntry)
      message.success('条目已创建')
    }
    showEntryModal.value = false
    await loadEntries()
    await loadStats()
  } catch (err) {
    message.error(`操作失败: ${(err as Error).message}`)
  }
}

async function confirmDelete(entry: KnowledgeEntry) {
  if (!entry.id) return
  try {
    await deleteKnowledgeEntry(entry.id)
    message.success('条目已删除')
    await loadEntries()
    await loadStats()
  } catch (err) {
    message.error(`删除失败: ${(err as Error).message}`)
  }
}

async function openViewEntry(entry: KnowledgeEntry) {
  try {
    const fullEntry = entry.id ? await getKnowledgeEntry(entry.id) : entry
    viewingEntry.value = fullEntry
    showEntryDrawer.value = true
  } catch (err) {
    message.error(`加载条目失败: ${(err as Error).message}`)
  }
}

async function markAsVerified() {
  if (!viewingEntry.value?.id) return
  try {
    await updateKnowledgeEntry(viewingEntry.value.id, {
      is_verified: true,
      validation_date: new Date().toISOString(),
    })
    message.success('已标记为已验证')
    viewingEntry.value.is_verified = true
    await loadEntries()
  } catch (err) {
    message.error(`操作失败: ${(err as Error).message}`)
  }
}

function openReviewDraft(draft: SkillDraft) {
  reviewingDraft.value = draft
  reviewAction.value = 'approve'
  reviewNotes.value = ''
  showDraftReviewDrawer.value = true
}

async function submitDraftReview() {
  if (!reviewingDraft.value?.id) return
  try {
    await reviewSkillDraft(reviewingDraft.value.id, reviewAction.value, reviewNotes.value)
    message.success(`草稿已${reviewAction.value === 'approve' ? '批准' : '打回'}`)
    showDraftReviewDrawer.value = false
    await loadSkillDrafts()
  } catch (err) {
    message.error(`审核失败: ${(err as Error).message}`)
  }
}

function onTabChange(tab: string) {
  activeTab.value = tab
  if (tab === 'analytics' && !analyticsLoading.value && !topUsedEntries.value.length) {
    loadAnalytics()
  }
}
</script>

<template>
  <div class="kb-management">
    <div class="page-header">
      <div>
        <h1>知识库管理</h1>
        <p class="subtitle">创建、管理、审核知识条目和 Skill 草稿</p>
      </div>
    </div>

    <!-- 统计卡片 -->
    <NSpin :show="statsLoading">
      <NGrid v-if="stats" :cols="5" :x-gap="12" :y-gap="12" class="stats-grid" responsive>
        <NGi>
          <NCard :bordered="false" size="small" class="stat-card">
            <NStatistic label="知识条目总数" :value="stats.total_entries" type="info" />
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" size="small" class="stat-card">
            <NStatistic label="待审核" :value="stats.pending_entries" type="warning" />
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" size="small" class="stat-card">
            <NStatistic label="已批准" :value="stats.approved_entries" type="success" />
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" size="small" class="stat-card">
            <NStatistic label="平均置信度" :value="`${(stats.average_confidence * 100).toFixed(1)}%`" />
          </NCard>
        </NGi>
        <NGi>
          <NCard :bordered="false" size="small" class="stat-card">
            <NStatistic label="待审核草稿" :value="stats.draft_skill_drafts" />
          </NCard>
        </NGi>
      </NGrid>
    </NSpin>

    <!-- Tab 切换 -->
    <NTabs :value="activeTab" @update:value="onTabChange" class="tabs-container">
      <!-- 1. 仪表板 Tab -->
      <NTabPane name="dashboard" tab="📊 仪表板">
        <div class="tab-content">
          <NGrid :cols="2" :x-gap="16" :y-gap="16">
            <!-- 左侧：模块分布 -->
            <NGi>
              <NCard title="按模块分布" :bordered="false">
                <div v-if="stats" class="module-dist">
                  <div v-for="(count, module) in stats.by_module" :key="module" class="dist-item">
                    <span class="dist-label">{{ module }}</span>
                    <div class="dist-bar">
                      <div
                        class="dist-fill"
                        :style="{ width: ((count / stats.total_entries) * 100) + '%' }"
                      />
                    </div>
                    <span class="dist-value">{{ count }}</span>
                  </div>
                </div>
              </NCard>
            </NGi>

            <!-- 右侧：业务类型分布 -->
            <NGi>
              <NCard title="按业务类型分布" :bordered="false">
                <div v-if="stats" class="type-dist">
                  <div v-for="(count, type) in stats.by_func_type" :key="type" class="type-item">
                    <NTag size="small" type="info">{{ type }}</NTag>
                    <span class="type-count">{{ count }}</span>
                  </div>
                </div>
              </NCard>
            </NGi>
          </NGrid>

          <!-- 快速操作 -->
          <NCard title="快速操作" :bordered="false" class="card-mt">
            <NSpace>
              <NButton type="primary" @click="openEditEntry">
                <template #icon><span>➕</span></template>
                新建条目
              </NButton>
              <NButton @click="loadEntries">
                <template #icon><span>🔄</span></template>
                刷新数据
              </NButton>
              <NButton type="info" @click="activeTab = 'entries'">
                <template #icon><span>📋</span></template>
                查看全部条目
              </NButton>
            </NSpace>
          </NCard>
        </div>
      </NTabPane>

      <!-- 2. 知识条目 Tab -->
      <NTabPane name="entries" tab="📚 知识条目">
        <div class="tab-content">
          <!-- 搜索和过滤 -->
          <NCard :bordered="false" class="filter-card">
            <NForm inline label-placement="left" size="small">
              <NFormItem label="关键词搜索">
                <NInput
                  v-model:value="searchKeyword"
                  placeholder="搜索内容..."
                  style="width: 180px"
                  clearable
                  @keyup.enter="searchEntries"
                />
              </NFormItem>
              <NFormItem label="模块">
                <NSelect
                  v-model:value="filterModule"
                  :options="moduleOptions"
                  style="width: 140px"
                  clearable
                  @update:value="loadEntries"
                />
              </NFormItem>
              <NFormItem label="业务类型">
                <NSelect
                  v-model:value="filterFuncType"
                  :options="funcTypeOptions"
                  style="width: 140px"
                  clearable
                  @update:value="loadEntries"
                />
              </NFormItem>
              <NFormItem label="状态">
                <NSelect
                  v-model:value="filterStatus"
                  :options="statusOptions"
                  style="width: 120px"
                  clearable
                  @update:value="loadEntries"
                />
              </NFormItem>
              <NFormItem>
                <NButton type="primary" @click="searchEntries">搜索</NButton>
              </NFormItem>
              <NFormItem>
                <NButton @click="openEditEntry">新建条目</NButton>
              </NFormItem>
              <NFormItem>
                <NButton @click="loadEntries">刷新</NButton>
              </NFormItem>
            </NForm>
          </NCard>

          <!-- 条目列表 -->
          <NCard :bordered="false" class="card-mt">
            <NSpin :show="entriesLoading">
              <NEmpty v-if="!entries.length && !entriesLoading" description="暂无条目" />
              <NDataTable
                v-else
                :columns="entryColumns"
                :data="entries"
                :pagination="{
                  page: currentPage,
                  pageSize: pageSize,
                  pageCount: Math.ceil(entriesTotal / pageSize),
                  prefix: (info) => `共 ${entriesTotal} 条`,
                  onChange: (p) => { currentPage = p; loadEntries() },
                }"
                size="small"
                class="data-table"
              />
            </NSpin>
          </NCard>
        </div>
      </NTabPane>

      <!-- 3. Skill 草稿 Tab -->
      <NTabPane name="drafts" tab="🚀 Skill草稿">
        <div class="tab-content">
          <NCard :bordered="false">
            <template #header-extra>
              <NButton size="small" @click="loadSkillDrafts">刷新</NButton>
            </template>

            <NSpin :show="skillDraftsLoading">
              <NEmpty v-if="!skillDrafts.length && !skillDraftsLoading" description="暂无待审核的Skill草稿" />
              <NDataTable
                v-else
                :columns="skillDraftColumns"
                :data="skillDrafts"
                :pagination="{
                  page: draftPage,
                  pageSize: draftPageSize,
                  pageCount: Math.ceil(skillDraftsTotal / draftPageSize),
                  prefix: (info) => `共 ${skillDraftsTotal} 条草稿`,
                  onChange: (p) => { draftPage = p; loadSkillDrafts() },
                }"
                size="small"
                class="data-table"
              />
            </NSpin>
          </NCard>
        </div>
      </NTabPane>

      <!-- 4. 统计分析 Tab -->
      <NTabPane name="analytics" tab="📈 统计分析">
        <div class="tab-content">
          <NSpin :show="analyticsLoading">
            <!-- 使用排行 -->
            <NCard title="🏆 最常使用的知识条目 (Top 10)" :bordered="false" class="analytics-card">
              <div v-if="topUsedEntries.length > 0" class="ranking">
                <div v-for="entry in topUsedEntries" :key="entry.id" class="rank-item">
                  <div class="rank-no">{{ entry._rank }}</div>
                  <div class="rank-info">
                    <div class="rank-title">{{ entry.content?.slice(0, 80) }}</div>
                    <div class="rank-meta">
                      <NTag size="small" type="info">{{ entry.module }}</NTag>
                      <NTag size="small">使用 {{ entry.usage_count }} 次</NTag>
                    </div>
                  </div>
                </div>
              </div>
              <NEmpty v-else description="暂无使用数据" />
            </NCard>

            <!-- 待验证条目 -->
            <NCard title="⏳ 待验证条目" :bordered="false" class="analytics-card">
              <div v-if="pendingEntries.length > 0" class="pending-list">
                <div v-for="entry in pendingEntries.slice(0, 10)" :key="entry.id" class="pending-item">
                  <div class="pending-content">{{ entry.content?.slice(0, 100) }}</div>
                  <div class="pending-meta">
                    <NTag size="small">{{ entry.module }}</NTag>
                    <NTag size="small" type="warning">待审核</NTag>
                    <span class="pending-time">{{ new Date(entry.created_at!).toLocaleDateString() }}</span>
                  </div>
                </div>
              </div>
              <NEmpty v-else description="暂无待验证条目" />
            </NCard>

            <!-- 即将过期条目 -->
            <NCard title="⚠️ 即将过期的条目" :bordered="false" class="analytics-card">
              <div v-if="expiredEntries.length > 0" class="expired-list">
                <div v-for="entry in expiredEntries.slice(0, 10)" :key="entry.id" class="expired-item">
                  <div class="expired-content">{{ entry.content?.slice(0, 100) }}</div>
                  <div class="expired-meta">
                    <NTag size="small">{{ entry.module }}</NTag>
                    <NTag size="small" type="error">{{ new Date(entry.expires_at!).toLocaleDateString() }}</NTag>
                  </div>
                </div>
              </div>
              <NEmpty v-else description="暂无即将过期的条目" />
            </NCard>
          </NSpin>
        </div>
      </NTabPane>
    </NTabs>

    <!-- 创建/编辑条目 Modal -->
    <NModal
      v-model:show="showEntryModal"
      preset="dialog"
      :title="editingEntry ? '编辑条目' : '新建条目'"
      style="width: 600px"
      positive-text="保存"
      negative-text="取消"
      @positive-click="submitEntry"
    >
      <NForm label-placement="left" label-width="80">
        <NFormItem label="分类" required>
          <NSelect v-model:value="formEntry.category" :options="categoryOptions" />
        </NFormItem>
        <NFormItem label="模块" required>
          <NSelect v-model:value="formEntry.module" :options="moduleOptions" />
        </NFormItem>
        <NFormItem label="业务类型" required>
          <NSelect v-model:value="formEntry.func_type" :options="funcTypeOptions" />
        </NFormItem>
        <NFormItem label="内容" required>
          <NInput
            v-model:value="formEntry.content"
            type="textarea"
            placeholder="知识内容..."
            :autosize="{ minRows: 6, maxRows: 12 }"
          />
        </NFormItem>
        <NFormItem label="关键词">
          <NInput
            v-model:value="formEntry.keywords"
            type="textarea"
            placeholder="每行一个关键词"
            :autosize="{ minRows: 3, maxRows: 6 }"
          />
        </NFormItem>
        <NFormItem label="置信度">
          <NSlider v-model:value="formEntry.confidence_score" :min="0" :max="1" :step="0.1" />
        </NFormItem>
        <NFormItem label="来源文件">
          <NInput v-model:value="formEntry.source_file" placeholder="文件路径或 Jira 链接" />
        </NFormItem>
        <NFormItem label="维护人">
          <NInput v-model:value="formEntry.maintenance_owner" placeholder="负责人名字" />
        </NFormItem>
      </NForm>
    </NModal>

    <!-- 查看条目 Drawer -->
    <NDrawer
      v-model:show="showEntryDrawer"
      :width="500"
      placement="right"
      title="条目详情"
    >
      <div v-if="viewingEntry" class="entry-detail">
        <div class="detail-section">
          <div class="detail-label">ID</div>
          <div class="detail-value monospace">{{ viewingEntry.id }}</div>
        </div>

        <div class="detail-section">
          <div class="detail-label">内容</div>
          <div class="detail-value pre">{{ viewingEntry.content }}</div>
        </div>

        <div class="detail-section">
          <div class="detail-label">分类</div>
          <div class="detail-value">{{ viewingEntry.category }}</div>
        </div>

        <div class="detail-section">
          <div class="detail-label">模块 / 业务类型</div>
          <div class="detail-value">
            <NTag type="info" size="small">{{ viewingEntry.module }}</NTag>
            <NTag type="warning" size="small" style="margin-left: 8px">{{ viewingEntry.func_type }}</NTag>
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-label">关键词</div>
          <div class="detail-value">
            <NSpace v-if="viewingEntry.keywords?.length">
              <NTag v-for="kw in viewingEntry.keywords" :key="kw" size="small">{{ kw }}</NTag>
            </NSpace>
            <span v-else>-</span>
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-label">置信度</div>
          <div class="detail-value">
            <NProgressBar :percentage="viewingEntry.confidence_score * 100" />
            <span style="margin-left: 8px">{{ (viewingEntry.confidence_score * 100).toFixed(1) }}%</span>
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-label">状态</div>
          <div class="detail-value">
            <NTag :type="viewingEntry.status === 'approved' ? 'success' : 'info'" size="small">
              {{ viewingEntry.status }}
            </NTag>
          </div>
        </div>

        <div class="detail-section">
          <div class="detail-label">验证状态</div>
          <div class="detail-value">
            <NTag :type="viewingEntry.is_verified ? 'success' : 'default'" size="small">
              {{ viewingEntry.is_verified ? '已验证' : '未验证' }}
            </NTag>
          </div>
        </div>

        <div v-if="!viewingEntry.is_verified" class="detail-section">
          <NButton type="primary" @click="markAsVerified">标记为已验证</NButton>
        </div>

        <div class="detail-section">
          <div class="detail-label">使用次数</div>
          <div class="detail-value">{{ viewingEntry.usage_count || 0 }}</div>
        </div>

        <div v-if="viewingEntry.last_used_in_task" class="detail-section">
          <div class="detail-label">最后使用任务</div>
          <div class="detail-value monospace">{{ viewingEntry.last_used_in_task }}</div>
        </div>

        <div class="detail-section">
          <div class="detail-label">创建时间</div>
          <div class="detail-value">{{ viewingEntry.created_at ? new Date(viewingEntry.created_at).toLocaleString('zh-CN') : '-' }}</div>
        </div>

        <div class="detail-section">
          <div class="detail-label">最后更新</div>
          <div class="detail-value">{{ viewingEntry.updated_at ? new Date(viewingEntry.updated_at).toLocaleString('zh-CN') : '-' }}</div>
        </div>

        <div v-if="viewingEntry.source_file" class="detail-section">
          <div class="detail-label">来源文件</div>
          <div class="detail-value monospace">{{ viewingEntry.source_file }}</div>
        </div>

        <div v-if="viewingEntry.maintenance_owner" class="detail-section">
          <div class="detail-label">维护人</div>
          <div class="detail-value">{{ viewingEntry.maintenance_owner }}</div>
        </div>
      </div>
    </NDrawer>

    <!-- Skill 草稿审核 Drawer -->
    <NDrawer
      v-model:show="showDraftReviewDrawer"
      :width="600"
      placement="right"
      title="Skill 草稿审核"
    >
      <div v-if="reviewingDraft" class="draft-review">
        <div class="review-info">
          <div class="info-row">
            <span class="info-label">Skill ID</span>
            <span class="info-value monospace">{{ reviewingDraft.skill_id }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">Skill 名称</span>
            <span class="info-value">{{ reviewingDraft.skill_name }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">分类</span>
            <div class="info-value">
              <NTag type="info" size="small">{{ reviewingDraft.module }}</NTag>
              <NTag type="warning" size="small" style="margin-left: 4px">{{ reviewingDraft.func_type }}</NTag>
            </div>
          </div>
          <div class="info-row">
            <span class="info-label">来源条目</span>
            <div class="info-value">
              <div v-if="reviewingDraft.generated_from_entries?.length > 0" class="source-entries">
                <NTag v-for="id in reviewingDraft.generated_from_entries" :key="id" size="small">{{ id }}</NTag>
              </div>
              <span v-else>无</span>
            </div>
          </div>
        </div>

        <NDivider />

        <div class="draft-content">
          <div class="content-label">草稿内容</div>
          <pre class="content-pre">{{ reviewingDraft.content }}</pre>
        </div>

        <NDivider />

        <NForm label-placement="left" label-width="60">
          <NFormItem label="审核意见">
            <NSelect
              v-model:value="reviewAction"
              :options="[
                { label: '批准', value: 'approve' },
                { label: '打回', value: 'reject' },
              ]"
            />
          </NFormItem>
          <NFormItem label="备注">
            <NInput
              v-model:value="reviewNotes"
              type="textarea"
              placeholder="审核备注（可选）"
              :autosize="{ minRows: 3, maxRows: 6 }"
            />
          </NFormItem>
        </NForm>

        <NSpace class="review-actions">
          <NButton type="primary" @click="submitDraftReview">
            {{ reviewAction === 'approve' ? '批准' : '打回' }}
          </NButton>
          <NButton @click="showDraftReviewDrawer = false">取消</NButton>
        </NSpace>
      </div>
    </NDrawer>
  </div>
</template>

<style scoped>
.kb-management {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 24px;
}

.page-header h1 {
  margin: 0 0 4px 0;
  font-size: 28px;
  font-weight: 600;
}

.subtitle {
  color: #666;
  margin: 0;
  font-size: 14px;
}

.stats-grid {
  margin-bottom: 24px;
}

.stat-card {
  border-radius: 8px;
}

.tabs-container {
  margin-bottom: 24px;
}

.tab-content {
  padding: 12px 0;
}

.filter-card {
  margin-bottom: 16px;
}

.card-mt {
  margin-top: 16px;
}

.data-table {
  min-height: 400px;
}

/* 模块分布 */
.module-dist {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.dist-item {
  display: grid;
  grid-template-columns: 80px 1fr 50px;
  align-items: center;
  gap: 12px;
}

.dist-label {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dist-bar {
  height: 20px;
  background: #f0f0f0;
  border-radius: 4px;
  overflow: hidden;
}

.dist-fill {
  height: 100%;
  background: linear-gradient(90deg, #52c41a, #1890ff);
  transition: width 0.3s ease;
}

.dist-value {
  text-align: right;
  font-size: 13px;
  font-weight: 500;
}

/* 业务类型分布 */
.type-dist {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.type-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px;
  background: #f5f5f5;
  border-radius: 4px;
}

.type-count {
  font-weight: 600;
  font-size: 14px;
}

/* 排行列表 */
.ranking {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.rank-item {
  display: grid;
  grid-template-columns: 30px 1fr;
  gap: 12px;
  padding: 8px 12px;
  background: #fafafa;
  border-radius: 4px;
  align-items: flex-start;
}

.rank-no {
  font-size: 20px;
  font-weight: 700;
  color: #1890ff;
  text-align: center;
  line-height: 1.4;
}

.rank-info {
  min-width: 0;
}

.rank-title {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 4px;
}

.rank-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

/* 待审核 */
.pending-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 400px;
  overflow-y: auto;
}

.pending-item {
  padding: 8px 12px;
  background: #fffbe6;
  border-radius: 4px;
  border-left: 3px solid #faad14;
}

.pending-content {
  font-size: 13px;
  margin-bottom: 6px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 60px;
  overflow: hidden;
}

.pending-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 12px;
}

.pending-time {
  color: #666;
}

/* 即将过期 */
.expired-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 400px;
  overflow-y: auto;
}

.expired-item {
  padding: 8px 12px;
  background: #fff7e6;
  border-radius: 4px;
  border-left: 3px solid #ff7a45;
}

.expired-content {
  font-size: 13px;
  margin-bottom: 6px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 60px;
  overflow: hidden;
}

.expired-meta {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.analytics-card {
  margin-bottom: 16px;
}

/* 条目详情 */
.entry-detail {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-label {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
}

.detail-value {
  font-size: 13px;
  word-break: break-all;
}

.detail-value.monospace {
  font-family: 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  background: #f5f5f5;
  padding: 4px 8px;
  border-radius: 4px;
  overflow-x: auto;
}

.detail-value.pre {
  white-space: pre-wrap;
  background: #f5f5f5;
  padding: 8px;
  border-radius: 4px;
  max-height: 200px;
  overflow-y: auto;
  font-family: 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.5;
}

/* Skill 草稿审核 */
.draft-review {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.review-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.info-row {
  display: grid;
  grid-template-columns: 80px 1fr;
  gap: 12px;
}

.info-label {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
}

.info-value {
  font-size: 13px;
  word-break: break-all;
}

.info-value.monospace {
  font-family: 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  background: #f5f5f5;
  padding: 4px 8px;
  border-radius: 4px;
}

.source-entries {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.draft-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.content-label {
  font-size: 12px;
  font-weight: 600;
  color: #666;
  text-transform: uppercase;
}

.content-pre {
  background: #f5f5f5;
  padding: 12px;
  border-radius: 4px;
  font-family: 'Monaco', 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
  margin: 0;
}

.review-actions {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* 响应式 */
@media (max-width: 1200px) {
  .kb-management {
    padding: 16px;
  }

  .stats-grid {
    :deep(.n-gi) {
      min-width: auto;
    }
  }
}
</style>
