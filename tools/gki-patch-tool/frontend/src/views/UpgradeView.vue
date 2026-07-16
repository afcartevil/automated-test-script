<template>
  <section>
    <div class="topbar">
      <div>
        <p class="eyebrow">GKI Upgrade</p>
        <h1 class="page-title">GKI 升级合入</h1>
        <p v-if="!isEmbedded" class="page-desc">填写 Tag 区间与合入路径后即可启动；高级选项默认展开，新建任务前请核对。</p>
      </div>
      <button class="btn" @click="loadJobs">刷新任务</button>
    </div>

    <div class="workspace-layout">
      <div class="workspace-left">
        <div class="card card-pad upgrade-create-card">
          <div class="upgrade-create-head">
            <h2>新建升级任务</h2>
            <button
              class="btn btn-sm"
              :class="{ primary: showAdvancedPanel }"
              type="button"
              @click="toggleAdvancedPanel"
            >
              高级选项
            </button>
          </div>

          <div v-if="prefillBanner" class="message info upgrade-prefill-banner">{{ prefillBanner }}</div>

          <div class="upgrade-create-body">
            <div class="upgrade-tag-row">
              <div class="field">
                <label>From Tag <span class="required">*</span></label>
                <input v-model="form.from_tag" class="input input-sm mono" placeholder="android14-5.10-..." />
              </div>
              <span class="upgrade-tag-arrow" aria-hidden="true">→</span>
              <div class="field">
                <label>To Tag <span class="required">*</span></label>
                <input v-model="form.to_tag" class="input input-sm mono" placeholder="android14-5.10-..." />
              </div>
            </div>
            <button class="btn primary upgrade-start-btn" :disabled="submitting" @click="startUpgrade">
              {{ submitting ? '启动中...' : '开始升级合入' }}
            </button>
          </div>
          <div v-if="error" class="message error upgrade-form-error">{{ error }}</div>
        </div>

        <div class="card card-pad">
          <div class="section-title">
            <div>
              <h2>升级任务</h2>
              <p>最近 50 条</p>
            </div>
            <div v-if="jobs.length" class="toolbar task-history-toolbar">
              <label class="task-select-all">
                <input
                  type="checkbox"
                  :checked="allJobsSelected"
                  @change="toggleSelectAllJobs(($event.target as HTMLInputElement).checked)"
                />
                全选
              </label>
              <button
                v-if="selectedJobCount > 0"
                class="btn danger btn-sm"
                :disabled="batchDeleting"
                @click="deleteSelectedJobs"
              >
                {{ batchDeleting ? '删除中…' : `批量删除 (${selectedJobCount})` }}
              </button>
            </div>
          </div>
          <div v-if="jobs.length" class="workspace-list">
            <div
              v-for="job in jobs"
              :key="job.id || job.job_id"
              class="selectable-item split task-history-item"
              :class="{
                active: activeJobId === (job.id || job.job_id) && !showAdvancedPanel,
                loading: loadingJobId === (job.id || job.job_id),
              }"
            >
              <label class="task-history-check" @click.stop>
                <input
                  type="checkbox"
                  :checked="selectedJobIds.has(job.id || job.job_id)"
                  @change="toggleJobSelection(job.id || job.job_id, ($event.target as HTMLInputElement).checked)"
                />
              </label>
              <button type="button" class="task-history-main" @click="selectJob(job.id || job.job_id)">
                <span>
                  <strong>{{ job.from_tag || '-' }} -> {{ job.to_tag || '-' }}</strong>
                  <span class="muted mono" style="display: block">{{ shortId(job.id || job.job_id) }}</span>
                </span>
                <span class="pill" :class="loadingJobId === (job.id || job.job_id) ? 'info' : statusTone(jobDisplayStatus(job))">
                  {{ loadingJobId === (job.id || job.job_id) ? '加载中' : upgradeStatusText(jobDisplayStatus(job)) }}
                </span>
              </button>
            </div>
          </div>
          <div v-else class="empty">暂无升级任务</div>
        </div>
      </div>

      <aside class="workspace-detail">
        <UpgradeAdvancedConfig
          v-if="showAdvancedPanel"
          ref="advancedConfigRef"
          :form="form"
          :can-copy-last="jobs.length > 0"
          @close="closeAdvancedPanel"
          @save="saveAdvancedConfig"
          @clear="clearAdvancedConfig"
          @copy-last="copyFromLastJob"
        />

        <div v-else-if="activeJob" class="card card-pad">
          <div v-if="loadingJobId" class="detail-banner">正在加载升级任务：{{ shortId(loadingJobId) }}</div>
          <div v-if="liveHint" class="message info" style="margin-bottom: 12px">{{ liveHint }}</div>

          <div class="upgrade-detail-head">
            <div class="upgrade-detail-title">
              <h2>{{ activeJob.from_tag || '-' }} -> {{ activeJob.to_tag || '-' }}</h2>
              <p class="mono">{{ activeJob.id || activeJob.job_id }}</p>
            </div>
            <div class="upgrade-detail-meta">
              <span class="pill" :class="statusTone(displayStatus)">{{ upgradeStatusText(displayStatus) }}</span>
              <template v-if="displayStatus === 'awaiting_otp'">
                <span class="upgrade-meta-otp-label">cqris OTP</span>
                <input
                  v-model="inlineOtp"
                  class="input mono upgrade-meta-otp-input"
                  maxlength="8"
                  placeholder="6 位动态口令"
                  @keyup.enter="connectSsh"
                />
                <button class="btn primary btn-sm" @click="connectSsh">确认进入</button>
              </template>
              <button class="btn btn-sm" @click="selectJob(activeJob.id || activeJob.job_id)">刷新</button>
              <a
                class="btn btn-sm"
                :href="`/api/upgrade/jobs/${activeJob.id || activeJob.job_id}/execution-log`"
                target="_blank"
              >
                完整执行日志
              </a>
              <button class="btn btn-sm danger" @click="deleteJob">删除</button>
              <button v-if="isCancellable" class="btn btn-sm danger" @click="cancelJob">取消</button>
            </div>
          </div>

          <div class="upgrade-detail-summary">
            <div class="upgrade-summary-item">
              <span class="upgrade-summary-label">合入</span>
              <span class="upgrade-summary-value">squash</span>
            </div>
            <span class="upgrade-summary-divider" aria-hidden="true" />
            <div class="upgrade-summary-item">
              <span class="upgrade-summary-label">冲突</span>
              <span class="upgrade-summary-value">{{ conflictCount }}</span>
            </div>
            <span class="upgrade-summary-divider" aria-hidden="true" />
            <div class="upgrade-summary-item upgrade-summary-item-grow">
              <span class="upgrade-summary-label">目标仓库</span>
              <span class="upgrade-summary-value mono" :title="activeJob.target_repo_dir || '-'">
                {{ activeJob.target_repo_dir || '-' }}
              </span>
            </div>
          </div>

          <div v-if="showPrimaryActionBar" class="upgrade-detail-action-bar">
            <template v-if="displayStatus === 'awaiting_ssh'">
              <span class="upgrade-action-label">远程连接</span>
              <button class="btn primary btn-sm" @click="connectBastion">连接 cqris</button>
            </template>
            <template v-else-if="displayStatus === 'conflicts'">
              <span class="upgrade-action-label">冲突处理</span>
              <button class="btn primary btn-sm" @click="continueJob">冲突已解决，继续</button>
            </template>
            <template v-else-if="displayStatus === 'applied'">
              <span class="upgrade-action-label">提交</span>
              <button class="btn primary btn-sm" @click="commitJob">提交代码</button>
            </template>
            <template v-else-if="displayStatus === 'committed' || displayStatus === 'build_failed'">
              <span class="upgrade-action-label">编译验证</span>
              <div class="upgrade-action-controls">
                <button class="btn primary btn-sm" :disabled="building" @click="buildJob">
                  {{ building ? '编译启动中…' : '开始编译' }}
                </button>
                <button v-if="displayStatus === 'build_failed'" class="btn btn-sm" @click="buildFixRetry">
                  AI 修复并重试
                </button>
              </div>
            </template>
            <template v-else-if="displayStatus === 'commit_failed'">
              <span class="upgrade-action-label">提交代码</span>
              <div class="upgrade-action-controls">
                <button class="btn primary btn-sm" :disabled="committing" @click="commitRetryJob">
                  {{ committing ? '提交中…' : '重新提交' }}
                </button>
              </div>
            </template>
            <template v-else-if="displayStatus === 'cancelled'">
              <span class="upgrade-action-label">恢复任务</span>
              <button class="btn primary btn-sm" @click="resumeJob">继续执行（{{ resumeHint }}）</button>
            </template>
          </div>

          <UpgradeProgressPanel
            :job="activeJob"
            :progress="progress"
            :job-id="activeJob.id || activeJob.job_id"
          />

          <GerritSubmissionsPanel
            :job="activeJob"
            :progress="progress"
          />

          <ConflictPanel
            v-if="showConflictPanel"
            ref="conflictPanelRef"
            :job-id="activeJob.id || activeJob.job_id"
            :job="activeJob"
            :visible="showConflictPanel"
            :auto-resolve="!!activeJob.options?.auto_resolve_conflicts"
            @refresh="refreshActiveJob"
          />

          <BuildFixPanel
            v-if="showBuildFixPanel"
            ref="buildFixPanelRef"
            :job-id="activeJob.id || activeJob.job_id"
            :job="activeJob"
            :visible="showBuildFixPanel"
          />
        </div>

        <div v-else class="card detail-empty">
          <div>
            <strong>右侧工作区</strong>
            <span>选择左侧任务查看详情，或点击「高级选项」配置新任务。</span>
          </div>
        </div>
      </aside>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import BuildFixPanel from '../components/upgrade/BuildFixPanel.vue'
