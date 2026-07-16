<template>
  <div v-if="summary?.total" class="summary-box">
    <div id="analysis-section-summary" class="analysis-anchor">
      <div class="summary-title">📊 分析总结</div>

      <div class="summary-grid">
        <div class="summary-stat">
          <div class="stat-value">{{ summary.total }}</div>
          <div class="stat-label">总 Patch 数</div>
        </div>
        <div v-if="summary.llm_analyzed" class="summary-stat">
          <div class="stat-value stat-llm">{{ summary.llm_analyzed }}</div>
          <div class="stat-label">LLM 分析</div>
        </div>
        <div v-if="summary.script_analyzed" class="summary-stat">
          <div class="stat-value stat-script">{{ summary.script_analyzed }}</div>
          <div class="stat-label">脚本分析</div>
        </div>
        <div v-if="summary.blocked" class="summary-stat">
          <div class="stat-value stat-blocked">{{ summary.blocked }}</div>
          <div class="stat-label">阻断</div>
        </div>
        <div class="summary-stat">
          <div class="stat-value">{{ summary.avg_score ?? '-' }}</div>
          <div class="stat-label">平均分</div>
        </div>
      </div>

      <div v-if="analysisCoverage.total_patches" class="summary-section coverage-banner">
        <div class="summary-section-title">📈 分层分析覆盖率</div>
        <div class="coverage-stats">
          <span>
            已分析 {{ analysisCoverage.total_patches }} 笔 patch ·
            {{ analysisCoverage.module_count }} 个模块 ·
            {{ analysisCoverage.total_chunks }} 个 chunk
          </span>
          <span
            class="coverage-badge"
            :class="analysisCoverage.coverage_complete ? 'coverage-ok' : 'coverage-warn'"
            :title="analysisCoverage.coverage_complete ? '' : DIFF_TRUNCATE_HINT"
          >
            {{ analysisCoverage.coverage_complete ? '全量覆盖' : '部分 Diff 未完整取证' }}
          </span>
        </div>
        <p v-if="!analysisCoverage.coverage_complete" class="coverage-truncate-hint">
          {{ DIFF_TRUNCATE_HINT }}
        </p>
      </div>

      <div v-if="tagEntries.length" class="summary-section summary-tags-section">
        <div class="summary-section-title">🏷️ 标签分布</div>
        <div class="summary-tags">
          <span v-for="[label, count] in tagEntries" :key="label" class="tag-pill">
            {{ label }} <strong>{{ count }}</strong>
          </span>
        </div>
      </div>

      <div v-if="summary.text" class="summary-section summary-prose-section">
        <div class="summary-section-title">📝 详细综述</div>
        <AccordionMarkdown :markdown="summary.text" :default-open-count="2" />
      </div>
    </div>

    <div v-if="moduleEntries.length" id="analysis-section-modules" class="summary-section analysis-anchor">
      <div class="summary-section-title">🗂 分模块分析 ({{ moduleEntries.length }} 个模块)</div>
      <div class="module-analysis-grid">
        <div
          v-for="entry in moduleEntries"
          :key="entry.name"
          class="module-card"
          :class="{ open: openModules.has(entry.name) }"
        >
          <button type="button" class="module-card-header" @click="toggleModule(entry.name)">
            <div>
              <div class="module-card-title">{{ entry.name || '未分类' }}</div>
              <div class="module-card-meta">
                {{ entry.stats.patch_count || 0 }} 笔 · {{ entry.stats.files_changed || 0 }} 文件 ·
                +{{ entry.stats.insertions || 0 }}/-{{ entry.stats.deletions || 0 }} ·
                均分 {{ entry.stats.avg_score || 0 }}
                <span v-if="entry.coverage.total_patch_count">
                  · 覆盖 {{ entry.coverage.covered_patch_count || 0 }}/{{ entry.coverage.total_patch_count }}
                </span>
                <span v-if="entry.coverage.chunk_count > 1">
                  · {{ entry.coverage.chunk_count }} chunks
                </span>
              </div>
            </div>
            <div class="module-card-badges">
              <span
                v-if="entry.coverage.truncated_chunk_count || entry.coverage.split_exhausted_count"
                class="coverage-badge coverage-warn module-truncate-badge"
                :title="truncateBadgeTitle(entry.coverage)"
              >
                Diff 截断 {{ (entry.coverage.truncated_chunk_count || 0) + (entry.coverage.split_exhausted_count || 0) }}
              </span>
              <span
                v-else-if="entry.coverage.auto_split"
                class="coverage-badge coverage-ok module-truncate-badge"
                title="模块 diff 过大，已自动拆分为多个 chunk"
              >
                已自动拆分
              </span>
              <span class="crash-badge" :class="crashBadgeClass(entry.analysis.crash_risk)">
                死机 {{ entry.analysis.crash_risk || '低' }}
              </span>
              <span class="module-card-chevron">▼</span>
            </div>
          </button>
          <div v-show="openModules.has(entry.name)" class="module-card-body">
            <p
              v-if="entry.coverage.truncated_chunk_count || entry.coverage.split_exhausted_count"
              class="coverage-truncate-hint module-truncate-hint"
            >
              {{ DIFF_TRUNCATE_HINT }}
            </p>
            <div v-if="entry.chunkSummaries?.length" class="module-card-section">
              <h4>🧩 Chunk 摘要 ({{ entry.chunkSummaries.length }})</h4>
              <div
                v-for="chunk in entry.chunkSummaries"
                :key="chunk.chunk_id"
                class="chunk-summary-item"
              >
                <div class="chunk-summary-head">
                  <strong>{{ chunk.chunk_id }}</strong>
                  <span class="muted">{{ chunk.patch_count || 0 }} 笔</span>
                  <span
                    v-if="chunk.truncated_input"
                    class="coverage-badge coverage-warn"
                    :title="DIFF_TRUNCATE_HINT"
                  >
                    Diff 截断
                  </span>
                </div>
                <p v-if="chunk.truncated_input" class="coverage-truncate-hint">
                  {{ DIFF_TRUNCATE_HINT }}
                </p>
                <div v-if="chunk.main_changes" class="summary-text chunk-summary-body">
                  {{ chunk.main_changes }}
                </div>
                <div v-if="chunk.covered_shas?.length" class="muted chunk-sha-list">
                  覆盖: {{ chunk.covered_shas.slice(0, 8).join(', ') }}
                  <span v-if="chunk.covered_shas.length > 8">…(+{{ chunk.covered_shas.length - 8 }})</span>
                </div>
              </div>
            </div>
            <div v-if="entry.analysis.modification_interpretation" class="module-card-section">
              <h4>📖 修改解读</h4>
              <div class="summary-text" v-html="renderSimpleMarkdown(entry.analysis.modification_interpretation)"></div>
            </div>
            <div v-if="entry.analysis.impact_scope" class="module-card-section">
              <h4>🎯 影响范围</h4>
              <div class="summary-text" v-html="renderSimpleMarkdown(entry.analysis.impact_scope)"></div>
            </div>
            <div v-if="entry.analysis.problem_closure_summary" class="module-card-section">
              <h4>✅ 问题闭环</h4>
              <div class="summary-text" v-html="renderSimpleMarkdown(entry.analysis.problem_closure_summary)"></div>
            </div>
            <div v-if="entry.analysis.code_changes?.length" class="module-card-section">
              <h4>🔧 代码变化</h4>
              <ul>
                <li v-for="(change, idx) in entry.analysis.code_changes" :key="idx">
                  <code>{{ change.location }}</code>
                  <span v-if="change.risk_level" class="muted"> [{{ change.risk_level }}]</span>
                  — {{ change.explanation }}
                </li>
              </ul>
            </div>
            <div class="module-card-section">
              <h4>🌳 代码树</h4>
              <div class="code-tree-hint">📁 点击目录展开/折叠 · 📄 点击文件查看 diff · 悬停 1 秒查看分析摘要</div>
              <div class="code-tree">
                <CodeTreeNode v-if="entry.codeTree" :node="entry.codeTree" />
                <div v-else class="code-tree-empty">(无文件变更)</div>
              </div>
            </div>
            <div v-if="entry.analysis.test_suggestions" class="module-card-section">
              <h4>🧪 测试建议</h4>
              <div class="summary-text" v-html="renderSimpleMarkdown(entry.analysis.test_suggestions)"></div>
            </div>
            <div v-if="entry.analysis.verification_checklist?.length" class="module-card-section">
              <h4>☑️ 验证清单</h4>
              <ul class="module-checklist">
                <li v-for="(item, idx) in entry.analysis.verification_checklist" :key="idx">{{ item }}</li>
              </ul>
            </div>
            <div class="module-card-section">
              <h4>⚠️ 死机风险评估</h4>
              <div>
                <strong>{{ entry.analysis.crash_risk || '低' }}</strong>
                <span v-if="entry.analysis.crash_risk_reason"> — {{ entry.analysis.crash_risk_reason }}</span>
              </div>
            </div>
            <div v-if="entry.analysis.high_risk_patches?.length" class="module-card-section">
              <h4>🔴 高风险 Patch</h4>
              <ul class="summary-risk-list">
                <li v-for="item in entry.analysis.high_risk_patches" :key="item.sha">
                  <button type="button" class="summary-risk-item summary-risk-item-btn" @click="jumpToPatchItem(item.sha)">
                    <code>{{ item.sha }}</code>
                    <span>{{ item.title || '-' }}</span>
                    <span class="high-risk-reason">原因：{{ formatHighRiskReason(item) || item.reason }}</span>
                  </button>
                </li>
              </ul>
            </div>
            <div v-if="entry.analysis.cross_module_notes" class="module-card-section">
              <h4>🔗 跨模块影响</h4>
              <div class="summary-text" v-html="renderSimpleMarkdown(entry.analysis.cross_module_notes)"></div>
            </div>
            <button type="button" class="btn btn-sm" @click="$emit('filter-module', entry.name)">
              筛选该模块 Patch
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="summary.test_summary_llm" id="analysis-section-tests" class="summary-section analysis-anchor">
      <div class="summary-section-title">🧪 综合测试建议（LLM）</div>
      <AccordionMarkdown :markdown="summary.test_summary_llm" :default-open-count="1" />
    </div>

    <div v-else-if="hasScriptTestSuggestions" id="analysis-section-tests" class="summary-section analysis-anchor">
      <div class="summary-section-title">🧪 综合测试建议</div>
      <div v-for="field in testFieldsWithData" :key="field.key" class="test-group">
        <strong>{{ field.label }}</strong>
        <span class="muted">({{ field.totalPatches }} 笔涉及)</span>
        <div class="summary-tags">
          <span v-for="item in field.items" :key="item.text" class="tag-pill" :title="item.text">
            {{ item.text }} <strong>{{ item.count }}</strong>
          </span>
        </div>
      </div>
    </div>

    <div v-if="summary.squash_summary && !summary.text" class="summary-section">
      <div class="summary-section-title">📦 Squash Diff 分析（历史数据）</div>
      <div class="summary-text" v-html="renderSimpleMarkdown(summary.squash_summary)"></div>
    </div>

    <div
      v-if="futureFixItems.length || Number(summary?.future_fix_pool_count || 0) > 0"
      id="analysis-section-future-fix"
      class="summary-section future-fix-section analysis-anchor"
    >
      <div class="summary-section-title">
        🔗 后续 Fixes 修复
        <span class="muted">
          ({{ futureFixItems.length || summary?.future_fix_pool_count || 0 }} 笔)
        </span>
      </div>
      <div class="future-fix-hint muted">
        以下 patch 在后续 tag 中有 Fixes: 提交指向本笔；合入前请确认修复是否已覆盖或风险可接受。
        <span
          v-if="summary?.future_fix_pool_count && summary.future_fix_pool_count > futureFixItems.length"
        >
          （扫描池共 {{ summary.future_fix_pool_count }} 笔，本页展示采样内
          {{ futureFixItems.length }} 笔）
        </span>
      </div>
      <div v-if="!futureFixItems.length" class="execution-steps-empty muted">
        扫描池内 {{ summary?.future_fix_pool_count || 0 }} 笔有后续修复，但当前任务采样的
        {{ summary?.total || 0 }} 笔中未包含这些 patch；请在下方的 Patch 列表中搜索 SHA，或重新运行分析以刷新数据。
      </div>
      <div v-else class="summary-risk-list future-fix-list">
        <button
          v-for="item in futureFixItems"
          :key="item.sha"
          type="button"
          class="summary-risk-item summary-risk-item-btn future-fix-item"
          @click="jumpToPatchItem(item.sha)"
        >
          <code>{{ shortId(item.sha, 12) }}</code>
          <span>{{ item.title || '-' }}</span>
          <span v-if="item.dev_module" class="tag-pill dev-module">{{ item.dev_module }}</span>
          <span class="future-fix-badge">{{ item.fix_count }} 笔后续修复</span>
          <span v-if="item.fix_tags?.length" class="future-fix-tags muted">
            修复 tag：{{ item.fix_tags.join('、') }}
          </span>
          <span v-if="item.introducer_summary" class="high-risk-reason">
            引入：{{ item.introducer_summary }}
          </span>
          <span v-if="item.fix_subjects?.length" class="high-risk-reason future-fix-subjects">
            修复：{{ item.fix_subjects.join('；') }}
          </span>
        </button>
      </div>
    </div>

    <div v-if="summary.high_risk?.length" id="analysis-section-high-risk" class="summary-section analysis-anchor">
      <div class="summary-section-title">⚠️ 高风险 Patch</div>
      <div class="summary-risk-list">
        <button
          v-for="item in summary.high_risk"
          :key="item.sha"
          type="button"
          class="summary-risk-item summary-risk-item-btn"
          @click="jumpToPatchItem(item.sha)"
        >
          <code>{{ shortId(item.sha, 12) }}</code>
          <span>{{ item.title || '-' }}</span>
          <span class="high-risk-reason">原因：{{ formatHighRiskReason(item) }}</span>
        </button>
      </div>
    </div>

    <PatchPopover />
  </div>
