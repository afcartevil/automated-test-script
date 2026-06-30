<script setup lang="ts">
import { onMounted, onActivated } from 'vue'
import { RouterLink } from 'vue-router'
import { NButton, NCheckbox, NScrollbar, NSpin, NEmpty } from 'naive-ui'
import MarkdownRenderer from '@/components/hermes/chat/MarkdownRenderer.vue'
import ModelProviderBanner from '@/components/tahp/ModelProviderBanner.vue'
import EaCard from '@/components/layout/EaCard.vue'
import { useGerritReviewWorkspace } from '@/composables/useGerritReviewWorkspace'

const {
  GERRIT_NOT_CONFIGURED_MSG,
  chatMessages,
  streamingText,
  isRunning,
  sending,
  stopping,
  inputText,
  gerritConfigured,
  thinkingLines,
  thinkingScrollRef,
  scrollRef,
  textareaRef,
  latestPhase,
  latestSkillUse,
  p0Result,
  modulesResult,
  recommendedCases,
  checkedRecommendedCount,
  p0Count,
  recommendedCount,
  loadingRecommendations,
  toggleRecommendedCase,
  setRecommendedCaseChecked,
  handleStartRecommendedTest,
  handleRefreshRecommend,
  handleTextareaInput,
  handleSend,
  handleStop,
  handleCompositionStart,
  handleCompositionEnd,
  handleKeydown,
  restoreWorkspace,
} = useGerritReviewWorkspace()
void [thinkingScrollRef, scrollRef, textareaRef, toggleRecommendedCase]

onMounted(restoreWorkspace)
onActivated(restoreWorkspace)
</script>

<template>
  <div class="gerrit-workspace-root">
    <ModelProviderBanner />

    <EaCard class="review-card">
      <div class="review-card-head">
        <div class="review-card-head-row">
          <h3>Gerrit Code Review</h3>
          <span v-if="isRunning" class="phase-hint">
            {{ latestPhase || latestSkillUse || 'Agent 评审中…' }}
          </span>
        </div>
        <p v-if="!gerritConfigured" class="gerrit-config-warning">
          {{ GERRIT_NOT_CONFIGURED_MSG }}
          <RouterLink class="gerrit-settings-link" to="/hermes/settings?tab=gerrit">
            去设置
          </RouterLink>
        </p>
      </div>

      <div class="review-workspace">
        <div class="panel chat-panel">
          <div class="panel-title">Code Review 对话</div>
          <NScrollbar ref="scrollRef" class="chat-scroll">
            <div v-if="chatMessages.length === 0" class="chat-empty">
              <p class="ea-muted">输入 Gerrit 链接或 topic 开始评审，例如：</p>
              <code class="example-link">https://gerrit.transsion.com/c/MTK_CODE/quark/kernel-5.15/+/1543793</code>
            </div>
            <div
              v-for="msg in chatMessages"
              :key="msg.id"
              class="chat-row"
              :class="msg.role"
            >
              <div class="bubble">
                <template v-if="msg.role === 'user'">{{ msg.content }}</template>
                <template v-else-if="msg.streaming && !streamingText">
                  <div class="thinking-panel">
                    <div class="thinking-title">
                      <NSpin size="small" />
                      <span>Gerrit 评审中</span>
                    </div>
                    <div ref="thinkingScrollRef" class="thinking-scroll">
                      <div
                        v-for="(line, idx) in thinkingLines"
                        :key="`${idx}-${line.slice(0, 24)}`"
                        class="thinking-line"
                      >
                        {{ line }}
                      </div>
                      <div v-if="!thinkingLines.length" class="thinking-line ea-muted">
                        等待 Agent 响应…
                      </div>
                    </div>
                  </div>
                </template>
                <MarkdownRenderer
                  v-else
                  :content="msg.streaming ? streamingText : msg.content"
                />
              </div>
            </div>
          </NScrollbar>

          <div class="chat-input-area">
            <div class="input-wrapper">
              <textarea
                ref="textareaRef"
                v-model="inputText"
                class="input-textarea"
                placeholder="Gerrit 链接、topic URL 或追问…"
                rows="1"
                :disabled="isRunning"
                @input="handleTextareaInput"
                @keydown="handleKeydown"
                @compositionstart="handleCompositionStart"
                @compositionend="handleCompositionEnd"
              />
              <div class="input-actions">
                <NButton
                  v-if="isRunning"
                  size="small"
                  type="error"
                  :disabled="stopping"
                  @click="handleStop"
                >
                  停止
                </NButton>
                <NButton
                  size="small"
                  type="primary"
                  :disabled="!inputText.trim() || isRunning || !gerritConfigured"
                  @click="handleSend"
                >
                  <template #icon>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
                  </template>
                  发送
                </NButton>
              </div>
            </div>
          </div>
        </div>

        <div class="panel p0-panel">
          <div class="panel-title">AI 测试建议</div>
          <div class="panel-subtitle module-subtitle">
            模块：{{ modulesResult.display }}
          </div>

          <div class="insight-body">
            <div
              v-if="isRunning && !p0Count && !recommendedCount"
              class="p0-loading"
            >
              <NSpin size="medium" />
              <p class="ea-muted">评审进行中，完成后自动提取测试建议…</p>
            </div>
            <template v-else>
              <div class="insight-section p0-section">
                <div class="section-title section-title-bold">
                  必须测试 · {{ p0Count }}
                </div>
                <NScrollbar class="section-scroll">
                  <template v-if="p0Count">
                    <ol class="p0-list">
                      <li v-for="(item, i) in p0Result.items" :key="i">
                        <MarkdownRenderer :content="item" />
                      </li>
                    </ol>
                  </template>
                  <NEmpty
                    v-else
                    description="未提取到必须测试项"
                    size="small"
                  />
                </NScrollbar>
              </div>

              <div class="insight-section recommended-section">
                <div class="section-title">
                  推荐测试用例 · {{ recommendedCount }}
                </div>
                <NScrollbar class="section-scroll">
                  <div
                    v-if="loadingRecommendations"
                    class="recommend-loading"
                  >
                    <NSpin size="small" />
                    <p class="ea-muted">AI 正在分析必须测试项，生成推荐用例…</p>
                  </div>
                  <NEmpty
                    v-else-if="!recommendedCount"
                    description="暂无推荐用例，请完成评审或点击重新推荐"
                    size="small"
                  />
                  <ul v-else class="recommended-list">
                    <li v-for="item in recommendedCases" :key="item.caseKey">
                      <NCheckbox
                        :checked="item.checked"
                        @update:checked="(checked: boolean) => setRecommendedCaseChecked(item.caseKey, checked)"
                      />
                      <div class="recommended-item-body">
                        <div class="recommended-item-name">{{ item.caseName }}</div>
                        <div class="recommended-item-meta ea-muted">
                          {{ item.caseKey }} · {{ item.moduleLabel }}
                        </div>
                      </div>
                    </li>
                  </ul>
                </NScrollbar>
              </div>
            </template>
          </div>

          <div class="insight-footer">
            <NButton
              type="primary"
              size="small"
              :disabled="checkedRecommendedCount === 0"
              @click="handleStartRecommendedTest"
            >
              开始测试（{{ checkedRecommendedCount }}）
            </NButton>
            <NButton
              size="small"
              :disabled="!p0Count || isRunning"
              :loading="loadingRecommendations"
              @click="handleRefreshRecommend"
            >
              重新推荐
            </NButton>
          </div>
        </div>
      </div>
    </EaCard>
  </div>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

