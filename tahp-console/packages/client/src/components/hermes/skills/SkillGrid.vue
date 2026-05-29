<script setup lang="ts">
import { computed } from 'vue'
import { NSwitch } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { toggleSkill, type SkillInfo } from '@/api/hermes/skills'

const { t } = useI18n()

const props = defineProps<{
  skills: SkillInfo[]
  selectedSkill: string | null   // "<category>/<name>"
  funcTypeFilter: string | null
  moduleFilter: string | null
  searchQuery: string
}>()

const emit = defineEmits<{
  select: [name: string]
}>()

// ── 模块颜色映射 ──────────────────────────────────────────────────────────────
const MODULE_COLOR: Record<string, { dot: string; tag: string; bg: string; border: string }> = {
  '通信': { dot: '#388bfd', tag: 'tag-telecom', bg: 'rgba(56,139,253,0.12)', border: 'rgba(56,139,253,0.25)' },
  '驱动': { dot: '#3fb950', tag: 'tag-driver',  bg: 'rgba(63,185,80,0.12)',  border: 'rgba(63,185,80,0.25)' },
  '内核': { dot: '#e3b341', tag: 'tag-kernel',  bg: 'rgba(227,179,65,0.12)', border: 'rgba(227,179,65,0.25)' },
  '功耗': { dot: '#f78166', tag: 'tag-power',   bg: 'rgba(247,129,102,0.12)',border: 'rgba(247,129,102,0.25)' },
}

// ── 平台徽标识别 ──────────────────────────────────────────────────────────────
function getPlatform(name: string): string | null {
  if (/^mtk[-_]|mediatek/i.test(name)) return 'MTK'
  if (/^qualcomm|^qcom/i.test(name)) return 'QCom'
  if (/^uns[-_]/i.test(name)) return 'UNISOC'
  if (/^spd[-_]/i.test(name)) return 'SPD'
  return null
}

// ── 模块图标 emoji ────────────────────────────────────────────────────────────
const MODULE_EMOJI: Record<string, string> = {
  '通信': '📡', '驱动': '⚙️', '内核': '🐧', '功耗': '⚡', '通用': '🔧',
}
function getIcon(skill: SkillInfo): string {
  if (skill.group && MODULE_EMOJI[skill.group]) return MODULE_EMOJI[skill.group]
  const n = skill.name.toLowerCase()
  if (n.includes('tp') || n.includes('touch') || n.includes('fingerprint')) return '🖐️'
  if (n.includes('audio') || n.includes('sound')) return '🔊'
  if (n.includes('battery') || n.includes('charging')) return '🔋'
  if (n.includes('usb') || n.includes('typec')) return '🔌'
  if (n.includes('sensor') || n.includes('als') || n.includes('light')) return '💡'
  if (n.includes('bt') || n.includes('bluetooth')) return '📶'
  if (n.includes('sim') || n.includes('call') || n.includes('sms')) return '📱'
  if (n.includes('screen') || n.includes('display') || n.includes('backlight')) return '🖥️'
  if (n.includes('boot') || n.includes('kernel') || n.includes('crash')) return '🐞'
  return '⚙️'
}

