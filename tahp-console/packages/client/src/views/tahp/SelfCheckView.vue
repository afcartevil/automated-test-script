<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { fetchSelfCheck, type SelfCheckResult } from '@/api/tahp/self-check'
import EaPageHead from '@/components/layout/EaPageHead.vue'
import EaCard from '@/components/layout/EaCard.vue'
import EaPill from '@/components/layout/EaPill.vue'

const data = ref<SelfCheckResult | null>(null)
const loading = ref(false)

const ringStyle = ref('')

async function load() {
  loading.value = true
  try {
    data.value = await fetchSelfCheck()
    ringStyle.value = `background: conic-gradient(var(--success) ${data.value.score}%, var(--surface-2) 0)`
  } catch {
    data.value = null
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <EaPageHead title="AI 自检" subtitle="一键体检运行环境、Agent、Skill、知识库与凭证，确保适配 / 诊断链路可用">
      <template #actions>
        <button type="button" class="ea-btn-primary" :disabled="loading" @click="load">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
          </svg>
          重新自检
        </button>
      </template>
    </EaPageHead>

    <div v-if="loading && !data" class="ea-muted" style="padding:40px;text-align:center">检测中…</div>

    <template v-else-if="data">
      <EaCard style="margin-bottom:16px">
        <div class="sc-hero">
          <div class="ring" :style="ringStyle">
            <div class="ring-val"><b>{{ data.score }}</b><span>健康度</span></div>
          </div>
          <div>
            <div class="ea-row" style="gap:10px">
              <EaPill :variant="data.fail > 0 ? 'err' : data.warn > 0 ? 'warn' : 'ok'">{{ data.level }}</EaPill>
              <span class="ea-muted" style="font-size:12.5px">更新于 {{ data.updated }}</span>
            </div>
            <div class="hero-text">
              共 {{ data.total }} 项检查，<b style="color:var(--success)">{{ data.pass }} 项通过</b>，
              <b style="color:var(--warn)">{{ data.warn }} 项告警</b>，<b style="color:var(--error)">{{ data.fail }} 项失败</b>。
            </div>
          </div>
          <div class="ea-meta-grid" style="grid-template-columns:1fr 1fr;min-width:240px">
            <div class="mg"><div class="mg-k">通过</div><div class="mg-v" style="color:var(--success)">{{ data.pass }}</div></div>
            <div class="mg"><div class="mg-k">告警</div><div class="mg-v" style="color:var(--warn)">{{ data.warn }}</div></div>
          </div>
        </div>
      </EaCard>

      <div class="sc-cats" style="margin-bottom:16px">
        <EaCard v-for="cat in data.categories" :key="cat.title" class="sc-cat">
          <h4>{{ cat.title }}</h4>
          <div class="sc-list">
            <div v-for="it in cat.items" :key="it.name" class="sc-row" :class="it.state">
              <span class="sc-dot" />
              <span class="sc-meta"><strong>{{ it.name }}</strong><span>{{ it.detail }}</span></span>
              <span class="sc-state">{{ it.label }}</span>
            </div>
          </div>
        </EaCard>
      </div>

      <EaCard>
        <div class="ea-section-title ea-mb0">自检历史</div>
        <div v-for="(h, i) in data.history" :key="i" class="ctx-row">
          <span class="ea-row" style="gap:12px"><b>{{ h.score }}</b><span>{{ h.time }}</span></span>
          <span class="ea-muted" style="text-align:right">{{ h.note }}</span>
        </div>
      </EaCard>
    </template>
  </div>
</template>

<style scoped lang="scss">
.sc-hero { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: 24px; }
.ring {
  width: 116px; height: 116px; border-radius: 50%; display: grid; place-items: center; position: relative; flex-shrink: 0;
  &::after { content: ''; position: absolute; inset: 10px; border-radius: 50%; background: var(--surface); }
}
.ring-val { position: relative; z-index: 1; text-align: center; }
.ring-val b { font-size: 30px; font-weight: 800; color: var(--success); }
.ring-val span { display: block; font-size: 11px; color: var(--muted); }
.hero-text { font-size: 14px; line-height: 1.6; margin-top: 10px; color: var(--text); }
.sc-cats { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }
.sc-cat h4 { font-size: 13px; font-weight: 700; margin-bottom: 10px; }
.sc-list { display: flex; flex-direction: column; gap: 8px; }
.sc-row {
  display: flex; align-items: center; gap: 12px; padding: 12px 14px;
  border-radius: 12px; background: var(--bg); border: 1px solid var(--line);
}
.sc-dot { width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }
.sc-row.ok .sc-dot { background: var(--success); }
.sc-row.warn .sc-dot { background: var(--warn); }
.sc-row.err .sc-dot { background: var(--error); }
.sc-meta { flex: 1; }
.sc-meta strong { font-size: 13.5px; }
.sc-meta span { display: block; font-size: 12px; color: var(--muted); font-family: 'JetBrains Mono', monospace; margin-top: 1px; }
.sc-state { font-size: 12px; font-weight: 700; }
.sc-row.ok .sc-state { color: var(--success); }
.sc-row.warn .sc-state { color: var(--warn); }
.sc-row.err .sc-state { color: var(--error); }
.ctx-row {
  display: flex; justify-content: space-between; gap: 10px; padding: 8px 0;
  border-bottom: 1px dashed var(--line); font-size: 12.5px;
  &:last-child { border: none; }
}
@media (max-width: 1100px) {
  .sc-cats { grid-template-columns: 1fr; }
  .sc-hero { grid-template-columns: 1fr; }
}
</style>
