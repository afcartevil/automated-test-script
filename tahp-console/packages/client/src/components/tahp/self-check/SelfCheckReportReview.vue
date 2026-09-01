<script setup lang="ts">
import { ref, computed, onMounted, onActivated, watch, inject } from 'vue'
import { NEmpty, NButton, useMessage } from 'naive-ui'
import EaCard from '@/components/layout/EaCard.vue'
import { DEVICE_SELF_CHECK_KEY } from './self-check-context'
import { getCaseResultColor, getTestTypeLabel, reportTitle, displayReportStatus, reportStatusKind, getAutomationModeIcon, getAutomationModeLabel, normalizeAutomationMode } from './self-check-utils'
import {
  listSelfCheckReports,
  getSelfCheckReportDetail,
  submitSelfCheckReportReview,
  updateReportCaseResult,
  retestReportCase,
  openSelfCheckReportFile,
  openSelfCheckCaseFailureLogs,
  type SelfCheckReportSummary,
  type SelfCheckReportDetail,
  type SelfCheckCaseItem,
  type SelfCheckReviewStatus,
} from '@/api/tahp/device-self-check'

const message = useMessage()
const ctx = inject(DEVICE_SELF_CHECK_KEY)!

const loading = ref(false)
const detailLoading = ref(false)
const submitting = ref(false)
const reports = ref<SelfCheckReportSummary[]>([])
const selectedId = ref<string | null>(null)
const reportPanelExpanded = ref(false)
const filterText = ref('')
const reviewNote = ref('')
const reportDetail = ref<SelfCheckReportDetail | null>(null)
const selectedCaseKey = ref<string | null>(null)
const expandedModules = ref<Set<string>>(new Set())

const showModifyDialog = ref(false)
const modifyStatus = ref('通过')
const modifyMessage = ref('')

const showRetestDialog = ref(false)
const retestAuxDeviceId = ref<string | null>(null)
const retesting = ref(false)

const filteredReports = computed(() => {
  const q = filterText.value.trim().toLowerCase()
  if (!q) return reports.value
  return reports.value.filter(r =>
    reportTitle(r).toLowerCase().includes(q) ||
    r.deviceName.toLowerCase().includes(q) ||
    r.deviceId.toLowerCase().includes(q),
  )
})

const RECENT_MS = 72 * 3600 * 1000

function isRecentReport(report: SelfCheckReportSummary): boolean {
  const t = Date.parse(report.completedAt || report.endTime || report.startTime) || 0
  return t >= Date.now() - RECENT_MS
}

const recentReports = computed(() => filteredReports.value.filter(isRecentReport))
const historyReports = computed(() => filteredReports.value.filter(r => !isRecentReport(r)))

const caseGroups = computed(() => {
  const items = reportDetail.value?.allCaseItems ?? []
  const map = new Map<string, SelfCheckCaseItem[]>()
  for (const item of items) {
    const label = item.module
    if (!map.has(label)) map.set(label, [])
    map.get(label)!.push(item)
  }
  return [...map.entries()].map(([label, cases]) => ({
    label,
    cases: cases.sort((a, b) => a.caseIndex - b.caseIndex),
  }))
})

const selectedCaseItem = computed(() =>
  reportDetail.value?.allCaseItems.find(c => c.caseKey === selectedCaseKey.value) ?? null,
)

function resolveCaseAutomationMode(item: SelfCheckCaseItem): 'full' | 'semi' | 'manual' {
  if (item.automationMode) return normalizeAutomationMode(item.automationMode)
  const moduleKey = `${item.testType}/${item.module}`
  const meta = ctx.moduleConditions.value[moduleKey]?.cases.find(c => c.caseIndex === item.caseIndex)
  if (meta?.automationMode) return normalizeAutomationMode(meta.automationMode)
  return item.fullAutomation === false ? 'manual' : 'full'
}

