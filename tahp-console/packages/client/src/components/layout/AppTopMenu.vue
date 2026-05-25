<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const selectedKey = computed(() => route.name as string)

function nav(name: string) {
  router.push({ name })
}

const groups = [
  {
    key: 'tahp',
    label: 'TAHP',
    items: [
      { name: 'tahp.dashboard', label: '仪表盘', icon: 'M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z' },
      { name: 'tahp.tasks',     label: '任务列表', icon: 'M9 11l3 3L22 4M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11' },
      { name: 'tahp.modules',   label: '模块矩阵', icon: 'M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z' },
      { name: 'tahp.playbooks', label: 'Playbooks', icon: 'M22 12l-4-4-8 9-3-3M2 12h4' },
      { name: 'tahp.reports',   label: '报告', icon: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6M16 13H8M16 17H8M10 9H8' },
    ],
  },
  {
    key: 'system',
    label: '系统',
    items: [
      { name: 'hermes.models',   label: '模型管理', icon: 'M12 2a10 10 0 100 20A10 10 0 0012 2zM2 12h20M12 2a15.3 15.3 0 010 20M12 2a15.3 15.3 0 000 20' },
      { name: 'hermes.history',  label: '历史记录', icon: 'M12 2a10 10 0 100 20A10 10 0 0012 2zM12 6v6l4 2' },
      { name: 'hermes.logs',     label: '日志', icon: 'M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8zM14 2v6h6M16 13H8M16 17H8' },
      { name: 'hermes.terminal', label: '终端', icon: 'M4 17l6-6-6-6M12 19h8' },
      { name: 'hermes.files',    label: '文件', icon: 'M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z' },
      { name: 'hermes.settings', label: '设置', icon: 'M12 15a3 3 0 100-6 3 3 0 000 6zM19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z' },
    ],
  },
]
</script>

<template>
  <nav class="top-menu">
    <div class="top-menu-inner">
      <template v-for="(group, gi) in groups" :key="group.key">
        <div v-if="gi > 0" class="group-divider" />
        <div class="group-label">{{ group.label }}</div>
        <button
          v-for="item in group.items"
          :key="item.name"
          class="menu-item"
          :class="{ active: selectedKey === item.name }"
          @click="nav(item.name)"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path :d="item.icon" />
          </svg>
          <span>{{ item.label }}</span>
        </button>
      </template>
    </div>
  </nav>
</template>

<style scoped lang="scss">
@use '@/styles/variables' as *;

.top-menu {
  height: 40px;
  border-bottom: 1px solid $border-color;
  background: $bg-sidebar;
  flex-shrink: 0;
  overflow: hidden;
}

.top-menu-inner {
  display: flex;
  align-items: center;
  height: 100%;
  padding: 0 12px;
  gap: 2px;
  overflow-x: auto;
  scrollbar-width: none;
  &::-webkit-scrollbar { display: none; }
}

.group-label {
  font-size: 10px;
  font-weight: 600;
  color: $text-muted;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  padding: 0 6px;
  white-space: nowrap;
  flex-shrink: 0;
}

.group-divider {
  width: 1px;
  height: 18px;
  background: $border-color;
  margin: 0 6px;
  flex-shrink: 0;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border: none;
  background: none;
  color: $text-secondary;
  font-size: 12px;
  border-radius: $radius-sm;
  cursor: pointer;
  transition: all $transition-fast;
  white-space: nowrap;
  flex-shrink: 0;

  &:hover {
    background: rgba(var(--accent-primary-rgb), 0.08);
    color: $text-primary;
  }

  &.active {
    background: rgba(var(--accent-primary-rgb), 0.14);
    color: $accent-primary;
    font-weight: 500;
  }
}
</style>
