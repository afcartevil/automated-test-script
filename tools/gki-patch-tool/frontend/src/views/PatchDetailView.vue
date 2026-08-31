<template>
  <section class="patch-detail-page">
    <div class="patch-detail-shell">
      <header class="patch-detail-hero">
        <div class="patch-detail-hero-main">
          <div class="patch-detail-crumbs">
            <RouterLink to="/analysis">分析任务</RouterLink>
            <span>/</span>
            <RouterLink to="/patches">Patch 数据库</RouterLink>
            <span>/</span>
            <span class="mono">{{ shortId(sha, 12) }}</span>
          </div>
          <h1 class="patch-detail-title">{{ metaTitle || 'Patch 详情' }}</h1>
          <div class="patch-detail-hero-meta">
            <span class="mono patch-detail-sha-chip">{{ shortId(sha, 12) }}</span>
            <span v-if="metaScore" class="patch-detail-score" :style="{ color: scoreColor }">
              {{ metaScore }}
            </span>
            <span v-if="metaModule" class="patch-detail-chip">{{ metaModule }}</span>
            <span v-if="metaType" class="patch-detail-chip" :class="metaType === 'LLM 分析' ? 'llm' : 'script'">
              {{ metaType }}
            </span>
          </div>
        </div>
        <div class="toolbar patch-detail-actions">
          <button class="btn" type="button" @click="goBack">返回</button>
          <a
            v-if="commitUrl"
            class="btn primary"
            :href="commitUrl"
            target="_blank"
            rel="noopener"
          >打开提交</a>
        </div>
      </header>

      <div v-if="loading" class="card card-pad patch-detail-state">加载 patch 详情…</div>
      <div v-else-if="error" class="message error">{{ error }}</div>
      <article
        v-else
        class="patch-detail-html patch-detail-frame"
        v-html="html"
        @click="onDetailHtmlClick"
      />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, shortId } from '../api'
import { patchScoreColor } from '../utils/analysisDisplay'

const route = useRoute()
const router = useRouter()

const sha = computed(() => String(route.params.sha || '').trim())
const html = ref('')
const metaTitle = ref('')
const metaScore = ref('')
const metaModule = ref('')
const metaType = ref('')
const commitUrl = ref('')
const loading = ref(false)
const error = ref('')

const scoreColor = computed(() => {
  const num = Number(String(metaScore.value).replace(/[^\d.]/g, ''))
  return Number.isFinite(num) ? patchScoreColor(num) : '#0f766e'
})

function extractMeta(content: string) {
  const titleMatch =
    content.match(/class="patch-title-text"[^>]*>([^<]+)/i) ||
    content.match(/class="patch-title"[^>]*>([^<]+)/i)
  metaTitle.value = titleMatch?.[1]?.trim() || ''

  const scoreMatch = content.match(/class="patch-score"[^>]*>\s*得分\s*([^<]+)/i)
  metaScore.value = scoreMatch?.[1]?.trim() ? `得分 ${scoreMatch[1].trim()}` : ''

  const moduleMatch = content.match(/class="patch-module"[^>]*>([^<]+)/i)
  metaModule.value = moduleMatch?.[1]?.trim() || ''

  const typeMatch = content.match(/class="patch-type-tag[^"]*"[^>]*>([^<]+)/i)
  metaType.value = typeMatch?.[1]?.trim() || ''

  const linkMatch = content.match(/href="(https?:\/\/[^"]+)"[^>]*>\s*🔗\s*原始提交/i)
  commitUrl.value = linkMatch?.[1]?.trim() || ''
}

async function loadDetail() {
  const target = sha.value
  if (!target) {
    error.value = '缺少 patch SHA'
    html.value = ''
    return
  }
  loading.value = true
  error.value = ''
  html.value = ''
  metaTitle.value = ''
  metaScore.value = ''
  metaModule.value = ''
  metaType.value = ''
  commitUrl.value = ''
  try {
    const content = await api.get<string>(`/api/patches/${encodeURIComponent(target)}/html`)
    html.value = content
    extractMeta(content)
  } catch (err: any) {
    error.value = err.message || String(err)
  } finally {
    loading.value = false
  }
}

function goBack() {
  if (window.history.length > 1) {
    router.back()
    return
  }
  router.push('/analysis')
}

function extractJumpSha(el: HTMLElement) {
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
  const jump = extractJumpSha(target)
  if (!jump) return
  event.preventDefault()
  event.stopPropagation()
  const href = router.resolve({ name: 'patch-detail', params: { sha: jump } }).href
  window.open(href, '_blank', 'noopener,noreferrer')
}

watch(sha, () => {
  void loadDetail()
})

onMounted(() => {
  void loadDetail()
})
</script>
