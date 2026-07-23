<script setup lang="ts">
import { ref, onMounted, h, reactive, computed } from 'vue'
import {
  NForm, NFormItem, NInput, NSelect, NInputNumber,
  NButton, NSpace, NTag, NSpin, NEmpty, NTabs, NTabPane,
  NDataTable, NModal, NAlert,
  NDrawer, NDrawerContent, useMessage, useDialog,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import {
  createKnowledgeEntry,
  listKnowledgeEntries,
  updateKnowledgeEntry,
  deleteKnowledgeEntry,
  getKnowledgeStats,
  semanticSearch,
  createSkillDraft,
  listSkillDrafts,
  reviewSkillDraft,
  submitSkillDraftForReview,
  startImportJob,
  subscribeImportProgress,
  saveImportedEntries,
  startFetchUrl,
  startScanFolder,
  listDocuments,
  getDocument,
  deleteDocument,
  getDocumentChunks,
  reconvertDocument,
  // Phase 4
  getSkillSuggestions,
  updateSkillDraft,
  upsertEvalCase,
  confirmEvalCase,
  deleteEvalCase,
  getSkillDraft,
  type KnowledgeEntry,
  type SkillDraft,
  type KnowledgeStats,
  type SemanticSearchResult,
  type ExtractedEntry,
  type KnowledgeDocument,
  type SkillSuggestion,
  type QualityScore,
  checkSkillSimilarity,
  mergeIntoSkill,
  type SimilarSkillItem,
  // 优化计划新增
  createUpgradeDraft,
  startGenerateStream,
  subscribeSkillGenProgress,
  getSkillGenJob,
  type DuplicateItem,
  type RecommendItem,
  type SkillGenJobResult,
  // 生命周期管控
  deleteSkillDraft,
  deprecateSkillDraft,
  deactivateSkill,
  archiveSkillDraft,
  restoreSkillDraft,
  bulkCleanupDrafts,
  hardDeleteEntry,
  bulkArchiveEntries,
  bulkDeleteArchived,
  // 草稿批量操作
  bulkApproveDrafts,
  bulkRejectDrafts,
  bulkDeleteDrafts,
  bulkArchiveSelectedDrafts,
  // 文档编辑
  updateDocument,
  // 治理面板
  getGovernance,
  type GovernanceData,
  // 运行角色（local + 中心已配置 → 隐藏审核入口）
  getRuntimeMode,
} from '@/api/tahp/knowledge'
import { useTahpModulesStore } from '@/stores/tahp/modules'
import EaPageHead from '@/components/layout/EaPageHead.vue'
import EaInnerTabs from '@/components/layout/EaInnerTabs.vue'
import MarkdownRenderer from '@/components/hermes/chat/MarkdownRenderer.vue'

const message = useMessage()
const dialog = useDialog()
const modulesStore = useTahpModulesStore()

const activeTab = ref('dashboard')
const entriesSubTab = ref<'list' | 'search' | 'documents' | 'import'>('list')
const draftsSubTab = ref<'list' | 'workshop'>('list')

const entriesSubTabs = [
  { key: 'list', label: '条目列表' },
  { key: 'search', label: '语义搜索' },
  { key: 'documents', label: '文档库' },
  { key: 'import', label: '文档导入' },
]

const draftsSubTabs = [
  { key: 'list', label: '草稿列表' },
  { key: 'workshop', label: 'Skill 工坊' },
]

// ─── Stats ──────────────────────────────────────────────────────────────
const statsLoading = ref(false)
const stats = ref<KnowledgeStats | null>(null)

// ─── Governance ───────────────────────────────────────────────────────────
const governance = ref<GovernanceData | null>(null)
const governanceLoading = ref(false)

// ─── Entries ─────────────────────────────────────────────────────────────
const entriesLoading = ref(false)
const entries = ref<KnowledgeEntry[]>([])
const entriesTotal = ref(0)
const filterModule = ref('')
const filterStatus = ref('')
const filterFuncType = ref('')
const showAddEntryModal = ref(false)
const editingEntry = ref<KnowledgeEntry | null>(null)
const submittingEntry = ref(false)

const newEntry = reactive<Partial<KnowledgeEntry>>({
  content: '',
  category: '',
  module: '',
  func_type: '',
  keywords: [],
  confidence_score: 0.8,
  source_file: '',
  maintenance_owner: '',
})
const keywordInput = ref('')

// ─── Search ───────────────────────────────────────────────────────────────
const searchQuery = ref('')
const searchLoading = ref(false)
const searchResults = ref<SemanticSearchResult | null>(null)
const searchModule = ref('')
const searchExpandedIds = ref<Set<string>>(new Set())

function searchResultKey(r: KnowledgeEntry & { search_relevance?: number }, index: number): string {
  return r.id || `search-${index}`
}

function stripMarkdownInline(text: string): string {
  return text
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/\*([^*]+)\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .replace(/^\s*[-*+]\s+/gm, '')
    .replace(/^\s*\d+\.\s+/gm, '')
    .replace(/\|/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

function extractEntryPreview(content: string): { title: string; summary: string } {
  const lines = content.split('\n').map(l => l.trim()).filter(Boolean)
  let title = ''
  let summary = ''

  const tldrIdx = lines.findIndex(l =>
    /^(#{1,3}\s*)?(摘要|TL;DR|tl;dr)/i.test(l) ||
    /^\d+\.\s*(摘要|TL;DR)/i.test(l),
  )

  if (tldrIdx >= 0) {
    const raw = lines[tldrIdx]
      .replace(/^#{1,3}\s*/, '')
      .replace(/^\d+\.\s*/, '')
    const afterLabel = raw.replace(/^(摘要\/TL;DR|摘要|TL;DR)[：:\s]*/i, '').trim()
    if (afterLabel.length > 8) title = afterLabel

    const body: string[] = []
    for (let i = tldrIdx + 1; i < lines.length; i++) {
      const line = lines[i]
      if (/^#{1,3}\s/.test(line)) break
      if (/^\d+\.\s+/.test(line) && !line.startsWith('|')) break
      if (line.startsWith('|')) continue
      body.push(line)
      if (body.join(' ').length > 160) break
    }
    summary = stripMarkdownInline(body.join(' '))
  }

  if (!title) {
    const heading = lines.find(l => /^#{1,2}\s+/.test(l) || /^\d+\.\s+\S/.test(l))
    if (heading) {
      title = heading.replace(/^#{1,2}\s+/, '').replace(/^\d+\.\s+/, '')
    }
  }

  if (!summary) {
    const para = lines.find(l =>
      !l.startsWith('#') &&
      !l.startsWith('|') &&
      !/^[-*+]\s/.test(l) &&
      l.length > 16,
    )
    summary = stripMarkdownInline(para || content)
  }

  if (summary.length > 240) summary = summary.slice(0, 240) + '…'
  return { title, summary }
}

function isSearchExpanded(key: string): boolean {
  return searchExpandedIds.value.has(key)
}

function toggleSearchExpand(key: string) {
  const next = new Set(searchExpandedIds.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  searchExpandedIds.value = next
}

function collapseAllSearchResults() {
  searchExpandedIds.value = new Set()
}

const searchResultPreviews = computed(() => {
  const map = new Map<string, { title: string; summary: string }>()
  if (!searchResults.value) return map
  searchResults.value.results.forEach((r, idx) => {
    map.set(searchResultKey(r, idx), extractEntryPreview(r.content))
  })
  return map
})

function getSearchPreview(key: string) {
  return searchResultPreviews.value.get(key) || { title: '', summary: '' }
}

// ─── Skill Drafts ─────────────────────────────────────────────────────────
const draftsLoading = ref(false)
const drafts = ref<SkillDraft[]>([])
const draftsTotal = ref(0)
const showCreateDraftModal = ref(false)
const showReviewDrawer = ref(false)
const reviewingDraft = ref<SkillDraft | null>(null)
const reviewAction = ref<'approve' | 'reject'>('approve')
const reviewNotes = ref('')
const submittingDraft = ref(false)
const submittingReview = ref(false)
// ─── 生命周期管控 ──────────────────────────────────────────────────────
const draftStatusFilter = ref('')  // 空=默认排除archived，逗号分隔多值
const showDeleteConfirmModal = ref(false)
const deletingDraft = ref<SkillDraft | null>(null)
const showDeprecateModal = ref(false)
const deprecatingDraft = ref<SkillDraft | null>(null)
const deprecateReason = ref('')
const showDeactivateModal = ref(false)
const deactivatingDraft = ref<SkillDraft | null>(null)
const deactivateReason = ref('')
const bulkCleanupLoading = ref(false)
const rejectedCount = ref(0)
const bulkArchiveLoading = ref(false)
const bulkDeleteLoading = ref(false)
// 行选择状态
const checkedEntryKeys = ref<string[]>([])
const checkedDraftKeys = ref<string[]>([])
// 草稿批量操作
const bulkDraftLoading = ref(false)
const showBulkRejectModal = ref(false)
const bulkRejectReason = ref('')
// 文档编辑
const showEditDocModal = ref(false)
const editingDoc = ref<KnowledgeDocument | null>(null)
const editDocTitle = ref('')
const editDocModule = ref('')
const submittingDoc = ref(false)

const newDraft = reactive({
  skill_id: '',
  skill_name: '',
  domain_label: '',
  module: '',
  func_type: '',
  content: '',
  entry_ids: [] as string[],
})

// ─── Options ──────────────────────────────────────────────────────────────
const MODULE_OPTIONS = [
  { label: '通信 (Telephony)', value: 'telephony' },
  { label: '驱动 (Kernel-Driver)', value: 'kernel-driver' },
  { label: '内核 (Kernel)', value: 'kernel' },
  { label: '功耗温升 (Power)', value: 'power-mgmt' },
  { label: '共享 (Shared)', value: 'shared' },
]
const MODULE_SHORT: Record<string, string> = {
  telephony: '通信', 'kernel-driver': '驱动', kernel: '内核', 'power-mgmt': '功耗', shared: '共享',
}
const MODULE_COLOR: Record<string, string> = {
  telephony: '#2080f0', 'kernel-driver': '#18a058', kernel: '#36ad6a', 'power-mgmt': '#f0a020', shared: '#722ed1',
}

const FUNC_TYPE_OPTIONS = [
  { label: 'Bug 分析', value: 'bug_analysis' },
  { label: '代码适配', value: 'code_adaptation' },
  { label: '版本适配', value: 'version_adaptation' },
  { label: '运营商移植', value: 'carrier_porting' },
  { label: '质量验测', value: 'ai_self_check' },
]
const FUNC_TYPE_SHORT: Record<string, string> = {
  bug_analysis: 'Bug分析', code_adaptation: '代码适配',
  version_adaptation: '版本适配', carrier_porting: '运营商移植', ai_self_check: '质量验测',
  // 兑容旧数据（中文大类）
  'AI故障分析': 'AI故障分析', 'AI自动化适配': 'AI适配', 'AI自检工具': '质量验测',
  // 中文细分透传
  'Bug分析': 'Bug分析', '代码适配': '代码适配', '版本适配': '版本适配', '运营商移植': '运营商移植', 'AI自检': '质量验测', '质量验测': '质量验测',
}

const STATUS_OPTIONS = [
  { label: '全部状态', value: '' },
  { label: '待审核', value: 'pending_review' },
  { label: '已批准', value: 'approved' },
  { label: '已拒绝', value: 'rejected' },
  { label: '已归档', value: 'archived' },
  { label: '已删除', value: 'deleted' },
]
const STATUS_TYPE: Record<string, 'default' | 'success' | 'error' | 'warning' | 'info'> = {
  pending_review: 'warning', approved: 'success', rejected: 'error', archived: 'default', deleted: 'error',
}
const STATUS_LABEL: Record<string, string> = {
  pending_review: '待审核', approved: '已批准', rejected: '已拒绝', archived: '已归档', deleted: '已删除',
}

const CATEGORY_OPTIONS = [
  { label: '错误模式', value: '错误模式' },
  { label: 'API 规范', value: 'API规范' },
  { label: '最佳实践', value: '最佳实践' },
  { label: '性能优化', value: '性能优化' },
  { label: '集成指南', value: '集成指南' },
  { label: '其他', value: '其他' },
]

// ─── Table columns ────────────────────────────────────────────────────────
const entryColumns: DataTableColumns<KnowledgeEntry> = [
  { type: 'selection' },
  {
    title: '知识内容',
    key: 'content',
    minWidth: 220,
    ellipsis: { tooltip: true },
    render: (r) => h('div', { class: 'cell-content' }, [
      h('div', { class: 'cell-main', title: r.content }, (r.content || '').slice(0, 80) + ((r.content || '').length > 80 ? '…' : '')),
      r.source_file ? h('div', { class: 'cell-sub' }, '📄 ' + r.source_file) : null,
    ].filter(Boolean) as any[]),
  },
  {
    title: '分类',
    key: 'category',
    width: 90,
    align: 'center',
    render: (r) => h('span', { class: 'badge badge-cat' }, r.category || '-'),
  },
  {
    title: '模块',
    key: 'module',
    width: 80,
    align: 'center',
    render: (r) => h(NTag, {
      size: 'small',
      style: { '--n-color': MODULE_COLOR[r.module] + '22', '--n-text-color': MODULE_COLOR[r.module], '--n-border': 'none', fontWeight: 600 },
    }, () => MODULE_SHORT[r.module] || r.module),
  },
  {
    title: '业务类型',
    key: 'func_type',
    width: 88,
    align: 'center',
    render: (r) => h('span', { class: 'badge badge-func' }, FUNC_TYPE_SHORT[r.func_type] || r.func_type),
  },
  {
    title: '状态',
    key: 'status',
    width: 80,
    align: 'center',
    render: (r) => h(NTag, {
      size: 'small',
      type: STATUS_TYPE[r.status || ''] || 'default',
    }, () => STATUS_LABEL[r.status || ''] || r.status),
  },
  {
    title: '置信度',
    key: 'confidence_score',
    width: 75,
    align: 'center',
    render: (r) => {
      const v = r.confidence_score || 0
      const color = v >= 0.8 ? '#18a058' : v >= 0.6 ? '#f0a020' : '#d03050'
      return h('span', { style: { color, fontWeight: 600, fontFamily: 'monospace' } }, v.toFixed(2))
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 140,
    align: 'center',
    render: (r) => {
      const btns: any[] = [
        h(NButton, { size: 'tiny', type: 'primary', ghost: true, onClick: () => editEntry(r) }, () => '编辑'),
      ]
      if (r.status === 'archived') {
        btns.push(h(NButton, { size: 'tiny', type: 'error', ghost: true, onClick: () => confirmHardDeleteEntry(r) }, () => '物理删除'))
      } else {
        btns.push(h(NButton, { size: 'tiny', type: 'error', ghost: true, onClick: () => confirmDeleteEntry(r) }, () => '归档'))
      }
      return h(NSpace, { size: 4 }, () => btns)
    },
  },
]

const draftColumns: DataTableColumns<SkillDraft> = [
  { type: 'selection' },
  {
    title: 'Skill 标识',
    key: 'skill_id',
    width: 160,
    render: (r) => h('div', {}, [
      h('div', { class: 'cell-main' }, r.skill_name),
      h('code', { class: 'cell-code' }, r.skill_id),
    ]),
  },
  {
    title: '域标签',
    key: 'domain_label',
    width: 130,
    render: (r) => h('span', { class: 'badge badge-domain' }, r.domain_label),
  },
  {
    title: '模块 / 业务',
    key: 'module',
    width: 130,
    render: (r) => h(NSpace, { vertical: true, size: 2 }, () => [
      h(NTag, { size: 'tiny', style: { '--n-color': MODULE_COLOR[r.module] + '22', '--n-text-color': MODULE_COLOR[r.module], '--n-border': 'none' } }, () => MODULE_SHORT[r.module] || r.module),
      h('span', { class: 'badge badge-func badge-xs' }, FUNC_TYPE_SHORT[r.func_type] || r.func_type),
    ]),
  },
  {
    title: '来源条目',
    key: 'generated_from_entries',
    width: 80,
    align: 'center',
    render: (r) => h('span', { class: 'entry-count' }, `${(r.generated_from_entries || []).length} 条`),
  },
  {
    title: '状态',
    key: 'status',
    width: 90,
    align: 'center',
    render: (r) => {
      const map: Record<string, 'warning'|'success'|'error'|'default'|'info'> = {
        draft: 'warning', reviewing: 'info', approved: 'success', rejected: 'error',
        deprecated: 'warning', archived: 'default',
      } as any
      const label: Record<string, string> = {
        draft: '草稿', reviewing: '审核中', approved: '已激活', rejected: '已拒绝',
        deprecated: '已废弃', archived: '已归档',
      }
      // 中心已配置：已提交中心待审
      if (centralConfigured.value && ((r as any).submitted_to_central || r.status === 'reviewing')) {
        return h(NTag, { size: 'small', type: 'info' }, () => '已提交中心待审')
      }
      const statusType = map[r.status || 'draft'] || 'default'
      const statusLabel = label[r.status || 'draft'] || r.status
      const style = r.status === 'deprecated' ? { '--n-color': '#fff3e022', '--n-text-color': '#e65100', '--n-border': 'none' } : {}
      return h(NTag, { size: 'small', type: statusType, style }, () => statusLabel)
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 240,
    align: 'center',
    render: (r) => {
      const btns: any[] = [
        h(NButton, { size: 'tiny', quaternary: true, onClick: () => openSkillPreview(r) }, () => '预览'),
      ]
      const s = r.status || 'draft'

      // 研发本机（中心已配置）：可编辑/删除/提交审核；批准拒绝仅在中心后台
      if (centralConfigured.value) {
        if (s === 'draft' || s === 'rejected' || s === 'reviewing') {
          btns.push(h(NButton, { size: 'tiny', type: 'primary', ghost: true, onClick: () => openSkillEditor(r) }, () => '编辑'))
        }
        if (s === 'draft' || s === 'rejected') {
          btns.push(h(NButton, { size: 'tiny', type: 'success', onClick: () => submitDraftForReview(r) }, () => '提交审核'))
          btns.push(h(NButton, { size: 'tiny', type: 'error', quaternary: true, onClick: () => confirmDeleteDraft(r) }, () => '删除'))
        }
        return h(NSpace, { size: 4, wrap: true }, () => btns)
      }

      if (s === 'draft' || s === 'reviewing') {
        btns.push(h(NButton, { size: 'tiny', type: 'success', onClick: () => openReviewModal(r, 'approve') }, () => '✓ 批准'))
        btns.push(h(NButton, { size: 'tiny', type: 'error', ghost: true, onClick: () => openReviewModal(r, 'reject') }, () => '✗ 拒绝'))
      }
      if (s === 'draft' || s === 'rejected') {
        btns.push(h(NButton, { size: 'tiny', type: 'error', quaternary: true, onClick: () => confirmDeleteDraft(r) }, () => '删除'))
      }
      if (s === 'approved') {
        btns.push(h(NButton, { size: 'tiny', type: 'warning', ghost: true, onClick: () => openDeprecateModal(r) }, () => '废弃'))
        btns.push(h(NButton, { size: 'tiny', quaternary: true, onClick: () => doArchiveDraft(r) }, () => '归档'))
      }
      if (s === 'deprecated') {
        btns.push(h(NButton, { size: 'tiny', type: 'error', ghost: true, onClick: () => openDeactivateModal(r) }, () => '下线'))
        btns.push(h(NButton, { size: 'tiny', quaternary: true, onClick: () => doArchiveDraft(r) }, () => '归档'))
      }
      if (s === 'archived') {
        btns.push(h(NButton, { size: 'tiny', type: 'info', ghost: true, onClick: () => doRestoreDraft(r) }, () => '恢复'))
      }
      return h(NSpace, { size: 4, wrap: true }, () => btns)
    },
  },
]

// ─── Lifecycle ────────────────────────────────────────────────────────────
// 中心已配置时（研发本机），审核集中到中心后台，本地仅展示与提交
const centralConfigured = ref(false)
const centralUrl = ref<string | null>(null)
async function loadRuntimeMode() {
  try {
    const mode = await getRuntimeMode()
    centralConfigured.value = mode.role === 'local' && mode.central_configured
    centralUrl.value = mode.central_url
  } catch {
    centralConfigured.value = false
  }
}

onMounted(async () => {
  await modulesStore.refresh()
  await Promise.all([loadStats(), loadDocuments(), loadRuntimeMode()])
})

// ─── Data loaders ─────────────────────────────────────────────────────────
async function loadStats() {
  statsLoading.value = true
  try {
    stats.value = await getKnowledgeStats()
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    statsLoading.value = false
  }
}

async function loadGovernance() {
  governanceLoading.value = true
  try {
    governance.value = await getGovernance()
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    governanceLoading.value = false
  }
}

/** 治理卡片钻取：跳到条目列表并按状态筛选 */
function drillToEntries(opts: { status?: string; module?: string; func_type?: string }) {
  filterStatus.value = opts.status || ''
  filterModule.value = opts.module || ''
  filterFuncType.value = opts.func_type || ''
  activeTab.value = 'entries'
  entriesSubTab.value = 'list'
  loadEntries()
}

/** 治理卡片钻取：跳到文档库 */
function drillToDocuments() {
  activeTab.value = 'entries'
  entriesSubTab.value = 'documents'
  loadDocuments()
}

/** 治理：从盲区一键进入 Skill 工坊生成建议 */
function drillToWorkshop() {
  activeTab.value = 'drafts'
  draftsSubTab.value = 'workshop'
  loadSkillSuggestions()
}

async function loadEntries() {
  entriesLoading.value = true
  try {
    const res = await listKnowledgeEntries({
      module: filterModule.value || undefined,
      status: filterStatus.value || undefined,
      func_type: filterFuncType.value || undefined,
      limit: 50,
    })
    entries.value = res.entries || []
    entriesTotal.value = res.total || 0
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    entriesLoading.value = false
  }
}

async function loadDrafts() {
  draftsLoading.value = true
  try {
    const query: { status?: string; limit?: number } = { limit: 100 }
    if (draftStatusFilter.value) {
      query.status = draftStatusFilter.value
    }
    const res = await listSkillDrafts(query)
    drafts.value = res.drafts || []
    draftsTotal.value = res.total || 0
    // 计算 rejected 数量（用于批量清理按钮）
    rejectedCount.value = drafts.value.filter(d => d.status === 'rejected').length
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    draftsLoading.value = false
  }
}

function setDraftStatusFilter(status: string) {
  draftStatusFilter.value = status
  loadDrafts()
}

// ─── 生命周期操作 ───────────────────────────────────────────────────
function confirmDeleteDraft(draft: SkillDraft) {
  if (draft.status !== 'draft' && draft.status !== 'rejected') {
    message.warning('仅 draft/rejected 状态可删除')
    return
  }
  deletingDraft.value = draft
  showDeleteConfirmModal.value = true
}

async function doDeleteDraft() {
  if (!deletingDraft.value) return
  try {
    await deleteSkillDraft(deletingDraft.value.id!)
    message.success(`草稿 ${deletingDraft.value.skill_name} 已删除`)
    showDeleteConfirmModal.value = false
    await loadDrafts()
  } catch (err) {
    message.error((err as Error).message)
  }
}

function openDeprecateModal(draft: SkillDraft) {
  if (draft.status !== 'approved') {
    message.warning('仅已激活的 Skill 可废弃')
    return
  }
  deprecatingDraft.value = draft
  deprecateReason.value = ''
  showDeprecateModal.value = true
}

async function doDeprecate() {
  if (!deprecatingDraft.value || !deprecateReason.value.trim()) {
    message.warning('废弃原因为必填')
    return
  }
  try {
    await deprecateSkillDraft(deprecatingDraft.value.id!, deprecateReason.value.trim())
    message.success(`Skill ${deprecatingDraft.value.skill_name} 已废弃`)
    showDeprecateModal.value = false
    await loadDrafts()
  } catch (err) {
    message.error((err as Error).message)
  }
}

function openDeactivateModal(draft: SkillDraft) {
  if (draft.status !== 'approved' && draft.status !== 'deprecated') {
    message.warning('仅 approved/deprecated 状态可下线')
    return
  }
  deactivatingDraft.value = draft
  deactivateReason.value = ''
  showDeactivateModal.value = true
}

async function doDeactivate() {
  if (!deactivatingDraft.value || !deactivateReason.value.trim()) {
    message.warning('下线原因为必填')
    return
  }
  try {
    await deactivateSkill(deactivatingDraft.value.id!, deactivateReason.value.trim())
    message.success(`Skill ${deactivatingDraft.value.skill_name} 已下线`)
    showDeactivateModal.value = false
    await loadDrafts()
  } catch (err) {
    message.error((err as Error).message)
  }
}

async function doArchiveDraft(draft: SkillDraft) {
  dialog.warning({
    title: '归档草稿',
    content: `确定归档草稿 "${draft.skill_name}"？归档后可恢复。`,
    positiveText: '确认归档',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await archiveSkillDraft(draft.id!)
        message.success('已归档')
        await loadDrafts()
      } catch (err) {
        message.error((err as Error).message)
      }
    },
  })
}

async function doRestoreDraft(draft: SkillDraft) {
  try {
    await restoreSkillDraft(draft.id!)
    message.success(`草稿 ${draft.skill_name} 已恢复`)
    await loadDrafts()
  } catch (err) {
    message.error((err as Error).message)
  }
}

async function doBulkCleanup() {
  if (rejectedCount.value === 0) { message.info('没有可清理的已拒绝草稿'); return }
  dialog.warning({
    title: '批量清理',
    content: `将删除所有 ${rejectedCount.value} 条已拒绝的草稿，此操作不可恢复。`,
    positiveText: '确认清理',
    negativeText: '取消',
    onPositiveClick: async () => {
      bulkCleanupLoading.value = true
      try {
        const res = await bulkCleanupDrafts()
        message.success(`已清理 ${res.cleaned} 条草稿`)
        await loadDrafts()
      } catch (err) {
        message.error((err as Error).message)
      } finally {
        bulkCleanupLoading.value = false
      }
    },
  })
}

// ─── Entry CRUD ───────────────────────────────────────────────────────────
function openAddEntryModal() {
  editingEntry.value = null
  Object.assign(newEntry, {
    content: '', category: '', module: '', func_type: '',
    keywords: [], confidence_score: 0.8, source_file: '', maintenance_owner: '',
  })
  keywordInput.value = ''
  showAddEntryModal.value = true
}

function editEntry(entry: KnowledgeEntry) {
  editingEntry.value = entry
  Object.assign(newEntry, { ...entry })
  keywordInput.value = ''
  showAddEntryModal.value = true
}

function addKeyword() {
  const t = keywordInput.value.trim()
  if (t && !newEntry.keywords?.includes(t)) {
    ;(newEntry.keywords ??= []).push(t)
  }
  keywordInput.value = ''
}

function removeKeyword(idx: number) {
  newEntry.keywords?.splice(idx, 1)
}

async function submitEntry() {
  if (!newEntry.content?.trim()) { message.warning('内容不能为空'); return }
  if (!newEntry.category) { message.warning('分类不能为空'); return }
  if (!newEntry.module) { message.warning('模块不能为空'); return }
  if (!newEntry.func_type) { message.warning('业务类型不能为空'); return }
  submittingEntry.value = true
  try {
    if (editingEntry.value?.id) {
      await updateKnowledgeEntry(editingEntry.value.id, newEntry)
      message.success('条目已更新')
    } else {
      await createKnowledgeEntry(newEntry as KnowledgeEntry)
      message.success('条目已创建')
    }
    showAddEntryModal.value = false
    await loadEntries()
    await loadStats()
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    submittingEntry.value = false
  }
}

function confirmDeleteEntry(entry: KnowledgeEntry) {
  dialog.warning({
    title: '归档条目',
    content: `将条目标记为“已归档”，可在筛选中恢复查看，但不会出现在正常列表中。`,
    positiveText: '确认归档',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteKnowledgeEntry(entry.id || '')
        message.success('已归档')
        await loadEntries()
        await loadStats()
      } catch (err) {
        message.error((err as Error).message)
      }
    },
  })
}

function confirmHardDeleteEntry(entry: KnowledgeEntry) {
  dialog.error({
    title: '物理删除条目',
    content: `将永久删除条目「${(entry.content || '').slice(0, 50)}...」，此操作不可恢复！`,
    positiveText: '确认删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await hardDeleteEntry(entry.id || '')
        message.success('已永久删除')
        await loadEntries()
        await loadStats()
      } catch (err) {
        message.error((err as Error).message)
      }
    },
  })
}

function doBulkArchiveEntries() {
  if (!checkedEntryKeys.value.length) { message.warning('请先选择条目'); return }
  dialog.warning({
    title: '批量归档',
    content: `将归档已选的 ${checkedEntryKeys.value.length} 条条目。确定继续？`,
    positiveText: '确认归档',
    negativeText: '取消',
    onPositiveClick: async () => {
      bulkArchiveLoading.value = true
      try {
        const res = await bulkArchiveEntries({ ids: checkedEntryKeys.value })
        message.success(`已归档 ${res.archived} 条`)
        checkedEntryKeys.value = []
        await loadEntries()
        await loadStats()
      } catch (err) {
        message.error((err as Error).message)
      } finally {
        bulkArchiveLoading.value = false
      }
    },
  })
}

function doBulkDeleteArchived() {
  if (!checkedEntryKeys.value.length) { message.warning('请先选择条目'); return }
  dialog.error({
    title: '批量物理删除',
    content: `将永久删除已选的 ${checkedEntryKeys.value.length} 条条目，此操作不可恢复！`,
    positiveText: '确认删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      bulkDeleteLoading.value = true
      try {
        const res = await bulkDeleteArchived({ ids: checkedEntryKeys.value })
        message.success(`已删除 ${res.deleted} 条`)
        checkedEntryKeys.value = []
        await loadEntries()
        await loadStats()
      } catch (err) {
        message.error((err as Error).message)
      } finally {
        bulkDeleteLoading.value = false
      }
    },
  })
}

// ─── 草稿批量操作 ──────────────────────────────────────────────────────
function getSelectedDrafts() {
  return drafts.value.filter(d => d.id && checkedDraftKeys.value.includes(d.id))
}

function doBulkApproveDrafts() {
  const selected = getSelectedDrafts().filter(d => d.status === 'draft' || d.status === 'reviewing')
  if (!selected.length) { message.warning('没有可批准的草稿'); return }
  dialog.warning({
    title: '批量批准',
    content: `将批准 ${selected.length} 条草稿并激活为 Skill。`,
    positiveText: '确认批准',
    negativeText: '取消',
    onPositiveClick: async () => {
      bulkDraftLoading.value = true
      try {
        const res = await bulkApproveDrafts(selected.map(d => d.id!))
        message.success(`已批准 ${res.approved} 条`)
        checkedDraftKeys.value = []
        await loadDrafts()
      } catch (err) { message.error((err as Error).message) } finally { bulkDraftLoading.value = false }
    },
  })
}

function doBulkRejectDrafts() {
  const selected = getSelectedDrafts().filter(d => d.status === 'draft' || d.status === 'reviewing')
  if (!selected.length) { message.warning('没有可拒绝的草稿'); return }
  bulkRejectReason.value = ''
  showBulkRejectModal.value = true
}

async function confirmBulkReject() {
  const selected = getSelectedDrafts().filter(d => d.status === 'draft' || d.status === 'reviewing')
  if (!selected.length) return
  bulkDraftLoading.value = true
  try {
    const res = await bulkRejectDrafts(selected.map(d => d.id!), bulkRejectReason.value || undefined)
    message.success(`已拒绝 ${res.rejected} 条`)
    showBulkRejectModal.value = false
    checkedDraftKeys.value = []
    await loadDrafts()
  } catch (err) { message.error((err as Error).message) } finally { bulkDraftLoading.value = false }
}

function doBulkDeleteDrafts() {
  const selected = getSelectedDrafts().filter(d => d.status === 'draft' || d.status === 'rejected')
  if (!selected.length) { message.warning('没有可删除的草稿'); return }
  dialog.error({
    title: '批量删除',
    content: `将永久删除 ${selected.length} 条草稿，此操作不可恢复！`,
    positiveText: '确认删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      bulkDraftLoading.value = true
      try {
        const res = await bulkDeleteDrafts(selected.map(d => d.id!))
        message.success(`已删除 ${res.deleted} 条`)
        checkedDraftKeys.value = []
        await loadDrafts()
      } catch (err) { message.error((err as Error).message) } finally { bulkDraftLoading.value = false }
    },
  })
}

function doBulkArchiveDrafts() {
  const selected = getSelectedDrafts().filter(d => d.status === 'approved' || d.status === 'deprecated')
  if (!selected.length) { message.warning('没有可归档的草稿'); return }
  dialog.warning({
    title: '批量归档',
    content: `将归档 ${selected.length} 条草稿，归档后可恢复。`,
    positiveText: '确认归档',
    negativeText: '取消',
    onPositiveClick: async () => {
      bulkDraftLoading.value = true
      try {
        const res = await bulkArchiveSelectedDrafts(selected.map(d => d.id!))
        message.success(`已归档 ${res.archived} 条`)
        checkedDraftKeys.value = []
        await loadDrafts()
      } catch (err) { message.error((err as Error).message) } finally { bulkDraftLoading.value = false }
    },
  })
}

// ─── 文档编辑 ──────────────────────────────────────────────────────────
function openEditDocModal(doc: KnowledgeDocument) {
  editingDoc.value = doc
  editDocTitle.value = doc.title
  editDocModule.value = doc.module
  showEditDocModal.value = true
}

async function submitEditDoc() {
  if (!editingDoc.value) return
  if (!editDocTitle.value.trim()) { message.warning('标题不能为空'); return }
  submittingDoc.value = true
  try {
    await updateDocument(editingDoc.value.id, { title: editDocTitle.value.trim(), module: editDocModule.value })
    message.success('文档已更新')
    showEditDocModal.value = false
    await loadDocuments()
  } catch (err) { message.error((err as Error).message) } finally { submittingDoc.value = false }
}

// ─── Semantic Search ──────────────────────────────────────────────────────
async function doSearch() {
  if (!searchQuery.value.trim()) { message.warning('请输入查询关键词'); return }
  searchLoading.value = true
  try {
    searchResults.value = await semanticSearch(searchQuery.value, searchModule.value || undefined)
    searchExpandedIds.value = new Set()
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    searchLoading.value = false
  }
}

// ─── Skill Drafts ─────────────────────────────────────────────────────────
function openCreateDraftModal() {
  Object.assign(newDraft, { skill_id: '', skill_name: '', domain_label: '', module: '', func_type: '', content: '', entry_ids: [] })
  showCreateDraftModal.value = true
}

async function submitCreateDraft() {
  if (!newDraft.skill_id.trim()) { message.warning('Skill ID 不能为空'); return }
  if (!newDraft.skill_name.trim()) { message.warning('Skill 名称不能为空'); return }
  if (!newDraft.domain_label.trim()) { message.warning('域标签不能为空'); return }
  if (!newDraft.module) { message.warning('模块不能为空'); return }
  if (!newDraft.func_type) { message.warning('业务类型不能为空'); return }
  submittingDraft.value = true
  try {
    await createSkillDraft(newDraft)
    message.success('Skill 草稿已创建')
    showCreateDraftModal.value = false
    await loadDrafts()
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    submittingDraft.value = false
  }
}

async function submitDraftForReview(draft: SkillDraft) {
  if (!draft.id) return
  try {
    await submitSkillDraftForReview(draft.id)
    message.success(centralConfigured.value ? '已提交中心审核' : '已提交审核')
    await loadDrafts()
    await loadStats()
  } catch (err) {
    message.error((err as Error).message)
  }
}

function openReviewModal(draft: SkillDraft, action: 'approve' | 'reject') {
  reviewingDraft.value = draft
  reviewAction.value = action
  reviewNotes.value = ''
  showReviewDrawer.value = true
}

async function submitReview() {
  if (!reviewingDraft.value) return
  submittingReview.value = true
  try {
    const result = await reviewSkillDraft(reviewingDraft.value.id || '', reviewAction.value, 'admin', reviewNotes.value)
    if (reviewAction.value === 'approve') {
      // 检测系统附加的质量警告
      const hasQualityWarning = result.review_notes?.includes('[系统警告]')
      if (hasQualityWarning) {
        message.success('已批准并激活 Skill', { duration: 3000 })
        message.warning('质量评分偏低，建议后续在 Skill 工坊中完善版本约束和 Eval 用例', { duration: 8000 })
      } else {
        message.success('已批准并激活 Skill ✓')
      }
    } else {
      message.info('草稿已拒绝')
    }
    showReviewDrawer.value = false
    await loadDrafts()
    await loadStats()
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    submittingReview.value = false
  }
}

function onEntriesSubTabChange(sub: string) {
  entriesSubTab.value = sub as typeof entriesSubTab.value
  if (sub === 'list') loadEntries()
  if (sub === 'documents') loadDocuments()
}

function onDraftsSubTabChange(sub: string) {
  draftsSubTab.value = sub as typeof draftsSubTab.value
  if (sub === 'list') loadDrafts()
  if (sub === 'workshop') loadSkillSuggestions()
}

function goToEntriesSub(sub: typeof entriesSubTab.value) {
  activeTab.value = 'entries'
  onEntriesSubTabChange(sub)
}

function goToDraftsSub(sub: typeof draftsSubTab.value) {
  activeTab.value = 'drafts'
  onDraftsSubTabChange(sub)
}

function onTabChange(tab: string) {
  activeTab.value = tab
  if (tab === 'entries') onEntriesSubTabChange(entriesSubTab.value)
  if (tab === 'drafts') onDraftsSubTabChange(draftsSubTab.value)
  if (tab === 'analytics') loadGovernance()
}

// ─── Phase 2: Document Import ─────────────────────────────────────────────────

// Import mode: 'file' = drag-drop upload, 'folder' = local path scan, 'url' = web URL fetch
const importMode        = ref<'file' | 'folder' | 'url'>('file')

const isDragging        = ref(false)
const fileInputRef      = ref<HTMLInputElement | null>(null)
const importJobId       = ref('')
const importStatus      = ref<'idle' | 'processing' | 'done' | 'error'>('idle')
const importProgress    = ref(0)
const importStage       = ref<'upload' | 'parse' | 'convert_markdown' | 'extract' | 'done' | 'error'>('upload')
const importMessage     = ref('')
const importEntries     = ref<ExtractedEntry[]>([])
const importError       = ref('')
const selectedEntryIds  = ref<Set<string>>(new Set())
const savingImport      = ref(false)
const importFileName    = ref('')
let   importEventSource: EventSource | null = null

// Folder mode
const folderPath        = ref('')
const folderRecursive   = ref(false)

// URL mode
const importUrl         = ref('')

// Only the 4 linear progress stages (error is handled separately)
const STAGE_LABELS: Record<string, string> = {
  upload:  '上传',
  parse:   '解析',
  convert_markdown: 'Markdown',
  extract: '提取',
  done:    '完成',
}

const ACCEPT_TYPES = '.txt,.md,.pdf,.docx,.doc'
const MAX_FILE_MB  = 20

// ─── Documents (Phase 3) ─────────────────────────────────────────────────────
const docsLoading        = ref(false)
const documents          = ref<KnowledgeDocument[]>([])
const docsTotal          = ref(0)
const showDocReader      = ref(false)
const readerDoc          = ref<KnowledgeDocument | null>(null)
const readerLoading      = ref(false)
const readerChunks       = ref<KnowledgeEntry[]>([])
const readerShowChunks   = ref(false)
const deletingDocId      = ref('')
const readerShowRaw      = ref(false)        // 切换 Markdown / 原始文本
const reconverting       = ref(false)        // 文档重新转换中

const CONVERSION_LABEL: Record<string, string> = {
  done: '✅ 已规范化',
  failed: '⚠️ 转换失败（显示原文本）',
  skipped: '⏭ 已跳过转换',
  pending: '⏳ 待转换',
}

async function handleReconvert() {
  if (!readerDoc.value?.id) return
  reconverting.value = true
  try {
    const r = await reconvertDocument(readerDoc.value.id)
    readerDoc.value = {
      ...readerDoc.value,
      content_markdown: r.content_markdown,
      conversion_status: r.conversion_status,
      conversion_note: r.conversion_note,
    }
    if (r.conversion_status === 'done') {
      readerShowRaw.value = false
      message.success('已重新转换为 Markdown')
    } else {
      message.warning(r.conversion_note || '转换未成功，仍显示原文本')
    }
  } catch (e) {
    message.error('转换失败：' + (e as Error).message)
  } finally {
    reconverting.value = false
  }
}

async function loadDocuments() {
  docsLoading.value = true
  try {
    const res = await listDocuments()
    documents.value = res.documents
    docsTotal.value = res.total
  } catch (e) {
    message.error('加载文档列表失败：' + (e as Error).message)
  } finally {
    docsLoading.value = false
  }
}

async function openDocReader(doc: KnowledgeDocument) {
  readerDoc.value = null
  readerChunks.value = []
  readerShowChunks.value = false
  readerShowRaw.value = false
  showDocReader.value = true
  readerLoading.value = true
  try {
    const [full, chunksRes] = await Promise.all([
      getDocument(doc.id),
      getDocumentChunks(doc.id),
    ])
    readerDoc.value = full
    readerChunks.value = chunksRes.chunks
  } catch (e) {
    message.error('加载文档失败：' + (e as Error).message)
    showDocReader.value = false
  } finally {
    readerLoading.value = false
  }
}

async function confirmDeleteDoc(doc: KnowledgeDocument) {
  dialog.warning({
    title: '删除文档',
    content: `确认删除「${doc.title}」？关联的 ${doc.chunk_count} 条知识条目也将被归档。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      deletingDocId.value = doc.id
      try {
        await deleteDocument(doc.id)
        message.success('已删除')
        documents.value = documents.value.filter(d => d.id !== doc.id)
        if (readerDoc.value?.id === doc.id) showDocReader.value = false
      } catch (e) {
        message.error('删除失败：' + (e as Error).message)
      } finally {
        deletingDocId.value = ''
      }
    },
  })
}

function formatDocDate(iso: string): string {
  const d = new Date(iso)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function formatCharCount(n: number): string {
  return n >= 10000 ? (n / 10000).toFixed(1) + '万' : n.toLocaleString()
}

function resetImport() {
  importEventSource?.close()
  importEventSource = null
  importJobId.value      = ''
  importStatus.value     = 'idle'
  importProgress.value   = 0
  importStage.value      = 'upload'
  importMessage.value    = ''
  importEntries.value    = []
  importError.value      = ''
  importFileName.value   = ''
  selectedEntryIds.value = new Set()
}

// ─── Folder Scan Mode ─────────────────────────────────────────────────────────

async function processFolderScan() {
  const path = folderPath.value.trim()
  if (!path) { message.warning('请输入文件夹路径'); return }

  resetImport()
  importFileName.value = path
  importStatus.value   = 'processing'
  importProgress.value = 5
  importStage.value    = 'upload'
  importMessage.value  = '正在扫描文件夹...'

  try {
    const { job_id, file_count } = await startScanFolder(path, folderRecursive.value)
    importJobId.value   = job_id
    importMessage.value = `发现 ${file_count} 个文件，开始处理...`

    importEventSource = subscribeImportProgress(job_id)
    importEventSource.onmessage = (e) => {
      try {
        const job = JSON.parse(e.data)
        importProgress.value = job.progress ?? importProgress.value
        importStage.value    = job.stage    ?? importStage.value
        importMessage.value  = job.message  ?? importMessage.value
        if (job.status === 'done') {
          importStatus.value  = 'done'
          importEntries.value = job.entries || []
          selectedEntryIds.value = new Set(importEntries.value.map((e: ExtractedEntry) => e.id))
          importEventSource?.close()
        } else if (job.status === 'error') {
          importStatus.value = 'error'
          importError.value  = job.error || job.message || '未知错误'
          importEventSource?.close()
        }
      } catch { /* ignore */ }
    }
    importEventSource.onerror = () => {
      importStatus.value = 'error'
      importError.value  = 'SSE 连接中断，请重试'
      importEventSource?.close()
    }
  } catch (err) {
    importStatus.value = 'error'
    importError.value  = (err as Error).message
  }
}

// ─── URL Fetch Mode ───────────────────────────────────────────────────────────

async function processUrlFetch() {
  const url = importUrl.value.trim()
  if (!url) { message.warning('请输入网页链接'); return }
  if (!/^https?:\/\/.+/.test(url)) { message.warning('请输入有效的 http/https 链接'); return }

  resetImport()
  importFileName.value = url
  importStatus.value   = 'processing'
  importProgress.value = 5
  importStage.value    = 'upload'
  importMessage.value  = '正在请求网页内容...'

  try {
    const { job_id } = await startFetchUrl(url)
    importJobId.value = job_id

    importEventSource = subscribeImportProgress(job_id)
    importEventSource.onmessage = (e) => {
      try {
        const job = JSON.parse(e.data)
        importProgress.value = job.progress ?? importProgress.value
        importStage.value    = job.stage    ?? importStage.value
        importMessage.value  = job.message  ?? importMessage.value
        if (job.status === 'done') {
          importStatus.value  = 'done'
          importEntries.value = job.entries || []
          selectedEntryIds.value = new Set(importEntries.value.map((e: ExtractedEntry) => e.id))
          importEventSource?.close()
        } else if (job.status === 'error') {
          importStatus.value = 'error'
          importError.value  = job.error || job.message || '未知错误'
          importEventSource?.close()
        }
      } catch { /* ignore */ }
    }
    importEventSource.onerror = () => {
      importStatus.value = 'error'
      importError.value  = 'SSE 连接中断，请重试'
      importEventSource?.close()
    }
  } catch (err) {
    importStatus.value = 'error'
    importError.value  = (err as Error).message
  }
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
  isDragging.value = true
}

function onDragLeave() {
  isDragging.value = false
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  isDragging.value = false
  const file = e.dataTransfer?.files[0]
  if (file) processFile(file)
}

function onFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) processFile(file)
  input.value = ''
}

async function processFile(file: File) {
  const ext = file.name.split('.').pop()?.toLowerCase() || ''
  const allowedExts = ['txt', 'md', 'pdf', 'docx', 'doc']
  if (!allowedExts.includes(ext)) {
    message.warning('仅支持 TXT、MD、PDF、DOCX 格式')
    return
  }
  if (file.size > MAX_FILE_MB * 1024 * 1024) {
    message.warning(`文件大小不能超过 ${MAX_FILE_MB} MB`)
    return
  }

  resetImport()
  importFileName.value  = file.name
  importStatus.value    = 'processing'
  importProgress.value  = 5
  importStage.value     = 'upload'
  importMessage.value   = '正在读取文件...'

  try {
    let params: { filename: string; content?: string; content_base64?: string }

    if (ext === 'txt' || ext === 'md') {
      // Read as text directly
      const content = await file.text()
      params = { filename: file.name, content }
    } else {
      // Read as base64 for binary files
      const buf = await file.arrayBuffer()
      const bytes = new Uint8Array(buf)
      let binary = ''
      for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i])
      params = { filename: file.name, content_base64: btoa(binary) }
    }

    importProgress.value = 15
    importMessage.value  = '正在提交到服务器...'

    const { job_id } = await startImportJob(params)
    importJobId.value = job_id

    // Subscribe to SSE progress
    importEventSource = subscribeImportProgress(job_id)
    importEventSource.onmessage = (e) => {
      try {
        const job = JSON.parse(e.data)
        importProgress.value = job.progress ?? importProgress.value
        importStage.value    = job.stage ?? importStage.value
        importMessage.value  = job.message ?? importMessage.value
        if (job.status === 'done') {
          importStatus.value  = 'done'
          importEntries.value = job.entries || []
          // Default: select all
          selectedEntryIds.value = new Set(importEntries.value.map((e: ExtractedEntry) => e.id))
          importEventSource?.close()
        } else if (job.status === 'error') {
          importStatus.value = 'error'
          importError.value  = job.error || job.message || '未知错误'
          importEventSource?.close()
        }
      } catch { /* ignore */ }
    }
    importEventSource.onerror = () => {
      importStatus.value = 'error'
      importError.value  = 'SSE 连接中断，请重试'
      importEventSource?.close()
    }
  } catch (err) {
    importStatus.value = 'error'
    importError.value  = (err as Error).message
  }
}

function toggleSelectEntry(id: string) {
  if (selectedEntryIds.value.has(id)) {
    selectedEntryIds.value.delete(id)
  } else {
    selectedEntryIds.value.add(id)
  }
  // Force reactivity
  selectedEntryIds.value = new Set(selectedEntryIds.value)
}

async function saveSelectedEntries() {
  if (!importJobId.value) return
  savingImport.value = true
  try {
    const ids = [...selectedEntryIds.value]
    const result = await saveImportedEntries(importJobId.value, ids.length > 0 ? ids : undefined)
    message.success(`已入库 ${result.saved} 条知识条目，文档已保存到文档库`)
    await loadStats()
    await loadDocuments()   // refresh document layer
    resetImport()
    // Phase 4: 检查是否有新的 Skill 推荐
    checkSkillRecommendations()
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    savingImport.value = false
  }
}

// ─── Phase 4: Skill 工坊 ─────────────────────────────────────────────────────

const skillSuggestions    = ref<SkillSuggestion[]>([])
const suggestionsLoading  = ref(false)
const recommendedCount    = ref(0)
// 保存"刚导入后有推荐"的提示状态
const importSuggestNotice = ref<{ module: string; func_type: string; business_domain_label?: string; count: number } | null>(null)

function suggestionGroupKey(s: Pick<SkillSuggestion, 'group_key' | 'module' | 'func_type' | 'business_domain'>): string {
  return s.group_key || `${s.module}::${s.func_type}::${s.business_domain || 'general'}`
}

// Skill 预览（只读审核）
const showSkillPreview     = ref(false)
const previewDraft         = ref<SkillDraft | null>(null)
const previewLoading       = ref(false)

// Skill 编辑器状态
const showSkillEditor       = ref(false)
const editingDraft          = ref<SkillDraft | null>(null)
const editorContent         = ref('')
const editorSkillName       = ref('')
const editorOwner           = ref('')
const editorExclusions      = ref<string[]>([])
const editorNewExclusion    = ref('')
const editorVersions        = ref<string[]>([])
const editorVersionInput    = ref('')
const editorPlatforms       = ref<string[]>([])
const editorPlatformInput   = ref('')
const editorQuality         = ref<QualityScore | null>(null)
const savingDraft           = ref(false)
const generatingSkill       = ref(false)
const generatingFor         = ref('')  // "module::func_type"
const checkingSimilarity    = ref(false)

// 相似 Skill 检查弹窗
const showSimilarModal      = ref(false)
const similarResults        = ref<SimilarSkillItem[]>([])
const similarHasExact       = ref(false)
const similarHasPartial     = ref(false)
const pendingSuggestion     = ref<SkillSuggestion | null>(null)

// 融合到已有 Skill 草稿
const mergingSkill          = ref(false)
const mergingTargetId       = ref('')

// ─── 优化计划新增响应式变量 ───
// 生成进度弹窗
const showGenProgressModal   = ref(false)
const genJobId               = ref('')
const genJobStatus           = ref<SkillGenJobResult | null>(null)
const genProgressSteps       = ref<Array<{ label: string; status: 'wait' | 'process' | 'finish' | 'error' }>>([
  { label: '文档重复检测', status: 'wait' },
  { label: '相似 Skill 检索', status: 'wait' },
  { label: 'AI 生成骨架', status: 'wait' },
  { label: '生成 Eval 用例', status: 'wait' },
  { label: '质量评分计算', status: 'wait' },
])
let genSseSource: EventSource | null = null
let genTimeoutTimer: ReturnType<typeof setTimeout> | null = null
let genSseRetryCount = 0
const GEN_SSE_MAX_RETRIES = 3

// 重复检测弹窗
const showDuplicateModal     = ref(false)
const duplicateItems         = ref<DuplicateItem[]>([])
const pendingSuggestionForDup = ref<SkillSuggestion | null>(null)
// SSE 生成期间暂存当前 suggestion，供重复检测弹窗使用
let currentGenSuggestion: SkillSuggestion | null = null

// 融合推荐弹窗
const showMergeRecommendModal = ref(false)
const mergeRecommendations   = ref<RecommendItem[]>([])
const mergeRecommendLoading  = ref(false)

// Eval 用例编辑
const showAddEvalModal      = ref(false)
const newEvalCase           = reactive({ title: '', input: '', expected_output: '', judgment_criteria: '' })
const submittingEval        = ref(false)


async function loadSkillSuggestions() {
  suggestionsLoading.value = true
  try {
    const res = await getSkillSuggestions()
    skillSuggestions.value = res.suggestions
    recommendedCount.value = res.recommended_count
  } catch (err) {
    message.error('加载 Skill 推荐失败：' + (err as Error).message)
  } finally {
    suggestionsLoading.value = false
  }
}

async function checkSkillRecommendations() {
  try {
    const res = await getSkillSuggestions()
    const top = res.suggestions.find(s => s.recommended)
    if (top) {
      importSuggestNotice.value = {
        module: top.module,
        func_type: top.func_type,
        business_domain_label: top.business_domain_label,
        count: top.entry_count,
      }
    }
  } catch { /* ignore */ }
}

async function startGenerateSkill(suggestion: SkillSuggestion) {
  // ── Step 1: 先检索相似 Skill ──────────────────────────────────────────────
  checkingSimilarity.value = true
  generatingFor.value = suggestionGroupKey(suggestion)
  try {
    const simResult = await checkSkillSimilarity({
      module: suggestion.module,
      func_type: suggestion.func_type,
      entry_ids: suggestion.entry_ids,
      skill_name: suggestion.suggested_skill_name,
      business_domain: suggestion.business_domain,
    })
    if (simResult.similar.length > 0) {
      // 有相似 Skill，暂存 suggestion 并弹出相似度弹窗
      pendingSuggestion.value = suggestion
      similarResults.value = simResult.similar
      similarHasExact.value = simResult.has_exact
      similarHasPartial.value = simResult.has_partial
      showSimilarModal.value = true
      return
    }
  } catch {
    // 检索失败不阻断流程，直接生成
  } finally {
    checkingSimilarity.value = false
    if (!showSimilarModal.value) generatingFor.value = ''
  }

  // ── Step 2: 无相似 Skill，使用 SSE 流程生成 ──────────────────────────────
  await doGenerateSkill(suggestion)
}

/** 实际调用 SSE 流式生成 Skill 草稿（相似检查通过后调用） */
async function doGenerateSkill(suggestion: SkillSuggestion) {
  generatingFor.value = suggestionGroupKey(suggestion)

  // 暂存 suggestion，供 SSE 完成后的重复检测弹窗使用
  currentGenSuggestion = suggestion

  // 重置进度弹窗状态
  genJobId.value = ''
  genJobStatus.value = null
  genProgressSteps.value = [
    { label: '文档重复检测', status: 'wait' },
    { label: '相似 Skill 检索', status: 'wait' },
    { label: 'AI 生成骨架', status: 'wait' },
    { label: '生成 Eval 用例', status: 'wait' },
    { label: '质量评分计算', status: 'wait' },
  ]
  showGenProgressModal.value = true
  generatingSkill.value = true

  try {
    const { job_id } = await startGenerateStream({
      module: suggestion.module,
      func_type: suggestion.func_type,
      entry_ids: suggestion.entry_ids,
      skill_name: suggestion.suggested_skill_name,
      generated_by: 'user',
      document_ids: suggestion.source_document_ids,
      business_domain: suggestion.business_domain,
      business_domain_label: suggestion.business_domain_label,
    })
    genJobId.value = job_id
    subscribeGenProgress(job_id)
  } catch (err) {
    message.error('启动生成任务失败：' + (err as Error).message)
    generatingSkill.value = false
    generatingFor.value = ''
    showGenProgressModal.value = false
  }
}

/** 订阅 SSE 生成进度 */
function subscribeGenProgress(jobId: string) {
  closeGenSse()
  genSseRetryCount = 0
  genSseSource = subscribeSkillGenProgress(jobId)

  genSseSource.onmessage = (e) => {
    try {
      const job: SkillGenJobResult = JSON.parse(e.data)
      genJobStatus.value = job
      updateGenProgressSteps(job)

      if (job.status === 'completed') {
        closeGenSse()
        onGenJobCompleted(job)
      } else if (job.status === 'error') {
        closeGenSse()
        message.error('Skill 生成失败：' + (job.message || '未知错误'), { duration: 8000 })
        generatingSkill.value = false
        generatingFor.value = ''
        // 保持弹窗显示，让用户看到错误状态
      }
    } catch { /* ignore parse errors */ }
  }

  genSseSource.onerror = () => {
    // SSE 断开时尝试重试
    if (genSseRetryCount < GEN_SSE_MAX_RETRIES && genJobId.value && generatingSkill.value) {
      genSseRetryCount++
      // 延迟 2s 后重新连接
      setTimeout(() => {
        if (genJobId.value && generatingSkill.value) {
          genSseSource = subscribeSkillGenProgress(genJobId.value)
          genSseSource.onmessage = (e: MessageEvent) => {
            try {
              const job: SkillGenJobResult = JSON.parse(e.data)
              genJobStatus.value = job
              updateGenProgressSteps(job)
              if (job.status === 'completed') {
                closeGenSse()
                onGenJobCompleted(job)
              } else if (job.status === 'error') {
                closeGenSse()
                message.error('Skill 生成失败：' + (job.message || '未知错误'), { duration: 8000 })
                generatingSkill.value = false
                generatingFor.value = ''
              }
            } catch { /* ignore */ }
          }
          genSseSource.onerror = () => {
            // 重试次数用尽，fallback 到轮询
            closeGenSse()
            pollJobStatus()
          }
        }
      }, 2000)
      return
    }
    // 重试次数用尽，fallback 到轮询
    closeGenSse()
    pollJobStatus()
  }

  // 3分钟超时保护
  genTimeoutTimer = setTimeout(() => {
    closeGenSse()
    message.warning('生成任务超时，请稍后在草稿列表中查看结果', { duration: 8000 })
    generatingSkill.value = false
    generatingFor.value = ''
  }, 3 * 60 * 1000)
}

/** SSE 断开后轮询获取任务状态 */
function pollJobStatus() {
  if (!genJobId.value) return
  getSkillGenJob(genJobId.value).then(job => {
    genJobStatus.value = job
    updateGenProgressSteps(job)
    if (job.status === 'completed') {
      onGenJobCompleted(job)
    } else if (job.status === 'running') {
      // 任务仍在运行，延迟 3s 后再次轮询
      setTimeout(() => pollJobStatus(), 3000)
    } else {
      message.error('生成任务异常中断，请重试', { duration: 5000 })
      generatingSkill.value = false
      generatingFor.value = ''
    }
  }).catch(() => {
    message.error('SSE 连接中断且无法获取任务状态，请重试', { duration: 5000 })
    generatingSkill.value = false
    generatingFor.value = ''
  })
}

function closeGenSse() {
  genSseSource?.close()
  genSseSource = null
  if (genTimeoutTimer) {
    clearTimeout(genTimeoutTimer)
    genTimeoutTimer = null
  }
}

/** 根据 job 状态更新进度步骤 */
function updateGenProgressSteps(job: SkillGenJobResult) {
  const stageMap: Record<string, number> = {
    init: -1,
    duplicate_check: 0,
    similarity_check: 1,
    llm_generate: 2,
    eval_extract: 3,
    quality_score: 4,
    persist: 4,
    done: 4,
  }
  const currentIdx = stageMap[job.stage] ?? -1
  genProgressSteps.value = genProgressSteps.value.map((step, i) => {
    if (job.status === 'error') {
      if (i < currentIdx) return { ...step, status: 'finish' as const }
      if (i === currentIdx) return { ...step, status: 'error' as const }
      return { ...step, status: 'wait' as const }
    }
    if (i < currentIdx) return { ...step, status: 'finish' as const }
    if (i === currentIdx) {
      return { ...step, status: job.status === 'completed' ? 'finish' as const : 'process' as const }
    }
    if (job.status === 'completed') return { ...step, status: 'finish' as const }
    return { ...step, status: 'wait' as const }
  })
}

/** 生成任务完成后处理 */
async function onGenJobCompleted(job: SkillGenJobResult) {
  generatingSkill.value = false
  generatingFor.value = ''

  // 检查是否触发重复检测
  if (job.result?.duplicate_detected && job.result.duplicate_drafts?.length) {
    pendingSuggestionForDup.value = currentGenSuggestion
    currentGenSuggestion = null
    duplicateItems.value = job.result.duplicate_drafts
    showGenProgressModal.value = false
    showDuplicateModal.value = true
    return
  }

  // 检查是否触发相似度检测
  if (job.result?.similar_skills?.length) {
    currentGenSuggestion = null
    showGenProgressModal.value = false
    message.info(`发现 ${job.result.similar_skills.length} 个相似 Skill，建议融合而非新建`, { duration: 6000 })
    await loadDrafts()
    await loadSkillSuggestions()
    return
  }

  // 正常完成，先刷新草稿列表
  currentGenSuggestion = null
  await loadDrafts()
  await loadSkillSuggestions()

  if (job.result?.draft) {
    // 验证草稿确实存在
    try {
      await getSkillDraft(job.result.draft.id!)
    } catch {
      // 草稿获取失败，但仍继续显示
    }

    if (job.result.llm_error) {
      // LLM 失败：保持弹窗显示错误状态，让用户手动关闭
      const detail = job.result.llm_error_detail || job.result.llm_error
      genProgressSteps.value = genProgressSteps.value.map((s, i) =>
        i === 2 ? { ...s, status: 'error' as const } : s
      )
      message.warning(`LLM 未就绪（${detail}），已使用模板骨架，请手动完善`, { duration: 8000 })
      // 不自动关闭弹窗，让用户手动确认
      generatingSkill.value = false
      return
    } else {
      message.success('Skill 已基于文档库生成，请在编辑器中完善')
    }

    // 延迟 1.5s 关闭弹窗，让用户看到完成状态
    await new Promise(resolve => setTimeout(resolve, 1500))
    showGenProgressModal.value = false
    openSkillEditor(job.result.draft)

    // 自动切换到草稿 Tab，清除筛选确保新草稿可见
    draftStatusFilter.value = ''
    goToDraftsSub('list')
  } else {
    message.info('生成完成，请在草稿列表中查看')
    showGenProgressModal.value = false
    // 自动切换到草稿 Tab
    draftStatusFilter.value = ''
    goToDraftsSub('list')
  }
}

/** 重复检测弹窗：强制新建（忽略重复） */
async function handleForceCreate() {
  showDuplicateModal.value = false
  if (!pendingSuggestionForDup.value) {
    // 通过 job result 获取最新 draft，没有 pendingSuggestion 则直接刷新列表
    await loadDrafts()
    await loadSkillSuggestions()
    return
  }
  // 重新以相同参数启动生成（后端会跳过重复检测步骤）
  const suggestion = pendingSuggestionForDup.value
  pendingSuggestionForDup.value = null
  generatingFor.value = suggestionGroupKey(suggestion)
  generatingSkill.value = true
  showGenProgressModal.value = true
  genProgressSteps.value = genProgressSteps.value.map(s => ({ ...s, status: 'wait' as const }))
  try {
    const { job_id } = await startGenerateStream({
      module: suggestion.module,
      func_type: suggestion.func_type,
      entry_ids: suggestion.entry_ids,
      skill_name: suggestion.suggested_skill_name,
      generated_by: 'user',
      document_ids: suggestion.source_document_ids,
      business_domain: suggestion.business_domain,
      business_domain_label: suggestion.business_domain_label,
    })
    genJobId.value = job_id
    subscribeGenProgress(job_id)
  } catch (err) {
    message.error('启动生成失败：' + (err as Error).message)
    generatingSkill.value = false
    generatingFor.value = ''
    showGenProgressModal.value = false
  }
}

/** 重复检测弹窗：打开现有 Skill 查看 */
function handleViewExisting(item: DuplicateItem) {
  showDuplicateModal.value = false
  pendingSuggestionForDup.value = null
  if (item.is_activated) {
    message.info(`已激活 Skill「${item.skill_name}」，请在技能库中找到并编辑`, { duration: 5000 })
  } else {
    openSkillEditorById(item.id)
  }
}

/** 重复检测弹窗：升级草案（为已激活 Skill 创建升级版本） */
async function handleUpgradeDraft(item: DuplicateItem) {
  showDuplicateModal.value = false
  const suggestion = pendingSuggestionForDup.value
  pendingSuggestionForDup.value = null
  try {
    const { draft } = await createUpgradeDraft(item.id, suggestion?.entry_ids)
    message.success(`已为「${item.skill_name}」创建升级草案，请在编辑器中完善内容`)
    openSkillEditor(draft)
    await loadDrafts()
    await loadSkillSuggestions()
  } catch (err) {
    message.error('创建升级草案失败：' + (err as Error).message)
  }
}

/** 相似弹窗：忽略相似，强制新建 */
async function confirmCreateAnyway() {
  showSimilarModal.value = false
  if (pendingSuggestion.value) {
    await doGenerateSkill(pendingSuggestion.value)
    pendingSuggestion.value = null
  }
}

/** 相似弹窗：查看已有 Skill（取消生成，让用户自行决定融合） */
function cancelAndViewSimilar() {
  showSimilarModal.value = false
  pendingSuggestion.value = null
  message.info('已取消生成。建议先在"技能库"中找到对应 Skill，补充相关内容后再决定是否新建。', { duration: 5000 })
}

/** 相似弹窗：融合新知识到已有草稿（只对 type=draft 有效） */
async function handleMergeIntoDraft(item: SimilarSkillItem) {
  if (item.type !== 'draft') {
    message.warning('已激活的 Skill 暂不支持自动融合，请在技能库中手动编辑')
    return
  }
  if (!pendingSuggestion.value) return

  mergingSkill.value = true
  mergingTargetId.value = item.id
  try {
    const res = await mergeIntoSkill(item.id, pendingSuggestion.value.entry_ids)
    showSimilarModal.value = false
    pendingSuggestion.value = null
    if (res.llm_error) {
      message.warning(`LLM 融合遇到问题，已返回原内容：${res.llm_error}`, { duration: 6000 })
    } else {
      message.success(res.message || `已成功融合 ${res.merged_count} 条知识到 Skill`, { duration: 5000 })
    }
    // 打开融合后的草稿编辑器
    openSkillEditor(res.draft)
    await loadDrafts()
    await loadSkillSuggestions()
  } catch (err) {
    message.error('融合失败：' + (err as Error).message)
  } finally {
    mergingSkill.value = false
    mergingTargetId.value = ''
  }
}

/** 相似弹窗：为已激活 Skill 生成升级草案（把新知识合入并走审核） */
async function handleUpgradeActivated(item: SimilarSkillItem) {
  if (!pendingSuggestion.value) return
  mergingSkill.value = true
  mergingTargetId.value = item.id
  try {
    const res = await createUpgradeDraft(item.id, pendingSuggestion.value.entry_ids)
    showSimilarModal.value = false
    pendingSuggestion.value = null
    message.success(`已为「${item.display_name}」生成升级草案，请在草稿列表审核后激活`, { duration: 5000 })
    openSkillEditor(res.draft)
    await loadDrafts()
    await loadSkillSuggestions()
  } catch (err) {
    message.error('生成升级草案失败：' + (err as Error).message)
  } finally {
    mergingSkill.value = false
    mergingTargetId.value = ''
  }
}

function openSkillEditor(draft: SkillDraft) {
  showSkillPreview.value = false
  editingDraft.value = draft
  editorContent.value = draft.content || ''
  editorSkillName.value = draft.skill_name || ''
  editorOwner.value = draft.maintenance_owner || ''
  editorExclusions.value = [...(draft.exclusion_cases || [])]
  editorVersions.value = [...(draft.version_constraints?.android_versions || [])]
  editorPlatforms.value = [...(draft.version_constraints?.chipset_platforms || [])]
  editorQuality.value = draft.quality_score || null
  showSkillEditor.value = true
}

async function openSkillEditorById(draftId: string) {
  try {
    const draft = await getSkillDraft(draftId)
    openSkillEditor(draft)
  } catch (err) {
    message.error('加载草稿失败：' + (err as Error).message)
  }
}

function openSkillPreview(draft: SkillDraft) {
  previewDraft.value = draft
  showSkillPreview.value = true
}

async function openSkillPreviewById(draftId: string) {
  previewLoading.value = true
  try {
    const draft = await getSkillDraft(draftId)
    openSkillPreview(draft)
  } catch (err) {
    message.error('加载预览失败：' + (err as Error).message)
  } finally {
    previewLoading.value = false
  }
}
void openSkillPreviewById

function previewToEditor() {
  if (!previewDraft.value) return
  openSkillEditor(previewDraft.value)
}

function previewToReview() {
  if (!previewDraft.value) return
  openReviewModal(previewDraft.value, 'approve')
  showSkillPreview.value = false
}

async function saveSkillDraft() {
  if (!editingDraft.value?.id) return
  savingDraft.value = true
  try {
    const updated = await updateSkillDraft(editingDraft.value.id, {
      content: editorContent.value,
      skill_name: editorSkillName.value,
      maintenance_owner: editorOwner.value,
      exclusion_cases: editorExclusions.value,
      version_constraints: {
        android_versions: editorVersions.value,
        chipset_platforms: editorPlatforms.value,
      },
    })
    editingDraft.value = updated
    editorQuality.value = updated.quality_score || null
    message.success('草稿已保存')
    await loadDrafts()
  } catch (err) {
    message.error('保存失败：' + (err as Error).message)
  } finally {
    savingDraft.value = false
  }
}

async function submitSkillForReview() {
  if (!editingDraft.value?.id) return
  await saveSkillDraft()

  const proceed = async () => {
    await submitDraftForReview(editingDraft.value!)
    showSkillEditor.value = false
  }

  if (!editorQuality.value?.pass_gate) {
    const score = editorQuality.value?.total ?? 0
    const reasons = editorQuality.value?.blocking_reasons ?? []
    dialog.warning({
      title: `Skill 质量评分偏低（${score}/100）`,
      content: `当前 Skill 尚有以下待补充项：\n${reasons.map(r => `• ${r}`).join('\n')}\n\n建议先完善后再提交，以确保 AI 执行任务时效果更好。`,
      positiveText: '仍要提交审核',
      negativeText: '去完善 Skill',
      onPositiveClick: () => { void proceed() },
    })
    return
  }

  if (centralConfigured.value) {
    await proceed()
    return
  }

  // 单机模式：沿用本地批准激活流程
  openReviewModal({ ...editingDraft.value } as SkillDraft, 'approve')
  showSkillEditor.value = false
}

function addExclusion() {
  const t = editorNewExclusion.value.trim()
  if (t && !editorExclusions.value.includes(t)) {
    editorExclusions.value.push(t)
  }
  editorNewExclusion.value = ''
}

function removeExclusion(idx: number) {
  editorExclusions.value.splice(idx, 1)
}

function addVersion() {
  const t = editorVersionInput.value.trim()
  if (t && !editorVersions.value.includes(t)) editorVersions.value.push(t)
  editorVersionInput.value = ''
}

function removeVersion(idx: number) {
  editorVersions.value.splice(idx, 1)
}

function addPlatform() {
  const t = editorPlatformInput.value.trim()
  if (t && !editorPlatforms.value.includes(t)) editorPlatforms.value.push(t)
  editorPlatformInput.value = ''
}

function removePlatform(idx: number) {
  editorPlatforms.value.splice(idx, 1)
}

async function submitNewEvalCase() {
  if (!editingDraft.value?.id) return
  if (!newEvalCase.title.trim()) { message.warning('用例标题不能为空'); return }
  submittingEval.value = true
  try {
    const updated = await upsertEvalCase(editingDraft.value.id, {
      ...newEvalCase,
      source: 'human',
      status: 'confirmed',
    })
    editingDraft.value = updated
    editorQuality.value = updated.quality_score || null
    Object.assign(newEvalCase, { title: '', input: '', expected_output: '', judgment_criteria: '' })
    showAddEvalModal.value = false
    message.success('Eval 用例已添加')
  } catch (err) {
    message.error('添加失败：' + (err as Error).message)
  } finally {
    submittingEval.value = false
  }
}

async function handleConfirmEval(caseId: string) {
  if (!editingDraft.value?.id) return
  try {
    const updated = await confirmEvalCase(editingDraft.value.id, caseId)
    editingDraft.value = updated
    editorQuality.value = updated.quality_score || null
    message.success('已确认')
  } catch (err) {
    message.error((err as Error).message)
  }
}

async function handleDeleteEval(caseId: string) {
  if (!editingDraft.value?.id) return
  try {
    const updated = await deleteEvalCase(editingDraft.value.id, caseId)
    editingDraft.value = updated
    editorQuality.value = updated.quality_score || null
    message.success('已删除')
  } catch (err) {
    message.error((err as Error).message)
  }
}

function scoreColor(score: number, max: number): string {
  const pct = score / max
  if (pct >= 0.8) return '#18a058'
  if (pct >= 0.5) return '#f0a020'
  return '#d03050'
}


</script>

<template>
  <div class="page page-wide kb-view">
    <EaPageHead title="知识库管理" subtitle="知识条目 · 语义搜索 · 文档库 · Skill 草稿审核">
      <template #actions>
        <button type="button" class="ea-btn-primary" @click="openAddEntryModal">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          新建条目
        </button>
      </template>
    </EaPageHead>

    <!-- ── Top stats bar ─────────────────────────────────── -->
    <NSpin :show="statsLoading">
      <div v-if="stats" class="ea-kb-stats">
        <div class="ea-kb-stat">
          <div class="ea-muted" style="font-size:12px;margin-bottom:6px">知识条目</div>
          <div style="font-size:24px;font-weight:800">{{ stats.total_entries }}</div>
          <div class="ea-muted" style="font-size:11px;margin-top:4px">{{ stats.approved_entries }} 已批准 · {{ stats.pending_entries }} 待审</div>
        </div>
        <div class="ea-kb-stat" style="cursor:pointer" @click="goToEntriesSub('documents')">
          <div class="ea-muted" style="font-size:12px;margin-bottom:6px">原始文档</div>
          <div style="font-size:24px;font-weight:800">{{ stats.total_documents ?? docsTotal }}</div>
          <div class="ea-muted" style="font-size:11px;margin-top:4px">点击查看文档库</div>
        </div>
        <div class="ea-kb-stat" style="cursor:pointer" @click="goToDraftsSub('list')">
          <div class="ea-muted" style="font-size:12px;margin-bottom:6px">Skill 草稿</div>
          <div style="font-size:24px;font-weight:800">{{ stats.total_skill_drafts }}</div>
          <div class="ea-muted" style="font-size:11px;margin-top:4px">{{ stats.approved_skill_drafts }} 已激活 · {{ stats.draft_skill_drafts }} 待审核</div>
        </div>
        <div class="ea-kb-stat">
          <div class="ea-muted" style="font-size:12px;margin-bottom:6px">平均置信度</div>
          <div style="font-size:24px;font-weight:800" :style="{ color: stats.average_confidence >= 0.8 ? 'var(--success)' : 'var(--warn)' }">
            {{ (stats.average_confidence * 100).toFixed(1) }}%
          </div>
          <div class="ea-muted" style="font-size:11px;margin-top:4px">基于 {{ stats.total_entries }} 条数据</div>
        </div>
        <div class="ea-kb-stat">
          <div class="ea-muted" style="font-size:12px;margin-bottom:6px">累计使用次数</div>
          <div style="font-size:24px;font-weight:800">{{ stats.total_usage_count }}</div>
          <div class="ea-muted" style="font-size:11px;margin-top:4px">任务引用量</div>
        </div>
      </div>
    </NSpin>

    <!-- ── Tabs ───────────────────────────────────────────── -->
    <NTabs :value="activeTab" @update:value="onTabChange" class="kb-tabs ea-card" animated>

      <!-- ── Dashboard ─────────────────────────────────── -->
      <NTabPane name="dashboard" tab="仪表板">
        <NSpin :show="statsLoading">
          <div class="dash-empty" v-if="!stats && !statsLoading">
            <NEmpty description="暂无统计数据" />
          </div>
          <div v-else-if="stats" class="dash-quick">
            <div class="ea-section-title">快捷入口</div>
            <div class="dash-quick-grid">
              <button type="button" class="dash-quick-card" @click="goToEntriesSub('list')">
                <span class="dash-quick-icon">📚</span>
                <span class="dash-quick-label">知识条目</span>
                <span class="dash-quick-desc">浏览、筛选与管理条目</span>
              </button>
              <button type="button" class="dash-quick-card" @click="goToEntriesSub('search')">
                <span class="dash-quick-icon">🔍</span>
                <span class="dash-quick-label">语义搜索</span>
                <span class="dash-quick-desc">按关键词检索相关知识</span>
              </button>
              <button type="button" class="dash-quick-card" @click="goToEntriesSub('import')">
                <span class="dash-quick-icon">📥</span>
                <span class="dash-quick-label">文档导入</span>
                <span class="dash-quick-desc">上传文件或抓取网页内容</span>
              </button>
              <button type="button" class="dash-quick-card" @click="goToDraftsSub('workshop')">
                <span class="dash-quick-icon">✨</span>
                <span class="dash-quick-label">Skill 工坊</span>
                <span class="dash-quick-desc">从知识条目生成 Skill 草稿</span>
              </button>
            </div>
            <div class="ea-section-title ea-mt16">数据概览</div>
            <p class="ea-muted" style="font-size:13px">详细模块与业务类型分布请查看「统计分析」标签页。</p>
          </div>
        </NSpin>
      </NTabPane>

      <!-- ── Entries (with sub-nav) ─────────────────────── -->
      <NTabPane name="entries" tab="知识条目">
        <EaInnerTabs :tabs="entriesSubTabs" :model-value="entriesSubTab" @update:model-value="onEntriesSubTabChange" />

        <div v-show="entriesSubTab === 'list'">
        <div class="tab-toolbar">
          <NSpace size="small">
            <NSelect
              v-model:value="filterModule"
              :options="[{ label: '全部模块', value: '' }, ...MODULE_OPTIONS]"
              style="width: 155px"
              size="small"
              clearable
              placeholder="筛选模块"
              @update:value="loadEntries"
            />
            <NSelect
              v-model:value="filterFuncType"
              :options="[{ label: '全部类型', value: '' }, ...FUNC_TYPE_OPTIONS]"
              style="width: 135px"
              size="small"
              clearable
              placeholder="筛选业务类型"
              @update:value="loadEntries"
            />
            <NSelect
              v-model:value="filterStatus"
              :options="STATUS_OPTIONS"
              style="width: 120px"
              size="small"
              clearable
              placeholder="筛选状态"
              @update:value="loadEntries"
            />
            <NButton size="small" @click="loadEntries">
              <template #icon>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>
              </template>
              刷新
            </NButton>
          </NSpace>
          <div class="toolbar-count" v-if="entriesTotal > 0">共 {{ entriesTotal }} 条</div>
        </div>

        <NSpin :show="entriesLoading">
          <NEmpty v-if="!entries.length && !entriesLoading" description="暂无条目 — 点击右上角「新建条目」开始" class="tab-empty">
            <template #extra>
              <NButton size="small" type="primary" @click="openAddEntryModal">新建第一条知识条目</NButton>
            </template>
          </NEmpty>
          <NDataTable
            v-else
            :columns="entryColumns"
            :data="entries"
            :row-key="(r: KnowledgeEntry) => r.id || ''"
            v-model:checked-row-keys="checkedEntryKeys"
            :pagination="{ pageSize: 15 }"
            :bordered="false"
            size="small"
            class="kb-table"
          />
          <!-- 条目批量操作栏 -->
          <div v-if="checkedEntryKeys.length > 0" class="batch-action-bar">
            <span class="batch-count">已选 {{ checkedEntryKeys.length }} 项</span>
            <NButton size="small" @click="checkedEntryKeys = []">取消选择</NButton>
            <NButton size="small" type="warning" :loading="bulkArchiveLoading" @click="doBulkArchiveEntries">批量归档</NButton>
            <NButton size="small" type="error" :loading="bulkDeleteLoading" @click="doBulkDeleteArchived">批量物理删除</NButton>
          </div>
        </NSpin>
        </div>

        <div v-show="entriesSubTab === 'search'">
        <div class="search-bar">
          <NInput
            v-model:value="searchQuery"
            size="medium"
            placeholder="输入关键词，如：RIL 通话丢失 / dts 加载失败 / suspend 唤醒..."
            class="search-input"
            clearable
            @keyup.enter="doSearch"
          >
            <template #prefix>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#aaa" stroke-width="2">
                <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
            </template>
          </NInput>
          <NSelect
            v-model:value="searchModule"
            :options="[{ label: '全部模块', value: '' }, ...MODULE_OPTIONS]"
            style="width: 160px; flex-shrink: 0"
            clearable
            placeholder="限定模块"
          />
          <NButton type="primary" :loading="searchLoading" @click="doSearch" style="flex-shrink: 0">搜索</NButton>
        </div>

        <NSpin :show="searchLoading">
          <div v-if="!searchResults" class="search-hint">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#ddd" stroke-width="1.5"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <p>输入关键词后按 Enter 或点击搜索</p>
          </div>
          <div v-else-if="searchResults.total === 0" class="search-hint">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#ddd" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
            <p>没有找到与"{{ searchQuery }}"相关的条目</p>
          </div>
          <div v-else class="search-results">
            <div class="search-meta-row">
              <span class="search-meta">找到 {{ searchResults.total }} 条相关结果</span>
              <button
                v-if="searchExpandedIds.size > 0"
                type="button"
                class="search-collapse-all"
                @click="collapseAllSearchResults"
              >全部收起</button>
            </div>
            <div
              v-for="(r, idx) in searchResults.results"
              :key="searchResultKey(r, idx)"
              class="result-card"
              :class="{ expanded: isSearchExpanded(searchResultKey(r, idx)) }"
            >
              <div class="result-head">
                <NTag
                  :style="{
                    '--n-color': MODULE_COLOR[r.module || ''] + '22',
                    '--n-text-color': MODULE_COLOR[r.module || ''] || '#888',
                    '--n-border': 'none',
                    fontWeight: 600,
                    marginRight: '6px',
                  }"
                  size="small"
                >{{ MODULE_SHORT[r.module || ''] || r.module }}</NTag>
                <span class="result-category">{{ r.category }}</span>
                <div class="result-relevance">
                  <div class="relevance-bar">
                    <div class="relevance-fill" :style="{ width: Math.min(100, r.search_relevance || 0) + '%' }"></div>
                  </div>
                  <span class="relevance-pct">{{ Math.round(r.search_relevance || 0) }}% 匹配</span>
                </div>
              </div>

              <template v-if="!isSearchExpanded(searchResultKey(r, idx))">
                <div
                  v-if="getSearchPreview(searchResultKey(r, idx)).title"
                  class="result-snippet-title"
                >{{ getSearchPreview(searchResultKey(r, idx)).title }}</div>
                <p class="result-snippet">{{ getSearchPreview(searchResultKey(r, idx)).summary }}</p>
              </template>

              <div v-else class="result-full">
                <MarkdownRenderer class="result-body" :content="r.content" />
              </div>

              <div class="result-actions">
                <div class="result-foot" v-if="r.keywords?.length">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#aaa" stroke-width="2"><path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>
                  {{ r.keywords.slice(0, 6).join(' · ') }}
                </div>
                <button
                  type="button"
                  class="result-toggle"
                  @click="toggleSearchExpand(searchResultKey(r, idx))"
                >
                  {{ isSearchExpanded(searchResultKey(r, idx)) ? '收起' : '展开全文' }}
                  <svg
                    width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
                    :style="{ transform: isSearchExpanded(searchResultKey(r, idx)) ? 'rotate(180deg)' : 'none' }"
                  >
                    <polyline points="6 9 12 15 18 9"/>
                  </svg>
                </button>
              </div>
            </div>
          </div>
        </NSpin>
        </div>

        <div v-show="entriesSubTab === 'documents'">
        <NSpin :show="docsLoading">
          <NEmpty v-if="!docsLoading && documents.length === 0" description="暂无文档，请通过「文档导入」上传" style="padding:60px 0" />
          <div v-else class="doc-grid">
            <div
              v-for="doc in documents"
              :key="doc.id"
              class="doc-card"
              @click="openDocReader(doc)"
            >
              <div class="doc-card-header">
                <div class="doc-icon">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                </div>
                <div class="doc-meta">
                  <div class="doc-title">{{ doc.title }}</div>
                  <div class="doc-filename">{{ doc.filename }}</div>
                </div>
                <NButton
                  size="tiny"
                  quaternary
                  @click.stop="openEditDocModal(doc)"
                  style="flex-shrink:0"
                >✏️</NButton>
                <NButton
                  size="tiny"
                  quaternary
                  type="error"
                  :loading="deletingDocId === doc.id"
                  @click.stop="confirmDeleteDoc(doc)"
                  style="flex-shrink:0"
                >🗑</NButton>
              </div>
              <div class="doc-stats">
                <NTag size="small" :style="{ '--n-color': (MODULE_COLOR[doc.module] || '#722ed1') + '18', '--n-text-color': MODULE_COLOR[doc.module] || '#722ed1', '--n-border': 'none', fontWeight: 600 }">
                  {{ MODULE_SHORT[doc.module] || doc.module }}
                </NTag>
                <span class="doc-stat-item">📄 {{ formatCharCount(doc.char_count) }} 字</span>
                <span class="doc-stat-item">🔖 {{ doc.chunk_count }} 条</span>
                <span class="doc-stat-date">{{ formatDocDate(doc.created_at) }}</span>
              </div>
            </div>
          </div>
        </NSpin>

        <!-- Document Reader Drawer -->
        <NDrawer v-model:show="showDocReader" width="60%" placement="right">
          <NDrawerContent :title="readerDoc?.title || '加载中…'" closable>
            <NSpin :show="readerLoading">
              <div v-if="readerDoc" class="doc-reader">
                <div class="doc-reader-meta">
                  <NTag size="small" :style="{ '--n-color': (MODULE_COLOR[readerDoc.module] || '#722ed1') + '18', '--n-text-color': MODULE_COLOR[readerDoc.module] || '#722ed1', '--n-border': 'none' }">
                    {{ MODULE_SHORT[readerDoc.module] || readerDoc.module }}
                  </NTag>
                  <span class="doc-reader-stat">📄 {{ formatCharCount(readerDoc.char_count) }} 字</span>
                  <span class="doc-reader-stat">🔖 {{ readerDoc.chunk_count }} 条检索片段</span>
                  <span class="doc-reader-stat">🗓 {{ formatDocDate(readerDoc.created_at) }}</span>
                  <span
                    v-if="readerDoc.conversion_status"
                    class="doc-reader-stat"
                    :title="readerDoc.conversion_note || ''"
                  >{{ CONVERSION_LABEL[readerDoc.conversion_status] || readerDoc.conversion_status }}</span>
                </div>

                <!-- Full text -->
                <div class="doc-reader-section-title">
                  <span>📝 文档全文</span>
                  <NSpace size="small" align="center">
                    <NButton
                      v-if="readerDoc.content_markdown"
                      size="tiny"
                      tertiary
                      @click="readerShowRaw = !readerShowRaw"
                    >{{ readerShowRaw ? '查看 Markdown' : '查看原文本' }}</NButton>
                    <NButton
                      size="tiny"
                      tertiary
                      :loading="reconverting"
                      @click="handleReconvert"
                    >{{ readerDoc.content_markdown ? '重新转换' : '转换为 Markdown' }}</NButton>
                  </NSpace>
                </div>
                <MarkdownRenderer
                  v-if="readerDoc.content_markdown && !readerShowRaw"
                  :content="readerDoc.content_markdown"
                  class="doc-markdown"
                />
                <pre v-else class="doc-fulltext">{{ readerDoc.content }}</pre>

                <!-- Chunks toggle -->
                <NButton
                  text
                  type="primary"
                  style="margin-top:16px"
                  @click="readerShowChunks = !readerShowChunks"
                >
                  {{ readerShowChunks ? '▲ 收起' : '▼ 展开' }} AI 检索片段 ({{ readerChunks.length }} 条)
                </NButton>
                <div v-if="readerShowChunks" class="doc-chunks-list">
                  <div v-for="(chunk, idx) in readerChunks" :key="chunk.id" class="doc-chunk-item">
                    <div class="doc-chunk-index">#{{ idx + 1 }}</div>
                    <div class="doc-chunk-body">
                      <div class="doc-chunk-content">{{ chunk.content }}</div>
                      <div class="doc-chunk-tags">
                        <span class="badge badge-cat">{{ chunk.category }}</span>
                        <span class="badge badge-func">{{ FUNC_TYPE_SHORT[chunk.func_type] || chunk.func_type }}</span>
                        <span v-for="kw in chunk.keywords.slice(0,4)" :key="kw" class="kw-tag">{{ kw }}</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </NSpin>
          </NDrawerContent>
        </NDrawer>
        </div>

        <div v-show="entriesSubTab === 'import'">

        <!-- ① Idle: mode selector + input panel -->
        <div v-if="importStatus === 'idle'" class="import-root">

          <!-- Mode tabs -->
          <div class="import-mode-row">
            <button
              class="import-mode-btn"
              :class="{ active: importMode === 'file' }"
              @click="importMode = 'file'"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              上传文件
            </button>
            <button
              class="import-mode-btn"
              :class="{ active: importMode === 'folder' }"
              @click="importMode = 'folder'"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>
              本地文件夹
            </button>
            <button
              class="import-mode-btn"
              :class="{ active: importMode === 'url' }"
              @click="importMode = 'url'"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg>
              网页链接
            </button>
          </div>

          <!-- Panel: Upload File -->
          <template v-if="importMode === 'file'">
            <div
              class="drop-zone"
              :class="{ dragging: isDragging }"
              @dragover="onDragOver"
              @dragleave="onDragLeave"
              @drop="onDrop"
              @click="fileInputRef?.click()"
            >
              <input
                ref="fileInputRef"
                type="file"
                :accept="ACCEPT_TYPES"
                style="display:none"
                @change="onFileSelect"
              />
              <div class="drop-icon-wrap">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                  <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                  <polyline points="17 8 12 3 7 8"/>
                  <line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
              </div>
              <p class="drop-title">拖拽文档到此处，或 <span class="drop-link">点击选择</span></p>
              <p class="drop-sub">自动解析内容，智能提取知识条目</p>
              <div class="drop-types">
                <span class="type-badge pdf">PDF</span>
                <span class="type-badge docx">DOCX</span>
                <span class="type-badge txt">TXT</span>
                <span class="type-badge md">MD</span>
              </div>
              <p class="drop-limit">最大 {{ MAX_FILE_MB }} MB</p>
            </div>
          </template>

          <!-- Panel: Local Folder -->
          <template v-else-if="importMode === 'folder'">
            <div class="import-panel">
              <div class="import-panel-icon">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>
              </div>
              <p class="import-panel-title">批量导入本地文件夹</p>
              <p class="import-panel-sub">输入服务器上的文件夹绝对路径，工程将自动扫描所有文档并批量提取知识条目</p>
              <div class="import-panel-form">
                <NInput
                  v-model:value="folderPath"
                  size="medium"
                  placeholder="例如：/data/docs  或  C:\Users\docs"
                  clearable
                  style="flex: 1"
                  @keyup.enter="processFolderScan"
                >
                  <template #prefix>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#aaa" stroke-width="2"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>
                  </template>
                </NInput>
                <NButton type="primary" @click="processFolderScan" :disabled="!folderPath.trim()">
                  开始扫描
                </NButton>
              </div>
              <div class="import-panel-opts">
                <label class="folder-opt-label">
                  <input type="checkbox" v-model="folderRecursive" class="folder-opt-check" />
                  <span>递归扫描子目录（最多 2 层）</span>
                </label>
              </div>
              <div class="import-panel-types">
                <span class="type-badge pdf">PDF</span>
                <span class="type-badge docx">DOCX</span>
                <span class="type-badge txt">TXT</span>
                <span class="type-badge md">MD</span>
                <span class="import-types-note">支持格式，每个文件单独成文档</span>
              </div>
            </div>
          </template>

          <!-- Panel: Web URL -->
          <template v-else>
            <div class="import-panel">
              <div class="import-panel-icon">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg>
              </div>
              <p class="import-panel-title">从网页链接导入</p>
              <p class="import-panel-sub">输入技术文档、API 文档或文章链接，系统将自动抓取并提取知识条目</p>
              <div class="import-panel-form">
                <NInput
                  v-model:value="importUrl"
                  size="medium"
                  placeholder="https://developer.android.com/..."
                  clearable
                  style="flex: 1"
                  @keyup.enter="processUrlFetch"
                >
                  <template #prefix>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#aaa" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z"/></svg>
                  </template>
                </NInput>
                <NButton type="primary" @click="processUrlFetch" :disabled="!importUrl.trim()">
                  抓取内容
                </NButton>
              </div>
              <div class="import-panel-hints">
                <div class="url-hint-item">📄 AOSP 文档 / Android 开发文档</div>
                <div class="url-hint-item">📋 JIRA / Confluence 页面</div>
                <div class="url-hint-item">📰 技术博客 / 问题分析文章</div>
                <div class="url-hint-item">📌 API 规范 / 接口文档页面</div>
              </div>
            </div>
          </template>

          <!-- Shared tips (only shown for file mode) -->
          <div class="import-tips" v-if="importMode === 'file'">
            <div class="tip-title">💡 支持的内容类型</div>
            <div class="tip-grid">
              <div class="tip-item">
                <div class="tip-icon">📑</div>
                <div>
                  <div class="tip-name">技术文档 / Release Note</div>
                  <div class="tip-desc">自动按章节拆分，提取问题描述、解决方案</div>
                </div>
              </div>
              <div class="tip-item">
                <div class="tip-icon">🐛</div>
                <div>
                  <div class="tip-name">Bug Report / 问题分析</div>
                  <div class="tip-desc">识别 Bug 模式，归类到对应模块和业务类型</div>
                </div>
              </div>
              <div class="tip-item">
                <div class="tip-icon">📐</div>
                <div>
                  <div class="tip-name">API 规范 / 接口文档</div>
                  <div class="tip-desc">提取接口定义、参数说明、示例代码</div>
                </div>
              </div>
              <div class="tip-item">
                <div class="tip-icon">📝</div>
                <div>
                  <div class="tip-name">会议纪要 / 经验总结</div>
                  <div class="tip-desc">从非结构化文本中提取可复用的知识点</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- ② Processing: stage progress -->
        <div v-else-if="importStatus === 'processing'" class="import-progress-root">
          <div class="progress-card">
            <div class="progress-filename">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              {{ importFileName }}
            </div>
            <div class="stage-track">
              <div
                v-for="(label, key) in STAGE_LABELS"
                :key="key"
                class="stage-dot-wrap"
                :class="{
                  active: importStage === key,
                  done: importStage !== key && importProgress >= (key === 'upload' ? 10 : key === 'parse' ? 30 : key === 'convert_markdown' ? 55 : key === 'extract' ? 80 : 100),
                }"
              >
                <div class="stage-dot"></div>
                <div class="stage-label">{{ label }}</div>
              </div>
            </div>
            <div class="progress-bar-wrap">
              <div class="progress-bar-track">
                <div class="progress-bar-fill" :style="{ width: importProgress + '%' }"></div>
              </div>
              <span class="progress-pct">{{ importProgress }}%</span>
            </div>
            <p class="progress-msg">{{ importMessage }}</p>
            <NButton size="small" @click="resetImport" style="margin-top: 16px; opacity: 0.7">取消</NButton>
          </div>
        </div>

        <!-- ③ Error state -->
        <div v-else-if="importStatus === 'error'" class="import-error-root">
          <div class="error-card">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#d03050" stroke-width="1.5">
              <circle cx="12" cy="12" r="10"/>
              <line x1="15" y1="9" x2="9" y2="15"/>
              <line x1="9" y1="9" x2="15" y2="15"/>
            </svg>
            <p class="error-title">解析失败</p>
            <p class="error-desc">{{ importError }}</p>
            <div class="error-actions">
              <NButton type="primary" @click="resetImport">
                {{ importMode === 'url' ? '重新输入链接' : importMode === 'folder' ? '重新扫描' : '重新上传' }}
              </NButton>
            </div>
          </div>
        </div>

        <!-- ④ Done: preview entries -->
        <div v-else-if="importStatus === 'done'" class="import-done-root">
          <div class="preview-header">
            <div class="preview-header-left">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#18a058" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
              <strong>{{ importFileName }}</strong>
              <span class="preview-count">提取了 {{ importEntries.length }} 条知识条目</span>
            </div>
            <NSpace size="small">
              <NButton
                size="small"
                @click="selectedEntryIds = new Set(importEntries.map(e => e.id))"
              >全选</NButton>
              <NButton size="small" @click="selectedEntryIds = new Set()">取消全选</NButton>
              <NButton size="small" @click="resetImport">重新导入</NButton>
              <NButton
                type="primary"
                size="small"
                :loading="savingImport"
                :disabled="selectedEntryIds.size === 0"
                @click="saveSelectedEntries"
              >
                入库选中 ({{ selectedEntryIds.size }})
              </NButton>
            </NSpace>
          </div>

          <div class="preview-list">
            <div
              v-for="entry in importEntries"
              :key="entry.id"
              class="preview-card"
              :class="{ selected: selectedEntryIds.has(entry.id) }"
              @click="toggleSelectEntry(entry.id)"
            >
              <div class="preview-select">
                <div class="select-box" :class="{ checked: selectedEntryIds.has(entry.id) }">
                  <svg v-if="selectedEntryIds.has(entry.id)" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
                </div>
              </div>
              <div class="preview-body">
                <div class="preview-tags">
                  <NTag
                    :style="{
                      '--n-color': (MODULE_COLOR[entry.module] || '#888') + '22',
                      '--n-text-color': MODULE_COLOR[entry.module] || '#888',
                      '--n-border': 'none',
                      fontWeight: 600,
                    }"
                    size="tiny"
                  >{{ MODULE_SHORT[entry.module] || entry.module }}</NTag>
                  <span class="badge badge-cat">{{ entry.category }}</span>
                  <span class="badge badge-func">{{ FUNC_TYPE_SHORT[entry.func_type] || entry.func_type }}</span>
                  <div class="conf-bar-mini" :title="`置信度 ${(entry.confidence_score * 100).toFixed(0)}%`">
                    <div
                      class="conf-fill"
                      :style="{
                        width: (entry.confidence_score * 100) + '%',
                        background: entry.confidence_score >= 0.8 ? '#18a058' : entry.confidence_score >= 0.6 ? '#f0a020' : '#d03050'
                      }"
                    ></div>
                  </div>
                  <span class="conf-pct" :style="{ color: entry.confidence_score >= 0.8 ? '#18a058' : entry.confidence_score >= 0.6 ? '#f0a020' : '#d03050' }">
                    {{ (entry.confidence_score * 100).toFixed(0) }}%
                  </span>
                </div>
                <p class="preview-content">{{ entry.content.slice(0, 200) }}{{ entry.content.length > 200 ? '…' : '' }}</p>
                <div class="preview-kws" v-if="entry.keywords?.length">
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="#aaa" stroke-width="2"><path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>
                  {{ entry.keywords.slice(0, 6).join(' · ') }}
                </div>
              </div>
            </div>
          </div>
        </div>
        </div>
      </NTabPane>

      <!-- ── Skill Drafts (with sub-nav) ─────────────────── -->
      <NTabPane name="drafts" tab="Skill 草稿">
        <EaInnerTabs :tabs="draftsSubTabs" :model-value="draftsSubTab" @update:model-value="onDraftsSubTabChange" />

        <div v-show="draftsSubTab === 'list'">
        <NAlert v-if="centralConfigured" type="info" :bordered="false" style="margin-bottom:10px" :show-icon="true">
          本机为研发端：Skill 草稿保存在本地可编辑；编辑完成后点击「提交审核」同步到
          <a v-if="centralUrl" :href="centralUrl + '/knowledge'" target="_blank" style="text-decoration:underline">中心后台「待审 Skill 草稿」</a>
          <span v-else>中心后台「待审 Skill 草稿」</span>
          。批准 / 拒绝仅在中心进行。
        </NAlert>
        <div class="tab-toolbar">
          <NSpace size="small">
            <NButton size="small" @click="loadDrafts">
              <template #icon>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 11-2.12-9.36L23 10"/></svg>
              </template>
              刷新
            </NButton>
            <NButton size="small" type="primary" @click="openCreateDraftModal">
              <template #icon>
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
              </template>
              新建草稿
            </NButton>
            <NButton v-if="!centralConfigured" size="small" type="error" secondary :loading="bulkCleanupLoading" :disabled="rejectedCount === 0" @click="doBulkCleanup">
              清理已拒绝 ({{ rejectedCount }})
            </NButton>
          </NSpace>
          <NSpace size="small" style="margin-top:6px">
            <NButton size="tiny" :type="!draftStatusFilter ? 'primary' : 'default'" secondary @click="setDraftStatusFilter('')">全部(未归档)</NButton>
            <NButton size="tiny" :type="draftStatusFilter === 'draft' ? 'primary' : 'default'" secondary @click="setDraftStatusFilter('draft')">草稿</NButton>
            <NButton size="tiny" :type="draftStatusFilter === 'reviewing' ? 'primary' : 'default'" secondary @click="setDraftStatusFilter('reviewing')">审核中</NButton>
            <NButton size="tiny" :type="draftStatusFilter === 'approved' ? 'primary' : 'default'" secondary @click="setDraftStatusFilter('approved')">已激活</NButton>
            <NButton size="tiny" :type="draftStatusFilter === 'rejected' ? 'primary' : 'default'" secondary @click="setDraftStatusFilter('rejected')">已拒绝</NButton>
            <NButton size="tiny" :type="draftStatusFilter === 'deprecated' ? 'primary' : 'default'" secondary @click="setDraftStatusFilter('deprecated')">已废弃</NButton>
            <NButton size="tiny" :type="draftStatusFilter === 'archived' ? 'primary' : 'default'" secondary @click="setDraftStatusFilter('archived')">已归档</NButton>
          </NSpace>
          <div class="toolbar-count" v-if="draftsTotal > 0">{{ draftsTotal }} 条</div>
        </div>

        <NSpin :show="draftsLoading">
          <NEmpty v-if="!drafts.length && !draftsLoading" description="暂无 Skill 草稿" class="tab-empty">
            <template #extra>
              <NButton size="small" type="primary" @click="openCreateDraftModal">创建 Skill 草稿</NButton>
            </template>
          </NEmpty>
          <NDataTable
            v-else
            :columns="draftColumns"
            :data="drafts"
            :row-key="(r: SkillDraft) => r.id || ''"
            v-model:checked-row-keys="checkedDraftKeys"
            :pagination="{ pageSize: 15 }"
            :bordered="false"
            size="small"
            class="kb-table"
          />
          <div v-if="checkedDraftKeys.length > 0" class="batch-action-bar">
            <span class="batch-count">已选 {{ checkedDraftKeys.length }} 项</span>
            <NButton size="small" @click="checkedDraftKeys = []">取消选择</NButton>
            <template v-if="!centralConfigured">
              <NButton size="small" type="success" :loading="bulkDraftLoading" @click="doBulkApproveDrafts">批准</NButton>
              <NButton size="small" type="warning" :loading="bulkDraftLoading" @click="doBulkRejectDrafts">拒绝</NButton>
              <NButton size="small" type="error" :loading="bulkDraftLoading" @click="doBulkDeleteDrafts">删除</NButton>
              <NButton size="small" :loading="bulkDraftLoading" @click="doBulkArchiveDrafts">归档</NButton>
            </template>
            <span v-else class="ea-muted" style="font-size:12px">审核操作请前往中心后台</span>
          </div>
        </NSpin>
        </div>

        <div v-show="draftsSubTab === 'workshop'">
        <!-- 导入后推荐提示 -->
        <div class="skill-import-notice" v-if="importSuggestNotice">
          <div class="notice-content">
            <span class="notice-icon">💡</span>
            <span class="notice-text">
              刚导入的内容使 <strong>{{ importSuggestNotice.business_domain_label || importSuggestNotice.module }} / {{ importSuggestNotice.func_type }}</strong>
              分组已有 {{ importSuggestNotice.count }} 条知识，建议生成 Skill 以便 AI 执行任务时使用
            </span>
            <NButton size="tiny" type="primary" @click="importSuggestNotice = null">知道了</NButton>
          </div>
        </div>

        <NSpin :show="suggestionsLoading">
          <!-- 推荐卡片区 -->
          <div class="workshop-section" v-if="skillSuggestions.length > 0 || !suggestionsLoading">
            <div class="workshop-section-hd">
              <span class="workshop-section-title">推荐生成 Skill</span>
              <NButton size="tiny" @click="loadSkillSuggestions">刷新</NButton>
            </div>

            <NEmpty v-if="skillSuggestions.length === 0 && !suggestionsLoading" description="暂无知识条目，请先通过「文档导入」上传文档" style="padding:40px 0" />

            <div class="suggestion-grid" v-else>
              <div
                v-for="s in skillSuggestions"
                :key="s.group_key || suggestionGroupKey(s)"
                class="suggestion-card"
                :class="{ 'suggestion-card--recommended': s.recommended, 'suggestion-card--dim': !s.recommended }"
              >
                <div class="suggestion-card-header">
                  <div class="suggestion-mod-badge">
                    <NTag
                      size="tiny"
                      :style="{ '--n-color': (MODULE_COLOR[s.module] || '#722ed1') + '22', '--n-text-color': MODULE_COLOR[s.module] || '#722ed1', '--n-border': 'none', fontWeight: 600 }"
                    >{{ MODULE_SHORT[s.module] || s.module }}</NTag>
                    <NTag v-if="s.business_domain_label && s.business_domain !== 'general'" size="tiny" type="success">
                      {{ s.business_domain_label }}
                    </NTag>
                    <span class="badge badge-func badge-xs">{{ s.func_type.replace(/_/g, ' ') }}</span>
                  </div>
                  <NTag v-if="s.existing_skill_count > 0" size="tiny" type="warning">
                    已有 {{ s.existing_skill_count }} 个 Skill
                  </NTag>
                  <NTag v-if="s.has_draft" size="tiny" type="info">
                    草稿已存在
                  </NTag>
                </div>
                <div class="suggestion-name">{{ s.suggested_skill_name }}</div>
                <div class="suggestion-stats">
                  <span>{{ s.entry_count }} 条知识条目</span>
                  <span v-if="s.source_document_ids && s.source_document_ids.length > 0" class="suggestion-doc-info">
                    {{ s.source_document_ids.length }} 个源文档
                  </span>
                  <span>置信度 {{ Math.round(s.avg_confidence * 100) }}%</span>
                </div>
                <div class="suggestion-reason">{{ s.reason }}</div>
                <NButton
                  v-if="s.recommended && !s.has_draft"
                  type="primary"
                  size="small"
                  :loading="(generatingSkill || checkingSimilarity) && generatingFor === suggestionGroupKey(s)"
                  :disabled="generatingSkill || checkingSimilarity"
                  @click="startGenerateSkill(s)"
                  class="suggestion-gen-btn"
                >
                  {{ checkingSimilarity && generatingFor === suggestionGroupKey(s) ? '检索相似中…' : '✨ 生成 Skill 草稿' }}
                </NButton>
                <NButton
                  v-else-if="s.has_draft"
                  size="small"
                  @click="setDraftStatusFilter('draft'); goToDraftsSub('list')"
                >查看草稿</NButton>
                <span v-else class="suggestion-need-more">需 {{ 3 - s.entry_count + (s.entry_count < 3 ? s.entry_count : 0) }} 条更多条目</span>
              </div>
            </div>
          </div>
        </NSpin>
        </div>
      </NTabPane>

      <!-- ── Analytics ─────────────────────────────────── -->
      <NTabPane name="analytics" tab="治理面板">
        <NSpin :show="governanceLoading">
          <div class="dash-empty" v-if="!governance && !governanceLoading">
            <NEmpty description="暂无治理数据" />
          </div>
          <template v-else-if="governance">
            <!-- 待办治理卡片：可点击钻取 -->
            <div class="gov-section-title">待处理事项</div>
            <div class="gov-grid">
              <button class="gov-card" :class="{ alert: governance.pending_entries > 0 }" @click="drillToEntries({ status: 'pending_review' })">
                <div class="gov-num">{{ governance.pending_entries }}</div>
                <div class="gov-label">待审核条目</div>
                <div class="gov-hint">点击查看 →</div>
              </button>
              <button class="gov-card" :class="{ warn: governance.expired_entries > 0 }" @click="drillToEntries({})">
                <div class="gov-num">{{ governance.expired_entries }}</div>
                <div class="gov-label">已过期条目</div>
                <div class="gov-hint">点击查看 →</div>
              </button>
              <button class="gov-card" :class="{ warn: governance.expiring_soon > 0 }" @click="drillToEntries({})">
                <div class="gov-num">{{ governance.expiring_soon }}</div>
                <div class="gov-label">30 天内将过期</div>
                <div class="gov-hint">点击查看 →</div>
              </button>
              <button class="gov-card" :class="{ warn: governance.low_confidence > 0 }" @click="drillToEntries({})">
                <div class="gov-num">{{ governance.low_confidence }}</div>
                <div class="gov-label">低置信条目 (&lt;0.6)</div>
                <div class="gov-hint">点击查看 →</div>
              </button>
              <button class="gov-card" @click="drillToEntries({})">
                <div class="gov-num">{{ governance.zero_usage }}</div>
                <div class="gov-label">零调用条目</div>
                <div class="gov-hint">点击查看 →</div>
              </button>
              <button class="gov-card" :class="{ alert: governance.pending_drafts > 0 }" @click="goToDraftsSub('list')">
                <div class="gov-num">{{ governance.pending_drafts }}</div>
                <div class="gov-label">待审 Skill 草稿</div>
                <div class="gov-hint">点击查看 →</div>
              </button>
              <button class="gov-card" :class="{ warn: governance.conversion_failed > 0 }" @click="drillToDocuments()">
                <div class="gov-num">{{ governance.conversion_failed }}</div>
                <div class="gov-label">Markdown 转换失败</div>
                <div class="gov-hint">点击查看 →</div>
              </button>
              <button class="gov-card" @click="drillToDocuments()">
                <div class="gov-num">{{ governance.conversion_skipped }}</div>
                <div class="gov-label">转换跳过(过大)</div>
                <div class="gov-hint">点击查看 →</div>
              </button>
            </div>

            <!-- Skill 覆盖盲区 -->
            <div class="gov-section-title" style="margin-top: 20px">
              Skill 覆盖盲区
              <span class="gov-section-sub">有 ≥3 条知识但无对应 Skill 的领域</span>
            </div>
            <div v-if="governance.blind_spots.length" class="gov-blind-list">
              <div v-for="bs in governance.blind_spots" :key="bs.module + bs.func_type" class="gov-blind-item">
                <div class="gov-blind-info">
                  <NTag size="small" :style="{ '--n-color': (MODULE_COLOR[bs.module] || '#722ed1') + '18', '--n-text-color': MODULE_COLOR[bs.module] || '#722ed1', '--n-border': 'none' }">
                    {{ MODULE_SHORT[bs.module] || bs.module }}
                  </NTag>
                  <span class="badge badge-func badge-xs">{{ FUNC_TYPE_SHORT[bs.func_type] || bs.func_type }}</span>
                  <span class="gov-blind-count">{{ bs.entry_count }} 条知识未沉淀为 Skill</span>
                </div>
                <NButton size="tiny" type="primary" ghost @click="drillToWorkshop()">去生成 →</NButton>
              </div>
            </div>
            <div v-else class="dist-empty">暂无覆盖盲区，知识沉淀情况良好 👍</div>

            <!-- 热门检索 -->
            <div class="gov-section-title" style="margin-top: 20px">热门知识（按调用次数）</div>
            <div v-if="governance.top_used.length" class="gov-top-list">
              <div v-for="(t, i) in governance.top_used" :key="t.id" class="gov-top-item">
                <span class="gov-top-rank">#{{ i + 1 }}</span>
                <NTag size="tiny" :style="{ '--n-color': (MODULE_COLOR[t.module] || '#722ed1') + '18', '--n-text-color': MODULE_COLOR[t.module] || '#722ed1', '--n-border': 'none' }">
                  {{ MODULE_SHORT[t.module] || t.module }}
                </NTag>
                <span class="gov-top-text">{{ t.content_preview }}</span>
                <span class="gov-top-count">{{ t.usage_count }} 次</span>
              </div>
            </div>
            <div v-else class="dist-empty">暂无调用记录</div>
          </template>
        </NSpin>
      </NTabPane>

    </NTabs>

    <!-- ── 新增/编辑条目弹窗 ──────────────────────────── -->
    <NModal
      v-model:show="showAddEntryModal"
      preset="dialog"
      :title="editingEntry ? '✏️ 编辑知识条目' : '📝 新建知识条目'"
      positive-text="保存"
      negative-text="取消"
      style="width: 680px"
      :loading="submittingEntry"
      @positive-click="submitEntry"
    >
      <NForm label-placement="left" label-width="80" size="medium" style="margin-top: 8px">
        <NFormItem label="内容" required>
          <NInput
            v-model:value="newEntry.content"
            type="textarea"
            placeholder="条目内容，支持 Markdown"
            :autosize="{ minRows: 3, maxRows: 10 }"
          />
        </NFormItem>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px">
          <NFormItem label="分类" required>
            <NSelect v-model:value="newEntry.category" :options="CATEGORY_OPTIONS" placeholder="选择分类" />
          </NFormItem>
          <NFormItem label="模块" required>
            <NSelect v-model:value="newEntry.module" :options="MODULE_OPTIONS" placeholder="选择模块" />
          </NFormItem>
          <NFormItem label="业务类型" required>
            <NSelect v-model:value="newEntry.func_type" :options="FUNC_TYPE_OPTIONS" placeholder="选择业务类型" />
          </NFormItem>
          <NFormItem label="置信度">
            <NInputNumber v-model:value="newEntry.confidence_score" :min="0" :max="1" :step="0.05" style="width: 100%" />
          </NFormItem>
        </div>
        <NFormItem label="关键词">
          <div style="width: 100%">
            <NSpace style="margin-bottom: 6px">
              <NInput
                v-model:value="keywordInput"
                placeholder="输入关键词后按 Enter"
                style="width: 220px"
                @keyup.enter="addKeyword"
              />
              <NButton size="small" @click="addKeyword">+ 添加</NButton>
            </NSpace>
            <NSpace v-if="newEntry.keywords?.length" wrap size="small">
              <NTag
                v-for="(kw, i) in newEntry.keywords"
                :key="i"
                type="info"
                closable
                @close="removeKeyword(i)"
              >{{ kw }}</NTag>
            </NSpace>
          </div>
        </NFormItem>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px">
          <NFormItem label="源文件">
            <NInput v-model:value="newEntry.source_file" placeholder="如：ReleaseNote_v13.pdf" />
          </NFormItem>
          <NFormItem label="维护人">
            <NInput v-model:value="newEntry.maintenance_owner" placeholder="负责人姓名" />
          </NFormItem>
        </div>
      </NForm>
    </NModal>

    <!-- ── 创建 Skill 草稿弹窗 ────────────────────────── -->
    <NModal
      v-model:show="showCreateDraftModal"
      preset="dialog"
      title="🚀 新建 Skill 草稿"
      positive-text="创建"
      negative-text="取消"
      style="width: 680px"
      :loading="submittingDraft"
      @positive-click="submitCreateDraft"
    >
      <NForm label-placement="left" label-width="90" size="medium" style="margin-top: 8px">
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px">
          <NFormItem label="Skill ID" required>
            <NInput v-model:value="newDraft.skill_id" placeholder="如：ril-call-loss-fix" />
          </NFormItem>
          <NFormItem label="Skill 名称" required>
            <NInput v-model:value="newDraft.skill_name" placeholder="如：RIL通话丢失修复" />
          </NFormItem>
          <NFormItem label="域标签" required>
            <NInput v-model:value="newDraft.domain_label" placeholder="如：RIL 通话问题" />
          </NFormItem>
          <NFormItem label="模块" required>
            <NSelect v-model:value="newDraft.module" :options="MODULE_OPTIONS" placeholder="选择模块" />
          </NFormItem>
          <NFormItem label="业务类型" required>
            <NSelect v-model:value="newDraft.func_type" :options="FUNC_TYPE_OPTIONS" placeholder="选择业务类型" />
          </NFormItem>
        </div>
        <NFormItem label="内容说明">
          <NInput
            v-model:value="newDraft.content"
            type="textarea"
            placeholder="Skill 详细说明（Markdown 格式，可选）"
            :autosize="{ minRows: 5, maxRows: 12 }"
            style="font-family: monospace; font-size: 12px"
          />
        </NFormItem>
      </NForm>
    </NModal>

    <!-- ── 审核草稿 Drawer ────────────────────────────── -->
    <NDrawer v-model:show="showReviewDrawer" :width="520" placement="right" @after-leave="reviewingDraft = null">
      <NDrawerContent title="审核 Skill 草稿" closable>
        <div v-if="reviewingDraft" class="review-body">
          <div class="review-info-grid">
            <div class="review-info-item">
              <span class="review-info-label">Skill ID</span>
              <code class="review-code">{{ reviewingDraft.skill_id }}</code>
            </div>
            <div class="review-info-item">
              <span class="review-info-label">名称</span>
              <strong>{{ reviewingDraft.skill_name }}</strong>
            </div>
            <div class="review-info-item">
              <span class="review-info-label">模块</span>
              <NTag :style="{ '--n-color': MODULE_COLOR[reviewingDraft.module]+'22', '--n-text-color': MODULE_COLOR[reviewingDraft.module], '--n-border':'none' }" size="small">
                {{ MODULE_SHORT[reviewingDraft.module] || reviewingDraft.module }}
              </NTag>
            </div>
            <div class="review-info-item">
              <span class="review-info-label">业务类型</span>
              <span class="badge badge-func">{{ FUNC_TYPE_SHORT[reviewingDraft.func_type] || reviewingDraft.func_type }}</span>
            </div>
          </div>
          <div class="review-content-wrap">
            <div class="review-info-label" style="margin-bottom: 6px">Skill 内容</div>
            <pre class="review-content">{{ reviewingDraft.content || '（无内容）' }}</pre>
          </div>
          <div class="review-actions">
            <div class="review-action-label">审核操作</div>
            <div class="review-btn-group">
              <button
                class="review-btn approve"
                :class="{ active: reviewAction === 'approve' }"
                @click="reviewAction = 'approve'"
              >✓ 批准并激活</button>
              <button
                class="review-btn reject"
                :class="{ active: reviewAction === 'reject' }"
                @click="reviewAction = 'reject'"
              >✗ 拒绝</button>
            </div>
            <NInput
              v-model:value="reviewNotes"
              type="textarea"
              placeholder="审核备注（可选）"
              :autosize="{ minRows: 2, maxRows: 5 }"
              style="margin-top: 10px"
            />
            <NButton
              :type="reviewAction === 'approve' ? 'success' : 'error'"
              :loading="submittingReview"
              style="width: 100%; margin-top: 12px"
              @click="submitReview"
            >
              {{ reviewAction === 'approve' ? '✓ 批准并写入 skills/' : '✗ 确认拒绝' }}
            </NButton>
          </div>
        </div>
      </NDrawerContent>
    </NDrawer>
    <!-- ── Skill 预览 Modal（只读审核） ─────────────────── -->
    <NModal
      v-model:show="showSkillPreview"
      preset="card"
      :title="previewDraft ? `Skill 预览：${previewDraft.skill_name}` : 'Skill 预览'"
      class="skill-preview-modal"
      :style="{ width: '92%', maxWidth: '960px' }"
      :content-style="{
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        flex: '1 1 auto',
        minHeight: '0',
        padding: '12px 20px 0',
      }"
      @after-leave="previewDraft = null"
    >
      <NSpin :show="previewLoading" class="skill-preview-spin">
        <div v-if="previewDraft" class="skill-preview-wrap">
          <div class="skill-preview-meta">
            <div class="skill-preview-meta-row">
              <code class="cell-code">{{ previewDraft.skill_id }}</code>
              <NTag size="small" type="info">{{ previewDraft.domain_label }}</NTag>
              <NTag
                v-if="previewDraft.business_domain && previewDraft.business_domain !== 'general'"
                size="small"
                type="success"
              >{{ previewDraft.domain_label?.split('—').pop()?.trim() || previewDraft.business_domain }}</NTag>
              <NTag size="small">{{ MODULE_SHORT[previewDraft.module] || previewDraft.module }}</NTag>
              <NTag size="small" type="warning">{{ FUNC_TYPE_SHORT[previewDraft.func_type] || previewDraft.func_type }}</NTag>
              <NTag v-if="previewDraft.quality_score" size="small" :type="previewDraft.quality_score.pass_gate ? 'success' : 'warning'">
                质量 Q{{ previewDraft.quality_score.total }}
              </NTag>
            </div>
            <div class="skill-preview-meta-sub">
              来源 {{ (previewDraft.generated_from_entries || []).length }} 条知识条目
              <span v-if="previewDraft.source_document_ids?.length"> · {{ previewDraft.source_document_ids.length }} 个源文档</span>
            </div>
          </div>
          <div class="skill-preview-scroll">
            <div class="skill-preview-body-inner">
              <MarkdownRenderer class="skill-preview-body" :content="previewDraft.content || '（暂无内容）'" />
            </div>
          </div>
        </div>
        <NEmpty v-else description="暂无预览内容" />
      </NSpin>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showSkillPreview = false">关闭</NButton>
          <NButton v-if="previewDraft" @click="previewToEditor">编辑</NButton>
          <NButton
            v-if="previewDraft && (previewDraft.status === 'draft' || previewDraft.status === 'rejected') && centralConfigured"
            type="success"
            @click="previewDraft && submitDraftForReview(previewDraft); showSkillPreview = false"
          >提交审核</NButton>
          <NButton
            v-if="previewDraft && !centralConfigured && (previewDraft.status === 'draft' || previewDraft.status === 'reviewing')"
            type="success"
            @click="previewToReview"
          >批准发布</NButton>
        </NSpace>
      </template>
    </NModal>
    <!-- ── Skill 编辑器 Drawer ─────────────────────────── -->
    <NDrawer v-model:show="showSkillEditor" :width="1080" placement="right" @after-leave="editingDraft = null">
      <NDrawerContent :title="`✏️ 编辑 Skill：${editingDraft?.skill_name || ''}`" closable>
        <div v-if="editingDraft" class="skill-editor-wrap">

          <!-- 左列：内容编辑区 -->
          <div class="skill-editor-left">
            <div class="skill-editor-section-hd">Skill 内容 <span class="skill-editor-hint">（Markdown 格式）</span></div>
            <NInput
              v-model:value="editorContent"
              type="textarea"
              placeholder="编辑 Skill 内容…"
              :autosize="{ minRows: 28, maxRows: 50 }"
              style="font-family: 'Courier New', Courier, monospace; font-size: 12px; line-height: 1.7"
            />

            <!-- 不适用情况 -->
            <div class="skill-editor-section-hd" style="margin-top:16px">
              ⚠️ 不适用情况
            </div>
            <div class="chip-input-row">
              <NInput
                v-model:value="editorNewExclusion"
                placeholder="输入不适用情况后按 Enter"
                size="small"
                style="flex:1"
                @keyup.enter="addExclusion"
              />
              <NButton size="small" @click="addExclusion">+ 添加</NButton>
            </div>
            <div class="chip-list" v-if="editorExclusions.length">
              <NTag
                v-for="(ex, i) in editorExclusions"
                :key="i"
                type="warning"
                closable
                size="small"
                @close="removeExclusion(i)"
              >{{ ex }}</NTag>
            </div>
            <div v-else class="chip-empty">暂无不适用情况</div>

            <!-- 维护人 -->
            <div class="skill-editor-section-hd" style="margin-top:14px">维护人</div>
            <NInput v-model:value="editorOwner" placeholder="负责人姓名" size="small" style="max-width:240px" />
          </div>

          <!-- 右列：质量面板 -->
          <div class="skill-editor-right">

            <!-- 质量得分卡 -->
            <div class="quality-panel">
              <div class="quality-panel-hd">
                <span class="quality-panel-title">质量评分</span>
                <span
                  class="quality-gate-badge"
                  :class="editorQuality?.pass_gate ? 'gate-pass' : 'gate-fail'"
                >
                  {{ editorQuality?.pass_gate ? '✓ 通过门禁' : '✗ 未达标' }}
                </span>
              </div>

              <div v-if="editorQuality" class="quality-score-ring-row">
                <div class="quality-score-ring">
                  <svg viewBox="0 0 60 60" width="60" height="60">
                    <circle cx="30" cy="30" r="24" fill="none" stroke="rgba(0,0,0,.08)" stroke-width="6"/>
                    <circle
                      cx="30" cy="30" r="24" fill="none"
                      :stroke="scoreColor(editorQuality.total, 100)"
                      stroke-width="6"
                      stroke-linecap="round"
                      :stroke-dasharray="`${(editorQuality.total / 100) * 150.8} 150.8`"
                      stroke-dashoffset="0"
                      transform="rotate(-90 30 30)"
                    />
                    <text x="30" y="34" text-anchor="middle" font-size="13" font-weight="700"
                      :fill="scoreColor(editorQuality.total, 100)">{{ editorQuality.total }}</text>
                  </svg>
                </div>
                <div class="quality-dims">
                  <div class="quality-dim-item">
                    <span class="quality-dim-name">结构完整性</span>
                    <div class="quality-dim-bar-track">
                      <div class="quality-dim-bar-fill" :style="{ width: (editorQuality.structure / 20 * 100) + '%', background: scoreColor(editorQuality.structure, 20) }"></div>
                    </div>
                    <span class="quality-dim-val">{{ editorQuality.structure }}/20</span>
                  </div>
                  <div class="quality-dim-item">
                    <span class="quality-dim-name">不适用情况 <span class="quality-required">必填</span></span>
                    <div class="quality-dim-bar-track">
                      <div class="quality-dim-bar-fill" :style="{ width: (editorQuality.exclusions / 15 * 100) + '%', background: scoreColor(editorQuality.exclusions, 15) }"></div>
                    </div>
                    <span class="quality-dim-val">{{ editorQuality.exclusions }}/15</span>
                  </div>
                  <div class="quality-dim-item">
                    <span class="quality-dim-name">版本范围 <span class="quality-required">必填</span></span>
                    <div class="quality-dim-bar-track">
                      <div class="quality-dim-bar-fill" :style="{ width: (editorQuality.version_range / 20 * 100) + '%', background: scoreColor(editorQuality.version_range, 20) }"></div>
                    </div>
                    <span class="quality-dim-val">{{ editorQuality.version_range }}/20</span>
                  </div>
                  <div class="quality-dim-item">
                    <span class="quality-dim-name">Eval 用例 <span class="quality-required">必填</span></span>
                    <div class="quality-dim-bar-track">
                      <div class="quality-dim-bar-fill" :style="{ width: (editorQuality.eval_cases / 25 * 100) + '%', background: scoreColor(editorQuality.eval_cases, 25) }"></div>
                    </div>
                    <span class="quality-dim-val">{{ editorQuality.eval_cases }}/25</span>
                  </div>
                  <div class="quality-dim-item">
                    <span class="quality-dim-name">无冲突</span>
                    <div class="quality-dim-bar-track">
                      <div class="quality-dim-bar-fill" :style="{ width: (editorQuality.no_conflict / 10 * 100) + '%', background: scoreColor(editorQuality.no_conflict, 10) }"></div>
                    </div>
                    <span class="quality-dim-val">{{ editorQuality.no_conflict }}/10</span>
                  </div>
                  <div class="quality-dim-item">
                    <span class="quality-dim-name">维护人</span>
                    <div class="quality-dim-bar-track">
                      <div class="quality-dim-bar-fill" :style="{ width: (editorQuality.owner / 10 * 100) + '%', background: scoreColor(editorQuality.owner, 10) }"></div>
                    </div>
                    <span class="quality-dim-val">{{ editorQuality.owner }}/10</span>
                  </div>
                </div>
              </div>
              <div v-else class="quality-no-data">保存后计算质量得分</div>

              <!-- 阻塞原因 -->
              <div v-if="editorQuality && editorQuality.blocking_reasons.length" class="quality-blocks">
                <div class="quality-block-title">⛔ 提交审核阻塞原因</div>
                <div v-for="r in editorQuality.blocking_reasons" :key="r" class="quality-block-item">{{ r }}</div>
              </div>
            </div>

            <!-- 版本约束 -->
            <div class="skill-editor-section-hd" style="margin-top:14px">版本约束</div>
            <div class="version-constraint-form">
              <div class="version-constraint-row">
                <span class="version-constraint-label">Android 版本</span>
                <div class="chip-input-row">
                  <NInput v-model:value="editorVersionInput" placeholder="如 Android 13" size="small" style="flex:1" @keyup.enter="addVersion" />
                  <NButton size="small" @click="addVersion">+</NButton>
                </div>
                <div class="chip-list" v-if="editorVersions.length">
                  <NTag v-for="(v,i) in editorVersions" :key="i" type="info" closable size="small" @close="removeVersion(i)">{{ v }}</NTag>
                </div>
              </div>
              <div class="version-constraint-row">
                <span class="version-constraint-label">芯片平台</span>
                <div class="chip-input-row">
                  <NInput v-model:value="editorPlatformInput" placeholder="如 MT6985 / SM8550" size="small" style="flex:1" @keyup.enter="addPlatform" />
                  <NButton size="small" @click="addPlatform">+</NButton>
                </div>
                <div class="chip-list" v-if="editorPlatforms.length">
                  <NTag v-for="(p,i) in editorPlatforms" :key="i" type="success" closable size="small" @close="removePlatform(i)">{{ p }}</NTag>
                </div>
              </div>
            </div>

            <!-- Eval 用例 -->
            <div class="skill-editor-section-hd" style="margin-top:14px">
              Eval 用例
              <NButton size="tiny" style="margin-left:8px" @click="showAddEvalModal = true">+ 新增</NButton>
            </div>
            <div class="eval-case-list" v-if="editingDraft.eval_cases && editingDraft.eval_cases.length">
              <div
                v-for="ec in editingDraft.eval_cases"
                :key="ec.id"
                class="eval-case-item"
                :class="{ 'eval-confirmed': ec.status === 'confirmed', 'eval-draft': ec.status === 'draft' }"
              >
                <div class="eval-case-header">
                  <span class="eval-case-title">{{ ec.title }}</span>
                  <NTag size="tiny" :type="ec.status === 'confirmed' ? 'success' : 'warning'">
                    {{ ec.status === 'confirmed' ? '✓ 已确认' : 'AI草稿' }}
                  </NTag>
                </div>
                <div class="eval-case-row">
                  <span class="eval-field-label">输入</span>
                  <span class="eval-field-val">{{ ec.input }}</span>
                </div>
                <div class="eval-case-row">
                  <span class="eval-field-label">期望输出</span>
                  <span class="eval-field-val">{{ ec.expected_output }}</span>
                </div>
                <div class="eval-case-actions">
                  <NButton
                    v-if="ec.status !== 'confirmed'"
                    size="tiny"
                    type="success"
                    ghost
                    @click="handleConfirmEval(ec.id)"
                  >✓ 确认</NButton>
                  <NButton size="tiny" type="error" ghost @click="handleDeleteEval(ec.id)">删除</NButton>
                </div>
              </div>
            </div>
            <div v-else class="eval-empty">暂无 Eval 用例，点击「+ 新增」添加</div>

          </div><!-- /right -->
        </div><!-- /skill-editor-wrap -->

        <template #footer>
          <NSpace justify="end" size="small">
            <NButton @click="showSkillEditor = false">取消</NButton>
            <NButton
              type="primary"
              ghost
              :loading="savingDraft"
              @click="saveSkillDraft"
            >💾 保存草稿</NButton>
            <NButton
              type="success"
              :loading="savingDraft"
              @click="submitSkillForReview"
            >
              🚀 {{ editorQuality && !editorQuality.pass_gate ? '提交审核（质量偏低）' : '提交审核' }}
            </NButton>
          </NSpace>
        </template>
      </NDrawerContent>
    </NDrawer>

    <!-- ── 添加 Eval 用例弹窗 ──────────────────────────── -->
    <NModal
      v-model:show="showAddEvalModal"
      preset="dialog"
      title="📝 新增 Eval 用例"
      positive-text="提交"
      negative-text="取消"
      style="width: 620px"
      :loading="submittingEval"
      @positive-click="submitNewEvalCase"
    >
      <NForm label-placement="top" size="medium" style="margin-top: 8px">
        <NFormItem label="标题" required>
          <NInput v-model:value="newEvalCase.title" placeholder="简要描述这个测试场景" />
        </NFormItem>
        <NFormItem label="输入（Input）" required>
          <NInput
            v-model:value="newEvalCase.input"
            type="textarea"
            placeholder="用户输入或任务描述"
            :autosize="{ minRows: 3, maxRows: 6 }"
          />
        </NFormItem>
        <NFormItem label="期望输出（Expected Output）" required>
          <NInput
            v-model:value="newEvalCase.expected_output"
            type="textarea"
            placeholder="AI 应该给出的正确回答或行为"
            :autosize="{ minRows: 3, maxRows: 6 }"
          />
        </NFormItem>
        <NFormItem label="判断标准（Judgment Criteria）">
          <NInput
            v-model:value="newEvalCase.judgment_criteria"
            type="textarea"
            placeholder="如何判断回答是否达标（可选）"
            :autosize="{ minRows: 2, maxRows: 4 }"
          />
        </NFormItem>
      </NForm>
    </NModal>

    <!-- ── 相似 Skill 检测弹窗（三档分级 + 融合操作） ──────────────── -->
    <NModal
      v-model:show="showSimilarModal"
      preset="card"
      style="width: 720px; max-height: 85vh"
      :title="similarHasExact ? '⚠️ 发现高度重叠 Skill，建议融合' : '🔍 发现相似 Skill'"
      :segmented="{ content: true, footer: true }"
    >
      <div class="similar-modal-body">

        <!-- 精确重叠提示横幅 -->
        <div v-if="similarHasExact" class="similar-exact-banner">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          检测到 <strong>来源条目高度重叠</strong> 的 Skill，再次生成会产生冗余。
          建议直接点击"融合到此 Skill"将新知识合入已有 Skill。
        </div>
        <div v-else-if="similarHasPartial" class="similar-partial-banner">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
          检测到 <strong>部分重叠</strong> 的 Skill，建议先查看是否可以融合补充。
        </div>

        <!-- EXACT 档 -->
        <div v-if="similarResults.some(r => r.tier === 'exact')" class="similar-tier-section">
          <div class="similar-tier-header tier-exact">
            <span class="tier-dot" />
            高度重叠（来源条目 ≥70% 相同）
          </div>
          <div class="similar-items">
            <div
              v-for="item in similarResults.filter(r => r.tier === 'exact')"
              :key="item.id"
              class="similar-item similar-item-exact"
            >
              <div class="similar-item-top">
                <span class="similar-name">{{ item.display_name }}</span>
                <span class="similar-type-badge" :class="item.type === 'draft' ? 'badge-draft' : 'badge-active'">
                  {{ item.type === 'draft' ? '草稿' : '已激活' }}
                </span>
                <span class="similar-score score-exact">{{ Math.round(item.jaccard_score * 100) }}% 重叠</span>
              </div>
              <div class="similar-desc">{{ item.description }}</div>
              <div class="similar-item-footer">
                <div class="similar-tags">
                  <NTag size="tiny" :bordered="false" type="info">{{ item.module }}</NTag>
                  <NTag size="tiny" :bordered="false" type="success">{{ item.func_type }}</NTag>
                  <span v-for="(r, i) in item.reasons" :key="i" class="similar-reason">{{ r }}</span>
                </div>
                <NButton
                  v-if="item.type === 'draft'"
                  size="tiny"
                  type="warning"
                  :loading="mergingSkill && mergingTargetId === item.id"
                  :disabled="mergingSkill && mergingTargetId !== item.id"
                  @click="handleMergeIntoDraft(item)"
                >融合到此 Skill</NButton>
                <NButton
                  v-else
                  size="tiny"
                  type="warning"
                  ghost
                  :loading="mergingSkill && mergingTargetId === item.id"
                  :disabled="mergingSkill && mergingTargetId !== item.id"
                  @click="handleUpgradeActivated(item)"
                >生成升级草案</NButton>
              </div>
            </div>
          </div>
        </div>

        <!-- PARTIAL 档 -->
        <div v-if="similarResults.some(r => r.tier === 'partial')" class="similar-tier-section">
          <div class="similar-tier-header tier-partial">
            <span class="tier-dot" />
            部分重叠（来源条目 30–70% 相同）
          </div>
          <div class="similar-items">
            <div
              v-for="item in similarResults.filter(r => r.tier === 'partial')"
              :key="item.id"
              class="similar-item similar-item-partial"
            >
              <div class="similar-item-top">
                <span class="similar-name">{{ item.display_name }}</span>
                <span class="similar-type-badge" :class="item.type === 'draft' ? 'badge-draft' : 'badge-active'">
                  {{ item.type === 'draft' ? '草稿' : '已激活' }}
                </span>
                <span class="similar-score score-partial">{{ Math.round(item.jaccard_score * 100) }}% 重叠</span>
              </div>
              <div class="similar-desc">{{ item.description }}</div>
              <div class="similar-item-footer">
                <div class="similar-tags">
                  <NTag size="tiny" :bordered="false" type="info">{{ item.module }}</NTag>
                  <NTag size="tiny" :bordered="false" type="success">{{ item.func_type }}</NTag>
                  <span v-for="(r, i) in item.reasons" :key="i" class="similar-reason">{{ r }}</span>
                </div>
                <NButton
                  v-if="item.type === 'draft'"
                  size="tiny"
                  type="default"
                  :loading="mergingSkill && mergingTargetId === item.id"
                  :disabled="mergingSkill && mergingTargetId !== item.id"
                  @click="handleMergeIntoDraft(item)"
                >融合补充</NButton>
                <NButton
                  v-else
                  size="tiny"
                  type="default"
                  ghost
                  :loading="mergingSkill && mergingTargetId === item.id"
                  :disabled="mergingSkill && mergingTargetId !== item.id"
                  @click="handleUpgradeActivated(item)"
                >生成升级草案</NButton>
              </div>
            </div>
          </div>
        </div>

        <!-- STRUCTURAL 档 -->
        <div v-if="similarResults.some(r => r.tier === 'structural')" class="similar-tier-section">
          <div class="similar-tier-header tier-structural">
            <span class="tier-dot" />
            同类别 / 内容相关（相同模块类型或主题相关）
          </div>
          <div class="similar-items">
            <div
              v-for="item in similarResults.filter(r => r.tier === 'structural')"
              :key="item.id"
              class="similar-item similar-item-structural"
            >
              <div class="similar-item-top">
                <span class="similar-name">{{ item.display_name }}</span>
                <span class="similar-type-badge" :class="item.type === 'draft' ? 'badge-draft' : 'badge-active'">
                  {{ item.type === 'draft' ? '草稿' : '已激活' }}
                </span>
              </div>
              <div class="similar-desc">{{ item.description }}</div>
              <div class="similar-item-footer">
                <div class="similar-tags">
                  <NTag size="tiny" :bordered="false" type="info">{{ item.module }}</NTag>
                  <NTag size="tiny" :bordered="false" type="success">{{ item.func_type }}</NTag>
                  <span v-for="(r, i) in item.reasons" :key="i" class="similar-reason">{{ r }}</span>
                </div>
                <NButton
                  v-if="item.type === 'draft'"
                  size="tiny"
                  type="default"
                  :loading="mergingSkill && mergingTargetId === item.id"
                  :disabled="mergingSkill && mergingTargetId !== item.id"
                  @click="handleMergeIntoDraft(item)"
                >融合补充</NButton>
                <NButton
                  v-else
                  size="tiny"
                  type="default"
                  ghost
                  :loading="mergingSkill && mergingTargetId === item.id"
                  :disabled="mergingSkill && mergingTargetId !== item.id"
                  @click="handleUpgradeActivated(item)"
                >生成升级草案</NButton>
              </div>
            </div>
          </div>
        </div>

        <p class="similar-note">
          如果以上 Skill 均不适合融合，可点击"仍要新建"创建独立 Skill，之后再手动合并。
        </p>
      </div>

      <template #footer>
        <div class="similar-modal-footer">
          <NButton size="small" @click="cancelAndViewSimilar">取消</NButton>
          <NButton
            size="small"
            type="primary"
            ghost
            :loading="generatingSkill"
            @click="confirmCreateAnyway"
          >仍要新建</NButton>
        </div>
      </template>
    </NModal>

    <!-- ── Skill 生成进度弹窗 ──────────────────────────────── -->
    <NModal
      v-model:show="showGenProgressModal"
      preset="card"
      style="width: 480px"
      title="✨ Skill 生成中..."
      :closable="!generatingSkill"
      :mask-closable="false"
    >
      <div class="gen-progress-body">
        <!-- 进度步骤列表 -->
        <div class="gen-steps">
          <div
            v-for="(step, i) in genProgressSteps"
            :key="i"
            class="gen-step"
            :class="[
              step.status === 'finish' ? 'step-finish' : '',
              step.status === 'process' ? 'step-process' : '',
              step.status === 'error' ? 'step-error' : '',
              step.status === 'wait' ? 'step-wait' : '',
            ]"
          >
            <div class="step-icon">
              <span v-if="step.status === 'finish'">&#10003;</span>
              <span v-else-if="step.status === 'error'">&#10007;</span>
              <span v-else-if="step.status === 'process'" class="step-spinner">&#9679;</span>
              <span v-else>{{ i + 1 }}</span>
            </div>
            <div class="step-label">{{ step.label }}</div>
          </div>
        </div>

        <!-- 当前状态消息 -->
        <div v-if="genJobStatus" class="gen-status-msg" :class="genJobStatus.status === 'error' ? 'msg-error' : 'msg-info'">
          {{ genJobStatus.message }}
        </div>
        <div v-else class="gen-status-msg msg-info">正在初始化生成任务...</div>

        <!-- 进度条 -->
        <div class="gen-progress-bar-wrap">
          <div
            class="gen-progress-bar"
            :style="{ width: (genJobStatus?.progress ?? 0) + '%' }"
            :class="genJobStatus?.status === 'error' ? 'bar-error' : 'bar-normal'"
          />
        </div>
        <div class="gen-progress-pct">{{ genJobStatus?.progress ?? 0 }}%</div>
      </div>

      <template #footer>
        <div style="display:flex; justify-content:flex-end; gap:8px">
          <NButton
            size="small"
            :disabled="generatingSkill"
            @click="showGenProgressModal = false; closeGenSse()"
          >
            {{ generatingSkill ? '生成中...' : '关闭' }}
          </NButton>
        </div>
      </template>
    </NModal>

    <!-- ── 文档重复检测弹窗 ───────────────────────────── -->
    <NModal
      v-model:show="showDuplicateModal"
      preset="card"
      style="width: 640px; max-height: 80vh"
      title="⚠️ 检测到重复或相似的 Skill"
      :segmented="{ content: true, footer: true }"
    >
      <div class="dup-modal-body">
        <div class="dup-banner">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          当前涉及的知识条目源文档与以下 Skill 高度重叠，再次生成会产生冗余。
        </div>
        <div class="dup-items">
          <div
            v-for="item in duplicateItems"
            :key="item.id"
            class="dup-item"
          >
            <div class="dup-item-top">
              <span class="dup-name">{{ item.skill_name }}</span>
              <span class="dup-badge" :class="item.is_activated ? 'badge-active' : 'badge-draft'">
                {{ item.is_activated ? '已激活' : '草稿' }}
              </span>
              <span class="dup-match-type">
                {{ item.match_type === 'source_document' ? '来源文档重复' : '内容指纹重复' }}
              </span>
            </div>
            <div class="dup-item-actions">
              <NButton size="tiny" type="default" @click="handleViewExisting(item)">
                {{ item.is_activated ? '查看技能库' : '打开编辑' }}
              </NButton>
              <NButton
                v-if="item.is_activated"
                size="tiny"
                type="warning"
                ghost
                @click="handleUpgradeDraft(item)"
              >创建升级草案</NButton>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <div style="display:flex; justify-content:flex-end; gap:8px">
          <NButton size="small" @click="showDuplicateModal = false">取消</NButton>
          <NButton size="small" type="primary" ghost @click="handleForceCreate">忽略重复，强制新建</NButton>
        </div>
      </template>
    </NModal>

    <!-- ── 融合目标推荐弹窗 ─────────────────────────── -->
    <NModal
      v-model:show="showMergeRecommendModal"
      preset="card"
      style="width: 680px; max-height: 80vh"
      title="🔗 融合目标推荐"
      :segmented="{ content: true, footer: true }"
    >
      <NSpin :show="mergeRecommendLoading">
        <div class="merge-rec-body">
          <div v-if="!mergeRecommendLoading && mergeRecommendations.length === 0" class="merge-empty">
            <NEmpty description="暂无合适的融合目标，建议直接新建 Skill" />
          </div>
          <div
            v-for="rec in mergeRecommendations"
            :key="rec.target_id"
            class="merge-rec-item"
          >
            <div class="merge-rec-top">
              <span class="merge-rec-name">{{ rec.target_name }}</span>
              <span class="dup-badge" :class="rec.target_type === 'activated' ? 'badge-active' : 'badge-draft'">
                {{ rec.target_type === 'activated' ? '已激活' : '草稿' }}
              </span>
              <span class="merge-score">{{ Math.round(rec.match_score * 100) }}% 相关</span>
            </div>
            <div class="merge-rec-reason">{{ rec.reason }}</div>
            <div v-if="rec.new_topics.length > 0" class="merge-rec-topics">
              <span class="topics-label">新增主题：</span>
              <NTag v-for="t in rec.new_topics" :key="t" size="tiny" :bordered="false" type="info">{{ t }}</NTag>
            </div>
            <div class="merge-rec-delta" v-if="rec.estimated_quality_delta > 0">
              质量预计提升 +{{ rec.estimated_quality_delta }}
            </div>
          </div>
        </div>
      </NSpin>
      <template #footer>
        <div style="display:flex; justify-content:flex-end">
          <NButton size="small" @click="showMergeRecommendModal = false">关闭</NButton>
        </div>
      </template>
    </NModal>

    <!-- 删除草稿确认弹窗 -->
    <NModal v-model:show="showDeleteConfirmModal" preset="dialog" type="warning" title="删除草稿"
      positive-text="确认删除" negative-text="取消" @positive-click="doDeleteDraft">
      <p v-if="deletingDraft">确定删除草稿 <strong>{{ deletingDraft.skill_name }}</strong>？</p>
      <p style="color:#d32f2f;font-size:13px">⚠ 此操作不可恢复，草稿 JSON 文件将被永久删除。</p>
    </NModal>

    <!-- 废弃 Skill 弹窗 -->
    <NModal v-model:show="showDeprecateModal" preset="card" title="废弃 Skill" style="max-width:480px">
      <p v-if="deprecatingDraft">将废弃已激活的 Skill <strong>{{ deprecatingDraft.skill_name }}</strong>，文件保留但标记为废弃。</p>
      <div style="margin-top:12px">
        <label style="display:block;font-weight:600;margin-bottom:4px">废弃原因 *</label>
        <NInput v-model:value="deprecateReason" type="textarea" :rows="3" placeholder="请填写废弃原因（必填）" />
      </div>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showDeprecateModal = false">取消</NButton>
          <NButton type="warning" :disabled="!deprecateReason.trim()" @click="doDeprecate">确认废弃</NButton>
        </NSpace>
      </template>
    </NModal>

    <!-- 下线 Skill 弹窗 -->
    <NModal v-model:show="showDeactivateModal" preset="card" title="下线 Skill" style="max-width:480px">
      <p v-if="deactivatingDraft">将下线 Skill <strong>{{ deactivatingDraft.skill_name }}</strong>，磁盘文件将移到 .archive 目录。</p>
      <p style="color:#d32f2f;font-size:13px">⚠ 下线后 AI Agent 将无法使用此 Skill。</p>
      <div style="margin-top:12px">
        <label style="display:block;font-weight:600;margin-bottom:4px">下线原因 *</label>
        <NInput v-model:value="deactivateReason" type="textarea" :rows="3" placeholder="请填写下线原因（必填）" />
      </div>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showDeactivateModal = false">取消</NButton>
          <NButton type="error" :disabled="!deactivateReason.trim()" @click="doDeactivate">确认下线</NButton>
        </NSpace>
      </template>
    </NModal>

    <!-- 文档编辑弹窗 -->
    <NModal
      v-model:show="showEditDocModal"
      preset="dialog"
      title="✏️ 编辑文档"
      positive-text="保存"
      negative-text="取消"
      style="width: 480px"
      :loading="submittingDoc"
      @positive-click="submitEditDoc"
    >
      <NForm label-placement="left" label-width="60" size="medium" style="margin-top: 8px">
        <NFormItem label="标题" required>
          <NInput v-model:value="editDocTitle" placeholder="文档标题" />
        </NFormItem>
        <NFormItem label="模块">
          <NSelect v-model:value="editDocModule" :options="MODULE_OPTIONS" placeholder="选择模块" />
        </NFormItem>
      </NForm>
    </NModal>

    <!-- 批量拒绝弹窗 -->
    <NModal v-model:show="showBulkRejectModal" preset="card" title="批量拒绝草稿" style="max-width:480px">
      <p>将拒绝已选的草稿，可填写拒绝原因。</p>
      <div style="margin-top:12px">
        <label style="display:block;font-weight:600;margin-bottom:4px">拒绝原因</label>
        <NInput v-model:value="bulkRejectReason" type="textarea" :rows="3" placeholder="填写拒绝原因（可选）" />
      </div>
      <template #footer>
        <NSpace justify="end">
          <NButton @click="showBulkRejectModal = false">取消</NButton>
          <NButton type="warning" :loading="bulkDraftLoading" @click="confirmBulkReject">确认拒绝</NButton>
        </NSpace>
      </template>
    </NModal>

  </div>
</template>

<style scoped>
/* ── Layout ──────────────────────────────────────────── */
.kb-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-bottom: 24px;
}

/* ── Tabs ────────────────────────────────────────────── */
.kb-tabs { padding: 4px 22px 22px; }

/* ── Dashboard quick links ─────────────────────────────── */
.dash-quick-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.dash-quick-card {
  text-align: left;
  border: 1px solid var(--line);
  background: var(--bg);
  border-radius: 14px;
  padding: 16px;
  cursor: pointer;
  font-family: inherit;
  color: var(--text);
  transition: all 0.18s;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.dash-quick-card:hover {
  border-color: var(--accent);
  background: var(--accent-soft);
}
.dash-quick-icon { font-size: 22px; }
.dash-quick-label { font-size: 14px; font-weight: 700; }
.dash-quick-desc { font-size: 12px; color: var(--muted); }

@media (max-width: 900px) {
  .dash-quick-grid { grid-template-columns: 1fr 1fr; }
}

/* ── Toolbar ─────────────────────────────────────────── */
.tab-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0 10px;
}
.toolbar-count { font-size: 12px; color: #999; }
.tab-empty { padding: 48px 0; }

/* ── Table ───────────────────────────────────────────── */
.kb-table :deep(.n-data-table-tr:hover .n-data-table-td) {
  background: rgba(32,128,240,.04) !important;
}
.cell-content { line-height: 1.5; }
.cell-main { font-size: 13px; color: var(--n-text-color); }
.cell-sub { font-size: 11px; color: #aaa; margin-top: 2px; }
.cell-code { font-size: 11px; color: #888; font-family: monospace; }

.badge {
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 20px;
  white-space: nowrap;
}
.badge-cat { background: rgba(240,160,32,.12); color: #c47a00; }
.badge-func { background: rgba(114,46,209,.10); color: #722ed1; }
.badge-domain { background: rgba(32,128,240,.10); color: #1677d2; }
.badge-xs { font-size: 10px; padding: 1px 5px; }
.entry-count { font-size: 12px; color: #888; font-family: monospace; }

/* ── Dashboard ───────────────────────────────────────── */
.stat-row {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
  padding: 12px 0;
}
.stat-card {
  padding: 16px 20px;
  background: var(--n-color-modal, #fafafa);
  border-radius: 10px;
  border: 1px solid rgba(0,0,0,.06);
  transition: box-shadow .2s;
}
.stat-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,.08); }
.stat-label { font-size: 12px; color: #888; font-weight: 500; margin-bottom: 6px; }
.stat-val { font-size: 32px; font-weight: 700; line-height: 1.1; color: var(--n-text-color); }
.stat-val .stat-unit { font-size: 16px; font-weight: 400; margin-left: 2px; }
.val-ok { color: #18a058; }
.val-warn { color: #f0a020; }
.stat-meta { font-size: 11px; color: #aaa; margin-top: 6px; display: flex; gap: 10px; }
.dot { display: inline-flex; align-items: center; gap: 4px; }
.dot::before { content: ''; width: 5px; height: 5px; border-radius: 50%; flex-shrink: 0; }
.dot-ok::before { background: #18a058; }
.dot-warn::before { background: #f0a020; }

.dist-section { padding: 12px 0 4px; }
.dist-title { font-size: 12px; font-weight: 600; color: #888; text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 10px; }
.dist-row { display: flex; flex-direction: column; gap: 8px; }
.dist-bar-item { display: flex; align-items: center; gap: 10px; }
.dist-bar-label { display: flex; align-items: center; gap: 5px; width: 60px; font-size: 12px; color: #666; }
.dist-mod-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dist-bar-track { flex: 1; height: 6px; background: rgba(0,0,0,.06); border-radius: 3px; overflow: hidden; }
.dist-bar-fill { height: 100%; border-radius: 3px; transition: width .4s ease; }
.dist-bar-count { font-size: 12px; color: #888; width: 24px; text-align: right; font-family: monospace; }
.dist-empty { font-size: 12px; color: #bbb; }

/* ── 治理面板 ─────────────────────────────────────── */
.gov-section-title {
  font-size: 13px; font-weight: 700; color: #555; margin: 6px 0 12px;
  display: flex; align-items: baseline; gap: 8px;
}
.gov-section-sub { font-size: 11px; font-weight: 400; color: #aaa; }
.gov-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
}
.gov-card {
  text-align: left; cursor: pointer;
  padding: 14px 16px; border-radius: 10px;
  border: 1px solid rgba(0,0,0,.08);
  background: rgba(0,0,0,.015);
  transition: transform .15s ease, box-shadow .15s ease, border-color .15s ease;
}
.gov-card:hover { transform: translateY(-2px); box-shadow: 0 4px 14px rgba(0,0,0,.08); border-color: rgba(32,128,240,.35); }
.gov-card.alert { border-color: rgba(32,128,240,.4); background: rgba(32,128,240,.05); }
.gov-card.warn { border-color: rgba(240,160,32,.4); background: rgba(240,160,32,.06); }
.gov-num { font-size: 26px; font-weight: 700; color: var(--n-text-color, #333); line-height: 1.1; }
.gov-label { font-size: 12px; color: #777; margin-top: 4px; }
.gov-hint { font-size: 11px; color: #2080f0; margin-top: 8px; opacity: 0; transition: opacity .15s; }
.gov-card:hover .gov-hint { opacity: 1; }

.gov-blind-list { display: flex; flex-direction: column; gap: 8px; }
.gov-blind-item {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 10px 12px; border-radius: 8px;
  background: rgba(240,160,32,.06); border: 1px solid rgba(240,160,32,.18);
}
.gov-blind-info { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.gov-blind-count { font-size: 12px; color: #999; }

.gov-top-list { display: flex; flex-direction: column; gap: 6px; }
.gov-top-item {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 10px; border-radius: 6px; background: rgba(0,0,0,.02);
}
.gov-top-rank { font-size: 11px; font-weight: 700; color: #2080f0; width: 26px; }
.gov-top-text { flex: 1; min-width: 0; font-size: 12px; color: var(--n-text-color); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.gov-top-count { font-size: 12px; color: #888; font-family: monospace; }

.dist-chips { display: flex; flex-wrap: wrap; gap: 8px; padding: 4px 0 12px; }
.ft-chip {
  display: flex; align-items: center; gap: 6px;
  padding: 4px 12px; border-radius: 20px;
  background: rgba(114,46,209,.08); border: 1px solid rgba(114,46,209,.15);
}
.ft-name { font-size: 12px; color: #722ed1; font-weight: 500; }
.ft-cnt { font-size: 13px; font-weight: 700; color: #722ed1; }

/* ── Search ──────────────────────────────────────────── */
.search-bar {
  display: flex;
  gap: 10px;
  padding: 12px 0 14px;
  align-items: center;
}
.search-input { flex: 1; }
.search-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60px 0;
  gap: 10px;
  color: #bbb;
  font-size: 13px;
}
.search-results { display: flex; flex-direction: column; gap: 10px; }
.search-meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 4px 0 8px;
}
.search-meta { font-size: 12px; color: #888; }
.search-collapse-all {
  border: none;
  background: none;
  font-size: 12px;
  color: #2080f0;
  cursor: pointer;
  padding: 2px 4px;
  font-family: inherit;
}
.search-collapse-all:hover { text-decoration: underline; }

.result-card {
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px solid rgba(0,0,0,.07);
  background: var(--n-color-modal, #fafafa);
  transition: border-color .15s, box-shadow .15s;
}
.result-card.expanded {
  border-color: rgba(32,128,240,.25);
  box-shadow: 0 2px 12px rgba(32,128,240,.06);
}
.result-card:hover {
  border-color: rgba(32,128,240,.3);
  box-shadow: 0 2px 12px rgba(32,128,240,.08);
}
.result-head {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}
.result-category { font-size: 11px; color: #aaa; }
.result-relevance { margin-left: auto; display: flex; align-items: center; gap: 6px; }
.relevance-bar {
  width: 60px; height: 4px;
  background: rgba(0,0,0,.08); border-radius: 2px; overflow: hidden;
}
.relevance-fill { height: 100%; background: linear-gradient(90deg, #2080f0, #0ea5e9); border-radius: 2px; }
.relevance-pct { font-size: 11px; color: #2080f0; font-weight: 600; white-space: nowrap; }
.result-snippet-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--n-text-color);
  margin-bottom: 6px;
  line-height: 1.45;
}
.result-snippet {
  font-size: 13px;
  color: var(--n-text-color-2, #666);
  line-height: 1.65;
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.result-full { margin-top: 4px; }
.result-body { font-size: 13px; color: var(--n-text-color); line-height: 1.6; }
.result-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid rgba(0,0,0,.05);
}
.result-foot { font-size: 11px; color: #aaa; display: flex; align-items: center; gap: 4px; flex: 1; min-width: 0; }
.result-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: none;
  background: none;
  font-size: 12px;
  font-weight: 600;
  color: #2080f0;
  cursor: pointer;
  padding: 2px 4px;
  flex-shrink: 0;
  font-family: inherit;
}
.result-toggle:hover { text-decoration: underline; }
.result-toggle svg { transition: transform .15s; }

/* ── Review Drawer ───────────────────────────────────── */
.review-body { display: flex; flex-direction: column; gap: 16px; padding: 4px 0; }
.review-info-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.review-info-item { display: flex; flex-direction: column; gap: 3px; }
.review-info-label { font-size: 11px; font-weight: 600; color: #aaa; text-transform: uppercase; letter-spacing: 0.5px; }
.review-code {
  font-family: monospace; font-size: 12px;
  background: rgba(0,0,0,.05); padding: 4px 8px;
  border-radius: 4px; color: #555;
}
.review-content-wrap { }
.review-content {
  margin: 0;
  background: rgba(0,0,0,.03);
  border: 1px solid rgba(0,0,0,.06);
  border-radius: 8px;
  padding: 12px;
  font-size: 12px;
  line-height: 1.7;
  overflow: auto;
  max-height: 280px;
  white-space: pre-wrap;
}
.review-actions { display: flex; flex-direction: column; gap: 0; padding-top: 4px; }
.review-action-label { font-size: 11px; font-weight: 600; color: #aaa; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }
.review-btn-group { display: flex; gap: 8px; }
.review-btn {
  flex: 1; padding: 8px 16px;
  border-radius: 8px; border: 2px solid transparent;
  font-size: 13px; font-weight: 600; cursor: pointer;
  transition: all .15s;
  background: rgba(0,0,0,.04); color: #666;
}
.review-btn.approve.active, .review-btn.approve:hover { background: rgba(24,160,88,.12); color: #18a058; border-color: #18a058; }
.review-btn.reject.active, .review-btn.reject:hover { background: rgba(208,48,80,.10); color: #d03050; border-color: #d03050; }

/* ── Document Import Tab ─────────────────────────────── */
.import-root { display: flex; flex-direction: column; gap: 20px; padding: 16px 0; }

.drop-zone {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 48px 32px;
  border: 2px dashed rgba(32,128,240,.35);
  border-radius: 16px;
  background: rgba(32,128,240,.02);
  cursor: pointer;
  transition: all .2s;
  user-select: none;
}
.drop-zone:hover, .drop-zone.dragging {
  border-color: #2080f0;
  background: rgba(32,128,240,.06);
  box-shadow: 0 4px 24px rgba(32,128,240,.12);
}
.drop-icon-wrap {
  width: 72px; height: 72px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(32,128,240,.12) 0%, rgba(14,165,233,.08) 100%);
  display: flex; align-items: center; justify-content: center;
  color: #2080f0;
  margin-bottom: 4px;
}
.drop-title { font-size: 15px; font-weight: 600; color: var(--n-text-color); margin: 0; }
.drop-link { color: #2080f0; text-decoration: underline; }
.drop-sub { font-size: 12px; color: #888; margin: 0; }
.drop-types { display: flex; gap: 8px; }
.type-badge {
  padding: 3px 10px; border-radius: 20px;
  font-size: 11px; font-weight: 700; letter-spacing: 0.5px;
}
.type-badge.pdf  { background: rgba(208,48,80,.1);  color: #d03050; }
.type-badge.docx { background: rgba(32,128,240,.1); color: #2080f0; }
.type-badge.txt  { background: rgba(24,160,88,.1);  color: #18a058; }
.type-badge.md   { background: rgba(114,46,209,.1); color: #722ed1; }
.drop-limit { font-size: 11px; color: #bbb; margin: 0; }

.import-tips { background: var(--n-color-modal, #fafafa); border-radius: 12px; padding: 16px 20px; border: 1px solid rgba(0,0,0,.06); }
.tip-title { font-size: 12px; font-weight: 600; color: #888; text-transform: uppercase; letter-spacing: 0.6px; margin-bottom: 12px; }
.tip-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.tip-item { display: flex; align-items: flex-start; gap: 10px; }
.tip-icon { font-size: 20px; flex-shrink: 0; }
.tip-name { font-size: 13px; font-weight: 600; color: var(--n-text-color); margin-bottom: 2px; }
.tip-desc { font-size: 12px; color: #888; line-height: 1.5; }

/* Processing */
.import-progress-root { display: flex; align-items: center; justify-content: center; padding: 48px 0; }
.progress-card {
  display: flex; flex-direction: column; align-items: center; gap: 16px;
  width: 480px; padding: 32px; border-radius: 16px;
  border: 1px solid rgba(0,0,0,.06);
  background: var(--n-color-modal, #fafafa);
}
.progress-filename {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; font-weight: 600; color: var(--n-text-color);
}
.stage-track {
  display: flex; align-items: center; gap: 0;
  width: 100%;
  justify-content: space-between;
  padding: 4px 0;
}
.stage-dot-wrap {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  flex: 1; position: relative;
}
.stage-dot-wrap::before {
  content: '';
  position: absolute; top: 8px; left: calc(50% + 8px);
  width: calc(100% - 16px); height: 2px;
  background: rgba(0,0,0,.1);
}
.stage-dot-wrap:last-child::before { display: none; }
.stage-dot {
  width: 16px; height: 16px; border-radius: 50%;
  background: rgba(0,0,0,.1); border: 2px solid transparent;
  transition: all .3s; z-index: 1;
}
.stage-dot-wrap.active .stage-dot {
  background: #2080f0; border-color: #2080f0;
  box-shadow: 0 0 0 4px rgba(32,128,240,.2);
}
.stage-dot-wrap.done .stage-dot { background: #18a058; border-color: #18a058; }
.stage-label { font-size: 11px; color: #888; }
.stage-dot-wrap.active .stage-label { color: #2080f0; font-weight: 600; }
.stage-dot-wrap.done .stage-label { color: #18a058; }

.progress-bar-wrap { display: flex; align-items: center; gap: 8px; width: 100%; }
.progress-bar-track { flex: 1; height: 6px; background: rgba(0,0,0,.08); border-radius: 3px; overflow: hidden; }
.progress-bar-fill {
  height: 100%; border-radius: 3px;
  background: linear-gradient(90deg, #2080f0, #0ea5e9);
  transition: width .4s ease;
}
.progress-pct { font-size: 12px; color: #2080f0; font-weight: 600; width: 32px; text-align: right; }
.progress-msg { font-size: 12px; color: #888; margin: 0; }

/* Error */
.import-error-root { display: flex; align-items: center; justify-content: center; padding: 48px 0; }
.error-card {
  display: flex; flex-direction: column; align-items: center; gap: 12px;
  padding: 32px; border-radius: 16px;
  border: 1px solid rgba(208,48,80,.2);
  background: rgba(208,48,80,.04);
  width: 400px;
}
.error-title { font-size: 16px; font-weight: 700; color: #d03050; margin: 0; }
.error-desc { font-size: 13px; color: #666; margin: 0; text-align: center; line-height: 1.6; }
.error-actions { display: flex; gap: 8px; margin-top: 8px; }

/* Done preview */
.import-done-root { display: flex; flex-direction: column; gap: 12px; padding: 12px 0; }
.preview-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 14px;
  background: rgba(24,160,88,.06);
  border: 1px solid rgba(24,160,88,.2);
  border-radius: 10px;
}
.preview-header-left { display: flex; align-items: center; gap: 8px; }
.preview-count { font-size: 12px; color: #888; }

.preview-list { display: flex; flex-direction: column; gap: 8px; max-height: 580px; overflow-y: auto; padding-right: 2px; }
.preview-card {
  display: flex; gap: 12px;
  padding: 12px 14px; border-radius: 10px;
  border: 2px solid rgba(0,0,0,.07);
  background: var(--n-color-modal, #fafafa);
  cursor: pointer; transition: all .15s;
}
.preview-card:hover { border-color: rgba(32,128,240,.3); }
.preview-card.selected { border-color: #2080f0; background: rgba(32,128,240,.04); }

.preview-select { padding-top: 2px; flex-shrink: 0; }
.select-box {
  width: 18px; height: 18px; border-radius: 4px;
  border: 2px solid rgba(0,0,0,.15);
  display: flex; align-items: center; justify-content: center;
  transition: all .15s;
}
.select-box.checked { background: #2080f0; border-color: #2080f0; }

.preview-body { flex: 1; min-width: 0; }
.preview-tags { display: flex; align-items: center; gap: 5px; flex-wrap: wrap; margin-bottom: 6px; }
.preview-content { font-size: 12px; color: var(--n-text-color); line-height: 1.6; margin: 0 0 6px; }
.preview-kws { font-size: 11px; color: #aaa; display: flex; align-items: center; gap: 4px; }

.conf-bar-mini { width: 40px; height: 3px; background: rgba(0,0,0,.08); border-radius: 2px; overflow: hidden; }
.conf-fill { height: 100%; border-radius: 2px; transition: width .3s; }
.conf-pct { font-size: 10px; font-weight: 600; }

/* ── Document Library (Phase 3) ─────────────────────── */
.doc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 14px;
  padding: 12px 0;
}

.doc-card {
  border: 1px solid rgba(0,0,0,.08);
  border-radius: 12px;
  padding: 14px 16px;
  background: #fff;
  cursor: pointer;
  transition: box-shadow .2s, border-color .2s;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.doc-card:hover {
  box-shadow: 0 4px 18px rgba(32,128,240,.12);
  border-color: rgba(32,128,240,.3);
}

.doc-card-header {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.doc-icon {
  width: 36px; height: 36px;
  border-radius: 8px;
  background: rgba(32,128,240,.1);
  color: #2080f0;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.doc-meta { flex: 1; min-width: 0; }
.doc-title {
  font-size: 14px; font-weight: 600;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  color: var(--n-text-color);
}
.doc-filename { font-size: 11px; color: #aaa; margin-top: 2px; }

.doc-stats {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.doc-stat-item { font-size: 12px; color: #666; }
.doc-stat-date { font-size: 11px; color: #bbb; margin-left: auto; }

/* Document Reader */
.doc-reader { display: flex; flex-direction: column; gap: 12px; }
.doc-reader-meta { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.doc-reader-stat { font-size: 12px; color: #888; }
.doc-reader-section-title {
  font-size: 13px; font-weight: 600; color: #555; margin-top: 8px;
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
}

.draft-lineage { display: flex; gap: 12px; margin-top: 4px; }
.draft-lineage-item { font-size: 11px; color: #999; }

.doc-markdown {
  background: rgba(0,0,0,.02);
  border-radius: 8px;
  padding: 14px 18px;
  border: 1px solid rgba(0,0,0,.06);
  max-height: 60vh;
  overflow-y: auto;
}

.doc-fulltext {
  white-space: pre-wrap;
  font-family: 'Courier New', Courier, monospace;
  font-size: 12px;
  line-height: 1.7;
  background: rgba(0,0,0,.03);
  border-radius: 8px;
  padding: 14px 16px;
  border: 1px solid rgba(0,0,0,.06);
  max-height: 55vh;
  overflow-y: auto;
  color: var(--n-text-color);
}

.doc-chunks-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 10px;
}
.doc-chunk-item {
  display: flex;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(32,128,240,.04);
  border: 1px solid rgba(32,128,240,.1);
}
.doc-chunk-index {
  font-size: 11px; font-weight: 700; color: #2080f0;
  min-width: 24px;
  padding-top: 2px;
}
.doc-chunk-body { flex: 1; min-width: 0; }
.doc-chunk-content {
  font-size: 12px; line-height: 1.6; color: var(--n-text-color);
  margin-bottom: 6px;
  display: -webkit-box; -webkit-line-clamp: 4; -webkit-box-orient: vertical;
  overflow: hidden;
}
.doc-chunk-tags { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.kw-tag {
  font-size: 10px; padding: 1px 6px;
  border-radius: 10px;
  background: rgba(0,0,0,.06);
  color: #888;
}

/* ── Import Mode Switcher ─────────────────────────────── */
.import-mode-row {
  display: flex;
  gap: 8px;
  border-bottom: 1px solid rgba(0,0,0,.08);
  padding-bottom: 0;
  margin-bottom: 4px;
}
.import-mode-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  border: none;
  background: none;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: #888;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  border-radius: 0;
  transition: color .15s, border-color .15s;
}
.import-mode-btn:hover { color: #2080f0; }
.import-mode-btn.active {
  color: #2080f0;
  border-bottom-color: #2080f0;
  font-weight: 600;
}

/* ── Import Panel (folder / url) ─────────────────────── */
.import-panel {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  padding: 40px 32px 32px;
  border: 1px solid rgba(0,0,0,.07);
  border-radius: 16px;
  background: rgba(0,0,0,.01);
}
.import-panel-icon {
  width: 68px; height: 68px;
  border-radius: 50%;
  background: linear-gradient(135deg, rgba(32,128,240,.1) 0%, rgba(14,165,233,.06) 100%);
  display: flex; align-items: center; justify-content: center;
  color: #2080f0;
  margin-bottom: 4px;
}
.import-panel-title { font-size: 16px; font-weight: 700; color: var(--n-text-color); margin: 0; }
.import-panel-sub { font-size: 13px; color: #888; text-align: center; max-width: 480px; margin: 0; line-height: 1.6; }

.import-panel-form {
  display: flex;
  gap: 10px;
  width: 100%;
  max-width: 580px;
}
.import-panel-opts {
  display: flex;
  align-items: center;
  gap: 12px;
}
.folder-opt-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #555;
  cursor: pointer;
  user-select: none;
}
.folder-opt-check {
  width: 15px; height: 15px; cursor: pointer;
  accent-color: #2080f0;
}
.import-panel-types {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: center;
}
.import-types-note { font-size: 11px; color: #bbb; margin-left: 4px; }

.import-panel-hints {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  max-width: 480px;
  width: 100%;
}
.url-hint-item {
  font-size: 12px;
  color: #888;
  padding: 8px 12px;
  background: rgba(0,0,0,.03);
  border-radius: 8px;
  border: 1px solid rgba(0,0,0,.05);
}

/* ── Phase 4 Skill 工坊 ──────────────────────────────── */
.skill-import-notice {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: linear-gradient(135deg, rgba(114,46,209,.08) 0%, rgba(32,128,240,.06) 100%);
  border: 1px solid rgba(114,46,209,.2);
  border-radius: 10px;
  margin-bottom: 4px;
}
.skill-import-notice-icon { font-size: 20px; flex-shrink: 0; }
.skill-import-notice-text { flex: 1; font-size: 13px; color: #555; line-height: 1.5; }
.skill-import-notice-text strong { color: #722ed1; }

.workshop-section { padding: 4px 0; }
.workshop-section-hd {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.workshop-section-title { font-size: 14px; font-weight: 600; color: var(--n-text-color); }

.suggestion-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}
.suggestion-card {
  padding: 16px;
  border-radius: 12px;
  border: 1.5px solid rgba(0,0,0,.07);
  background: var(--n-color-modal, #fafafa);
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: box-shadow .2s, border-color .2s;
}
.suggestion-card--recommended {
  border-color: rgba(114,46,209,.25);
  background: rgba(114,46,209,.03);
}
.suggestion-card--recommended:hover {
  box-shadow: 0 4px 20px rgba(114,46,209,.12);
  border-color: rgba(114,46,209,.4);
}
.suggestion-card--dim { opacity: 0.65; }

.suggestion-card-header { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.suggestion-mod-badge { display: flex; align-items: center; gap: 6px; }
.suggestion-name { font-size: 14px; font-weight: 600; color: var(--n-text-color); line-height: 1.4; }
.suggestion-stats { display: flex; gap: 10px; font-size: 12px; color: #888; }
.suggestion-doc-info { color: #18a058; font-weight: 500; }
.suggestion-reason { font-size: 12px; color: #666; line-height: 1.5; }
.suggestion-gen-btn { width: 100%; margin-top: 4px; }
.suggestion-need-more { font-size: 12px; color: #bbb; text-align: center; padding: 6px 0 2px; }

.draft-list { display: flex; flex-direction: column; gap: 8px; }
.draft-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-radius: 8px;
  border: 1px solid rgba(0,0,0,.07);
  background: var(--n-color-modal, #fafafa);
  transition: border-color .15s;
}
.draft-item:hover { border-color: rgba(32,128,240,.3); }
.draft-item-main { flex: 1; min-width: 0; }
.draft-item-name { font-size: 13px; font-weight: 600; color: var(--n-text-color); margin-bottom: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.draft-item-meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.quality-badge {
  font-size: 11px; font-weight: 700;
  padding: 1px 6px;
  border-radius: 10px;
  background: rgba(0,0,0,.05);
}

/* ── Skill 预览 Modal ───────────────────────────────── */
.skill-preview-spin {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: hidden;

  :deep(.n-spin-content) {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }
}
.skill-preview-wrap {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  height: min(62vh, calc(100vh - 260px));
  max-height: min(62vh, calc(100vh - 260px));
  overflow: hidden;
}
.skill-preview-meta {
  flex-shrink: 0;
  padding-bottom: 4px;
}
.skill-preview-meta-row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.skill-preview-meta-sub { margin-top: 8px; font-size: 12px; color: var(--n-text-color-3); }
.skill-preview-scroll {
  flex: 1 1 auto;
  min-height: 0;
  min-width: 0;
  margin-top: 12px;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
}
.skill-preview-body-inner {
  padding: 4px 12px 16px 4px;
  min-width: 0;
  max-width: 100%;
}
.skill-preview-body {
  font-size: 13px;
  line-height: 1.7;
  overflow-wrap: anywhere;
  word-break: break-word;
}
.skill-preview-body-inner :deep(.markdown-body) {
  min-width: 0;
  max-width: 100%;
  overflow-x: auto;
}
.skill-preview-body-inner :deep(table) {
  display: block;
  max-width: 100%;
  overflow-x: auto;
}
.skill-preview-body-inner :deep(pre),
.skill-preview-body-inner :deep(.hljs-code-block) {
  max-width: 100%;
  overflow-x: auto;
}
.skill-preview-body-inner :deep(.hljs-code-block code.hljs) {
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── Skill 编辑器 Drawer ─────────────────────────────── */
.skill-editor-wrap {
  display: flex;
  gap: 20px;
  height: 100%;
  min-height: 600px;
}
.skill-editor-left {
  flex: 3;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}
.skill-editor-right {
  flex: 2;
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 320px;
  max-width: 420px;
  overflow-y: auto;
}
.skill-editor-section-hd {
  font-size: 12px;
  font-weight: 700;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
  display: flex;
  align-items: center;
  gap: 6px;
}
.skill-editor-hint { font-size: 11px; font-weight: 400; color: #bbb; text-transform: none; letter-spacing: 0; }

/* Chip input */
.chip-input-row { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; }
.chip-list { display: flex; flex-wrap: wrap; gap: 5px; }
.chip-empty { font-size: 12px; color: #bbb; padding: 4px 0; }

/* Quality Panel */
.quality-panel {
  background: var(--n-color-modal, #fafafa);
  border: 1px solid rgba(0,0,0,.07);
  border-radius: 10px;
  padding: 14px 16px;
}
.quality-panel-hd { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.quality-panel-title { font-size: 13px; font-weight: 700; color: var(--n-text-color); }
.quality-gate-badge {
  font-size: 11px; font-weight: 700;
  padding: 2px 8px; border-radius: 20px;
}
.gate-pass { background: rgba(24,160,88,.12); color: #18a058; }
.gate-fail { background: rgba(208,48,80,.10); color: #d03050; }

.quality-score-ring-row { display: flex; align-items: flex-start; gap: 14px; }
.quality-score-ring { flex-shrink: 0; }
.quality-dims { flex: 1; display: flex; flex-direction: column; gap: 7px; }
.quality-dim-item { display: flex; align-items: center; gap: 6px; }
.quality-dim-name { font-size: 11px; color: #666; width: 100px; flex-shrink: 0; display: flex; align-items: center; gap: 4px; }
.quality-dim-bar-track { flex: 1; height: 4px; background: rgba(0,0,0,.08); border-radius: 2px; overflow: hidden; }
.quality-dim-bar-fill { height: 100%; border-radius: 2px; transition: width .4s; }
.quality-dim-val { font-size: 10px; color: #888; font-family: monospace; width: 30px; text-align: right; flex-shrink: 0; }
.quality-required { font-size: 9px; color: #d03050; font-weight: 700; background: rgba(208,48,80,.1); padding: 0 3px; border-radius: 3px; }
.quality-no-data { font-size: 12px; color: #bbb; text-align: center; padding: 12px 0; }

.quality-blocks { margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(0,0,0,.06); }
.quality-block-title { font-size: 11px; font-weight: 700; color: #d03050; margin-bottom: 6px; }
.quality-block-item { font-size: 12px; color: #666; padding: 4px 0; border-bottom: 1px solid rgba(0,0,0,.04); line-height: 1.5; }
.quality-block-item:last-child { border-bottom: none; }

/* Version constraints */
.version-constraint-form {
  background: var(--n-color-modal, #fafafa);
  border: 1px solid rgba(0,0,0,.06);
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.version-constraint-row { display: flex; flex-direction: column; gap: 6px; }
.version-constraint-label { font-size: 11px; font-weight: 600; color: #888; }

/* Eval cases */
.eval-case-list { display: flex; flex-direction: column; gap: 8px; }
.eval-case-item {
  padding: 10px 12px;
  border-radius: 8px;
  border: 1.5px solid rgba(0,0,0,.07);
  background: var(--n-color-modal, #fafafa);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.eval-case-item.eval-confirmed { border-color: rgba(24,160,88,.2); background: rgba(24,160,88,.03); }
.eval-case-item.eval-draft { border-color: rgba(240,160,32,.2); background: rgba(240,160,32,.02); }
.eval-case-header { display: flex; align-items: center; justify-content: space-between; }
.eval-case-title { font-size: 12px; font-weight: 600; color: var(--n-text-color); }
.eval-case-row { display: flex; gap: 6px; align-items: flex-start; }
.eval-field-label { font-size: 10px; font-weight: 700; color: #aaa; min-width: 52px; padding-top: 1px; flex-shrink: 0; }
.eval-field-val { font-size: 11px; color: #555; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.eval-case-actions { display: flex; gap: 6px; justify-content: flex-end; margin-top: 2px; }
.eval-empty { font-size: 12px; color: #bbb; padding: 10px 0; }

/* ── 待完善草稿样式 ───────────────────────────────────── */
.draft-item--needs-polish {
  border-color: rgba(240,160,32,.3);
  background: rgba(240,160,32,.03);
}
.draft-item--needs-polish:hover {
  border-color: rgba(240,160,32,.5);
  box-shadow: 0 2px 10px rgba(240,160,32,.1);
}
.draft-needs-polish-tag {
  font-size: 10px;
  font-weight: 700;
  color: #d07020;
  background: rgba(240,160,32,.12);
  padding: 1px 5px;
  border-radius: 4px;
}
.draft-polish-hint {
  font-size: 11px;
  color: #d07020;
  margin-top: 4px;
  line-height: 1.4;
}

/* ── 相似 Skill 弹窗（三档分级 + 融合操作） ─────────────────── */
.similar-modal-body {
  font-size: 13px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 60vh;
  overflow-y: auto;
  padding-right: 2px;
}

/* 提示横幅 */
.similar-exact-banner,
.similar-partial-banner {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 7px;
  font-size: 12.5px;
  line-height: 1.5;
}
.similar-exact-banner {
  background: rgba(247,129,102,0.12);
  border: 1px solid rgba(247,129,102,0.3);
  color: #c0440e;
  svg { color: #f78166; flex-shrink: 0; margin-top: 1px; }
}
.similar-partial-banner {
  background: rgba(227,179,65,0.12);
  border: 1px solid rgba(227,179,65,0.3);
  color: #9a7200;
  svg { color: #e3b341; flex-shrink: 0; margin-top: 1px; }
}

/* 分档区块 */
.similar-tier-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.similar-tier-header {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11.5px;
  font-weight: 700;
  padding: 3px 0;
  .tier-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
}
.tier-exact   { color: #c04020; .tier-dot { background: #f78166; } }
.tier-partial { color: #9a6400; .tier-dot { background: #e3b341; } }
.tier-structural { color: #1060b0; .tier-dot { background: #388bfd; } }

/* 条目卡片 */
.similar-items {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.similar-item {
  border-radius: 7px;
  padding: 10px 12px;
  border: 1px solid var(--n-border-color, #e0e0e6);
  background: var(--n-card-color, #fff);
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.similar-item-exact     { border-left: 3px solid #f78166; }
.similar-item-partial   { border-left: 3px solid #e3b341; }
.similar-item-structural { border-left: 3px solid #388bfd; }

.similar-item-top {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-wrap: wrap;
}
.similar-name {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--n-text-color, #333);
  font-family: 'Consolas', monospace;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.similar-type-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}
.badge-draft  { background: rgba(240,160,32,0.15); color: #c08020; }
.badge-active { background: rgba(24,160,88,0.15);  color: #18a058; }

.similar-score {
  font-size: 10.5px;
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 10px;
  flex-shrink: 0;
}
.score-exact   { background: rgba(247,129,102,0.15); color: #d04020; }
.score-partial { background: rgba(227,179,65,0.15);  color: #9a6400; }

.similar-desc {
  font-size: 11.5px;
  color: var(--n-text-color-3, #666);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.similar-item-footer {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 2px;
}
.similar-tags {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  flex: 1;
}
.similar-reason {
  font-size: 10px;
  color: var(--n-text-color-3, #888);
  background: var(--n-color-embedded, rgba(0,0,0,0.04));
  border-radius: 4px;
  padding: 1px 5px;
}
.similar-activated-hint,
.similar-structural-hint {
  font-size: 10.5px;
  color: var(--n-text-color-3, #aaa);
  flex-shrink: 0;
}

.similar-note {
  margin: 2px 0 4px;
  font-size: 11.5px;
  color: var(--n-text-color-3, #999);
}

/* 弹窗底部按鈕行 */
.similar-modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* ── Skill 生成进度弹窗 ──────────────────────────── */
.gen-progress-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 4px 0;
}
.gen-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.gen-step {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 7px;
  font-size: 13px;
  transition: background 0.2s;
}
.step-finish { background: rgba(24,160,88,0.08); color: #18a058; }
.step-process { background: rgba(32,128,240,0.1); color: #2080f0; }
.step-error   { background: rgba(208,48,80,0.08); color: #d03050; }
.step-wait    { background: var(--n-color-embedded, rgba(0,0,0,0.03)); color: var(--n-text-color-3, #aaa); }
.step-icon {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 700;
  flex-shrink: 0;
  border: 1.5px solid currentColor;
}
.step-spinner {
  animation: spin 1s linear infinite;
  display: inline-block;
}
@keyframes spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}
.step-label { font-size: 13px; font-weight: 500; }
.gen-status-msg {
  font-size: 12px;
  padding: 8px 12px;
  border-radius: 6px;
  line-height: 1.5;
}
.msg-info  { background: rgba(32,128,240,0.08); color: #1060b0; }
.msg-error { background: rgba(208,48,80,0.08); color: #c0203c; }
.gen-progress-bar-wrap {
  height: 6px;
  background: var(--n-border-color, #e8e8ed);
  border-radius: 3px;
  overflow: hidden;
}
.gen-progress-bar {
  height: 100%;
  border-radius: 3px;
  transition: width 0.4s ease;
}
.bar-normal { background: linear-gradient(90deg, #2080f0, #18a058); }
.bar-error  { background: #d03050; }
.gen-progress-pct {
  font-size: 11px;
  text-align: right;
  color: var(--n-text-color-3, #aaa);
  margin-top: -6px;
}

/* ── 重复检测弹窗 ────────────────────────────────── */
.dup-modal-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  font-size: 13px;
}
.dup-banner {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  background: rgba(247,129,102,0.1);
  border: 1px solid rgba(247,129,102,0.3);
  border-radius: 7px;
  color: #c0440e;
  font-size: 12.5px;
  line-height: 1.5;
  svg { color: #f78166; flex-shrink: 0; margin-top: 2px; }
}
.dup-items { display: flex; flex-direction: column; gap: 8px; }
.dup-item {
  padding: 10px 12px;
  border: 1px solid var(--n-border-color, #e0e0e6);
  border-radius: 7px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.dup-item-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.dup-name { font-size: 13px; font-weight: 600; font-family: 'Consolas', monospace; flex: 1; }
.dup-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}
.dup-match-type {
  font-size: 11px;
  color: var(--n-text-color-3, #888);
  background: var(--n-color-embedded, rgba(0,0,0,0.04));
  border-radius: 4px;
  padding: 1px 6px;
}
.dup-item-actions { display: flex; gap: 6px; flex-wrap: wrap; }

/* ── 融合推荐弹窗 ─────────────────────────────────── */
.merge-rec-body {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 80px;
  font-size: 13px;
}
.merge-rec-item {
  padding: 10px 12px;
  border: 1px solid var(--n-border-color, #e0e0e6);
  border-radius: 7px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.merge-rec-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.merge-rec-name { font-size: 13px; font-weight: 600; font-family: 'Consolas', monospace; flex: 1; }
.merge-score {
  font-size: 11px;
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 10px;
  background: rgba(24,160,88,0.12);
  color: #18a058;
  flex-shrink: 0;
}
.merge-rec-reason {
  font-size: 12px;
  color: var(--n-text-color-3, #666);
  line-height: 1.5;
}
.merge-rec-topics {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  .topics-label { font-size: 11px; color: var(--n-text-color-3, #888); }
}
.merge-rec-delta {
  font-size: 11px;
  color: #18a058;
  font-weight: 600;
}
.merge-empty { padding: 24px 0; }

/* ── Batch Action Bar ─────────────────────────────────── */
.batch-action-bar {
  position: sticky;
  bottom: 0;
  background: #fff;
  border-top: 1px solid #e8e8e8;
  padding: 8px 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  box-shadow: 0 -2px 8px rgba(0,0,0,0.06);
  z-index: 10;
  margin-top: 8px;
  border-radius: 0 0 8px 8px;
}
.batch-count {
  font-size: 13px;
  font-weight: 600;
  color: #2080f0;
  margin-right: 8px;
}
</style>

<style lang="scss">
/* Skill 预览 Modal：固定卡片高度，避免正文撑开整页 */
.skill-preview-modal.n-modal .n-card {
  max-height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
}
.skill-preview-modal.n-modal .n-card__content {
  flex: 1 1 auto;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
</style>
