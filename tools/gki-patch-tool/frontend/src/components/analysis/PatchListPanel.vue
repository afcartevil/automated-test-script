<template>
  <div id="analysis-section-patches" class="patch-results analysis-anchor">
    <div class="patch-count-bar">
      <span class="count">
        📦 {{ filteredPatches.length }} 笔 patch
        <template v-if="filteredPatches.length !== patches.length">
          / 共 {{ patches.length }} 笔
        </template>
        · LLM {{ llmCount }} 笔 · 平均分 <strong>{{ averageScore }}</strong>
      </span>
    </div>

    <div v-if="moduleStats.length" class="module-stats-bar">
      <span class="module-stats-label">🗂 模块分布:</span>
      <button
        v-for="[mod, count] in moduleStats.slice(0, 12)"
        :key="mod"
        type="button"
        class="module-stat-tag"
        :class="{ active: moduleFilter === mod }"
        @click="setModuleFilter(mod)"
      >
        {{ mod }} <b>{{ count }}</b>
      </button>
    </div>

    <div v-if="futureFixCount" class="future-fix-summary-bar">
      <span class="future-fix-summary-label">
        🔗 {{ futureFixCount }} 笔引入问题且有后续 Fixes 修复
      </span>
      <button
        type="button"
        class="btn btn-sm future-fix-filter-btn"
        :class="{ active: futureFixFilter }"
        @click="toggleFutureFixFilter"
      >
        {{ futureFixFilter ? '显示全部' : '仅看有后续修复' }}
      </button>
    </div>

    <div class="legend">
      <span class="legend-item"><span class="pill llm-badge">LLM</span> 深度分析</span>
      <span class="legend-item"><span class="pill script-badge">脚本</span> 规则分析</span>
    </div>

    <div class="filter-toolbar">
      <select v-model="llmFilter" class="input">
        <option value="">全部方式</option>
        <option value="llm">仅 LLM</option>
        <option value="script">仅脚本</option>
      </select>
      <select v-model="moduleFilter" class="input">
        <option value="">全部模块</option>
        <option v-for="[mod, count] in moduleStats" :key="mod" :value="mod">
          {{ mod }} ({{ count }})
        </option>
      </select>
      <input v-model="searchQuery" class="input" placeholder="搜索 SHA / 标题 / 风险…" />
    </div>

    <div v-if="!filteredPatches.length" class="empty-state-inline">没有匹配的 patch</div>

    <div ref="patchListScrollRef" class="patch-list-scroll">
      <div
        v-for="patch in filteredPatches"
        :key="patch.sha"
        class="patch-item"
        :class="{ open: expandedSha === patch.sha }"
        :data-patch-sha="patch.sha"
      >
        <button type="button" class="patch-header" @click="togglePatch(patch.sha)">
          <div class="patch-row">
            <span class="pill" :class="patch.llm_analyzed ? 'llm-badge' : 'script-badge'">
              {{ patch.llm_analyzed ? 'LLM' : '脚本' }}
            </span>
            <span class="sha mono">{{ shortId(patch.sha, 12) }}</span>
            <span class="title">{{ patch.title || patch.subject || '-' }}</span>
            <span class="score" :style="{ color: patchScoreColor(patch.score) }">
              {{ formatPatchScore(patch.score) }}
            </span>
            <span class="rec-pill">{{ patch.recommendation || patch.merge_advice || 'GKI 合入' }}</span>
          </div>
          <div class="patch-meta">
            <span v-if="hasFutureFix(patch)" class="pill defect-pill" :title="formatFutureFixLine(patch)">
              ⚠ 已知缺陷 · {{ patch.fix_in_future.length }} 笔修复
            </span>
            <span v-for="tag in futureFixTags(patch)" :key="tag" class="pill future-fix-tag-pill">
              修复于 {{ tag }}
            </span>
            <span v-if="patch.crash_risk === '高'" class="pill crash-pill">🚨 死机风险</span>
            <span
              v-for="label in patchTagLabels(patch)"
              :key="label"
              class="tag-pill"
              :class="{ 'dev-module': label === patch.dev_module }"
            >
              {{ label }}
            </span>
            <span v-if="patch.key_risk" class="risk">{{ formatKeyRiskLabel(patch.key_risk) }}</span>
            <span v-if="patch.blocked" class="blocked-tag">⛔ 阻断</span>
          </div>
        </button>
        <div v-if="expandedSha === patch.sha" class="patch-detail open">
          <div v-if="detailLoading[patch.sha]" class="patch-detail-loading">加载中…</div>
          <div v-else-if="detailErrors[patch.sha]" class="message error">{{ detailErrors[patch.sha] }}</div>
          <div
            v-else
            class="patch-detail-html"
            v-html="detailHtml[patch.sha] || ''"
            @click="onDetailHtmlClick"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { api, shortId } from '../../api'
import { scrollPanelToSection } from '../../composables/useSectionScroll'
import {
  buildModuleStats,
  collectFutureFixPatches,
  formatFutureFixLine,
  formatKeyRiskLabel,
  formatPatchScore,
  futureFixTags,
  hasFutureFix,
  patchScoreColor,
  patchTagLabels,
  resolvePatchSha,
} from '../../utils/analysisDisplay'

