<script setup lang="ts">
import { ref, computed } from 'vue'
import { NSwitch } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import {
  scanPath,
  importFromPath,
  fileToBase64,
  previewImport,
  importSkills,
  type PathScanItem,
  type SkillPreviewItem,
  type ImportSkillsResult,
} from '@/api/hermes/skills'

const { t } = useI18n()

const emit = defineEmits<{
  close: []
  imported: [names: string[]]
}>()

// ── 阶段 ──────────────────────────────────────────────────────────────────────
type Stage = 'select' | 'path' | 'zip' | 'preview' | 'result'
type ImportMode = 'path' | 'zip'

const stage = ref<Stage>('select')
const mode = ref<ImportMode>('path')

// ── 通用状态 ───────────────────────────────────────────────────────────────────
const loading = ref(false)
const error = ref('')
const overwrite = ref(false)
const result = ref<ImportSkillsResult | null>(null)

// ── 路径模式 ───────────────────────────────────────────────────────────────────
const pathInput = ref('')
const pathItems = ref<PathScanItem[]>([])

// ── ZIP 模式 ───────────────────────────────────────────────────────────────────
const isDragOver = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const zipData = ref('')
const zipFilename = ref('')
const zipItems = ref<SkillPreviewItem[]>([])

// ── 预览共享数据 ───────────────────────────────────────────────────────────────
// 按 category 分组（路径模式）
const categorizedItems = computed(() => {
  if (mode.value !== 'path') return []
  const map = new Map<string, PathScanItem[]>()
  for (const item of pathItems.value) {
    const cat = item.category || ''
    if (!map.has(cat)) map.set(cat, [])
    map.get(cat)!.push(item)
  }
  // 排序：先无分类，再按名称排序分类
  const entries = [...map.entries()]
  entries.sort(([a], [b]) => {
    if (!a && b) return -1
    if (a && !b) return 1
    return a.localeCompare(b)
  })
  return entries
})

const totalCount = computed(() =>
  mode.value === 'path' ? pathItems.value.length : zipItems.value.length,
)
const newCount = computed(() =>
  mode.value === 'path'
    ? pathItems.value.filter(s => !s.exists).length
    : zipItems.value.filter(s => !s.exists).length,
)
const existsCount = computed(() =>
  mode.value === 'path'
    ? pathItems.value.filter(s => s.exists).length
    : zipItems.value.filter(s => s.exists).length,
)

// ── 模式选择 ───────────────────────────────────────────────────────────────────
function selectMode(m: ImportMode) {
  mode.value = m
  error.value = ''
  if (m === 'path') stage.value = 'path'
  else stage.value = 'zip'
}

// ── 路径扫描 ───────────────────────────────────────────────────────────────────
async function doScan() {
  const p = pathInput.value.trim()
  if (!p) { error.value = t('skills.import.noPathInput'); return }
  error.value = ''
  loading.value = true
  try {
    const res = await scanPath(p)
    if (!res.skills || res.skills.length === 0) {
      error.value = t('skills.import.noSkillsInPath')
      loading.value = false
      return
    }
    pathItems.value = res.skills
    stage.value = 'preview'
  } catch (err: any) {
    error.value = err.message || t('skills.import.pathNotFound')
  } finally {
    loading.value = false
  }
}

function onPathKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter') doScan()
}

// ── ZIP 处理 ───────────────────────────────────────────────────────────────────
function onDragOver(e: DragEvent) { e.preventDefault(); isDragOver.value = true }
function onDragLeave() { isDragOver.value = false }
function onDrop(e: DragEvent) {
  e.preventDefault(); isDragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) handleZipFile(file)
}
function onFileChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) handleZipFile(file)
}
function openFilePicker() { fileInputRef.value?.click() }

async function handleZipFile(file: File) {
  if (!file.name.toLowerCase().endsWith('.zip')) {
    error.value = t('skills.import.parseError') + ': 请选择 .zip 文件'
    return
  }
  error.value = ''
  loading.value = true
  try {
    const base64 = await fileToBase64(file)
    const res = await previewImport(base64, file.name)
    if (!res.skills || res.skills.length === 0) {
      error.value = t('skills.import.noSkillsFound')
      loading.value = false
      return
    }
    zipData.value = base64
    zipFilename.value = file.name
    zipItems.value = res.skills
    stage.value = 'preview'
  } catch (err: any) {
    error.value = `${t('skills.import.parseError')}: ${err.message}`
  } finally {
    loading.value = false
  }
}

