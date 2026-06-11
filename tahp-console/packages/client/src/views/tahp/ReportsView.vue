<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NCard, NButton, NSpin, NEmpty, NTag, NBreadcrumb, NBreadcrumbItem,
  NDescriptions, NDescriptionsItem, NScrollbar, NDivider, NSpace,
  NGrid, NGridItem, NStatistic, NAlert, useMessage,
} from 'naive-ui'
import { listTaskReports, getTaskReport, type TaskReportSummary, type TaskReportDetail, type AuditCheckItem } from '@/api/tahp/reports'

const route  = useRoute()
const router = useRouter()
const message = useMessage()

// ── 列表模式 ────────────────────────────────────────────────────────────────
const summaries   = ref<TaskReportSummary[]>([])
const listLoading = ref(false)

// ── 详情模式 ────────────────────────────────────────────────────────────────
const detail        = ref<TaskReportDetail | null>(null)
const detailLoading = ref(false)

const taskId = computed(() => route.query.task_id as string | undefined)
const mode   = computed<'detail' | 'list'>(() => taskId.value ? 'detail' : 'list')

onMounted(() => { loadData() })
watch(taskId, () => { loadData() })

async function loadData() {
  if (mode.value === 'detail') {
    detail.value = null
    detailLoading.value = true
    try {
      detail.value = await getTaskReport(taskId.value!)
    } catch (err) {
      message.error((err as Error).message)
    } finally {
      detailLoading.value = false
    }
  } else {
    summaries.value = []
    listLoading.value = true
    try {
      summaries.value = await listTaskReports()
    } catch (err) {
      message.error((err as Error).message)
    } finally {
      listLoading.value = false
    }
  }
}

function openTask(id: string) {
  router.push({ name: 'tahp.reports', query: { task_id: id } })
}

function backToList() {
  router.push({ name: 'tahp.reports' })
}

// ── 格式化工具 ───────────────────────────────────────────────────────────────
const DOMAIN_LABELS: Record<string, string> = {
  bug_analysis: 'Bug 分析',
  code_adaptation: '代码适配',
  version_adaptation: '版本适配',
  carrier_porting: '运营商移植',
  tp: 'TP触摸屏',
  vib: '振动马达',
  fp: '指纹',
  audio: '音频',
  charging: '充电',
  modem: '通信Modem',
  'comm-framework': '通信框架',
  kernel: '内核CPU',
  scp: 'SCP传感器',
  aikey: 'AI按键',
}

function domainDisplay(detail: TaskReportDetail): string {
  if (detail.domain_label) return detail.domain_label
  return DOMAIN_LABELS[detail.domain || ''] || detail.domain || '-'
}

function fmtTime(iso?: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return `${d.getFullYear()}/${d.getMonth()+1}/${d.getDate()} ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}:${d.getSeconds().toString().padStart(2,'0')}`
}

function fmtDuration(ms?: number): string {
  if (!ms && ms !== 0) return '-'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`
}

function fmtRelTime(mtime?: number): string {
  if (!mtime) return '-'
  const diff = Date.now() - mtime
  if (diff < 60_000) return '刚刚'
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)} 小时前`
  return fmtTime(new Date(mtime).toISOString())
}

const AUDIT_STATUS_LABEL: Record<AuditCheckItem['status'], string> = {
  pass: 'PASS',
  fail: 'FAIL',
  warn: 'WARN',
  na: 'N/A',
  unknown: 'UNKNOWN',
}

function auditStatusTagType(status: AuditCheckItem['status']): 'success' | 'error' | 'warning' | 'default' | 'info' {
  switch (status) {
    case 'pass': return 'success'
    case 'fail': return 'error'
    case 'warn': return 'warning'
    case 'na': return 'info'
    default: return 'default'
  }
}
</script>

