<template>
  <div v-if="submissions.length" class="gerrit-submissions-panel">
    <div class="gerrit-submissions-header">
      <div>
        <h2>Gerrit 提交</h2>
        <p class="muted">按仓库展示本次升级生成的 commit 与 Gerrit 链接</p>
      </div>
      <span class="pill success">{{ submissions.length }} 个仓库</span>
    </div>

    <div class="gerrit-submissions-body">
      <table class="gerrit-submissions-table">
        <thead>
          <tr>
            <th class="col-repo">仓库</th>
            <th class="col-sha">Commit</th>
            <th class="col-branch">目标分支</th>
            <th class="col-gerrit">Gerrit</th>
            <th class="col-status">状态</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in submissions" :key="row.repo_key || row.repo_label">
            <td class="col-repo">
              <div class="gerrit-repo-name" :title="row.repo_root || row.repo_key">{{ row.repo_label || row.repo_key || '-' }}</div>
              <div v-if="row.repo_root && row.repo_root !== row.repo_label" class="gerrit-repo-path muted mono" :title="row.repo_root">
                {{ shortPath(row.repo_root) }}
              </div>
            </td>
            <td class="col-sha mono">
              <a
                v-if="row.gerrit_url && row.commit_sha"
                :href="row.gerrit_url"
                target="_blank"
                rel="noopener"
                :title="row.commit_sha"
              >
                {{ shortSha(row.commit_sha) }}
              </a>
              <span v-else-if="row.commit_sha" :title="row.commit_sha">{{ shortSha(row.commit_sha) }}</span>
              <span v-else class="muted">-</span>
            </td>
            <td class="col-branch mono muted" :title="row.review_branch || row.push_cmd">
              {{ row.review_branch || '-' }}
            </td>
            <td class="col-gerrit">
              <a
                v-if="row.gerrit_url"
                class="gerrit-link"
                :href="row.gerrit_url"
                target="_blank"
                rel="noopener"
              >
                打开 Gerrit
              </a>
              <span v-else class="muted">-</span>
            </td>
            <td class="col-status">
              <span v-if="row.pushed" class="pill success">已推送</span>
              <span v-else-if="row.push_error" class="pill danger" :title="row.push_error">Push 失败</span>
              <span v-else class="pill muted">仅 commit</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { gerritSubmissionsForJob } from '../../utils/upgrade'

const props = defineProps<{
  job?: Record<string, any>
  progress?: Record<string, any>
}>()

const submissions = computed(() => gerritSubmissionsForJob(props.job, props.progress))

function shortSha(sha?: string) {
  const s = String(sha || '').trim()
  return s ? s.slice(0, 12) : '-'
}

function shortPath(path?: string, max = 56) {
  const s = String(path || '').replace(/\\/g, '/')
  if (!s) return ''
  return s.length > max ? `…${s.slice(-max + 1)}` : s
}
</script>
