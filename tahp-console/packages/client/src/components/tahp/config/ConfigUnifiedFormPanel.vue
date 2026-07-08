<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import {
  NButton, NSpin, NInput, NSpace, NCollapse, NCollapseItem, useMessage,
} from 'naive-ui'
import EaCard from '@/components/layout/EaCard.vue'
import EaPill from '@/components/layout/EaPill.vue'
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

const formFields = ref<UnifiedConfigField[]>([])
const formValues = ref<Record<string, string>>({})
const savedValues = ref<Record<string, string>>({})
const formLoading = ref(false)
const formSaving = ref(false)
const saveFlash = ref(false)

/** 可选分组默认折叠；有已填值时自动展开 */
const expandedGroups = reactive<Record<string, boolean>>({})

const formGroups = computed(() => {
  const groups: Array<{ name: string; fields: UnifiedConfigField[]; optional: boolean }> = []
  for (const f of formFields.value) {
    let g = groups.find(x => x.name === f.group)
    if (!g) {
      g = {
        name: f.group,
        fields: [],
        optional: f.group.includes('可选'),
      }
      groups.push(g)
    }
    g.fields.push(f)
  }
  return groups
})

const filledCount = computed(() =>
  formFields.value.filter(f => (formValues.value[f.key] || '').trim()).length,
)

const canStartSkillCheck = computed(() =>
  hasAnySavedFormValue(savedValues.value, formFields.value),
)

function groupAnchor(name: string): string {
  return `ufg-${name.replace(/[^\w\u4e00-\u9fff]+/g, '-')}`
}

function isFieldSaved(key: string): boolean {
  return !!(savedValues.value[key] || '').trim()
}

function groupFilledCount(fields: UnifiedConfigField[]): number {
  return fields.filter(f => (formValues.value[f.key] || '').trim()).length
}

function isGroupExpanded(name: string, fields: UnifiedConfigField[], optional: boolean): boolean {
  if (name in expandedGroups) return expandedGroups[name]
  if (!optional) return true
  return groupFilledCount(fields) > 0
}

function setGroupExpanded(name: string, open: boolean) {
  expandedGroups[name] = open
}

function fieldSpanClass(field: UnifiedConfigField): string {
  const long = (field.description?.length ?? 0) > 48
    || (field.label?.length ?? 0) > 24
    || field.key.includes('path')
    || field.key.includes('workspace')
  return long ? 'form-field form-field--full' : 'form-field'
}

