<script setup lang="ts">
import { ref } from 'vue'
import { NCard, NTabs, NTabPane, NForm, NFormItem, NInput, NSelect, NButton, NSpace, useMessage } from 'naive-ui'
import { callTool } from '@/api/tahp/tools'

const message = useMessage()

const logForm = ref({ log_content: '', log_type: 'logcat', filters: '' })
const logLoading = ref(false)
const logResult = ref<unknown>(null)

const reviewForm = ref({ patch_content: '', check_level: 'P0' })
const reviewLoading = ref(false)
const reviewResult = ref<unknown>(null)

const migrationForm = ref({ action: 'list' as 'list' | 'search' | 'add', module: '', old_api: '' })
const migrationLoading = ref(false)
const migrationResult = ref<unknown>(null)

async function runLog() {
  if (!logForm.value.log_content.trim()) { message.warning('请粘贴日志内容'); return }
  logLoading.value = true
  try {
    const filters = logForm.value.filters.split(',').map(s => s.trim()).filter(Boolean)
    logResult.value = await callTool('tahp_analyze_log', {
      log_content: logForm.value.log_content,
      log_type: logForm.value.log_type,
      filters,
    })
  } catch (err) { message.error((err as Error).message) }
  finally { logLoading.value = false }
}

async function runReview() {
  if (!reviewForm.value.patch_content.trim()) { message.warning('请粘贴 patch 内容'); return }
  reviewLoading.value = true
  try {
    reviewResult.value = await callTool('tahp_code_review', { ...reviewForm.value })
  } catch (err) { message.error((err as Error).message) }
  finally { reviewLoading.value = false }
}

async function runMigration() {
  migrationLoading.value = true
  try {
    const args: Record<string, unknown> = { action: migrationForm.value.action }
    if (migrationForm.value.module) args.module = migrationForm.value.module
    if (migrationForm.value.old_api) args.old_api = migrationForm.value.old_api
    migrationResult.value = await callTool('tahp_api_migration', args)
  } catch (err) { message.error((err as Error).message) }
  finally { migrationLoading.value = false }
}
</script>

<template>
  <div class="tahp-tools">
    <div class="page-header">
      <h1>工具箱</h1>
      <p class="subtitle">单步调用 TAHP 底层工具 (日志分析 / 代码审查 / API 迁移)</p>
    </div>

    <NCard :bordered="false">
      <NTabs type="line">
        <NTabPane name="log" tab="Android 日志分析">
          <NForm :model="logForm" label-placement="top">
            <NFormItem label="日志类型">
              <NSelect
                v-model:value="logForm.log_type"
                :options="[{label:'logcat',value:'logcat'},{label:'ril',value:'ril'},{label:'atcmd',value:'atcmd'}]"
                style="width: 200px"
              />
            </NFormItem>
            <NFormItem label="日志内容">
              <NInput
                v-model:value="logForm.log_content"
                type="textarea"
                placeholder="粘贴 logcat / ril / atcmd 原文"
                :autosize="{ minRows: 6, maxRows: 16 }"
              />
            </NFormItem>
            <NFormItem label="过滤关键词 (逗号分隔)">
              <NInput v-model:value="logForm.filters" placeholder="如: RILJ, IMS" />
            </NFormItem>
            <NSpace>
              <NButton type="primary" :loading="logLoading" @click="runLog">分析</NButton>
            </NSpace>
          </NForm>
          <pre v-if="logResult" class="result-block">{{ JSON.stringify(logResult, null, 2) }}</pre>
        </NTabPane>

        <NTabPane name="review" tab="代码审查">
          <NForm :model="reviewForm" label-placement="top">
            <NFormItem label="审查级别">
              <NSelect
                v-model:value="reviewForm.check_level"
                :options="[{label:'P0',value:'P0'},{label:'P1',value:'P1'},{label:'P2',value:'P2'}]"
                style="width: 160px"
              />
            </NFormItem>
            <NFormItem label="Patch / Diff 内容">
              <NInput
                v-model:value="reviewForm.patch_content"
                type="textarea"
                placeholder="粘贴 git diff 输出"
                :autosize="{ minRows: 8, maxRows: 20 }"
              />
            </NFormItem>
            <NSpace>
              <NButton type="primary" :loading="reviewLoading" @click="runReview">审查</NButton>
            </NSpace>
          </NForm>
          <pre v-if="reviewResult" class="result-block">{{ JSON.stringify(reviewResult, null, 2) }}</pre>
        </NTabPane>

        <NTabPane name="migration" tab="API 迁移">
          <NForm :model="migrationForm" label-placement="top">
            <NFormItem label="操作">
              <NSelect
                v-model:value="migrationForm.action"
                :options="[{label:'list',value:'list'},{label:'search',value:'search'},{label:'add',value:'add'}]"
                style="width: 160px"
              />
            </NFormItem>
            <NFormItem v-if="migrationForm.action === 'list'" label="按模块过滤 (可选)">
              <NInput v-model:value="migrationForm.module" placeholder="telephony / kernel-driver / ..." />
            </NFormItem>
            <NFormItem v-if="migrationForm.action === 'search'" label="旧 API 名称">
              <NInput v-model:value="migrationForm.old_api" placeholder="如 PhoneStateListener" />
            </NFormItem>
            <NSpace>
              <NButton type="primary" :loading="migrationLoading" @click="runMigration">查询</NButton>
            </NSpace>
          </NForm>
          <pre v-if="migrationResult" class="result-block">{{ JSON.stringify(migrationResult, null, 2) }}</pre>
        </NTabPane>
      </NTabs>
    </NCard>
  </div>
</template>

<style scoped>
.tahp-tools { padding: 24px; max-width: 1280px; margin: 0 auto; }
.page-header { margin-bottom: 24px; }
.page-header h1 { margin: 0 0 6px; font-size: 24px; }
.subtitle { color: #888; margin: 0; }
.result-block {
  margin-top: 16px; padding: 12px;
  background: var(--n-color-modal); border-radius: 6px;
  max-height: 480px; overflow: auto; font-size: 12px; white-space: pre-wrap;
}
</style>
