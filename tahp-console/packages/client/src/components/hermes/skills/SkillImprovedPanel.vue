<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { NButton, NEmpty, NPopconfirm, NSpin, NTag, useMessage } from 'naive-ui'
import MarkdownRenderer from '@/components/hermes/chat/MarkdownRenderer.vue'
import {
  fetchImprovedSkills,
  fetchSkillContent,
  fetchSkillFiles,
  importFromPath,
  removeImprovedProfileCopy,
  type ImprovedSkill,
  type SkillFileEntry,
} from '@/api/hermes/skills'

const route = useRoute()
const message = useMessage()

const skills = ref<ImprovedSkill[]>([])
const loading = ref(false)
const selectedName = ref('')
const content = ref('')
const files = ref<SkillFileEntry[]>([])
const contentLoading = ref(false)
const promoting = ref(false)
const removing = ref(false)
const pendingRemoveHint = ref(false)

const STATUS_LABEL: Record<ImprovedSkill['status'], string> = {
  agent_only: '仅 Agent',
  promoted: '已固化',
  at_risk: '有覆盖风险',
}

const STATUS_TYPE: Record<ImprovedSkill['status'], 'default' | 'success' | 'warning'> = {
  agent_only: 'default',
  promoted: 'success',
  at_risk: 'warning',
}

const ACTION_LABELS: Record<string, string> = {
  create: '新建',
  edit: '整篇改写',
  patch: '局部补丁',
  write_file: '附属文件',
  remove_file: '删除文件',
  delete: '删除',
  file_write: '直接改文件',
}

const selected = computed(() => skills.value.find(s => s.name === selectedName.value) || null)

function querySkillName(): string {
  const raw = route.query.skill
  return typeof raw === 'string' ? raw.trim() : ''
}

function applyQuerySkill() {
  const name = querySkillName()
  if (name && skills.value.some(s => s.name === name)) {
    selectedName.value = name
  }
}

async function loadList() {
  loading.value = true
  try {
    skills.value = await fetchImprovedSkills()
    applyQuerySkill()
    if (!selectedName.value && skills.value.length) {
      selectedName.value = skills.value[0].name
    } else if (selectedName.value && !skills.value.some(s => s.name === selectedName.value)) {
      selectedName.value = skills.value[0]?.name || ''
    }
  } catch (err: any) {
    message.error(`加载自改进 Skill 失败: ${err.message}`)
  } finally {
    loading.value = false
  }
}

function contentPath(skill: ImprovedSkill): string {
  const rel = skill.profile_rel_path || skill.name
  return `${rel}/SKILL.md`
}

function fileCategory(skill: ImprovedSkill): { category: string; skill: string } {
  const rel = skill.profile_rel_path || skill.name
  const parts = rel.split('/').filter(Boolean)
  if (parts.length >= 2) return { category: parts[0], skill: parts[parts.length - 1] }
  return { category: 'misc', skill: skill.name }
}

async function loadContent(skill: ImprovedSkill) {
  contentLoading.value = true
  content.value = ''
  files.value = []
  if (!skill.exists_on_disk) {
    content.value = '磁盘上已找不到该 Skill 目录，可能已被手动删除。'
    contentLoading.value = false
    return
  }
  try {
    const { category, skill: skillId } = fileCategory(skill)
    const [md, listed] = await Promise.all([
      fetchSkillContent(contentPath(skill)),
      fetchSkillFiles(category, skillId).catch(() => [] as SkillFileEntry[]),
    ])
    content.value = md
    files.value = listed.filter(f => !f.isDir && f.path !== 'SKILL.md')
  } catch (err: any) {
    content.value = `加载失败: ${err.message}`
  } finally {
    contentLoading.value = false
  }
}

watch(() => selected.value?.name, (name, prev) => {
  if (name !== prev) pendingRemoveHint.value = false
  const skill = selected.value
  if (skill) void loadContent(skill)
  else {
    content.value = ''
    files.value = []
  }
})

watch(() => route.query.skill, () => {
  if (!loading.value) applyQuerySkill()
})

onMounted(() => {
  void loadList()
})

function formatTime(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN', { hour12: false })
}