import ConflictPanel from '../components/upgrade/ConflictPanel.vue'
import GerritSubmissionsPanel from '../components/upgrade/GerritSubmissionsPanel.vue'
import UpgradeAdvancedConfig from '../components/upgrade/UpgradeAdvancedConfig.vue'
import UpgradeProgressPanel from '../components/upgrade/UpgradeProgressPanel.vue'
import { api, shortId, statusTone, wsUrl } from '../api'
import { isEmbeddedMode } from '../composables/useEmbeddedNav'

const isEmbedded = isEmbeddedMode()
import {
  UPGRADE_CANCELLABLE,
  effectiveUpgradeStatus,
  ensureRemoteSshSaved,
  jobDisplayStatus,
  remoteSshBody,
  resolveRemoteSshForStart,
  upgradeResumePhaseHint,
  upgradeStatusText,
} from '../utils/upgrade'
import { isUpgradeAutomatedRunning } from '../utils/upgradeProgress'
import {
  applyUpgradeFormDefaults,
  clearUpgradeFormDefaults,
  createEmptyUpgradeForm,
  jobToUpgradeForm,
  saveUpgradeFormDefaults,
} from '../utils/upgradeFormDefaults'

const route = useRoute()
const form = reactive<any>(createEmptyUpgradeForm())