</template>

<script setup lang="ts">
import { computed, provide, ref } from 'vue'
import AccordionMarkdown from './AccordionMarkdown.vue'
import CodeTreeNode from './CodeTreeNode.vue'
import PatchPopover from './PatchPopover.vue'
import { shortId } from '../../api'
import {
  TEST_SUGGESTION_FIELDS,
  buildFutureFixDisplayItem,
  collectFutureFixPatches,
  crashBadgeClass,
  DIFF_TRUNCATE_HINT,
  filterFutureFixItemsInPatches,
  formatHighRiskReason,
  formatKeyRiskLabel,
  renderSimpleMarkdown,
} from '../../utils/analysisDisplay'

const props = defineProps<{
  summary: any
  patches?: any[]
}>()

const emit = defineEmits<{
  'filter-module': [name: string]
  'jump-to-patch': [sha: string]
}>()

provide('jumpToPatch', (sha: string) => emit('jump-to-patch', sha))

const openModules = ref<Set<string>>(new Set())

const analysisCoverage = computed(() => {
  const fromSummary = props.summary?.analysis_coverage || {}
  const fromModules = props.summary?.module_summaries || {}
  return {
    module_count: fromSummary.module_count || fromModules.module_count || 0,
    total_patches: fromSummary.total_patches || fromModules.total_patches || props.summary?.total || 0,
    total_chunks: fromSummary.total_chunks || fromModules.total_chunks || 0,
    coverage_complete:
      fromSummary.coverage_complete ?? fromModules.coverage_complete ?? true,
  }
})

