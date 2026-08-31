<template>
  <div class="card card-pad upgrade-advanced-panel">
    <div class="upgrade-topbar">
      <h2>高级选项</h2>
      <div class="upgrade-topbar-actions">
        <button type="button" class="btn btn-sm" @click="$emit('copy-last')" :disabled="!canCopyLast">
          复制上次任务
        </button>
        <button class="btn btn-sm" type="button" @click="$emit('clear')">清除配置</button>
        <button class="btn btn-sm primary" type="button" @click="$emit('save')">保存配置</button>
        <button class="btn btn-sm" type="button" @click="$emit('close')">返回</button>
      </div>
    </div>

    <div class="upgrade-auto-bar">
      <span class="upgrade-auto-label">自动化</span>
      <div class="upgrade-auto-items">
        <label class="upgrade-auto-item">
          <input v-model="form.auto_commit" type="checkbox" />
          <span>自动提交</span>
        </label>
        <label class="upgrade-auto-item">
          <input v-model="form.auto_build" type="checkbox" />
          <span>自动编译</span>
        </label>
        <label class="upgrade-auto-item">
          <input v-model="form.auto_resolve_conflicts" type="checkbox" />
          <span>AI 冲突合入</span>
        </label>
        <label class="upgrade-auto-item">
          <input v-model="form.auto_fix_build_errors" type="checkbox" />
          <span>AI 编译修复</span>
        </label>
      </div>
    </div>

    <div class="upgrade-config-card">
      <div class="upgrade-config-head">
        <span class="upgrade-config-title">路径与编译</span>
        <div class="upgrade-config-head-meta">
          <span v-if="sshLoading" class="upgrade-ssh-status muted">检查 SSH…</span>
          <span v-else-if="sshConfigured" class="upgrade-ssh-status ok">
            <svg class="upgrade-ssh-icon" viewBox="0 0 16 16" aria-hidden="true">
              <circle cx="8" cy="8" r="7" fill="currentColor" opacity="0.15" />
              <path
                d="M4.5 8.2 6.8 10.5 11.5 5.8"
                fill="none"
                stroke="currentColor"
                stroke-width="1.6"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            {{ sshManagedByEa ? 'SSH 已托管（EasyAdapter）' : 'SSH 已配置' }}
          </span>
          <span v-else class="upgrade-ssh-status warn">
            <span v-if="sshManagedByEa || isEmbedded">
              SSH 未就绪，请在 EasyAdapter「一键配置」补全后重启
            </span>
            <template v-else>
              <span>SSH 未配置，远程任务需先保存账号</span>
              <button class="btn btn-sm" type="button" @click="goSshSettings">去设置</button>
            </template>
          </span>
          <span class="upgrade-remote-badge">cqris 远程</span>
        </div>
      </div>

      <div class="upgrade-field-grid">
        <div class="field span-all">
          <label>合入目标代码路径 <span class="required">*</span></label>
          <input v-model="form.target_repo_dir" class="input input-sm mono" :placeholder="targetRepoPlaceholder" />
        </div>
        <div class="field">
          <label>服务器映射路径</label>
          <input v-model="form.local_repo_mount" class="input input-sm mono" placeholder="可选" />
        </div>
        <div class="field">
          <label>远程临时工作目录</label>
          <input v-model="form.remote_temp_dir" class="input input-sm mono" placeholder="/tmp" />
        </div>
        <div class="field">
          <label>编译工作目录</label>
          <input v-model="form.build_workdir" class="input input-sm mono" :placeholder="buildWorkdirPlaceholder" />
        </div>
        <div class="field">
          <label>编译命令</label>
          <input v-model="form.build_command" class="input input-sm mono" placeholder="./build/build.sh" />
        </div>
      </div>

      <div class="upgrade-commit-block">
        <label>Commit message</label>
        <textarea
          v-model="form.commit_message"
          class="input input-sm upgrade-commit-message mono"
          rows="6"
          placeholder="留空使用默认"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api'
import { isEmbeddedMode } from '../../composables/useEmbeddedNav'

const props = defineProps<{
  form: Record<string, any>
  canCopyLast?: boolean
}>()

defineEmits<{
  close: []
  save: []
  clear: []
  'copy-last': []
}>()

