<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import {
  NButton, NSpin, NAlert, NForm, NFormItem, NInput, NSpace, useMessage,
} from 'naive-ui'
import {
  fetchUnifiedConfigForm,
  saveUnifiedConfigForm,
  type UnifiedConfigField,
} from '@/api/tahp/skill-config'
import {
  hasAnySavedFormValue,
  SKILL_CONFIG_CHECK_BUTTON_LABEL,
} from '@/utils/config-navigation'

const emit = defineEmits<{
  startBatch: []
}>()

const message = useMessage()
const formActionsRef = ref<HTMLElement | null>(null)

const formFields = ref<UnifiedConfigField[]>([])
const formValues = ref<Record<string, string>>({})
/** unified-config.json 中已落盘的值 */
const savedValues = ref<Record<string, string>>({})
const formLoading = ref(false)
const formSaving = ref(false)

const formGroups = computed(() => {
  const groups: Array<{ name: string; fields: UnifiedConfigField[] }> = []
  for (const f of formFields.value) {
    let g = groups.find(x => x.name === f.group)
    if (!g) { g = { name: f.group, fields: [] }; groups.push(g) }
    g.fields.push(f)
  }
  return groups
})

/** 默认显示按钮；已保存数据中至少一项非空时可点击 */
const canStartSkillCheck = computed(() =>
  hasAnySavedFormValue(savedValues.value, formFields.value),
)

function scrollToFormActions() {
  const shell = document.querySelector('.ck-content')
  if (shell) {
    shell.scrollTo({ top: shell.scrollHeight, behavior: 'smooth' })
  }
  formActionsRef.value?.scrollIntoView({ behavior: 'smooth', block: 'end' })
}

async function loadUnifiedForm() {
  formLoading.value = true
  try {
    const data = await fetchUnifiedConfigForm()
    formFields.value = data.fields
    formValues.value = { ...data.values }
    savedValues.value = { ...(data.saved_values ?? {}) }
  } catch (err) {
    message.error((err as Error).message || '加载配置表单失败')
  } finally {
    formLoading.value = false
  }
}

async function saveConfigForm() {
  formSaving.value = true
  try {
    await saveUnifiedConfigForm(formValues.value)
    await loadUnifiedForm()
    message.success('一键配置表单已保存')
    await nextTick()
    scrollToFormActions()
  } catch (err) {
    message.error((err as Error).message || '保存失败')
  } finally {
    formSaving.value = false
  }
}

function onStartSkillCheck() {
  if (!canStartSkillCheck.value) {
    message.warning('请先在表单中填写并保存至少一项配置')
    return
  }
  emit('startBatch')
}

onMounted(() => {
  void loadUnifiedForm()
})
</script>

<template>
  <div class="config-form-panel">
    <NAlert type="info" :show-icon="false" style="margin-bottom: 16px">
      此表单汇总了配置清单中各 Skill 需要的配置项（已去重）。其中<strong>域账号 / 域密码</strong> 为 Jira、Gerrit、OpenGrok 共用。
      保存至少一项配置后，可点击「{{ SKILL_CONFIG_CHECK_BUTTON_LABEL }}」由 Agent 依次检查并完成各 Skill 配置。
    </NAlert>

    <NSpin :show="formLoading">
      <NForm label-placement="top" class="config-form">
        <div v-for="group in formGroups" :key="group.name" class="form-group">
          <div class="form-group-title">{{ group.name }}</div>
          <NFormItem v-for="field in group.fields" :key="field.key" :label="field.label">
            <NInput
              v-model:value="formValues[field.key]"
              :type="field.type === 'password' ? 'password' : 'text'"
              :show-password-on="field.type === 'password' ? 'click' : undefined"
              :placeholder="field.placeholder || ''"
            />
            <template v-if="field.description">
              <div class="form-field-hint ea-muted">{{ field.description }}</div>
            </template>
          </NFormItem>
        </div>
      </NForm>
    </NSpin>

    <div ref="formActionsRef" class="form-actions">
      <NSpace>
        <NButton type="primary" :loading="formSaving" @click="saveConfigForm">
          保存配置
        </NButton>
        <NButton
          type="primary"
          secondary
          :disabled="!canStartSkillCheck"
          @click="onStartSkillCheck"
        >
          {{ SKILL_CONFIG_CHECK_BUTTON_LABEL }}
        </NButton>
      </NSpace>
      <p v-if="!canStartSkillCheck" class="form-actions-hint ea-muted">
        填写并保存至少一项配置后，「{{ SKILL_CONFIG_CHECK_BUTTON_LABEL }}」将变为可点击。
      </p>
    </div>
  </div>
</template>

<style scoped lang="scss">
.config-form-panel {
  max-width: 720px;
}

.config-form {
  margin-bottom: 8px;
}

.form-group {
  margin-bottom: 12px;
}

.form-group-title {
  font-size: 13px;
  font-weight: 700;
  margin: 8px 0 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}

.form-field-hint {
  font-size: 11.5px;
  margin-top: 4px;
}

.form-actions {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.form-actions-hint {
  margin: 10px 0 0;
  font-size: 12px;
}
</style>