function relativeTime(ts: number): string {
  const diff = Date.now() - ts
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return '刚刚'
  if (mins < 60) return `${mins}分钟前`
  const hours = Math.floor(diff / 3600000)
  if (hours < 24) return `${hours}小时前`
  const days = Math.floor(diff / 86400000)
  if (days < 7) return `${days}天前`
  return new Date(ts).toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

// ── 过滤逻辑 ──────────────────────────────────────────────────────────────────

/** funcType 过滤后（未加 module / search）的数量，用于面包屑显示 */
const funcTypeCount = computed<number>(() => {
  if (!props.funcTypeFilter) return props.skills.length
  return props.skills.filter(s => s.funcType === props.funcTypeFilter).length
})

const filtered = computed<SkillInfo[]>(() => {
  let list = props.skills
  if (props.funcTypeFilter) list = list.filter(s => s.funcType === props.funcTypeFilter)
  if (props.moduleFilter)   list = list.filter(s => (s.group || '通用') === props.moduleFilter)
  if (props.searchQuery) {
    const q = props.searchQuery.toLowerCase()
    list = list.filter(s =>
      s.name.toLowerCase().includes(q) ||
      (s.description ?? '').toLowerCase().includes(q)
    )
  }
  return list
})

/** 面包屑文本：funcType · module */
const contextBreadcrumb = computed<string>(() => {
  const parts: string[] = []
  if (props.funcTypeFilter) parts.push(props.funcTypeFilter)
  if (props.moduleFilter)   parts.push(props.moduleFilter)
  return parts.join(' · ')
})

/** 是否有额外过滤（module/search）生效 */
const hasExtraFilter = computed<boolean>(
  () => !!(props.moduleFilter || props.searchQuery),
)

function isSelected(skill: SkillInfo): boolean {
  return props.selectedSkill?.split('/')[1] === skill.name
}

function moduleStyle(group: string | undefined) {
  const c = group ? MODULE_COLOR[group] : null
  return c ? { background: c.bg, border: `1px solid ${c.border}`, color: '' } : {}
}

async function handleToggle(skill: SkillInfo, val: boolean) {
  await toggleSkill(skill.name, val)
  skill.enabled = val
}
</script>

<template>
  <div class="skill-grid-wrap">

    <!-- 上下文面包屑 + 统计 -->
    <div v-if="skills.length > 0" class="grid-context-bar">
      <span class="ctx-breadcrumb">
        <template v-if="contextBreadcrumb">{{ contextBreadcrumb }}</template>
        <template v-else>全部技能</template>
      </span>
      <span class="ctx-count">
        共 <b>{{ funcTypeCount }}</b> 个技能
        <template v-if="hasExtraFilter">
          &nbsp;·&nbsp;筛选 <b>{{ filtered.length }}</b>
        </template>
      </span>
    </div>

    <!-- 空状态 -->
    <div v-if="filtered.length === 0" class="grid-empty">
      <svg class="empty-icon" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
        <polygon points="12 2 2 7 12 12 22 7 12 2"/>
        <polyline points="2 17 12 22 22 17"/>
        <polyline points="2 12 12 17 22 12"/>
      </svg>
      <span>{{ searchQuery ? t('skills.noMatch') : t('skills.noSkills') }}</span>
    </div>

    <!-- 卡片网格 -->
    <div v-else class="skill-grid">
      <div
        v-for="skill in filtered"
        :key="skill.name"
        class="skill-card"
        :class="{ active: isSelected(skill) }"
        @click="emit('select', skill.name)"
      >
        <!-- 顶部渐变条（hover/active 激活） -->
        <div class="card-glow-bar" />

        <!-- 卡片头部 -->
        <div class="card-header">
          <div class="card-icon" :style="moduleStyle(skill.group)">
            {{ getIcon(skill) }}
          </div>
          <div class="card-title-area">
            <div class="card-name" :title="skill.name">
              {{ skill.name }}
              <span v-if="skill.status === 'deprecated'" class="tag tag-deprecated">已废弃</span>
            </div>
            <div class="card-tags">
              <span
                v-if="skill.group"
                class="tag"
                :class="`tag-${skill.group === '通信' ? 'telecom' : skill.group === '驱动' ? 'driver' : skill.group === '内核' ? 'kernel' : skill.group === '功耗' ? 'power' : 'general'}`"
              >{{ skill.group }}</span>
              <span v-if="getPlatform(skill.name)" class="tag tag-platform">{{ getPlatform(skill.name) }}</span>
            </div>
          </div>
        </div>

        <!-- 描述 -->
        <div class="card-desc">{{ skill.description || '暂无描述' }}</div>

        <!-- 底部元信息 -->
        <div class="card-footer">
          <span v-if="skill.updatedAt" class="card-time">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
            </svg>
            {{ relativeTime(skill.updatedAt) }}
          </span>
          <span class="card-spacer" />
          <span v-if="skill.version" class="card-version">{{ skill.version }}</span>
          <NSwitch
            size="small"
            :value="skill.enabled !== false"
            @update:value="handleToggle(skill, $event)"
            @click.stop
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

// ── 容器 ─────────────────────────────────────────────────────────────────────

.skill-grid-wrap {
  flex: 1;
  overflow-y: auto;
  padding: 0 16px 16px;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

// ── 面包屑/统计栏 ─────────────────────────────────────────────────────────────

.grid-context-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 2px 10px;
  flex-shrink: 0;
}

.ctx-breadcrumb {
  font-size: 12px;
  font-weight: 600;
  color: $text-primary;
}

.ctx-count {
  font-size: 11.5px;
  color: $text-muted;
  b { color: $text-secondary; font-weight: 600; }
}

.grid-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: $text-muted;
  font-size: 13px;
  .empty-icon { opacity: 0.2; }
}

