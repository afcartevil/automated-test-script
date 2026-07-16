<template>
  <section>
    <div class="topbar">
      <div>
        <p class="eyebrow">Crash Analysis</p>
        <h1 class="page-title">GKI 升级死机分析</h1>
        <p v-if="!isEmbedded" class="page-desc">提交升级区间和死机日志，实时查看分析阶段、可疑 patch 与结论。</p>
      </div>
      <button class="btn" @click="refreshHistory">刷新历史</button>
    </div>

    <div class="workspace-layout">
      <div class="workspace-left">
        <div class="card card-pad">
          <div class="section-title">
            <div>
              <h2>新建死机分析</h2>
              <p>输入 tag 区间和关键日志</p>
            </div>
          </div>
          <div class="form-grid">
            <div class="field">
              <label>From Tag</label>
              <input v-model="form.from_tag" class="input mono" placeholder="如 2025-06_r4" />
            </div>
            <div class="field">
              <label>To Tag</label>
              <input v-model="form.to_tag" class="input mono" placeholder="如 2025-12_r4" />
            </div>
            <div class="field full">
              <label>死机日志 / 分析结果</label>
              <textarea
                v-model="form.crash_log"
                class="textarea mono"
                placeholder="粘贴死机日志内容，或已完成的死机分析结果...&#10;&#10;• 支持 kernel panic、oops、watchdog timeout 等各类死机日志&#10;• 支持直接粘贴已有的死机分析结果，系统将自动识别并跳过死机分析阶段"
              ></textarea>
              <p class="field-hint">直接粘贴日志内容，或通过下方上传文件。若上传已分析的结果文件，系统将自动跳过死机分析阶段。</p>
            </div>
            <div class="field full">
              <label>上传日志文件</label>
              <div
                class="upload-area"
                :class="{ dragging }"
                @click="fileInputRef?.click()"
                @dragover.prevent="dragging = true"
                @dragleave.prevent="dragging = false"
                @drop.prevent="onFileDrop"
              >
                {{ uploadHint }}
              </div>
              <input
                ref="fileInputRef"
                type="file"
                class="hidden-file"
                accept=".txt,.log,.dmesg,.kernel,.yaml,.yml,.json,.md"
                @change="onFileChange"
              />
            </div>
          </div>
          <div class="toolbar" style="margin-top: 16px">
            <button class="btn primary" :disabled="submitting" @click="startCrashAnalysis">
              {{ submitting ? '分析中...' : '开始分析' }}
            </button>
          </div>
          <div v-if="error" class="message error" style="margin-top: 14px">{{ error }}</div>
        </div>

        <div class="card card-pad">
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
                <div class="history-tags">{{ shortTag(item.from_tag) }} → {{ shortTag(item.to_tag) }}</div>
                <div class="history-meta">
                  <span class="pill" :class="statusTone(item.status)">{{ statusLabel(item.status) }}</span>
                  <span v-if="causeBadge(item)" :class="causeBadge(item)?.class">{{ causeBadge(item)?.text }}</span>
                  <span v-if="item.elapsed_seconds" class="muted">{{ Math.round(item.elapsed_seconds) }}s</span>
                  <span class="muted">{{ formatDate(item.created_at) }}</span>
                </div>
              </button>
              <div class="history-actions">
                <button
                  class="btn-icon"
                  title="下载报告"
                  :disabled="item.status !== 'completed'"
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

      <aside class="workspace-detail">
        <div v-if="activeCrash" class="card card-pad crash-report-panel">
          <div v-if="loadingCrashId" class="detail-banner">
            正在加载诊断详情：{{ shortId(loadingCrashId) }}
          </div>

          <div class="section-title">
            <div>
              <h2>{{ activeCrash.from_tag || '-' }} → {{ activeCrash.to_tag || '-' }}</h2>
              <p class="mono">{{ activeCrash.id || activeCrash.crash_id }}</p>
            </div>
            <div class="toolbar">
              <span class="pill" :class="statusTone(currentStatus)">{{ statusLabel(currentStatus) }}</span>
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
              <strong>分析进度</strong>
              <span class="muted">{{ elapsedText }}</span>
            </div>
            <div class="progress" :class="{ failed: currentStatus === 'failed' }" style="margin: 10px 0">
              <span :style="{ width: `${progressPercent}%` }"></span>
            </div>
            <div class="muted">{{ progress.message || progressMsg }}</div>
            <div class="phase-tags">
              <span
                v-for="(phase, index) in PHASES"
                :key="phase"
                class="phase-tag"
                :class="phaseTagClass(index)"
              >
                {{ PHASE_NAMES[phase] }}
              </span>
            </div>
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
                <div class="summary-val" :class="isCausedByMerge ? 'cause-yes' : 'cause-no'">{{ causeText }}</div>
                <div class="summary-key">
                  是否合入代码引起 | 置信度: {{ confidence }} | 因果类型: {{ causationType }}
                </div>
              </div>
            </div>

            <div class="result-card">
              <h3>死机分析详情</h3>
              <div class="kv-row">
                <span class="kv-k">调用栈摘要</span>
                <span class="kv-v"><code>{{ crashSummary.call_stack_summary || '-' }}</code></span>
              </div>
              <template v-if="dependencyAnalysis">
                <h4>依赖关系分析</h4>
                <div class="info-box">{{ dependencyAnalysis }}</div>
              </template>
              <h4>死机现象描述</h4>
              <div class="info-box" :class="isCausedByMerge ? 'red' : 'green'">
                {{ crashSummary.crash_description || '-' }}
              </div>
              <h4>归因分析</h4>
              <div class="info-box blue"><strong>原因：</strong>{{ explanation || '-' }}</div>
            </div>

            <div class="result-card">
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
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="fix in fixCommits" :key="fix.sha">
                        <td class="mono">{{ shortId(fix.sha, 12) }}</td>
                        <td>{{ fix.title || '-' }}</td>
                        <td><span class="pill muted">{{ fix.fix_type || '-' }}</span></td>
                        <td><span class="pill info">{{ fix.confidence || '-' }}</span></td>
                        <td>{{ fix.reason || '-' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
              <div v-else-if="isCausedByMerge" class="muted">未在 B tag 之后的提交中找到修复</div>
              <div v-else class="muted">（非合入代码引起，未进行修复检查）</div>
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
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { api, formatDate, shortId, statusTone, wsUrl } from '../api'
import { isEmbeddedMode } from '../composables/useEmbeddedNav'

const isEmbedded = isEmbeddedMode()
const PHASES = ['fetching', 'squash_diff', 'crash_analysis', 'enrich', 'find_fix', 'report'] as const
const PHASE_NAMES: Record<string, string> = {
  fetching: '获取提交列表',
  squash_diff: '生成 Squash Diff',
  crash_analysis: 'LLM 分析死机日志',
  enrich: '获取 Patch 详情',
  find_fix: '查找修复提交',
  report: '生成报告',
}

const form = reactive({ from_tag: '', to_tag: '', crash_log: '' })
const history = ref<any[]>([])
const activeCrashId = ref('')
const loadingCrashId = ref('')
const activeCrash = ref<any | null>(null)
const progress = ref<any>({})
const submitting = ref(false)
const error = ref('')
const uploadHint = ref('📁 点击或拖拽文件到此处上传')
const dragging = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const selectedIds = ref<string[]>([])
const selectAll = ref(false)
const elapsedStart = ref(0)
const elapsedSeconds = ref(0)
let socket: WebSocket | null = null
let elapsedTimer: number | null = null

const currentStatus = computed(() => progress.value.status || activeCrash.value?.status || '')
const showProgress = computed(() => ['pending', 'analyzing', 'failed'].includes(currentStatus.value))
const progressMsg = computed(() => {
  if (currentStatus.value === 'completed') return '分析完成'
  if (currentStatus.value === 'failed') return progress.value.message || '分析失败'
  return progress.value.message || '准备中...'
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
const confidence = computed(() => crashSummary.value.confidence || activeCrash.value?.confidence || '低')
const causationType = computed(() => crashSummary.value.causation_type || activeCrash.value?.causation_type || '无')
const explanation = computed(() => crashSummary.value.explanation || activeCrash.value?.explanation || '')
const dependencyAnalysis = computed(() => crashSummary.value.dependency_analysis || '')
const causeText = computed(() =>
  isCausedByMerge.value
    ? `是（${causationType.value === '直接' ? '直接' : '间接'}合入代码引起）`
    : '否（非合入代码引起）',
)

const progressPercent = computed(() => {
  if (currentStatus.value === 'completed') return 100
  if (currentStatus.value === 'failed') return 100
  const currentIdx = PHASES.indexOf(progress.value.status || '')
  if (currentIdx >= 0) return Math.min(((currentIdx + 1) / PHASES.length) * 100, 100)
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

function statusLabel(status?: string) {
  const map: Record<string, string> = {
    completed: '已完成',
    analyzing: '分析中',
    failed: '失败',
    pending: '等待中',
  }
  return map[status || ''] || status || '-'
}

function shortTag(tag?: string) {
  if (!tag) return '?'
  return tag.replace(/android\d+-[\d.]+-/, '')
}

function causeBadge(item: any) {
  if (item.is_caused_by_merge === 1) return { text: '合入引起', class: 'cause-yes' }
  if (item.is_caused_by_merge === 0 && item.status === 'completed') return { text: '非合入引起', class: 'cause-no' }
  return null
}

function llmScoreClass(score?: number) {
  const value = Number(score || 0)
  if (value >= 60) return 'high'
  if (value >= 30) return 'medium'
  return 'low'
}

function phaseTagClass(index: number) {
  const currentIdx = PHASES.indexOf(progress.value.status || '')
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
    uploadHint.value = `✅ 已加载: ${file.name} (${(file.size / 1024).toFixed(1)}KB)`
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

async function loadHistory() {
  const data = await api.get<any>('/api/crash-analyses')
  history.value = data.items || []
  selectAll.value = false
  selectedIds.value = []
}

async function refreshHistory() {
  await loadHistory()
  if (activeCrashId.value) {
    const exists = history.value.some((item) => (item.id || item.crash_id) === activeCrashId.value)
    if (exists) await selectCrash(activeCrashId.value)
    else await selectLatestCrash()
  } else {
    await selectLatestCrash()
  }
}

async function selectLatestCrash() {
  if (!history.value.length) {
    activeCrash.value = null
    activeCrashId.value = ''
    return
  }
  const latest = history.value[0]
  await selectCrash(latest.id || latest.crash_id)
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
  socket = new WebSocket(wsUrl(`/ws/crash-analysis/${crashId}`))
  socket.onmessage = (event) => {
    progress.value = JSON.parse(event.data || '{}')
    if (progress.value.status === 'completed') {
      stopElapsedTimer()
      selectCrash(crashId)
    } else if (progress.value.status === 'failed') {
      stopElapsedTimer()
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
  if (!form.from_tag.trim() || !form.to_tag.trim()) {
    error.value = '请填写起始和结束 Tag'
    return
  }
  if (!form.crash_log.trim()) {
    error.value = '请提供死机日志'
    return
  }
  submitting.value = true
  error.value = ''
  try {
    const data = await api.post<any>('/api/crash-analysis', { ...form })
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

onMounted(async () => {
  await loadHistory()
  await selectLatestCrash()
})

onBeforeUnmount(() => {
  if (socket) socket.close()
  stopElapsedTimer()
})
</script>
