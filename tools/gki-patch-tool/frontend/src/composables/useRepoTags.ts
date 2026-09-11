import { ref } from 'vue'
import { api } from '../api'

const repoTags = ref<string[]>([])
const tagsLoading = ref(false)
const tagsHint = ref('未读取到 tag，请先在设置中配置本地 kernel 仓')
let inflight: Promise<void> | null = null

export function useRepoTags() {
  async function loadRepoTags(force = false) {
    if (!force && repoTags.value.length) return
    if (tagsLoading.value && inflight) return inflight
    tagsLoading.value = true
    inflight = (async () => {
      try {
        const data = await api.get<any>(`/api/repo/tags${force ? '?refresh=1' : ''}`)
        repoTags.value = data.tags || []
        if (!data.configured) {
          tagsHint.value = '未配置本地 kernel 仓，请先在设置中填写路径；仍可手动输入 tag'
        } else if (!repoTags.value.length) {
          tagsHint.value = '本地仓库暂无 tag，请确认已 fetch tags；仍可手动输入'
        } else {
          tagsHint.value = `已加载 ${data.total ?? repoTags.value.length} 个 tag`
        }
      } catch (err: any) {
        repoTags.value = []
        tagsHint.value = err.message || '读取仓库 tag 失败，仍可手动输入'
      } finally {
        tagsLoading.value = false
        inflight = null
      }
    })()
    return inflight
  }

  return { repoTags, tagsLoading, tagsHint, loadRepoTags }
}
