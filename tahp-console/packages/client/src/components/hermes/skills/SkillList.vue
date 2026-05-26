<script setup lang="ts">
import { ref, computed } from 'vue'
import { NSwitch, useMessage } from 'naive-ui'
import type { SkillCategory, SkillSource, SkillInfo } from '@/api/hermes/skills'
import { toggleSkill } from '@/api/hermes/skills'
import { useI18n } from 'vue-i18n'

type SourceFilter = SkillSource | 'modified'

const { t } = useI18n()
const message = useMessage()

const props = defineProps<{
  categories: SkillCategory[]
  archived: SkillInfo[]
  selectedSkill: string | null
  searchQuery: string
  sourceFilter: SourceFilter | null
  funcTypeFilter: string | null   // null = 全部，非 null = 仅该功能类型
}>()

const emit = defineEmits<{
  select: [category: string, skill: string]
}>()

const togglingSkills = ref<Set<string>>(new Set())
const archiveCollapsed = ref(true)

// ── 最近更新（7天内）──────────────────────────────────────────────────────────
const RECENT_MS = 7 * 24 * 60 * 60 * 1000

const allSkills = computed<SkillInfo[]>(() => {
  return props.categories.flatMap(c => c.skills)
})

// 经过功能类型过滤后的技能集
const filteredSkills = computed<SkillInfo[]>(() => {
  if (!props.funcTypeFilter) return allSkills.value
  return allSkills.value.filter(s => s.funcType === props.funcTypeFilter)
})

const recentSkills = computed<SkillInfo[]>(() => {
  const now = Date.now()
  return filteredSkills.value
    .filter(s => s.updatedAt && (now - s.updatedAt) <= RECENT_MS)
    .sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0))
    .filter(s => matchesSearch(s))
})

// ── 按业务模块分组（group 字段 = 内核/驱动/通信/功耗）────────────────────────
const groupedSkills = computed(() => {
  const map = new Map<string, SkillInfo[]>()
  for (const skill of filteredSkills.value) {
    if (!matchesSearch(skill)) continue
    const g = skill.group || ''
    if (!map.has(g)) map.set(g, [])
    map.get(g)!.push(skill)
  }
  // 排序：有分组按名称排，无分组放最后
  const entries = [...map.entries()]
  entries.sort(([a], [b]) => {
    if (!a && b) return 1
    if (a && !b) return -1
    return a.localeCompare(b)
  })
  return entries
})

const collapsedGroups = ref<Set<string>>(new Set())

function toggleGroup(key: string) {
  if (collapsedGroups.value.has(key)) collapsedGroups.value.delete(key)
  else collapsedGroups.value.add(key)
}

function matchesSearch(skill: SkillInfo): boolean {
  if (!props.searchQuery) return true
  const q = props.searchQuery.toLowerCase()
  return skill.name.toLowerCase().includes(q) || (skill.description ?? '').toLowerCase().includes(q)
}

function groupLabel(g: string): string {
  return g || t('skills.noGroup')
}

