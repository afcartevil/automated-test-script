<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { NEmpty, NTag, NButton, useMessage } from 'naive-ui'
import EaCard from '@/components/layout/EaCard.vue'
import {
  listSelfCheckReports,
  getSelfCheckReportDetail,
  submitSelfCheckReportReview,
  type SelfCheckReportSummary,
  type SelfCheckReportDetail,
  type SelfCheckReviewStatus,
} from '@/api/tahp/device-self-check'

const message = useMessage()
const loading = ref(false)
const detailLoading = ref(false)
const submitting = ref(false)
const reports = ref<SelfCheckReportSummary[]>([])
const selectedId = ref<string | null>(null)
const filterText = ref('')
const reviewNote = ref('')
const reportDetail = ref<SelfCheckReportDetail | null>(null)

const filteredReports = computed(() => {
  const q = filterText.value.trim().toLowerCase()
  if (!q) return reports.value
  return reports.value.filter(r =>
    reportTitle(r).toLowerCase().includes(q) ||
    r.deviceName.toLowerCase().includes(q) ||
    r.deviceId.toLowerCase().includes(q),
  )
})

function statusTagType(status: SelfCheckReviewStatus | string): 'success' | 'error' | 'warning' | 'default' {
  if (status === 'reviewed') return 'success'
  if (status === 'retest') return 'warning'
  if (/fail|失败/i.test(status)) return 'error'
  if (status === 'pending' || /待/i.test(status)) return 'warning'
  return 'default'
}

function displayStatus(report: SelfCheckReportSummary): string {
  if (report.reviewStatus === 'reviewed') return '已 Review'
  if (report.reviewStatus === 'retest') return '待补测'
  if (report.failedCases > 0) return '待 Review'
  return report.status.includes('通过') ? '通过' : '待 Review'
}

function reportShortType(testType: string): string {
  if (testType === 'monkey') return 'monkey'
  if (testType === 'smoke') return '冒烟'
  if (testType === 'str4') return 'STR4'
  if (testType === 'week') return '周版本'
  if (testType === 'custom') return '自定义'
  return testType
}

function reportTitle(report: SelfCheckReportSummary): string {
  const typeLabel = report.testType === 'custom'
    ? '自定义测试'
    : report.testType === 'str4'
      ? 'STR4'
      : report.testType === 'monkey'
        ? 'monkey测试'
        : report.testType === 'smoke'
          ? '冒烟测试'
          : '周版本'
  if (report.aiPlanned) {
    return `${report.deviceName} · ${reportShortType(report.testType)} · AI规划`
  }
  return `${report.deviceName} · ${typeLabel}`
}

function reportTime(report: SelfCheckReportSummary): string {
  const t = report.completedAt || report.endTime || report.startTime
  try {
    return new Date(t).toLocaleString('zh-CN')
  } catch {
    return t
  }
}

async function loadReports() {
  loading.value = true
  try {
    reports.value = await listSelfCheckReports({ sinceHours: 72 })
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
    message.success(status === 'retest' ? '已标记待补测' : 'Review 结论已提交')
    await loadReports()
  } catch (err) {
    message.error((err as Error).message || '提交失败')
  } finally {
    submitting.value = false
  }
}

watch(selectedId, (id) => {
  if (id) void loadDetail(id)
  else reportDetail.value = null
})

onMounted(async () => {
  await loadReports()
  if (selectedId.value) await loadDetail(selectedId.value)
})
</script>

