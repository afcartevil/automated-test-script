<script setup lang="ts">
import { ref, onMounted, computed, h } from 'vue'
import { NCard, NForm, NFormItem, NSelect, NInput, NButton, NSpace, NTag, NSpin, NDataTable, useMessage } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { runGateCheck, type GateCheckRequest, type GateCheckResult } from '@/api/tahp/gate'
import { useTahpModulesStore } from '@/stores/tahp/modules'

const message = useMessage()
const modulesStore = useTahpModulesStore()

const form = ref<GateCheckRequest>({ module: 'telephony', level: 'all' })
const loading = ref(false)
const result = ref<GateCheckResult | null>(null)

const LEVEL_OPTIONS = [
  { label: '全部 (all)', value: 'all' },
  { label: 'P0 (阻塞级)', value: 'P0' },
  { label: 'P1 (警告级)', value: 'P1' },
  { label: 'P2 (记录级)', value: 'P2' },
]

const moduleOptions = computed(() => modulesStore.modules.map(m => ({ label: m.name, value: m.name })))

onMounted(() => modulesStore.refresh())

async function runCheck() {
  if (!form.value.module && !form.value.task_id) {
    message.warning('请填写模块或 task_id')
    return
  }
  loading.value = true
  result.value = null
  try {
    result.value = await runGateCheck(form.value)
  } catch (err) {
    message.error((err as Error).message)
  } finally {
    loading.value = false
  }
}

const violationColumns: DataTableColumns<any> = [
  {
    title: '级别',
    key: 'level',
    width: 80,
    render: (r) => h(NTag, {
      size: 'small',
      type: r.level === 'P0' ? 'error' : r.level === 'P1' ? 'warning' : 'default',
    }, () => r.level),
  },
  { title: '规则', key: 'rule', width: 180 },
  { title: '文件', key: 'file', width: 240, ellipsis: { tooltip: true } },
  { title: '行', key: 'line', width: 60 },
  { title: '消息', key: 'message', ellipsis: { tooltip: true } },
]
</script>

<template>
  <div class="tahp-gate">
    <div class="page-header">
      <h1>质量门禁</h1>
      <p class="subtitle">手动触发 P0/P1/P2 门禁检查，查看违规清单</p>
    </div>

    <NCard title="检查参数" :bordered="false">
      <NForm :model="form" inline label-placement="left">
        <NFormItem label="模块">
          <NSelect v-model:value="form.module" :options="moduleOptions" style="width: 200px" clearable />
        </NFormItem>
        <NFormItem label="或 Task ID">
          <NInput v-model:value="form.task_id" placeholder="task-id (与模块二选一)" style="width: 280px" clearable />
        </NFormItem>
        <NFormItem label="级别">
          <NSelect v-model:value="form.level" :options="LEVEL_OPTIONS" style="width: 160px" />
        </NFormItem>
        <NFormItem>
          <NButton type="primary" :loading="loading" @click="runCheck">运行门禁</NButton>
        </NFormItem>
      </NForm>
    </NCard>

    <NCard
      v-if="result"
      title="检查结果"
      :bordered="false"
      style="margin-top: 16px"
    >
      <NSpace align="center" style="margin-bottom: 12px">
        <NTag :type="result.result === 'PASS' ? 'success' : 'error'" size="medium">
          {{ result.result || (result.violations?.length ? 'FAIL' : 'PASS') }}
        </NTag>
        <span v-if="result.score !== undefined">得分: {{ result.score }}</span>
        <span>违规数: {{ result.violations?.length || 0 }}</span>
      </NSpace>
      <NDataTable
        :columns="violationColumns"
        :data="result.violations || []"
        :pagination="{ pageSize: 20 }"
      />
    </NCard>

    <NSpin v-if="loading" style="margin-top: 16px" />
  </div>
</template>

<style scoped>
.tahp-gate { padding: 24px; max-width: 1280px; margin: 0 auto; }
.page-header { margin-bottom: 24px; }
.page-header h1 { margin: 0 0 6px; font-size: 24px; }
.subtitle { color: #888; margin: 0; }
</style>
