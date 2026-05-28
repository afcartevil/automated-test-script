<script setup lang="ts">
import { ref, onMounted, h, reactive, computed } from 'vue'
import {
  NCard, NForm, NFormItem, NInput, NSelect, NInputNumber,
  NButton, NSpace, NTag, NSpin, NEmpty, NTabs, NTabPane,
  NDataTable, NModal, NStatistic, NTooltip,
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
  startImportJob,
  subscribeImportProgress,
  saveImportedEntries,
  startFetchUrl,
  startScanFolder,
  listDocuments,
  getDocument,
  deleteDocument,
  getDocumentChunks,
  type KnowledgeEntry,
  type SkillDraft,
  type KnowledgeStats,
  type SemanticSearchResult,
  type ExtractedEntry,
  type KnowledgeDocument,
} from '@/api/tahp/knowledge'
import { useTahpModulesStore } from '@/stores/tahp/modules'

const message = useMessage()
const dialog = useDialog()
const modulesStore = useTahpModulesStore()

const activeTab = ref('dashboard')

// ─── Stats ──────────────────────────────────────────────────────────────
const statsLoading = ref(false)
const stats = ref<KnowledgeStats | null>(null)

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
  { label: '驱动 (Kernel)', value: 'kernel-driver' },
  { label: '功耗温升 (Power)', value: 'power-mgmt' },
  { label: '共享 (Shared)', value: 'shared' },
]
const MODULE_SHORT: Record<string, string> = {
  telephony: '通信', 'kernel-driver': '驱动', 'power-mgmt': '功耗', shared: '共享',
}
const MODULE_COLOR: Record<string, string> = {
  telephony: '#2080f0', 'kernel-driver': '#18a058', 'power-mgmt': '#f0a020', shared: '#722ed1',
}

const FUNC_TYPE_OPTIONS = [
  { label: 'Bug 分析', value: 'bug_analysis' },
  { label: '代码适配', value: 'code_adaptation' },
  { label: '版本适配', value: 'version_adaptation' },
  { label: '运营商移植', value: 'carrier_porting' },
  { label: 'AI 自检', value: 'ai_self_check' },
]
const FUNC_TYPE_SHORT: Record<string, string> = {
  bug_analysis: 'Bug分析', code_adaptation: '代码适配',
  version_adaptation: '版本适配', carrier_porting: '运营商移植', ai_self_check: 'AI自检',
}

const STATUS_OPTIONS = [
  { label: '全部状态', value: '' },
  { label: '待审核', value: 'pending_review' },
  { label: '已批准', value: 'approved' },
  { label: '已拒绝', value: 'rejected' },
  { label: '已归档', value: 'archived' },
]
const STATUS_TYPE: Record<string, 'default' | 'success' | 'error' | 'warning' | 'info'> = {
  pending_review: 'warning', approved: 'success', rejected: 'error', archived: 'default',
}
const STATUS_LABEL: Record<string, string> = {
  pending_review: '待审核', approved: '已批准', rejected: '已拒绝', archived: '已归档',
}

const CATEGORY_OPTIONS = [
  { label: '错误模式', value: '错误模式' },
  { label: 'API 规范', value: 'API规范' },
  { label: '最佳实践', value: '最佳实践' },
  { label: '性能优化', value: '性能优化' },
  { label: '集成指南', value: '集成指南' },
  { label: '其他', value: '其他' },
]

// ─── Computed ─────────────────────────────────────────────────────────────
const pendingCount = computed(() => drafts.value.length)
const activeEntryCount = computed(() => entries.value.filter(e => e.status === 'approved').length)

// ─── Table columns ────────────────────────────────────────────────────────
const entryColumns: DataTableColumns<KnowledgeEntry> = [
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
    width: 110,
    align: 'center',
    render: (r) => h(NSpace, { size: 4 }, () => [
      h(NButton, { size: 'tiny', type: 'primary', ghost: true, onClick: () => editEntry(r) }, () => '编辑'),
      h(NButton, { size: 'tiny', type: 'error', ghost: true, onClick: () => confirmDeleteEntry(r) }, () => '归档'),
    ]),
  },
]

