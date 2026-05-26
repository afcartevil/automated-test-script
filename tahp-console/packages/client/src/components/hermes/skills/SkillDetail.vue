<script setup lang="ts">
import { ref, watch } from 'vue'
import MarkdownRenderer from '@/components/hermes/chat/MarkdownRenderer.vue'
import {
  fetchSkillContent, fetchSkillFiles, pinSkillApi,
  fetchSkillHistory, fetchSkillCommitDetail,
  type SkillFileEntry, type SkillCommit, type SkillCommitDetail,
} from '@/api/hermes/skills'
import { useI18n } from 'vue-i18n'
import { useMessage } from 'naive-ui'

const { t } = useI18n()
const message = useMessage()

const props = defineProps<{
  category: string
  skill: string
  skillName: string
  version?: string
  updatedAt?: number
  patchCount?: number
  useCount?: number
  viewCount?: number
  pinned?: boolean
}>()

const emit = defineEmits<{
  pinToggled: [name: string, pinned: boolean]
}>()

// ── tab 切换 ──────────────────────────────────────────────────────────────────
type Tab = 'content' | 'history'
const activeTab = ref<Tab>('content')

// ── content tab ───────────────────────────────────────────────────────────────
const content = ref('')
const files = ref<SkillFileEntry[]>([])
const loading = ref(false)
const fileContent = ref('')
const viewingFile = ref<string | null>(null)
const fileLoading = ref(false)

// ── history tab ───────────────────────────────────────────────────────────────
const historyLoading = ref(false)
const commits = ref<SkillCommit[]>([])
const historyMessage = ref('')
const selectedCommit = ref<SkillCommit | null>(null)
const commitDetail = ref<SkillCommitDetail | null>(null)
const commitDetailLoading = ref(false)

async function loadSkill() {
  loading.value = true
  viewingFile.value = null
  fileContent.value = ''
  files.value = []
  content.value = ''
  try {
    const skillPath = `${props.category}/${props.skill}/SKILL.md`
    const [skillContent, skillFiles] = await Promise.all([
      fetchSkillContent(skillPath),
      fetchSkillFiles(props.category, props.skill),
    ])
    content.value = skillContent
    files.value = skillFiles.filter(f => !f.isDir && f.path !== 'SKILL.md')
  } catch (err: any) {
    content.value = t('skills.loadFailed') + `: ${err.message}`
  } finally {
    loading.value = false
  }
}

async function loadHistory() {
  if (historyLoading.value) return
  historyLoading.value = true
  commits.value = []
  historyMessage.value = ''
  selectedCommit.value = null
  commitDetail.value = null
  try {
    const res = await fetchSkillHistory(props.category, props.skill)
    commits.value = res.commits ?? []
    historyMessage.value = res.message ?? ''
  } catch (err: any) {
    historyMessage.value = `${t('skills.historyUnavailable')}: ${err.message}`
  } finally {
    historyLoading.value = false
  }
}

async function selectCommit(commit: SkillCommit) {
  selectedCommit.value = commit
  commitDetail.value = null
  commitDetailLoading.value = true
  try {
    commitDetail.value = await fetchSkillCommitDetail(props.category, props.skill, commit.hash)
  } catch (err: any) {
    commitDetail.value = {
      hash: commit.hash, date: commit.date, author: commit.author,
      message: commit.message, body: '', diff: `获取失败: ${err.message}`,
    }
  } finally {
    commitDetailLoading.value = false
  }
}

function switchTab(tab: Tab) {
  activeTab.value = tab
  if (tab === 'history' && commits.value.length === 0 && !historyLoading.value) {
    loadHistory()
  }
}

async function viewFile(filePath: string) {
  fileLoading.value = true
  viewingFile.value = filePath
  try {
    const base = `${props.category}/${props.skill}/`
    let relPath = filePath
    if (filePath.startsWith('/') || /^[a-zA-Z]:[\\/]/.test(filePath)) {
      const normalizedPath = filePath.replace(/\\/g, '/')
      const segments = normalizedPath.split(/(?:^|\/)(?:\.hermes|hermes)\/skills\//)[1]
      if (segments) {
        const afterSkillDir = segments.split('/').slice(2).join('/')
        relPath = afterSkillDir
      }
    }
    fileContent.value = await fetchSkillContent(`${base}${relPath}`)
  } catch (err: any) {
    fileContent.value = t('skills.fileLoadFailed') + `: ${err.message}`
  } finally {
    fileLoading.value = false
  }
}

function backToSkill() { viewingFile.value = null; fileContent.value = '' }

const pinLoading = ref(false)
async function handlePinToggle() {
  if (pinLoading.value) return
  pinLoading.value = true
  try {
    const newPinned = !props.pinned
    await pinSkillApi(props.skillName, newPinned)
    emit('pinToggled', props.skillName, newPinned)
  } catch (err: any) {
    message.error(t('skills.pinFailed') + `: ${err.message}`)
  } finally {
    pinLoading.value = false
  }
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString('zh-CN', {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    })
  } catch { return iso }
}

