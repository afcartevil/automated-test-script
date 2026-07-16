<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/hermes/app'
import { useTahpModulesStore } from '@/stores/tahp/modules'
import EaCard from '@/components/layout/EaCard.vue'

const router = useRouter()
const appStore = useAppStore()
const modulesStore = useTahpModulesStore()

const coreCards = [
  {
    route: 'tahp.adapt-debug',
    tone: 'ea-t-indigo',
    icon: 'play',
    title: 'AI 适配调试',
    summary: '把源版本的驱动 / 框架改动自动适配到目标版本，Agent 产出补丁与自检报告。',
    large: true,
  },
  {
    route: 'tahp.bug-analysis',
    tone: 'ea-t-sky',
    icon: 'stethoscope',
    title: '智能诊断',
    summary: '输入 JIRA Key 或日志，Agent 自动拉单、调 Skill、定位根因并给修复路径。',
  },
  {
    route: 'tahp.modem-baseline.workbench',
    tone: 'ea-t-amber',
    icon: 'branch',
    title: 'Modem基线',
    summary: 'Modem基线升级、Modem Patch自动化合入，自动编译烧录验证。',
  },
  {
    route: 'tahp.gki-patch.dashboard',
    tone: 'ea-t-violet',
    icon: 'kernel',
    title: 'GKI Patch',
    summary: 'GKI 内核 patch 区间分析、风险评估与 vendor 合入。',
  },
  {
    route: 'tahp.self-check',
    tone: 'ea-t-emerald',
    icon: 'shield',
    title: 'AI 自检',
    summary: '项目节点驱动，自动烧录、自动测试、AI Review，第二天人工复核报告',
  },
]

const heroCard = computed(() => coreCards[0])
const smallCards = computed(() => coreCards.slice(1))

const modelGroups = computed(() => {
  const groups = appStore.profileModelGroups[0]?.groups || []
  const items: { name: string; vendor: string; model: string; provider: string; badge?: string }[] = []
  for (const g of groups) {
    for (const m of g.models.slice(0, 4)) {
      items.push({
        name: appStore.displayModelName(m, g.provider),
        vendor: g.label,
        model: m,
        provider: g.provider,
        badge: g.model_meta?.[m]?.preview ? 'Preview' : undefined,
      })
      if (items.length >= 4) break
    }
    if (items.length >= 4) break
  }
  return items
})

onMounted(async () => {
  await Promise.all([modulesStore.refresh(), appStore.loadModels()])
})

function go(name: string) {
  router.push({ name })
}

function selectModel(model: string, provider: string) {
  appStore.switchModel(model, provider)
}

const currentModelName = computed(() =>
  appStore.displayModelName(appStore.selectedModel, appStore.selectedProvider),
)
</script>

<template>
  <div class="page">
    <button
      type="button"
      class="ea-hm-card hm-hero"
      :class="heroCard.tone"
      @click="go(heroCard.route)"
    >
      <span class="hm-icon hm-icon-lg">
        <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
      </span>
      <h2>{{ heroCard.title }}</h2>
      <p>{{ heroCard.summary }}</p>
    </button>

    <div class="hm-row">
      <button
        v-for="card in smallCards"
        :key="card.route"
        type="button"
        class="ea-hm-card hm-sm"
        :class="card.tone"
        @click="go(card.route)"
      >
        <span class="hm-icon">
          <svg v-if="card.icon === 'stethoscope'" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 9c-1.6-.6-3.2-.9-4-.9C5 8.1 3 10 3 12s2 3.9 5 3.9c.8 0 2.4-.3 4-.9"/>
            <path d="M12 9c1.6-.6 3.2-.9 4-.9 3 0 5 1.9 5 3.9s-2 3.9-5 3.9c-.8 0-2.4-.3-4-.9"/>
            <path d="M12 3v18"/>
          </svg>
          <svg v-else-if="card.icon === 'branch'" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M6 3v12"/>
            <path d="M6 9c4 0 4 6 8 6h4"/>
            <path d="M18 9v6"/>
            <circle cx="6" cy="3" r="2"/>
            <circle cx="6" cy="15" r="2"/>
            <circle cx="18" cy="9" r="2"/>
            <circle cx="18" cy="15" r="2"/>
          </svg>
          <svg v-else-if="card.icon === 'kernel'" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="4" y="4" width="16" height="16" rx="2"/>
            <rect x="9" y="9" width="6" height="6"/>
            <path d="M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2"/>
          </svg>
          <svg v-else width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
          </svg>
        </span>
        <h3>{{ card.title }}</h3>
        <p>{{ card.summary }}</p>
      </button>
    </div>

    <EaCard class="mdl-card">
      <div class="mdl-head">
        <div>
          <h3>模型选择</h3>
          <p>为 AI 适配 / 诊断 / 自检选择内置大模型</p>
        </div>
        <span class="mdl-current">当前：<b>{{ currentModelName || '—' }}</b></span>
      </div>
      <div class="mdl-grid">
        <button
          v-for="m in modelGroups"
          :key="`${m.provider}:${m.model}`"
          type="button"
          class="mdl-item"
          :class="{ selected: m.model === appStore.selectedModel && m.provider === appStore.selectedProvider }"
          @click="selectModel(m.model, m.provider)"
        >
          <span class="mdl-radio" />
          <span class="mdl-info">
            <strong>{{ m.name }}<span v-if="m.badge" class="mdl-badge">{{ m.badge }}</span></strong>
            <small>{{ m.vendor }}</small>
          </span>
        </button>
      </div>
    </EaCard>
  </div>