// ── 执行导入 ───────────────────────────────────────────────────────────────────
async function doImport() {
  loading.value = true
  error.value = ''
  try {
    let res: ImportSkillsResult
    if (mode.value === 'path') {
      res = await importFromPath(
        pathItems.value.map(s => ({ name: s.name, sourcePath: s.sourcePath })),
        overwrite.value,
      )
    } else {
      res = await importSkills(zipData.value, zipFilename.value, overwrite.value)
    }
    result.value = res
    stage.value = 'result'
    if (res.imported.length > 0) emit('imported', res.imported)
  } catch (err: any) {
    error.value = `导入请求失败: ${err.message}`
  } finally {
    loading.value = false
  }
}

// ── 重置 ──────────────────────────────────────────────────────────────────────
function reset() {
  stage.value = 'select'
  pathInput.value = ''
  pathItems.value = []
  zipData.value = ''
  zipFilename.value = ''
  zipItems.value = []
  overwrite.value = false
  result.value = null
  error.value = ''
  loading.value = false
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function close() { reset(); emit('close') }

function goBack() {
  error.value = ''
  if (stage.value === 'preview') stage.value = mode.value === 'path' ? 'path' : 'zip'
  else stage.value = 'select'
}
</script>

<template>
  <div class="modal-overlay" @click.self="close">
    <div class="modal-box" @click.stop>

      <!-- Header -->
      <div class="modal-header">
        <span class="modal-title">{{ t('skills.import.title') }}</span>
        <button class="close-btn" @click="close">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
          </svg>
        </button>
      </div>

      <!-- ─── Stage: select ─── -->
      <div v-if="stage === 'select'" class="modal-body">
        <p class="select-hint">{{ t('skills.import.modeSelectTitle') }}</p>
        <div class="mode-grid">
          <button class="mode-card" @click="selectMode('path')">
            <span class="mode-icon">📁</span>
            <span class="mode-name">本地目录</span>
            <span class="mode-desc">{{ t('skills.import.modePathDesc') }}</span>
          </button>
          <button class="mode-card" @click="selectMode('zip')">
            <span class="mode-icon">📦</span>
            <span class="mode-name">ZIP 文件</span>
            <span class="mode-desc">{{ t('skills.import.modeZipDesc') }}</span>
          </button>
        </div>
      </div>

      <!-- ─── Stage: path ─── -->
      <div v-else-if="stage === 'path'" class="modal-body">
        <p class="section-label">输入包含技能的目录路径（支持多层子目录结构）</p>
        <div class="path-row">
          <input
            v-model="pathInput"
            class="path-input"
            :placeholder="t('skills.import.pathPlaceholder')"
            :disabled="loading"
            @keydown="onPathKeydown"
          />
          <button class="btn btn-primary btn-scan" :disabled="loading" @click="doScan">
            <span v-if="loading" class="spinner btn-spinner" />
            {{ loading ? t('skills.import.scanning') : t('skills.import.scanBtn') }}
          </button>
        </div>
        <div class="path-tip">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
          每个包含 <code>SKILL.md</code> 的子目录会被识别为一个技能；父目录名自动作为分类。
        </div>
        <p v-if="error" class="error-msg">{{ error }}</p>
      </div>

      <!-- ─── Stage: zip ─── -->
      <div v-else-if="stage === 'zip'" class="modal-body">
        <div
          class="drop-zone"
          :class="{ 'drag-active': isDragOver, 'has-error': !!error }"
          @dragover="onDragOver"
          @dragleave="onDragLeave"
          @drop="onDrop"
          @click="openFilePicker"
        >
          <input ref="fileInputRef" type="file" accept=".zip" class="file-input-hidden" @change="onFileChange" />
          <div v-if="loading" class="drop-loading">
            <span class="spinner" />
            <span>解析 ZIP 中...</span>
          </div>
          <template v-else>
            <svg class="drop-icon" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
              <polyline points="17 8 12 3 7 8"/>
              <line x1="12" y1="3" x2="12" y2="15"/>
            </svg>
            <p class="drop-hint">{{ isDragOver ? t('skills.import.dragActive') : t('skills.import.dropZoneHint') }}</p>
            <p class="drop-accept">{{ t('skills.import.dropZoneAccept') }}</p>
          </template>
        </div>
        <p v-if="error" class="error-msg">{{ error }}</p>
      </div>

      <!-- ─── Stage: preview ─── -->
      <div v-else-if="stage === 'preview'" class="modal-body">
        <!-- 标题行 -->
        <div class="preview-header">
          <span class="preview-title">{{ t('skills.import.previewTitle', { count: totalCount }) }}</span>
          <span class="preview-stats">
            <span v-if="newCount > 0" class="badge badge-new">+{{ newCount }} 新</span>
            <span v-if="existsCount > 0" class="badge badge-exists">{{ existsCount }} 已存在</span>
          </span>
        </div>

        <!-- 路径模式：按 category 分组 -->
        <div v-if="mode === 'path'" class="preview-list">
          <template v-for="[cat, items] in categorizedItems" :key="cat">
            <div class="category-group">
              <div class="category-label">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
                {{ cat || t('skills.import.rootCategory') }}
              </div>
              <div
                v-for="item in items"
                :key="item.sourcePath"
                class="skill-preview-item"
                :class="{ 'is-exists': item.exists }"
              >
                <div class="spi-info">
                  <span class="spi-name">{{ item.name }}</span>
                  <span v-if="item.description" class="spi-desc">{{ item.description }}</span>
                </div>
                <span class="spi-badge" :class="item.exists ? 'badge-exists' : 'badge-new'">
                  {{ item.exists ? t('skills.import.existsBadge') : t('skills.import.newBadge') }}
                </span>
              </div>
            </div>
          </template>
        </div>

        <!-- ZIP 模式：扁平列表 -->
        <div v-else class="preview-list">
          <div
            v-for="item in zipItems"
            :key="item.name"
            class="skill-preview-item"
            :class="{ 'is-exists': item.exists }"
          >
            <div class="spi-info">
              <span class="spi-name">{{ item.name }}</span>
              <span v-if="item.description" class="spi-desc">{{ item.description }}</span>
            </div>
            <span class="spi-badge" :class="item.exists ? 'badge-exists' : 'badge-new'">
              {{ item.exists ? t('skills.import.existsBadge') : t('skills.import.newBadge') }}
            </span>
          </div>
        </div>

        <!-- 覆盖开关 -->
        <div v-if="existsCount > 0" class="overwrite-row">
          <NSwitch v-model:value="overwrite" size="small" />
          <div class="overwrite-label-group">
            <span class="overwrite-label">{{ t('skills.import.overwriteLabel') }}</span>
            <span class="overwrite-hint">{{ t('skills.import.overwriteHint') }}</span>
          </div>
        </div>

        <p v-if="error" class="error-msg">{{ error }}</p>
      </div>

      <!-- ─── Stage: result ─── -->
      <div v-else-if="stage === 'result' && result" class="modal-body">
        <div class="result-title">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
          </svg>
          {{ t('skills.import.resultTitle') }}
        </div>
        <div class="result-rows">
          <div v-if="result.imported.length > 0" class="result-row success">
            <span class="dot dot-success" />
            {{ t('skills.import.resultImported', { count: result.imported.length }) }}
            <span class="result-names">{{ result.imported.join(', ') }}</span>
          </div>
          <div v-if="result.skipped.length > 0" class="result-row warn">
            <span class="dot dot-warn" />
            {{ t('skills.import.resultSkipped', { count: result.skipped.length }) }}
            <span class="result-names">{{ result.skipped.join(', ') }}</span>
          </div>
          <div v-if="result.errors.length > 0" class="result-row error">
            <span class="dot dot-error" />
            {{ t('skills.import.resultErrors', { count: result.errors.length }) }}
            <details class="error-details">
              <summary>{{ t('skills.import.errorDetail') }}</summary>
              <ul>
                <li v-for="e in result.errors" :key="e.name"><b>{{ e.name }}</b>: {{ e.error }}</li>
              </ul>
            </details>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="modal-footer">
        <!-- select -->
        <template v-if="stage === 'select'">
          <button class="btn btn-ghost" @click="close">{{ t('skills.import.cancel') }}</button>
        </template>
        <!-- path -->
        <template v-else-if="stage === 'path'">
          <button class="btn btn-ghost" @click="stage = 'select'">{{ t('skills.import.back') }}</button>
          <button class="btn btn-primary" :disabled="loading" @click="doScan">
            <span v-if="loading" class="spinner btn-spinner" />
            {{ loading ? t('skills.import.scanning') : t('skills.import.scanBtn') }}
          </button>
        </template>
        <!-- zip -->
        <template v-else-if="stage === 'zip'">
          <button class="btn btn-ghost" @click="stage = 'select'">{{ t('skills.import.back') }}</button>
        </template>
        <!-- preview -->
        <template v-else-if="stage === 'preview'">
          <button class="btn btn-ghost" @click="goBack">{{ t('skills.import.back') }}</button>
          <button class="btn btn-primary" :disabled="loading" @click="doImport">
            <span v-if="loading" class="spinner btn-spinner" />
            {{ loading ? t('skills.import.importing') : t('skills.import.importBtn') }}
          </button>
        </template>
        <!-- result -->
        <template v-else-if="stage === 'result'">
          <button class="btn btn-ghost" @click="reset">{{ t('skills.import.importAgain') }}</button>
          <button class="btn btn-primary" @click="close">{{ t('skills.import.done') }}</button>
        </template>
      </div>

    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  padding: 16px;
}