$gerrit-action-inner-min: 48px;
$gerrit-bottom-bar-min: calc(10px + 12px + #{$gerrit-action-inner-min});

.gerrit-workspace-root {
  margin-top: 24px;
}

.review-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 16px 18px;
}

.review-card-head {
  margin-bottom: 12px;
}

.review-card-head-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  h3 {
    font-size: 15px;
    font-weight: 700;
    margin: 0;
  }
}

.gerrit-config-warning {
  margin: 8px 0 0;
  font-size: 13px;
  color: var(--error);
  line-height: 1.5;
}

.gerrit-settings-link {
  margin-left: 6px;
  color: var(--accent);
  text-decoration: none;
  &:hover {
    text-decoration: underline;
  }
}

.phase-hint {
  font-size: 12px;
  color: var(--muted);
}

.review-workspace {
  height: calc((50vh - 40px) * 4 / 3);
  min-height: 480px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}

.panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--bg);
  overflow: hidden;
}

.panel-title {
  font-size: 13px;
  font-weight: 700;
  padding: 10px 14px;
  border-bottom: 1px solid var(--line);
  background: var(--surface);
}

.panel-subtitle {
  font-size: 11.5px;
  color: var(--muted);
  padding: 4px 14px 8px;
  border-bottom: 1px dashed var(--line);
  background: var(--surface);
}

.module-subtitle {
  border-bottom: none;
  padding-bottom: 4px;
}

.module-hint {
  margin-left: 4px;
  font-size: 11px;
}

.chat-panel {
  .chat-scroll {
    flex: 1;
    min-height: 0;
    padding: 12px 14px;
  }
}

