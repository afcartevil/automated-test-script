<template>
  <div id="analysis-section-patch-index" class="card card-pad task-patch-index analysis-anchor">
    <div class="section-title">
      <div>
        <h3>本任务 Patch 索引</h3>
        <p>轻量分页列表；点击条目打开独立详情页（按需从数据库生成）</p>
      </div>
      <span class="muted">{{ resultSummary }}</span>
    </div>

    <div v-if="moduleStats.length" class="module-stats-bar">
      <span class="module-stats-label">模块:</span>
      <button
        type="button"
        class="module-stat-tag"
        :class="{ active: !moduleFilter }"
        @click="selectModule('')"
      >
        全部 <b>{{ totalAllHint }}</b>
      </button>
      <button
        v-for="item in moduleStats.slice(0, 14)"
        :key="item.dev_module || '__empty__'"
        type="button"
        class="module-stat-tag"
        :class="{ active: moduleFilter === moduleValue(item.dev_module) }"
        @click="selectModule(moduleValue(item.dev_module))"
      >
        {{ item.dev_module || '未分类' }} <b>{{ item.count }}</b>
      </button>
    </div>

    <div class="filter-toolbar task-patch-index-filters">
      <select v-model="llmFilter" class="input" @change="reload(1)">
        <option value="">全部方式</option>
        <option value="llm">仅 LLM</option>
        <option value="script">仅脚本</option>
      </select>
      <input
        v-model="search"
        class="input"
        placeholder="搜索 SHA / 标题 / 风险…"
        @keyup.enter="reload(1)"
      />
      <button class="btn" type="button" :disabled="loading" @click="reload(1)">
        {{ loading ? '加载中…' : '搜索' }}
      </button>
    </div>

    <div v-if="error" class="message error">{{ error }}</div>
    <div v-else-if="loading && !items.length" class="empty-state-inline">加载索引…</div>
    <div v-else-if="!items.length" class="empty-state-inline">没有匹配的 patch</div>
    <div v-else class="task-patch-index-list">
      <div
        v-for="patch in items"
        :key="patch.sha"
        class="patch-item patch-item-link"
      >
        <button type="button" class="patch-header" @click="openDetail(patch.sha)">
          <div class="patch-row">
            <span class="pill" :class="patch.llm_analyzed ? 'llm-badge' : 'script-badge'">
              {{ patch.llm_analyzed ? 'LLM' : '脚本' }}
            </span>
            <span class="sha mono">{{ shortId(patch.sha, 12) }}</span>
            <span class="title">{{ patch.title || '-' }}</span>
            <span v-if="patch.dev_module" class="tag-pill dev-module">{{ patch.dev_module }}</span>
            <span class="score" :style="{ color: patchScoreColor(patch.score) }">
              {{ formatPatchScore(patch.score) }}
            </span>
            <span class="rec-pill">{{ patch.recommendation || 'GKI 合入' }}</span>
          </div>
          <div v-if="hasMeta(patch)" class="patch-meta">
            <span v-if="patch.crash_risk === '高'" class="pill crash-pill">🚨 死机风险</span>
            <span v-if="showKeyRisk(patch.key_risk)" class="risk">{{ formatKeyRiskLabel(patch.key_risk) }}</span>
            <span v-if="patch.blocked" class="blocked-tag">⛔ 阻断</span>
          </div>
        </button>
      </div>
    </div>

    <div v-if="totalPages > 1" class="task-patch-index-pagination">
      <button class="btn btn-sm" type="button" :disabled="loading || page <= 1" @click="reload(page - 1)">
        上一页
      </button>
      <span class="muted">{{ page }} / {{ totalPages }}</span>
      <button
        class="btn btn-sm"
        type="button"
        :disabled="loading || page >= totalPages"
        @click="reload(page + 1)"
      >
        下一页
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, shortId } from '../../api'
import {
  formatKeyRiskLabel,
  formatPatchScore,
  isKeyRiskNone,
  patchScoreColor,
} from '../../utils/analysisDisplay'

const props = defineProps<{
  taskId: string
  initialModule?: string
}>()

const router = useRouter()
const PAGE_SIZE = 50
const EMPTY = '__empty__'

const items = ref<any[]>([])
const moduleStats = ref<any[]>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const error = ref('')
const search = ref('')
const moduleFilter = ref('')
const llmFilter = ref('')

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const totalAllHint = computed(() =>
  moduleStats.value.reduce((sum, item) => sum + Number(item.count || 0), 0),
)
const resultSummary = computed(() => {
  if (!total.value) return '0 条'
  const start = (page.value - 1) * PAGE_SIZE + 1
  const end = Math.min(page.value * PAGE_SIZE, total.value)
  return `第 ${start}-${end} 条 / 共 ${total.value} 条`
})

function moduleValue(devModule?: string | null) {
  const value = String(devModule ?? '').trim()
  return value || EMPTY
}

function selectModule(value: string) {
  moduleFilter.value = moduleFilter.value === value ? '' : value
  void reload(1)
}

function openDetail(sha: string) {
  const target = String(sha || '').trim()
  if (!target) return
  const href = router.resolve({ name: 'patch-detail', params: { sha: target } }).href
  window.open(href, '_blank', 'noopener,noreferrer')
}

function showKeyRisk(keyRisk?: string) {
  const raw = String(keyRisk || '').trim()
  return Boolean(raw) && !isKeyRiskNone(raw)
}

function hasMeta(patch: any) {
  return Boolean(
    patch?.crash_risk === '高' ||
    showKeyRisk(patch?.key_risk) ||
    patch?.blocked,
  )
}

async function loadModules() {
  try {
    const data = await api.get<any>(`/api/tasks/${encodeURIComponent(props.taskId)}/module-stats`)
    moduleStats.value = data.stats || []
  } catch {
    moduleStats.value = []
  }
}

async function reload(nextPage = page.value) {
  if (!props.taskId) return
  loading.value = true
  error.value = ''
  page.value = Math.max(1, nextPage)
  try {
    const params = new URLSearchParams({
      page: String(page.value),
      page_size: String(PAGE_SIZE),
    })
    if (search.value.trim()) params.set('search', search.value.trim())
    if (moduleFilter.value) params.set('module', moduleFilter.value)
    if (llmFilter.value) params.set('llm', llmFilter.value)
    const data = await api.get<any>(
      `/api/tasks/${encodeURIComponent(props.taskId)}/patches?${params.toString()}`,
    )
    items.value = data.items || []
    total.value = Number(data.total || 0)
  } catch (err: any) {
    error.value = err.message || String(err)
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

watch(
  () => props.taskId,
  async () => {
    search.value = ''
    llmFilter.value = ''
    moduleFilter.value = props.initialModule || ''
    await loadModules()
    await reload(1)
  },
)

watch(
  () => props.initialModule,
  (value) => {
    if (value == null) return
    moduleFilter.value = value
    void reload(1)
  },
)

onMounted(async () => {
  moduleFilter.value = props.initialModule || ''
  await loadModules()
  await reload(1)
})

defineExpose({
  setModuleFilter(mod: string) {
    moduleFilter.value = mod || ''
    void reload(1)
  },
})
</script>