.modal-box {
  background: $bg-card;
  border: 1px solid $border-color;
  border-radius: $radius-lg;
  width: 100%;
  max-width: 540px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.25);
  max-height: 88vh;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid $border-color;
  flex-shrink: 0;
}

.modal-title {
  flex: 1;
  font-size: 15px;
  font-weight: 600;
  color: $text-primary;
}

.close-btn {
  border: none;
  background: none;
  cursor: pointer;
  color: $text-muted;
  padding: 4px;
  border-radius: $radius-sm;
  display: flex;
  align-items: center;
  &:hover { color: $text-secondary; background: rgba(var(--accent-primary-rgb), 0.06); }
}

.modal-body {
  padding: 20px;
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid $border-color;
  flex-shrink: 0;
}

// ── 模式选择 ────────────────────────────────────────────────────────────────

.select-hint {
  font-size: 13px;
  color: $text-secondary;
  margin: 0 0 14px;
}

.mode-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.mode-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  padding: 16px;
  border: 1px solid $border-color;
  border-radius: $radius-md;
  background: none;
  cursor: pointer;
  text-align: left;
  transition: all $transition-fast;

  &:hover {
    border-color: rgba(var(--accent-primary-rgb), 0.4);
    background: rgba(var(--accent-primary-rgb), 0.04);
  }
}

