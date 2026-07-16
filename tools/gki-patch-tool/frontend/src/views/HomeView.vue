<template>
  <section class="home-page">
    <RouterLink to="/analysis" class="home-hero card">
      <div class="home-hero-icon">▶</div>
      <div>
        <h2>patch分析</h2>
        <p>单 SHA 与 tag 区间分析，实时进度、评分分布与 patch 报告。</p>
      </div>
    </RouterLink>

    <div class="home-feature-row">
      <RouterLink to="/crash" class="home-feature card tone-blue">
        <div class="home-feature-icon">诊</div>
        <div>
          <h3>故障诊断</h3>
          <p>升级后死机日志分析，定位可疑 patch 与修复建议。</p>
        </div>
      </RouterLink>

      <RouterLink to="/upgrade" class="home-feature card tone-green">
        <div class="home-feature-icon">库</div>
        <div>
          <h3>patch入库</h3>
          <p>GKI 升级合入、冲突处理、提交与编译流程。</p>
        </div>
      </RouterLink>
    </div>

    <div class="home-feature-row">
      <RouterLink to="/patches" class="home-feature card tone-slate">
        <div class="home-feature-icon">DB</div>
        <div>
          <h3>数据库</h3>
          <p>浏览已分析 patch，按模块筛选与详情预览。</p>
        </div>
      </RouterLink>

      <RouterLink to="/dashboard" class="home-feature card tone-amber">
        <div class="home-feature-icon">板</div>
        <div>
          <h3>看板</h3>
          <p>任务统计、最近分析与升级流程一览。</p>
        </div>
      </RouterLink>
    </div>

    <div class="env-section card card-pad">
      <div class="env-section-head">
        <div>
          <h2>环境配置</h2>
          <p class="muted">首页快速查看当前环境；详细参数请点右上角「设置」。</p>
        </div>
        <div class="env-current">
          <span class="muted">当前</span>
          <strong>{{ currentEnvLabel }}</strong>
        </div>
      </div>

      <div class="env-grid">
        <button
          type="button"
          class="env-option"
          :class="{ active: repoConfigured }"
          @click="goSettings"
        >
          <span class="env-radio"></span>
          <span class="env-option-body">
            <strong>本地代码</strong>
            <span>{{ repoConfigured ? repoPath || '已配置' : '未配置，点击去设置' }}</span>
          </span>
        </button>

        <button
          type="button"
          class="env-option"
          :class="{ active: llmConfigured }"
          @click="goSettings"
        >
          <span class="env-radio"></span>
          <span class="env-option-body">
            <strong>{{ llmModel || 'LLM 未配置' }}</strong>
            <span>{{ llmConfigured ? 'AI 分析与冲突处理可用' : '点击配置 API Key 与模型' }}</span>
          </span>
        </button>
      </div>
    </div>

    <div v-if="error" class="message error" style="margin-top: 18px">{{ error }}</div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'

const router = useRouter()
const repoConfigured = ref(false)
const repoPath = ref('')
const llmConfigured = ref(false)
const llmModel = ref('')
const error = ref('')

const currentEnvLabel = computed(() => {
  const parts: string[] = []
  if (repoConfigured.value) parts.push('本地代码就绪')
  if (llmConfigured.value) parts.push(llmModel.value || 'LLM')
  return parts.join(' · ') || '待配置'
})

function goSettings() {
  router.push('/settings')
}

async function loadEnv() {
  error.value = ''
  try {
    const [repoData, llmData] = await Promise.all([
      api.get<any>('/api/repo/config'),
      api.get<any>('/api/llm/config'),
    ])
    repoConfigured.value = Boolean(repoData.configured || repoData.effective_dir || repoData.repo_dir)
    repoPath.value = repoData.effective_dir || repoData.repo_dir || ''
    llmConfigured.value = Boolean(llmData.configured)
    llmModel.value = llmData.model || ''
  } catch (err: any) {
    error.value = err.message || String(err)
  }
}

onMounted(loadEnv)
</script>
