<template>
  <section class="crash-page">
    <div class="topbar">
      <div>
        <p class="eyebrow">Crash Analysis</p>
        <h1 class="page-title">GKI 死机故障分析</h1>
        <p v-if="!isEmbedded" class="page-desc">两种入口：分析两个 Tag 之间哪笔 patch 引入问题，或只输入当前 GKI Tag，检索社区/谷歌最新提交是否已有修复。</p>
      </div>
      <button class="btn" @click="refreshHistory">刷新历史</button>
    </div>

    <div class="workspace-layout crash-workspace">
      <div class="workspace-left crash-left">
        <div class="card card-pad crash-create">
          <div class="section-title">
            <div>
              <h2>新建死机分析</h2>
              <p>选择分析模式并提交任务</p>
            </div>
            <div class="segmented" role="tablist" aria-label="分析类型">
              <button
                type="button"
                :class="{ active: form.mode === 'interval' }"
                @click="form.mode = 'interval'"
              >
                升级区间
              </button>
              <button
                type="button"
                :class="{ active: form.mode === 'current_tag' }"
                @click="form.mode = 'current_tag'"
              >
                当前 Tag
              </button>
            </div>
          </div>
          <div class="form-grid">
            <template v-if="form.mode === 'interval'">
              <div class="field">
                <label>From Tag</label>
                <TagSelect
                  v-model="form.from_tag"
                  :options="repoTags"
                  :loading="tagsLoading"
                  :empty-hint="tagsHint"
                  placeholder="如 android13 2025-09 r9"
                />
              </div>
              <div class="field">
                <label>To Tag</label>
                <TagSelect
                  v-model="form.to_tag"
                  :options="repoTags"
                  :loading="tagsLoading"
                  :empty-hint="tagsHint"
                  placeholder="如 android13 2026-03 r16"
                />
              </div>
            </template>
            <div v-else class="field full">
              <label>当前 GKI Tag</label>
              <TagSelect
                v-model="form.to_tag"
                :options="repoTags"
                :loading="tagsLoading"
                :empty-hint="tagsHint"
                placeholder="如 android13 2026-03 r16"
              />
            </div>
            <div class="field full">
              <label>死机日志</label>
              <textarea
                v-model="form.crash_log"
                class="textarea mono crash-log-input"
                placeholder="粘贴 panic / oops / watchdog 日志，或已有分析结果"
              ></textarea>
              <button
                type="button"
                class="crash-upload-row"
                :class="{ dragging }"
                @click="fileInputRef?.click()"
                @dragover.prevent="dragging = true"
                @dragleave.prevent="dragging = false"
                @drop.prevent="onFileDrop"
              >
                {{ uploadHint }}
              </button>
              <input
                ref="fileInputRef"
                type="file"
                class="hidden-file"
                accept=".txt,.log,.dmesg,.kernel,.yaml,.yml,.json,.md"
                @change="onFileChange"
              />
            </div>
          </div>
          <div class="toolbar crash-create-actions">
            <button class="btn primary" :disabled="submitting" @click="startCrashAnalysis">
              {{ submitting ? '分析中...' : '开始分析' }}
            </button>
          </div>
          <div v-if="error" class="message error" style="margin-top: 14px">{{ error }}</div>
        </div>

        <div class="card card-pad crash-history-card">
          <div class="section-title">
            <div>
              <h2>历史记录</h2>
              <p>点击查看已有结果</p>
            </div>
          </div>
          <div class="history-toolbar">
            <label class="history-select-all">
              <input v-model="selectAll" type="checkbox" @change="toggleSelectAll" />
              <span>全选</span>
            </label>
            <button v-if="selectedIds.length" class="btn danger btn-sm" @click="batchDeleteCrash">
              批量删除 ({{ selectedIds.length }})
            </button>
          </div>
          <div v-if="history.length" class="workspace-list">
            <div
              v-for="item in history"
              :key="item.id || item.crash_id"
              class="history-item"
              :class="{
                active: activeCrashId === (item.id || item.crash_id),
                loading: loadingCrashId === (item.id || item.crash_id),
              }"
            >
              <input
                type="checkbox"
                class="history-cb"
                :value="item.id || item.crash_id"
                :checked="selectedIds.includes(item.id || item.crash_id)"
                @click.stop
                @change="toggleSelect(item.id || item.crash_id, ($event.target as HTMLInputElement).checked)"
              />
              <button class="history-main" @click="selectCrash(item.id || item.crash_id)">
                <div class="history-tags">{{ historyTitle(item) }}</div>
                <div class="history-meta">
                  <span class="pill" :class="statusTone(historyItemStatus(item))">{{ statusLabel(historyItemStatus(item)) }}</span>
                  <span v-if="causeBadge(item)" :class="causeBadge(item)?.class">{{ causeBadge(item)?.text }}</span>
                  <span v-if="item.elapsed_seconds" class="muted">{{ Math.round(item.elapsed_seconds) }}s</span>
                  <span class="muted">{{ formatDate(item.created_at) }}</span>
                </div>
              </button>
              <div class="history-actions">
                <button
                  class="btn-icon"
                  title="下载报告"
                  :disabled="historyItemStatus(item) !== 'completed'"
                  @click.stop="downloadReport(item.id || item.crash_id)"
                >
                  下载
                </button>
                <button class="btn-icon danger-text" title="删除" @click.stop="deleteHistory(item.id || item.crash_id)">
                  删除
                </button>
              </div>
            </div>
          </div>
          <div v-else class="empty">暂无死机分析记录</div>
        </div>
      </div>

      <aside class="workspace-detail-shell">
        <div class="workspace-detail">
        <div v-if="activeCrash" class="card card-pad crash-report-panel">
          <div v-if="loadingCrashId" class="detail-banner">
            正在加载诊断详情：{{ shortId(loadingCrashId) }}
          </div>

          <div class="section-title">
            <div>
              <h2>{{ detailTitle }}</h2>
              <p class="mono">{{ activeCrash.id || activeCrash.crash_id }}</p>
            </div>
            <div class="toolbar">
              <span class="pill" :class="statusTone(headerStatus)">{{ statusLabel(headerStatus) }}</span>
              <button
                v-if="currentStatus === 'completed'"
                class="btn primary"
                @click="downloadReport(activeCrash.id || activeCrash.crash_id)"
              >
                下载完整报告
              </button>
            </div>
          </div>

          <div v-if="showProgress" class="crash-progress card card-pad">
            <div class="split">
              <strong>{{ progressPhaseName }}</strong>
              <span class="muted">{{ elapsedText }}</span>
            </div>
            <div class="progress" :class="{ failed: currentStatus === 'failed' }" style="margin: 10px 0">
              <span :style="{ width: `${progressPercent}%` }"></span>
            </div>
            <div class="crash-progress-current">{{ progress.message || progressMsg }}</div>
            <div class="phase-tags">
              <span
                v-for="(phase, index) in activePhases"
                :key="phase"
                class="phase-tag"
                :class="phaseTagClass(index)"
              >
                {{ PHASE_NAMES[phase] }}
              </span>
            </div>
            <ol v-if="progressSteps.length" ref="progressLogRef" class="crash-progress-log">
              <li v-for="(step, index) in progressSteps" :key="`${step.elapsed_seconds}-${index}`">
                <span class="crash-progress-log-time">{{ step.elapsed_seconds || 0 }}s</span>
                <span class="crash-progress-log-phase">{{ PHASE_NAMES[step.phase] || step.phase }}</span>
                <span class="crash-progress-log-msg">{{ step.message }}</span>
              </li>
            </ol>
          </div>

          <template v-if="currentStatus === 'completed'">
            <div class="summary-grid">
              <div class="summary-item">
                <div class="summary-val">{{ crashSummary.crash_type || '未知' }}</div>
                <div class="summary-key">死机类型</div>
              </div>
              <div class="summary-item">
                <div class="summary-val">{{ crashSummary.crash_function || '未知' }}</div>
                <div class="summary-key">崩溃函数</div>
              </div>
              <div class="summary-item">
                <div class="summary-val">{{ crashSummary.crash_module || '未知' }}</div>
                <div class="summary-key">相关模块</div>
              </div>
              <div class="summary-item">
                <div class="summary-val" :class="causeValClass">{{ causeText }}</div>
                <div class="summary-key">{{ causeKey }}</div>
              </div>
            </div>

            <div class="result-card">
              <h3>死机分析详情</h3>
              <div class="kv-row">
                <span class="kv-k">调用栈摘要</span>
                <span class="kv-v"><code>{{ crashSummary.call_stack_summary || '-' }}</code></span>
              </div>
              <div v-if="crashSummary.bug_class" class="kv-row">
                <span class="kv-k">问题分类</span>
                <span class="kv-v">{{ crashSummary.bug_class }}</span>
              </div>
              <div v-if="crashSummary.crash_site_function" class="kv-row">
                <span class="kv-k">崩溃现场函数</span>
                <span class="kv-v"><code>{{ crashSummary.crash_site_function }}</code></span>
              </div>
              <div v-if="crashSummary.pc_symbol" class="kv-row">
                <span class="kv-k">PC / RIP</span>
                <span class="kv-v"><code>{{ crashSummary.pc_symbol }}</code></span>
              </div>
              <div v-if="crashSummary.fault_addr && crashSummary.fault_addr !== '未知'" class="kv-row">
                <span class="kv-k">出错地址</span>
                <span class="kv-v"><code>{{ crashSummary.fault_addr }}</code></span>
              </div>
              <template v-if="crashSummary.crash_mechanism">
                <h4>机制说明</h4>
                <div class="info-box blue">{{ crashSummary.crash_mechanism }}</div>
              </template>
              <template v-if="sourceSnippets.length">
                <h4>崩溃点源码（{{ crashSummary.source_tag || '-' }}）</h4>
                <div
                  v-if="crashSummary.crash_source_statement"
                  class="info-box blue"
                >
                  <strong>死在：</strong>{{ crashSummary.crash_source_statement }}
                </div>
                <div
                  v-for="(snip, index) in sourceSnippets"
                  :key="`${snip.path}-${snip.line}-${index}`"
                  class="source-snip"
                >
                  <div class="kv-row">
                    <span class="kv-k">位置</span>
                    <span class="kv-v"><code>{{ sourceLocation(snip) }}</code></span>
                  </div>
                  <p v-if="snip.missing" class="muted">仓库中未能取出该文件</p>
                  <pre v-else class="diff-view">{{ snip.text }}</pre>
                </div>
              </template>
              <p
                v-else-if="crashSummary.source_missing_reason"
                class="muted"
              >{{ crashSummary.source_missing_reason }}</p>
              <template v-if="latestCompare.latest_status || latestCompare.summary">
                <h4>对照社区最新源码（{{ latestCompare.latest_ref || '-' }}）</h4>
                <div class="info-box" :class="latestCompareBoxClass">
                  <strong>{{ latestCompareLabel }}</strong>
                  <div v-if="latestCompare.summary">{{ latestCompare.summary }}</div>
                  <div v-if="latestCompare.code_change"><strong>代码变化：</strong>{{ latestCompare.code_change }}</div>
                  <div v-if="latestCompare.fix_evidence"><strong>依据：</strong>{{ latestCompare.fix_evidence }}</div>
                </div>
                <div
                  v-for="(snip, index) in latestSourceSnippets"
                  :key="`latest-${snip.path}-${index}`"
                  class="source-snip"
                >
                  <div class="kv-row">
                    <span class="kv-k">最新</span>
                    <span class="kv-v"><code>{{ snip.path || '-' }}</code></span>
                  </div>
                  <p v-if="snip.missing" class="muted">最新 revision 未能取出该文件</p>
                  <pre v-else class="diff-view">{{ snip.text }}</pre>
                </div>
              </template>
              <template v-if="dependencyAnalysis">
                <h4>依赖关系分析</h4>
                <div class="info-box">{{ dependencyAnalysis }}</div>
              </template>
              <h4>死机现象描述</h4>
              <div class="info-box" :class="isCurrentTagMode ? 'blue' : (isCausedByMerge ? 'red' : 'green')">
                {{ crashSummary.crash_description || '-' }}
              </div>
              <h4>{{ isCurrentTagMode ? '检索说明' : '归因分析' }}</h4>
              <div class="info-box blue">
                <template v-if="!isCurrentTagMode"><strong>原因：</strong></template>{{ explanation || '-' }}
              </div>
            </div>

            <div v-if="!isCurrentTagMode" class="result-card">
              <h3>疑似问题 Patch ({{ suspectedPatches.length }})</h3>
              <div v-if="suspectedPatches.length" class="patch-card-list">
                <div v-for="(patch, index) in suspectedPatches" :key="patch.sha || index" class="patch-card">
                  <div class="patch-card-header">
                    <div class="patch-card-main">
                      <code class="patch-sha">{{ shortId(patch.sha, 12) }}</code>
                      <span class="patch-title">{{ patch.title || patch.subject || '-' }}</span>
                      <span class="pill" :class="patch.causation === '直接' ? 'success' : 'warning'">
                        {{ patch.causation || '间接' }}
                      </span>
                    </div>
                    <div class="patch-card-meta"><strong>可疑原因：</strong>{{ patch.reason || '-' }}</div>
                    <div v-if="patch.related_files" class="patch-files mono">{{ patch.related_files }}</div>
                  </div>
                  <details v-if="patch.commit_message || patch.diff" class="patch-details">
                    <summary class="patch-details-toggle">查看 Commit 信息和修改内容</summary>
                    <div class="patch-details-content">
                      <div v-if="patch.commit_message" class="detail-section">
                        <h5>Commit Message</h5>
                        <pre class="commit-msg">{{ patch.commit_message }}</pre>
                      </div>
                      <div v-if="patch.diff" class="detail-section">
                        <h5>Diff</h5>
                        <pre class="diff-view">{{ patch.diff }}</pre>
                      </div>
                    </div>
                  </details>
                  <details v-if="patch.llm_analysis" class="patch-details llm-details">
                    <summary class="patch-details-toggle llm-toggle">查看代码分析报告 (LLM)</summary>
                    <div class="patch-details-content">
                      <div v-if="patch.llm_analysis.score || patch.llm_analysis.recommendation" class="llm-score-row">
                        <span class="llm-score-badge" :class="llmScoreClass(patch.llm_analysis.score)">
                          评分: {{ patch.llm_analysis.score || 0 }}
                        </span>
                        <span class="llm-rec">{{ patch.llm_analysis.recommendation || '' }}</span>
                      </div>
                      <div v-if="patch.llm_analysis.key_risk" class="llm-risk">
                        <strong>关键风险：</strong>{{ patch.llm_analysis.key_risk }}
                      </div>
                      <div v-if="patch.llm_analysis.summary" class="detail-section">
                        <h5>修改解读</h5>
                        <div class="info-box">{{ patch.llm_analysis.summary }}</div>
                      </div>
                      <div v-if="patch.llm_analysis.code_changes?.length" class="detail-section">
                        <h5>代码变更分析</h5>
                        <ul class="llm-changes">
                          <li v-for="(change, ci) in patch.llm_analysis.code_changes" :key="ci">
                            <code>{{ change.location || '' }}</code>：{{ change.explanation || '' }}
                          </li>
                        </ul>
                      </div>
                      <div v-if="patch.llm_analysis.problem_solved" class="detail-section">
                        <h5>问题解决结论</h5>
                        <div class="info-box green">{{ patch.llm_analysis.problem_solved }}</div>
                      </div>
                      <div v-if="patch.llm_analysis.introducer" class="detail-section">
                        <h5>引入问题分析</h5>
                        <div class="info-box">{{ patch.llm_analysis.introducer }}</div>
                      </div>
                      <div v-if="patch.llm_analysis.test_suggestions" class="detail-section">
                        <h5>测试建议</h5>
                        <div class="info-box blue">{{ patch.llm_analysis.test_suggestions }}</div>
                      </div>
                    </div>
                  </details>
                </div>
              </div>
              <div v-else class="empty">未识别出疑似问题 patch</div>
            </div>

            <div class="result-card">
              <h3>后续修复提交 ({{ fixCommits.length }})</h3>
              <p v-if="fixSearchHint" class="muted">{{ fixSearchHint }}</p>
              <div v-if="fixCommits.length" class="table-wrap">
                <div class="table-scroll">
                  <table class="data-table">
                    <thead>
                      <tr>
                        <th>SHA</th>
                        <th>标题</th>
                        <th>类型</th>
                        <th>置信度</th>
                        <th>原因</th>
                        <th>依据</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="fix in fixCommits" :key="fix.sha">
                        <td class="mono">
                          <a
                            v-if="fixCommitUrl(fix)"
                            class="sha-link"
                            :href="fixCommitUrl(fix)"
                            target="_blank"
                            rel="noopener"
                            :title="'打开原始 patch：' + fixCommitUrl(fix)"
                          >{{ shortId(fix.sha, 12) }}</a>
                          <template v-else>{{ shortId(fix.sha, 12) }}</template>
                        </td>
                        <td>{{ fix.title || '-' }}</td>
                        <td><span class="pill muted">{{ fix.fix_type || '-' }}</span></td>
                        <td><span class="pill info">{{ fix.confidence || '-' }}</span></td>
                        <td>{{ fix.reason || '-' }}</td>
                        <td>{{ fix.via === 'source_diff' ? '源码 diff' : '标题检索' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
              <div v-else class="muted">{{ fixEmptyText }}</div>
            </div>

            <div v-if="hasRecommendations" class="result-card">
              <h3>建议</h3>
              <div v-if="recommendations.immediate_actions">
                <h4>紧急措施</h4>
                <div class="info-box red">{{ recommendations.immediate_actions }}</div>
              </div>
              <div v-if="recommendations.test_suggestions">
                <h4>测试验证建议</h4>
                <div class="info-box blue">{{ recommendations.test_suggestions }}</div>
              </div>
              <div v-if="recommendations.next_steps">
                <h4>后续排查步骤</h4>
                <div class="info-box green">{{ recommendations.next_steps }}</div>
              </div>
            </div>
          </template>
        </div>
        <div v-else class="card detail-empty">
          <div>
            <strong>请选择一条历史记录</strong>
            <span>点击左侧记录后，诊断结果会在这里显示。</span>
          </div>
        </div>
        </div>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { api, formatDate, shortId, statusTone, wsUrl } from '../api'
import { isEmbeddedMode } from '../composables/useEmbeddedNav'
import { useRepoTags } from '../composables/useRepoTags'
import TagSelect from '../components/TagSelect.vue'

const isEmbedded = isEmbeddedMode()
const { repoTags, tagsLoading, tagsHint, loadRepoTags } = useRepoTags()
const PHASES_INTERVAL = ['fetching', 'squash_diff', 'crash_analysis', 'enrich', 'find_fix', 'report'] as const
const PHASES_CURRENT = ['crash_analysis', 'find_fix', 'report'] as const
const PHASE_NAMES: Record<string, string> = {
  fetching: '获取提交列表',
  squash_diff: '生成 Squash Diff',
  crash_analysis: 'LLM 分析死机日志',
  enrich: '获取 Patch 详情',
  find_fix: '对照最新源码 / 查找修复',
  report: '生成报告',
}

const form = reactive({
  mode: 'interval' as 'interval' | 'current_tag',
  from_tag: '',
  to_tag: '',
  crash_log: '',
})
const history = ref<any[]>([])
const activeCrashId = ref('')
const loadingCrashId = ref('')
const activeCrash = ref<any | null>(null)
const progress = ref<any>({})
const submitting = ref(false)
const error = ref('')
const uploadHint = ref('点击或拖入日志文件')
const dragging = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const progressLogRef = ref<HTMLElement | null>(null)
const selectedIds = ref<string[]>([])
const selectAll = ref(false)
const elapsedStart = ref(0)
const elapsedSeconds = ref(0)
let socket: WebSocket | null = null
let elapsedTimer: number | null = null

const currentStatus = computed(() => progress.value.status || activeCrash.value?.status || '')
const isRunningStatus = computed(() => {
  const status = currentStatus.value
  return !!status && status !== 'completed' && status !== 'failed'
})
const showProgress = computed(() => isRunningStatus.value || currentStatus.value === 'failed')
const headerStatus = computed(() => {
  const status = currentStatus.value
  if (status === 'completed' || status === 'failed' || status === 'pending' || status === 'analyzing') return status
  if (PHASE_NAMES[status]) return 'analyzing'
  return status
})
const progressPhaseName = computed(() => PHASE_NAMES[currentStatus.value] || statusLabel(headerStatus.value))
const progressSteps = computed(() => (Array.isArray(progress.value.steps) ? progress.value.steps : []))
const progressMsg = computed(() => {
  if (currentStatus.value === 'completed') return '分析完成'
  if (currentStatus.value === 'failed') return progress.value.message || '分析失败'
  return progress.value.message || PHASE_NAMES[currentStatus.value] || '准备中...'
})

const crashSummary = computed(() => {
  const raw = activeCrash.value?.crash_summary
  if (!raw) return {}
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw)
    } catch {
      return {}
    }
  }
  return raw
})