// ── 卡片网格 ──────────────────────────────────────────────────────────────────

.skill-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
  gap: 10px;
  align-content: start;
}

// ── 卡片 ─────────────────────────────────────────────────────────────────────

.skill-card {
  background: $bg-card;
  border: 1px solid $border-color;
  border-radius: $radius-md;
  padding: 14px 15px 12px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 8px;
  position: relative;
  overflow: hidden;
  transition: border-color $transition-fast, box-shadow $transition-fast, transform $transition-fast;

  &:hover {
    border-color: rgba(var(--accent-info-rgb), 0.45);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.12);
    transform: translateY(-1px);

    .card-glow-bar {
      opacity: 1;
    }
  }

  &.active {
    border-color: var(--accent-info);
    box-shadow: 0 0 0 1px var(--accent-info), 0 4px 20px rgba(var(--accent-info-rgb), 0.2);

    .card-glow-bar { opacity: 1; background: linear-gradient(90deg, var(--accent-info), #a371f7); }
    .card-name { color: var(--accent-info); }
  }
}

.card-glow-bar {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, var(--accent-info), #a371f7);
  opacity: 0;
  transition: opacity $transition-fast;
  border-radius: $radius-md $radius-md 0 0;
}

// ── 卡片头部 ──────────────────────────────────────────────────────────────────

.card-header {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.card-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  flex-shrink: 0;
  background: rgba(var(--accent-primary-rgb), 0.06);
  border: 1px solid $border-color;
}

.card-title-area {
  flex: 1;
  min-width: 0;
}

.card-name {
  font-size: 12.5px;
  font-weight: 600;
  color: $text-primary;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
  transition: color $transition-fast;
}

.card-tags {
  display: flex;
  gap: 4px;
  margin-top: 4px;
  flex-wrap: wrap;
}

.tag {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
  border: 1px solid;
}
.tag-telecom { background: rgba(56,139,253,0.12);  color: #388bfd; border-color: rgba(56,139,253,0.25); }
.tag-driver  { background: rgba(63,185,80,0.12);   color: #3fb950; border-color: rgba(63,185,80,0.25); }
.tag-kernel  { background: rgba(227,179,65,0.12);  color: #e3b341; border-color: rgba(227,179,65,0.25); }
.tag-power   { background: rgba(247,129,102,0.12); color: #f78166; border-color: rgba(247,129,102,0.25); }
.tag-general { background: rgba(var(--accent-primary-rgb), 0.06); color: $text-muted; border-color: $border-color; }
.tag-platform{ background: rgba(163,113,247,0.12); color: #a371f7; border-color: rgba(163,113,247,0.25); }
.tag-deprecated{ background: rgba(230,81,0,0.12); color: #e65100; border-color: rgba(230,81,0,0.25); font-size:10px; margin-left:6px; vertical-align:middle; }

// ── 描述 ─────────────────────────────────────────────────────────────────────

.card-desc {
  font-size: 11.5px;
  color: $text-secondary;
  line-height: 1.55;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  flex: 1;
}

// ── 底部 ─────────────────────────────────────────────────────────────────────

.card-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
}

.card-time {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 10.5px;
  color: $text-muted;
}

.card-spacer { flex: 1; }

.card-version {
  font-size: 10px;
  color: $text-muted;
  background: $bg-secondary;
  border: 1px solid $border-color;
  padding: 1px 6px;
  border-radius: 4px;
  font-family: $font-code;
}
</style>
