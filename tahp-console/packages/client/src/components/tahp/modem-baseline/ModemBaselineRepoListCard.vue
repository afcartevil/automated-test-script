<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { NButton, NEmpty, NInput, NModal, NPagination, NTag, useMessage } from 'naive-ui'
import type { RepoProfile } from '@/api/tahp/modem-baseline'

const message = useMessage()

const props = defineProps<{
  repos: RepoProfile[]
  selectedRepoId?: string
  updating?: boolean
  removing?: boolean
  refreshingBranches?: boolean
  /** 右侧等高滚动模式：展示全部过滤结果，列表区域内部滚动 */
  fillHeight?: boolean
}>()

const emit = defineEmits<{
  choose: [repoId: string]
  update: [repoId: string, value: { label: string; localPath: string; platform: string; branches?: RepoProfile['branches'] }]
  remove: [repoId: string]
  refreshBranches: [repoId?: string]
}>()

const page = ref(1)
const pageSize = 6
const keyword = ref('')
const editingRepoId = ref('')
const editing = ref(false)
const pendingSave = ref<{ repoId: string; localPath: string; platform: string } | null>(null)
const editForm = reactive({
  localPath: '',
  platform: '',
  trunkNodeBranch: '',
  trunkBranch: '',
  mp: [] as Array<{ tos: string; mpNodeBranch: string; mpBranch: string }>,
})

function compareTos(left: string, right: string) {
  const parse = (value: string) => String(value || '')
    .replace(/^tOS/i, '')
    .split('.')
    .map(part => Number(part) || 0)
  const leftParts = parse(left)
  const rightParts = parse(right)
  const max = Math.max(leftParts.length, rightParts.length)
  for (let i = 0; i < max; i += 1) {
    const diff = (leftParts[i] ?? 0) - (rightParts[i] ?? 0)
    if (diff !== 0) return diff
  }
  return String(left).localeCompare(String(right))
}

function getRepoBranchSummary(repo: RepoProfile) {
  const trunk = repo.branches?.trunk?.trunkBranch
    ? `${String(repo.branches?.trunk?.nodeBranch || '').trim() || '—'} -> ${repo.branches?.trunk?.trunkBranch}`
    : ''
  const mpItems = Array.isArray(repo.branches?.mp) ? [...repo.branches!.mp!] : []
  mpItems.sort((left, right) => compareTos(left.tos, right.tos))
  return trunk || mpItems.length
    ? {
      trunk,
      mpItems: mpItems.map(item => ({
        tos: item.tos,
        text: `${String(item.mpNodeBranch || '').trim() || '—'} -> ${item.mpBranch}`,
      })),
    }
    : null
}

const filteredRepos = computed(() => {
  const key = keyword.value.trim().toLowerCase()
  if (!key) return props.repos
  return props.repos.filter((repo) => {
    const fields = [
      repo.label,
      repo.platform,
      repo.localPath,
    ].filter(Boolean).join('\n').toLowerCase()
    return fields.includes(key)
  })
})

const total = computed(() => filteredRepos.value.length)
const pagedRepos = computed(() => {
  if (props.fillHeight) return filteredRepos.value
  const start = (page.value - 1) * pageSize
  return filteredRepos.value.slice(start, start + pageSize)
})

watch(total, (value) => {
  const pageCount = Math.max(1, Math.ceil(value / pageSize))
  if (page.value > pageCount) page.value = pageCount
})

watch(
  () => props.repos,
  (repos) => {
    const currentRepoId = editingRepoId.value
    if (!currentRepoId) return
    const repo = repos.find(item => item.repoId === currentRepoId)
    if (!repo) {
      closeEdit()
      return
    }
    const pending = pendingSave.value
    if (!pending || pending.repoId !== repo.repoId) return
    const currentPlatform = repo.platform || repo.label
    if (repo.label === pending.platform && currentPlatform === pending.platform && repo.localPath === pending.localPath) {
      closeEdit()
    }
  },
  { deep: true },
)

function closeEdit() {
  editing.value = false
  editingRepoId.value = ''
  pendingSave.value = null
}

