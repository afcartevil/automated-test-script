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
  handleModifyCaseResult,
  handleRetestCase,
  handleManualDecision,
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
    <div class="modify-dialog">
      <div class="modify-dialog-header">
        <span class="section-title">{{ manualDeviceName || '需人工确认' }}</span>
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

.manual-message {
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
}
</style>