const jobs = ref<any[]>([])
const selectedJobIds = ref<Set<string>>(new Set())
const batchDeleting = ref(false)
const activeJobId = ref('')
const loadingJobId = ref('')
const activeJob = ref<any | null>(null)
const progress = ref<any>({})
const submitting = ref(false)
const building = ref(false)
const committing = ref(false)
const error = ref('')
const liveHint = ref('')
const inlineOtp = ref('')
const showAdvancedPanel = ref(true)
const prefillBanner = ref('')
const advancedConfigRef = ref<InstanceType<typeof UpgradeAdvancedConfig> | null>(null)
const conflictPanelRef = ref<InstanceType<typeof ConflictPanel> | null>(null)
const buildFixPanelRef = ref<InstanceType<typeof BuildFixPanel> | null>(null)
let socket: WebSocket | null = null
let pollTimer: number | null = null

const displayStatus = computed(() => effectiveUpgradeStatus(activeJob.value, progress.value))
const selectedJobCount = computed(() => selectedJobIds.value.size)
const allJobsSelected = computed(() => {
  if (!jobs.value.length) return false
  return jobs.value.every((job) => selectedJobIds.value.has(job.id || job.job_id))
})
const isCancellable = computed(() => UPGRADE_CANCELLABLE.has(displayStatus.value))
const resumeHint = computed(() => upgradeResumePhaseHint(activeJob.value))

