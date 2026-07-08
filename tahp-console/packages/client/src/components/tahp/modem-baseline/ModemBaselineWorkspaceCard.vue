<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { NButton, NInput, NModal, NSelect } from 'naive-ui'
import type { RepoProfile, ScannedRepoCandidate, UserWorkspaceProfile } from '@/api/tahp/modem-baseline'

const props = defineProps<{
  workspaceProfile: UserWorkspaceProfile | null
  repos: RepoProfile[]
  selectedRepoId?: string
  scanResults?: ScannedRepoCandidate[]
  scanWarnings?: string[]
  savingWorkspace?: boolean
  savingRepo?: boolean
  scanningRepos?: boolean
  removingRepo?: boolean
}>()

const emit = defineEmits<{
  'save-workspace': [value: { mappedPrefix: string; remotePrefix: string; roots: string[] }]
  'save-repo': [value: { label: string; localPath: string; platform: string }]
  'scan-repos': [root: string]
  'choose-repo': [repoId: string]
  'clear-repo': []
  'remove-repo': [repoId: string]
}>()

const workspaceForm = reactive({
  owner: '',
  rootsText: '',
  selectedRoot: '',
})

const repoForm = reactive({
  localPath: '',
  platform: '',
})
const scanImportDialogOpen = ref(false)
const pendingScanImport = ref<{ localPath: string; platform: string } | null>(null)
const scanImportSourceName = ref('')
const scanImportForm = reactive({
  localPath: '',
  platform: '',
})

const scanRoot = computed(() => {
  const roots = workspaceForm.rootsText.split(/\r?\n/).map(item => item.trim()).filter(Boolean)
  if (workspaceForm.selectedRoot) return workspaceForm.selectedRoot
  return roots[0] ?? ''
})

const rootOptions = computed(() => {
  const roots = workspaceForm.rootsText.split(/\r?\n/).map(item => item.trim()).filter(Boolean)
  return roots.map(item => ({ label: item, value: item }))
})

const workspaceRoots = computed(() => rootsFromForm())

const inferredMappedPrefix = computed(() => {
  const firstRoot = workspaceRoots.value[0] ?? ''
  const matched = firstRoot.match(/^[A-Za-z]:/)
  return matched ? matched[0].toUpperCase() : ''
})

const canSaveWorkspace = computed(() => (
  Boolean(workspaceForm.owner.trim())
  && workspaceRoots.value.length > 0
  && Boolean(inferredMappedPrefix.value)
))

const inferredRemotePrefix = computed(() => {
  const owner = workspaceForm.owner.trim()
  return owner ? `/work/${owner}/code` : ''
})

