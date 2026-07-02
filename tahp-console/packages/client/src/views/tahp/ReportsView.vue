<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  NSpin, NEmpty, NDescriptions, NDescriptionsItem, NScrollbar, NDivider,
  NAlert, useMessage,
} from 'naive-ui'
import EaPageHead from '@/components/layout/EaPageHead.vue'
import EaCard from '@/components/layout/EaCard.vue'
import EaPill from '@/components/layout/EaPill.vue'
import EaSectionTitle from '@/components/layout/EaSectionTitle.vue'
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
  lcm: 'LCM',
  fp: '指纹',
  audio: '音频',
  charging: '充电',
  sensor: 'Sensor',
  video: 'Video',
  security: '安全',
  'mini-system': '小系统',
  modem: '通信Modem',
  'comm-framework': '通信框架',
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

function auditPillVariant(status: AuditCheckItem['status']): 'ok' | 'err' | 'warn' | 'muted' | 'info' {
  switch (status) {
    case 'pass': return 'ok'
    case 'fail': return 'err'
    case 'warn': return 'warn'
    case 'na': return 'muted'
    default: return 'info'
  }
}
</script>

<template>
  <div class="page page-wide">
    <EaPageHead
      :title="mode === 'detail' ? '任务报告详情' : '任务报告'"
      :subtitle="mode === 'detail' ? 'AI 适配执行详情、分析结果与文件修改记录' : '所有已完成任务的执行报告汇总，含文件修改与 AI 自检审核'"
    >
      <template v-if="mode === 'detail'" #breadcrumb>
        <div class="rep-breadcrumb">
          <a class="rep-crumb-link" @click.prevent="backToList">报告列表</a>
          <span class="rep-crumb-sep">/</span>
          <code class="rep-crumb-id">{{ taskId }}</code>
        </div>
      </template>
      <template #actions>
        <button type="button" class="ea-btn-ghost ea-btn-sm" @click="loadData">刷新</button>
        <button v-if="mode === 'detail'" type="button" class="ea-btn-ghost ea-btn-sm" @click="backToList">← 返回列表</button>
        <button v-else type="button" class="ea-btn-primary ea-btn-sm" @click="router.push({ name: 'tahp.adapt-debug' })">启动新任务</button>
      </template>
    </EaPageHead>

    <!-- ── 列表模式 ─────────────────────────────────────────────────────── -->
    <template v-if="mode === 'list'">
      <NSpin :show="listLoading">
        <NEmpty v-if="!listLoading && !summaries.length"
          description="暂无报告。执行任务后，报告将自动生成并显示在此处。"
          style="margin-top: 60px"
        >
          <template #extra>
            <button type="button" class="ea-btn-primary" @click="router.push({ name: 'tahp.adapt-debug' })">启动第一个任务</button>
          </template>
        </NEmpty>
        <div v-else class="ea-rep-grid">
          <EaCard
            v-for="s in summaries"
            :key="s.task_id"
            tag="button"
            class="ea-rep-card rep-card"
            @click="openTask(s.task_id)"
          >
            <div class="rc-top">
              <div class="ea-row">
                <EaPill variant="ok">已完成</EaPill>
                <span class="module-tag">{{ s.module || '-' }}</span>
              </div>
              <span class="card-time">{{ fmtRelTime(s.mtime) }}</span>
            </div>
            <div class="rc-id"><code>{{ s.task_id }}</code></div>
            <div class="rep-stats">
              <div class="rs">
                <span class="rs-k">域</span>
                <span class="rs-v">{{ s.domain_label || DOMAIN_LABELS[s.domain || ''] || s.domain || '-' }}</span>
              </div>
              <div class="rs">
                <span class="rs-k">耗时</span>
                <span class="rs-v">{{ fmtDuration(s.duration_ms) }}</span>
              </div>
              <div class="rs">
                <span class="rs-k">修改文件</span>
                <span class="rs-v" :class="{ hl: s.files_modified > 0 }">{{ s.files_modified }} 个</span>
              </div>
              <div class="rs">
                <span class="rs-k">完成时间</span>
                <span class="rs-v rs-v-sm">{{ fmtTime(s.completed_at) }}</span>
              </div>
            </div>
          </EaCard>
        </div>
      </NSpin>
    </template>

    <!-- ── 详情模式 ─────────────────────────────────────────────────────── -->
    <template v-else>
      <NSpin :show="detailLoading">
        <div v-if="!detailLoading && !detail">
          <NAlert type="error" title="报告不存在">
            未找到任务 <code>{{ taskId }}</code> 的报告。可能该任务尚未完成，或报告文件不存在。
          </NAlert>
          <button type="button" class="ea-btn-ghost ea-mt16" @click="backToList">返回列表</button>
        </div>

        <div v-if="detail" class="detail-layout">
          <!-- 任务元信息 -->
          <EaCard class="detail-block">
            <EaSectionTitle class="ea-mb0">任务信息</EaSectionTitle>
            <div class="ea-meta-grid ea-mt16">
              <div class="mg">
                <div class="mg-k">模块</div>
                <div class="mg-v mg-v-sm">{{ detail.module || '-' }}</div>
              </div>
              <div class="mg">
                <div class="mg-k">域</div>
                <div class="mg-v mg-v-sm">{{ domainDisplay(detail) }}</div>
              </div>
              <div class="mg">
                <div class="mg-k">耗时</div>
                <div class="mg-v mg-v-sm">{{ fmtDuration(detail.duration_ms) }}</div>
              </div>
              <div class="mg">
                <div class="mg-k">修改文件数</div>
                <div class="mg-v mg-v-sm">{{ detail.files_modified?.length ?? 0 }}</div>
              </div>
            </div>

            <NDivider style="margin: 16px 0 12px" />
            <NDescriptions :column="2" label-placement="left" size="small" bordered>
              <NDescriptionsItem label="Task ID" :span="2">
                <code class="mono-sm">{{ detail.task_id }}</code>
              </NDescriptionsItem>
              <NDescriptionsItem label="启动时间">{{ fmtTime(detail.started_at) }}</NDescriptionsItem>
              <NDescriptionsItem label="完成时间">{{ fmtTime(detail.completed_at) }}</NDescriptionsItem>
              <NDescriptionsItem v-if="detail.correction_of" label="纠偏自" :span="2">
                <code class="mono-sm">{{ detail.correction_of }}</code>
                <button type="button" class="ea-btn-ghost ea-btn-sm" style="margin-left:8px" @click="openTask(detail.correction_of!)">查看原任务</button>
              </NDescriptionsItem>
            </NDescriptions>
          </EaCard>

          <!-- 附加上下文 -->
          <EaCard v-if="detail.extra_context" class="detail-block">
            <EaSectionTitle>附加上下文</EaSectionTitle>
            <pre class="content-pre">{{ detail.extra_context }}</pre>
          </EaCard>

          <!-- 使用的 Skill（完整路径） -->
          <EaCard v-if="detail.skills_used?.length" class="detail-block">
            <EaSectionTitle>使用的 Skill</EaSectionTitle>
            <div v-for="sk in detail.skills_used" :key="sk.skill_id + sk.path" class="file-row">
              <EaPill variant="info">{{ sk.skill_id }}</EaPill>
              <code class="skill-path">{{ sk.path }}</code>
              <EaPill v-if="sk.source" variant="muted">{{ sk.source }}</EaPill>
            </div>
          </EaCard>

          <!-- 已修改文件 -->
          <EaCard v-if="detail.files_modified?.length" class="detail-block">
            <EaSectionTitle>已修改文件</EaSectionTitle>
            <div
              v-for="(f, idx) in (detail.file_changes?.length ? detail.file_changes : detail.files_modified!.map(p => ({ path: p, action: 'modify', tool: '' })))"
              :key="f.path + idx"
              class="file-row"
            >
              <span class="file-icon">{{ f.action === 'create' ? '🆕' : '✅' }}</span>
              <code>{{ f.path }}</code>
              <span v-if="f.tool" class="f-meta">{{ f.action === 'create' ? '新建' : '修改' }} · {{ f.tool }}</span>
            </div>
          </EaCard>
          <EaCard v-else class="detail-block">
            <EaSectionTitle>已修改文件</EaSectionTitle>
            <NEmpty size="small" description="本次任务未修改任何文件（纯分析结果）" />
          </EaCard>

          <!-- 输入文档摘要 -->
          <EaCard v-if="detail.document_content" class="detail-block">
            <EaSectionTitle>输入文档（摘要）</EaSectionTitle>
            <NScrollbar style="max-height:200px">
              <pre class="content-pre">{{ detail.document_content }}</pre>
            </NScrollbar>
          </EaCard>

          <!-- 适配自检审核（报告末尾章节） -->
          <EaCard v-if="detail.audit_report" class="detail-block llm-card llm-card-warn">
            <div class="ea-row ea-between">
              <EaSectionTitle class="ea-mb0">自检审核结果</EaSectionTitle>
              <div class="ea-row" style="gap:6px">
                <EaPill v-if="detail.audit_skill" variant="warn">{{ detail.audit_skill }}</EaPill>
                <EaPill variant="info">{{ detail.audit_report.length }} 字</EaPill>
              </div>
            </div>

            <!-- 审核摘要表 -->
            <div v-if="detail.audit_summary?.length" class="audit-table-wrap">
              <table class="audit-table">
                <thead>
                  <tr>
                    <th>检查环节</th>
                    <th>结果</th>
                    <th>说明</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in detail.audit_summary" :key="row.key">
                    <td class="audit-col-label"><b>{{ row.label }}</b></td>
                    <td class="audit-col-status">
                      <EaPill :variant="auditPillVariant(row.status)">{{ AUDIT_STATUS_LABEL[row.status] }}</EaPill>
                    </td>
                    <td class="audit-col-reason a-reason">{{ row.reason }}</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <NDivider v-if="detail.audit_summary?.length" style="margin: 14px 0 12px" />

            <div class="audit-detail-label">完整审核原文</div>
            <NScrollbar style="max-height:480px">
              <pre class="content-pre llm-pre">{{ detail.audit_report }}</pre>
            </NScrollbar>
          </EaCard>

          <!-- AI 分析结果 -->
          <EaCard class="detail-block llm-card llm-card-accent">
            <div class="ea-row ea-between">
              <EaSectionTitle class="ea-mb0">AI 分析结果</EaSectionTitle>
              <EaPill variant="info">{{ detail.llm_response ? detail.llm_response.length + ' 字' : '无' }}</EaPill>
            </div>
            <NEmpty v-if="!detail.llm_response" size="small" description="无 AI 输出内容" />
            <NScrollbar v-else style="max-height:600px">
              <pre class="content-pre llm-pre">{{ detail.llm_response }}</pre>
            </NScrollbar>
          </EaCard>

          <!-- 操作按钮 -->
          <div class="ea-row" style="gap:10px;margin-top:8px">
            <button
              type="button"
              class="ea-btn-primary"
              @click="router.push({ name: detail.domain === 'bug_analysis' ? 'tahp.bug-analysis' : 'tahp.adapt-debug', query: { module: detail.module, domain: detail.domain } })"
            >
              以相同参数重新执行
            </button>
            <button type="button" class="ea-btn-ghost" @click="backToList">返回报告列表</button>
          </div>
        </div>
      </NSpin>
    </template>
  </div>