watch(() => `${props.category}/${props.skill}`, () => {
  activeTab.value = 'content'
  commits.value = []
  selectedCommit.value = null
  commitDetail.value = null
  loadSkill()
}, { immediate: true })
</script>

<template>
  <div class="skill-detail">

    <!-- ── 标题行 ─────────────────────────────────────────────────────────── -->
    <div class="detail-title">
      <div class="title-left">
        <span class="detail-category">{{ category }}</span>
        <span class="detail-separator">/</span>
        <span class="detail-name">{{ skill }}</span>
        <span v-if="version" class="detail-version">v{{ version }}</span>
      </div>
      <div class="usage-stats">
        <button class="pin-toggle" :class="{ active: pinned }" :disabled="pinLoading"
          :title="pinned ? t('skills.unpin') : t('skills.pin')" @click="handlePinToggle">
          <svg width="16" height="16" viewBox="0 0 24 24" :fill="pinned ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2">
            <path d="M16 12V4h1V2H7v2h1v8l-2 2v2h5.2v6h1.6v-6H18v-2l-2-2z"/>
          </svg>
        </button>
        <span v-if="viewCount != null" class="usage-stat" title="Views">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>
          </svg>{{ viewCount }}
        </span>
        <span v-if="useCount != null" class="usage-stat" title="Uses">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <polyline points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
          </svg>{{ useCount }}
        </span>
      </div>
    </div>

    <!-- ── Tab 切换 ──────────────────────────────────────────────────────── -->
    <div class="tab-bar">
      <button class="tab-btn" :class="{ active: activeTab === 'content' }" @click="switchTab('content')">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
          <polyline points="14 2 14 8 20 8"/>
        </svg>
        {{ t('skills.skillContent') }}
      </button>
      <button class="tab-btn" :class="{ active: activeTab === 'history' }" @click="switchTab('history')">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <polyline points="12 8 12 12 14 14"/><path d="M3.05 11a9 9 0 1 1 .5 4m-.5 5v-5h5"/>
        </svg>
        {{ t('skills.history') }}
        <span v-if="commits.length > 0" class="tab-count">{{ commits.length }}</span>
      </button>
    </div>

    <!-- ── 技能内容 Tab ───────────────────────────────────────────────────── -->
    <template v-if="activeTab === 'content'">
      <div v-if="loading && !content" class="detail-loading">{{ t('common.loading') }}</div>
      <template v-else>
        <div v-if="viewingFile" class="detail-breadcrumb">
          <button class="back-btn" @click="backToSkill">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
            {{ t('skills.backTo') }} {{ skill }}
          </button>
          <span class="breadcrumb-path">{{ viewingFile }}</span>
        </div>
        <div class="detail-content">
          <MarkdownRenderer v-if="viewingFile" :content="fileContent" />
          <MarkdownRenderer v-else :content="content" />
        </div>
        <div v-if="!viewingFile && files.length > 0" class="detail-files">
          <div class="files-header">{{ t('skills.attachedFiles') }}</div>
          <div class="files-list">
            <button v-for="f in files" :key="f.path" class="file-item" @click="viewFile(f.path)">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
              <span>{{ f.path }}</span>
            </button>
          </div>
        </div>
      </template>
    </template>

    <!-- ── 变更历史 Tab ──────────────────────────────────────────────────── -->
    <template v-else-if="activeTab === 'history'">
      <div v-if="historyLoading" class="detail-loading">{{ t('common.loading') }}</div>

      <!-- commit 详情视图 -->
      <template v-else-if="selectedCommit && commitDetail">
        <div class="history-detail-header">
          <button class="back-btn" @click="selectedCommit = null; commitDetail = null">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="15 18 9 12 15 6"/>
            </svg>
            {{ t('skills.backToHistory') }}
          </button>
        </div>
        <div class="commit-detail-meta">
          <div class="meta-row">
            <span class="meta-label">{{ t('skills.commitHash') }}</span>
            <code class="commit-hash-full">{{ commitDetail.hash.slice(0, 12) }}</code>
          </div>
          <div class="meta-row">
            <span class="meta-label">{{ t('skills.commitDate') }}</span>
            <span>{{ formatDate(commitDetail.date) }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">{{ t('skills.commitAuthor') }}</span>
            <span>{{ commitDetail.author }}</span>
          </div>
          <div class="meta-row message-row">
            <span class="meta-label">{{ t('skills.commitMessage') }}</span>
            <span class="commit-message-text">{{ commitDetail.message }}</span>
          </div>
          <div v-if="commitDetail.body" class="commit-body">{{ commitDetail.body }}</div>
        </div>
        <div v-if="commitDetail.diff" class="diff-section">
          <div class="diff-title">{{ t('skills.diffTitle') }}</div>
          <div v-if="commitDetailLoading" class="detail-loading">{{ t('common.loading') }}</div>
          <pre v-else class="diff-block"><code>{{ commitDetail.diff }}</code></pre>
        </div>
      </template>

      <!-- commit 列表 -->
      <template v-else>
        <div v-if="historyMessage && commits.length === 0" class="history-empty">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" opacity="0.25">
            <polyline points="12 8 12 12 14 14"/><path d="M3.05 11a9 9 0 1 1 .5 4m-.5 5v-5h5"/>
          </svg>
          <span>{{ historyMessage }}</span>
        </div>
        <div v-else-if="commits.length === 0" class="history-empty">
          <span>{{ t('skills.historyEmpty') }}</span>
        </div>
        <div v-else class="commit-list">
          <button
            v-for="commit in commits"
            :key="commit.hash"
            class="commit-item"
            @click="selectCommit(commit)"
          >
            <div class="commit-left">
              <code class="commit-hash">{{ commit.shortHash }}</code>
              <span class="commit-msg">{{ commit.message }}</span>
            </div>
            <div class="commit-right">
              <span class="commit-author">{{ commit.author }}</span>
              <span class="commit-date">{{ formatDate(commit.date) }}</span>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="commit-arrow">
                <polyline points="9 18 15 12 9 6"/>
              </svg>
            </div>
          </button>
        </div>
      </template>
    </template>

  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.skill-detail {
  height: 100%;
  display: flex;
  flex-direction: column;
}

// ── 标题 ─────────────────────────────────────────────────────────────────────

.detail-title {
  flex-shrink: 0;
  padding-bottom: 10px;
  border-bottom: 1px solid $border-color;
  display: flex;
  align-items: center;
  gap: 8px;
}

.title-left {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  gap: 0;
}

.detail-category { color: $text-muted; font-size: 13px; }
.detail-separator { color: $text-muted; margin: 0 5px; }
.detail-name { color: $text-primary; font-weight: 600; font-size: 14px; }
.detail-version {
  font-size: 11px;
  color: $text-muted;
  background: rgba(var(--accent-primary-rgb), 0.08);
  padding: 1px 6px;
  border-radius: 6px;
  font-weight: 600;
  margin-left: 6px;
}

.usage-stats {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.usage-stat {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  font-weight: 500;
  color: $text-secondary;
  svg { opacity: 0.65; }
}

.pin-toggle {
  display: inline-flex;
  align-items: center;
  border: 1px solid transparent;
  background: none;
  color: $text-muted;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  opacity: 0.5;
  transition: all $transition-fast;

  &:hover { opacity: 1; color: $accent-primary; background: rgba(var(--accent-primary-rgb), 0.08); }
  &.active { opacity: 1; color: $accent-primary; }
  &:disabled { cursor: wait; opacity: 0.3; }
}

// ── Tab ───────────────────────────────────────────────────────────────────────

.tab-bar {
  display: flex;
  gap: 2px;
  padding: 8px 0;
  border-bottom: 1px solid $border-color;
  flex-shrink: 0;
}

.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border: none;
  background: none;
  color: $text-secondary;
  font-size: 13px;
  cursor: pointer;
  border-radius: $radius-sm;
  transition: all $transition-fast;
  border-bottom: 2px solid transparent;

  &:hover { color: $text-primary; background: rgba(var(--accent-primary-rgb), 0.05); }
  &.active {
    color: var(--accent-primary);
    font-weight: 500;
    border-bottom-color: var(--accent-primary);
  }
}

.tab-count {
  background: rgba(var(--accent-primary-rgb), 0.12);
  color: var(--accent-primary);
  font-size: 10px;
  padding: 0 5px;
  border-radius: 8px;
  font-weight: 600;
}

// ── Content Tab ───────────────────────────────────────────────────────────────

.detail-loading {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-size: 13px;
  color: $text-muted;
}

.detail-breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0 10px;
  flex-shrink: 0;
}

