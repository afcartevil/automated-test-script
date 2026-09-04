<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ChatPanel from '@/components/hermes/chat/ChatPanel.vue'
import { useAppStore } from '@/stores/hermes/app'
import { useChatStore } from '@/stores/hermes/chat'
import { useProfilesStore } from '@/stores/hermes/profiles'
import { useSettingsStore } from '@/stores/hermes/settings'
import {
  HERMES_CHAT_ROUTE,
  hasHermesChatFreshQuery,
  withoutHermesChatFreshQuery,
} from '@/utils/chat-navigation'

const route = useRoute()
const router = useRouter()
const appStore = useAppStore()
const chatStore = useChatStore()
const profilesStore = useProfilesStore()
const settingsStore = useSettingsStore()

async function startFreshChatIfRequested() {
  if (!hasHermesChatFreshQuery(route.query)) return
  await chatStore.newChat()
  await router.replace({
    name: HERMES_CHAT_ROUTE,
    query: withoutHermesChatFreshQuery(route.query),
  })
}

onMounted(async () => {
  appStore.loadModels()
  // 先加载 profile，确保缓存 key 使用正确的 profile name；同时预取显示设置，
  // 让聊天完成提示音不依赖用户先打开 Settings 页面。
  await Promise.all([
    profilesStore.fetchProfiles(),
    settingsStore.fetchSettings(),
  ])
  if (hasHermesChatFreshQuery(route.query)) {
    await startFreshChatIfRequested()
    void chatStore.loadSessions(undefined, { activate: false })
    return
  }
  await chatStore.loadSessions()
})

watch(
  () => route.query.fresh,
  async (fresh, previous) => {
    if (!fresh || fresh === previous) return
    await startFreshChatIfRequested()
  },
)
</script>

<template>
  <div class="chat-page">
    <div class="chat-wrap">
      <ChatPanel />
    </div>
  </div>
</template>

<style scoped lang="scss">
.chat-page {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  width: 100%;
  overflow: hidden;
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
  border-radius: 0;
  border: none;
  box-shadow: none;
}
</style>