const showPrimaryActionBar = computed(() => {
  const st = displayStatus.value
  return (
    st === 'awaiting_ssh'
    || st === 'conflicts'
    || st === 'applied'
    || st === 'committed'
    || st === 'build_failed'
    || st === 'commit_failed'
    || st === 'cancelled'
  )
})

const conflictCount = computed(() => {
  const job = activeJob.value || {}
  const opts = job.options || {}
  return Math.max((job.conflict_files || []).length, (opts.conflict_history_files || []).length, 0)
})

const showPostRunPanels = computed(() => !isUpgradeAutomatedRunning(activeJob.value, progress.value))

const showConflictPanel = computed(
  () =>
    showPostRunPanels.value &&
    (conflictCount.value > 0 || displayStatus.value === 'conflicts'),
)

const showBuildFixPanel = computed(() => {
  if (!showPostRunPanels.value) return false
  const job = activeJob.value || {}
  const opts = job.options || {}
  const attempts = (opts.build_fix || progress.value.build_fix || {}).attempts || []
  return (
    attempts.length > 0 ||
    displayStatus.value === 'build_failed' ||
    displayStatus.value === 'commit_failed' ||
    displayStatus.value === 'completed' ||
    displayStatus.value === 'cancelled'
  )
})

function toggleAdvancedPanel() {
  if (showAdvancedPanel.value) {
    closeAdvancedPanel()
    return
  }
  openAdvancedPanel()
}

async function openAdvancedPanel() {
  showAdvancedPanel.value = true
  await nextTick()
  advancedConfigRef.value?.refreshSshStatus?.()
}

function closeAdvancedPanel() {
  showAdvancedPanel.value = false
}

function saveAdvancedConfig() {
  saveUpgradeFormDefaults(form)
  advancedConfigRef.value?.flashSaved()
}

function clearAdvancedConfig() {
  if (!window.confirm('清除已保存的高级选项？页面将恢复为空。')) return
  clearUpgradeFormDefaults()
  Object.assign(form, createEmptyUpgradeForm())
}

function copyFromLastJob() {
  if (!jobs.value.length) return
  const job = jobs.value[0]
  Object.assign(form, jobToUpgradeForm(job))
  form.remote = true
  prefillBanner.value = `已从最近任务 ${shortId(job.id || job.job_id)} 复制配置（请核对 Tag）`
}

async function loadDefaults() {
  applyUpgradeFormDefaults(form)
  form.remote = true
}

async function prefillFromAnalysisTask(taskId: string) {
  const task = await api.get<any>(`/api/tasks/${taskId}`)
  form.from_tag = task.from_tag || form.from_tag
  form.to_tag = task.to_tag || form.to_tag
  form.analysis_task_id = taskId
  prefillBanner.value = '已从分析任务预填 Tag'
}

async function loadJobs() {
  const data = await api.get<any>('/api/upgrade/jobs?limit=50')
  jobs.value = data.jobs || []
  const valid = new Set(jobs.value.map((job) => job.id || job.job_id))
  const next = new Set<string>()
  for (const id of selectedJobIds.value) {
    if (valid.has(id)) next.add(id)
  }
  selectedJobIds.value = next
}

function toggleJobSelection(jobId: string, checked: boolean) {
  const next = new Set(selectedJobIds.value)
  if (checked) next.add(jobId)
  else next.delete(jobId)
  selectedJobIds.value = next
}

function toggleSelectAllJobs(checked: boolean) {
  selectedJobIds.value = checked
    ? new Set(jobs.value.map((job) => job.id || job.job_id))
    : new Set()
}

function clearActiveJobDetail() {
  if (socket) socket.close()
  stopPoll()
  activeJob.value = null
  activeJobId.value = ''
  progress.value = {}
}

function stopPoll() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

function startPoll(jobId: string) {
  stopPoll()
  pollTimer = window.setInterval(() => refreshActiveJob(jobId), 3000)
}

async function refreshActiveJob(jobId?: string) {
  const id = jobId || activeJobId.value
  if (!id) return
  try {
    const data = await api.get<any>(`/api/upgrade/jobs/${id}`)
    activeJob.value = data.job
    progress.value = data.progress || {}
  } catch {
    // ignore polling errors
  }
}

