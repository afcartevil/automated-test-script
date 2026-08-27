<script setup lang="ts">
/**
 * 模块级「路径参数解析」面板（复用适配流水线的解析服务）。
 *
 * 每个「工作区:模块」持有独立 scope；解析结果随该模块表单一起注入关联 Skill，
 * 同名字段以模块自身表单为准。字段增删仍只改服务端 PATH_PARAM_FIELDS。
 */
import { computed } from 'vue'
import { NButton, NInput, NSelect, useMessage } from 'naive-ui'
import { parsePipelinePathParams } from '@/api/tahp/adapt-pipeline'
import {
  applyPathParamResult,
  canParsePathParams,
  pathParamFailCount,
  pathParamFieldOptions,
  pathParamOkCount,
  pathParamRequestPayload,
  pathParamsFresh,
  resetPathParamScope,
  setPathParamFieldValue,
  type AdaptPathParamInputs,
  type AdaptPathParamScope,
} from '@/utils/adapt-path-params'

const props = defineProps<{
  scope: AdaptPathParamScope
  domainLabel: string
  /** 上一次解析成功的输入，用于「沿用上次输入」 */
  lastInputs: AdaptPathParamInputs | null
}>()

const emit = defineEmits<{
  parsed: []
  'reuse-last': []
}>()

const message = useMessage()

const okCount = computed(() => pathParamOkCount(props.scope))
const failCount = computed(() => pathParamFailCount(props.scope))
const canParse = computed(() => canParsePathParams(props.scope))
const isFresh = computed(() => pathParamsFresh(props.scope))
const hasInputs = computed(() =>
  Object.values(props.scope.inputs).some(v => String(v ?? '').trim()),
)

const summaryText = computed(() => {
  if (!props.scope.fields.length) return '未解析'
  if (!isFresh.value) return `输入已变化 · 需重新解析（原 ${okCount.value} 成功）`
  return failCount.value
    ? `${okCount.value} 项成功 · ${failCount.value} 项待手填`
    : `${okCount.value} 项全部解析成功`
})

const canReuseLast = computed(() => {
  const last = props.lastInputs
  if (!last) return false
  const cur = props.scope.inputs
  return last.project_code !== cur.project_code
    || last.OLD_VENDOR_ROOT !== cur.OLD_VENDOR_ROOT
    || last.NEW_VENDOR_ROOT !== cur.NEW_VENDOR_ROOT
    || last.NEW_SYSTEM_ROOT !== cur.NEW_SYSTEM_ROOT
})

function toggle() {
  props.scope.expanded = !props.scope.expanded
}

function setInput(key: keyof AdaptPathParamInputs, value: string) {
  props.scope.inputs[key] = value
}

async function handleParse() {
  if (!canParse.value || props.scope.parsing) return
  props.scope.parsing = true
  try {
    const data = await parsePipelinePathParams(pathParamRequestPayload(props.scope))
    applyPathParamResult(props.scope, data)
    const failed = data.fields.filter(f => !f.ok).length
    if (failed) {
      message.warning(`解析完成，${failed} 个字段失败，可手工填写后使用`)
    } else {
      message.success(`「${props.domainLabel}」路径参数解析完成`)
    }
    emit('parsed')
  } catch (err) {
    message.error((err as Error).message || '路径解析失败')
  } finally {
    props.scope.parsing = false
  }
}

function handleReset() {
  resetPathParamScope(props.scope)
}
</script>