function openEdit(repo: RepoProfile) {
  editingRepoId.value = repo.repoId
  editForm.localPath = repo.localPath
  editForm.platform = repo.platform || repo.label
  editForm.trunkNodeBranch = repo.branches?.trunk?.nodeBranch || ''
  editForm.trunkBranch = repo.branches?.trunk?.trunkBranch || ''
  editForm.mp = Array.isArray(repo.branches?.mp)
    ? repo.branches!.mp!.map(item => ({
      tos: item.tos,
      mpNodeBranch: item.mpNodeBranch || '',
      mpBranch: item.mpBranch,
    })).sort((left, right) => compareTos(left.tos, right.tos))
    : []
  pendingSave.value = null
  editing.value = true
}

function addMpRow() {
  editForm.mp.push({ tos: '', mpNodeBranch: '', mpBranch: '' })
}

function removeMpRow(index: number) {
  editForm.mp.splice(index, 1)
}

function submitEdit() {
  const repoId = editingRepoId.value
  if (!repoId) return
  const platform = editForm.platform.trim()
  const localPath = editForm.localPath.trim()
  if (!platform || !localPath) return
  const trunkNodeBranch = editForm.trunkNodeBranch.trim()
  const trunkBranch = editForm.trunkBranch.trim()
  const trunkEnabled = trunkNodeBranch || trunkBranch
  if (trunkEnabled && (!trunkNodeBranch || !trunkBranch)) {
    message.error('主干节点分支与主干分支需同时填写')
    return
  }
  for (let index = 0; index < editForm.mp.length; index += 1) {
    const item = editForm.mp[index]
    const tos = item.tos.trim()
    const mpNodeBranch = item.mpNodeBranch.trim()
    const mpBranch = item.mpBranch.trim()
    const enabled = tos || mpNodeBranch || mpBranch
    if (!enabled) continue
    if (!tos || !mpNodeBranch || !mpBranch) {
      message.error(`MP 第 ${index + 1} 行需填写 tOS / 节点分支 / 量产分支`)
      return
    }
  }
  pendingSave.value = {
    repoId,
    localPath,
    platform,
  }
  emit('update', repoId, {
    label: platform,
    localPath,
    platform,
    branches: {
      trunk: trunkEnabled ? { nodeBranch: trunkNodeBranch, trunkBranch } : undefined,
      mp: editForm.mp
        .map(item => ({
          tos: item.tos.trim(),
          mpNodeBranch: item.mpNodeBranch.trim(),
          mpBranch: item.mpBranch.trim(),
        }))
        .filter(item => item.tos && item.mpNodeBranch && item.mpBranch),
    },
  })
}

const canSubmitEdit = computed(() => {
  if (!editForm.platform.trim() || !editForm.localPath.trim()) return false
  const trunkNodeBranch = editForm.trunkNodeBranch.trim()
  const trunkBranch = editForm.trunkBranch.trim()
  const trunkEnabled = trunkNodeBranch || trunkBranch
  if (trunkEnabled && (!trunkNodeBranch || !trunkBranch)) return false
  return editForm.mp.every((item) => {
    const tos = item.tos.trim()
    const mpNodeBranch = item.mpNodeBranch.trim()
    const mpBranch = item.mpBranch.trim()
    const enabled = tos || mpNodeBranch || mpBranch
    return !enabled || (tos && mpNodeBranch && mpBranch)
  })
})

function branchTemplateTagType(status?: RepoProfile['branchTemplateStatus']) {
  if (status === 'running') return 'info'
  if (status === 'success') return 'success'
  if (status === 'failed') return 'error'
  return 'default'
}

function branchTemplateTagLabel(status?: RepoProfile['branchTemplateStatus']) {
  if (status === 'running') return '分支提取中'
  if (status === 'success') return '分支已提取'
  if (status === 'failed') return '分支提取失败'
  return '分支未提取'
}
</script>