function normalizeLocalPath(localPath: string) {
  return localPath.trim().replace(/\//g, '\\').replace(/\\+/g, '\\').toUpperCase()
}

const repoOptions = computed(() => props.repos.map(item => ({
  label: `${item.label} · ${item.localPath}`,
  value: item.repoId,
})))

const importedRepoPathSet = computed(() => new Set(
  props.repos.map(item => normalizeLocalPath(item.localPath)),
))

const sortedScanResults = computed(() => {
  const items = [...(props.scanResults ?? [])]
  return items.sort((left, right) => {
    const leftImported = importedRepoPathSet.value.has(normalizeLocalPath(left.localPath))
    const rightImported = importedRepoPathSet.value.has(normalizeLocalPath(right.localPath))
    if (leftImported === rightImported) return 0
    return leftImported ? 1 : -1
  })
})

watch(
  () => props.workspaceProfile,
  (value) => {
    workspaceForm.owner = localStorage.getItem('tahp_modem_patch_owner') || value?.owner || ''
    workspaceForm.rootsText = (value?.roots ?? []).join('\n')
    const firstRoot = (value?.roots ?? [])[0] || ''
    workspaceForm.selectedRoot = firstRoot
  },
  { immediate: true },
)

function persistOwner() {
  const owner = workspaceForm.owner.trim()
  try {
    if (owner) localStorage.setItem('tahp_modem_patch_owner', owner)
  } catch {}
}

function rootsFromForm() {
  return workspaceForm.rootsText.split(/\r?\n/).map(item => item.trim()).filter(Boolean)
}

function inferPlatformFromPath(localPath: string) {
  const normalized = normalizeLocalPath(localPath)

  if (normalized.includes('TK_MD_MOLY.NR16.R1.MP3.MP_S0')) {
    return 'GEN98S(MP3)'
  }
  if (normalized.includes('TK_MD_MOLY.NR16.R1.MP1MP2.MP_S0')) {
    return 'GEN98S(MP1MP2)'
  }

  let base = ''
  if (normalized.includes('LR12A')) base = 'GEN93'
  else if (normalized.includes('LR13')) base = 'GEN95'
  else if (normalized.includes('NR15')) base = 'GEN97'
  else if (normalized.includes('NR16')) base = 'GEN98'
  else if (normalized.includes('NR17.R2')) base = 'GEN99-R2'
  else if (normalized.includes('NR17')) base = 'GEN99'

  if (!base) return ''

  const suffixMatch = normalized.match(/(?:\\|_)([STUVW])(?:\\|0|$)/)
  const suffix = suffixMatch?.[1] || ''
  return `${base}${suffix}`
}

watch(
  () => props.repos,
  (repos) => {
    const pending = pendingScanImport.value
    if (!pending) return
    const matched = repos.some(item =>
      normalizeLocalPath(item.localPath) === normalizeLocalPath(pending.localPath)
      && (item.platform || item.label) === pending.platform,
    )
    if (!matched) return
    closeScanImportDialog()
  },
  { deep: true },
)

function openScanImportDialog(item: ScannedRepoCandidate) {
  scanImportSourceName.value = item.repoName
  scanImportForm.localPath = item.localPath
  scanImportForm.platform = inferPlatformFromPath(item.localPath)
  pendingScanImport.value = null
  scanImportDialogOpen.value = true
}

function closeScanImportDialog() {
  scanImportDialogOpen.value = false
  scanImportSourceName.value = ''
  pendingScanImport.value = null
}

function submitScanImport() {
  const localPath = scanImportForm.localPath.trim()
  const platform = scanImportForm.platform.trim()
  if (!localPath || !platform) return
  pendingScanImport.value = { localPath, platform }
  emit('save-repo', {
    label: platform,
    localPath,
    platform,
  })
}

function isScannedRepoImported(localPath: string) {
  return importedRepoPathSet.value.has(normalizeLocalPath(localPath))
}
</script>

<template>
  <div class="ea-card ea-stack">
    <div class="cfg-head">
      <div>
        <div class="ea-section-title">工作区与仓库</div>
        <h3>路径配置</h3>
        <p>按当前用户维护本地映射盘、远端工作区和常用仓库，减少 `work_dir` 重复输入。</p>
      </div>
      <span class="ea-pill-info">{{ workspaceProfile?.owner || '当前用户' }}</span>
    </div>

    <div class="ea-form-grid2">
      <div class="ea-field">
        <label>Owner</label>
        <NInput v-model:value="workspaceForm.owner" placeholder="例如 yue.chen11" />
      </div>
      <div class="ea-field">
        <label>远端工作区前缀</label>
        <NInput :value="inferredRemotePrefix || '将根据 Owner 自动生成'" readonly />
        <div class="field-hint">固定按 `/work/&lt;owner&gt;/code` 生成，不再手工填写。</div>
      </div>
    </div>

    <div class="ea-field">
      <label>仓库根目录（每行一个）</label>
      <NInput
        v-model:value="workspaceForm.rootsText"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        placeholder="例如&#10;Z:\mtk\modem&#10;Z:\temp\modem"
      />
    </div>

    <div class="cfg-actions">
      <NButton
        type="primary"
        :loading="savingWorkspace"
        :disabled="!canSaveWorkspace"
        @click="persistOwner(); emit('save-workspace', {
        mappedPrefix: inferredMappedPrefix,
        remotePrefix: inferredRemotePrefix,
        roots: workspaceRoots,
      })">
        保存工作区配置
      </NButton>
      <NButton secondary :disabled="!scanRoot" :loading="scanningRepos" @click="emit('scan-repos', scanRoot)">扫描根目录</NButton>
    </div>

    <div v-if="rootOptions.length" class="ea-field">
      <label>扫描根目录</label>
      <NSelect
        v-model:value="workspaceForm.selectedRoot"
        :options="rootOptions"
        placeholder="选择一个根目录用于扫描"
      />
    </div>

    <div class="ea-field">
      <label>已登记仓库</label>
      <NSelect
        :value="selectedRepoId || null"
        :options="repoOptions"
        clearable
        placeholder="选择已登记仓库后自动带出路径"
        @update:value="value => value ? emit('choose-repo', String(value)) : emit('clear-repo')"
      />
    </div>

    <div v-if="selectedRepoId" class="cfg-actions">
      <NButton secondary :loading="removingRepo" @click="emit('remove-repo', selectedRepoId)">删除当前仓库</NButton>
    </div>

    <div class="ea-section-title">新增仓库</div>
    <div class="ea-form-grid2">
      <div class="ea-field">
        <label>本地路径</label>
        <NInput v-model:value="repoForm.localPath" placeholder="例如 Z:\mtk\modem\t\GEN95\repo" />
      </div>
      <div class="ea-field">
        <label>平台</label>
        <NInput v-model:value="repoForm.platform" placeholder="例如 GEN93V / GEN99U / GEN99-R2U" />
        <div class="field-hint">显示名称会自动使用平台值，不再单独填写。</div>
      </div>
    </div>
    <div class="cfg-actions">
      <NButton
        type="primary"
        :loading="savingRepo"
        :disabled="!repoForm.localPath.trim() || !repoForm.platform.trim()"
        @click="emit('save-repo', {
        label: repoForm.platform.trim(),
        localPath: repoForm.localPath,
        platform: repoForm.platform.trim(),
      })">
        保存仓库
      </NButton>
    </div>

    <div v-if="scanWarnings?.length" class="warning-list">
      <div v-for="warning in scanWarnings" :key="warning" class="warning-item">{{ warning }}</div>
    </div>

    <div v-if="sortedScanResults.length" class="scan-list">
      <div class="ea-section-title">扫描结果</div>
      <div
        v-for="item in sortedScanResults"
        :key="item.localPath"
        class="scan-item"
        :class="{ 'scan-item--imported': isScannedRepoImported(item.localPath) }"
      >
        <div>
          <strong>{{ item.repoName }}</strong>
          <p>{{ item.localPath }}</p>
          <p v-if="inferPlatformFromPath(item.localPath)" class="scan-platform">
            推断平台：{{ inferPlatformFromPath(item.localPath) }}
          </p>
          <p v-if="isScannedRepoImported(item.localPath)" class="scan-status">已导入到仓库清单</p>
        </div>
        <div class="scan-actions">
          <NButton
            secondary
            size="small"
            :disabled="isScannedRepoImported(item.localPath)"
            @click="openScanImportDialog(item)"
          >
            修改后导入
          </NButton>
          <NButton
            type="primary"
            size="small"
            :loading="savingRepo"
            :disabled="isScannedRepoImported(item.localPath) || !inferPlatformFromPath(item.localPath)"
            @click="emit('save-repo', {
              label: inferPlatformFromPath(item.localPath),
              localPath: item.localPath,
              platform: inferPlatformFromPath(item.localPath),
            })"
          >
            快速导入
          </NButton>
        </div>
      </div>
    </div>

    <NModal v-model:show="scanImportDialogOpen" preset="card" title="修改后导入" class="scan-import-modal">
      <div class="ea-stack">
        <div>
          <strong>{{ scanImportSourceName || '扫描结果' }}</strong>
          <p class="field-hint">在这里直接调整平台和本地路径，再导入到已配置仓库列表。</p>
        </div>
        <div class="ea-field">
          <label>平台</label>
          <NInput v-model:value="scanImportForm.platform" placeholder="例如 GEN93V / GEN99U / GEN99-R2U" />
        </div>
        <div class="ea-field">
          <label>本地路径</label>
          <NInput v-model:value="scanImportForm.localPath" placeholder="例如 Z:\mtk\modem\v\TK_MD..." />
        </div>
        <div class="modal-actions">
          <NButton secondary @click="closeScanImportDialog">取消</NButton>
          <NButton
            type="primary"
            :loading="savingRepo"
            :disabled="!scanImportForm.platform.trim() || !scanImportForm.localPath.trim()"
            @click="submitScanImport"
          >
            导入仓库
          </NButton>
        </div>
      </div>
    </NModal>
  </div>