async function selectJob(jobId: string) {
  showAdvancedPanel.value = false
  error.value = ''
  activeJobId.value = jobId
  loadingJobId.value = jobId
  liveHint.value = ''
  if (socket) socket.close()
  stopPoll()
  try {
    const data = await api.get<any>(`/api/upgrade/jobs/${jobId}`)
    activeJob.value = data.job
    progress.value = data.progress || {}
    socket = new WebSocket(wsUrl(`/ws/upgrade/${jobId}`))
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data || '{}')
      progress.value = payload
      if (payload.job) activeJob.value = payload.job
    }
    socket.onclose = () => {
      socket = null
      liveHint.value = '实时连接已断开，已切换为轮询更新'
      startPoll(jobId)
    }
  } catch (err: any) {
    error.value = err.message || String(err)
  } finally {
    loadingJobId.value = ''
  }
}

async function startUpgrade() {
  if (!form.from_tag || !form.to_tag) {
    error.value = '请填写 From Tag 和 To Tag'
    return
  }
  if (!form.target_repo_dir?.trim()) {
    error.value = '请先在「高级选项」中填写合入目标代码路径'
    openAdvancedPanel()
    return
  }
  if (form.auto_build && (!form.build_workdir || !form.build_command)) {
    error.value = '自动编译已开启，请在「高级选项」中填写编译工作目录和命令'
    openAdvancedPanel()
    return
  }
  submitting.value = true
  error.value = ''
  try {
    const body: Record<string, unknown> = {
      ...form,
      remote: true,
      apply_mode: 'squash',
      upgrade_branch: '',
      commit_message_file: '',
    }
    const remoteSsh = await resolveRemoteSshForStart(() => api.get<any>('/api/upgrade/ssh-config'))
    if (remoteSsh) body.remote_ssh = remoteSsh
    const data = await api.post<any>('/api/upgrade', body)
    showAdvancedPanel.value = false
    await loadJobs()
    await selectJob(data.job_id)
    if (data.awaiting_ssh) {
      liveHint.value = '任务已创建，请先连接 cqris 堡垒机'
    }
  } catch (err: any) {
    error.value = err.message || String(err)
  } finally {
    submitting.value = false
  }
}

async function continueJob() {
  if (!activeJob.value) return
  const jobId = activeJob.value.id || activeJob.value.job_id
  const body: Record<string, unknown> = {
    ...(await remoteSshBody(activeJob.value, () => api.get<any>('/api/upgrade/ssh-config'))),
  }
  await api.post(`/api/upgrade/jobs/${jobId}/continue`, body)
  startPoll(jobId)
  await refreshActiveJob(jobId)
}

async function commitJob() {
  if (!activeJob.value) return
  const jobId = activeJob.value.id || activeJob.value.job_id
  const body: Record<string, unknown> = {
    ...(await remoteSshBody(activeJob.value, () => api.get<any>('/api/upgrade/ssh-config'))),
  }
  const resp = await api.post<any>(`/api/upgrade/jobs/${jobId}/commit`, body)
  alert(resp.commit_sha ? `提交成功: ${resp.commit_sha}` : resp.message || '提交完成')
  startPoll(jobId)
  await refreshActiveJob(jobId)
}

async function buildJob() {
  if (!activeJob.value) return
  const jobId = activeJob.value.id || activeJob.value.job_id
  let workdir = (activeJob.value.build_workdir || form.build_workdir || '').trim()
  let command = (activeJob.value.build_command || form.build_command || '').trim()
  if (!workdir) workdir = window.prompt('请输入编译工作目录:', form.build_workdir)?.trim() || ''
  if (!command) command = window.prompt('请输入编译命令:', form.build_command)?.trim() || ''
  if (!workdir || !command) {
    alert('编译需要同时提供工作目录和命令')
    return
  }
  building.value = true
  liveHint.value = '正在启动编译…'
  try {
    const body: Record<string, unknown> = {
      build_workdir: workdir,
      build_command: command,
      auto_fix_build_errors: form.auto_fix_build_errors || activeJob.value.options?.auto_fix_build_errors,
    }
    Object.assign(body, await remoteSshBody(activeJob.value, () => api.get<any>('/api/upgrade/ssh-config')))
    const resp = await api.post<any>(`/api/upgrade/jobs/${jobId}/build`, body)
    liveHint.value = resp.message || '编译已在后台启动'
    startPoll(jobId)
    await refreshActiveJob(jobId)
  } catch (err: any) {
    alert(`编译启动失败: ${err.message}`)
    liveHint.value = ''
  } finally {
    building.value = false
  }
}