function actionLabel(actions: string[]): string {
  return actions.map(a => ACTION_LABELS[a] || a).filter(Boolean).join('、')
}

async function promoteSkill(overwrite: boolean) {
  const skill = selected.value
  if (!skill?.profile_abs_path) {
    message.warning('找不到 profile 路径，无法固化')
    return
  }
  promoting.value = true
  try {
    const res = await importFromPath(
      [{ name: skill.name, sourcePath: skill.profile_abs_path }],
      overwrite,
    )
    if (res.errors?.length) {
      message.error(res.errors.map(e => `${e.name}: ${e.error}`).join('；'))
      return
    }
    if (res.skipped?.includes(skill.name)) {
      message.warning(`${skill.name} 已在仓库中。若要用当前 Agent 版本覆盖，请确认后重试。`)
      return
    }
    message.success(`已固化 ${skill.name} 到仓库 skills/.claude/skills/`)
    pendingRemoveHint.value = !!skill.profile_rel_path && skill.profile_rel_path.includes('/')
    await loadList()
  } catch (err: any) {
    message.error(`固化失败: ${err.message}`)
  } finally {
    promoting.value = false
  }
}

async function onRemoveProfileCopy() {
  const skill = selected.value
  if (!skill) return
  removing.value = true
  try {
    const res = await removeImprovedProfileCopy(skill.name)
    message.success(`已删除 profile 原副本 ${res.removed}`)
    pendingRemoveHint.value = false
    await loadList()
  } catch (err: any) {
    message.error(`删除失败: ${err.message}`)
  } finally {
    removing.value = false
  }
}
</script>

<template>
  <div class="improved-panel">
    <div class="improved-intro">
      Agent 在本机 Hermes Skill 目录里新建或改过的 Skill。仓库里没有的不会被 Console 启动覆盖；仓库里已有同名且落在扁平路径上的，下次启动会被仓库版本盖掉，请尽快固化。
    </div>

    <div v-if="loading && !skills.length" class="improved-loading">加载自改进记录…</div>
    <NEmpty v-else-if="!skills.length" description="暂无自改进 Skill（curator ledger 为空）" class="improved-empty" />

    <div v-else class="improved-body">
      <aside class="improved-list">
        <button
          v-for="s in skills"
          :key="s.name"
          type="button"
          class="improved-item"
          :class="{ active: selectedName === s.name, 'is-risk': s.status === 'at_risk' }"
          @click="selectedName = s.name"
        >
          <div class="item-row">
            <span class="item-name">{{ s.name }}</span>
            <NTag size="tiny" :type="STATUS_TYPE[s.status]" :bordered="false">
              {{ STATUS_LABEL[s.status] }}
            </NTag>
          </div>
          <div class="item-meta">
            <span>{{ actionLabel(s.actions) || '改动' }}</span>
            <span>{{ formatTime(s.last_updated_at) }}</span>
          </div>
        </button>
      </aside>

      <section v-if="selected" class="improved-detail">
        <header class="detail-head">
          <div>
            <h3 class="detail-title">{{ selected.name }}</h3>
            <p class="detail-sub">
              <code>{{ selected.profile_rel_path || '（磁盘上不存在）' }}</code>
              <span v-if="!selected.exists_on_disk"> · 已不在磁盘</span>
              <span v-if="selected.in_repo"> · 仓库已有同名</span>
            </p>
          </div>
          <div class="detail-actions">
            <NPopconfirm
              v-if="selected.in_repo && selected.exists_on_disk"
              positive-text="覆盖仓库版本"
              negative-text="取消"
              @positive-click="promoteSkill(true)"
            >
              <template #trigger>
                <NButton size="small" type="warning" :loading="promoting" :disabled="!selected.exists_on_disk">
                  覆盖固化
                </NButton>
              </template>
              仓库已有 {{ selected.name }}。要用当前 Agent 改过的版本覆盖仓库副本吗？
            </NPopconfirm>
            <NButton
              v-else
              size="small"
              type="primary"
              :loading="promoting"
              :disabled="!selected.exists_on_disk"
              @click="promoteSkill(false)"
            >
              固化进仓库
            </NButton>
            <NPopconfirm
              v-if="selected.in_repo && selected.exists_on_disk"
              positive-text="删除原副本"
              negative-text="取消"
              @positive-click="onRemoveProfileCopy"
            >
              <template #trigger>
                <NButton size="small" :loading="removing">删除 profile 原副本</NButton>
              </template>
              固化后注入器会把仓库版写到扁平路径。删除分类目录下的原副本，避免 Agent 检索到同名双份。
            </NPopconfirm>
          </div>
        </header>

        <p v-if="selected.status === 'at_risk'" class="risk-banner">
          该 Skill 在仓库中已有同名，且 profile 副本落在扁平路径。下次启动 Console 会被仓库版本整目录覆盖，请先固化。
        </p>
        <p v-if="pendingRemoveHint" class="dup-banner">
          已写入仓库。若原副本在分类目录（如 stability/xxx），下次注入会再生成一份扁平副本。建议删除上面的 profile 原副本。
        </p>

        <div v-if="selected.task_ids.length" class="task-links">
          <span class="task-label">关联诊断任务</span>
          <RouterLink
            v-for="tid in selected.task_ids"
            :key="tid"
            class="task-link"
            :to="{ name: 'tahp.bug-analysis', query: { task_id: tid } }"
          >
            {{ tid }}
          </RouterLink>
        </div>

        <NSpin :show="contentLoading" class="detail-spin">
          <div class="md-wrap">
            <MarkdownRenderer :content="content" />
          </div>
          <div v-if="files.length" class="file-list">
            <div class="file-head">附属文件</div>
            <div v-for="f in files" :key="f.path" class="file-row">{{ f.path }}</div>
          </div>
        </NSpin>
      </section>
    </div>
  </div>
