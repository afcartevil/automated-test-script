<script setup lang="ts">
import { onMounted } from 'vue'
import ChatPanel from '@/components/hermes/chat/ChatPanel.vue'
import EaPageHead from '@/components/layout/EaPageHead.vue'
import { useAppStore } from '@/stores/hermes/app'
import { useChatStore } from '@/stores/hermes/chat'
import { useProfilesStore } from '@/stores/hermes/profiles'
import { useSettingsStore } from '@/stores/hermes/settings'

const appStore = useAppStore()
const chatStore = useChatStore()
const profilesStore = useProfilesStore()
const settingsStore = useSettingsStore()

onMounted(async () => {
  appStore.loadModels()
  // 先加载 profile，确保缓存 key 使用正确的 profile name；同时预取显示设置，
  // 让聊天完成提示音不依赖用户先打开 Settings 页面。
  await Promise.all([
    profilesStore.fetchProfiles(),
    settingsStore.fetchSettings(),
  ])
  chatStore.loadSessions()
})
</script>

<template>
  <div class="page page-wide chat-page">
    <EaPageHead
      title="AI 对话"
      subtitle="在自由对话上下文中继续追问 / 产出补丁 / 沉淀知识（Agent + 完整 Skill）"
    />
    <div class="chat-wrap">
      <ChatPanel />
    </div>
  </div>
</template>

<style scoped lang="scss">
.chat-page {
  display: flex;
  flex-direction: column;
  height: calc(100 * var(--vh) - 100px);
  min-height: 0;
}

.chat-wrap {
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
}

.chat-wrap :deep(.chat-panel) {
  flex: 1;
  min-height: 0;
  width: 100%;
}
</style>