const availableAuxForRetest = computed(() =>
  ctx.devices.value.filter(d =>
    d.deviceId !== reportDetail.value?.deviceId &&
    (d.role === '辅测机' || d.role === '测试机') &&
    d.status === '空闲',
  ),
)

function reportTime(report: SelfCheckReportSummary): string {
  const t = report.completedAt || report.endTime || report.startTime
  try {
    return new Date(t).toLocaleString('zh-CN')
  } catch {
    return t
  }
}

function toggleModule(module: string) {
  if (expandedModules.value.has(module)) expandedModules.value.delete(module)
  else expandedModules.value.add(module)
  expandedModules.value = new Set(expandedModules.value)
}

function selectReport(reportId: string) {
  if (selectedId.value === reportId && reportPanelExpanded.value) {
    reportPanelExpanded.value = false
    return
  }
  selectedId.value = reportId
  reportPanelExpanded.value = true
}

function collapseReportPanel() {
  reportPanelExpanded.value = false
}

const openingReport = ref(false)
const openingLogs = ref(false)

async function openReportFile() {
  if (!selectedId.value || openingReport.value) return
  openingReport.value = true
  try {
    const { filePath } = await openSelfCheckReportFile(selectedId.value)
    message.success(`已在本地打开：${filePath}`)
  } catch (err: unknown) {
    const text = err instanceof Error ? err.message : '打开报告失败'
    message.error(text)
  } finally {
    openingReport.value = false
  }
}

function canOpenFailureLogs(item: SelfCheckCaseItem | null | undefined): boolean {
  if (!item) return false
  return Boolean(item.failureLogDir) || item.status === '失败'
}

async function openFailureLogs() {
  if (!selectedId.value || !selectedCaseItem.value || openingLogs.value) return
  openingLogs.value = true
  try {
    const { dirPath } = await openSelfCheckCaseFailureLogs(
      selectedId.value,
      selectedCaseItem.value.caseKey,
    )
    message.success(`已打开日志目录：${dirPath}`)
  } catch (err: unknown) {
    const text = err instanceof Error ? err.message : '打开日志失败'
    message.error(text)
  } finally {
    openingLogs.value = false
  }
}

function selectCase(caseKey: string) {
  selectedCaseKey.value = caseKey
}

async function loadReports() {
  loading.value = true
  try {
    reports.value = await listSelfCheckReports()
    if (!selectedId.value && reports.value.length) {
      selectedId.value = reports.value[0].reportId
    }
  } catch {
    reports.value = []
  } finally {
    loading.value = false
  }
}

async function loadDetail(reportId: string) {
  detailLoading.value = true
  try {
    reportDetail.value = await getSelfCheckReportDetail(reportId)
    reviewNote.value = reportDetail.value.reviewNote || ''
    expandedModules.value = new Set(
      (reportDetail.value.allCaseItems ?? []).map(item => item.module),
    )
    const first = reportDetail.value.allCaseItems[0]
    selectedCaseKey.value = first?.caseKey ?? null
  } catch {
    reportDetail.value = null
  } finally {
    detailLoading.value = false
  }
}

async function handleSubmitReview(status: SelfCheckReviewStatus) {
  if (!selectedId.value) return
  submitting.value = true
  try {
    reportDetail.value = await submitSelfCheckReportReview(selectedId.value, {
      status,
      note: reviewNote.value,
    })
    message.success(status === 'retest' ? '已标记待补测' : '审阅结论已提交')
    await loadReports()
  } catch (err) {
    message.error((err as Error).message || '提交失败')
  } finally {
    submitting.value = false
  }
}

function openModifyDialog() {
  if (!selectedCaseItem.value) return
  modifyStatus.value = selectedCaseItem.value.status
  modifyMessage.value = selectedCaseItem.value.message || ''
  showModifyDialog.value = true
}

async function handleModifyCaseResult() {
  if (!selectedId.value || !selectedCaseKey.value) return
  submitting.value = true
  try {
    reportDetail.value = await updateReportCaseResult(selectedId.value, {
      caseKey: selectedCaseKey.value,
      status: modifyStatus.value,
      message: modifyMessage.value,
    })
    showModifyDialog.value = false
    message.success('用例结果已更新')
    await loadReports()
  } catch (err) {
    message.error((err as Error).message || '修改失败')
  } finally {
    submitting.value = false
  }
}

