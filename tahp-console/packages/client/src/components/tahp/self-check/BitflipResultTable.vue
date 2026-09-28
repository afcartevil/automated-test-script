<script setup lang="ts">
import { computed } from 'vue'
import type { BitflipResultDetail } from '@/api/tahp/device-self-check'

const props = defineProps<{
  result: BitflipResultDetail
}>()

const resultColIndex = computed(() =>
  props.result.columns.findIndex(c => String(c).toLowerCase() === 'result'),
)

/** 行补齐到表头列数（xlsx 末列空单元格可能缺省） */
const normalizedRows = computed(() =>
  (props.result.rows || []).map(row => {
    const cells = Array.isArray(row) ? [...row] : []
    while (cells.length < props.result.columns.length) cells.push('')
    return cells
  }),
)

const overallOk = computed(() => props.result.overallResult === 'PASS')

function rowOk(row: any[]): boolean {
  const idx = resultColIndex.value
  return idx >= 0 && row[idx] === true
}

function displayCell(cell: any): string {
  if (cell === null || cell === undefined) return ''
  return String(cell)
}
</script>

<template>
  <div class="bitflip-result">
    <div class="bitflip-summary">
      <span class="bitflip-overall" :class="overallOk ? 'is-pass' : 'is-fail'">
        整体结果: {{ result.overallResult || 'UNKNOWN' }}
      </span>
      <span class="bitflip-stat">
        共 {{ result.totalRounds ?? 0 }} 轮：通过 {{ result.passedRounds ?? 0 }}、失败 {{ result.failedRounds ?? 0 }}
      </span>
      <span v-if="result.repeatCount" class="bitflip-stat">每项重复 {{ result.repeatCount }} 次 (-r)</span>
    </div>
    <div class="bitflip-table-wrap">
      <table class="bitflip-table">
        <thead>
          <tr>
            <th v-for="(col, i) in result.columns" :key="i">{{ col }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, ri) in normalizedRows"
            :key="ri"
            :class="{ 'row-pass': rowOk(row), 'row-fail': !rowOk(row) }"
          >
            <td v-for="(cell, ci) in row" :key="ci">
              <span
                v-if="typeof cell === 'boolean'"
                :class="cell ? 'cell-pass' : 'cell-fail'"
              >{{ cell ? '通过' : '失败' }}</span>
              <template v-else>{{ displayCell(cell) }}</template>
            </td>
          </tr>
          <tr v-if="!normalizedRows.length">
            <td :colspan="result.columns.length" class="bitflip-empty">无有效轮次</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="bitflip-paths">
      <div v-if="result.logDir" class="bitflip-path">
        <span class="path-label">测试日志目录</span>
        <span class="path-value">{{ result.logDir }}</span>
      </div>
      <div v-if="result.bstLogPath" class="bitflip-path">
        <span class="path-label">主日志 (BST_Log.txt)</span>
        <span class="path-value">{{ result.bstLogPath }}</span>
      </div>
      <div v-if="result.xlsxPath" class="bitflip-path">
        <span class="path-label">原始结果表</span>
        <span class="path-value">{{ result.xlsxPath }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.bitflip-result {
  margin-top: 12px;
}

.bitflip-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  align-items: center;
  margin-bottom: 8px;
  font-size: 13px;
}

.bitflip-overall {
  font-weight: 600;

  &.is-pass { color: var(--success); }
  &.is-fail { color: var(--error); }
}

.bitflip-stat {
  color: var(--muted);
}

.bitflip-table-wrap {
  overflow-x: auto;
  border: 1px solid var(--border);
  border-radius: 6px;
}

.bitflip-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
  white-space: nowrap;

  th,
  td {
    padding: 6px 10px;
    border-bottom: 1px solid var(--border);
    text-align: left;
  }

  th {
    background: var(--bg);
    font-weight: 600;
    position: sticky;
    top: 0;
  }

  .row-fail {
    background: rgba(244, 68, 68, 0.06);
  }

  .cell-pass { color: var(--success); }
  .cell-fail { color: var(--error); font-weight: 600; }
}

.bitflip-empty {
  text-align: center;
  color: var(--muted);
}

.bitflip-paths {
  margin-top: 8px;
  font-size: 12px;
}

.bitflip-path {
  display: flex;
  gap: 8px;
  margin-bottom: 4px;
  word-break: break-all;

  .path-label {
    flex-shrink: 0;
    color: var(--muted);
  }

  .path-value {
    color: var(--text);
    user-select: text;
  }
}
</style>
