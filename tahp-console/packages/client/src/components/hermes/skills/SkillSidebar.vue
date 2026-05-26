<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { SkillInfo } from '@/api/hermes/skills'

const { t } = useI18n()

const props = defineProps<{
  skills: SkillInfo[]          // 当前功能类型下所有技能
  moduleFilter: string | null
  funcTypeFilter: string | null
}>()

const emit = defineEmits<{
  setModule: [module: string | null]
}>()

// ── 最近更新（7天内，最多 5 条）──────────────────────────────────────────────
const RECENT_MS = 7 * 24 * 60 * 60 * 1000

const recentSkills = computed<SkillInfo[]>(() => {
  const now = Date.now()
  return props.skills
    .filter(s => s.updatedAt && (now - s.updatedAt) <= RECENT_MS)
    .sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0))
    .slice(0, 6)
})

// ── 业务模块分组（按 group 字段）────────────────────────────────────────────
const MODULE_ORDER = ['通信', '驱动', '内核', '功耗', '通用']

const modules = computed(() => {
  const map: Record<string, number> = {}
  for (const s of props.skills) {
    const g = s.group || '通用'
    map[g] = (map[g] ?? 0) + 1
  }
  const entries = Object.entries(map)
  entries.sort(([a], [b]) => {
    const ia = MODULE_ORDER.indexOf(a)
    const ib = MODULE_ORDER.indexOf(b)
    if (ia >= 0 && ib >= 0) return ia - ib
    if (ia >= 0) return -1
    if (ib >= 0) return 1
    return a.localeCompare(b)
  })
  return entries
})

function relativeTime(ts: number): string {
  const diff = Date.now() - ts
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins}分钟前`
  const hours = Math.floor(diff / 3600000)
  if (hours < 24) return `${hours}小时前`
  return `${Math.floor(diff / 86400000)}天前`
}

const MODULE_DOT: Record<string, string> = {
  '通信': '#388bfd',
  '驱动': '#3fb950',
  '内核': '#e3b341',
  '功耗': '#f78166',
  '通用': '#8b949e',
}
function dotColor(name: string): string {
  return MODULE_DOT[name] ?? '#8b949e'
}
</script>

<template>
  <div class="skill-sidebar">

    <!-- ── 最近更新 ──────────────────────────────────────────────────────── -->
    <div v-if="recentSkills.length > 0" class="sidebar-section">
      <div class="section-label">
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
        </svg>
        最近更新
      </div>
      <button
        v-for="skill in recentSkills"
        :key="'recent/' + skill.name"
        class="recent-item"
      >
        <span class="recent-pulse"></span>
        <span class="recent-name">{{ skill.name }}</span>
        <span class="recent-time">{{ relativeTime(skill.updatedAt!) }}</span>
      </button>
    </div>

    <div v-if="recentSkills.length > 0" class="section-divider" />

    <!-- ── 业务模块 ──────────────────────────────────────────────────────── -->
    <div class="sidebar-section">
      <div class="section-label">业务模块</div>

      <!-- 全部 -->
      <button
        class="module-item"
        :class="{ active: moduleFilter === null }"
        @click="emit('setModule', null)"
      >
        <div class="module-dot" style="background: #8b949e; box-shadow: none;" />
        <span class="module-name">全部</span>
        <span class="module-count">{{ skills.length }}</span>
      </button>

      <button
        v-for="[name, count] in modules"
        :key="name"
        class="module-item"
        :class="{ active: moduleFilter === name }"
        @click="emit('setModule', moduleFilter === name ? null : name)"
      >
        <div class="module-dot" :style="{ background: dotColor(name), boxShadow: moduleFilter === name ? `0 0 6px ${dotColor(name)}` : 'none' }" />
        <span class="module-name">{{ name }}</span>
        <span class="module-count" :class="{ 'active-count': moduleFilter === name }">{{ count }}</span>
      </button>
    </div>

  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.skill-sidebar {
  width: 200px;
  flex-shrink: 0;
  background: $bg-sidebar;
  border-right: 1px solid $border-color;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  padding: 8px 0 16px;
}

// ── Section ───────────────────────────────────────────────────────────────────

.sidebar-section {
  padding: 8px 0 4px;
}

.section-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.7px;
  color: $text-muted;
  padding: 0 12px 6px;
}

.section-divider {
  height: 1px;
  background: $border-color;
  margin: 4px 12px 8px;
}

// ── 最近更新 ──────────────────────────────────────────────────────────────────

.recent-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  width: 100%;
  border: none;
  background: none;
  cursor: pointer;
  transition: background $transition-fast;
  text-align: left;

  &:hover { background: rgba(var(--accent-info-rgb), 0.05); }
}

.recent-pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-info);
  flex-shrink: 0;
  box-shadow: 0 0 5px var(--accent-info);
  animation: pulse 2s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 5px var(--accent-info); }
  50% { opacity: 0.6; box-shadow: 0 0 2px var(--accent-info); }
}

.recent-name {
  font-size: 11.5px;
  color: $text-secondary;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.recent-time {
  font-size: 10px;
  color: $text-muted;
  white-space: nowrap;
  flex-shrink: 0;
}

// ── 业务模块 ──────────────────────────────────────────────────────────────────

.module-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 7px 12px;
  width: 100%;
  border: none;
  background: none;
  cursor: pointer;
  position: relative;
  transition: background $transition-fast;
  text-align: left;

  &:hover { background: rgba(var(--accent-info-rgb), 0.05); }

  &.active {
    background: rgba(var(--accent-info-rgb), 0.08);

    &::before {
      content: '';
      position: absolute;
      left: 0;
      top: 5px;
      bottom: 5px;
      width: 2.5px;
      background: var(--accent-info);
      border-radius: 0 2px 2px 0;
    }
  }
}

.module-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  transition: box-shadow $transition-fast;
}

.module-name {
  flex: 1;
  font-size: 12.5px;
  color: $text-secondary;
  .active & { color: $text-primary; font-weight: 500; }
}

.module-count {
  font-size: 10px;
  color: $text-muted;
  background: $bg-secondary;
  border: 1px solid $border-color;
  padding: 1px 6px;
  border-radius: 8px;
  font-weight: 600;

  &.active-count {
    color: var(--accent-info);
    background: rgba(var(--accent-info-rgb), 0.1);
    border-color: rgba(var(--accent-info-rgb), 0.3);
  }
}
</style>
