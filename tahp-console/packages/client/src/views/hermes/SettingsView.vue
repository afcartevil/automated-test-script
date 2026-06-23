<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRoute } from "vue-router";
import {
  NTabs,
  NTabPane,
  NSpin,
} from "naive-ui";
import { useI18n } from "vue-i18n";
import { useSettingsStore } from "@/stores/hermes/settings";
import DisplaySettings from "@/components/hermes/settings/DisplaySettings.vue";
import AgentSettings from "@/components/hermes/settings/AgentSettings.vue";
import CompressionSettings from "@/components/hermes/settings/CompressionSettings.vue";
import SessionSettings from "@/components/hermes/settings/SessionSettings.vue";
import PrivacySettings from "@/components/hermes/settings/PrivacySettings.vue";
import ModelSettings from "@/components/hermes/settings/ModelSettings.vue";
import AccountSettings from "@/components/hermes/settings/AccountSettings.vue";
import GerritSettings from "@/components/tahp/settings/GerritSettings.vue";
import EaPageHead from "@/components/layout/EaPageHead.vue";

const settingsStore = useSettingsStore();
const { t } = useI18n();
const route = useRoute();
const activeTab = ref("account");

onMounted(() => {
  settingsStore.fetchSettings();
  const tab = String(route.query.tab || "").trim();
  if (tab) activeTab.value = tab;
});
</script>

<template>
  <div class="page settings-view">
    <EaPageHead :title="t('settings.title')" />

    <div class="settings-content">
      <NSpin
        :show="settingsStore.loading || settingsStore.saving"
        size="large"
        :description="t('common.loading')"
      >
        <NTabs v-model:value="activeTab" type="line" animated>
          <NTabPane name="account" :tab="t('settings.tabs.account')">
            <AccountSettings />
          </NTabPane>
          <NTabPane name="display" :tab="t('settings.tabs.display')">
            <DisplaySettings />
          </NTabPane>
          <NTabPane name="agent" :tab="t('settings.tabs.agent')">
            <AgentSettings />
          </NTabPane>
          <NTabPane name="compression" :tab="t('settings.tabs.compression')">
            <CompressionSettings />
          </NTabPane>
          <NTabPane name="session" :tab="t('settings.tabs.session')">
            <SessionSettings />
          </NTabPane>
          <NTabPane name="privacy" :tab="t('settings.tabs.privacy')">
            <PrivacySettings />
          </NTabPane>
          <NTabPane name="models" :tab="t('settings.tabs.models')">
            <ModelSettings />
          </NTabPane>
          <NTabPane name="gerrit" tab="Gerrit 账号">
            <GerritSettings />
          </NTabPane>
        </NTabs>
      </NSpin>
    </div>
  </div>
</template>

<style scoped lang="scss">
@use "@/styles/variables" as *;

.settings-view {
  height: calc(100 * var(--vh));
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.settings-content {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
}
</style>
