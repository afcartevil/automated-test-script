<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { NButton, NInput, NForm, NFormItem, useMessage } from 'naive-ui'
import SettingRow from '@/components/hermes/settings/SettingRow.vue'
import {
  fetchGerritConfig,
  saveGerritConfig,
  type GerritConfigPublic,
} from '@/api/tahp/gerrit-config'

const DEFAULT_HOST = 'https://gerrit.transsion.com'
const PASSWORD_PLACEHOLDER = '••••••••'

const message = useMessage()
const loading = ref(false)
const saving = ref(false)
const passwordSet = ref(false)
const passwordTouched = ref(false)

const form = ref({
  host: DEFAULT_HOST,
  user: '',
  password: '',
})

function applyConfig(data: GerritConfigPublic) {
  form.value.host = data.host || DEFAULT_HOST
  form.value.user = data.user || ''
  passwordSet.value = data.passwordSet
  passwordTouched.value = false
  form.value.password = data.passwordSet ? PASSWORD_PLACEHOLDER : ''
}

onMounted(async () => {
  loading.value = true
  try {
    const data = await fetchGerritConfig()
    applyConfig(data)
  } catch (err) {
    const msg = (err as Error).message || ''
    if (/failed to fetch|networkerror|load failed/i.test(msg)) {
      message.error('无法连接后端服务，请确认已执行 npm run dev 且 server:8650 已启动')
    } else {
      message.error(msg || '加载 Gerrit 配置失败')
    }
  } finally {
    loading.value = false
  }
})

function onPasswordInput(value: string) {
  passwordTouched.value = true
  form.value.password = value
}

async function handleSave() {
  const host = form.value.host.trim() || DEFAULT_HOST
  const user = form.value.user.trim()
  const passwordRaw = form.value.password.trim()

  if (!user) {
    message.warning('请填写 Gerrit 账号')
    return
  }

  const payload: { host: string; user: string; password?: string } = { host, user }
  if (passwordTouched.value) {
    if (!passwordRaw) {
      message.warning('请填写 Gerrit HTTP Password')
      return
    }
    payload.password = passwordRaw
  } else if (!passwordSet.value) {
    message.warning('请填写 Gerrit HTTP Password')
    return
  }

  saving.value = true
  try {
    const data = await saveGerritConfig(payload)
    applyConfig(data)
    message.success('Gerrit 账号已保存')
  } catch (err) {
    const msg = (err as Error).message || ''
    if (/failed to fetch|networkerror|load failed/i.test(msg)) {
      message.error('无法连接后端服务，请确认已执行 npm run dev 且 server:8650 已启动')
    } else {
      message.error(msg || '保存失败')
    }
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="settings-section">
    <p class="section-desc">
      账号为 Gerrit 登录账号；密码请在 Gerrit 网页
      <strong>Settings → HTTP Password</strong>
      中生成后填入。
    </p>

    <NForm label-placement="top" class="gerrit-form">
      <NFormItem label="Gerrit Host">
        <NInput
          v-model:value="form.host"
          placeholder="https://gerrit.transsion.com"
          :disabled="loading"
        />
      </NFormItem>
      <NFormItem label="账号">
        <NInput
          v-model:value="form.user"
          placeholder="Gerrit 登录账号"
          :disabled="loading"
        />
      </NFormItem>
      <NFormItem label="HTTP Password">
        <NInput
          :value="form.password"
          type="password"
          show-password-on="click"
          placeholder="从 Gerrit Settings → HTTP Password 获取"
          :disabled="loading"
          @update:value="onPasswordInput"
        />
      </NFormItem>
    </NForm>

    <SettingRow label="保存配置" hint="保存后 AI 自检 Gerrit Code Review 将自动使用此账号">
      <NButton type="primary" :loading="saving" :disabled="loading" @click="handleSave">
        保存
      </NButton>
    </SettingRow>
  </section>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.settings-section {
  margin-top: 16px;
}

.section-desc {
  font-size: 13px;
  color: $text-muted;
  margin: 0 0 16px;
  line-height: 1.6;
}

.gerrit-form {
  max-width: 520px;
  margin-bottom: 8px;
}
</style>
