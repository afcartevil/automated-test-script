<script setup lang="ts">
import { inject } from 'vue'
import { DEVICE_SELF_CHECK_KEY } from './self-check-context'

const {
  showModifyDialog,
  modifyStatus,
  modifyMessage,
  showRetestDialog,
  retestAuxDeviceId,
  retesting,
  availableAuxForRetest,
  showManualDialog,
  manualDeviceName,
  manualMessage,
  manualMode,
  manualSubmitting,
  manualFailLabel,
  manualPassLabel,
  manualQueueRemaining,
  showGmsTradefedDialog,
  gmsTradefedDraft,
  gmsPathPickingSuite,
  catalogSettingsSaving,
  handleModifyCaseResult,
  handleRetestCase,
  handleManualDecision,
  handleBrowseGmsTradefedPath,
  closeGmsTradefedDialog,
  saveGmsTradefedSettingsFromDialog,
  showOtaPretestDialog,
  otaPretestDraft,
  otaPretestPathPicking,
  otaPretestConfigSaving,
  handleBrowseOtaPretestPath,
  closeOtaPretestDialog,
  saveOtaPretestSettingsFromDialog,
} = inject(DEVICE_SELF_CHECK_KEY)!
</script>

<template>
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
          <textarea v-model="modifyMessage" class="form-input" rows="3" placeholder="输入备注..." />
        </div>
      </div>
      <div class="modify-dialog-footer">
        <button type="button" class="ea-btn-ghost" @click="showModifyDialog = false">取消</button>
        <button type="button" class="ea-btn-primary" @click="handleModifyCaseResult">确认修改</button>
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
          {{ retesting ? '正在复测...' : '开始复测' }}
        </button>
      </div>
    </div>
  </div>

  <div v-if="showManualDialog" class="modify-overlay">
    <div class="modify-dialog manual-confirm-dialog">
      <div class="modify-dialog-header">
        <span class="section-title">{{ manualDeviceName || '需人工确认' }}</span>
        <span v-if="manualQueueRemaining > 0" class="manual-queue-hint">
          还有 {{ manualQueueRemaining }} 台待确认
        </span>
      </div>
      <div class="modify-dialog-body">
        <p class="manual-message">{{ manualMessage }}</p>
      </div>
      <div class="modify-dialog-footer">
        <template v-if="manualMode === 'ack'">
          <button type="button" class="ea-btn-primary" :disabled="manualSubmitting" @click="handleManualDecision('ack')">
            {{ manualSubmitting ? '提交中...' : '知道了' }}
          </button>
        </template>
        <template v-else>
          <button type="button" class="ea-btn-ghost" :disabled="manualSubmitting" @click="handleManualDecision('fail')">
            {{ manualFailLabel }}
          </button>
          <button type="button" class="ea-btn-primary" :disabled="manualSubmitting" @click="handleManualDecision('pass')">
            {{ manualSubmitting ? '提交中...' : manualPassLabel }}
          </button>
        </template>
      </div>
    </div>
  </div>

  <div v-if="showGmsTradefedDialog" class="modify-overlay" @click.self="closeGmsTradefedDialog">
    <div class="modify-dialog gms-tradefed-dialog">
      <div class="modify-dialog-header">
        <span class="section-title">GMS Tradefed 路径配置</span>
        <button type="button" class="ea-btn-ghost ea-btn-sm" @click="closeGmsTradefedDialog">✕</button>
      </div>
      <div class="modify-dialog-body">
        <p class="gms-tradefed-dialog-hint">
          配置 Linux 服务器上的 cts/gts/vts-tradefed 可执行文件路径，保存后对所有 GMS 用例生效。
        </p>
        <div class="form-group">
          <label class="form-label" for="gms-dialog-cts">cts-tradefed</label>
          <div class="gms-tradefed-path-row">
            <input
              id="gms-dialog-cts"
              v-model.trim="gmsTradefedDraft.cts"
              type="text"
              class="form-input"
              placeholder="/opt/gms/android-cts/tools/cts-tradefed"
            />
            <button
              type="button"
              class="ea-btn-ghost ea-btn-sm"
              :disabled="catalogSettingsSaving || gmsPathPickingSuite === 'cts'"
              @click="handleBrowseGmsTradefedPath('cts')"
            >
              {{ gmsPathPickingSuite === 'cts' ? '选择中...' : '浏览' }}
            </button>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label" for="gms-dialog-gts">gts-tradefed</label>
          <div class="gms-tradefed-path-row">
            <input
              id="gms-dialog-gts"
              v-model.trim="gmsTradefedDraft.gts"
              type="text"
              class="form-input"
              placeholder="/opt/gms/android-gts/tools/gts-tradefed"
            />
            <button
              type="button"
              class="ea-btn-ghost ea-btn-sm"
              :disabled="catalogSettingsSaving || gmsPathPickingSuite === 'gts'"
              @click="handleBrowseGmsTradefedPath('gts')"
            >
              {{ gmsPathPickingSuite === 'gts' ? '选择中...' : '浏览' }}
            </button>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label" for="gms-dialog-vts">vts-tradefed</label>
          <div class="gms-tradefed-path-row">
            <input
              id="gms-dialog-vts"
              v-model.trim="gmsTradefedDraft.vts"
              type="text"
              class="form-input"
              placeholder="/opt/gms/android-vts/tools/vts-tradefed"
            />
            <button
              type="button"
              class="ea-btn-ghost ea-btn-sm"
              :disabled="catalogSettingsSaving || gmsPathPickingSuite === 'vts'"
              @click="handleBrowseGmsTradefedPath('vts')"
            >
              {{ gmsPathPickingSuite === 'vts' ? '选择中...' : '浏览' }}
            </button>
          </div>
        </div>
        <p class="gms-tradefed-dialog-footnote">
          执行命令形如 cts-tradefed run &lt;name&gt; -s &lt;serial&gt;
        </p>
      </div>
      <div class="modify-dialog-footer">
        <button type="button" class="ea-btn-ghost" :disabled="catalogSettingsSaving" @click="closeGmsTradefedDialog">
          取消
        </button>
        <button
          type="button"
          class="ea-btn-primary"
          :disabled="catalogSettingsSaving"
          @click="saveGmsTradefedSettingsFromDialog"
        >
          {{ catalogSettingsSaving ? '保存中...' : '保存' }}
        </button>
      </div>
    </div>
  </div>

  <div v-if="showOtaPretestDialog" class="modify-overlay" @click.self="closeOtaPretestDialog">
    <div class="modify-dialog gms-tradefed-dialog">
      <div class="modify-dialog-header">
        <span class="section-title">刷机配置</span>
        <button type="button" class="ea-btn-ghost ea-btn-sm" @click="closeOtaPretestDialog">✕</button>
      </div>
      <div class="modify-dialog-body">
        <p class="gms-tradefed-dialog-hint">同一账号用于刷 UD 和 OEM 解锁，保存在本机，重启后仍然有效。</p>
        <div class="form-group">
          <label class="form-label" for="ota-pretest-user">账号</label>
          <input id="ota-pretest-user" v-model.trim="otaPretestDraft.username" type="text" class="form-input" placeholder="例如 18660000" autocomplete="username" />
        </div>
        <div class="form-group">
          <label class="form-label" for="ota-pretest-password">密码</label>
          <input id="ota-pretest-password" v-model="otaPretestDraft.password" type="password" class="form-input" placeholder="OA Password" autocomplete="current-password" />
        </div>
        <div class="form-group">
          <label class="form-label" for="ota-pretest-swd">SWD 工具目录</label>
          <div class="gms-tradefed-path-row">
            <input id="ota-pretest-swd" v-model.trim="otaPretestDraft.swdToolDir" type="text" class="form-input" placeholder="含 SWD_Development_Center.exe" />
            <button type="button" class="ea-btn-ghost ea-btn-sm" :disabled="otaPretestPathPicking != null" @click="handleBrowseOtaPretestPath('swdTool')">
              {{ otaPretestPathPicking === 'swdTool' ? '选择中...' : '浏览' }}
            </button>
          </div>
        </div>
      </div>
      <div class="modify-dialog-footer">
        <button type="button" class="ea-btn-ghost" :disabled="otaPretestConfigSaving" @click="closeOtaPretestDialog">取消</button>
        <button type="button" class="ea-btn-primary" :disabled="otaPretestConfigSaving" @click="saveOtaPretestSettingsFromDialog">
          {{ otaPretestConfigSaving ? '保存中...' : '保存' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.section-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.form-group { margin-bottom: 16px; }

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
  color: var(--text, #222);
}

.modify-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--line);
}

.manual-queue-hint {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--accent, #2563eb);
  white-space: nowrap;
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

.manual-message {
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  max-height: min(50vh, 420px);
  overflow-y: auto;
}

.manual-confirm-dialog {
  width: 560px;
}

.gms-tradefed-dialog {
  width: 560px;
}

.gms-tradefed-dialog-hint,
.gms-tradefed-dialog-footnote {
  font-size: 13px;
  line-height: 1.5;
  color: var(--muted);
  margin: 0 0 16px;
}

.gms-tradefed-dialog-footnote {
  margin: 0;
}

.gms-tradefed-path-row {
  display: flex;
  align-items: center;
  gap: 8px;

  .form-input {
    flex: 1;
    min-width: 0;
  }
}
</style>
