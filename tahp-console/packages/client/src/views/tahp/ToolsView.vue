<script setup lang="ts">
import { ref } from 'vue'
import {
  NCard, NTabs, NTabPane, NForm, NFormItem, NInput, NSelect,
  NButton, NSpace, NAlert, useMessage,
} from 'naive-ui'
import { callTool } from '@/api/tahp/tools'

const message = useMessage()

function useTool() {
  const loading = ref(false)
  const result = ref<unknown>(null)
  const error = ref<string | null>(null)
  return { loading, result, error }
}

async function run(
  tool: ReturnType<typeof useTool>,
  name: string,
  args: Record<string, unknown>,
) {
  tool.loading.value = true
  tool.result.value = null
  tool.error.value = null
  try {
    tool.result.value = await callTool(name, args)
  } catch (err) {
    tool.error.value = (err as Error).message
    message.error((err as Error).message)
  } finally {
    tool.loading.value = false
  }
}

function fmt(v: unknown): string {
  if (typeof v === 'string') return v
  return JSON.stringify(v, null, 2)
}

// 1. Android 日志分析
const log = useTool()
const logForm = ref({ log_content: '', log_type: 'logcat', filters: '' })
async function runLog() {
  if (!logForm.value.log_content.trim()) { message.warning('请粘贴日志内容'); return }
  const filters = logForm.value.filters.split(',').map((s: string) => s.trim()).filter(Boolean)
  await run(log, 'tahp_analyze_log', {
    log_content: logForm.value.log_content,
    log_type: logForm.value.log_type,
    filters,
  })
}

// 2. Bug 分析
const bug = useTool()
const bugForm = ref({ module: 'telephony', description: '', log_snippet: '', jira_id: '' })
const BUG_MODULE_OPTIONS = [
  { label: 'telephony', value: 'telephony' },
  { label: 'kernel-driver', value: 'kernel-driver' },
  { label: 'power-mgmt', value: 'power-mgmt' },
  { label: 'shared', value: 'shared' },
]
async function runBug() {
  if (!bugForm.value.description.trim()) { message.warning('请填写 Bug 描述'); return }
  await run(bug, 'tahp_analyze_bug', {
    module: bugForm.value.module,
    description: bugForm.value.description,
    log_snippet: bugForm.value.log_snippet || undefined,
    jira_id: bugForm.value.jira_id || undefined,
  })
}

// 3. AOSP Diff 分析
const diff = useTool()
const diffForm = ref({ source_version: '', target_version: '', diff_content: '', module_filter: '' })
async function runDiff() {
  if (!diffForm.value.diff_content.trim()) { message.warning('请粘贴 git diff 内容'); return }
  await run(diff, 'tahp_aosp_diff', {
    source_version: diffForm.value.source_version,
    target_version: diffForm.value.target_version,
    diff_content: diffForm.value.diff_content,
    module_filter: diffForm.value.module_filter || undefined,
  })
}

// 4. 代码审查
const review = useTool()
const reviewForm = ref({ patch_content: '', check_level: 'P0' })
async function runReview() {
  if (!reviewForm.value.patch_content.trim()) { message.warning('请粘贴 patch 内容'); return }
  await run(review, 'tahp_code_review', { ...reviewForm.value })
}

// 5. Patch 生成
const patch = useTool()
const patchForm = ref({ migration_rules: '', target_files: '', source_code_paths: '' })
async function runPatch() {
  if (!patchForm.value.migration_rules.trim()) { message.warning('请填写迁移规则描述'); return }
  await run(patch, 'tahp_patch_generator', {
    migration_rules: patchForm.value.migration_rules,
    target_files: patchForm.value.target_files
      ? patchForm.value.target_files.split('\n').map((s: string) => s.trim()).filter(Boolean)
      : [],
    source_code_paths: patchForm.value.source_code_paths
      ? patchForm.value.source_code_paths.split('\n').map((s: string) => s.trim()).filter(Boolean)
      : [],
  })
}

// 6. 编译验证
const build = useTool()
const buildForm = ref({ build_command: 'make -j8', targets: '', patch_files: '' })
async function runBuild() {
  await run(build, 'tahp_build_verify', {
    build_command: buildForm.value.build_command,
    targets: buildForm.value.targets
      ? buildForm.value.targets.split('\n').map((s: string) => s.trim()).filter(Boolean)
      : [],
    patch_files: buildForm.value.patch_files
      ? buildForm.value.patch_files.split('\n').map((s: string) => s.trim()).filter(Boolean)
      : [],
  })
}