function openRetestDialog() {
  retestAuxDeviceId.value = null
  showRetestDialog.value = true
}

async function handleRetestCase() {
  if (!selectedId.value || !selectedCaseKey.value) return
  retesting.value = true
  try {
    const { detail } = await retestReportCase(selectedId.value, {
      caseKey: selectedCaseKey.value,
      auxDeviceId: retestAuxDeviceId.value || undefined,
    })
    reportDetail.value = detail
    showRetestDialog.value = false
    message.success('复测完成')
    await loadReports()
    await ctx.loadDevices()
  } catch (err) {
    message.error((err as Error).message || '复测失败')
  } finally {
    retesting.value = false
  }
}

watch(selectedId, (id) => {
  if (id) void loadDetail(id)
  else reportDetail.value = null
})

watch(
  () => ctx.reportsEpoch.value,
  (epoch, prev) => {
    if (epoch === prev) return
    void loadReports()
  },
)

onMounted(async () => {
  await loadReports()
  if (selectedId.value) await loadDetail(selectedId.value)
})

onActivated(async () => {
  await loadReports()
})
</script>

<template>
  <div class="report-review-root">
    <EaCard class="report-list-card">
      <div class="list-head">
        <div>
          <h3>测试报告</h3>
          <p class="ea-muted">全部自检报告统一在此审阅；近 72 小时优先展示，历史报告可展开</p>
        </div>
        <input
          v-model="filterText"
          class="filter-input"
          placeholder="按设备 / 项目筛选…"
        />
      </div>

      <div v-if="loading" class="panel-empty ea-muted">加载报告…</div>
      <NEmpty
        v-else-if="!filteredReports.length"
        description="暂无测试报告。测试完成后将自动汇总至此"
        size="small"
      />
      <div v-else class="report-sections">
        <section class="report-section">
          <div class="report-section-title">
            近 72 小时
            <span class="report-section-count">{{ recentReports.length }}</span>
          </div>
          <p v-if="!recentReports.length" class="panel-empty ea-muted">近 72 小时暂无报告</p>
          <ul v-else class="report-grid">
            <li
              v-for="report in recentReports"
              :key="report.reportId"
              class="report-card"
              :class="{ selected: selectedId === report.reportId && reportPanelExpanded }"
              @click="selectReport(report.reportId)"
            >
              <div class="report-card-tags">
                <span class="report-status" :class="reportStatusKind(report)">
                  {{ displayReportStatus(report) }}
                </span>
                <span v-if="report.passedCases > 0" class="report-stat report-stat--pass">
                  通过 {{ report.passedCases }}
                </span>
                <span v-if="report.failedCases > 0" class="report-stat report-stat--fail">
                  失败 {{ report.failedCases }}
                </span>
                <span v-if="report.skippedCases > 0" class="report-stat report-stat--skip">
                  跳过 {{ report.skippedCases }}
                </span>
              </div>
              <strong class="report-card-title">{{ reportTitle(report) }}</strong>
              <small class="report-card-meta ea-muted">
                {{ reportTime(report) }} · {{ report.passedCases }}/{{ report.totalCases }}
              </small>
            </li>
          </ul>
        </section>

        <details v-if="historyReports.length" class="report-section report-section--history">
          <summary class="report-section-title">
            历史报告
            <span class="report-section-count">{{ historyReports.length }}</span>
          </summary>
          <ul class="report-grid">
            <li
              v-for="report in historyReports"
              :key="report.reportId"
              class="report-card"
              :class="{ selected: selectedId === report.reportId && reportPanelExpanded }"
              @click="selectReport(report.reportId)"
            >
              <div class="report-card-tags">
                <span class="report-status" :class="reportStatusKind(report)">
                  {{ displayReportStatus(report) }}
                </span>
                <span v-if="report.passedCases > 0" class="report-stat report-stat--pass">
                  通过 {{ report.passedCases }}
                </span>
                <span v-if="report.failedCases > 0" class="report-stat report-stat--fail">
                  失败 {{ report.failedCases }}
                </span>
                <span v-if="report.skippedCases > 0" class="report-stat report-stat--skip">
                  跳过 {{ report.skippedCases }}
                </span>
              </div>
              <strong class="report-card-title">{{ reportTitle(report) }}</strong>
              <small class="report-card-meta ea-muted">
                {{ reportTime(report) }} · {{ report.passedCases }}/{{ report.totalCases }}
              </small>
            </li>
          </ul>
        </details>
      </div>
    </EaCard>

    <div
      v-if="reportPanelExpanded && selectedId"
      class="report-detail-layout report-stack-pane"
    >
      <EaCard class="report-overview-card">
        <div v-if="detailLoading" class="panel-empty ea-muted">加载详情…</div>
        <template v-else-if="reportDetail">
          <div class="catalog-overview-header">
            <div class="detail-head">
              <h3>{{ reportTitle(reportDetail) }}</h3>
              <span class="report-status" :class="reportStatusKind(reportDetail)">
                {{ displayReportStatus(reportDetail) }}
              </span>
            </div>
            <div class="overview-header-actions">
              <button
                type="button"
                class="ea-btn-ghost ea-btn-sm"
                :disabled="openingReport"
                @click="openReportFile"
              >
                {{ openingReport ? '打开中…' : '打开报告' }}
              </button>
              <button type="button" class="ea-btn-ghost ea-btn-sm" @click="collapseReportPanel">
                收起
              </button>
            </div>
          </div>

          <div class="report-review-section">
            <div class="section-title">人工审阅</div>
            <textarea
              v-model="reviewNote"
              class="review-textarea"
              rows="3"
              placeholder="填写审阅结论、补测意见…"
            />
            <div class="detail-actions">
              <NButton size="small" type="primary" :loading="submitting" @click="handleSubmitReview('reviewed')">
                提交结论
              </NButton>
              <NButton size="small" tertiary :loading="submitting" @click="handleSubmitReview('retest')">
                标记待补测
              </NButton>
            </div>
          </div>

          <dl class="catalog-overview-meta">
            <div>
              <dt>设备</dt>
              <dd>{{ reportDetail.deviceName }}（{{ reportDetail.deviceId }}）</dd>
            </div>
            <div>
              <dt>测试类型</dt>
              <dd>{{ getTestTypeLabel(reportDetail.testType) }}</dd>
            </div>
            <div>
              <dt>OTA 版本</dt>
              <dd>{{ reportDetail.version?.trim() ? reportDetail.version : '未获取 (persist.sys.ota_version)' }}</dd>
            </div>
            <div>
              <dt>完成时间</dt>
              <dd>{{ reportTime(reportDetail) }}</dd>
            </div>
            <div>
              <dt>通过率</dt>
              <dd>{{ reportDetail.passedCases }}/{{ reportDetail.totalCases }}</dd>
            </div>
          </dl>
          <p class="detail-text overview-summary">{{ reportDetail.aiSummary }}</p>
        </template>
      </EaCard>

      <div v-if="reportDetail && !detailLoading" class="detail-container report-detail-body">
        <EaCard class="sidebar-card">
          <div class="section-title">用例列表</div>
          <div class="case-list">
            <div v-for="group in caseGroups" :key="group.label" class="module-group">
              <div class="module-name" @click="toggleModule(group.label)">
                <span class="module-arrow" :class="{ open: expandedModules.has(group.label) }">&#9654;</span>
                {{ group.label }}
                <span class="module-count">{{ group.cases.length }}</span>
              </div>
              <div v-show="expandedModules.has(group.label)" class="module-cases">
                <div
                  v-for="item in group.cases"
                  :key="item.caseKey"
                  class="case-item"
                  :class="{ selected: selectedCaseKey === item.caseKey }"
                  :style="{ color: getCaseResultColor(item.status) }"
                  @click="selectCase(item.caseKey)"
                >
                  <span
                    class="auto-mode-icon"
                    :class="`auto-mode-icon--${resolveCaseAutomationMode(item)}`"
                    :title="getAutomationModeLabel(resolveCaseAutomationMode(item))"
                  >{{ getAutomationModeIcon(resolveCaseAutomationMode(item)) }}</span>
                  <span class="case-item-name">{{ item.caseName }}</span>
                </div>
              </div>
            </div>
          </div>
        </EaCard>

        <div class="detail-main">
          <EaCard class="report-case-detail-card">
            <template v-if="selectedCaseItem">
              <div class="case-detail-header">
                <span class="catalog-case-title">{{ selectedCaseItem.caseName }}</span>
                <span
                  class="auto-mode-badge"
                  :class="`auto-mode-badge--${resolveCaseAutomationMode(selectedCaseItem)}`"
                >
                  <span
                    class="auto-mode-icon"
                    :class="`auto-mode-icon--${resolveCaseAutomationMode(selectedCaseItem)}`"
                  >{{ getAutomationModeIcon(resolveCaseAutomationMode(selectedCaseItem)) }}</span>
                  {{ getAutomationModeLabel(resolveCaseAutomationMode(selectedCaseItem)) }}
                </span>
              </div>
              <div class="case-detail-content">
                <div class="case-info">
                  <div class="detail-item">
                    <span class="detail-label">模块</span>
                    <span class="detail-value">{{ selectedCaseItem.module }}</span>
                  </div>
                  <div class="detail-item">
                    <span class="detail-label">结果</span>
                    <span class="detail-value" :style="{ color: getCaseResultColor(selectedCaseItem.status) }">
                      {{ selectedCaseItem.status }}
                    </span>
                  </div>
                  <div class="detail-item detail-item--full">
                    <span class="detail-label">结论</span>
                    <span class="detail-value">{{ selectedCaseItem.message || '暂无' }}</span>
                  </div>
                </div>
                <div v-if="selectedCaseItem.steps?.length" class="case-steps">
                  <div class="section-title">子步骤</div>
                  <div v-for="(step, idx) in selectedCaseItem.steps" :key="idx" class="step-item">
                    {{ step.stepDesc }}
                  </div>
                </div>
                <div class="case-detail-actions">
                  <button
                    v-if="canOpenFailureLogs(selectedCaseItem)"
                    type="button"
                    class="ea-btn-ghost"
                    :disabled="openingLogs"
                    @click="openFailureLogs"
                  >
                    {{ openingLogs ? '打开中…' : '打开日志' }}
                  </button>
                  <button type="button" class="ea-btn-primary" @click="openRetestDialog">复测此用例</button>
                  <button type="button" class="ea-btn-ghost" @click="openModifyDialog">修改用例结果</button>
                </div>
              </div>
            </template>
            <NEmpty v-else description="请从左侧选择用例" size="small" />
          </EaCard>
        </div>
      </div>
    </div>

    <div v-if="showModifyDialog" class="modify-overlay" @click.self="showModifyDialog = false">
      <div class="modify-dialog">
        <div class="modify-dialog-header">
          <span class="section-title">修改用例结果</span>
          <button type="button" class="ea-btn-ghost ea-btn-sm" @click="showModifyDialog = false">✕</button>
        </div>
        <div class="modify-dialog-body">
          <div class="form-group">
            <label class="form-label">测试结果</label>
            <select v-model="modifyStatus" class="form-input">
              <option value="通过">通过</option>
              <option value="失败">失败</option>
              <option value="部分通过">部分通过</option>
              <option value="NA">NA</option>
              <option value="跳过">跳过</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">备注</label>
            <textarea v-model="modifyMessage" class="form-input" rows="3" placeholder="输入备注…" />
          </div>
        </div>
        <div class="modify-dialog-footer">
          <button type="button" class="ea-btn-ghost" @click="showModifyDialog = false">取消</button>
          <button type="button" class="ea-btn-primary" :disabled="submitting" @click="handleModifyCaseResult">
            确认修改
          </button>
        </div>
      </div>
    </div>

    <div v-if="showRetestDialog" class="modify-overlay" @click.self="showRetestDialog = false">
      <div class="modify-dialog">
        <div class="modify-dialog-header">
          <span class="section-title">复测用例</span>
          <button type="button" class="ea-btn-ghost ea-btn-sm" @click="showRetestDialog = false">✕</button>
        </div>
        <div class="modify-dialog-body">
          <div class="form-group">
            <label class="form-label">选择辅测机（可选）</label>
            <select v-model="retestAuxDeviceId" class="form-input">
              <option :value="null">无（不需要辅测机）</option>
              <option v-for="d in availableAuxForRetest" :key="d.deviceId" :value="d.deviceId">
                {{ d.deviceName }}（{{ d.role }}）
              </option>
            </select>
          </div>
        </div>
        <div class="modify-dialog-footer">
          <button type="button" class="ea-btn-ghost" :disabled="retesting" @click="showRetestDialog = false">取消</button>
          <button type="button" class="ea-btn-primary" :disabled="retesting" @click="handleRetestCase">
            {{ retesting ? '正在复测…' : '开始复测' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
$report-pane-height: calc(100vh - 48px);

.report-review-root {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 420px;
}

.report-list-card {
  padding: 16px 18px;
}

.list-head {
  margin-bottom: 14px;

  h3 {
    margin: 0 0 4px;
    font-size: 15px;
    font-weight: 700;
  }

  p {
    margin: 0 0 10px;
    font-size: 12px;
  }
}

.filter-input {
  width: 100%;
  max-width: 360px;
  padding: 6px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  font-size: 13px;
  background: var(--bg);
}

.panel-empty {
  padding: 24px 0;
  text-align: center;
  font-size: 13px;
}

.report-sections {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.report-section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 700;
  color: var(--head);
  list-style: none;
  cursor: default;

  &::-webkit-details-marker {
    display: none;
  }
}

.report-section--history > summary.report-section-title {
  cursor: pointer;
  user-select: none;

  &::before {
    content: '▸';
    display: inline-block;
    font-size: 11px;
    color: var(--muted);
    transition: transform 0.15s;
  }
}

.report-section--history[open] > summary.report-section-title::before {
  transform: rotate(90deg);
}

.report-section-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 18px;
  padding: 0 6px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: var(--muted);
  background: var(--bg);
}

.report-grid {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.report-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border-radius: 10px;
  cursor: pointer;
  border: 1px solid var(--line);
  background: var(--surface, var(--bg));
  min-width: 0;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;

  &:hover {
    border-color: color-mix(in srgb, var(--accent) 40%, var(--line));
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  }

  &.selected {
    border-color: var(--accent);
    background: var(--accent-soft);
    box-shadow: 0 0 0 1px var(--accent);
  }
}

.report-card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.report-status,
.report-stat {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 700;
  line-height: 1.4;
  white-space: nowrap;
}

.report-status {
  &.passed {
    background: rgba(16, 185, 129, 0.14);
    color: #059669;
  }

  &.pending {
    background: rgba(245, 158, 11, 0.16);
    color: #d97706;
  }

  &.reviewed {
    background: rgba(59, 130, 246, 0.14);
    color: #2563eb;
  }

  &.retest {
    background: rgba(249, 115, 22, 0.16);
    color: #ea580c;
  }
}

.report-stat--pass {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
}

.report-stat--fail {
  background: rgba(239, 68, 68, 0.12);
  color: #dc2626;
}

.report-stat--skip {
  background: rgba(100, 116, 139, 0.12);
  color: #64748b;
}

.report-card-title {
  font-size: 13px;
  font-weight: 600;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.report-card-meta {
  font-size: 11px;
  line-height: 1.35;
}

@media (max-width: 1200px) {
  .report-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 900px) {
  .report-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 560px) {
  .report-grid {
    grid-template-columns: 1fr;
  }
}

.report-stack-pane {
  height: $report-pane-height;
  min-height: $report-pane-height;
  max-height: $report-pane-height;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
}

.report-overview-card {
  flex-shrink: 0;
  padding: 16px 18px;
}

.catalog-overview-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.detail-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;

  h3 {
    margin: 0;
    font-size: 15px;
    font-weight: 700;
  }
}

.overview-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.report-review-section {
  margin-bottom: 14px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line);
}