async function commitRetryJob() {
  if (!activeJob.value) return
  const jobId = activeJob.value.id || activeJob.value.job_id
  committing.value = true
  liveHint.value = '正在重新提交并推送…'
  try {
    const body: Record<string, unknown> = {
      ...(await remoteSshBody(activeJob.value, () => api.get<any>('/api/upgrade/ssh-config'))),
    }
    const resp = await api.post<any>(`/api/upgrade/jobs/${jobId}/commit-retry`, body)
    liveHint.value = resp.message || '提交完成'
    startPoll(jobId)
    await refreshActiveJob(jobId)
  } catch (err: any) {
    alert(`提交失败: ${err.message}`)
    liveHint.value = ''
  } finally {
    committing.value = false
  }
}

async function buildFixRetry() {
  if (!activeJob.value || !confirm('将启用 AI 编译修复并重新编译。是否继续？')) return
  const jobId = activeJob.value.id || activeJob.value.job_id
  liveHint.value = '正在启动 AI 修复并重试编译…'
  try {
    const body: Record<string, unknown> = {
      ...(await remoteSshBody(activeJob.value, () => api.get<any>('/api/upgrade/ssh-config'))),
    }
    const resp = await api.post<any>(`/api/upgrade/jobs/${jobId}/build/fix-retry`, body)
    liveHint.value = resp.message || 'AI 修复重试已启动'
    startPoll(jobId)
    await refreshActiveJob(jobId)
  } catch (err: any) {
    alert(`启动失败: ${err.message}`)
    liveHint.value = ''
  }
}

async function resumeJob() {
  if (!activeJob.value) return
  const hint = resumeHint.value
  if (!confirm(`从取消前的「${hint}」阶段继续执行？`)) return
  const jobId = activeJob.value.id || activeJob.value.job_id
  liveHint.value = '正在恢复任务…'
  try {
    const body: Record<string, unknown> = {
      ...(await remoteSshBody(activeJob.value, () => api.get<any>('/api/upgrade/ssh-config'))),
    }
    const resp = await api.post<any>(`/api/upgrade/jobs/${jobId}/resume`, body)
    liveHint.value = resp.message || '已继续执行'
    startPoll(jobId)
    await refreshActiveJob(jobId)
  } catch (err: any) {
    alert(`继续执行失败: ${err.message}`)
    liveHint.value = ''
  }
}

async function connectBastion() {
  if (!activeJob.value) return
  const jobId = activeJob.value.id || activeJob.value.job_id
  try {
    await ensureRemoteSshSaved(
      () => api.get<any>('/api/upgrade/ssh-config'),
      (creds) => api.put('/api/upgrade/ssh-credentials', creds),
    )
    await api.post(`/api/upgrade/jobs/${jobId}/ssh-bastion`, {})
    await refreshActiveJob(jobId)
  } catch (err: any) {
    alert(err.message || String(err))
  }
}

async function connectSsh() {
  if (!activeJob.value) return
  const otp = inlineOtp.value.trim()
  if (otp.length < 4) {
    alert('请输入 6 位 OTP')
    return
  }
  const jobId = activeJob.value.id || activeJob.value.job_id
  await api.post(`/api/upgrade/jobs/${jobId}/ssh-connect`, { otp })
  inlineOtp.value = ''
  await refreshActiveJob(jobId)
}

async function cancelJob() {
  if (!activeJob.value || !confirm('确定取消此升级任务？')) return
  const jobId = activeJob.value.id || activeJob.value.job_id
  stopPoll()
  await api.post(`/api/upgrade/jobs/${jobId}/cancel`, {})
  await refreshActiveJob(jobId)
}

async function deleteJob() {
  if (!activeJob.value || !confirm('确定删除此升级任务记录？')) return
  const jobId = activeJob.value.id || activeJob.value.job_id
  await api.delete(`/api/upgrade/jobs/${jobId}`)
  const next = new Set(selectedJobIds.value)
  next.delete(jobId)
  selectedJobIds.value = next
  clearActiveJobDetail()
  await loadJobs()
}