<template>
  <div class="ea-card repo-list-card" :class="{ 'is-fill': fillHeight }">
    <div class="list-head">
      <div>
        <div class="ea-section-title">仓库清单</div>
        <h3>已配置仓库</h3>
        <p>查看、核对和修改已登记仓库。</p>
      </div>
      <div class="list-head__actions">
        <span class="ea-pill-info">共 {{ filteredRepos.length }} 项</span>
        <NButton secondary size="small" :loading="refreshingBranches" :disabled="!repos.length" @click="emit('refreshBranches')">
          刷新新增分支
        </NButton>
      </div>
    </div>

    <div class="search-row">
      <NInput v-model:value="keyword" placeholder="搜索平台 / 路径" clearable />
    </div>

    <div class="repo-scroll">
      <NEmpty v-if="!repos.length" description="当前还没有已登记仓库，先在左侧新增或扫描导入。" />
      <NEmpty v-else-if="!filteredRepos.length" description="未找到匹配仓库，换个关键词试试。" />

      <div v-else class="repo-list">
        <div
          v-for="repo in pagedRepos"
          :key="repo.repoId"
          class="repo-item"
          :class="{ 'repo-item--active': repo.repoId === selectedRepoId }"
        >
          <div class="repo-meta">
            <div class="repo-head">
              <div class="repo-title">
                <strong>{{ repo.label }}</strong>
                <NTag v-if="repo.repoId === selectedRepoId" size="small" type="success" round>当前选中</NTag>
                <NTag
                  v-if="repo.branchTemplateStatus"
                  size="small"
                  :type="branchTemplateTagType(repo.branchTemplateStatus)"
                  round
                  :title="repo.branchTemplateError || ''"
                >
                  {{ branchTemplateTagLabel(repo.branchTemplateStatus) }}
                </NTag>
              </div>
              <div class="repo-actions">
                <NButton secondary size="small" @click="emit('choose', repo.repoId)">设为当前</NButton>
                <NButton secondary size="small" :loading="refreshingBranches" @click="emit('refreshBranches', repo.repoId)">刷新分支</NButton>
                <NButton secondary size="small" @click="openEdit(repo)">编辑</NButton>
                <NButton tertiary size="small" type="error" :loading="removing" @click="emit('remove', repo.repoId)">删除</NButton>
              </div>
            </div>
            <p>{{ repo.localPath }}</p>
            <div class="repo-extra">
              <span class="ea-pill-muted">平台 {{ repo.platform || repo.label }}</span>
              <span class="ea-pill-muted">映射 {{ repo.mappedPrefix }} → {{ repo.remotePrefix }}</span>
            </div>
            <div v-if="getRepoBranchSummary(repo)" class="repo-branches">
              <div class="repo-branches__row">
                <NTag size="small" type="info" round>主干</NTag>
                <span
                  class="repo-branches__text"
                  :title="getRepoBranchSummary(repo)?.trunk || ''"
                >
                  {{ getRepoBranchSummary(repo)?.trunk || '—' }}
                </span>
              </div>
              <div v-for="mp in getRepoBranchSummary(repo)?.mpItems || []" :key="mp.tos" class="repo-branches__row">
                <NTag size="small" type="info" round>{{ mp.tos }}</NTag>
                <span class="repo-branches__text" :title="mp.text">{{ mp.text }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div v-if="!fillHeight && filteredRepos.length > pageSize" class="pagination-wrap">
      <NPagination v-model:page="page" :page-size="pageSize" :item-count="total" />
    </div>

    <NModal v-model:show="editing" preset="card" title="编辑仓库" class="repo-edit-modal">
      <div class="ea-stack">
        <div class="ea-field">
          <label>平台</label>
          <NInput v-model:value="editForm.platform" placeholder="例如 GEN93V / GEN99U / GEN99-R2U" />
        </div>
        <div class="ea-field">
          <label>本地路径</label>
          <NInput v-model:value="editForm.localPath" placeholder="例如 Z:\mtk\modem\v\TK_MD..." />
        </div>
        <div class="branch-edit">
          <div class="branch-table__head">
            <div class="ea-section-title">分支信息</div>
            <NButton secondary size="small" @click="addMpRow">新增 MP</NButton>
          </div>
          <div class="branch-table">
            <div class="branch-table__row branch-table__row--header">
              <span>类型 / tOS</span>
              <span>节点分支</span>
              <span>目标分支</span>
              <span class="branch-table__op">操作</span>
            </div>
            <div class="branch-table__row">
              <NInput :value="'主干'" disabled />
              <NInput v-model:value="editForm.trunkNodeBranch" placeholder="例如 master" />
              <NInput v-model:value="editForm.trunkBranch" placeholder="例如 PRODUCT_W_w0mp1rc_LR13_common" />
              <span class="branch-table__op branch-table__op--muted">—</span>
            </div>
            <div v-for="(item, index) in editForm.mp" :key="index" class="branch-table__row">
              <NInput v-model:value="item.tos" placeholder="tOS16.3 / tOS17.0" />
              <NInput v-model:value="item.mpNodeBranch" placeholder="节点分支" />
              <NInput v-model:value="item.mpBranch" placeholder="量产分支（tOSxx.x release）" />
              <div class="branch-table__op">
                <NButton tertiary size="small" type="error" @click="removeMpRow(index)">删除</NButton>
              </div>
            </div>
          </div>
        </div>
        <div class="modal-actions">
          <NButton secondary @click="closeEdit">取消</NButton>
          <NButton
            type="primary"
            :loading="updating"
            :disabled="!canSubmitEdit"
            @click="submitEdit"
          >
            保存修改
          </NButton>
        </div>
      </div>
    </NModal>
  </div>
</template>

<style scoped lang="scss">
.repo-list-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;

  &.is-fill {
    height: 100%;
  }
}

