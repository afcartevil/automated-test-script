<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { NInput, useMessage } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import SkillSidebar from '@/components/hermes/skills/SkillSidebar.vue'
import SkillGrid from '@/components/hermes/skills/SkillGrid.vue'
import SkillDetail from '@/components/hermes/skills/SkillDetail.vue'
import SkillImportModal from '@/components/hermes/skills/SkillImportModal.vue'
import { fetchSkills, backfillCategories, type SkillCategory, type SkillInfo } from '@/api/hermes/skills'

const { t } = useI18n()
const message = useMessage()
const categories = ref<SkillCategory[]>([])
const archived = ref<SkillInfo[]>([])
const loading = ref(false)
const backfilling = ref(false)
const selectedCategory = ref('')
const selectedSkill = ref('')
const searchQuery = ref('')
const funcTypeFilter = ref<string | null>(null)
const moduleFilter = ref<string | null>(null)
const showImportModal = ref(false)
let mobileQuery: MediaQueryList | null = null

// ── 所有技能扁平化 ─────────────────────────────────────────────────────────────
const allSkills = computed<SkillInfo[]>(() => categories.value.flatMap(c => c.skills))

// ── 功能类型列表（动态读取，固定优先顺序）──────────────────────────────────────
const funcTypes = computed<string[]>(() => {
  const set = new Set<string>()
  for (const s of allSkills.value) {
    if (s.funcType) set.add(s.funcType)
  }
  const priority = ['AI故障分析', 'AI自动化适配', 'AI自检工具']
  return [...set].sort((a, b) => {
    const ia = priority.indexOf(a), ib = priority.indexOf(b)
    if (ia >= 0 && ib >= 0) return ia - ib
    if (ia >= 0) return -1
    if (ib >= 0) return 1
    return a.localeCompare(b)
  })
})

const funcTypeCounts = computed<Record<string, number>>(() => {
  const map: Record<string, number> = {}
  for (const s of allSkills.value) {
    if (s.funcType) map[s.funcType] = (map[s.funcType] ?? 0) + 1
  }
  return map
})

// ── 当前侧边栏显示的 skills（按 funcType 过滤，供模块分组用）─────────────────
const sidebarSkills = computed<SkillInfo[]>(() => {
  if (!funcTypeFilter.value) return allSkills.value
  return allSkills.value.filter(s => s.funcType === funcTypeFilter.value)
})

// ── 选中技能的完整数据 ────────────────────────────────────────────────────────
const selectedSkillData = computed<SkillInfo | null>(() => {
  if (!selectedCategory.value || !selectedSkill.value) return null
  if (selectedCategory.value === '.archive') {
    return archived.value.find(s => s.name === selectedSkill.value) ?? null
  }
  const cat = categories.value.find(c => c.name === selectedCategory.value)
  return cat?.skills.find(s => s.name === selectedSkill.value) ?? null
})

onMounted(() => {
  mobileQuery = window.matchMedia('(max-width: 768px)')
  mobileQuery.addEventListener('change', () => {})
  loadSkills()
})

onUnmounted(() => {
  mobileQuery?.removeEventListener('change', () => {})
})

async function loadSkills() {
  loading.value = true
  try {
    const data = await fetchSkills()
    categories.value = data.categories
    archived.value = data.archived
  } catch (err: any) {
    console.error('Failed to load skills:', err)
  } finally {
    loading.value = false
  }
}

function setFuncTypeFilter(ft: string | null) {
  funcTypeFilter.value = ft
  moduleFilter.value = null
  selectedCategory.value = ''
  selectedSkill.value = ''
}

function handleSelect(skillName: string) {
  // Find which category this skill belongs to
  for (const cat of categories.value) {
    const found = cat.skills.find(s => s.name === skillName)
    if (found) {
      if (selectedCategory.value === cat.name && selectedSkill.value === skillName) {
        // Deselect
        selectedCategory.value = ''
        selectedSkill.value = ''
      } else {
        selectedCategory.value = cat.name
        selectedSkill.value = skillName
      }
      return
    }
  }
  // Fallback: check archived
  const arc = archived.value.find(s => s.name === skillName)
  if (arc) {
    selectedCategory.value = '.archive'
    selectedSkill.value = skillName
  }
}

function handleClose() {
  selectedCategory.value = ''
  selectedSkill.value = ''
}