.catalog-overview-meta {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px 16px;
  margin: 0 0 10px;

  dt {
    font-size: 11px;
    color: var(--muted);
    margin: 0;
  }

  dd {
    margin: 2px 0 0;
    font-size: 13px;
  }
}

.overview-summary {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
}

.report-detail-body {
  flex: 1 1 0;
  min-height: 0;
  display: flex;
  gap: 16px;
  overflow: hidden;
}

.sidebar-card {
  width: 280px;
  flex-shrink: 0;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.section-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 8px;
  flex-shrink: 0;
}

.case-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.module-group {
  margin-bottom: 8px;
}

.module-name {
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  padding: 6px 4px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.module-arrow {
  display: inline-block;
  transition: transform 0.15s;
  font-size: 10px;

  &.open {
    transform: rotate(90deg);
  }
}

.module-count {
  font-size: 11px;
  color: var(--muted);
  margin-left: auto;
}

.case-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  padding: 6px 8px 6px 12px;
  border-radius: 6px;
  cursor: pointer;

  &:hover {
    background: var(--bg);
  }

  &.selected {
    background: var(--accent-soft);
  }
}

.case-item-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.auto-mode-icon {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  line-height: 1;
  user-select: none;
}

.auto-mode-icon--full {
  background: #d1fae5;
  color: #047857;
}