<template>
  <div class="report-review-root">
    <EaCard class="report-list-card">
      <div class="list-head">
        <div>
          <h3>次日报告 Review</h3>
          <p class="ea-muted">展示近 72 小时完成的自检报告，支持 AI 摘要与人工结论</p>
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
        description="暂无待 Review 报告。自动测试完成后，报告将在此汇总"
        size="small"
      />
      <ul v-else class="report-list">
        <li
          v-for="report in filteredReports"
          :key="report.reportId"
          class="report-item"
          :class="{ selected: selectedId === report.reportId }"
          @click="selectedId = report.reportId"
        >
          <NTag size="small" :type="statusTagType(report.reviewStatus)" :bordered="false">
            {{ displayStatus(report) }}
          </NTag>
          <div class="report-item-body">
            <strong>{{ reportTitle(report) }}</strong>
            <small class="ea-muted">
              {{ reportTime(report) }} · {{ report.passedCases }}/{{ report.totalCases }} 通过
            </small>
          </div>
        </li>
      </ul>
    </EaCard>

    <EaCard class="report-detail-card">
      <div v-if="detailLoading" class="panel-empty ea-muted">加载详情…</div>
      <template v-else-if="reportDetail">
        <div class="detail-head">
          <h3>{{ reportTitle(reportDetail) }}</h3>
          <NTag size="small" :type="statusTagType(reportDetail.reviewStatus)" :bordered="false">
            {{ displayStatus(reportDetail) }}
          </NTag>
        </div>
        <div class="detail-section">
          <div class="section-label">AI 摘要</div>
          <p class="detail-text">{{ reportDetail.aiSummary }}</p>
        </div>
        <div class="detail-section">
          <div class="section-label">失败用例（{{ reportDetail.failedCaseItems.length }}）</div>
          <NEmpty
            v-if="!reportDetail.failedCaseItems.length"
            description="无失败项"
            size="small"
          />
          <ul v-else class="failed-list">
            <li v-for="item in reportDetail.failedCaseItems" :key="item.caseKey">
              <strong>{{ item.caseName }}</strong>
              <span class="ea-muted">{{ item.module }} · {{ item.status }}</span>
              <p v-if="item.message" class="ea-muted">{{ item.message }}</p>
            </li>
          </ul>
        </div>
        <div class="detail-section">
          <div class="section-label">人工结论</div>
          <textarea
            v-model="reviewNote"
            class="review-textarea"
            rows="4"
            placeholder="填写 Review 结论、补测意见…"
          />
          <div class="detail-actions">
            <NButton
              size="small"
              type="primary"
              :loading="submitting"
              @click="handleSubmitReview('reviewed')"
            >
              提交结论
            </NButton>
            <NButton
              size="small"
              tertiary
              :loading="submitting"
              @click="handleSubmitReview('retest')"
            >
              标记待补测
            </NButton>
          </div>
        </div>
      </template>
      <NEmpty v-else description="选择左侧报告查看详情" size="small" />
    </EaCard>
  </div>
</template>

<style scoped lang="scss">
.report-review-root {
  display: grid;
  grid-template-columns: 360px 1fr;
  gap: 14px;
  min-height: 420px;
}

.report-list-card,
.report-detail-card {
  padding: 16px 18px;
  min-height: 400px;
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

.report-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 480px;
  overflow-y: auto;
}

.report-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 10px;
  cursor: pointer;
  border: 1px solid transparent;

  &:hover {
    background: var(--bg);
  }

  &.selected {
    border-color: var(--accent);
    background: var(--accent-soft);
  }
}

.report-item-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;

  strong {
    font-size: 13px;
    font-weight: 600;
  }

  small {
    font-size: 11px;
  }
}

.detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;

  h3 {
    margin: 0;
    font-size: 15px;
    font-weight: 700;
  }
}

.detail-section {
  margin-bottom: 18px;
}

.section-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 8px;
}

.detail-text {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
}

.failed-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;

  li {
    padding: 10px 12px;
    border-radius: 8px;
    background: var(--bg);
    display: flex;
    flex-direction: column;
    gap: 4px;

    strong {
      font-size: 13px;
    }

    p {
      margin: 0;
      font-size: 12px;
    }
  }
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

  &:focus {
    outline: none;
    border-color: var(--accent);
  }
}

.detail-actions {
  display: flex;
  gap: 8px;
  margin-top: 10px;
}

@media (max-width: 900px) {
  .report-review-root {
    grid-template-columns: 1fr;
  }
}
</style>