.list-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex: 0 0 auto;

  h3 {
    font-size: 18px;
    font-weight: 700;
    color: var(--head);
  }

  p {
    margin-top: 4px;
    font-size: 13px;
    color: var(--muted);
  }
}

.search-row {
  flex: 0 0 auto;
}

.repo-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
  scrollbar-gutter: stable;
}

.repo-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.repo-item {
  display: block;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--bg);
}

.repo-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.repo-item--active {
  border-color: color-mix(in srgb, var(--accent) 35%, var(--line));
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 15%, transparent);
}

.repo-title {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;

  strong {
    font-size: 15px;
    color: var(--text);
  }
}

.repo-meta {
  flex: 1 1 auto;
  min-width: 0;
  width: 100%;

  p {
    margin-top: 6px;
    font-size: 13px;
    color: var(--muted);
    word-break: break-word;
    overflow-wrap: anywhere;
  }
}

.repo-extra {
  margin-top: 10px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.search-row {
  display: flex;
}

.list-head__actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.repo-branches {
  margin-top: 10px;
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.repo-branches__row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  width: 100%;
}

.repo-branches__text {
  flex: 1 1 0%;
  min-width: 0;
  font-size: 12px;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.modal-actions,
.pagination-wrap {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  flex: 0 0 auto;
}

.repo-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.repo-edit-modal {
  width: min(560px, calc(100vw - 32px));
}

.branch-edit {
  padding-top: 8px;
  border-top: 1px solid var(--line);
}

.branch-table {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.branch-table__head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.branch-table__row {
  display: grid;
  grid-template-columns: minmax(110px, 140px) minmax(160px, 1fr) minmax(200px, 1.2fr) minmax(56px, 72px);
  gap: 8px;
  align-items: center;
}

.branch-table__row--header {
  font-size: 12px;
  color: var(--muted);
}

.branch-table__op {
  display: flex;
  justify-content: flex-end;
}

.branch-table__op--muted {
  color: var(--muted);
  font-size: 12px;
}

@media (max-width: 720px) {
  .list-head,
  .repo-head {
    flex-direction: column;
    align-items: stretch;
  }

  .list-head__actions {
    justify-content: stretch;
  }

  .repo-actions,
  .modal-actions,
  .pagination-wrap {
    justify-content: stretch;
    flex-direction: column;
  }

  .branch-table__row {
    grid-template-columns: 1fr;
  }
}
</style>