</template>

<style scoped lang="scss">
.rep-breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 6px;
}

.rep-crumb-link {
  color: var(--accent);
  text-decoration: none;
  cursor: pointer;
  font-weight: 600;

  &:hover { text-decoration: underline; }
}

.rep-crumb-sep { color: var(--faint); }
.rep-crumb-id { font-size: 12px; color: var(--muted); }

.rep-card {
  text-align: left;
  width: 100%;
  font-family: inherit;
}

.rc-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.module-tag {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
}

.card-time {
  font-size: 11px;
  color: var(--faint);
}

.rc-id {
  font-size: 11px;
  color: var(--faint);
  margin-bottom: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;

  code { font-family: var(--font-code, 'JetBrains Mono', monospace); }
}

.rep-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
}

.rs {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.rs-k { font-size: 11px; color: var(--faint); }
.rs-v { font-size: 13px; font-weight: 600; color: var(--text); }
.rs-v-sm { font-size: 11px; font-weight: 400; }
.rs-v.hl { color: var(--success); font-weight: 700; }

.detail-layout {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.detail-block { margin-bottom: 0; }

.mg-v-sm { font-size: 15px !important; }

.mono-sm {
  font-size: 11px;
  word-break: break-all;
  font-family: var(--font-code, 'JetBrains Mono', monospace);
}

.llm-card { border-left: 3px solid var(--accent); }
.llm-card-warn { border-left-color: var(--warn); }
.llm-card-accent { border-left-color: var(--accent); }

.skill-path {
  font-size: 12px;
  color: var(--accent);
  word-break: break-all;
  flex: 1;
  min-width: 200px;
  font-family: var(--font-code, 'JetBrains Mono', monospace);
}

.file-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 0;
  border-bottom: 1px solid var(--line);
  font-size: 12.5px;

  &:last-child { border-bottom: none; }

  code {
    font-family: var(--font-code, 'JetBrains Mono', monospace);
    color: var(--success);
    word-break: break-all;
    flex: 1;
    min-width: 0;
    font-size: 12px;
  }
}

.f-meta {
  color: var(--muted);
  font-size: 11px;
  margin-left: auto;
  flex-shrink: 0;
}

.file-icon { flex-shrink: 0; }

.content-pre {
  margin: 0;
  font-size: 12px;
  font-family: var(--font-code, 'JetBrains Mono', monospace);
  white-space: pre-wrap;
  word-break: break-all;
  line-height: 1.6;
  color: var(--text);
}

.llm-pre { font-size: 13px; line-height: 1.7; }

.audit-table-wrap { overflow-x: auto; margin-top: 8px; }

.audit-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.audit-table th,
.audit-table td {
  padding: 10px 12px;
  border: 1px solid var(--line);
  text-align: left;
  vertical-align: top;
}

.audit-table th {
  background: var(--surface-2);
  font-weight: 700;
  white-space: nowrap;
}

.audit-col-label { width: 168px; white-space: nowrap; }
.audit-col-status { width: 88px; }
.a-reason { color: var(--muted); line-height: 1.5; }

.audit-detail-label {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 8px;
}
</style>
