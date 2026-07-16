<template>
  <div id="analysis-section-subtag" class="card card-pad monthly-recommendation analysis-anchor">
    <div class="section-title">
      <div>
        <h2>目标月份子 tag 分析</h2>
        <p>自 r1 累计至各子 tag（r1→r2、r1→r3…），点击区间查看全部 patch 分析</p>
      </div>
      <span v-if="recommendation.recommended_tag" class="pill success">
        优选 {{ recommendation.recommended_tag }}
      </span>
    </div>
    <p v-if="recommendation.reason" class="monthly-reason">{{ recommendation.reason }}</p>

    <div v-if="rangeStats.length" class="table-wrap">
      <table class="monthly-subtag-table">
        <thead>
          <tr>
            <th>子区间</th>
            <th>目标子 tag</th>
            <th>Patch</th>
            <th>平均分</th>
            <th>最低分</th>
            <th>风险分布</th>
            <th>未来修复</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          <template v-for="item in rangeStats" :key="intervalKey(item)">
            <tr
              class="monthly-subtag-row"
              :class="{ expanded: expandedKey === intervalKey(item) }"
            >
              <td class="mono">{{ item.from_tag }} → {{ item.to_tag }}</td>
              <td class="mono">{{ item.to_tag }}</td>
              <td>{{ item.total_patches }}</td>
              <td>{{ item.avg_score }}</td>
              <td>{{ item.min_score }}</td>
              <td>
                高 {{ item.risk_distribution?.high || 0 }} /
                中 {{ item.risk_distribution?.medium || 0 }} /
                低 {{ item.risk_distribution?.low || 0 }}
              </td>
              <td>{{ item.has_future_fix_count || 0 }}</td>
              <td class="monthly-subtag-actions">
                <button
                  type="button"
                  class="btn btn-sm monthly-subtag-toggle"
                  :class="{ 'is-expanded': expandedKey === intervalKey(item) }"
                  :disabled="loadingKey === intervalKey(item)"
                  @click="toggleInterval(item)"
                >
                  {{
                    loadingKey === intervalKey(item)
                      ? '加载中…'
                      : expandedKey === intervalKey(item)
                        ? '收起'
                        : '查看 patch'
                  }}
                </button>
              </td>
            </tr>
            <tr v-if="expandedKey === intervalKey(item)" class="monthly-subtag-detail-row">
              <td colspan="8">
                <div class="monthly-subtag-detail">
                  <div v-if="errorByKey[intervalKey(item)]" class="message error">
                    {{ errorByKey[intervalKey(item)] }}
                  </div>
                  <PatchListPanel
                    v-else-if="patchesByKey[intervalKey(item)]?.length"
                    :patches="patchesByKey[intervalKey(item)]"
                  />
                  <div v-else-if="loadingKey === intervalKey(item)" class="empty-state-inline">
                    加载 patch 列表…
                  </div>
                  <div v-else class="empty-state-inline">暂无 patch 数据</div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import PatchListPanel from './PatchListPanel.vue'
import { api } from '../../api'

const props = defineProps<{
  taskId: string
  recommendation: Record<string, any>
}>()

const rangeStats = computed(() => props.recommendation?.range_stats || [])

const expandedKey = ref('')
const loadingKey = ref('')
const patchesByKey = reactive<Record<string, any[]>>({})
const errorByKey = reactive<Record<string, string>>({})

function intervalKey(item: Record<string, any>) {
  return `${item.from_tag}::${item.to_tag}`
}

async function toggleInterval(item: Record<string, any>) {
  const key = intervalKey(item)
  if (expandedKey.value === key) {
    expandedKey.value = ''
    return
  }
  expandedKey.value = key
  if (patchesByKey[key]?.length) return

  loadingKey.value = key
  errorByKey[key] = ''
  try {
    const params = new URLSearchParams({
      from_tag: item.from_tag,
      to_tag: item.to_tag,
    })
    const data = await api.get<any>(
      `/api/tasks/${encodeURIComponent(props.taskId)}/monthly-subtag-patches?${params.toString()}`,
    )
    patchesByKey[key] = data.patches || []
    if (!patchesByKey[key].length && data.missing_shas?.length) {
      errorByKey[key] = `有 ${data.missing_shas.length} 笔 patch 尚未入库（请重新分析子 tag）`
    }
  } catch (err: any) {
    errorByKey[key] = err.message || String(err)
    patchesByKey[key] = []
  } finally {
    if (loadingKey.value === key) loadingKey.value = ''
  }
}
</script>
