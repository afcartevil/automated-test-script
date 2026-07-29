<script setup lang="ts">
import { computed, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { NModal, useMessage } from "naive-ui";
import { useAppStore } from "@/stores/hermes/app";
import ModelSelector from "./ModelSelector.vue";
import ProfileSelector from "./ProfileSelector.vue";
import ThemeSwitch from "./ThemeSwitch.vue";
import { changelog } from "@/data/changelog";

const message = useMessage();
const route = useRoute();
const router = useRouter();
const appStore = useAppStore();
const selectedKey = computed(() => route.name as string);
const logoPath = '/logo.png';
const showChangelog = ref(false);

// 核心功能入口（6项）
const coreItems = [
  {
    name: 'tahp.bug-analysis',
    label: '智能诊断',
    color: '#d03050',
    icon: `<path d="M12 9c-1.6-.6-3.2-.9-4-.9C5 8.1 3 10 3 12s2 3.9 5 3.9c.8 0 2.4-.3 4-.9"/>
           <path d="M12 9c1.6-.6 3.2-.9 4-.9 3 0 5 1.9 5 3.9s-2 3.9-5 3.9c-.8 0-2.4-.3-4-.9"/>
           <path d="M12 3v18"/>`,
  },
  {
    name: 'tahp.adapt-debug',
    label: 'AI适配调试',
    color: '#2080f0',
    icon: `<polygon points="5 3 19 12 5 21 5 3"/>`,
  },
  {
    name: 'tahp.pipeline',
    label: '适配流水线',
    color: '#5256d4',
    icon: `<rect x="3" y="5" width="6" height="14" rx="2"/>
           <rect x="11" y="5" width="6" height="14" rx="2"/>
           <rect x="19" y="5" width="2" height="14" rx="1"/>`,
  },
  {
    name: 'tahp.reports',
    label: '报告',
    color: '#18a058',
    icon: `<path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
           <polyline points="14 2 14 8 20 8"/>
           <line x1="16" y1="13" x2="8" y2="13"/>
           <line x1="16" y1="17" x2="8" y2="17"/>`,
  },
  {
    name: 'tahp.knowledge',
    label: '知识库',
    color: '#f0a020',
    icon: `<path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/>
           <path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/>`,
  },
  {
    name: 'hermes.skills',
    label: 'Skills库',
    color: '#722ed1',
    icon: `<polygon points="12 2 2 7 12 12 22 7 12 2"/>
           <polyline points="2 17 12 22 22 17"/>
           <polyline points="2 12 12 17 22 12"/>`,
  },
  {
    name: 'hermes.chat',
    label: '对话',
    color: '#13c2c2',
    icon: `<path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/>`,
  },
]

function handleNav(name: string) {
  router.push({ name });
}

function handleLogout() {
  localStorage.clear();
  router.replace({ name: 'login' });
}

async function handleUpdate() {
  const ok = await appStore.doUpdate();
  if (ok) {
    message.success('更新成功', { duration: 5000 });
  } else {
    message.error('更新失败');
  }
}

function handleReloadClient() {
  appStore.reloadClient();
}
</script>

<template>
  <aside class="sidebar" :class="{ open: appStore.sidebarOpen, collapsed: appStore.sidebarCollapsed }">
    <!-- Logo -->
    <div class="sidebar-logo" @click="router.push('/tahp/dashboard')">
      <img :src="logoPath" alt="EasyAdapter" class="logo-img" />
      <span class="logo-text">EasyAdapter</span>
    </div>

    <!-- 折叠按钮 -->
    <button class="collapse-btn" @click="appStore.toggleSidebarCollapsed()" title="折叠/展开">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline v-if="appStore.sidebarCollapsed" points="9 18 15 12 9 6" />
        <polyline v-else points="15 18 9 12 15 6" />
      </svg>
    </button>

    <!-- 核心功能导航 -->
    <nav class="sidebar-nav">
      <div class="nav-section-label">核心功能</div>
      <button
        v-for="item in coreItems"
        :key="item.name"
        class="nav-item"
        :class="{ active: selectedKey === item.name }"
        :title="item.label"
        @click="handleNav(item.name)"
      >
        <span class="nav-icon" :style="{ color: selectedKey === item.name ? item.color : '' }">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <g v-html="item.icon" />
          </svg>
        </span>
        <span class="nav-label">{{ item.label }}</span>
        <span v-if="selectedKey === item.name" class="active-indicator" :style="{ background: item.color }" />
      </button>
    </nav>

    <!-- 底部 -->
    <ProfileSelector />
    <ModelSelector />

    <div class="sidebar-footer">
      <button class="nav-item logout-item" @click="handleLogout">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4" />
          <polyline points="16 17 21 12 16 7" />
          <line x1="21" y1="12" x2="9" y2="12" />
        </svg>
        <span>退出登录</span>
      </button>
      <div class="footer-row">
        <div class="status-indicator" :class="{ connected: appStore.connected, disconnected: !appStore.connected }">
          <span class="status-dot" />
          <span class="status-text">{{ appStore.connected ? '已连接' : '未连接' }}</span>
        </div>
        <ThemeSwitch />
      </div>
      <div class="version-row">
        <span class="version-text" @click="showChangelog = true">v{{ appStore.serverVersion || '0.1.0' }}</span>
      </div>
      <NButton v-if="appStore.clientOutdated" type="warning" size="tiny" block class="update-btn" @click="handleReloadClient">
        重载客户端 {{ appStore.serverVersion }}
      </NButton>
      <NButton v-if="appStore.updateAvailable" type="primary" size="tiny" block class="update-btn" :loading="appStore.updating" @click="handleUpdate">
        {{ appStore.updating ? '更新中...' : `更新至 ${appStore.latestVersion}` }}
      </NButton>
    </div>

    <!-- Changelog -->
    <NModal v-model:show="showChangelog" preset="dialog" title="更新日志" style="width: 520px;">
      <div class="changelog-list">
        <div v-for="entry in changelog" :key="entry.version" class="changelog-block">
          <div class="changelog-header">
            <span class="changelog-version">v{{ entry.version }}</span>
            <span class="changelog-date">{{ entry.date }}</span>
          </div>
          <ul class="changelog-changes">
            <li v-for="(change, idx) in entry.changes" :key="idx">{{ change }}</li>
          </ul>
        </div>
      </div>
    </NModal>
  </aside>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.sidebar {
  position: relative;
  width: $sidebar-width;
  height: calc(100 * var(--vh));
  background-color: $bg-sidebar;
  border-right: 1px solid $border-color;
  display: flex;
  flex-direction: column;
  padding: 0 10px 16px;
  flex-shrink: 0;
  transition: width $transition-normal;
}

// Logo
.logo-img { width: 28px; height: 28px; flex-shrink: 0; }
.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 10px 16px;
  margin: 0 -10px;
  cursor: pointer;
  background-color: $bg-card;
  box-shadow: 0 2px 8px rgba(0,0,0,.08);
  .dark & { background-color: #393939; }
  .logo-text { font-size: 18px; font-weight: 700; letter-spacing: 0.5px; color: $text-primary; }
}

// Collapse button
.collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  background: none;
  color: $text-muted;
  border-radius: $radius-sm;
  cursor: pointer;
  transition: all $transition-fast;
  position: absolute;
  top: 18px;
  right: 14px;
  z-index: 5;
  &:hover { color: $text-primary; background: rgba(var(--accent-primary-rgb), 0.08); }
}