// 7. 回归测试
const regression = useTool()
const regressionForm = ref({ test_targets: '', test_type: 'smoke', device_serial: '' })
async function runRegression() {
  if (!regressionForm.value.test_targets.trim()) { message.warning('请填写测试目标'); return }
  await run(regression, 'tahp_regression_test', {
    test_targets: regressionForm.value.test_targets.split('\n').map((s: string) => s.trim()).filter(Boolean),
    test_type: regressionForm.value.test_type,
    device_serial: regressionForm.value.device_serial || undefined,
  })
}

// 8. API 迁移数据库
const migration = useTool()
const migrationForm = ref({ action: 'list' as 'list' | 'search' | 'add', module: '', old_api: '' })
async function runMigration() {
  const args: Record<string, unknown> = { action: migrationForm.value.action }
  if (migrationForm.value.module) args.module = migrationForm.value.module
  if (migrationForm.value.old_api) args.old_api = migrationForm.value.old_api
  await run(migration, 'tahp_api_migration', args)
}
</script>

<template>
  <div class="tahp-tools">
    <div class="page-header">
      <h1>工具箱</h1>
      <p class="subtitle">单步调用 TAHP 底层工具，无需启动完整 Pipeline</p>
    </div>

    <NCard :bordered="false">
      <NTabs type="card" animated>

        <!-- 1. 日志分析 -->
        <NTabPane name="log" tab="日志分析">
          <NAlert type="info" style="margin-bottom:14px" :bordered="false">
            解析 logcat / ril / atcmd / bugreport，提取关键事件和异常信息。
          </NAlert>
          <NForm :model="logForm" label-placement="top">
            <NFormItem label="日志类型">
              <NSelect v-model:value="logForm.log_type" style="width:200px"
                :options="[{label:'logcat',value:'logcat'},{label:'ril',value:'ril'},{label:'atcmd',value:'atcmd'},{label:'bugreport',value:'bugreport'}]" />
            </NFormItem>
            <NFormItem label="过滤关键词（逗号分隔，可选）">
              <NInput v-model:value="logForm.filters" placeholder="如: RILJ, IMS" />
            </NFormItem>
            <NFormItem label="日志内容" required>
              <NInput v-model:value="logForm.log_content" type="textarea"
                placeholder="粘贴原始日志..." :autosize="{ minRows: 8, maxRows: 16 }" />
            </NFormItem>
            <NButton type="primary" :loading="log.loading.value" @click="runLog">分析</NButton>
          </NForm>
          <pre v-if="log.result.value" class="result-block">{{ fmt(log.result.value) }}</pre>
        </NTabPane>

        <!-- 2. Bug 分析 -->
        <NTabPane name="bug" tab="Bug 分析">
          <NAlert type="info" style="margin-bottom:14px" :bordered="false">
            对指定模块执行 Bug 根因分析，输出根因定位与修复建议。
          </NAlert>
          <NForm :model="bugForm" label-placement="top">
            <NFormItem label="模块" required>
              <NSelect v-model:value="bugForm.module" :options="BUG_MODULE_OPTIONS" style="width:200px" />
            </NFormItem>
            <NFormItem label="Jira ID（可选）">
              <NInput v-model:value="bugForm.jira_id" placeholder="如 PRJT-12345" style="width:200px" />
            </NFormItem>
            <NFormItem label="Bug 描述" required>
              <NInput v-model:value="bugForm.description" type="textarea"
                placeholder="描述现象、复现步骤、影响版本..." :autosize="{ minRows: 5, maxRows: 12 }" />
            </NFormItem>
            <NFormItem label="日志片段（可选）">
              <NInput v-model:value="bugForm.log_snippet" type="textarea"
                placeholder="可粘贴关键日志片段辅助分析" :autosize="{ minRows: 3, maxRows: 8 }" />
            </NFormItem>
            <NButton type="primary" :loading="bug.loading.value" @click="runBug">分析 Bug</NButton>
          </NForm>
          <pre v-if="bug.result.value" class="result-block">{{ fmt(bug.result.value) }}</pre>
        </NTabPane>

        <!-- 3. AOSP Diff 分析 -->
        <NTabPane name="diff" tab="AOSP Diff">
          <NAlert type="info" style="margin-bottom:14px" :bordered="false">
            对比两个 Android 版本的 diff，提取 API / 接口 / 行为变更清单。
          </NAlert>
          <NForm :model="diffForm" label-placement="top">
            <NSpace>
              <NFormItem label="源版本">
                <NInput v-model:value="diffForm.source_version" placeholder="android-13.0.0_r1" style="width:220px" />
              </NFormItem>
              <NFormItem label="目标版本">
                <NInput v-model:value="diffForm.target_version" placeholder="android-14.0.0_r1" style="width:220px" />
              </NFormItem>
              <NFormItem label="模块过滤（可选）">
                <NInput v-model:value="diffForm.module_filter" placeholder="telephony" style="width:160px" />
              </NFormItem>
            </NSpace>
            <NFormItem label="git diff 内容" required>
              <NInput v-model:value="diffForm.diff_content" type="textarea"
                placeholder="粘贴 git diff 或 repo diff 输出..." :autosize="{ minRows: 10, maxRows: 20 }" />
            </NFormItem>
            <NButton type="primary" :loading="diff.loading.value" @click="runDiff">分析 Diff</NButton>
          </NForm>
          <pre v-if="diff.result.value" class="result-block">{{ fmt(diff.result.value) }}</pre>
        </NTabPane>

        <!-- 4. 代码审查 -->
        <NTabPane name="review" tab="代码审查">
          <NAlert type="info" style="margin-bottom:14px" :bordered="false">
            对 patch 文件进行静态代码审查，按 P0/P1/P2 级别输出违规项。
          </NAlert>
          <NForm :model="reviewForm" label-placement="top">
            <NFormItem label="审查级别">
              <NSelect v-model:value="reviewForm.check_level" style="width:180px"
                :options="[{label:'全部',value:'all'},{label:'P0（阻塞）',value:'P0'},{label:'P1（警告）',value:'P1'},{label:'P2（记录）',value:'P2'}]" />
            </NFormItem>
            <NFormItem label="Patch / Diff 内容" required>
              <NInput v-model:value="reviewForm.patch_content" type="textarea"
                placeholder="粘贴 git diff 输出..." :autosize="{ minRows: 10, maxRows: 20 }" />
            </NFormItem>
            <NButton type="primary" :loading="review.loading.value" @click="runReview">审查</NButton>
          </NForm>
          <pre v-if="review.result.value" class="result-block">{{ fmt(review.result.value) }}</pre>
        </NTabPane>

        <!-- 5. Patch 生成 -->
        <NTabPane name="patch" tab="Patch 生成">
          <NAlert type="warning" style="margin-bottom:14px" :bordered="false">
            根据迁移规则批量生成适配 patch，需要在 Android 源码环境中执行。
          </NAlert>
          <NForm :model="patchForm" label-placement="top">
            <NFormItem label="迁移规则描述" required>
              <NInput v-model:value="patchForm.migration_rules" type="textarea"
                placeholder="描述适配规则，如：将 PhoneStateListener 替换为 TelephonyCallback..."
                :autosize="{ minRows: 4, maxRows: 10 }" />
            </NFormItem>
            <NFormItem label="目标文件路径（每行一个）">
              <NInput v-model:value="patchForm.target_files" type="textarea"
                placeholder="frameworks/opt/telephony/src/..." :autosize="{ minRows: 3, maxRows: 8 }" />
            </NFormItem>
            <NFormItem label="源码搜索路径（每行一个）">
              <NInput v-model:value="patchForm.source_code_paths" type="textarea"
                placeholder="frameworks/ vendor/..." :autosize="{ minRows: 3, maxRows: 8 }" />
            </NFormItem>
            <NButton type="primary" :loading="patch.loading.value" @click="runPatch">生成 Patch</NButton>
          </NForm>
          <pre v-if="patch.result.value" class="result-block">{{ fmt(patch.result.value) }}</pre>
        </NTabPane>

        <!-- 6. 编译验证 -->
        <NTabPane name="build" tab="编译验证">
          <NAlert type="warning" style="margin-bottom:14px" :bordered="false">
            触发 Android 编译验证，需在已配置好编译环境的服务器上执行。
          </NAlert>
          <NForm :model="buildForm" label-placement="top">
            <NFormItem label="编译命令">
              <NInput v-model:value="buildForm.build_command" placeholder="make -j8" />
            </NFormItem>
            <NFormItem label="编译目标（每行一个）">
              <NInput v-model:value="buildForm.targets" type="textarea"
                placeholder="telephony framework..." :autosize="{ minRows: 3, maxRows: 6 }" />
            </NFormItem>
            <NFormItem label="相关 Patch 文件（每行一个，可选）">
              <NInput v-model:value="buildForm.patch_files" type="textarea"
                placeholder="/tmp/fix.patch" :autosize="{ minRows: 3, maxRows: 6 }" />
            </NFormItem>
            <NButton type="primary" :loading="build.loading.value" @click="runBuild">触发编译</NButton>
          </NForm>
          <pre v-if="build.result.value" class="result-block">{{ fmt(build.result.value) }}</pre>
        </NTabPane>

        <!-- 7. 回归测试 -->
        <NTabPane name="regression" tab="回归测试">
          <NAlert type="warning" style="margin-bottom:14px" :bordered="false">
            运行冒烟测试或功能回归，需连接测试设备。
          </NAlert>
          <NForm :model="regressionForm" label-placement="top">
            <NFormItem label="测试类型">
              <NSelect v-model:value="regressionForm.test_type" style="width:220px"
                :options="[{label:'冒烟测试 (smoke)',value:'smoke'},{label:'功能回归 (regression)',value:'regression'},{label:'全量 (full)',value:'full'}]" />
            </NFormItem>
            <NFormItem label="设备序列号（可选）">
              <NInput v-model:value="regressionForm.device_serial" placeholder="adb devices 中的序列号" style="width:260px" />
            </NFormItem>
            <NFormItem label="测试目标（每行一个）" required>
              <NInput v-model:value="regressionForm.test_targets" type="textarea"
                placeholder="TelephonyTests ImsTests..." :autosize="{ minRows: 4, maxRows: 8 }" />
            </NFormItem>
            <NButton type="primary" :loading="regression.loading.value" @click="runRegression">运行测试</NButton>
          </NForm>
          <pre v-if="regression.result.value" class="result-block">{{ fmt(regression.result.value) }}</pre>
        </NTabPane>

        <!-- 8. API 迁移数据库 -->
        <NTabPane name="migration" tab="API 迁移 DB">
          <NAlert type="info" style="margin-bottom:14px" :bordered="false">
            查询 / 新增 API 迁移规则数据库（deprecated API → new API 映射）。
          </NAlert>
          <NForm :model="migrationForm" label-placement="top">
            <NFormItem label="操作">
              <NSelect v-model:value="migrationForm.action" style="width:180px"
                :options="[{label:'列出所有规则',value:'list'},{label:'搜索旧 API',value:'search'},{label:'新增规则',value:'add'}]" />
            </NFormItem>
            <NFormItem v-if="['list','add'].includes(migrationForm.action)" label="模块">
              <NInput v-model:value="migrationForm.module" placeholder="telephony / kernel-driver / ..." style="width:260px" />
            </NFormItem>
            <NFormItem v-if="['search','add'].includes(migrationForm.action)" label="旧 API 名称">
              <NInput v-model:value="migrationForm.old_api" placeholder="如 PhoneStateListener" />
            </NFormItem>
            <NButton type="primary" :loading="migration.loading.value" @click="runMigration">执行</NButton>
          </NForm>
          <pre v-if="migration.result.value" class="result-block">{{ fmt(migration.result.value) }}</pre>
        </NTabPane>

      </NTabs>
    </NCard>
  </div>
</template>

<style scoped>
.tahp-tools { padding: 24px; max-width: 1280px; margin: 0 auto; }
.page-header { margin-bottom: 20px; }
.page-header h1 { margin: 0 0 4px; font-size: 22px; font-weight: 600; }
.subtitle { color: #888; margin: 0; font-size: 13px; }
.result-block {
  margin-top: 16px; padding: 14px;
  background: var(--n-color-modal, rgba(0,0,0,.04));
  border-radius: 6px; max-height: 520px; overflow: auto;
  font-size: 12px; white-space: pre-wrap; word-break: break-all;
  line-height: 1.6; font-family: monospace;
}
</style>