function scrollToGroup(name: string) {
  expandedGroups[name] = true
  const el = document.getElementById(groupAnchor(name))
  el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function loadUnifiedForm() {
  formLoading.value = true
  try {
    const data = await fetchUnifiedConfigForm()
    formFields.value = data.fields
    formValues.value = { ...data.values }
    savedValues.value = { ...(data.saved_values ?? {}) }
    for (const g of formGroups.value) {
      if (g.optional && groupFilledCount(g.fields) > 0) {
        expandedGroups[g.name] = true
      }
    }
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
    saveFlash.value = true
    setTimeout(() => { saveFlash.value = false }, 2000)
    message.success('一键配置表单已保存')
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
  <div class="unified-form">
    <header class="form-intro">
      <p class="form-intro__text">
        汇总各 Skill 需填写的凭据与路径（已去重）。<strong>域账号 / 域密码</strong> 供 Jira、Gerrit、OpenGrok 共用；其余分组可按需填写。
      </p>
      <div class="form-intro__meta">
        <EaPill variant="info">已填写 {{ filledCount }} / {{ formFields.length }} 项</EaPill>
        <EaPill v-if="canStartSkillCheck" variant="ok">可启动检查</EaPill>
        <EaPill v-else variant="muted">保存后启用检查</EaPill>
      </div>
    </header>

    <NSpin :show="formLoading">
      <div class="form-layout">
        <nav v-if="formGroups.length" class="form-nav" aria-label="配置分组导航">
          <div class="form-nav__title">分组</div>
          <button
            v-for="group in formGroups"
            :key="group.name"
            type="button"
            class="form-nav__item"
            @click="scrollToGroup(group.name)"
          >
            <span class="form-nav__label">{{ group.name.replace(/（可选[^）]*）/g, '').trim() }}</span>
            <span class="form-nav__count">
              {{ groupFilledCount(group.fields) }}/{{ group.fields.length }}
            </span>
          </button>
        </nav>

        <div class="form-sections">
          <template v-for="group in formGroups" :key="group.name">
            <!-- 必填 / 核心分组：始终展开卡片 -->
            <EaCard
              v-if="!group.optional"
              :id="groupAnchor(group.name)"
              class="form-section"
            >
              <div class="form-section__head">
                <h3 class="form-section__title">{{ group.name }}</h3>
                <EaPill variant="warn">建议填写</EaPill>
              </div>
              <div class="form-fields-grid">
                <div
                  v-for="field in group.fields"
                  :key="field.key"
                  :class="fieldSpanClass(field)"
                >
                  <label class="form-field__label" :for="`uf-${field.key}`">
                    {{ field.label }}
                    <EaPill v-if="isFieldSaved(field.key)" variant="ok" class="form-field__badge">已保存</EaPill>
                  </label>
                  <p v-if="field.description" class="form-field__desc">{{ field.description }}</p>
                  <NInput
                    :id="`uf-${field.key}`"
                    v-model:value="formValues[field.key]"
                    :type="field.type === 'password' ? 'password' : 'text'"
                    :show-password-on="field.type === 'password' ? 'click' : undefined"
                    :placeholder="field.placeholder || ''"
                  />
                </div>
              </div>
            </EaCard>

            <!-- 可选分组：折叠面板 -->
            <div v-else :id="groupAnchor(group.name)" class="form-section form-section--collapse">
              <NCollapse
                :expanded-names="isGroupExpanded(group.name, group.fields, group.optional) ? [group.name] : []"
                @update:expanded-names="(names: string[]) => setGroupExpanded(group.name, names.includes(group.name))"
              >
                <NCollapseItem :name="group.name">
                  <template #header>
                    <div class="collapse-header">
                      <span class="form-section__title">{{ group.name }}</span>
                      <EaPill variant="muted">可选</EaPill>
                      <span class="collapse-header__count ea-muted">
                        {{ groupFilledCount(group.fields) }}/{{ group.fields.length }}
                      </span>
                    </div>
                  </template>
                  <div class="form-fields-grid">
                    <div
                      v-for="field in group.fields"
                      :key="field.key"
                      :class="fieldSpanClass(field)"
                    >
                      <label class="form-field__label" :for="`uf-${field.key}`">
                        {{ field.label }}
                        <EaPill v-if="isFieldSaved(field.key)" variant="ok" class="form-field__badge">已保存</EaPill>
                      </label>
                      <p v-if="field.description" class="form-field__desc">{{ field.description }}</p>
                      <NInput
                        :id="`uf-${field.key}`"
                        v-model:value="formValues[field.key]"
                        :type="field.type === 'password' ? 'password' : 'text'"
                        :show-password-on="field.type === 'password' ? 'click' : undefined"
                        :placeholder="field.placeholder || ''"
                      />
                    </div>
                  </div>
                </NCollapseItem>
              </NCollapse>
            </div>
          </template>
        </div>
      </div>
    </NSpin>

    <footer class="form-footer" :class="{ 'form-footer--saved': saveFlash }">
      <div class="form-footer__hint ea-muted">
        <template v-if="canStartSkillCheck">
          配置已保存，可启动 Agent 自动检查各 Skill。
        </template>
        <template v-else>
          填写并保存至少一项后，「{{ SKILL_CONFIG_CHECK_BUTTON_LABEL }}」将变为可点击。
        </template>
      </div>
      <NSpace>
        <NButton type="primary" size="medium" :loading="formSaving" @click="saveConfigForm">
          保存配置
        </NButton>
        <NButton
          type="primary"
          secondary
          size="medium"
          :disabled="!canStartSkillCheck"
          @click="onStartSkillCheck"
        >
          {{ SKILL_CONFIG_CHECK_BUTTON_LABEL }}
        </NButton>
      </NSpace>
    </footer>
  </div>
</template>

<style scoped lang="scss">
.unified-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-bottom: 88px;
}

.form-intro {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px 20px;
  padding: 14px 16px;
  border-radius: 12px;
  background: var(--accent-soft);
  border: 1px solid color-mix(in srgb, var(--accent) 22%, transparent);
}

.form-intro__text {
  margin: 0;
  flex: 1;
  min-width: 240px;
  font-size: 13px;
  line-height: 1.55;
  color: var(--text);
}

.form-intro__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  flex-shrink: 0;
}

.form-layout {
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 20px;
  align-items: start;
}

.form-nav {
  position: sticky;
  top: 8px;
  padding: 12px;
  border-radius: 12px;
  background: var(--surface);
  border: 1px solid var(--line, var(--border));
}

.form-nav__title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--muted);
  margin-bottom: 8px;
}