const sourceSnippets = computed(() => {
  const rows = crashSummary.value.crash_source_snippets
  return Array.isArray(rows) ? rows : []
})

const latestSourceSnippets = computed(() => {
  const rows = crashSummary.value.latest_source_snippets
  return Array.isArray(rows) ? rows : []
})

const latestCompare = computed(() => crashSummary.value.latest_compare || {})

const latestCompareLabel = computed(() => {
  const status = latestCompare.value.latest_status
  if (status === 'likely_fixed') return '最新源码已避开该崩溃路径'
  if (status === 'still_buggy') return '最新源码仍可能存在该问题'
  if (status === 'cannot_compare') return '未能对照最新源码'
  return '对照结果'
})

const latestCompareBoxClass = computed(() => {
  const status = latestCompare.value.latest_status
  if (status === 'likely_fixed') return 'green'
  if (status === 'still_buggy') return 'red'
  return 'blue'
})

function sourceLocation(snip: { path?: string; line?: number; function?: string }) {
  const path = snip?.path || ''
  const line = Number(snip?.line || 0)
  const func = snip?.function ? ` ${snip.function}()` : ''
  return line ? `${path}:${line}${func}` : `${path}${func}`
}

const suspectedPatches = computed(() => parseJsonArray(activeCrash.value?.suspected_patches || activeCrash.value?.related_patches))
const fixCommits = computed(() => parseJsonArray(activeCrash.value?.fix_commits))
const recommendations = computed(() => {
  const raw = activeCrash.value?.recommendations
  if (!raw) return {}
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw)
    } catch {
      return {}
    }
  }
  return raw
})
const hasRecommendations = computed(
  () =>
    recommendations.value.immediate_actions ||
    recommendations.value.test_suggestions ||
    recommendations.value.next_steps,
)