const draftColumns: DataTableColumns<SkillDraft> = [
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
    width: 80,
    align: 'center',
    render: (r) => {
      const map: Record<string, 'warning'|'success'|'error'|'default'> = {
        draft: 'warning', reviewing: 'info', approved: 'success', rejected: 'error',
      } as any
      const label: Record<string, string> = { draft: '草稿', reviewing: '审核中', approved: '已批准', rejected: '已拒绝' }
      return h(NTag, { size: 'small', type: map[r.status || 'draft'] }, () => label[r.status || 'draft'] || r.status)
    },
  },
  {
    title: '操作',
    key: 'actions',
    width: 130,
    align: 'center',
    render: (r) => h(NSpace, { size: 4 }, () => [
      h(NButton, {
        size: 'tiny', type: 'success', onClick: () => openReviewModal(r, 'approve'),
      }, () => '✓ 批准'),
      h(NButton, {
        size: 'tiny', type: 'error', ghost: true, onClick: () => openReviewModal(r, 'reject'),
      }, () => '✗ 拒绝'),
    ]),
  },
]

// ─── Lifecycle ────────────────────────────────────────────────────────────
onMounted(async () => {
  await modulesStore.refresh()
  await Promise.all([loadStats(), loadDocuments()])
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
    const res = await listSkillDrafts({ status: 'draft', limit: 50 })
    drafts.value = res.drafts || []
    draftsTotal.value = res.total || 0
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    draftsLoading.value = false
  }
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
    content: `将条目标记为"已归档"，可在筛选中恢复查看，但不会出现在正常列表中。`,
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

// ─── Semantic Search ──────────────────────────────────────────────────────
async function doSearch() {
  if (!searchQuery.value.trim()) { message.warning('请输入查询关键词'); return }
  searchLoading.value = true
  try {
    searchResults.value = await semanticSearch(searchQuery.value, searchModule.value || undefined)
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
    await reviewSkillDraft(reviewingDraft.value.id || '', reviewAction.value, 'admin', reviewNotes.value)
    message.success(`草稿已${reviewAction.value === 'approve' ? '批准并激活' : '拒绝'}`)
    showReviewDrawer.value = false
    await loadDrafts()
    await loadStats()
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    submittingReview.value = false
  }
}

function onTabChange(tab: string) {
  activeTab.value = tab
  if (tab === 'entries')   loadEntries()
  if (tab === 'drafts')    loadDrafts()
  if (tab === 'documents') loadDocuments()
}

// ─── Phase 2: Document Import ─────────────────────────────────────────────────

// Import mode: 'file' = drag-drop upload, 'folder' = local path scan, 'url' = web URL fetch
const importMode        = ref<'file' | 'folder' | 'url'>('file')

const isDragging        = ref(false)
const fileInputRef      = ref<HTMLInputElement | null>(null)
const importJobId       = ref('')
const importStatus      = ref<'idle' | 'processing' | 'done' | 'error'>('idle')
const importProgress    = ref(0)
const importStage       = ref<'upload' | 'parse' | 'extract' | 'done' | 'error'>('upload')
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
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    savingImport.value = false
  }
}
</script>

