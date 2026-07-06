<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { NButton, NEmpty, NInput, NModal, NPagination, NTag } from 'naive-ui'
import type { RepoProfile } from '@/api/tahp/modem-baseline'

const props = defineProps<{
  repos: RepoProfile[]
  selectedRepoId?: string
  updating?: boolean
  removing?: boolean
}>()

const emit = defineEmits<{
  choose: [repoId: string]
  update: [repoId: string, value: { label: string; localPath: string; platform: string }]
  remove: [repoId: string]
}>()

const page = ref(1)
const pageSize = 6
const editingRepoId = ref('')
const editing = ref(false)
const pendingSave = ref<{ repoId: string; localPath: string; platform: string } | null>(null)
const editForm = reactive({
  localPath: '',
  platform: '',
})

const total = computed(() => props.repos.length)
const pagedRepos = computed(() => {
  const start = (page.value - 1) * pageSize
  return props.repos.slice(start, start + pageSize)
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
  pendingSave.value = null
  editing.value = true
}

function submitEdit() {
  const repoId = editingRepoId.value
  if (!repoId) return
  const platform = editForm.platform.trim()
  const localPath = editForm.localPath.trim()
  if (!platform || !localPath) return
  pendingSave.value = {
    repoId,
    localPath,
    platform,
  }
  emit('update', repoId, {
    label: platform,
    localPath,
    platform,
  })
}
</script>

<template>
  <div class="ea-card ea-stack">
    <div class="list-head">
      <div>
        <div class="ea-section-title">仓库清单</div>
        <h3>已配置仓库</h3>
        <p>统一查看、核对和修改已登记仓库，避免后续只能删除重建。</p>
      </div>
      <span class="ea-pill-info">共 {{ repos.length }} 项</span>
    </div>

    <NEmpty v-if="!repos.length" description="当前还没有已登记仓库，先在上方新增或扫描导入。" />

    <div v-else class="repo-list">
      <div
        v-for="repo in pagedRepos"
        :key="repo.repoId"
        class="repo-item"
        :class="{ 'repo-item--active': repo.repoId === selectedRepoId }"
      >
        <div class="repo-meta">
          <div class="repo-title">
            <strong>{{ repo.label }}</strong>
            <NTag v-if="repo.repoId === selectedRepoId" size="small" type="success" round>当前选中</NTag>
          </div>
          <p>{{ repo.localPath }}</p>
          <div class="repo-extra">
            <span class="ea-pill-muted">平台 {{ repo.platform || repo.label }}</span>
            <span class="ea-pill-muted">映射 {{ repo.mappedPrefix }} → {{ repo.remotePrefix }}</span>
          </div>
        </div>
        <div class="repo-actions">
          <NButton secondary size="small" @click="emit('choose', repo.repoId)">设为当前</NButton>
          <NButton secondary size="small" @click="openEdit(repo)">编辑</NButton>
          <NButton tertiary size="small" type="error" :loading="removing" @click="emit('remove', repo.repoId)">删除</NButton>
        </div>
      </div>
    </div>

    <div v-if="repos.length > pageSize" class="pagination-wrap">
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
        <div class="modal-actions">
          <NButton secondary @click="closeEdit">取消</NButton>
          <NButton
            type="primary"
            :loading="updating"
            :disabled="!editForm.platform.trim() || !editForm.localPath.trim()"
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
.list-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;

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

.repo-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.repo-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 14px 16px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--bg);
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
  min-width: 0;

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

.repo-actions,
.modal-actions,
.pagination-wrap {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.repo-actions {
  flex: 0 0 auto;
  flex-wrap: wrap;
}

.repo-edit-modal {
  width: min(560px, calc(100vw - 32px));
}

@media (max-width: 720px) {
  .list-head,
  .repo-item {
    flex-direction: column;
    align-items: stretch;
  }

  .repo-actions,
  .modal-actions,
  .pagination-wrap {
    justify-content: stretch;
    flex-direction: column;
  }
}
</style>