const isCausedByMerge = computed(() => activeCrash.value?.is_caused_by_merge === 1)
const isCurrentTagMode = computed(() => {
  const mode = crashSummary.value.analysis_mode || progress.value.mode
  if (mode) return mode === 'current_tag'
  return !activeCrash.value?.from_tag && !!activeCrash.value?.to_tag
})
const activePhases = computed(() =>
  isCurrentTagMode.value ? [...PHASES_CURRENT] : [...PHASES_INTERVAL],
)
const detailTitle = computed(() => {
  if (!activeCrash.value) return ''
  if (isCurrentTagMode.value) return `当前 ${activeCrash.value.to_tag || '-'} · 查社区修复`
  return `${activeCrash.value.from_tag || '-'} → ${activeCrash.value.to_tag || '-'}`
})
const confidence = computed(() => crashSummary.value.confidence || activeCrash.value?.confidence || '低')
const causationType = computed(() => crashSummary.value.causation_type || activeCrash.value?.causation_type || '无')
const explanation = computed(() => crashSummary.value.explanation || activeCrash.value?.explanation || '')
const dependencyAnalysis = computed(() => crashSummary.value.dependency_analysis || '')
const causeText = computed(() => {
  if (isCurrentTagMode.value) {
    if (fixCommits.value.length) return '已找到社区/谷歌修复'
    if (latestCompare.value.latest_status === 'likely_fixed') return '最新源码已避开，未定位到具体提交'
    if (latestCompare.value.latest_status === 'still_buggy') return '最新源码仍可能有该问题'
    return '未找到社区/谷歌修复'
  }
  return isCausedByMerge.value
    ? `是（${causationType.value === '直接' ? '直接' : '间接'}合入代码引起）`
    : '否（非合入代码引起）'
})
const causeKey = computed(() => {
  if (isCurrentTagMode.value) return '社区/谷歌修复'
  return `是否合入代码引起 | 置信度: ${confidence.value} | 因果类型: ${causationType.value}`
})
const causeValClass = computed(() => {
  if (isCurrentTagMode.value) {
    if (fixCommits.value.length || latestCompare.value.latest_status === 'likely_fixed') return 'cause-no'
    return 'cause-yes'
  }
  return isCausedByMerge.value ? 'cause-yes' : 'cause-no'
})
const fixSearchHint = computed(() => {
  const search = crashSummary.value.fix_search
  if (!search?.search_from_tag) return ''
  const endRef = search.search_to_ref || 'HEAD'
  const source = search.fetch_source ? `，源 ${search.fetch_source}` : ''
  const strategy = search.strategy === 'source_compare_and_diff'
    ? '，依据：对照最新源码后读文件 diff'
    : ''
  return `检索范围 ${search.search_from_tag}..${endRef}，共 ${search.commits_after_tag || 0} 笔提交，筛出 ${search.candidates || 0} 笔候选${source}${strategy}`
})
const fixEmptyText = computed(() => {
  const search = crashSummary.value.fix_search
  if (latestCompare.value.latest_status === 'still_buggy') {
    return '最新源码仍可能走这次崩溃路径，因此没有把后续提交判成修复。'
  }
  if (latestCompare.value.latest_status === 'likely_fixed') {
    return '最新源码已避开该路径，但未能从后续 diff 中定位到具体提交。'
  }
  if (search && Number(search.commits_after_tag) === 0) {
    return search.empty_reason || '本地没有比该 Tag 更新的同系列提交。请 fetch 社区/谷歌对应分支后再查。'
  }
  return '未在当前 Tag 至社区/谷歌最新提交中找到与本次崩溃相关的修复'
})