<template>
  <div class="kb-page">
    <!-- ── Header ─────────────────────────────────────────── -->
    <div class="kb-header">
      <div class="kb-header-left">
        <div class="kb-icon-wrap">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
            <path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/>
            <path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/>
          </svg>
        </div>
        <div>
          <h1 class="kb-title">知识库管理</h1>
          <p class="kb-sub">Phase 1 · 知识条目 · 语义搜索 · Skill 草稿审核</p>
        </div>
      </div>
      <NButton type="primary" class="kb-add-btn" @click="openAddEntryModal">
        <template #icon>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
        </template>
        新建条目
      </NButton>
    </div>

    <!-- ── Tabs ───────────────────────────────────────────── -->
    <NTabs :value="activeTab" @update:value="onTabChange" class="kb-tabs" animated>

      <!-- ── Dashboard ─────────────────────────────────── -->
      <NTabPane name="dashboard" tab="📊 仪表板">
        <NSpin :show="statsLoading">
          <div class="dash-empty" v-if="!stats && !statsLoading">
            <NEmpty description="暂无统计数据" />
          </div>
          <template v-else-if="stats">
            <!-- Row 1: core counters -->
            <div class="stat-row">
              <div class="stat-card">
                <div class="stat-label">知识条目</div>
                <div class="stat-val">{{ stats.total_entries }}</div>
                <div class="stat-meta">
                  <span class="dot dot-ok">{{ stats.approved_entries }} 已批准</span>
                  <span class="dot dot-warn">{{ stats.pending_entries }} 待审</span>
                </div>
              </div>
              <div class="stat-card" style="cursor:pointer" @click="onTabChange('documents')">
                <div class="stat-label">原始文档</div>
                <div class="stat-val">{{ stats.total_documents ?? docsTotal }}</div>
                <div class="stat-meta">点击查看文档库</div>
              </div>
              <div class="stat-card">
                <div class="stat-label">Skill 草稿</div>
                <div class="stat-val">{{ stats.total_skill_drafts }}</div>
                <div class="stat-meta">
                  <span class="dot dot-ok">{{ stats.approved_skill_drafts }} 已激活</span>
                  <span class="dot dot-warn">{{ stats.draft_skill_drafts }} 待审核</span>
                </div>
              </div>
              <div class="stat-card">
                <div class="stat-label">平均置信度</div>
                <div class="stat-val" :class="stats.average_confidence >= 0.8 ? 'val-ok' : 'val-warn'">
                  {{ (stats.average_confidence * 100).toFixed(1) }}<span class="stat-unit">%</span>
                </div>
                <div class="stat-meta">基于 {{ stats.total_entries }} 条数据</div>
              </div>
              <div class="stat-card">
                <div class="stat-label">累计使用次数</div>
                <div class="stat-val">{{ stats.total_usage_count }}</div>
                <div class="stat-meta">任务引用量</div>
              </div>
            </div>
            <!-- Row 2: module distribution -->
            <div class="dist-section">
              <div class="dist-title">模块分布</div>
              <div class="dist-row">
                <div
                  v-for="(cnt, mod) in stats.by_module"
                  :key="mod"
                  class="dist-bar-item"
                >
                  <div class="dist-bar-label">
                    <span class="dist-mod-dot" :style="{ background: MODULE_COLOR[mod] || '#888' }"></span>
                    {{ MODULE_SHORT[mod] || mod }}
                  </div>
                  <div class="dist-bar-track">
                    <div
                      class="dist-bar-fill"
                      :style="{
                        width: stats.total_entries > 0 ? (cnt / stats.total_entries * 100) + '%' : '0%',
                        background: MODULE_COLOR[mod] || '#888',
                      }"
                    ></div>
                  </div>
                  <div class="dist-bar-count">{{ cnt }}</div>
                </div>
                <div v-if="!Object.keys(stats.by_module).length" class="dist-empty">暂无数据</div>
              </div>
            </div>
            <!-- Row 3: func_type distribution -->
            <div class="dist-section">
              <div class="dist-title">业务类型分布</div>
              <div class="dist-chips">
                <div v-for="(cnt, ft) in stats.by_func_type" :key="ft" class="ft-chip">
                  <span class="ft-name">{{ FUNC_TYPE_SHORT[ft] || ft }}</span>
                  <span class="ft-cnt">{{ cnt }}</span>
                </div>
                <div v-if="!Object.keys(stats.by_func_type).length" style="color:#888;font-size:13px">暂无数据</div>
              </div>
            </div>
          </template>
        </NSpin>
      </NTabPane>

      <!-- ── Entries ────────────────────────────────────── -->
      <NTabPane name="entries" tab="📚 知识条目">
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
            :pagination="{ pageSize: 15 }"
            :bordered="false"
            size="small"
            class="kb-table"
          />
        </NSpin>
      </NTabPane>

      <!-- ── Search ─────────────────────────────────────── -->
      <NTabPane name="search" tab="🔍 语义搜索">
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
            <div class="search-meta">找到 {{ searchResults.total }} 条相关结果</div>
            <div
              v-for="r in searchResults.results"
              :key="r.id"
              class="result-card"
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
              <div class="result-body">{{ r.content }}</div>
              <div class="result-foot" v-if="r.keywords?.length">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="#aaa" stroke-width="2"><path d="M20.59 13.41l-7.17 7.17a2 2 0 01-2.83 0L2 12V2h10l8.59 8.59a2 2 0 010 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>
                {{ r.keywords.join(' · ') }}
              </div>
            </div>
          </div>
        </NSpin>
      </NTabPane>

      <!-- ── Skill Drafts ───────────────────────────────── -->
      <NTabPane name="drafts" tab="🚀 Skill 草稿">
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
          </NSpace>
          <div class="toolbar-count" v-if="draftsTotal > 0">{{ draftsTotal }} 条待审核</div>
        </div>

        <NSpin :show="draftsLoading">
          <NEmpty v-if="!drafts.length && !draftsLoading" description="暂无待审核的 Skill 草稿" class="tab-empty">
            <template #extra>
              <NButton size="small" type="primary" @click="openCreateDraftModal">创建 Skill 草稿</NButton>
            </template>
          </NEmpty>
          <NDataTable
            v-else
            :columns="draftColumns"
            :data="drafts"
            :pagination="{ pageSize: 15 }"
            :bordered="false"
            size="small"
            class="kb-table"
          />
        </NSpin>
      </NTabPane>
      <!-- ── Document Library ──────────────────────────── -->
      <NTabPane name="documents" tab="📂 文档库">
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
                </div>

                <!-- Full text -->
                <div class="doc-reader-section-title">📝 文档全文</div>
                <pre class="doc-fulltext">{{ readerDoc.content }}</pre>

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
      </NTabPane>

      <!-- ── Document Import ──────────────────────────── -->
      <NTabPane name="import" tab="📥 文档导入">

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
                  done: importStage !== key && importProgress >= (key === 'upload' ? 10 : key === 'parse' ? 30 : key === 'extract' ? 60 : 100),
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
  </div>