const router = useRouter()
const isEmbedded = isEmbeddedMode()
const sshConfigured = ref(false)
const sshManagedByEa = ref(false)
const sshLoading = ref(true)

const targetRepoPlaceholder = '/work/.../vnd/kernel-5.10'
const buildWorkdirPlaceholder = '/work/.../vnd'

function ensureRemote() {
  props.form.remote = true
}

async function loadSshStatus() {
  sshLoading.value = true
  try {
    const cfg = await api.get<any>('/api/upgrade/ssh-config')
    sshConfigured.value = !!cfg.credentials_configured
    sshManagedByEa.value = !!(cfg.managed_by_ea || cfg.readonly)
  } catch {
    sshConfigured.value = false
    sshManagedByEa.value = false
  } finally {
    sshLoading.value = false
  }
}

function goSshSettings() {
  router.push({ name: 'settings', query: { section: 'ssh' } })
}

onMounted(() => {
  ensureRemote()
  loadSshStatus()
})

function flashSaved() {
  // no-op
}

defineExpose({ flashSaved, refreshSshStatus: loadSshStatus })
</script>

<style scoped>
.upgrade-advanced-panel.card-pad {
  padding: 14px 16px;
}

.upgrade-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.upgrade-topbar h2 {
  margin: 0;
  font-size: 16px;
  white-space: nowrap;
}

.upgrade-topbar-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 6px;
}

.btn-sm {
  padding: 3px 9px;
  font-size: 12px;
}

.required {
  color: var(--danger);
}

.upgrade-auto-bar {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 12px;
  padding: 8px 10px;
  border: 1px solid #dbeafe;
  border-radius: 8px;
  background: linear-gradient(180deg, #f8fbff 0%, #f1f5f9 100%);
}

.upgrade-auto-label {
  flex: 0 0 auto;
  margin-top: 5px;
  color: #64748b;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.upgrade-auto-items {
  display: flex;
  flex: 1;
  flex-wrap: wrap;
  gap: 6px;
}

.upgrade-auto-item {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #fff;
  cursor: pointer;
  font-size: 12px;
  line-height: 1.2;
  white-space: nowrap;
}

.upgrade-auto-item:has(input:checked) {
  border-color: #93c5fd;
  background: #eff6ff;
  color: #1d4ed8;
}

.upgrade-auto-item input {
  margin: 0;
}

.upgrade-config-card {
  border: 1px solid var(--border);
  border-radius: 10px;
  background: #fafbfc;
  overflow: hidden;
}

.upgrade-config-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid #e2e8f0;
  background: #fff;
}

.upgrade-config-head-meta {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.upgrade-ssh-status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  line-height: 1.3;
}

.upgrade-ssh-status.muted {
  color: #94a3b8;
}

.upgrade-ssh-status.ok {
  color: #15803d;
  font-weight: 600;
}

.upgrade-ssh-status.warn {
  color: #b45309;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.upgrade-ssh-icon {
  width: 16px;
  height: 16px;
  flex: 0 0 auto;
}

.upgrade-config-title {
  font-size: 12px;
  font-weight: 700;
  color: #334155;
}

.upgrade-remote-badge {
  padding: 2px 8px;
  border-radius: 999px;
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  color: #1d4ed8;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
}

.upgrade-field-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 12px;
  padding: 12px;
}

.upgrade-field-grid .span-all {
  grid-column: 1 / -1;
}

.upgrade-advanced-panel .field {
  display: grid;
  gap: 4px;
  min-width: 0;
}

.upgrade-advanced-panel .field label {
  font-size: 11px;
  font-weight: 700;
  color: #435266;
}

.input-sm {
  padding: 6px 8px;
  font-size: 12px;
}

.upgrade-commit-block {
  display: grid;
  gap: 6px;
  padding: 0 12px 12px;
  border-top: 1px dashed #dbe3ea;
  margin-top: 2px;
  padding-top: 12px;
}

.upgrade-commit-block label {
  font-size: 11px;
  font-weight: 700;
  color: #435266;
}

.upgrade-commit-message {
  resize: vertical;
  min-height: 132px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
}

@media (max-width: 720px) {
  .upgrade-field-grid {
    grid-template-columns: 1fr;
  }

  .upgrade-auto-bar {
    flex-direction: column;
    gap: 6px;
  }

  .upgrade-auto-label {
    margin-top: 0;
  }
}
</style>