.p0-panel {
  .insight-body {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 10px 12px;
    overflow: hidden;
  }

  .insight-section {
    min-height: 0;
    display: flex;
    flex-direction: column;
    border: 1px solid var(--line);
    border-radius: 10px;
    background: var(--surface);
    overflow: hidden;
  }

  .p0-section {
    flex: 0.85;
  }

  .recommended-section {
    flex: 1;
    min-height: 0;
  }

  .section-title {
    flex-shrink: 0;
    font-size: 12px;
    font-weight: 600;
    padding: 8px 12px;
    border-bottom: 1px dashed var(--line);
    background: color-mix(in srgb, var(--surface) 92%, var(--bg));
  }

  .section-title-bold {
    font-weight: 700;
  }

  .section-scroll {
    flex: 1;
    min-height: 0;
    padding: 10px 12px;
  }

  .insight-footer {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 8px;
    min-height: $gerrit-bottom-bar-min;
    padding: 10px 12px 12px;
    border-top: 1px solid var(--line);
    background: var(--surface);
    box-sizing: border-box;

    :deep(.n-button) {
      height: 28px;
      padding: 0 14px;
      font-size: 14px;
    }
  }
}

.chat-empty {
  padding: 24px 8px;
  text-align: center;
  .example-link {
    display: block;
    margin-top: 10px;
    font-size: 11.5px;
    word-break: break-all;
    color: var(--accent);
    font-family: 'JetBrains Mono', monospace;
  }
}

.chat-row {
  display: flex;
  margin-bottom: 12px;
  &.user { justify-content: flex-end; }
  &.assistant { justify-content: flex-start; }
}

.bubble {
  max-width: 92%;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.55;
  border: 1px solid var(--line);
}

.chat-row.user .bubble {
  background: color-mix(in srgb, var(--accent) 12%, var(--surface));
  border-color: color-mix(in srgb, var(--accent) 25%, var(--line));
}

.chat-row.assistant .bubble {
  background: var(--surface);
}

.chat-input-area {
  padding: 10px 12px 12px;
  border-top: 1px solid var(--line);
  background: var(--surface);
  flex-shrink: 0;
  min-height: $gerrit-bottom-bar-min;
  box-sizing: border-box;
  display: flex;
  align-items: center;
}

.input-wrapper {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-height: $gerrit-action-inner-min;
  background-color: $bg-input;
  border: 1px solid $border-color;
  border-radius: $radius-md;
  padding: 10px 12px;
  transition: border-color $transition-fast, background-color $transition-fast;
  box-sizing: border-box;

  &:focus-within {
    border-color: $accent-primary;
  }

  .dark & {
    background-color: #333333;
  }

  :deep(.n-button) {
    height: 28px;
    padding: 0 14px;
    font-size: 14px;
  }
}

.input-textarea {
  flex: 1;
  min-width: 0;
  background: none;
  border: none;
  outline: none;
  color: $text-primary;
  font-family: $font-ui;
  font-size: 14px;
  line-height: 1.5;
  resize: none;
  max-height: 100px;
  min-height: 20px;
  overflow-y: auto;

  &::placeholder {
    color: $text-muted;
  }

  &:disabled {
    opacity: 0.65;
    cursor: not-allowed;
  }
}

.input-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
  align-items: center;
}

.thinking-panel {
  min-width: 260px;
}

.thinking-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 8px;
}

.thinking-scroll {
  height: calc(1.45em * 5 + 8px);
  overflow-y: auto;
  overflow-x: hidden;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--bg);
  border: 1px dashed var(--line);
  scroll-behavior: smooth;
}

.thinking-line {
  font-size: 12px;
  line-height: 1.45;
  color: var(--muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  padding: 1px 0;
  animation: thinking-fade-in 0.25s ease;
}

@keyframes thinking-fade-in {
  from { opacity: 0.4; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

.p0-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 32px 16px;
  text-align: center;
}

.recommend-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  min-height: 120px;
  padding: 24px 12px;
  text-align: center;

  p {
    margin: 0;
    font-size: 12px;
    line-height: 1.5;
  }
}

.p0-list {
  margin: 0;
  padding-left: 1.2em;
  li {
    margin-bottom: 12px;
    font-size: 13px;
    line-height: 1.55;
  }
}

.p0-raw {
  margin-top: 16px;
  font-size: 12px;
  summary {
    cursor: pointer;
    color: var(--muted);
    margin-bottom: 8px;
  }
}

.recommended-section {
  margin-top: 0;
  padding-top: 0;
  border-top: none;
}

.recommended-list {
  margin: 0;
  padding: 0;
  list-style: none;

  li {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    margin: 0 0 10px 2px;
  }
}

.recommended-item-body {
  flex: 1;
  min-width: 0;
}

.recommended-item-name {
  font-size: 13px;
  line-height: 1.45;
}

.recommended-item-meta {
  font-size: 11px;
  margin-top: 2px;
}

@media (max-width: 900px) {
  .review-workspace {
    grid-template-columns: 1fr;
    height: auto;
    min-height: 693px;
  }
  .panel {
    min-height: 320px;
  }
}
</style>