const progressPercent = computed(() => {
  if (currentStatus.value === 'completed') return 100
  if (currentStatus.value === 'failed') return 100
  const currentIdx = activePhases.value.indexOf(progress.value.status || '')
  if (currentIdx >= 0) return Math.min(((currentIdx + 1) / activePhases.value.length) * 100, 100)
  return progress.value.percent !== undefined ? Number(progress.value.percent) : 10
})

const elapsedText = computed(() => {
  if (!elapsedSeconds.value) return ''
  return `已运行 ${elapsedSeconds.value}s`
})

function parseJsonArray(value: any) {
  if (Array.isArray(value)) return value
  if (!value) return []
  try {
    return JSON.parse(value)
  } catch {
    return []
  }
}

const DEFAULT_KERNEL_COMMON = 'https://android.googlesource.com/kernel/common'

function fixCommitUrl(fix: { sha?: string; commit_url?: string } | null | undefined): string {
  const direct = String(fix?.commit_url || '').trim()
  if (direct) return direct
  const sha = String(fix?.sha || '').trim()
  if (!sha) return ''
  const source = String(crashSummary.value?.fix_search?.fetch_source || '').trim()
  const base = (source.includes('://') ? source : DEFAULT_KERNEL_COMMON)
    .replace(/\.git$/i, '')
    .replace(/\/+$/, '')
  return `${base}/+/${sha}`
}