.back-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  border: none;
  background: none;
  color: var(--accent-primary);
  font-size: 13px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  &:hover { background: rgba(var(--accent-primary-rgb), 0.06); }
}

.breadcrumb-path {
  font-size: 13px;
  color: $text-muted;
}

.detail-content {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding-bottom: 16px;
  margin-top: 10px;

  :deep(hr) { border: none; margin: 12px 0; }
}

.detail-files {
  flex-shrink: 0;
  border-top: 1px solid $border-color;
  padding-top: 10px;
  margin-top: 10px;
}

.files-header {
  font-size: 11px;
  font-weight: 600;
  color: $text-muted;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  margin-bottom: 6px;
}

.files-list { display: flex; flex-wrap: wrap; gap: 4px; }

.file-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border: 1px solid $border-color;
  border-radius: $radius-sm;
  background: $bg-secondary;
  color: $text-secondary;
  font-size: 12px;
  cursor: pointer;
  transition: all $transition-fast;
  &:hover { border-color: var(--accent-primary); color: var(--accent-primary); }
}

// ── History Tab ───────────────────────────────────────────────────────────────

.history-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: $text-muted;
  font-size: 13px;
  padding: 40px;
}

.commit-list {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  margin-top: 10px;
}

.commit-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 10px 12px;
  border: none;
  border-bottom: 1px solid $border-color;
  background: none;
  text-align: left;
  cursor: pointer;
  gap: 12px;
  transition: background $transition-fast;

  &:hover { background: rgba(var(--accent-primary-rgb), 0.04); }
  &:first-child { border-top: 1px solid $border-color; }
}