</template>

<style scoped lang="scss">
.cfg-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;

  h3 {
    font-size: 18px;
    font-weight: 700;
    color: var(--head);
  }

  p {
    font-size: 13px;
    color: var(--muted);
    margin-top: 4px;
  }
}

.cfg-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  flex-wrap: wrap;
}

.warning-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.warning-item {
  padding: 10px 12px;
  border-radius: 12px;
  background: var(--amber-bg);
  color: var(--amber-fg);
  border: 1px solid color-mix(in srgb, var(--amber-ic) 20%, transparent);
  font-size: 12px;
}

.field-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--muted);
}

.scan-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.scan-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  border-radius: 14px;
  background: var(--bg);
  border: 1px solid var(--line);

  strong {
    display: block;
    color: var(--text);
    font-size: 13px;
  }

  p {
    margin-top: 4px;
    color: var(--muted);
    font-size: 12px;
    word-break: break-word;
    overflow-wrap: anywhere;
  }
}

.scan-item--imported {
  opacity: 0.58;
}

.scan-platform {
  color: var(--accent) !important;
}

.scan-status {
  color: var(--muted) !important;
}

.scan-actions {
  display: flex;
  gap: 8px;
  flex: 0 0 auto;
}

.scan-import-modal {
  width: min(560px, calc(100vw - 32px));
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

@media (max-width: 720px) {
  .cfg-head,
  .cfg-actions,
  .scan-item,
  .modal-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