function statusLabel(status?: string) {
  const map: Record<string, string> = {
    completed: '已完成',
    analyzing: '分析中',
    failed: '失败',
    pending: '等待中',
  }
  if (map[status || '']) return map[status || '']
  if (status && PHASE_NAMES[status]) return '分析中'
  return status || '-'
}

function shortTag(tag?: string) {
  if (!tag) return '?'
  return tag.replace(/android\d+-[\d.]+-/, '')
}

function historyTitle(item: any) {
  if (!item?.from_tag && item?.to_tag) return `当前 ${shortTag(item.to_tag)} · 查修复`
  return `${shortTag(item?.from_tag)} → ${shortTag(item?.to_tag)}`
}

function historyItemStatus(item: any) {
  const id = item?.id || item?.crash_id
  if (id && id === activeCrashId.value) {
    const live = currentStatus.value
    if (live === 'completed' || live === 'failed' || live === 'pending') return live
    if (live === 'analyzing' || (live && PHASE_NAMES[live])) return 'analyzing'
  }
  if (item?.status && PHASE_NAMES[item.status]) return 'analyzing'
  return item?.status || ''
}

function patchHistoryStatus(crashId: string, status: string) {
  const item = history.value.find((row) => (row.id || row.crash_id) === crashId)
  if (!item) return
  if (status === 'completed' || status === 'failed' || status === 'pending') {
    item.status = status
  } else if (status) {
    item.status = 'analyzing'
  }
}