const props = defineProps<{
  patches: any[]
  activeModule?: string
  futureFixPoolCount?: number
}>()

const emit = defineEmits<{
  'update:activeModule': [value: string]
}>()

const llmFilter = ref('')
const moduleFilter = ref('')
const futureFixFilter = ref(false)
const searchQuery = ref('')
const expandedSha = ref('')
const patchListScrollRef = ref<HTMLElement | null>(null)
const detailHtml = reactive<Record<string, string>>({})
const detailLoading = reactive<Record<string, boolean>>({})
const detailErrors = reactive<Record<string, string>>({})

watch(
  () => props.activeModule,
  (value) => {
    moduleFilter.value = value || ''
  },
  { immediate: true },
)

const moduleStats = computed(() => buildModuleStats(props.patches))

const futureFixCount = computed(() => {
  const pool = Number(props.futureFixPoolCount || 0)
  if (pool > 0) return pool
  return collectFutureFixPatches(props.patches).length
})

const filteredPatches = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  return props.patches.filter((patch) => {
    if (futureFixFilter.value && !hasFutureFix(patch)) return false
    if (llmFilter.value === 'llm' && !patch.llm_analyzed) return false
    if (llmFilter.value === 'script' && patch.llm_analyzed) return false
    if (moduleFilter.value && (patch.dev_module || '其他') !== moduleFilter.value) return false
    if (!query) return true
    const haystack = [
      patch.sha,
      patch.title,
      patch.subject,
      patch.key_risk,
      patch.recommendation,
      patch.merge_advice,
      patch.dev_module,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    return haystack.includes(query)
  })
})

const llmCount = computed(() => props.patches.filter((patch) => patch.llm_analyzed).length)

const averageScore = computed(() => {
  const scores = props.patches.map((patch) => Number(patch.score)).filter((score) => Number.isFinite(score))
  if (!scores.length) return '0.0'
  return (scores.reduce((sum, score) => sum + score, 0) / scores.length).toFixed(1)
})

function setModuleFilter(mod: string) {
  moduleFilter.value = moduleFilter.value === mod ? '' : mod
  emit('update:activeModule', moduleFilter.value)
}

function toggleFutureFixFilter() {
  futureFixFilter.value = !futureFixFilter.value
}

async function togglePatch(sha: string) {
  if (expandedSha.value === sha) {
    expandedSha.value = ''
    return
  }
  expandedSha.value = sha
  if (detailHtml[sha]) return
  detailLoading[sha] = true
  detailErrors[sha] = ''
  try {
    detailHtml[sha] = await api.get<string>(`/api/patches/${sha}/html`)
  } catch (err: any) {
    detailErrors[sha] = err.message || String(err)
  } finally {
    detailLoading[sha] = false
  }
}

async function scrollToPatchRow(targetSha: string, scrollPanel?: HTMLElement | null) {
  if (scrollPanel) {
    scrollPanelToSection(scrollPanel, 'analysis-section-patches')
  }
  await nextTick()
  const listEl = patchListScrollRef.value
  const row = listEl?.querySelector(
    `[data-patch-sha="${CSS.escape(targetSha)}"]`,
  ) as HTMLElement | null
  if (row && listEl) {
    const top = row.offsetTop - listEl.clientHeight / 2 + row.clientHeight / 2
    listEl.scrollTo({ top: Math.max(0, top), behavior: 'smooth' })
    return
  }
  row?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

function extractDetailJumpSha(el: HTMLElement) {
  const dataSha = el.getAttribute('data-patch-jump')
  if (dataSha) return dataSha.trim()

  if (el.tagName === 'A') {
    const href = el.getAttribute('href') || ''
    const match = href.match(/\/\+\/([0-9a-f]+)$/i)
    if (match) return match[1]
  }

  const text = (el.textContent || '').trim()
  const hex = text.replace(/[^0-9a-f]/gi, '')
  return hex.length >= 7 ? hex : ''
}

function onDetailHtmlClick(event: MouseEvent) {
  const target = (event.target as HTMLElement | null)?.closest(
    '.future-fix-sha, .future-fix-cp, [data-patch-jump]',
  ) as HTMLElement | null
  if (!target) return

  const sha = extractDetailJumpSha(target)
  const resolved = resolvePatchSha(props.patches, sha)
  if (!resolved) return

  event.preventDefault()
  event.stopPropagation()
  void openPatch(resolved)
}

async function openPatch(sha: string, scrollPanel?: HTMLElement | null) {
  const target = resolvePatchSha(props.patches, sha)
  if (!target) {
    searchQuery.value = String(sha || '').slice(0, 12)
    return false
  }

  llmFilter.value = ''
  moduleFilter.value = ''
  futureFixFilter.value = false
  emit('update:activeModule', '')
  searchQuery.value = ''
  await togglePatch(target)
  await scrollToPatchRow(target, scrollPanel)
  return true
}

defineExpose({
  openPatch,
  getScrollElement: () => patchListScrollRef.value,
})
</script>
