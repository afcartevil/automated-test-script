<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import {
  NButton, NSpin, NInput, NCollapse, NCollapseItem, useMessage,
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

const formFields = ref<UnifiedConfigField[]>([])
const formValues = ref<Record<string, string>>({})
const savedValues = ref<Record<string, string>>({})
const groupGuides = ref<Record<string, { label: string; url: string }>>({})
const formLoading = ref(false)
const formSaving = ref(false)
const saveHint = ref('')
const saveHintKind = ref<'success' | 'error' | ''>('')
const activeNav = ref('')

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

function groupShortName(name: string): string {
  return name.replace(/（可选）/g, '').trim()
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
  const isPath = field.key.includes('path')
    || field.key.includes('workspace')
    || field.key.includes('home')
    || field.key.includes('map_drive')
  return isPath ? 'form-field form-field--full' : 'form-field'
}

function scrollToGroup(name: string) {
  activeNav.value = name
  expandedGroups[name] = true
  const el = document.getElementById(groupAnchor(name))
  el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function groupGuide(name: string) {
  return groupGuides.value[name]
}

async function loadUnifiedForm() {
  formLoading.value = true
  try {
    const data = await fetchUnifiedConfigForm()
    formFields.value = data.fields
    formValues.value = { ...data.values }
    savedValues.value = { ...(data.saved_values ?? {}) }
    groupGuides.value = { ...(data.group_guides ?? {}) }
    if (!activeNav.value && data.fields.length) {
      activeNav.value = data.fields[0].group
    }
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
  saveHint.value = ''
  saveHintKind.value = ''
  try {
    await saveUnifiedConfigForm(formValues.value)
    await loadUnifiedForm()
    saveHint.value = '已保存（含 harness 配置同步）'
    saveHintKind.value = 'success'
    message.success('配置已保存')
    window.setTimeout(() => {
      if (saveHintKind.value === 'success') {
        saveHint.value = ''
        saveHintKind.value = ''
      }
    }, 4000)
  } catch (err) {
    const text = (err as Error).message || '保存失败'
    saveHint.value = text
    saveHintKind.value = 'error'
    message.error(text)
  } finally {
    formSaving.value = false
  }
}

function onStartSkillCheck() {
  if (!canStartSkillCheck.value) {
    message.warning('请先填写并保存至少一项配置')
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
    <header class="form-toolbar">
      <div class="form-toolbar__meta">
        <div class="form-toolbar__stat">
          <span class="form-toolbar__count">{{ filledCount }}</span>
          <span class="form-toolbar__sep">/</span>
          <span class="form-toolbar__total">{{ formFields.length }}</span>
          <span class="form-toolbar__label">已填写</span>
        </div>
        <span
          class="form-toolbar__status"
          :class="canStartSkillCheck ? 'form-toolbar__status--ok' : ''"
        >
          {{ canStartSkillCheck ? '可启动检查' : '保存后启用检查' }}
        </span>
        <span
          v-if="saveHint"
          class="form-toolbar__hint"
          :class="saveHintKind === 'error' ? 'form-toolbar__hint--error' : 'form-toolbar__hint--success'"
          role="status"
        >
          {{ saveHint }}
        </span>
      </div>
      <div class="form-toolbar__actions">
        <NButton type="primary" size="small" :loading="formSaving" @click="saveConfigForm">
          保存配置
        </NButton>
        <NButton
          type="default"
          size="small"
          :disabled="!canStartSkillCheck"
          @click="onStartSkillCheck"
        >
          {{ SKILL_CONFIG_CHECK_BUTTON_LABEL }}
        </NButton>
      </div>
    </header>

    <NSpin :show="formLoading">
      <div class="form-layout">
        <nav v-if="formGroups.length" class="form-nav" aria-label="配置分组">
          <button
            v-for="group in formGroups"
            :key="group.name"
            type="button"
            class="form-nav__item"
            :class="{ 'form-nav__item--active': activeNav === group.name }"
            @click="scrollToGroup(group.name)"
          >
            <span class="form-nav__label">{{ groupShortName(group.name) }}</span>
            <span class="form-nav__count">{{ groupFilledCount(group.fields) }}/{{ group.fields.length }}</span>
          </button>
        </nav>

        <div class="form-sections">
          <section
            v-for="group in formGroups"
            :id="groupAnchor(group.name)"
            :key="group.name"
            class="form-section"
            :class="{ 'form-section--optional': group.optional }"
          >
            <template v-if="!group.optional">
              <div class="form-section__bar">
                <h3 class="form-section__title">{{ groupShortName(group.name) }}</h3>
                <span class="form-section__tag form-section__tag--req">必填</span>
              </div>
              <div class="form-fields-grid">
                <div
                  v-for="field in group.fields"
                  :key="field.key"
                  :class="fieldSpanClass(field)"
                >
                  <label class="form-field__label" :for="`uf-${field.key}`">
                    <span>{{ field.label }}</span>
                    <a
                      v-if="field.doc_url"
                      class="form-field__doc"
                      :href="field.doc_url"
                      target="_blank"
                      rel="noopener noreferrer"
                      @click.stop
                    >{{ field.doc_label || '文档' }}</a>
                    <span
                      v-if="isFieldSaved(field.key)"
                      class="form-field__saved"
                      title="已保存"
                    />
                  </label>
                  <NInput
                    :id="`uf-${field.key}`"
                    v-model:value="formValues[field.key]"
                    size="small"
                    :type="field.type === 'password' ? 'password' : 'text'"
                    :show-password-on="field.type === 'password' ? 'click' : undefined"
                    :placeholder="field.placeholder || ''"
                  />
                </div>
              </div>
            </template>

            <NCollapse
              v-else
              :expanded-names="isGroupExpanded(group.name, group.fields, group.optional) ? [group.name] : []"
              @update:expanded-names="(names: string[]) => setGroupExpanded(group.name, names.includes(group.name))"
            >
              <NCollapseItem :name="group.name">
                <template #header>
                  <div class="form-section__bar form-section__bar--collapse">
                    <h3 class="form-section__title">{{ groupShortName(group.name) }}</h3>
                    <a
                      v-if="groupGuide(group.name)"
                      class="form-section__guide"
                      :href="groupGuide(group.name)!.url"
                      target="_blank"
                      rel="noopener noreferrer"
                      @click.stop
                    >
                      {{ groupGuide(group.name)!.label }}
                    </a>
                    <span class="form-section__tag">{{ groupFilledCount(group.fields) }}/{{ group.fields.length }}</span>
                  </div>
                </template>
                <div class="form-fields-grid">
                  <div
                    v-for="field in group.fields"
                    :key="field.key"
                    :class="fieldSpanClass(field)"
                  >
                    <label class="form-field__label" :for="`uf-${field.key}`">
                      <span>{{ field.label }}</span>
                      <a
                        v-if="field.doc_url"
                        class="form-field__doc"
                        :href="field.doc_url"
                        target="_blank"
                        rel="noopener noreferrer"
                        @click.stop
                      >{{ field.doc_label || '文档' }}</a>
                      <span
                        v-if="isFieldSaved(field.key)"
                        class="form-field__saved"
                        title="已保存"
                      />
                    </label>
                    <NInput
                      :id="`uf-${field.key}`"
                      v-model:value="formValues[field.key]"
                      size="small"
                      :type="field.type === 'password' ? 'password' : 'text'"
                      :show-password-on="field.type === 'password' ? 'click' : undefined"
                      :placeholder="field.placeholder || ''"
                    />
                  </div>
                </div>
              </NCollapseItem>
            </NCollapse>
          </section>
        </div>
      </div>
    </NSpin>
  </div>
</template>

<style scoped lang="scss">
.unified-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.form-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  padding: 10px 14px;
  border-radius: 10px;
  background: var(--surface);
  border: 1px solid var(--line, var(--border));
}

.form-toolbar__meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  min-width: 0;
}

.form-toolbar__actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.form-toolbar__hint {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;

  &--success {
    color: var(--success, #18a058);
  }

  &--error {
    color: var(--error, #d33b3b);
  }
}

.form-toolbar__stat {
  display: flex;
  align-items: baseline;
  gap: 2px;
  font-variant-numeric: tabular-nums;
}

.form-toolbar__count {
  font-size: 20px;
  font-weight: 700;
  color: var(--accent);
  line-height: 1;
}

.form-toolbar__sep,
.form-toolbar__total {
  font-size: 13px;
  font-weight: 600;
  color: var(--muted);
}

.form-toolbar__label {
  margin-left: 6px;
  font-size: 12px;
  color: var(--muted);
}

.form-toolbar__status {
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);

  &--ok {
    color: var(--success, #18a058);
  }
}

.form-layout {
  display: grid;
  grid-template-columns: 168px 1fr;
  gap: 16px;
  align-items: start;
}

.form-nav {
  position: sticky;
  top: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px;
  border-radius: 10px;
  background: var(--surface);
  border: 1px solid var(--line, var(--border));
}

.form-nav__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: none;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
  font-weight: 600;
  color: var(--muted);
  text-align: left;
  transition: background 0.15s, color 0.15s;

  &:hover {
    background: var(--accent-soft);
    color: var(--text);
  }

  &--active {
    background: var(--accent-soft);
    color: var(--accent);
  }
}

.form-nav__label {
  flex: 1;
  min-width: 0;
  line-height: 1.3;
}

.form-nav__count {
  font-size: 10px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  opacity: 0.85;
}

.form-sections {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
}

.form-section {
  scroll-margin-top: 12px;
  padding: 14px 16px;
  border-radius: 10px;
  background: var(--surface);
  border: 1px solid var(--line, var(--border));

  &--optional {
    padding: 0;
    border: none;
    background: transparent;

    :deep(.n-collapse) {
      border-radius: 10px;
      overflow: hidden;
      border: 1px solid var(--line, var(--border));
      background: var(--surface);
    }

    :deep(.n-collapse-item__header) {
      padding: 12px 16px !important;
    }

    :deep(.n-collapse-item__content-inner) {
      padding: 0 16px 14px !important;
    }
  }
}

.form-section__bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  min-width: 0;

  &--collapse {
    margin-bottom: 0;
    flex: 1;
  }
}

.form-section__title {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  line-height: 1.3;
  color: var(--head, var(--text));
}

.form-section__tag {
  margin-left: auto;
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.02em;
  padding: 2px 7px;
  border-radius: 999px;
  color: var(--muted);
  background: color-mix(in srgb, var(--muted) 12%, transparent);

  &--req {
    color: #c45656;
    background: color-mix(in srgb, #c45656 12%, transparent);
  }
}

.form-section__guide {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  text-decoration: none;
  white-space: nowrap;

  &:hover {
    text-decoration: underline;
  }
}

.form-fields-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 16px;
}

.form-field--full {
  grid-column: 1 / -1;
}

.form-field__label {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--head, var(--text));
}

.form-field__doc {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  text-decoration: none;
  white-space: nowrap;

  &:hover {
    text-decoration: underline;
  }
}

.form-field__saved {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--success, #18a058);
  flex-shrink: 0;
}

@media (max-width: 960px) {
  .form-layout {
    grid-template-columns: 1fr;
  }

  .form-nav {
    position: static;
    flex-direction: row;
    flex-wrap: wrap;
  }

  .form-nav__item {
    flex: 1 1 auto;
    min-width: 120px;
  }
}

@media (max-width: 640px) {
  .form-fields-grid {
    grid-template-columns: 1fr;
  }

  .form-toolbar__actions {
    width: 100%;
    justify-content: flex-end;
  }
}
</style>
