<template>
  <Teleport to="body">
    <div
      v-if="visible"
      id="patch-analysis-popover"
      class="patch-popover"
      :style="{ left: `${position.x}px`, top: `${position.y}px` }"
      @mouseenter="cancelHide"
      @mouseleave="scheduleHide"
    >
      <div v-for="(patch, index) in patches" :key="patch.full_sha || patch.sha || index" class="patch-popover-item">
        <div class="patch-popover-title">
          {{ shortId(patch.sha || patch.full_sha, 12) }} · {{ patch.title || '-' }}
        </div>
        <div class="patch-popover-meta">
          <span>{{ patch.llm_analyzed ? 'LLM' : '脚本' }}</span>
          <span>评分 {{ formatPatchScore(patch.score) }}</span>
          <span>+{{ patch.insertions || 0 }}/-{{ patch.deletions || 0 }}</span>
        </div>
        <div v-if="patch.crash_risk" class="patch-popover-meta">
          <span>死机风险 {{ patch.crash_risk }}</span>
        </div>
        <div class="patch-popover-summary">{{ patch.summary || '(暂无解读)' }}</div>
        <div
          v-if="patch.key_risk"
          class="patch-popover-risk"
          :class="keyRiskTone(patch.key_risk) === 'none' ? 'patch-popover-risk-none' : 'patch-popover-risk-warn'"
        >
          {{ keyRiskTone(patch.key_risk) === 'none' ? '✓' : '⚠' }} {{ formatKeyRiskLabel(patch.key_risk) }}
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { shortId } from '../../api'
import { usePatchPopover } from '../../composables/usePatchPopover'
import { formatKeyRiskLabel, formatPatchScore, keyRiskTone } from '../../utils/analysisDisplay'

const { visible, patches, position, scheduleHide, cancelHide } = usePatchPopover()
</script>
