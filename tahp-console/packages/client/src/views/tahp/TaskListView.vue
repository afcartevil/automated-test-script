<script setup lang="ts">
import { computed, onMounted, ref, h } from 'vue'
import { NCard, NDataTable, NButton, NSpace, NTag, NSpin, NModal, NInput, useMessage } from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import { useRouter } from 'vue-router'
import { useTahpTasksStore } from '@/stores/tahp/tasks'
import type { TaskInfo } from '@/api/tahp/tasks'

const router = useRouter()
const message = useMessage()
const tasksStore = useTahpTasksStore()

const showCorrect = ref(false)
const correctFeedback = ref('')
const correctTarget = ref<string | null>(null)

onMounted(() => tasksStore.refresh())

function openCorrect(taskId: string) {
  correctTarget.value = taskId
  correctFeedback.value = ''
  showCorrect.value = true
}

async function submitCorrect() {
  if (!correctTarget.value || !correctFeedback.value.trim()) return
  try {
    await tasksStore.correct(correctTarget.value, correctFeedback.value)
    message.success('纠偏指令已下发')
    showCorrect.value = false
  } catch (err) {
    message.error((err as Error).message)
  }
}

const columns = computed<DataTableColumns<TaskInfo>>(() => [
  { title: 'Task ID', key: 'task_id', render: r => (r.task_id || r.taskId || '-') as string, width: 220 },
  { title: '模块', key: 'module', width: 120 },
  { title: '域', key: 'domain', width: 160 },
  { title: '设计文档', key: 'document_path', ellipsis: { tooltip: true } },
  {
    title: '阶段',
    key: 'phase',
    width: 160,
    render: (r) => h(NTag, {
      size: 'small',
      type: r.status === 'completed' || r.phase === 'COMPLETED' ? 'success'
        : r.status === 'failed' || r.phase === 'FAILED' ? 'error'
          : 'info',
    }, () => r.phase || r.status || '-'),
  },
  {
    title: '进度',
    key: 'progress',
    width: 100,
    render: (r) => typeof r.progress === 'number' ? `${(r.progress * 100).toFixed(0)}%` : '-',
  },
  {
    title: '操作',
    key: 'actions',
    width: 220,
    render: (r) => {
      const tid = (r.task_id || r.taskId) as string | undefined
      if (!tid) return ''
      return h(NSpace, {}, () => [
        h(NButton, { size: 'small', onClick: () => router.push({ name: 'tahp.executor', query: { task_id: tid } }) }, () => '详情'),
        h(NButton, { size: 'small', type: 'warning', onClick: () => openCorrect(tid) }, () => '纠偏'),
      ])
    },
  },
])
</script>

<template>
  <div class="tahp-tasks">
    <div class="page-header">
      <h1>任务列表</h1>
      <p class="subtitle">所有 TAHP 执行任务的历史与状态</p>
    </div>

    <NCard :bordered="false">
      <template #header-extra>
        <NSpace>
          <NButton size="small" @click="tasksStore.refresh(true)">刷新</NButton>
          <NButton size="small" type="primary" @click="router.push({ name: 'tahp.executor' })">
            启动新任务
          </NButton>
        </NSpace>
      </template>
      <NSpin :show="tasksStore.loading">
        <NDataTable
          :columns="columns"
          :data="tasksStore.tasks"
          :pagination="{ pageSize: 20 }"
          :row-key="(r: TaskInfo) => (r.task_id || r.taskId || '') as string"
        />
      </NSpin>
    </NCard>

    <NModal
      v-model:show="showCorrect"
      preset="dialog"
      title="纠偏反馈"
      positive-text="发送"
      negative-text="取消"
      @positive-click="submitCorrect"
    >
      <div style="margin-bottom: 8px">Task: <code>{{ correctTarget }}</code></div>
      <NInput
        v-model:value="correctFeedback"
        type="textarea"
        placeholder="描述需要调整的内容"
        :autosize="{ minRows: 4, maxRows: 10 }"
      />
    </NModal>
  </div>
</template>

<style scoped>
.tahp-tasks { padding: 24px; max-width: 1400px; margin: 0 auto; }
.page-header { margin-bottom: 24px; }
.page-header h1 { margin: 0 0 6px; font-size: 24px; }
.subtitle { color: #888; margin: 0; }
</style>