</template>

<style scoped>
/* ── Layout ──────────────────────────────────────────── */
.kb-page {
  padding: 20px 28px;
  max-width: 1320px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* ── Header ──────────────────────────────────────────── */
.kb-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 24px;
  background: linear-gradient(135deg, rgba(32,128,240,.08) 0%, rgba(24,160,88,.06) 100%);
  border: 1px solid rgba(32,128,240,.15);
  border-radius: 12px;
}
.kb-header-left { display: flex; align-items: center; gap: 14px; }
.kb-icon-wrap {
  width: 44px; height: 44px;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #2080f0 0%, #0ea5e9 100%);
  border-radius: 10px;
  color: #fff;
  flex-shrink: 0;
  box-shadow: 0 4px 12px rgba(32,128,240,.35);
}
.kb-title { margin: 0 0 2px; font-size: 20px; font-weight: 700; letter-spacing: 0.2px; }
.kb-sub { margin: 0; font-size: 12px; color: #888; }
.kb-add-btn { border-radius: 8px; font-weight: 600; }

/* ── Tabs ────────────────────────────────────────────── */
.kb-tabs { background: var(--n-color, #fff); border-radius: 12px; }

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
.search-meta { font-size: 12px; color: #888; padding: 4px 0 8px; }

.result-card {
  padding: 14px 16px;
  border-radius: 10px;
  border: 1px solid rgba(0,0,0,.07);
  background: var(--n-color-modal, #fafafa);
  transition: border-color .15s, box-shadow .15s;
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
.result-body { font-size: 13px; color: var(--n-text-color); line-height: 1.6; }
.result-foot { font-size: 11px; color: #aaa; margin-top: 8px; display: flex; align-items: center; gap: 4px; }

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
.doc-reader-section-title { font-size: 13px; font-weight: 600; color: #555; margin-top: 8px; }

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
</style>