.form-nav__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  margin-bottom: 2px;
  border: none;
  border-radius: 8px;
  background: none;
  cursor: pointer;
  font-family: inherit;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text);
  text-align: left;
  transition: background 0.15s, color 0.15s;

  &:hover {
    background: var(--accent-soft);
    color: var(--accent);
  }
}

.form-nav__label {
  flex: 1;
  min-width: 0;
  line-height: 1.35;
}

.form-nav__count {
  font-size: 11px;
  font-weight: 700;
  color: var(--muted);
  font-variant-numeric: tabular-nums;
}

.form-sections {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}

.form-section {
  scroll-margin-top: 12px;
}

.form-section__head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.form-section__title {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.35;
}

.form-section--collapse {
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--line, var(--border));
  background: var(--surface);

  :deep(.n-collapse-item__header) {
    padding: 14px 16px !important;
    font-weight: 600;
  }

  :deep(.n-collapse-item__content-inner) {
    padding: 0 16px 16px !important;
  }
}

.collapse-header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.collapse-header__count {
  margin-left: auto;
  font-size: 12px;
  font-weight: 600;
}

.form-fields-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px 20px;
}

.form-field--full {
  grid-column: 1 / -1;
}

.form-field__label {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 4px;
  font-size: 13px;
  font-weight: 600;
  color: var(--head, var(--text));
}

.form-field__badge {
  font-size: 10px;
}

.form-field__desc {
  margin: 0 0 6px;
  font-size: 11.5px;
  line-height: 1.45;
  color: var(--muted);
}

.form-footer {
  position: sticky;
  bottom: 0;
  z-index: 10;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px 20px;
  margin: 4px -4px 0;
  padding: 14px 18px;
  border-radius: 12px;
  background: color-mix(in srgb, var(--surface) 92%, transparent);
  backdrop-filter: blur(8px);
  border: 1px solid var(--line, var(--border));
  box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.06);
  transition: border-color 0.25s, box-shadow 0.25s;

  &--saved {
    border-color: var(--success, #18a058);
    box-shadow: 0 -4px 20px color-mix(in srgb, var(--success, #18a058) 18%, transparent);
  }
}

.form-footer__hint {
  font-size: 12.5px;
  line-height: 1.45;
  max-width: 480px;
}

@media (max-width: 960px) {
  .form-layout {
    grid-template-columns: 1fr;
  }

  .form-nav {
    position: static;
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 10px;
  }

  .form-nav__title {
    width: 100%;
    margin-bottom: 4px;
  }

  .form-nav__item {
    width: auto;
    flex: 1 1 auto;
    min-width: 140px;
    margin-bottom: 0;
  }
}

@media (max-width: 640px) {
  .form-fields-grid {
    grid-template-columns: 1fr;
  }

  .form-footer {
    flex-direction: column;
    align-items: stretch;

    :deep(.n-space) {
      width: 100%;
      justify-content: stretch !important;

      .n-button {
        flex: 1;
      }
    }
  }
}
</style>