<template>
  <div class="path-params-panel" :class="{ collapsed: !scope.expanded }">
    <div class="ppp-head" @click="toggle">
      <svg
        class="ppp-caret"
        :class="{ open: scope.expanded }"
        width="12"
        height="12"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="3"
      >
        <polyline points="9 18 15 12 9 6" />
      </svg>
      <span class="ppp-title">路径参数解析</span>
      <span
        class="ppp-pill"
        :class="{
          ok: scope.fields.length && isFresh && !failCount,
          warn: scope.fields.length && (!isFresh || failCount > 0),
        }"
      >{{ summaryText }}</span>
      <span class="ppp-hint">本模块独立，解析结果随表单注入关联 Skill</span>
    </div>

    <div v-if="scope.expanded" class="ppp-body">
      <div class="ppp-grid">
        <div class="ppp-field">
          <label>项目码 <span class="req">*</span></label>
          <NInput
            :value="scope.inputs.project_code"
            placeholder="例如 KM9"
            @update:value="v => setInput('project_code', v)"
          />
        </div>
        <div class="ppp-field">
          <label>OLD_VENDOR_ROOT <span class="req">*</span></label>
          <NInput
            :value="scope.inputs.OLD_VENDOR_ROOT"
            placeholder="例如 Z:\code-pull\cpull-xxx\vendor"
            @update:value="v => setInput('OLD_VENDOR_ROOT', v)"
          />
        </div>
        <div class="ppp-field">
          <label>NEW_VENDOR_ROOT <span class="req">*</span></label>
          <NInput
            :value="scope.inputs.NEW_VENDOR_ROOT"
            placeholder="例如 Z:\project\CM8\vendor"
            @update:value="v => setInput('NEW_VENDOR_ROOT', v)"
          />
        </div>
        <div class="ppp-field">
          <label>NEW_SYSTEM_ROOT</label>
          <NInput
            :value="scope.inputs.NEW_SYSTEM_ROOT"
            placeholder="可选，仅随参数传给 Skill，不参与解析"
            @update:value="v => setInput('NEW_SYSTEM_ROOT', v)"
          />
        </div>
      </div>

      <div class="ppp-actions">
        <NButton
          size="small"
          type="primary"
          :disabled="!canParse"
          :loading="scope.parsing"
          @click="handleParse"
        >
          {{ scope.fields.length ? '重新解析' : '解析' }}
        </NButton>
        <NButton
          v-if="canReuseLast"
          size="small"
          secondary
          @click="emit('reuse-last')"
        >
          沿用上次输入
        </NButton>
        <NButton
          v-if="hasInputs || scope.fields.length"
          size="small"
          quaternary
          @click="handleReset"
        >
          清空
        </NButton>
        <span v-if="!canParse" class="ppp-note">填写项目码与两个 vendor 根目录后可解析。</span>
        <span v-else-if="scope.fields.length && !isFresh" class="ppp-note is-err">
          项目码或 vendor 根已变化，请重新解析。
        </span>
        <span v-else-if="scope.parsedAt" class="ppp-note">
          解析于 {{ new Date(scope.parsedAt).toLocaleString() }}
        </span>
      </div>

      <div v-if="scope.fields.length" class="ppp-grid ppp-parsed">
        <div v-for="field in scope.fields" :key="field.key" class="ppp-field">
          <label>
            {{ field.label }}
            <span class="ppp-pill" :class="field.ok ? 'ok' : 'warn'">
              {{ field.ok ? '成功' : '失败' }}
            </span>
          </label>
          <NSelect
            v-if="field.kind === 'select'"
            :value="field.value || null"
            :options="pathParamFieldOptions(field)"
            filterable
            clearable
            placeholder="请选择项目目录"
            @update:value="v => setPathParamFieldValue(scope, field.key, v == null ? '' : String(v))"
          />
          <NInput
            v-else
            :value="field.value"
            :placeholder="field.error || field.label"
            @update:value="v => setPathParamFieldValue(scope, field.key, v)"
          />
          <p v-if="!field.ok && field.error" class="ppp-note is-err">{{ field.error }}</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.path-params-panel {
  border: 1px solid var(--line);
  border-radius: 10px;
  margin-bottom: 14px;
  background: color-mix(in srgb, var(--line) 8%, transparent);
}

.ppp-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  cursor: pointer;
  user-select: none;
}

.ppp-caret {
  color: var(--muted);
  transition: transform 0.15s ease;
  &.open { transform: rotate(90deg); }
}

.ppp-title {
  font-size: 13px;
  font-weight: 700;
}

.ppp-hint {
  margin-left: auto;
  font-size: 11.5px;
  color: var(--muted);
}

.ppp-pill {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--muted) 16%, transparent);
  color: var(--muted);
  &.ok {
    background: color-mix(in srgb, var(--ok, #3fb950) 18%, transparent);
    color: var(--ok, #2da44e);
  }
  &.warn {
    background: color-mix(in srgb, var(--warn, #e3b341) 20%, transparent);
    color: var(--warn, #9a6700);
  }
}

.ppp-body {
  padding: 0 12px 12px;
}

.ppp-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 12px;
  @media (max-width: 900px) { grid-template-columns: 1fr; }
}

.ppp-parsed {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--line);
}

.ppp-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  label {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    font-weight: 600;
    color: var(--muted);
  }
}

.ppp-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 12px;
}

.ppp-note {
  font-size: 12px;
  color: var(--muted);
  &.is-err { color: var(--err, #b03351); }
}

.req { color: var(--err, #b03351); }
</style>
