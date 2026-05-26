<script setup lang="ts">
import { ref, onMounted, computed, h } from 'vue'
import {
  NCard, NForm, NFormItem, NInput, NSelect, NInputNumber, NCheckbox,
  NButton, NSpace, NTag, NSpin, NEmpty, NTabs, NTabPane,
  NDataTable, NModal, NStatistic, NGrid, NGi, NDivider,
  useMessage, useDialog,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import {
  queryKnowledge,
  listKnowledgeEntries,
  addKnowledgeEntry,
  deleteKnowledgeEntry,
  getKnowledgeStats,
  importKnowledgeBatch,
  type KnowledgeQueryRequest,
  type KnowledgeResult,
  type KnowledgeEntry,
  type KnowledgeStats,
} from '@/api/tahp/knowledge'
import {
  createAdaptSkill,
  listAdaptSkills,
  deleteAdaptSkill,
  type SkillInfo,
  type AdaptFieldDef,
} from '@/api/tahp/skills'
import { useTahpModulesStore } from '@/stores/tahp/modules'

const message = useMessage()
const dialog = useDialog()
const modulesStore = useTahpModulesStore()

const activeTab = ref('query')

// ---- 检索 ----
const form = ref<KnowledgeQueryRequest>({ query: '', top_k: 5, cross_module: false })
const loading = ref(false)
const result = ref<KnowledgeResult | null>(null)

// ---- 条目管理 ----
const entriesLoading = ref(false)
const entries = ref<KnowledgeEntry[]>([])
const entriesTotal = ref(0)
const filterModule = ref('')
const showAddModal = ref(false)
const addForm = ref<KnowledgeEntry>({ title: '', content: '', module: '', tags: [], source: '' })
const adding = ref(false)

// ---- 统计 ----
const statsLoading = ref(false)
const stats = ref<KnowledgeStats | null>(null)

// ---- 批量导入 ----
const importJson = ref('')
const importing = ref(false)

const moduleOptions = computed(() => [
  { label: '(全部模块)', value: '' },
  ...modulesStore.modules.map(m => ({ label: m.name, value: m.name })),
])

const entryColumns: DataTableColumns<KnowledgeEntry> = [
  { title: '标题', key: 'title', ellipsis: { tooltip: true } },
  { title: '模块', key: 'module', width: 120 },
  { title: '来源', key: 'source', width: 180, ellipsis: { tooltip: true } },
  {
    title: '创建时间',
    key: 'created_at',
    width: 160,
    render: r => r.created_at ? new Date(r.created_at).toLocaleString() : '-',
  },
  {
    title: '操作',
    key: 'actions',
    width: 100,
    render: r => {
      const id = r.id
      if (!id) return ''
      return h(NButton, {
        size: 'small',
        type: 'error',
        ghost: true,
        onClick: () => confirmDelete(id, r.title),
      }, () => '删除')
    },
  },
]

onMounted(async () => {
  await modulesStore.refresh()
  loadStats()
})

async function doQuery() {
  if (!form.value.query?.trim()) { message.warning('请输入查询内容'); return }
  loading.value = true
  result.value = null
  try {
    const payload = { ...form.value }
    if (!payload.module) delete payload.module
    result.value = await queryKnowledge(payload)
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

async function loadEntries() {
  entriesLoading.value = true
  try {
    const res = await listKnowledgeEntries(filterModule.value || undefined)
    entries.value = res.entries || []
    entriesTotal.value = res.total || 0
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    entriesLoading.value = false
  }
}

async function loadStats() {
  statsLoading.value = true
  try {
    stats.value = await getKnowledgeStats()
  } catch {
    stats.value = null
  } finally {
    statsLoading.value = false
  }
}

function openAddModal() {
  addForm.value = { title: '', content: '', module: '', tags: [], source: '' }
  showAddModal.value = true
}

async function submitAdd() {
  if (!addForm.value.title?.trim() || !addForm.value.content?.trim()) {
    message.warning('标题和内容不能为空')
    return
  }
  adding.value = true
  try {
    await addKnowledgeEntry(addForm.value)
    message.success('知识条目已添加')
    showAddModal.value = false
    if (activeTab.value === 'manage') loadEntries()
    loadStats()
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    adding.value = false
  }
}

function confirmDelete(id: string, title: string) {
  dialog.warning({
    title: '确认删除',
    content: `删除知识条目「${title}」？此操作不可撤销。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteKnowledgeEntry(id)
        message.success('已删除')
        loadEntries()
        loadStats()
      } catch (err) {
        message.error((err as Error).message)
      }
    },
  })
}

async function doImport() {
  if (!importJson.value.trim()) { message.warning('请粘贴 JSON 数组'); return }
  let parsed: KnowledgeEntry[]
  try {
    parsed = JSON.parse(importJson.value)
    if (!Array.isArray(parsed)) throw new Error('必须是 JSON 数组')
  } catch (e) {
    message.error(`JSON 格式错误: ${(e as Error).message}`)
    return
  }
  importing.value = true
  try {
    const res = await importKnowledgeBatch(parsed)
    message.success(`成功导入 ${res.imported} 条，失败 ${res.errors} 条`)
    importJson.value = ''
    if (activeTab.value === 'manage') loadEntries()
    loadStats()
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    importing.value = false
  }
}

function onTabChange(tab: string) {
  activeTab.value = tab
  if (tab === 'manage' && !entries.value.length) loadEntries()
  if (tab === 'stats') loadStats()
  if (tab === 'skills') loadSkills()
}

// ─── 技能创建 ─────────────────────────────────────────────────────────────────
const skillsLoading  = ref(false)
const skillsList     = ref<SkillInfo[]>([])
const skillCreating  = ref(false)

const PRESET_COLORS = [
  '#388bfd','#10b981','#f59e0b','#d03050',
  '#7c3aed','#0ea5e9','#f97316','#84cc16',
]

const FIXED_MODULES = ['telephony','kernel-driver','power-mgmt','shared']
const skillModuleOptions = computed(() => [
  ...FIXED_MODULES.map(m => ({ label: m, value: m })),
  { label: '自定义…', value: 'custom' },
])

const newSkill = ref({
  skillId:     '',
  domainLabel: '',
  domainId:    '',
  module:      'kernel-driver',
  customModule:'',
  icon:        '',
  color:       '#388bfd',
  content:     '',
  description: '',
})

const newSkillFields = ref<AdaptFieldDef[]>([
  { name: 'issue_desc', label: '问题描述', type: 'textarea', required: true, placeholder: '描述需要适配的具体问题' },
])

function addField() {
  newSkillFields.value.push({ name: '', label: '', type: 'text', required: false, placeholder: '' })
}

function removeField(idx: number) {
  newSkillFields.value.splice(idx, 1)
}

const fieldTypeOptions = [
  { label: '单行文本', value: 'text' },
  { label: '多行文本', value: 'textarea' },
  { label: '下拉选择', value: 'select' },
]

async function loadSkills() {
  skillsLoading.value = true
  try {
    const res = await listAdaptSkills()
    skillsList.value = res.skills || []
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    skillsLoading.value = false
  }
}

async function submitCreateSkill() {
  const s = newSkill.value
  if (!s.skillId.trim()) { message.warning('请填写技能 ID'); return }
  if (!/^[a-zA-Z0-9_-]+$/.test(s.skillId.trim())) { message.warning('技能 ID 只能包含字母、数字、连字符、下划线'); return }
  if (!s.domainLabel.trim()) { message.warning('请填写域显示名'); return }

  const validFields = newSkillFields.value.filter(f => f.name.trim() && f.label.trim())
  if (!validFields.length) { message.warning('至少添加一个有效的前置条件字段'); return }

  const resolvedModule = s.module === 'custom' ? (s.customModule.trim() || 'shared') : s.module

  skillCreating.value = true
  try {
    const result = await createAdaptSkill({
      skillId:     s.skillId.trim(),
      domainLabel: s.domainLabel.trim(),
      domainId:    s.domainId.trim() || s.skillId.trim(),
      module:      resolvedModule,
      icon:        s.icon.trim() || s.skillId.slice(0, 4).toUpperCase(),
      color:       s.color,
      adaptFields: validFields,
      content:     s.content.trim() || '',
      description: s.description.trim() || s.domainLabel.trim(),
    })
    message.success(`技能 "${result.domainLabel}" 创建成功，AI适配调试页面会自动出现新业务域`)
    // 重置表单
    Object.assign(newSkill.value, {
      skillId: '', domainLabel: '', domainId: '', module: 'kernel-driver',
      customModule: '', icon: '', color: '#388bfd', content: '', description: '',
    })
    newSkillFields.value = [{ name: 'issue_desc', label: '问题描述', type: 'textarea', required: true, placeholder: '' }]
    loadSkills()
  } catch (err) {
    message.error(`创建失败: ${(err as Error).message}`)
  } finally {
    skillCreating.value = false
  }
}

function confirmDeleteSkill(skillId: string, label: string) {
  dialog.warning({
    title: '确认删除技能',
    content: `删除「${label}」技能后，AI适配调试页面的对应域将消失，无法恢复。`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        await deleteAdaptSkill(skillId)
        message.success('技能已删除')
        loadSkills()
      } catch (err) {
        message.error((err as Error).message)
      }
    },
  })
}
</script>

<template>
  <div class="tahp-kb">
    <div class="page-header">
      <div>
        <h1>知识库</h1>
        <p class="subtitle">语义检索 · 条目管理 · 统计 (SQLite + ONNX 嵌入向量)</p>
      </div>
      <NButton type="primary" @click="openAddModal">
        <template #icon>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        </template>
        新增条目
      </NButton>
    </div>

    <!-- 统计卡片 -->
    <NGrid v-if="stats" :cols="3" :x-gap="16" :y-gap="12" style="margin-bottom: 16px">
      <NGi>
        <NCard :bordered="false" size="small">
          <NStatistic label="知识条目总数" :value="stats.total" />
        </NCard>
      </NGi>
      <NGi v-for="(cnt, mod) in stats.by_module" :key="mod">
        <NCard :bordered="false" size="small">
          <NStatistic :label="String(mod)" :value="cnt" />
        </NCard>
      </NGi>
    </NGrid>

    <NTabs :value="activeTab" @update:value="onTabChange">
      <!-- 检索 Tab -->
      <NTabPane name="query" tab="语义检索">
        <NCard :bordered="false" style="margin-top: 8px">
          <NForm :model="form" inline label-placement="left">
            <NFormItem label="查询" style="flex: 1; min-width: 240px">
              <NInput
                v-model:value="form.query"
                placeholder="如：RILJ 错误码 / dts 加载流程 / suspend 异常 ..."
                @keyup.enter="doQuery"
              />
            </NFormItem>
            <NFormItem label="模块">
              <NSelect v-model:value="form.module" :options="moduleOptions" style="width: 160px" clearable />
            </NFormItem>
            <NFormItem label="Top K">
              <NInputNumber v-model:value="form.top_k" :min="1" :max="50" style="width: 90px" />
            </NFormItem>
            <NFormItem>
              <NCheckbox v-model:checked="form.cross_module">跨模块</NCheckbox>
            </NFormItem>
            <NFormItem>
              <NButton type="primary" :loading="loading" @click="doQuery">搜索</NButton>
            </NFormItem>
          </NForm>
        </NCard>

        <NCard :bordered="false" style="margin-top: 12px">
          <template v-if="result">
            <NSpace style="margin-bottom: 12px">
              <NTag size="small">{{ (result.results || []).length }} 条</NTag>
              <NTag v-if="result.confidence !== undefined" size="small" type="info">
                置信度: {{ Number(result.confidence).toFixed(3) }}
              </NTag>
            </NSpace>
          </template>
          <NSpin :show="loading">
            <NEmpty v-if="!result" description="输入关键词后回车或点击搜索" />
            <NEmpty v-else-if="!result.results?.length" description="无匹配结果" />
            <div v-else class="result-list">
              <div v-for="(r, i) in result.results" :key="i" class="result-card">
                <div class="result-header">
                  <strong>{{ r.title || `结果 ${i + 1}` }}</strong>
                  <NSpace size="small">
                    <NTag v-if="r.module" size="tiny" type="info">{{ r.module }}</NTag>
                    <NTag v-if="r.score !== undefined" size="tiny">{{ Number(r.score).toFixed(3) }}</NTag>
                  </NSpace>
                </div>
                <div v-if="r.source" class="result-source">{{ r.source }}</div>
                <pre v-if="r.content" class="result-content">{{ r.content }}</pre>
              </div>
            </div>
          </NSpin>
        </NCard>
      </NTabPane>

      <!-- 条目管理 Tab -->
      <NTabPane name="manage" tab="条目管理">
        <NCard :bordered="false" style="margin-top: 8px">
          <template #header-extra>
            <NSpace>
              <NSelect
                v-model:value="filterModule"
                :options="moduleOptions"
                placeholder="筛选模块"
                style="width: 150px"
                clearable
                size="small"
                @update:value="loadEntries"
              />
              <NButton size="small" @click="loadEntries">刷新</NButton>
              <NButton size="small" type="primary" @click="openAddModal">新增</NButton>
            </NSpace>
          </template>
          <NSpin :show="entriesLoading">
            <NEmpty v-if="!entries.length && !entriesLoading" description="暂无条目，点击刷新或新增" />
            <NDataTable
              v-else
              :columns="entryColumns"
              :data="entries"
              :pagination="{ pageSize: 15 }"
              size="small"
            />
          </NSpin>
        </NCard>
      </NTabPane>

      <!-- 批量导入 Tab -->
      <NTabPane name="import" tab="批量导入">
        <NCard :bordered="false" style="margin-top: 8px">
          <p style="color: #888; font-size: 13px; margin-bottom: 12px">
            粘贴符合以下格式的 JSON 数组，每条包含 <code>title</code>、<code>content</code>（必填），
            以及可选的 <code>module</code>、<code>source</code>、<code>tags</code>。
          </p>
          <NInput
            v-model:value="importJson"
            type="textarea"
            placeholder='[{"title":"标题","content":"内容","module":"telephony","source":"来源"}]'
            :autosize="{ minRows: 10, maxRows: 20 }"
            style="font-family: monospace; font-size: 12px"
          />
          <NDivider style="margin: 12px 0" />
          <NButton type="primary" :loading="importing" @click="doImport">导入</NButton>
        </NCard>
      </NTabPane>

      <!-- 技能创建 Tab ─────────────────────────────────────────── -->
      <NTabPane name="skills" tab="⚡ 创建适配技能">
        <div class="skill-create-layout">

          <!-- 左：创建表单 -->
          <NCard :bordered="false" class="skill-form-card" title="新建适配技能">
            <template #header-extra>
              <span style="font-size:12px;color:#888;">技能创建后会立即出现在"AI 适配调试"页面的业务域列表中</span>
            </template>
            <NForm label-placement="left" label-width="90" size="small">

              <!-- 基本信息 -->
              <NDivider title-placement="left" style="margin:0 0 12px">基本信息</NDivider>
              <NFormItem label="技能 ID" required>
                <NInput
                  v-model:value="newSkill.skillId"
                  placeholder="仅英文/数字/连字符，如 audio-test-adapt"
                />
              </NFormItem>
              <NFormItem label="域显示名" required>
                <NInput v-model:value="newSkill.domainLabel" placeholder="如：Audio 测试适配" />
              </NFormItem>
              <NFormItem label="域 ID">
                <NInput v-model:value="newSkill.domainId" placeholder="留空则与技能 ID 相同" />
              </NFormItem>
              <NFormItem label="所属模块" required>
                <NSelect
                  v-model:value="newSkill.module"
                  :options="skillModuleOptions"
                  style="width: 200px"
                />
                <NInput
                  v-if="newSkill.module === 'custom'"
                  v-model:value="newSkill.customModule"
                  placeholder="自定义模块名"
                  style="margin-left: 8px; flex: 1"
                />
              </NFormItem>
              <NFormItem label="徽章图标">
                <NInput v-model:value="newSkill.icon" placeholder="2-4 字符，如 AUD" style="width: 100px" />
              </NFormItem>
              <NFormItem label="主题颜色">
                <NSpace>
                  <button
                    v-for="c in PRESET_COLORS" :key="c"
                    class="color-swatch"
                    :style="{ background: c, outline: newSkill.color === c ? `2px solid ${c}` : 'none', outlineOffset: '2px' }"
                    @click="newSkill.color = c"
                  />
                  <NInput v-model:value="newSkill.color" style="width: 100px; font-family: monospace" />
                </NSpace>
              </NFormItem>
              <NFormItem label="简介">
                <NInput v-model:value="newSkill.description" placeholder="一行简介（可选）" />
              </NFormItem>

              <!-- 前置条件字段 -->
              <NDivider title-placement="left" style="margin:16px 0 12px">前置条件字段</NDivider>
              <p style="font-size:12px;color:#888;margin:0 0 12px;">
                定义用户在启动适配时需要填写的信息项（前置条件表单）
              </p>
              <div class="fields-builder">
                <div
                  v-for="(f, idx) in newSkillFields"
                  :key="idx"
                  class="field-row"
                >
                  <NInput v-model:value="f.name"  placeholder="字段key" style="width: 120px" />
                  <NInput v-model:value="f.label" placeholder="显示名" style="width: 120px" />
                  <NSelect v-model:value="f.type" :options="fieldTypeOptions" style="width: 110px" />
                  <NInput v-model:value="f.placeholder" placeholder="提示文字（可选）" style="flex:1" />
                  <NCheckbox v-model:checked="f.required">必填</NCheckbox>
                  <NButton
                    size="tiny"
                    type="error"
                    ghost
                    :disabled="newSkillFields.length <= 1"
                    @click="removeField(idx)"
                  >删除</NButton>
                </div>
              </div>
              <NButton size="small" dashed style="margin-top:8px" @click="addField">
                + 添加字段
              </NButton>

              <!-- 技能内容 -->
              <NDivider title-placement="left" style="margin:16px 0 12px">技能说明（Markdown）</NDivider>
              <NFormItem label="">
                <NInput
                  v-model:value="newSkill.content"
                  type="textarea"
                  placeholder="描述该技能的执行流程、注意事项、关键约束等（支持 Markdown）"
                  :autosize="{ minRows: 6, maxRows: 16 }"
                  style="font-family: monospace; font-size: 12px"
                />
              </NFormItem>

              <NButton
                type="primary"
                :loading="skillCreating"
                style="margin-top: 8px"
                @click="submitCreateSkill"
              >
                <template #icon>
                  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>
                </template>
                创建技能并发布到 AI 适配调试
              </NButton>
            </NForm>
          </NCard>

          <!-- 右：已创建技能列表 -->
          <NCard :bordered="false" class="skill-list-card" title="已创建的适配技能">
            <template #header-extra>
              <NButton size="small" @click="loadSkills">刷新</NButton>
            </template>
            <NSpin :show="skillsLoading">
              <NEmpty v-if="!skillsList.length && !skillsLoading" description="暂无自定义技能" />
              <div v-else class="skill-cards">
                <div
                  v-for="s in skillsList"
                  :key="s.skillId"
                  class="skill-card"
                >
                  <div class="sc-head">
                    <span class="sc-icon" :style="{ background: s.color }">{{ s.icon }}</span>
                    <div class="sc-info">
                      <div class="sc-label">{{ s.domainLabel }}</div>
                      <div class="sc-id">{{ s.skillId }} · {{ s.module }}</div>
                    </div>
                    <NButton
                      size="tiny"
                      type="error"
                      ghost
                      @click="confirmDeleteSkill(s.skillId, s.domainLabel)"
                    >删除</NButton>
                  </div>
                  <div v-if="s.adaptFields?.length" class="sc-fields">
                    <NTag
                      v-for="f in s.adaptFields.slice(0, 4)"
                      :key="f.name"
                      size="tiny"
                      :type="f.required ? 'warning' : 'default'"
                      style="margin: 2px"
                    >{{ f.label }}</NTag>
                  </div>
                  <div v-if="s.description" class="sc-desc">{{ s.description }}</div>
                </div>
              </div>
            </NSpin>
          </NCard>
        </div>
      </NTabPane>
    </NTabs>

    <!-- 新增条目弹窗 -->
    <NModal
      v-model:show="showAddModal"
      preset="dialog"
      title="新增知识条目"
      positive-text="添加"
      negative-text="取消"
      style="width: 560px"
      @positive-click="submitAdd"
    >
      <NForm :model="addForm" label-placement="left" label-width="72">
        <NFormItem label="标题" required>
          <NInput v-model:value="addForm.title" placeholder="条目标题" />
        </NFormItem>
        <NFormItem label="模块">
          <NSelect v-model:value="addForm.module" :options="moduleOptions" clearable />
        </NFormItem>
        <NFormItem label="来源">
          <NInput v-model:value="addForm.source" placeholder="文件路径或 Jira 链接" />
        </NFormItem>
        <NFormItem label="内容" required>
          <NInput
            v-model:value="addForm.content"
            type="textarea"
            placeholder="知识内容，支持 Markdown"
            :autosize="{ minRows: 6, maxRows: 16 }"
          />
        </NFormItem>
      </NForm>
    </NModal>
  </div>
</template>

<style scoped>
.tahp-kb { padding: 24px; max-width: 1280px; margin: 0 auto; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 16px; }
.page-header h1 { margin: 0 0 4px; font-size: 22px; font-weight: 600; }
.subtitle { color: #888; margin: 0; font-size: 13px; }
.result-list { display: flex; flex-direction: column; gap: 12px; }
.result-card { padding: 12px; background: var(--n-color-modal, rgba(0,0,0,.03)); border-radius: 6px; }
.result-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.result-source { color: #888; font-size: 12px; margin-bottom: 8px; font-family: monospace; }
.result-content { margin: 0; white-space: pre-wrap; font-size: 13px; line-height: 1.6; }
code { background: rgba(0,0,0,.06); padding: 1px 4px; border-radius: 3px; font-size: 12px; }

/* ── 技能创建 Tab ─────────────────────────────────────────────── */
.skill-create-layout {
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: 16px;
  margin-top: 8px;
  align-items: start;
}

.skill-form-card,
.skill-list-card { min-height: 200px; }

/* 颜色色块按钮 */
.color-swatch {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  border: none;
  cursor: pointer;
  padding: 0;
  transition: transform .15s;
}
.color-swatch:hover { transform: scale(1.15); }

/* 字段构建器 */
.fields-builder { display: flex; flex-direction: column; gap: 8px; }
.field-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  background: rgba(0,0,0,.03);
  border-radius: 6px;
  flex-wrap: wrap;
}

/* 已创建技能卡片列表 */
.skill-cards { display: flex; flex-direction: column; gap: 10px; }
.skill-card {
  padding: 10px 12px;
  border: 1px solid rgba(0,0,0,.08);
  border-radius: 8px;
  background: var(--n-color-modal, rgba(255,255,255,.6));
  transition: box-shadow .15s;
}
.skill-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,.08); }

.sc-head {
  display: flex;
  align-items: center;
  gap: 10px;
}
.sc-icon {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: #fff;
  flex-shrink: 0;
  letter-spacing: .5px;
}
.sc-info { flex: 1; min-width: 0; }
.sc-label { font-size: 13px; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sc-id { font-size: 11px; color: #888; margin-top: 2px; }
.sc-desc { font-size: 12px; color: #999; margin-top: 6px; line-height: 1.4; }
.sc-fields { display: flex; flex-wrap: wrap; gap: 2px; margin-top: 6px; }
</style>