function handleImported(_names: string[]) {
  loadSkills()
}

function handlePinToggled(name: string, pinned: boolean) {
  if (selectedCategory.value === '.archive') {
    const skill = archived.value.find(s => s.name === name)
    if (skill) skill.pinned = pinned
  } else {
    const cat = categories.value.find(c => c.name === selectedCategory.value)
    const skill = cat?.skills.find(s => s.name === name)
    if (skill) skill.pinned = pinned
  }
}

async function handleBackfill() {
  if (backfilling.value) return
  backfilling.value = true
  try {
    const res = await backfillCategories()
    message.success(res.message)
    if (res.updated.length > 0) {
      await loadSkills()
    }
  } catch (err: any) {
    message.error(`回填失败: ${err.message}`)
  } finally {
    backfilling.value = false
  }
}
</script>

<template>
  <div class="skills-view">

    <!-- ── 顶部工具栏 ──────────────────────────────────────────────────────── -->
    <header class="page-header">
      <div class="header-left">
        <h2 class="header-title">{{ t('skills.title') }}</h2>
      </div>

      <!-- 功能类型 Tab 过滤 -->
      <div class="func-type-tabs">
        <button
          class="func-tab"
          :class="{ active: funcTypeFilter === null }"
          @click="setFuncTypeFilter(null)"
        >
          全部
          <span class="tab-badge">{{ allSkills.length }}</span>
        </button>
        <button
          v-for="ft in funcTypes"
          :key="ft"
          class="func-tab"
          :class="{ active: funcTypeFilter === ft }"
          @click="setFuncTypeFilter(ft)"
        >
          {{ ft }}
          <span class="tab-badge">{{ funcTypeCounts[ft] ?? 0 }}</span>
        </button>
      </div>

      <div class="header-right">
        <button class="import-btn backfill-btn" :disabled="backfilling" :title="backfilling ? '回填中...' : '一键为所有 skill 补充 funcType/category 分类字段'" @click="handleBackfill">
          <svg v-if="!backfilling" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 4h6v6H4z"/><path d="M14 4h6v6h-6z"/><path d="M4 14h6v6H4z"/>
            <path d="M17 14v6m-3-3h6"/>
          </svg>
          <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation: spin 1s linear infinite">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
          </svg>
          修复分类
        </button>
        <button class="import-btn" @click="showImportModal = true">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/>
            <line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          {{ t('skills.import.button') }}
        </button>
        <NInput
          v-model:value="searchQuery"
          :placeholder="t('skills.searchPlaceholder')"
          size="small"
          clearable
          style="width: 160px"
        />
      </div>
    </header>

    <!-- 批量导入模态框 -->
    <SkillImportModal
      v-if="showImportModal"
      @close="showImportModal = false"
      @imported="handleImported"
    />

    <!-- ── 三栏主体 ────────────────────────────────────────────────────────── -->
    <div class="skills-body">
      <div v-if="loading && categories.length === 0" class="skills-loading">
        {{ t('common.loading') }}
      </div>
      <template v-else>

        <!-- 左侧：模块导航侧边栏 -->
        <SkillSidebar
          :skills="sidebarSkills"
          :module-filter="moduleFilter"
          :func-type-filter="funcTypeFilter"
          @set-module="moduleFilter = $event"
        />

        <!-- 中间：技能卡片网格 -->
        <SkillGrid
          :skills="allSkills"
          :selected-skill="selectedCategory && selectedSkill ? `${selectedCategory}/${selectedSkill}` : null"
          :func-type-filter="funcTypeFilter"
          :module-filter="moduleFilter"
          :search-query="searchQuery"
          @select="handleSelect"
        />

        <!-- 右侧：技能详情抽屉 -->
        <transition name="drawer">
          <div v-if="selectedCategory && selectedSkill" class="detail-drawer">
            <div class="drawer-header">
              <span class="drawer-title">{{ selectedSkill }}</span>
              <button class="drawer-close" @click="handleClose" title="关闭">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
            <div class="drawer-body">
              <SkillDetail
                :category="selectedCategory"
                :skill="selectedSkill"
                :skill-name="selectedSkillData?.name || selectedSkill"
                :version="selectedSkillData?.version"
                :updated-at="selectedSkillData?.updatedAt"
                :patch-count="selectedSkillData?.patchCount"
                :use-count="selectedSkillData?.useCount"
                :view-count="selectedSkillData?.viewCount"
                :pinned="selectedSkillData?.pinned"
                @pin-toggled="handlePinToggled"
              />
            </div>
          </div>
        </transition>

      </template>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.skills-view {
  height: calc(100 * var(--vh));
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

// ── 顶部工具栏 ────────────────────────────────────────────────────────────────

.page-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid $border-color;
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.header-title {
  font-size: 15px;
  font-weight: 600;
  color: $text-primary;
  white-space: nowrap;
}

// ── 功能类型 Tab ──────────────────────────────────────────────────────────────

.func-type-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1;
  min-width: 0;
  overflow-x: auto;
  scrollbar-width: none;
  &::-webkit-scrollbar { display: none; }
}