// Nav
.sidebar-nav {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding-top: 16px;
  overflow-y: auto;
  min-height: 0;
  scrollbar-width: none;
  &::-webkit-scrollbar { display: none; }
}

.nav-section-label {
  font-size: 10px;
  font-weight: 600;
  color: $text-muted;
  text-transform: uppercase;
  letter-spacing: 0.8px;
  padding: 0 10px 8px;
}

.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 10px;
  border: none;
  background: none;
  color: $text-secondary;
  font-size: 13px;
  font-weight: 500;
  border-radius: $radius-sm;
  cursor: pointer;
  transition: all $transition-fast;
  width: 100%;
  text-align: left;

  .nav-icon {
    display: flex;
    align-items: center;
    flex-shrink: 0;
    transition: color $transition-fast;
  }

  .nav-label { flex: 1; }

  .active-indicator {
    position: absolute;
    right: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 3px;
    height: 20px;
    border-radius: 2px;
  }

  &:hover {
    background: rgba(var(--accent-primary-rgb), 0.06);
    color: $text-primary;
  }

  &.active {
    background: rgba(var(--accent-primary-rgb), 0.10);
    color: $text-primary;
    font-weight: 600;
  }
}

// Footer
:deep(.profile-selector) {
  padding-top: 10px;
  border-top: 1px solid $border-color;
}

