<script setup lang="ts">
import { ref, onMounted, watch, shallowRef, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NCard, NButton, NSpace, NTag, NSpin, useMessage, NAlert, NModal } from 'naive-ui'
import * as monaco from 'monaco-editor'
import { readConstraint, saveConstraint, validateConstraint, type ValidateResult } from '@/api/tahp/constraints'

const route = useRoute()
const router = useRouter()
const message = useMessage()

const moduleName = ref<string>(route.params.module as string)
const fileName = ref<string>(route.params.file as string)
const loading = ref(false)
const dirty = ref(false)
const validating = ref(false)
const validateResult = ref<ValidateResult | null>(null)
const showConfirm = ref(false)

const editorContainer = ref<HTMLDivElement | null>(null)
const editorInstance = shallowRef<monaco.editor.IStandaloneCodeEditor | null>(null)
let originalContent = ''

async function loadFile() {
  loading.value = true
  try {
    const data = await readConstraint(moduleName.value, fileName.value)
    originalContent = data.content
    if (editorInstance.value) {
      editorInstance.value.setValue(data.content)
    }
    dirty.value = false
    validateResult.value = null
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

function initEditor() {
  if (!editorContainer.value) return
  const ed = monaco.editor.create(editorContainer.value, {
    value: '',
    language: 'yaml',
    theme: 'vs-dark',
    automaticLayout: true,
    minimap: { enabled: false },
    fontSize: 13,
    scrollBeyondLastLine: false,
    tabSize: 2,
  })
  ed.onDidChangeModelContent(() => {
    dirty.value = ed.getValue() !== originalContent
    validateResult.value = null
  })
  editorInstance.value = ed
}

async function doValidate(): Promise<ValidateResult | null> {
  if (!editorInstance.value) return null
  validating.value = true
  try {
    const r = await validateConstraint(moduleName.value, fileName.value, editorInstance.value.getValue())
    validateResult.value = r
    return r
  } catch (err) {
    message.error((err as Error).message)
    return null
  } finally {
    validating.value = false
  }
}

async function clickSave() {
  if (!editorInstance.value) return
  const r = await doValidate()
  if (!r) return
  if (!r.ok) {
    message.warning('校验未通过，请先修复或选择 "跳过校验保存"')
    return
  }
  showConfirm.value = true
}

async function confirmSave(skipValidate: boolean) {
  if (!editorInstance.value) return
  try {
    await saveConstraint(moduleName.value, fileName.value, editorInstance.value.getValue(), skipValidate)
    message.success('已保存')
    originalContent = editorInstance.value.getValue()
    dirty.value = false
    showConfirm.value = false
  } catch (err) {
    message.error((err as Error).message)
  }
}

function revert() {
  if (editorInstance.value) {
    editorInstance.value.setValue(originalContent)
    dirty.value = false
    validateResult.value = null
  }
}

onMounted(async () => {
  initEditor()
  await loadFile()
})

onBeforeUnmount(() => {
  if (editorInstance.value) editorInstance.value.dispose()
})

watch(() => route.params, async (p) => {
  if (p.module && p.file) {
    moduleName.value = p.module as string
    fileName.value = p.file as string
    await loadFile()
  }
})
</script>

<template>
  <div class="tahp-editor">
    <div class="page-header">
      <NSpace align="center" justify="space-between">
        <div>
          <h1>约束编辑器</h1>
          <p class="subtitle">
            <code>constraints/{{ moduleName }}/{{ fileName }}</code>
            <NTag v-if="dirty" size="tiny" type="warning" style="margin-left: 8px">未保存</NTag>
          </p>
        </div>
        <NSpace>
          <NButton @click="router.push({ name: 'tahp.modules' })">返回矩阵</NButton>
          <NButton :disabled="!dirty" @click="revert">撤销修改</NButton>
          <NButton :loading="validating" @click="doValidate">校验</NButton>
          <NButton type="primary" :disabled="!dirty" @click="clickSave">保存</NButton>
        </NSpace>
      </NSpace>
    </div>

    <NAlert
      v-if="validateResult"
      :type="validateResult.ok ? 'success' : 'error'"
      :title="validateResult.ok ? '校验通过' : '校验失败'"
      style="margin-bottom: 12px"
    >
      <pre style="margin: 0; white-space: pre-wrap; font-size: 12px">{{ validateResult.stdout || validateResult.stderr || '(无输出)' }}</pre>
    </NAlert>

    <NCard :bordered="false" content-style="padding: 0">
      <NSpin :show="loading">
        <div ref="editorContainer" class="editor-host" />
      </NSpin>
    </NCard>

    <NModal
      v-model:show="showConfirm"
      preset="dialog"
      title="确认保存"
      :show-icon="false"
    >
      <div style="margin-bottom: 12px">
        将写入 <code>constraints/{{ moduleName }}/{{ fileName }}</code>，操作可在 git 中追溯。
      </div>
      <NSpace justify="end">
        <NButton @click="showConfirm = false">取消</NButton>
        <NButton type="warning" @click="confirmSave(true)">跳过校验保存</NButton>
        <NButton type="primary" @click="confirmSave(false)">校验并保存</NButton>
      </NSpace>
    </NModal>
  </div>
</template>

<style scoped>
.tahp-editor { padding: 24px; max-width: 1400px; margin: 0 auto; }
.page-header { margin-bottom: 16px; }
.page-header h1 { margin: 0 0 6px; font-size: 22px; }
.subtitle { color: #888; margin: 0; }
.subtitle code { background: transparent; }
.editor-host { height: calc(100vh - 240px); min-height: 480px; }
</style>
