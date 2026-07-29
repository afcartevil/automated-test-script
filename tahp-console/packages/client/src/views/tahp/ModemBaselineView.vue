<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const navItems = [
  { name: 'tahp.modem-baseline.workbench', label: '工作台', icon: 'dashboard' },
  { name: 'tahp.modem-baseline.history', label: '运行历史', icon: 'database' },
  { name: 'tahp.modem-baseline.settings', label: '配置中心', icon: 'settings' },
]

const activeName = computed(() => route.name?.toString() || 'tahp.modem-baseline.workbench')

const SIDEBAR_COLLAPSED_KEY = 'ea_modem_baseline_sidebar_collapsed'
const sidebarCollapsed = ref(localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1')

function toggleSidebar() {
  sidebarCollapsed.value = !sidebarCollapsed.value
  localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebarCollapsed.value ? '1' : '0')
}

function nav(name: string) {
  router.push({ name })
}
</script>

<template>
  <div class="modem-shell" :class="{ collapsed: sidebarCollapsed }">
    <aside class="modem-sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="modem-sidebar-top">
        <button
          type="button"
          class="modem-collapse-btn"
          :title="sidebarCollapsed ? '展开导航' : '折叠导航'"
          @click="toggleSidebar"
        >
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            :class="{ 'is-flipped': sidebarCollapsed }"
          >
            <polyline points="15 18 9 12 15 6" />
          </svg>
        </button>
      </div>

      <nav class="modem-nav">
        <button
          v-for="item in navItems"
          :key="item.name"
          type="button"
          class="modem-nav-btn"
          :class="{ active: activeName === item.name }"
          :title="item.label"
          @click="nav(item.name)"
        >
          <span class="modem-nav-icon" :data-icon="item.icon" />
          <span class="modem-nav-label">{{ item.label }}</span>
        </button>
      </nav>
    </aside>

    <section class="modem-main">
      <div class="modem-main-body">
        <router-view />
      </div>
    </section>
  </div>
</template>

<style scoped lang="scss">
.modem-shell {
  display: grid;
  grid-template-columns: 220px minmax(0, 1fr);
  height: calc(100vh - 120px);
  min-height: calc(100vh - 120px);
  margin: -8px -28px -40px;
  background: var(--bg);

  &.collapsed {
    grid-template-columns: 64px minmax(0, 1fr);
  }
}

.modem-sidebar {
  display: flex;
  flex-direction: column;
  padding: 12px 10px 16px;
  border-right: 1px solid color-mix(in srgb, var(--sky-ic) 12%, var(--line));
  background: linear-gradient(180deg, var(--sky-bg) 0%, color-mix(in srgb, var(--sky-bg) 70%, var(--surface)) 100%);
  overflow: hidden;
  min-width: 0;

  &.collapsed {
    padding-inline: 8px;
  }
}

.modem-sidebar-top {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 10px;

  .collapsed & {
    justify-content: center;
  }
}

.modem-collapse-btn {
  width: 32px;
  height: 32px;
  border: 1px solid color-mix(in srgb, var(--sky-ic) 18%, var(--line));
  border-radius: 10px;
  background: color-mix(in srgb, var(--surface) 82%, var(--sky-bg));
  color: var(--sky-fg);
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: background 0.18s, border-color 0.18s, color 0.18s;

  &:hover {
    background: var(--surface);
    border-color: color-mix(in srgb, var(--sky-ic) 35%, var(--line));
    color: var(--accent);
  }

  svg {
    transition: transform 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  }

  svg.is-flipped {
    transform: rotate(180deg);
  }
}

.modem-nav {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.modem-nav-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 11px 14px;
  border: none;
  border-radius: 12px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font: inherit;
  font-size: 13.5px;
  font-weight: 600;
  text-align: left;
  transition: color 0.18s, background 0.18s;

  .collapsed & {
    justify-content: center;
    padding: 11px 8px;
  }

  &:hover {
    color: var(--sky-fg);
    background: color-mix(in srgb, var(--surface) 65%, var(--sky-bg));
  }

  &.active {
    color: var(--sky-fg);
    background: color-mix(in srgb, var(--surface) 88%, var(--sky-bg));
    box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--sky-ic) 22%, transparent);
    font-weight: 700;
  }
}

.modem-nav-label {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  opacity: 1;
  transform: translateX(0);
  transition:
    opacity 0.2s cubic-bezier(0.4, 0, 0.2, 1),
    transform 0.2s cubic-bezier(0.4, 0, 0.2, 1);

  .collapsed & {
    flex: 0;
    width: 0;
    opacity: 0;
    transform: translateX(-4px);
    pointer-events: none;
  }
}

.modem-nav-icon {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  opacity: 0.85;
}

.modem-nav-icon[data-icon='dashboard'] {
  background: currentColor;
  mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2'%3E%3Crect x='3' y='3' width='7' height='7' rx='1'/%3E%3Crect x='14' y='3' width='7' height='7' rx='1'/%3E%3Crect x='3' y='14' width='7' height='7' rx='1'/%3E%3Crect x='14' y='14' width='7' height='7' rx='1'/%3E%3C/svg%3E") center/contain no-repeat;
}

.modem-nav-icon[data-icon='database'] {
  background: currentColor;
  mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2'%3E%3Cellipse cx='12' cy='5' rx='9' ry='3'/%3E%3Cpath d='M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5'/%3E%3Cpath d='M3 12c0 1.66 4 3 9 3s9-1.34 9-3'/%3E%3C/svg%3E") center/contain no-repeat;
}

.modem-nav-icon[data-icon='settings'] {
  background: currentColor;
  mask: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2'%3E%3Ccircle cx='12' cy='12' r='3'/%3E%3Cpath d='M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z'/%3E%3C/svg%3E") center/contain no-repeat;
}

.modem-main {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 12px 16px 16px;
  overflow: hidden;
}

.modem-main-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modem-main-body > :deep(*) {
  flex: 1;
  min-height: 0;
}

@media (max-width: 900px) {
  .modem-shell {
    display: flex;
    flex-direction: column;

    &.collapsed {
      grid-template-columns: unset;
    }
  }

  .modem-main {
    padding: 12px 16px 16px;
  }

  .modem-sidebar {
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
    border-right: none;
    border-bottom: 1px solid color-mix(in srgb, var(--sky-ic) 12%, var(--line));
    padding: 12px 14px;

    &.collapsed {
      padding-inline: 14px;
    }
  }

  .modem-sidebar-top {
    margin-bottom: 0;
    margin-right: 8px;
  }

  .modem-nav {
    flex-direction: row;
    flex-wrap: wrap;
    flex: 1;
  }
}
</style>