<template>
  <div class="tahp-reports">
    <!-- 页头面包屑 -->
    <div class="page-header">
      <NBreadcrumb>
        <NBreadcrumbItem @click="backToList" style="cursor:pointer">报告列表</NBreadcrumbItem>
        <NBreadcrumbItem v-if="mode === 'detail'">
          <code style="font-size:12px">{{ taskId }}</code>
        </NBreadcrumbItem>
      </NBreadcrumb>
      <div class="header-row">
        <h1>{{ mode === 'detail' ? '任务报告详情' : '任务报告' }}</h1>
        <NSpace>
          <NButton size="small" @click="loadData">刷新</NButton>
          <NButton v-if="mode === 'detail'" size="small" @click="backToList">← 返回列表</NButton>
          <NButton v-else size="small" type="primary" @click="router.push({ name: 'tahp.executor' })">启动新任务</NButton>
        </NSpace>
      </div>
      <p class="subtitle">{{ mode === 'detail' ? 'AI 适配执行详情、分析结果与文件修改记录' : '所有已完成任务的执行报告汇总' }}</p>
    </div>

    <!-- ── 列表模式 ─────────────────────────────────────────────────────── -->
    <template v-if="mode === 'list'">
      <NSpin :show="listLoading">
        <NEmpty v-if="!listLoading && !summaries.length"
          description="暂无报告。执行任务后，报告将自动生成并显示在此处。"
          style="margin-top: 60px"
        >
          <template #extra>
            <NButton type="primary" @click="router.push({ name: 'tahp.executor' })">启动第一个任务</NButton>
          </template>
        </NEmpty>
        <NGrid v-else :cols="3" :x-gap="16" :y-gap="16" responsive="screen" item-responsive>
          <NGridItem
            v-for="s in summaries"
            :key="s.task_id"
            span="3 m:1"
          >
            <NCard
              hoverable
              class="report-card"
              @click="openTask(s.task_id)"
            >
              <template #header>
                <div class="card-header">
                  <div class="card-title">
                    <NTag size="small" type="success">已完成</NTag>
                    <span class="module-tag">{{ s.module || '-' }}</span>
                  </div>
                  <span class="card-time">{{ fmtRelTime(s.mtime) }}</span>
                </div>
              </template>
              <div class="card-task-id"><code>{{ s.task_id }}</code></div>
              <div class="card-stats">
                <div class="stat-item">
                  <span class="stat-label">域</span>
                  <span class="stat-value">{{ s.domain_label || DOMAIN_LABELS[s.domain || ''] || s.domain || '-' }}</span>
                </div>
                <div class="stat-item">
                  <span class="stat-label">耗时</span>
                  <span class="stat-value">{{ fmtDuration(s.duration_ms) }}</span>
                </div>
                <div class="stat-item">
                  <span class="stat-label">修改文件</span>
                  <span class="stat-value" :class="s.files_modified > 0 ? 'highlight' : ''">
                    {{ s.files_modified }} 个
                  </span>
                </div>
                <div class="stat-item">
                  <span class="stat-label">完成时间</span>
                  <span class="stat-value small">{{ fmtTime(s.completed_at) }}</span>
                </div>
              </div>
            </NCard>
          </NGridItem>
        </NGrid>
      </NSpin>
    </template>

    <!-- ── 详情模式 ─────────────────────────────────────────────────────── -->
    <template v-else>
      <NSpin :show="detailLoading">
        <div v-if="!detailLoading && !detail">
          <NAlert type="error" title="报告不存在">
            未找到任务 <code>{{ taskId }}</code> 的报告。可能该任务尚未完成，或报告文件不存在。
          </NAlert>
          <NButton style="margin-top:16px" @click="backToList">返回列表</NButton>
        </div>

        <div v-if="detail" class="detail-layout">
          <!-- 任务元信息 -->
          <NCard title="任务信息" :bordered="false" class="detail-card">
            <NGrid :cols="4" :x-gap="16" :y-gap="8" responsive="screen" item-responsive>
              <NGridItem span="4 m:1">
                <NStatistic label="模块" :value="detail.module || '-'" />
              </NGridItem>
              <NGridItem span="4 m:1">
                <NStatistic label="域" :value="domainDisplay(detail)" />
              </NGridItem>
              <NGridItem span="4 m:1">
                <NStatistic label="耗时" :value="fmtDuration(detail.duration_ms)" />
              </NGridItem>
              <NGridItem span="4 m:1">
                <NStatistic label="修改文件数" :value="String(detail.files_modified?.length ?? 0)" />
              </NGridItem>
            </NGrid>

            <NDivider style="margin: 16px 0 12px" />
            <NDescriptions :column="2" label-placement="left" size="small" bordered>
              <NDescriptionsItem label="Task ID" :span="2">
                <code style="font-size:11px;word-break:break-all">{{ detail.task_id }}</code>
              </NDescriptionsItem>
              <NDescriptionsItem label="启动时间">{{ fmtTime(detail.started_at) }}</NDescriptionsItem>
              <NDescriptionsItem label="完成时间">{{ fmtTime(detail.completed_at) }}</NDescriptionsItem>
              <NDescriptionsItem v-if="detail.correction_of" label="纠偏自" :span="2">
                <code style="font-size:11px">{{ detail.correction_of }}</code>
                <NButton size="tiny" style="margin-left:8px" @click="openTask(detail.correction_of!)">查看原任务</NButton>
              </NDescriptionsItem>
            </NDescriptions>
          </NCard>

          <!-- 附加上下文 -->
          <NCard v-if="detail.extra_context" title="附加上下文" :bordered="false" class="detail-card">
            <pre class="content-pre">{{ detail.extra_context }}</pre>
          </NCard>

          <!-- 使用的 Skill（完整路径） -->
          <NCard
            v-if="detail.skills_used?.length"
            title="使用的 Skill"
            :bordered="false"
            class="detail-card"
          >
            <div v-for="sk in detail.skills_used" :key="sk.skill_id + sk.path" class="skill-ref-row">
              <NTag size="small" type="info">{{ sk.skill_id }}</NTag>
              <code class="skill-path">{{ sk.path }}</code>
              <NTag v-if="sk.source" size="tiny" quaternary>{{ sk.source }}</NTag>
            </div>
          </NCard>

          <!-- 已修改文件 -->
          <NCard v-if="detail.files_modified?.length" title="已修改文件" :bordered="false" class="detail-card">
            <div
              v-for="(f, idx) in (detail.file_changes?.length ? detail.file_changes : detail.files_modified!.map(p => ({ path: p, action: 'modify', tool: '' })))"
              :key="f.path + idx"
              class="file-path"
            >
              <span class="file-icon">{{ f.action === 'create' ? '🆕' : '✅' }}</span>
              <div class="file-path-main">
                <code>{{ f.path }}</code>
                <span v-if="f.tool" class="file-meta">{{ f.action === 'create' ? '新建' : '修改' }} · {{ f.tool }}</span>
              </div>
            </div>
          </NCard>
          <NCard v-else title="已修改文件" :bordered="false" class="detail-card">
            <NEmpty size="small" description="本次任务未修改任何文件（纯分析结果）" />
          </NCard>

          <!-- 输入文档摘要 -->
          <NCard v-if="detail.document_content" title="输入文档（摘要）" :bordered="false" class="detail-card">
            <NScrollbar style="max-height:200px">
              <pre class="content-pre">{{ detail.document_content }}</pre>
            </NScrollbar>
          </NCard>

          <!-- 适配自检审核（报告末尾章节） -->
          <NCard
            v-if="detail.audit_report"
            title="自检审核结果"
            :bordered="false"
            class="detail-card llm-card"
          >
            <template #header-extra>
              <NTag v-if="detail.audit_skill" size="small" type="warning">{{ detail.audit_skill }}</NTag>
              <NTag size="small" type="info" style="margin-left:6px">{{ detail.audit_report.length }} 字</NTag>
            </template>

            <!-- 审核摘要表 -->
            <div v-if="detail.audit_summary?.length" class="audit-summary-table-wrap">
              <table class="audit-summary-table">
                <thead>
                  <tr>
                    <th>检查环节</th>
                    <th>结果</th>
                    <th>说明</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in detail.audit_summary" :key="row.key">
                    <td class="audit-col-label">{{ row.label }}</td>
                    <td class="audit-col-status">
                      <NTag size="small" :type="auditStatusTagType(row.status)" :bordered="false">
                        {{ AUDIT_STATUS_LABEL[row.status] }}
                      </NTag>
                    </td>
                    <td class="audit-col-reason">{{ row.reason }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <NDivider v-if="detail.audit_summary?.length" style="margin: 14px 0 12px" />

            <div class="audit-detail-label">完整审核原文</div>
            <NScrollbar style="max-height:480px">
              <pre class="content-pre llm-pre">{{ detail.audit_report }}</pre>
            </NScrollbar>
          </NCard>

          <!-- AI 分析结果 -->
          <NCard title="AI 分析结果" :bordered="false" class="detail-card llm-card">
            <template #header-extra>
              <NTag size="small" type="info">{{ detail.llm_response ? detail.llm_response.length + ' 字' : '无' }}</NTag>
            </template>
            <NEmpty v-if="!detail.llm_response" size="small" description="无 AI 输出内容" />
            <NScrollbar v-else style="max-height:600px">
              <pre class="content-pre llm-pre">{{ detail.llm_response }}</pre>
            </NScrollbar>
          </NCard>

          <!-- 操作按钮 -->
          <NSpace style="margin-top:8px">
            <NButton type="primary"
              @click="router.push({ name: 'tahp.executor', query: { module: detail.module, domain: detail.domain } })">
              以相同参数重新执行
            </NButton>
            <NButton @click="router.push({ name: 'tahp.tasks', query: { task_id: detail.task_id } })">
              在任务列表中查看
            </NButton>
            <NButton @click="backToList">返回报告列表</NButton>
          </NSpace>
        </div>
      </NSpin>
    </template>
  </div>
</template>

<style scoped>
.tahp-reports { padding: 24px; max-width: 1400px; margin: 0 auto; }

.page-header { margin-bottom: 20px; }
.header-row { display: flex; align-items: center; justify-content: space-between; margin: 6px 0 2px; }
.header-row h1 { margin: 0; font-size: 22px; font-weight: 600; }
.subtitle { color: #888; margin: 0; font-size: 13px; }

/* ── 列表卡片 ── */
.report-card { cursor: pointer; transition: box-shadow .15s; }
.report-card:hover { box-shadow: 0 4px 18px rgba(0,0,0,.12); }
.card-header { display: flex; align-items: center; justify-content: space-between; }
.card-title { display: flex; align-items: center; gap: 8px; }
.module-tag { font-size: 12px; font-weight: 600; color: var(--n-text-color-3, #888); }
.card-time { font-size: 11px; color: #aaa; }
.card-task-id { font-size: 11px; color: #888; margin-bottom: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.card-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; }
.stat-item { display: flex; flex-direction: column; gap: 2px; }
.stat-label { font-size: 11px; color: #aaa; }
.stat-value { font-size: 13px; font-weight: 500; color: var(--n-text-color, #333); }
.stat-value.small { font-size: 11px; font-weight: 400; }
.stat-value.highlight { color: #18a058; font-weight: 600; }

/* ── 详情布局 ── */
.detail-layout { display: flex; flex-direction: column; gap: 16px; }
.detail-card { border-radius: 8px; }
.llm-card { border-left: 3px solid #2080f0; }
.skill-ref-row {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 8px 0; border-bottom: 1px solid var(--n-border-color, #eee);
}
.skill-ref-row:last-child { border-bottom: none; }
.skill-path { font-size: 12px; color: #2080f0; word-break: break-all; flex: 1; min-width: 200px; }

.file-path { display: flex; align-items: flex-start; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--n-border-color, #eee); }
.file-path:last-child { border-bottom: none; }
.file-icon { flex-shrink: 0; margin-top: 2px; }
.file-path-main { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.file-path code { font-size: 12px; color: #10b981; word-break: break-all; }
.file-meta { font-size: 11px; color: #888; }

.content-pre {
  margin: 0;
  font-size: 12px;
  font-family: 'Consolas', 'Menlo', monospace;
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.6;
  color: var(--n-text-color, #333);
}
.llm-pre { font-size: 13px; line-height: 1.7; }

.audit-summary-table-wrap { overflow-x: auto; margin-bottom: 4px; }
.audit-summary-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.audit-summary-table th,
.audit-summary-table td {
  padding: 10px 12px;
  border: 1px solid var(--n-border-color, #eee);
  text-align: left;
  vertical-align: top;
}
.audit-summary-table th {
  background: var(--n-table-header-color, rgba(0,0,0,.02));
  font-weight: 600;
  white-space: nowrap;
}
.audit-col-label { width: 168px; font-weight: 500; white-space: nowrap; }
.audit-col-status { width: 88px; }
.audit-col-reason { color: var(--n-text-color-2, #666); line-height: 1.5; }
.audit-detail-label { font-size: 12px; color: #888; margin-bottom: 8px; }
</style>