</template>

<style scoped>
.improved-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.improved-intro {
  font-size: 12px;
  color: var(--muted);
  line-height: 1.55;
}
.improved-loading,
.improved-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
  font-size: 13px;
}
.improved-body {
  flex: 1;
  min-height: 0;
  display: flex;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--surface);
  overflow: hidden;
}
.improved-list {
  width: 280px;
  flex-shrink: 0;
  overflow: auto;
  border-right: 1px solid var(--line);
  padding: 8px;
}
.improved-item {
  display: block;
  width: 100%;
  text-align: left;
  border: 1px solid transparent;
  background: transparent;
  border-radius: 10px;
  padding: 8px 10px;
  cursor: pointer;
  margin-bottom: 4px;
}
.improved-item:hover { background: color-mix(in srgb, var(--accent) 8%, transparent); }
.improved-item.active {
  background: color-mix(in srgb, var(--accent) 12%, var(--surface));
  border-color: color-mix(in srgb, var(--accent) 35%, transparent);
}
.improved-item.is-risk { box-shadow: inset 3px 0 0 #d97706; }
.item-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.item-name {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  font-weight: 600;
  color: var(--head);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.item-meta {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 4px;
  font-size: 11px;
  color: var(--muted);
}
.improved-detail {
  flex: 1;
  min-width: 0;
  overflow: auto;
  padding: 16px 18px 24px;
}
.detail-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 12px;
}
.detail-title {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
}
.detail-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--muted);
}
.detail-sub code {
  font-size: 11px;
}
.detail-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.risk-banner,
.dup-banner {
  margin: 0 0 12px;
  padding: 8px 10px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.5;
}
.risk-banner {
  background: color-mix(in srgb, #d97706 12%, var(--surface));
  border: 1px solid color-mix(in srgb, #d97706 35%, transparent);
}
.dup-banner {
  background: color-mix(in srgb, var(--accent) 10%, var(--surface));
  border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
}
.task-links {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 10px;
  align-items: center;
  margin-bottom: 12px;
  font-size: 12px;
}
.task-label { color: var(--muted); }
.task-link {
  font-family: ui-monospace, monospace;
  color: var(--accent);
}
.md-wrap { font-size: 13px; }
.detail-spin { min-height: 120px; }
.file-list { margin-top: 16px; }
.file-head {
  font-size: 12px;
  font-weight: 700;
  color: var(--head);
  margin-bottom: 6px;
}
.file-row {
  font-family: ui-monospace, monospace;
  font-size: 12px;
  color: var(--muted);
  padding: 2px 0;
}
</style>