.mode-icon {
  font-size: 22px;
  line-height: 1;
}

.mode-name {
  font-size: 13px;
  font-weight: 600;
  color: $text-primary;
}

.mode-desc {
  font-size: 12px;
  color: $text-muted;
  line-height: 1.5;
}

// ── 路径输入 ────────────────────────────────────────────────────────────────

.section-label {
  font-size: 13px;
  color: $text-secondary;
  margin: 0 0 10px;
}

.path-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.path-input {
  flex: 1;
  padding: 7px 10px;
  border: 1px solid $border-color;
  border-radius: $radius-sm;
  background: $bg-primary;
  color: $text-primary;
  font-size: 13px;
  font-family: 'Consolas', 'Monaco', monospace;
  outline: none;
  transition: border-color $transition-fast;
  min-width: 0;

  &:focus { border-color: var(--accent-primary); }
  &::placeholder { color: $text-muted; }
  &:disabled { opacity: 0.5; }
}

.btn-scan {
  flex-shrink: 0;
  white-space: nowrap;
}

.path-tip {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 10px;
  padding: 10px 12px;
  background: rgba(var(--accent-primary-rgb), 0.04);
  border: 1px solid $border-color;
  border-radius: $radius-sm;
  font-size: 12px;
  color: $text-muted;
  line-height: 1.6;

  svg { flex-shrink: 0; margin-top: 1px; }

  code {
    background: rgba(var(--accent-primary-rgb), 0.1);
    padding: 1px 4px;
    border-radius: 3px;
    font-size: 11px;
    color: $text-secondary;
  }
}

// ── Drop zone ────────────────────────────────────────────────────────────────

.drop-zone {
  border: 2px dashed $border-color;
  border-radius: $radius-lg;
  padding: 40px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  transition: all $transition-fast;

  &:hover, &.drag-active {
    border-color: var(--accent-primary);
    background: rgba(var(--accent-primary-rgb), 0.04);
  }

  &.has-error { border-color: $error; }
}

.file-input-hidden { display: none; }

.drop-icon { color: $text-muted; opacity: 0.4; }

.drop-hint {
  font-size: 14px;
  color: $text-secondary;
  margin: 0;
  text-align: center;
}

