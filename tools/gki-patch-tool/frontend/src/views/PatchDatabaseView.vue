<template>
  <section class="patch-db-page">
    <div class="topbar">
      <div>
        <p class="eyebrow">Patch Database</p>
        <h1 class="page-title">Patch 数据库</h1>
        <p v-if="!isEmbedded" class="page-desc">浏览已入库的分析结果，按模块筛选并快速预览 patch 详情。</p>
      </div>
    </div>

    <div class="grid grid-4 patch-db-stats">
      <div class="card metric">
        <div class="metric-label">Patch 总量</div>
        <div class="metric-value">{{ dbOverview.totalPatches }}</div>
        <div class="metric-note">{{ isAllModulesFilter ? '全库统计' : `筛选后 ${total} 条` }}</div>
      </div>
      <div class="card metric">
        <div class="metric-label">开发模块</div>
        <div class="metric-value">{{ dbOverview.moduleCount }}</div>
        <div class="metric-note">已分类模块数</div>
      </div>
      <div class="card metric">
        <div class="metric-label">全库均分</div>
        <div class="metric-value">{{ dbOverview.avgScore }}</div>
        <div class="metric-note">10 分制加权平均</div>
      </div>
      <div class="card metric">
        <div class="metric-label">当前页</div>
        <div class="metric-value">{{ pageRangeLabel }}</div>
        <div class="metric-note">共 {{ totalPages }} 页</div>
      </div>
    </div>

    <div class="card card-pad patch-db-filter-card">
      <div class="patch-db-filter-row">
        <div class="patch-db-search-wrap">
          <input
            v-model="search"
            class="input patch-db-search"
            placeholder="搜索 SHA 或标题…"
            @keyup.enter="loadPatches(1)"
          />
          <button v-if="search" type="button" class="patch-db-search-clear" @click="clearSearch">×</button>
        </div>
        <select v-model="moduleName" class="input patch-db-module-select" @change="loadPatches(1)">
          <option :value="MODULE_ALL">全部模块</option>
          <option
            v-for="module in moduleStats"
            :key="module.dev_module || '__empty__'"
            :value="moduleFilterValue(module.dev_module)"
          >
            {{ module.dev_module || '未分类' }} ({{ module.count }})
          </option>
        </select>
        <button class="btn primary" :disabled="loading" @click="loadPatches(1)">
          {{ loading ? '加载中…' : '搜索' }}
        </button>
        <button
          v-if="hasActiveFilter"
          type="button"
          class="btn"
          :disabled="loading"
          @click="resetFilters"
        >
          重置筛选
        </button>
      </div>

      <div v-if="topModuleStats.length" class="patch-db-module-bar">
        <span class="patch-db-module-label">快捷筛选</span>
        <div class="patch-db-module-chips">
          <button
            type="button"
            class="chip"
            :class="{ active: isAllModulesFilter }"
            @click="selectModule(MODULE_ALL)"
          >
            全部
          </button>
          <button
            v-for="module in topModuleStats"
            :key="module.dev_module || '__empty__'"
            type="button"
            class="chip"
            :class="{ active: isModuleChipActive(module.dev_module) }"
            @click="selectModule(moduleFilterValue(module.dev_module))"
          >
            {{ module.dev_module || '未分类' }}
            <strong>{{ module.count }}</strong>
          </button>
        </div>
      </div>
    </div>

    <div class="workspace-layout patch-db-layout">
      <div class="workspace-left">
        <div class="card patch-db-table-card">
          <div class="patch-db-table-head">
            <strong>Patch 列表</strong>
            <span class="muted">{{ resultSummary }}</span>
          </div>

          <div v-if="loading" class="patch-db-loading">正在加载 patch 列表…</div>

          <div v-else-if="!patches.length" class="empty patch-db-empty">
            {{ hasActiveFilter ? '没有匹配的 patch，试试调整筛选条件' : '暂无 patch 数据' }}
          </div>

          <div v-else class="patch-db-list-scroll">
            <button
              v-for="patch in patches"
              :key="patch.sha"
              type="button"
              class="patch-db-list-item"
              :class="{ active: previewSha === patch.sha }"
              @click="togglePreview(patch.sha)"
            >
              <span class="mono patch-db-sha">{{ shortId(patch.sha, 12) }}</span>
              <span class="patch-db-title" :title="patch.title || ''">{{ patch.title || '-' }}</span>
            </button>
          </div>

          <div v-if="totalPages > 1" class="patch-db-pagination">
            <button class="btn btn-sm" :disabled="loading || page <= 1" @click="loadPatches(page - 1)">
              上一页
            </button>
            <span class="muted">{{ page }} / {{ totalPages }}</span>
            <button class="btn btn-sm" :disabled="loading || page >= totalPages" @click="loadPatches(page + 1)">
              下一页
            </button>
          </div>
        </div>
      </div>

      <aside class="workspace-detail-shell patch-db-detail-shell">
        <div class="workspace-detail patch-db-detail">
          <div v-if="previewSha" class="card card-pad patch-db-preview">
            <div class="section-title">
              <div>
                <h2>Patch 详情</h2>
                <p class="mono">{{ previewSha }}</p>
              </div>
              <div class="toolbar">
                <RouterLink
                  class="btn btn-sm"
                  :to="{ name: 'patch-detail', params: { sha: previewSha } }"
                  target="_blank"
                  rel="noopener"
                >
                  打开详情页
                </RouterLink>
                <a class="btn btn-sm" :href="`/api/patches/${previewSha}/html`" target="_blank">原始 HTML</a>
                <button type="button" class="btn btn-sm" @click="previewSha = ''">收起</button>
              </div>
            </div>
            <div class="patch-db-preview-body">
              <div v-if="previewLoading" class="detail-loading">正在加载 Patch 详情…</div>
              <div v-else-if="previewError" class="message error">{{ previewError }}</div>
              <div v-else class="patch-detail-html" v-html="previewHtml"></div>
            </div>
          </div>
          <div v-else class="card detail-empty">
            <div>
              <strong>请选择一条 Patch</strong>
              <span>点击左侧表格行后，详情会在这里显示。</span>
            </div>
          </div>
        </div>
      </aside>
    </div>

    <div v-if="error" class="message error patch-db-error">{{ error }}</div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { api, shortId } from '../api'