function relativeTime(ts: number): string {
  const diff = Date.now() - ts
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins} 分钟前`
  const hours = Math.floor(diff / 3600000)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.floor(diff / 86400000)
  return `${days} 天前`
}

function skillKey(catName: string, skill: SkillInfo): string {
  return `${catName}/${skill.name}`
}

function accessCategory(_skill: SkillInfo): string {
  return 'tahp-project'
}

function handleSelect(catName: string, skillName: string) {
  emit('select', catName, skillName)
}

async function handleToggle(catName: string, skillName: string, newEnabled: boolean) {
  if (togglingSkills.value.has(skillName)) return
  togglingSkills.value.add(skillName)
  try {
    await toggleSkill(skillName, newEnabled)
    const cat = props.categories.find(c => c.name === catName)
    const skill = cat?.skills.find(s => s.name === skillName)
    if (skill) skill.enabled = newEnabled
  } catch (err: any) {
    message.error(t('skills.toggleFailed') + `: ${err.message}`)
  } finally {
    togglingSkills.value.delete(skillName)
  }
}
</script>

<template>
  <div class="skill-list">

    <!-- ── 最近更新 ────────────────────────────────────────────────────────── -->
    <div v-if="recentSkills.length > 0" class="recent-section">
      <div class="section-header recent-header">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
        </svg>
        <span>{{ t('skills.recentlyUpdated') }}</span>
        <span class="section-count">{{ recentSkills.length }}</span>
      </div>
      <button
        v-for="skill in recentSkills"
        :key="'recent/' + skill.name"
        class="skill-item recent-item"
        :class="{ active: selectedSkill === skillKey('tahp-project', skill) }"
        @click="handleSelect(accessCategory(skill), skill.name)"
      >
        <div class="skill-info">
          <span class="skill-name">
            <span class="source-dot dot-tahp" />
            {{ skill.name }}
            <span v-if="skill.version" class="version-badge">v{{ skill.version }}</span>
          </span>
          <span v-if="skill.description" class="skill-desc">{{ skill.description }}</span>
        </div>
        <span v-if="skill.updatedAt" class="skill-time">{{ relativeTime(skill.updatedAt) }}</span>
      </button>
    </div>

    <div v-if="recentSkills.length > 0 && groupedSkills.length > 0" class="divider" />

    <!-- ── 无结果 ───────────────────────────────────────────────────────────── -->
    <div v-if="groupedSkills.length === 0 && recentSkills.length === 0" class="skill-empty">
      {{ searchQuery ? t('skills.noMatch') : t('skills.noSkills') }}
    </div>

    <!-- ── 业务分组 ────────────────────────────────────────────────────────── -->
    <div v-for="[group, skills] in groupedSkills" :key="group || '__nogroup__'" class="skill-category">
      <button class="category-header" @click="toggleGroup(group)">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
          class="category-arrow" :class="{ collapsed: collapsedGroups.has(group) }">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" class="group-icon">
          <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
        </svg>
        <span class="category-name">{{ groupLabel(group) }}</span>
        <span class="category-count">{{ skills.length }}</span>
      </button>
      <div v-if="!collapsedGroups.has(group)" class="category-skills">
        <button
          v-for="skill in skills"
          :key="skillKey('tahp-project', skill)"
          class="skill-item"
          :class="{ active: selectedSkill === skillKey('tahp-project', skill) }"
          @click="handleSelect(accessCategory(skill), skill.name)"
        >
          <div class="skill-info">
            <span class="skill-name">
              <span class="source-dot dot-tahp" />
              {{ skill.name }}
              <span v-if="skill.version" class="version-badge">v{{ skill.version }}</span>
            </span>
            <span v-if="skill.description" class="skill-desc">{{ skill.description }}</span>
          </div>
          <div class="skill-right">
            <span v-if="skill.updatedAt" class="skill-time">{{ relativeTime(skill.updatedAt) }}</span>
            <NSwitch
              size="small"
              :value="skill.enabled !== false"
              :loading="togglingSkills.has(skill.name)"
              @update:value="handleToggle('tahp-project', skill.name, $event)"
              @click.stop
            />
          </div>
        </button>
      </div>
    </div>

    <!-- ── 已归档 ──────────────────────────────────────────────────────────── -->
    <div v-if="archived.length > 0" class="skill-category archive-section">
      <button class="category-header archive-header" @click="archiveCollapsed = !archiveCollapsed">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
          class="category-arrow" :class="{ collapsed: archiveCollapsed }">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
        <span class="category-name">{{ t('skills.archived') }}</span>
        <span class="category-count">{{ archived.length }}</span>
      </button>
      <div v-if="!archiveCollapsed" class="category-skills">
        <button
          v-for="skill in archived"
          :key="skillKey('.archive', skill)"
          class="skill-item skill-archived"
          :class="{ active: selectedSkill === skillKey('.archive', skill) }"
          @click="handleSelect('.archive', skill.name)"
        >
          <div class="skill-info">
            <span class="skill-name">
              <span class="source-dot dot-tahp" />{{ skill.name }}
            </span>
            <span v-if="skill.description" class="skill-desc">{{ skill.description }}</span>
          </div>
        </button>
      </div>
    </div>

  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.skill-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.skill-empty {
  padding: 24px 16px;
  font-size: 13px;
  color: $text-muted;
  text-align: center;
}

// ── 最近更新 ─────────────────────────────────────────────────────────────────

.recent-section { margin-bottom: 2px; }

.section-header {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.recent-header {
  color: var(--accent-primary);
}

.section-count {
  margin-left: auto;
  font-size: 11px;
  color: $text-muted;
  background: rgba(var(--accent-primary-rgb), 0.08);
  padding: 1px 6px;
  border-radius: 8px;
  font-weight: 500;
}

.recent-item {
  border-left: 2px solid rgba(var(--accent-primary-rgb), 0.3);
  padding-left: 26px !important;
  &.active { border-left-color: var(--accent-primary); }
}

.divider {
  height: 1px;
  background: $border-color;
  margin: 8px 10px;
}

// ── 分组 ─────────────────────────────────────────────────────────────────────

.skill-category { margin-bottom: 2px; }

.category-header {
  display: flex;
  align-items: center;
  gap: 5px;
  width: 100%;
  padding: 6px 10px;
  border: none;
  background: none;
  color: $text-secondary;
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  cursor: pointer;
  border-radius: $radius-sm;
  &:hover { background: rgba(var(--accent-primary-rgb), 0.04); }
}

.category-arrow {
  flex-shrink: 0;
  transition: transform $transition-fast;
  &.collapsed { transform: rotate(-90deg); }
}

.group-icon { flex-shrink: 0; opacity: 0.45; }

.category-name {
  flex: 1;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.category-count {
  font-size: 11px;
  color: $text-muted;
  background: rgba(var(--accent-primary-rgb), 0.06);
  padding: 1px 6px;
  border-radius: 8px;
}

.category-skills { padding: 2px 0 4px; }

// ── 技能条目 ──────────────────────────────────────────────────────────────────

.skill-item {
  display: flex;
  flex-direction: row;
  align-items: center;
  width: 100%;
  padding: 7px 10px 7px 28px;
  border: none;
  background: none;
  color: $text-secondary;
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  border-radius: $radius-sm;
  transition: all $transition-fast;
  gap: 6px;

  &:hover { background: rgba(var(--accent-primary-rgb), 0.06); color: $text-primary; }
  &.active { background: rgba(var(--accent-primary-rgb), 0.1); color: $text-primary; font-weight: 500; }
}

.source-dot {
  display: inline-block;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-right: 5px;
  flex-shrink: 0;
  vertical-align: middle;
}

.dot-tahp { background: #ff9800; }

.skill-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.skill-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  display: flex;
  align-items: center;
  gap: 4px;
}

.version-badge {
  font-size: 10px;
  color: $text-muted;
  background: rgba(var(--accent-primary-rgb), 0.08);
  padding: 1px 5px;
  border-radius: 4px;
  font-weight: 600;
  flex-shrink: 0;
}

.skill-desc {
  font-size: 11px;
  color: $text-muted;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 1px;
}

.skill-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.skill-time {
  font-size: 10px;
  color: $text-muted;
  white-space: nowrap;
}

// ── 归档 ─────────────────────────────────────────────────────────────────────

.archive-section {
  margin-top: 12px;
  padding-top: 8px;
  border-top: 1px solid $border-color;
}

.archive-header { color: $text-muted; }

.skill-archived {
  opacity: 0.6;
  padding-left: 28px;
}
</style>