function causeBadge(item: any) {
  if (!item?.from_tag && item?.to_tag) {
    return { text: '查社区修复', class: 'cause-no' }
  }
  if (item.is_caused_by_merge === 1) return { text: '合入引起', class: 'cause-yes' }
  if (item.is_caused_by_merge === 0 && historyItemStatus(item) === 'completed') {
    return { text: '非合入引起', class: 'cause-no' }
  }
  return null
}

function llmScoreClass(score?: number) {
  const value = Number(score || 0)
  if (value >= 60) return 'high'
  if (value >= 30) return 'medium'
  return 'low'
}

function phaseTagClass(index: number) {
  const currentIdx = activePhases.value.indexOf(progress.value.status || '')
  if (currentIdx < 0) return ''
  if (index < currentIdx) return 'done'
  if (index === currentIdx) return 'active'
  return ''
}

function startElapsedTimer() {
  elapsedStart.value = Date.now()
  elapsedSeconds.value = 0
  stopElapsedTimer()
  elapsedTimer = window.setInterval(() => {
    elapsedSeconds.value = Math.round((Date.now() - elapsedStart.value) / 1000)
  }, 1000)
}

function stopElapsedTimer() {
  if (elapsedTimer) {
    window.clearInterval(elapsedTimer)
    elapsedTimer = null
  }
}

