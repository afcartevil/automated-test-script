<script setup lang="ts">
import { computed } from 'vue'
import { NButton, NInput } from 'naive-ui'

export type ParseFeedback = {
  tone: 'success' | 'warning'
  title: string
  successes: string[]
  failures: string[]
} | null

const props = defineProps<{
  noticeText: string
  parsing?: boolean
  recommending?: boolean
  parseFeedback?: ParseFeedback
}>()

const emit = defineEmits<{
  'update:noticeText': [value: string]
  'parse-and-apply': []
}>()

const processing = computed(() => Boolean(props.parsing || props.recommending))
const hasFeedback = computed(() => Boolean(props.parseFeedback))
const filled = computed(() => (props.parseFeedback?.successes.length ?? 0) > 0)
const unfilled = computed(() => (props.parseFeedback?.failures.length ?? 0) > 0)
</script>

<template>
  <div class="parse-card" :class="{ 'has-feedback': hasFeedback }">
    <div class="parse-head">
      <div class="parse-title">
        <div class="ea-section-title">新建升级任务</div>
        <h3>
          通知解析
          <span v-if="hasFeedback" class="parse-badge" :class="filled && !unfilled ? 'ok' : 'warn'">
            {{ filled && !unfilled ? '已回填' : filled ? '部分回填' : '未回填' }}
          </span>
        </h3>
      </div>
      <NButton type="primary" secondary size="small" :loading="processing" @click="$emit('parse-and-apply')">
        解析并应用
      </NButton>
    </div>

    <div class="parse-main" :class="{ 'with-feedback': hasFeedback }">
      <div class="ea-field notice-field">
        <label>通知内容</label>
        <NInput
          class="notice-input"
          type="textarea"
          :value="noticeText"
          :autosize="{ minRows: 3, maxRows: 3 }"
          placeholder="例如：7月基线升级 GEN99-V V11.35"
          @update:value="$emit('update:noticeText', $event)"
        />
      </div>

      <div v-if="hasFeedback && parseFeedback" class="parse-feedback" :class="parseFeedback.tone">
        <div class="feedback-title">{{ parseFeedback.title }}</div>
        <div class="feedback-cols">
          <div v-if="parseFeedback.successes.length" class="feedback-col ok">
            <div class="col-label">已识别 / 已回填</div>
            <div v-for="item in parseFeedback.successes" :key="`ok-${item}`" class="feedback-line">{{ item }}</div>
          </div>
          <div v-if="parseFeedback.failures.length" class="feedback-col warn">
            <div class="col-label">未识别 / 未回填</div>
            <div v-for="item in parseFeedback.failures" :key="`fail-${item}`" class="feedback-line">{{ item }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.parse-card {
  flex: 0 0 auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 148px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--line);

  &.has-feedback {
    min-height: 200px;
  }
}

.parse-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  flex: 0 0 auto;
}

.parse-title {
  h3 {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    margin: 0;
    font-size: 16px;
    font-weight: 700;
    color: var(--head);
  }
}

.parse-badge {
  flex: 0 0 auto;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 999px;

  &.ok {
    color: var(--ok-fg, #16a34a);
    background: color-mix(in srgb, var(--ok-fg, #16a34a) 14%, transparent);
  }

  &.warn {
    color: var(--amber-fg, #b45309);
    background: color-mix(in srgb, var(--amber-fg, #b45309) 14%, transparent);
  }
}

.parse-main {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
  flex: 1;
  min-height: 0;

  &.with-feedback {
    grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
    align-items: stretch;
  }
}

.notice-field {
  min-width: 0;
  margin: 0;

  label {
    margin-bottom: 6px;
    font-size: 12px;
  }
}

.notice-input {
  min-width: 0;

  :deep(textarea) {
    min-height: 72px !important;
  }
}

.parse-feedback {
  min-width: 0;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--line);
  background: var(--bg);
  overflow: auto;
  max-height: 120px;

  &.success {
    border-color: color-mix(in srgb, var(--ok-fg, #16a34a) 28%, var(--line));
    background: color-mix(in srgb, var(--ok-fg, #16a34a) 8%, var(--bg));
  }

  &.warning {
    border-color: color-mix(in srgb, var(--amber-fg, #b45309) 28%, var(--line));
    background: color-mix(in srgb, var(--amber-fg, #b45309) 8%, var(--bg));
  }
}

.feedback-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--head);
  margin-bottom: 6px;
}

.feedback-cols {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 8px 12px;
}

.feedback-col {
  &.ok .col-label {
    color: var(--ok-fg, #16a34a);
  }

  &.warn .col-label {
    color: var(--amber-fg, #b45309);
  }
}

.col-label {
  font-size: 11px;
  font-weight: 700;
  margin-bottom: 2px;
}

.feedback-line {
  font-size: 12px;
  line-height: 1.4;
  color: var(--text);
  word-break: break-word;
}

@media (max-width: 960px) {
  .parse-main.with-feedback {
    grid-template-columns: 1fr;
  }

  .parse-feedback {
    max-height: 100px;
  }
}
</style>
