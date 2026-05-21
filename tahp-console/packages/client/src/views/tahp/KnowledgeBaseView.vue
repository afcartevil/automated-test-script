<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { NCard, NForm, NFormItem, NInput, NSelect, NInputNumber, NCheckbox, NButton, NSpace, NTag, NSpin, NEmpty, useMessage } from 'naive-ui'
import { queryKnowledge, type KnowledgeQueryRequest, type KnowledgeResult } from '@/api/tahp/knowledge'
import { useTahpModulesStore } from '@/stores/tahp/modules'

const message = useMessage()
const modulesStore = useTahpModulesStore()

const form = ref<KnowledgeQueryRequest>({ query: '', top_k: 5, cross_module: false })
const loading = ref(false)
const result = ref<KnowledgeResult | null>(null)

const moduleOptions = computed(() => [
  { label: '(全部模块)', value: '' },
  ...modulesStore.modules.map(m => ({ label: m.name, value: m.name })),
])

onMounted(() => modulesStore.refresh())

async function doQuery() {
  if (!form.value.query?.trim()) {
    message.warning('请输入查询内容')
    return
  }
  loading.value = true
  result.value = null
  try {
    const payload = { ...form.value }
    if (!payload.module) delete payload.module
    result.value = await queryKnowledge(payload)
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="tahp-kb">
    <div class="page-header">
      <h1>知识库</h1>
      <p class="subtitle">语义检索 TAHP 知识库 (SQLite + ONNX 嵌入向量)</p>
    </div>

    <NCard title="检索条件" :bordered="false">
      <NForm :model="form" inline label-placement="left">
        <NFormItem label="查询" style="flex: 1; min-width: 240px">
          <NInput
            v-model:value="form.query"
            placeholder="如：RILJ 错误码 / dts 加载流程 / suspend 异常 ..."
            @keyup.enter="doQuery"
          />
        </NFormItem>
        <NFormItem label="模块">
          <NSelect v-model:value="form.module" :options="moduleOptions" style="width: 180px" clearable />
        </NFormItem>
        <NFormItem label="Top K">
          <NInputNumber v-model:value="form.top_k" :min="1" :max="50" style="width: 100px" />
        </NFormItem>
        <NFormItem>
          <NCheckbox v-model:checked="form.cross_module">跨模块</NCheckbox>
        </NFormItem>
        <NFormItem>
          <NButton type="primary" :loading="loading" @click="doQuery">搜索</NButton>
        </NFormItem>
      </NForm>
    </NCard>

    <NCard
      title="检索结果"
      :bordered="false"
      style="margin-top: 16px"
    >
      <template v-if="result">
        <NSpace style="margin-bottom: 12px">
          <NTag size="small">{{ (result.results || []).length }} 条</NTag>
          <NTag v-if="result.confidence !== undefined" size="small" type="info">
            confidence: {{ result.confidence }}
          </NTag>
        </NSpace>
      </template>
      <NSpin :show="loading">
        <NEmpty v-if="!result" description="输入查询后回车" />
        <NEmpty v-else-if="!result.results?.length" description="无匹配结果" />
        <div v-else class="result-list">
          <div v-for="(r, i) in result.results" :key="i" class="result-card">
            <div class="result-header">
              <strong>{{ r.title || `结果 ${i + 1}` }}</strong>
              <NSpace>
                <NTag v-if="r.module" size="tiny" type="info">{{ r.module }}</NTag>
                <NTag v-if="r.score !== undefined" size="tiny">score: {{ Number(r.score).toFixed(3) }}</NTag>
              </NSpace>
            </div>
            <div v-if="r.source" class="result-source">{{ r.source }}</div>
            <pre v-if="r.content" class="result-content">{{ r.content }}</pre>
          </div>
        </div>
      </NSpin>
    </NCard>
  </div>
</template>

<style scoped>
.tahp-kb { padding: 24px; max-width: 1280px; margin: 0 auto; }
.page-header { margin-bottom: 24px; }
.page-header h1 { margin: 0 0 6px; font-size: 24px; }
.subtitle { color: #888; margin: 0; }
.result-list { display: flex; flex-direction: column; gap: 12px; }
.result-card { padding: 12px; background: var(--n-color-modal); border-radius: 6px; }
.result-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.result-source { color: #888; font-size: 12px; margin-bottom: 8px; font-family: monospace; }
.result-content { margin: 0; white-space: pre-wrap; font-size: 13px; }
</style>