.commit-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.commit-hash {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  color: var(--accent-primary);
  background: rgba(var(--accent-primary-rgb), 0.08);
  padding: 2px 6px;
  border-radius: 4px;
  flex-shrink: 0;
}

.commit-msg {
  font-size: 13px;
  color: $text-primary;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.commit-right {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}

.commit-author {
  font-size: 12px;
  color: $text-secondary;
}

.commit-date {
  font-size: 11px;
  color: $text-muted;
  white-space: nowrap;
}

.commit-arrow {
  color: $text-muted;
  opacity: 0.5;
}

// ── Commit Detail ─────────────────────────────────────────────────────────────

.history-detail-header {
  padding: 10px 0;
  flex-shrink: 0;
}

.commit-detail-meta {
  background: rgba(var(--accent-primary-rgb), 0.03);
  border: 1px solid $border-color;
  border-radius: $radius-md;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex-shrink: 0;
  margin-bottom: 12px;
}

.meta-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  font-size: 13px;
  color: $text-primary;
}

.message-row { align-items: flex-start; }

.meta-label {
  font-size: 11px;
  font-weight: 600;
  color: $text-muted;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  width: 60px;
  flex-shrink: 0;
}

.commit-hash-full {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  color: var(--accent-primary);
}

.commit-message-text {
  font-weight: 500;
  line-height: 1.5;
}

.commit-body {
  font-size: 12px;
  color: $text-secondary;
  white-space: pre-wrap;
  padding-top: 4px;
  border-top: 1px solid $border-color;
  margin-top: 4px;
}

.diff-section {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.diff-title {
  font-size: 11px;
  font-weight: 600;
  color: $text-muted;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.diff-block {
  background: $bg-secondary;
  border: 1px solid $border-color;
  border-radius: $radius-md;
  padding: 12px;
  overflow-x: auto;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.6;
  color: $text-secondary;
  flex: 1;
  white-space: pre;

  :deep(.diff-add) { color: #4caf50; background: rgba(76, 175, 80, 0.06); }
  :deep(.diff-del) { color: #ef5350; background: rgba(239, 83, 80, 0.06); }
}
</style>