.func-tab {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border: 1px solid transparent;
  border-radius: 20px;
  background: none;
  color: $text-secondary;
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: all $transition-fast;

  &:hover {
    color: $text-primary;
    background: rgba(var(--accent-info-rgb), 0.06);
    border-color: rgba(var(--accent-info-rgb), 0.15);
  }

  &.active {
    color: var(--accent-info);
    background: rgba(var(--accent-info-rgb), 0.1);
    border-color: rgba(var(--accent-info-rgb), 0.3);
    font-weight: 600;
  }
}

.tab-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 600;
  color: inherit;
  opacity: 0.7;
  background: rgba(0, 0, 0, 0.06);
  padding: 0 5px;
  border-radius: 8px;
  min-width: 18px;
  height: 16px;

  .active & {
    background: rgba(var(--accent-info-rgb), 0.15);
    opacity: 1;
  }
}

// ── 右侧工具 ──────────────────────────────────────────────────────────────────

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.import-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border: 1px solid $border-color;
  border-radius: $radius-sm;
  background: none;
  color: $text-secondary;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  transition: all $transition-fast;

  &:hover {
    color: $text-primary;
    background: rgba(var(--accent-info-rgb), 0.06);
    border-color: rgba(var(--accent-info-rgb), 0.3);
  }

  &:disabled {
    opacity: 0.5;
    cursor: wait;
  }
}

.backfill-btn {
  color: $text-muted;
  &:hover {
    color: #3fb950;
    background: rgba(63, 185, 80, 0.06);
    border-color: rgba(63, 185, 80, 0.3);
  }
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}

// ── 三栏布局 ──────────────────────────────────────────────────────────────────

.skills-body {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
  position: relative;
}

.skills-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: $text-muted;
}

// ── 右侧详情抽屉 ──────────────────────────────────────────────────────────────

.detail-drawer {
  width: 360px;
  flex-shrink: 0;
  border-left: 1px solid $border-color;
  background: $bg-sidebar;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.drawer-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px 10px;
  border-bottom: 1px solid $border-color;
  flex-shrink: 0;
}

.drawer-title {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  color: $text-primary;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.drawer-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  background: none;
  color: $text-muted;
  cursor: pointer;
  border-radius: 4px;
  flex-shrink: 0;
  transition: all $transition-fast;

  &:hover {
    color: $text-primary;
    background: rgba(var(--accent-info-rgb), 0.08);
  }
}

.drawer-body {
  flex: 1;
  overflow: hidden;
  padding: 0 16px 16px;
  display: flex;
  flex-direction: column;
  min-height: 0;

  // SkillDetail 内部顶部标题区在抽屉里隐藏，已由 drawer-header 代替
  :deep(.detail-title) {
    display: none;
  }
}

// ── 抽屉滑入动画 ──────────────────────────────────────────────────────────────

.drawer-enter-active,
.drawer-leave-active {
  transition: width $transition-fast, opacity $transition-fast;
  overflow: hidden;
}

.drawer-enter-from,
.drawer-leave-to {
  width: 0;
  opacity: 0;
}

.drawer-enter-to,
.drawer-leave-from {
  width: 360px;
  opacity: 1;
}

// ── 移动端适配 ────────────────────────────────────────────────────────────────

@media (max-width: $breakpoint-mobile) {
  .func-type-tabs { display: none; }

  .detail-drawer {
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
    z-index: 20;
    box-shadow: -4px 0 16px rgba(0, 0, 0, 0.15);
  }
}
</style>