.drop-accept {
  font-size: 12px;
  color: $text-muted;
  margin: 0;
}

.drop-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: $text-muted;
  font-size: 13px;
}

// ── Preview list ─────────────────────────────────────────────────────────────

.preview-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.preview-title {
  font-size: 13px;
  font-weight: 600;
  color: $text-primary;
}

.preview-stats {
  display: flex;
  gap: 4px;
}

.badge {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 10px;
  font-weight: 500;
}

.badge-new { background: rgba(102, 187, 106, 0.15); color: #66bb6a; }
.badge-exists { background: rgba(255, 152, 0, 0.15); color: #ff9800; }

.preview-list {
  border: 1px solid $border-color;
  border-radius: $radius-md;
  overflow: hidden;
  max-height: 300px;
  overflow-y: auto;
}

.category-group {
  &:not(:first-child) { border-top: 1px solid $border-color; }
}

.category-label {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.4px;
  color: $text-muted;
  background: rgba(var(--accent-primary-rgb), 0.03);
  border-bottom: 1px solid $border-color;

  svg { opacity: 0.6; flex-shrink: 0; }
}

.skill-preview-item {
  display: flex;
  align-items: center;
  padding: 9px 12px;
  gap: 10px;
  border-bottom: 1px solid $border-color;
  transition: background $transition-fast;

  &:last-child { border-bottom: none; }
  &:hover { background: rgba(var(--accent-primary-rgb), 0.03); }
  &.is-exists { opacity: 0.8; }
}

.spi-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.spi-name {
  font-size: 13px;
  color: $text-primary;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.spi-desc {
  font-size: 11px;
  color: $text-muted;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}

.spi-badge {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 10px;
  font-weight: 500;
  flex-shrink: 0;
}

// ── Overwrite ────────────────────────────────────────────────────────────────

.overwrite-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-top: 12px;
  padding: 12px;
  background: rgba(var(--accent-primary-rgb), 0.04);
  border-radius: $radius-md;
  border: 1px solid $border-color;
}

.overwrite-label-group { display: flex; flex-direction: column; gap: 2px; }

.overwrite-label {
  font-size: 13px;
  color: $text-primary;
  font-weight: 500;
}

.overwrite-hint {
  font-size: 11px;
  color: $text-muted;
  line-height: 1.5;
}

// ── Result ───────────────────────────────────────────────────────────────────

.result-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  color: $text-primary;
  margin-bottom: 16px;

  svg { color: #66bb6a; }
}

.result-rows { display: flex; flex-direction: column; gap: 8px; }

.result-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 13px;
  flex-wrap: wrap;

  &.success { color: #66bb6a; }
  &.warn { color: #ff9800; }
  &.error { color: $error; }
}

.result-names {
  font-size: 12px;
  color: $text-muted;
  word-break: break-all;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 3px;

  &.dot-success { background: #66bb6a; }
  &.dot-warn { background: #ff9800; }
  &.dot-error { background: $error; }
}

.error-details {
  width: 100%;
  font-size: 12px;
  color: $text-secondary;
  cursor: pointer;

  ul {
    margin: 6px 0 0 16px;
    padding: 0;
    list-style: disc;
    color: $text-muted;
  }
}

// ── Error ─────────────────────────────────────────────────────────────────────

.error-msg {
  margin-top: 10px;
  font-size: 12px;
  color: $error;
}

// ── Spinner ────────────────────────────────────────────────────────────────────

.spinner {
  display: inline-block;
  width: 18px;
  height: 18px;
  border: 2px solid rgba(var(--accent-primary-rgb), 0.2);
  border-top-color: var(--accent-primary);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;

  &.btn-spinner { width: 13px; height: 13px; }
}

@keyframes spin { to { transform: rotate(360deg); } }

// ── Buttons ───────────────────────────────────────────────────────────────────

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 16px;
  border-radius: $radius-md;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all $transition-fast;

  &:disabled { opacity: 0.5; cursor: not-allowed; }
}

.btn-primary {
  background: var(--accent-primary);
  color: #fff;
  border-color: var(--accent-primary);
  &:hover:not(:disabled) { filter: brightness(1.1); }
}

.btn-ghost {
  background: none;
  color: $text-secondary;
  border-color: $border-color;
  &:hover { background: rgba(var(--accent-primary-rgb), 0.06); color: $text-primary; }
}
</style>