const moduleEntries = computed(() => {
  const modulesMap = props.summary?.module_summaries?.modules || {}
  return Object.entries(modulesMap)
    .map(([name, mod]: [string, any]) => ({
      name,
      stats: mod?.stats || {},
      analysis: mod?.analysis || {},
      codeTree: mod?.code_tree || null,
      coverage: mod?.coverage || {},
      chunkSummaries: mod?.chunk_summaries || [],
    }))
    .sort((a, b) => (b.stats.patch_count || 0) - (a.stats.patch_count || 0))
})

const tagEntries = computed(() =>
  Object.entries(props.summary?.tag_counts || {}).sort((a, b) => Number(b[1]) - Number(a[1])),
)

const testFieldsWithData = computed(() =>
  TEST_SUGGESTION_FIELDS.map((field) => {
    const items = props.summary?.test_suggestions?.[field.key] || []
    return {
      ...field,
      items,
      totalPatches: items.reduce((sum: number, item: any) => sum + Number(item.count || 0), 0),
    }
  }).filter((field) => field.items.length > 0),
)

const hasScriptTestSuggestions = computed(() => testFieldsWithData.value.length > 0)

const futureFixItems = computed(() => {
  const fromSummary = props.summary?.future_fix_patches
  const rawItems =
    Array.isArray(fromSummary) && fromSummary.length
      ? fromSummary
      : collectFutureFixPatches(props.patches || []).map(buildFutureFixDisplayItem)
  return filterFutureFixItemsInPatches(rawItems, props.patches || []).slice(0, 30)
})

function truncateBadgeTitle(coverage: Record<string, number | undefined>) {
  const truncated = coverage.truncated_chunk_count || 0
  const exhausted = coverage.split_exhausted_count || 0
  const parts: string[] = []
  if (truncated) parts.push(`${truncated} 个 chunk diff 被截断`)
  if (exhausted) parts.push(`${exhausted} 个超大 patch 无法继续拆分`)
  const detail = parts.join('；') || '部分 diff 未完整送入 LLM'
  return `${detail}。${DIFF_TRUNCATE_HINT}`
}

function toggleModule(name: string) {
  const next = new Set(openModules.value)
  if (next.has(name)) next.delete(name)
  else next.add(name)
  openModules.value = next
}

function jumpToPatchItem(sha: string) {
  if (!sha) return
  emit('jump-to-patch', sha)
}
</script>
