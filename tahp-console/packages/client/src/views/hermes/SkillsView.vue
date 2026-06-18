<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { NInput, useMessage } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import EaPageHead from '@/components/layout/EaPageHead.vue'
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
const isFullscreen = ref(false)
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
    categories.value = data.categories ?? []
    archived.value = data.archived ?? []
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
        selectedCategory.value = ''
        selectedSkill.value = ''
        isFullscreen.value = false
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
  isFullscreen.value = false
}

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value
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
  <div class="skills-view page page-wide">

    <EaPageHead
      :title="t('skills.title')"
      subtitle="业务规则与执行规范的载体 · 适配 / 诊断 Agent 按 Skill SOP 执行"
    >
      <template #actions>
        <button
          type="button"
          class="ea-btn-ghost ea-btn-sm backfill-btn"
          :disabled="backfilling"
          :title="backfilling ? '回填中...' : '一键为所有 skill 补充 funcType/category 分类字段'"
          @click="handleBackfill"
        >
          <svg v-if="!backfilling" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 4h6v6H4z"/><path d="M14 4h6v6h-6z"/><path d="M4 14h6v6H4z"/>
            <path d="M17 14v6m-3-3h6"/>
          </svg>
          <svg v-else width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="spin-icon">
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
          </svg>
          修复分类
        </button>
        <button type="button" class="ea-btn-primary ea-btn-sm" @click="showImportModal = true">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="17 8 12 3 7 8"/>
            <line x1="12" y1="3" x2="12" y2="15"/>
          </svg>
          {{ t('skills.import.button') }}
        </button>
      </template>
    </EaPageHead>

    <!-- 功能类型 domain-chip 过滤 -->
    <div class="ea-domain-bar skills-domain-bar">
      <button
        type="button"
        class="ea-domain-chip"
        :class="{ active: funcTypeFilter === null }"
        @click="setFuncTypeFilter(null)"
      >
        全部
        <span class="chip-cnt">{{ allSkills.length }}</span>
      </button>
      <button
        v-for="ft in funcTypes"
        :key="ft"
        type="button"
        class="ea-domain-chip"
        :class="{ active: funcTypeFilter === ft }"
        @click="setFuncTypeFilter(ft)"
      >
        {{ ft }}
        <span class="chip-cnt">{{ funcTypeCounts[ft] ?? 0 }}</span>
      </button>
    </div>

    <!-- 搜索栏 -->
    <div class="skill-search">
      <NInput
        v-model:value="searchQuery"
        :placeholder="t('skills.searchPlaceholder')"
        clearable
        class="skill-search-input"
      />
    </div>

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

        <!-- 右侧：技能详情预览 / 全屏 -->
        <transition name="drawer">
          <div
            v-if="selectedCategory && selectedSkill"
            class="skill-detail-panel"
            :class="{ 'is-fullscreen': isFullscreen }"
          >
            <div class="panel-header">
              <span class="panel-title">{{ selectedSkill }}</span>
              <button
                type="button"
                class="panel-action"
                :title="isFullscreen ? '退出全屏' : '全屏查看'"
                @click="toggleFullscreen"
              >
                <svg v-if="!isFullscreen" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="15 3 21 3 21 9"/>
                  <polyline points="9 21 3 21 3 15"/>
                  <line x1="21" y1="3" x2="14" y2="10"/>
                  <line x1="3" y1="21" x2="10" y2="14"/>
                </svg>
                <svg v-else width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="4 14 10 14 10 20"/>
                  <polyline points="20 10 14 10 14 4"/>
                  <line x1="14" y1="10" x2="21" y2="3"/>
                  <line x1="3" y1="21" x2="10" y2="14"/>
                </svg>
              </button>
              <button type="button" class="panel-close" title="关闭" @click="handleClose">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                </svg>
              </button>
            </div>
            <div class="panel-body">
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
.skills-view {
  height: calc(100 * var(--vh) - 80px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.skills-domain-bar {
  flex-shrink: 0;
  margin-bottom: 0;
  padding-bottom: 4px;
}

.chip-cnt {
  font-size: 11px;
  font-weight: 700;
  color: var(--muted);
  background: var(--surface-2);
  padding: 1px 7px;
  border-radius: 999px;
  min-width: 18px;
  text-align: center;

  .ea-domain-chip.active & {
    background: color-mix(in srgb, var(--accent) 18%, transparent);
    color: var(--accent);
  }
}

.skill-search {
  display: flex;
  gap: 10px;
  margin-bottom: 14px;
  flex-shrink: 0;
}

.skill-search-input {
  flex: 1;
  max-width: 360px;
}

.backfill-btn:not(:disabled):hover {
  color: var(--success);
  border-color: color-mix(in srgb, var(--success) 35%, transparent);
  background: var(--success-soft);
}

.spin-icon {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.skills-body {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
  position: relative;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: var(--surface);
  box-shadow: var(--shadow);
}

.skills-loading {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  color: var(--muted);
}

// ── V26 skill-grid overrides (child component) ───────────────────────────────

.skills-body :deep(.skill-grid-wrap) {
  padding: 12px 16px 16px;
}

.skills-body :deep(.grid-context-bar) {
  padding: 8px 2px 10px;
}

.skills-body :deep(.ctx-breadcrumb) {
  font-size: 12px;
  font-weight: 700;
  color: var(--text);
}

.skills-body :deep(.ctx-count) {
  font-size: 11.5px;
  color: var(--muted);

  b { color: var(--text); font-weight: 700; }
}

.skills-body :deep(.skill-grid) {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 14px;
  align-content: start;
}

.skills-body :deep(.skill-card) {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 16px;
  padding: 18px;
  cursor: pointer;
  transition: all 0.18s;
  box-shadow: none;

  &:hover {
    transform: translateY(-3px);
    box-shadow: var(--shadow-lg);
    border-color: var(--line-strong);
  }

  &.active {
    border-color: var(--accent);
    background: var(--accent-soft);
    transform: none;
  }
}

.skills-body :deep(.card-glow-bar) {
  display: none;
}

.skills-body :deep(.card-name) {
  font-family: var(--font-code, 'JetBrains Mono', monospace);
  font-size: 14px;
  font-weight: 700;
  color: var(--accent);
}

.skills-body :deep(.card-desc) {
  font-size: 12.5px;
  color: var(--muted);
  line-height: 1.55;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.skills-body :deep(.grid-empty) {
  color: var(--muted);
}

// ── 右侧详情预览 / 全屏 ──────────────────────────────────────────────────────

.skill-detail-panel {
  width: 360px;
  flex-shrink: 0;
  border-left: 1px solid var(--line);
  background: var(--bg);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  transition: width 0.22s ease, box-shadow 0.22s ease, border-radius 0.22s ease;

  &.is-fullscreen {
    position: fixed;
    inset: 0;
    z-index: 1000;
    width: 100%;
    border-left: none;
    border-radius: 0;
    box-shadow: none;
    background: var(--surface);
  }
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px 10px;
  border-bottom: 1px solid var(--line);
  flex-shrink: 0;
  background: var(--bg);

  .is-fullscreen & {
    padding: 16px 24px 12px;
    max-width: 1080px;
    width: 100%;
    margin: 0 auto;
    box-sizing: border-box;
    background: transparent;
  }
}

.panel-title {
  flex: 1;
  font-size: 13px;
  font-weight: 700;
  color: var(--head);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;

  .is-fullscreen & {
    font-size: 15px;
  }
}

.panel-action,
.panel-close {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid var(--line);
  border-radius: 9px;
  background: var(--surface);
  color: var(--muted);
  cursor: pointer;
  flex-shrink: 0;
  transition: all 0.18s;

  &:hover {
    color: var(--accent);
    border-color: var(--accent);
    background: var(--accent-soft);
  }
}

.panel-body {
  flex: 1;
  overflow: hidden;
  padding: 0 16px 16px;
  display: flex;
  flex-direction: column;
  min-height: 0;

  :deep(.detail-title) {
    display: none;
  }

  .is-fullscreen & {
    padding: 0 24px 32px;
    max-width: 1080px;
    width: 100%;
    margin: 0 auto;
    box-sizing: border-box;

    :deep(.detail-title) {
      display: flex;
    }
  }
}

.drawer-enter-active,
.drawer-leave-active {
  transition: width 0.2s, opacity 0.2s;
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

@media (max-width: 1100px) {
  .skills-body :deep(.skill-grid) {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 768px) {
  .skills-domain-bar { display: none; }

  .skills-body :deep(.skill-grid) {
    grid-template-columns: 1fr;
  }

  .skill-detail-panel {
    position: absolute;
    right: 0;
    top: 0;
    bottom: 0;
    z-index: 20;
    box-shadow: var(--shadow-lg);

    &.is-fullscreen {
      position: fixed;
      inset: 0;
      z-index: 1000;
      box-shadow: none;
    }
  }
}

@media (max-width: 720px) {
  .skill-search-input { max-width: none; }
}
</style>