import { isEmbeddedMode } from '../composables/useEmbeddedNav'

const isEmbedded = isEmbeddedMode()
const route = useRoute()
const PAGE_SIZE = 50
const MODULE_ALL = '__all__'
const MODULE_EMPTY = '__empty__'

const patches = ref<any[]>([])
const moduleStats = ref<any[]>([])
const search = ref('')
const moduleName = ref(MODULE_ALL)
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const previewSha = ref('')
const previewHtml = ref('')
const previewLoading = ref(false)
const previewError = ref('')
const error = ref('')

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))

const dbOverview = computed(() => {
  const allCount = moduleStats.value.reduce((sum, item) => sum + Number(item.count || 0), 0)
  const weighted =
    allCount > 0
      ? moduleStats.value.reduce(
          (sum, item) => sum + Number(item.avg_score || 0) * Number(item.count || 0),
          0,
        ) / allCount
      : 0
  const moduleCount = moduleStats.value.filter((item) => String(item.dev_module || '').trim()).length
  return {
    totalPatches: allCount,
    moduleCount,
    avgScore: allCount > 0 ? weighted.toFixed(1) : '-',
  }
})

const topModuleStats = computed(() => moduleStats.value.slice(0, 14))

const isAllModulesFilter = computed(() => moduleName.value === MODULE_ALL)

const hasActiveFilter = computed(() => Boolean(search.value.trim() || !isAllModulesFilter.value))

function moduleFilterValue(devModule?: string | null) {
  const value = String(devModule ?? '').trim()
  return value || MODULE_EMPTY
}

function isModuleChipActive(devModule?: string | null) {
  if (isAllModulesFilter.value) return false
  return moduleName.value === moduleFilterValue(devModule)
}

function moduleFilterParam() {
  return isAllModulesFilter.value ? '' : moduleName.value
}

const pageStart = computed(() => (total.value ? (page.value - 1) * PAGE_SIZE + 1 : 0))
const pageEnd = computed(() => Math.min(page.value * PAGE_SIZE, total.value))

const pageRangeLabel = computed(() => {
  if (!total.value) return '-'
  return `${pageStart.value}-${pageEnd.value}`
})

const resultSummary = computed(() => {
  if (!total.value) return '0 条结果'
  return `第 ${pageStart.value}-${pageEnd.value} 条，共 ${total.value} 条`
})

function selectModule(name: string) {
  moduleName.value = name
  loadPatches(1)
}

function clearSearch() {
  search.value = ''
  loadPatches(1)
}

function resetFilters() {
  search.value = ''
  moduleName.value = MODULE_ALL
  loadPatches(1)
}

async function loadPreview(sha: string) {
  previewLoading.value = true
  previewError.value = ''
  previewHtml.value = ''
  try {
    previewHtml.value = await api.get<string>(`/api/patches/${sha}/html`)
  } catch (err: any) {
    previewError.value = err.message || String(err)
  } finally {
    previewLoading.value = false
  }
}

function togglePreview(sha: string) {
  if (previewSha.value === sha) {
    previewSha.value = ''
    previewHtml.value = ''
    previewError.value = ''
    previewLoading.value = false
    return
  }
  previewSha.value = sha
  loadPreview(sha)
}

async function loadPatches(nextPage = page.value) {
  error.value = ''
  loading.value = true
  try {
    page.value = nextPage
    const params = new URLSearchParams({
      page: String(page.value),
      page_size: String(PAGE_SIZE),
      search: search.value.trim(),
      dev_module: moduleFilterParam(),
    })
    const data = await api.get<any>(`/api/patches?${params}`)
    patches.value = data.items || data.patches || []
    total.value = Number(data.total || patches.value.length)

    if (previewSha.value && !patches.value.some((patch) => patch.sha === previewSha.value)) {
      previewSha.value = ''
      previewHtml.value = ''
      previewError.value = ''
    }
  } catch (err: any) {
    error.value = err.message || String(err)
    patches.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

async function loadModules() {
  try {
    const data = await api.get<any>('/api/patches/module-stats')
    moduleStats.value = data.stats || []
  } catch {
    moduleStats.value = []
  }
}

watch(previewSha, (sha) => {
  if (!sha) {
    previewHtml.value = ''
    previewError.value = ''
    previewLoading.value = false
  }
})

onMounted(async () => {
  const moduleQuery = String(route.query.module || '').trim()
  if (moduleQuery) {
    moduleName.value = moduleFilterValue(moduleQuery)
  }
  await loadModules()
  await loadPatches(1)
})
</script>