.sidebar-footer {
  padding-top: 8px;
  border-top: 1px solid $border-color;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.logout-item {
  margin: 0 -10px;
  padding: 10px;
  border-radius: 0;
  font-size: 13px;
  color: $text-muted;
  &:hover { color: $error; background: rgba(var(--error-rgb, 239,68,68), 0.06); }
}

.footer-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  .status-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
  &.connected .status-dot { background: $success; box-shadow: 0 0 5px rgba(var(--success-rgb),.5); }
  &.disconnected .status-dot { background: $error; }
  .status-text { color: $text-secondary; }
}

.version-row {
  padding: 2px 10px 6px;
  display: flex;
  justify-content: flex-start;
}
.version-text {
  font-size: 11px;
  color: $text-muted;
  cursor: pointer;
  &:hover { color: $accent-primary; }
}

.update-btn { margin: 4px 0 0; border-radius: 4px; }

// Changelog
.changelog-list { max-height: 400px; overflow-y: auto; }
.changelog-block { margin-bottom: 18px; &:last-child { margin-bottom: 0; } }
.changelog-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.changelog-version { font-weight: 600; font-size: 14px; color: $text-primary; }
.changelog-date { font-size: 12px; color: $text-muted; }
.changelog-changes {
  list-style: none; padding: 0; margin: 0;
  li { font-size: 13px; color: $text-secondary; padding: 3px 0 3px 14px; position: relative;
    &::before { content: ''; position: absolute; left: 0; top: 11px; width: 5px; height: 5px; border-radius: 50%; background: $text-muted; }
  }
}

// ── Collapsed ─────────────────────────────────────────────────
.sidebar.collapsed {
  width: $sidebar-collapsed-width;
  padding: 0 6px 12px;
  overflow: hidden;

  .sidebar-logo {
    padding: 12px 0 8px;
    margin: 0 -6px;
    justify-content: center;
    gap: 0;
    .logo-text { display: none; }
  }

  .collapse-btn { position: static; margin: 4px auto 0; display: flex; }

  .nav-section-label { display: none; }

  .nav-item {
    justify-content: center;
    padding: 10px 4px;
    gap: 0;
    .nav-label { display: none; }
    .active-indicator { display: none; }
  }

  :deep(.model-selector) { display: none; }
  :deep(.profile-selector) {
    display: flex; justify-content: center; padding: 8px 0; margin: 0 0 6px;
    border-top: 1px solid $border-color;
    .selector-label, .profile-name { display: none; }
    .profile-display { width: 36px; height: 36px; justify-content: center; padding: 0; gap: 0; border: none; border-radius: 0; background: transparent; }
    .profile-avatar { width: 28px !important; height: 28px !important; flex-basis: 28px !important; }
  }

  .sidebar-footer {
    .logout-item { margin: 0; padding: 10px 4px; border-radius: $radius-sm; span { display: none; } }
    .footer-row { justify-content: center; :deep(.input-sm) { display: none; } }
    .status-text, .version-row { display: none; }
    :deep(.theme-switch-container) { flex-direction: column; }
  }
}

// ── Mobile ─────────────────────────────────────────────────────
@media (max-width: $breakpoint-mobile) {
  .sidebar {
    position: fixed; left: 0; top: 0; z-index: 1000;
    transform: translateX(-100%); transition: transform $transition-normal;
    &.open { transform: translateX(0); }
  }
}
</style>
