<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NInput } from 'naive-ui'
import type { NoticeParseResult, RecommendationResult } from '@/api/tahp/modem-baseline'

const props = defineProps<{
  noticeText: string
  parsed: NoticeParseResult | null
  recommendation: RecommendationResult | null
  parsing?: boolean
  recommending?: boolean
}>()

const emit = defineEmits<{
  'update:noticeText': [value: string]
  'parse-and-apply': []
}>()

const processing = computed(() => Boolean(props.parsing || props.recommending))

const parseSummary = computed(() => {
  if (!props.parsed) return null
  const parts = [
    props.parsed.operationType,
    props.parsed.platform ? `platform=${props.parsed.platform}` : '',
    props.parsed.version ? `version=${props.parsed.version}` : '',
    `confidence=${props.parsed.confidence.toFixed(2)}`,
  ].filter(Boolean)
  return parts.join(' ')
})

const recommendationSummary = computed(() => {
  if (!props.recommendation) return null
  const parts = [
    props.recommendation.nodeBranch ? `NODE_BRANCH=${props.recommendation.nodeBranch}` : '',
    props.recommendation.targetBranch ? `target_BRANCH=${props.recommendation.targetBranch}` : '',
    props.recommendation.apLabel ? `AP=${props.recommendation.apLabel}` : '',
  ].filter(Boolean)
  return parts.join('\n')
})
</script>

<template>
  <div class="ea-card ea-stack">
    <div class="cfg-head">
      <div>
        <div class="ea-section-title">通知解析与推荐</div>
        <h3>Recommendation</h3>
        <p>粘贴通知文本，系统解析平台/版本并基于规则生成推荐分支，可一键应用到执行参数。</p>
      </div>
      <div class="cfg-actions">
        <NButton type="primary" :loading="processing" @click="$emit('parse-and-apply')">解析并应用</NButton>
      </div>
    </div>

    <div class="ea-field">
      <label>通知内容</label>
      <NInput
        :value="noticeText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 6 }"
        placeholder="例如：7月基线升级 GEN99-V V11.35"
        @update:value="$emit('update:noticeText', $event)"
      />
    </div>

    <div class="ea-form-grid2">
      <div class="ea-field">
        <label>解析结果</label>
        <div class="mono-box">{{ parseSummary || '尚未解析' }}</div>
        <div v-if="parsed?.warnings?.length" class="warn-lines">
          <div v-for="w in parsed.warnings" :key="w" class="warn-line">{{ w }}</div>
        </div>
      </div>

      <div class="ea-field">
        <label>推荐结果</label>
        <div class="mono-box">{{ recommendationSummary || '尚未生成推荐' }}</div>
        <div v-if="recommendation?.warnings?.length" class="warn-lines">
          <div v-for="w in recommendation.warnings" :key="w" class="warn-line">{{ w }}</div>
        </div>
      </div>
    </div>

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
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.mono-box {
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid var(--line);
  background: var(--bg);
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 12px;
  color: var(--text);
  min-height: 56px;
}

.warn-lines {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.warn-line {
  padding: 8px 10px;
  border-radius: 12px;
  background: var(--amber-bg);
  color: var(--amber-fg);
  border: 1px solid color-mix(in srgb, var(--amber-ic) 20%, transparent);
  font-size: 12px;
}

@media (max-width: 720px) {
  .cfg-head,
  .cfg-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