</template>

<style scoped lang="scss">
.hm-icon {
  width: 50px;
  height: 50px;
  border-radius: 15px;
  display: grid;
  place-items: center;
  background: rgba(255, 255, 255, 0.72);
}
.hm-icon-lg { width: 58px; height: 58px; border-radius: 17px; }
.hm-hero { padding: 28px; margin-bottom: 16px; }
.hm-hero h2 { font-size: 26px; font-weight: 800; letter-spacing: -0.02em; margin: 16px 0 6px; }
.hm-hero p { font-size: 15px; opacity: 0.85; max-width: 720px; line-height: 1.55; }

.hm-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}

.hm-sm {
  padding: 24px;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  min-height: 168px;
}

.hm-sm h3 { font-size: 19px; font-weight: 700; margin: 14px 0 6px; }
.hm-sm p {
  flex: 1;
  font-size: 13.5px;
  opacity: 0.82;
  line-height: 1.5;
  margin: 0;
}

.mdl-card { border-radius: 20px; margin-top: 16px; }
.mdl-head { display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; margin-bottom: 16px; }
.mdl-head h3 { font-size: 18px; font-weight: 700; }
.mdl-head p { font-size: 13px; color: var(--muted); margin-top: 3px; }
.mdl-current { font-size: 13px; color: var(--muted); white-space: nowrap; }
.mdl-current b { color: var(--accent); font-weight: 700; }
.mdl-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.mdl-item {
  display: flex; align-items: center; gap: 12px; padding: 14px 16px;
  border: 1px solid var(--line); border-radius: 14px; background: var(--bg);
  cursor: pointer; text-align: left; font-family: inherit; color: var(--text);
  transition: border-color 0.18s, background 0.18s;
  &:hover { border-color: var(--line-strong); }
  &.selected { border-color: var(--accent); background: var(--accent-soft); }
}
.mdl-radio {
  width: 18px; height: 18px; border-radius: 50%; border: 2px solid var(--line-strong); flex-shrink: 0; position: relative;
}
.mdl-item.selected .mdl-radio { border-color: var(--accent); }
.mdl-item.selected .mdl-radio::after {
  content: ''; position: absolute; inset: 3px; border-radius: 50%; background: var(--accent);
}
.mdl-info strong { display: flex; align-items: center; gap: 8px; font-size: 14.5px; font-weight: 700; }
.mdl-info small { display: block; font-size: 12px; color: var(--muted); margin-top: 2px; }
.mdl-badge {
  font-size: 10px; font-weight: 700; color: var(--accent); background: #fff;
  border: 1px solid var(--accent); padding: 1px 7px; border-radius: 999px;
}
.mdl-item.selected .mdl-badge { background: var(--accent); color: #fff; }

@media (min-width: 1100px) {
  .hm-row { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}

@media (max-width: 720px) {
  .hm-row, .mdl-grid { grid-template-columns: 1fr; }
  .hm-sm { min-height: 0; }
}
</style>