function readFile(file: File) {
  const reader = new FileReader()
  reader.onload = (event) => {
    form.crash_log = String(event.target?.result || '')
    uploadHint.value = `已加载 ${file.name} (${(file.size / 1024).toFixed(1)}KB)`
  }
  reader.readAsText(file)
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement
  if (input.files?.length) readFile(input.files[0])
}

function onFileDrop(event: DragEvent) {
  dragging.value = false
  const file = event.dataTransfer?.files?.[0]
  if (file) readFile(file)
}

function toggleSelect(id: string, checked: boolean) {
  if (checked) {
    if (!selectedIds.value.includes(id)) selectedIds.value.push(id)
  } else {
    selectedIds.value = selectedIds.value.filter((item) => item !== id)
  }
  selectAll.value = history.value.length > 0 && selectedIds.value.length === history.value.length
}

function toggleSelectAll() {
  if (selectAll.value) {
    selectedIds.value = history.value.map((item) => item.id || item.crash_id)
  } else {
    selectedIds.value = []
  }
}

function downloadReport(crashId: string) {
  window.open(`/api/crash-analysis/${crashId}/report`, '_blank')
}

async function loadHistory(preserveSelection = false) {
  const keep = preserveSelection ? [...selectedIds.value] : []
  const data = await api.get<any>('/api/crash-analyses')
  history.value = data.items || []
  if (preserveSelection) {
    const ids = new Set(history.value.map((item) => item.id || item.crash_id))
    selectedIds.value = keep.filter((id) => ids.has(id))
    selectAll.value = history.value.length > 0 && selectedIds.value.length === history.value.length
  } else {
    selectAll.value = false
    selectedIds.value = []
  }
}

async function refreshHistory() {
  const currentId = activeCrashId.value
  await loadHistory(true)
  if (!currentId) return
  const exists = history.value.some((item) => (item.id || item.crash_id) === currentId)
  if (exists) await selectCrash(currentId)
}

