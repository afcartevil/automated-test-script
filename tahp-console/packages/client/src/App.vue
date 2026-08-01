<script setup lang="ts">
import { onMounted, onUnmounted, computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NConfigProvider, NMessageProvider, NDialogProvider, NNotificationProvider } from 'naive-ui'
import { useI18n } from 'vue-i18n'
import { getThemeOverrides } from '@/styles/theme'
import EaShell from '@/components/layout/EaShell.vue'
import SkillConfigBanner from '@/components/tahp/SkillConfigBanner.vue'
import { useKeyboard } from '@/composables/useKeyboard'
import { useAppStore } from '@/stores/hermes/app'
import SessionSearchModal from '@/components/hermes/chat/SessionSearchModal.vue'

const { t } = useI18n()
const appStore = useAppStore()
const route = useRoute()
const router = useRouter()
const ready = ref(false)

const themeOverrides = computed(() => getThemeOverrides())
const isLoginPage = computed(() => route.name === 'login')

const nodeVersionLow = computed(() => {
  const v = appStore.nodeVersion
  const major = parseInt(v.split('.')[0], 10)
  return !isNaN(major) && major < 23
})

router.isReady().then(() => {
  ready.value = true
})

onMounted(() => {
  if (!isLoginPage.value) {
    appStore.loadModels()
    appStore.startHealthPolling()
  }
})

onUnmounted(() => {
  appStore.stopHealthPolling()
})

useKeyboard()
</script>

<template>
  <NConfigProvider :theme-overrides="themeOverrides">
    <NMessageProvider>
      <NDialogProvider>
        <NNotificationProvider>
          <div class="app-frame">
            <div v-if="nodeVersionLow && ready && !isLoginPage" class="global-warning-bar">
              {{ t('sidebar.nodeVersionWarning', { version: appStore.nodeVersion }) }}
            </div>
            <SkillConfigBanner v-if="ready && !isLoginPage" />
            <template v-if="ready">
              <router-view v-if="isLoginPage" />
              <EaShell v-else>
                <router-view />
              </EaShell>
            </template>
          </div>
          <SessionSearchModal />
        </NNotificationProvider>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>

<style scoped lang="scss">
.app-frame {
  height: calc(100 * var(--vh));
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.global-warning-bar {
  flex-shrink: 0;
  background: var(--warn-soft);
  color: var(--warn);
  text-align: center;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 600;
}
</style>