.auto-mode-icon--semi {
  background: #fef3c7;
  color: #b45309;
}

.auto-mode-icon--manual {
  background: #e2e8f0;
  color: #475569;
}

.auto-mode-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 8px 2px 4px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 500;
  flex-shrink: 0;
}

.auto-mode-badge--full {
  background: #ecfdf5;
  color: #047857;
}

.auto-mode-badge--semi {
  background: #fffbeb;
  color: #b45309;
}

.auto-mode-badge--manual {
  background: #f1f5f9;
  color: #475569;
}

.detail-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: hidden;
}

.report-case-detail-card {
  padding: 16px 18px;
}

.report-case-detail-card {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.catalog-case-title {
  font-size: 14px;
  font-weight: 700;
}

.case-detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.case-detail-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.case-info {
  display: grid;
  gap: 10px;
  margin-bottom: 14px;
}

.detail-item {
  display: flex;
  gap: 12px;
  font-size: 13px;

  &--full {
    flex-direction: column;
    gap: 4px;
  }
}

.detail-label {
  color: var(--muted);
  min-width: 48px;
}

.step-item {
  font-size: 12px;
  padding: 4px 0;
  border-bottom: 1px solid var(--line);
}

.case-detail-actions,
.detail-actions {
  display: flex;
  gap: 8px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.review-textarea {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: 10px;
  font-size: 13px;
  font-family: inherit;
  background: var(--bg);
  resize: vertical;
  margin-bottom: 10px;

  &:focus {
    outline: none;
    border-color: var(--accent);
  }
}

.modify-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modify-dialog {
  background: var(--card, #fff);
  border-radius: 16px;
  width: 440px;
  max-width: 90vw;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  overflow: hidden;
}

.modify-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--line);
}

.modify-dialog-body {
  padding: 20px;
}

.modify-dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--line);
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--muted);
}

.form-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  font-size: 14px;
  background: var(--bg);

  &:focus {
    outline: none;
    border-color: var(--accent);
  }
}
</style>