async function selectCrash(crashId: string) {
  error.value = ''
  activeCrashId.value = crashId
  loadingCrashId.value = crashId
  if (socket) socket.close()
  try {
    activeCrash.value = await api.get<any>(`/api/crash-analysis/${crashId}`)
    progress.value = { status: activeCrash.value.status, message: activeCrash.value.message || '' }
    if (activeCrash.value.status !== 'completed' && activeCrash.value.status !== 'failed') {
      startElapsedTimer()
      connectWs(crashId)
    } else {
      stopElapsedTimer()
    }
  } catch (err: any) {
    error.value = err.message || String(err)
  } finally {
    loadingCrashId.value = ''
  }
}

function connectWs(crashId: string) {
  if (socket) {
    socket.onmessage = null
    socket.close()
    socket = null
  }
  let terminalRefreshDone = false
  socket = new WebSocket(wsUrl(`/ws/crash-analysis/${crashId}`))
  socket.onmessage = (event) => {
    progress.value = JSON.parse(event.data || '{}')
    const status = String(progress.value.status || '')
    patchHistoryStatus(crashId, status)
    if ((status === 'completed' || status === 'failed') && !terminalRefreshDone) {
      terminalRefreshDone = true
      stopElapsedTimer()
      void selectCrash(crashId)
      void loadHistory(true)
    }
  }
}

async function deleteHistory(crashId: string) {
  if (!window.confirm('确定删除这条分析记录？')) return
  await api.delete(`/api/crash-analysis/${crashId}`)
  if (activeCrashId.value === crashId) {
    activeCrashId.value = ''
    activeCrash.value = null
    progress.value = {}
  }
  await refreshHistory()
}

async function batchDeleteCrash() {
  if (!selectedIds.value.length) return
  if (!window.confirm(`确定删除选中的 ${selectedIds.value.length} 条分析记录？`)) return
  await Promise.all(selectedIds.value.map((id) => api.delete(`/api/crash-analysis/${id}`)))
  if (selectedIds.value.includes(activeCrashId.value)) {
    activeCrashId.value = ''
    activeCrash.value = null
    progress.value = {}
  }
  await refreshHistory()
}

async function startCrashAnalysis() {
  if (form.mode === 'interval') {
    if (!form.from_tag.trim() || !form.to_tag.trim()) {
      error.value = '请填写起始和结束 Tag'
      return
    }
  } else if (!form.to_tag.trim()) {
    error.value = '请填写当前 GKI Tag'
    return
  }
  if (!form.crash_log.trim()) {
    error.value = '请提供死机日志'
    return
  }
  submitting.value = true
  error.value = ''
  try {
    const data = await api.post<any>('/api/crash-analysis', {
      mode: form.mode,
      from_tag: form.mode === 'interval' ? form.from_tag : '',
      to_tag: form.to_tag,
      crash_log: form.crash_log,
    })
    startElapsedTimer()
    await loadHistory()
    await selectCrash(data.crash_id)
  } catch (err: any) {
    error.value = err.message || String(err)
    stopElapsedTimer()
  } finally {
    submitting.value = false
  }
}

watch(
  () => progressSteps.value.length,
  async () => {
    await nextTick()
    const el = progressLogRef.value
    if (el) el.scrollTop = el.scrollHeight
  },
)

onMounted(async () => {
  void loadRepoTags()
  await loadHistory()
})

onBeforeUnmount(() => {
  if (socket) socket.close()
  stopElapsedTimer()
})
</script>

<style scoped>
.crash-page {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: calc(100vh - 118px);
}

.app-shell-embedded .crash-page {
  height: calc(100vh - 8px);
}

.crash-page .topbar {
  flex-shrink: 0;
  margin-bottom: 12px;
}

.crash-workspace {
  flex: 1 1 0;
  min-height: 0;
  align-items: stretch;
  height: auto;
}

.crash-left {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

.crash-create {
  flex: 0 0 auto;
  overflow: visible;
}

.crash-create :deep(.section-title) {
  margin-bottom: 8px;
}

.crash-create :deep(.crash-create-actions) {
  margin-top: 10px;
}

.crash-create :deep(.crash-upload-row) {
  margin-top: 6px;
  padding: 6px 10px;
}

.crash-history-card {
  flex: 1 1 0;
  min-height: 360px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.crash-history-card .section-title,
.crash-history-card .history-toolbar {
  flex-shrink: 0;
}

.crash-history-card .workspace-list {
  flex: 1 1 auto;
  min-height: 0;
  max-height: none;
  overflow: auto;
}

.crash-history-card .empty {
  flex: 1 1 auto;
  min-height: 0;
}

.crash-workspace :deep(.workspace-detail-shell) {
  position: relative;
  top: auto;
  height: 100%;
  max-height: none;
}

.crash-log-input {
  min-height: 72px;
}

.sha-link {
  color: #2563eb;
  text-decoration: none;
  font-weight: 600;
}

.sha-link:hover {
  text-decoration: underline;
}
</style>