async function deleteSelectedJobs() {
  const ids = [...selectedJobIds.value]
  if (!ids.length) return
  if (!confirm(`确定删除选中的 ${ids.length} 个升级任务记录？`)) return
  batchDeleting.value = true
  error.value = ''
  try {
    await Promise.all(ids.map((id) => api.delete(`/api/upgrade/jobs/${id}`)))
    if (ids.includes(activeJobId.value)) {
      clearActiveJobDetail()
    }
    selectedJobIds.value = new Set()
    await loadJobs()
  } catch (err: any) {
    error.value = err.message || String(err)
  } finally {
    batchDeleting.value = false
  }
}

onMounted(async () => {
  await loadDefaults()
  await loadJobs()
  const taskId = String(route.query.task || '')
  if (taskId) {
    try {
      await prefillFromAnalysisTask(taskId)
    } catch (err: any) {
      error.value = err.message || '加载分析任务失败'
    }
  }
  const jobId = String(route.query.job || '')
  if (jobId) {
    await selectJob(jobId)
  } else {
    await openAdvancedPanel()
  }
})

onBeforeUnmount(() => {
  if (socket) socket.close()
  stopPoll()
})
</script>

<style scoped>
.required {
  color: var(--danger);
}

.upgrade-create-card.card-pad {
  padding: 14px 16px;
}

.upgrade-create-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.upgrade-create-head h2 {
  margin: 0;
  font-size: 16px;
}

.upgrade-create-body {
  display: grid;
  gap: 10px;
}

.upgrade-tag-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
  gap: 8px;
  align-items: end;
}

.upgrade-tag-row .field {
  gap: 4px;
  min-width: 0;
}

.upgrade-tag-row .field label {
  font-size: 11px;
}

.upgrade-tag-arrow {
  padding-bottom: 7px;
  color: #94a3b8;
  font-size: 15px;
  line-height: 1;
  user-select: none;
}

.input-sm {
  padding: 6px 8px;
  font-size: 12px;
}

.upgrade-start-btn {
  width: 100%;
  padding: 8px 12px;
  font-size: 13px;
}

.btn-sm {
  padding: 3px 9px;
  font-size: 12px;
}

.upgrade-prefill-banner {
  margin-bottom: 8px;
  font-size: 12px;
}

.upgrade-form-error {
  margin-top: 8px;
  font-size: 12px;
}

.upgrade-detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}

.upgrade-detail-title {
  min-width: 0;
  flex: 1;
}

.upgrade-detail-title h2 {
  margin: 0;
  font-size: 18px;
  line-height: 1.3;
}

.upgrade-detail-title p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--muted);
  word-break: break-all;
}

.upgrade-detail-meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 6px;
  flex: 0 0 auto;
  max-width: 100%;
}

.upgrade-meta-otp-label {
  font-size: 12px;
  font-weight: 700;
  color: #334155;
  white-space: nowrap;
}

.upgrade-meta-otp-input {
  width: 120px;
  padding: 5px 8px;
  font-size: 13px;
}

.upgrade-detail-action-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  padding: 8px 12px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: #f8fbff;
}

.upgrade-action-label {
  flex: 0 0 auto;
  font-size: 12px;
  font-weight: 700;
  color: #334155;
  white-space: nowrap;
}

.upgrade-action-controls {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  margin-left: auto;
}

.upgrade-detail-summary {
  display: flex;
  align-items: center;
  gap: 0;
  margin-bottom: 10px;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: #fafbfc;
  min-width: 0;
}

.upgrade-summary-item {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  padding: 0 12px;
}

.upgrade-summary-item:first-child {
  padding-left: 0;
}

.upgrade-summary-item-grow {
  flex: 1;
  min-width: 0;
}

.upgrade-summary-label {
  flex: 0 0 auto;
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
  white-space: nowrap;
}

.upgrade-summary-value {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  word-break: break-all;
}

.upgrade-summary-divider {
  width: 1px;
  align-self: stretch;
  background: #e2e8f0;
  flex: 0 0 auto;
}

.btn-sm {
  padding: 3px 9px;
  font-size: 12px;
}
</style>
