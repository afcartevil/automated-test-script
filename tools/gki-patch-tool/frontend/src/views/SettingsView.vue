<template>
  <section>
    <div class="topbar">
      <div>
        <p class="eyebrow">Settings</p>
        <h1 class="page-title">系统设置</h1>
        <p v-if="!isEmbedded" class="page-desc">管理本地仓库路径、LLM API 与远程 SSH 账号。</p>
      </div>
      <button class="btn" @click="loadAll">刷新配置</button>
    </div>

    <div class="grid grid-2">
      <div class="card card-pad">
        <div class="section-title">
          <div>
            <h2>本地代码</h2>
            <p>GKI 内核源码本地路径，用于 commit / diff 查询</p>
          </div>
        </div>
        <div class="field">
          <label>本地代码路径</label>
          <input v-model="repo.repo_dir" class="input mono" placeholder="如 E:\code\kernel\common 或 /data/kernel/common" />
        </div>
        <div class="toolbar" style="margin-top: 14px">
          <button class="btn primary" @click="saveRepo">保存</button>
          <span class="pill" :class="repo.configured ? 'success' : 'warning'">
            {{ repo.configured ? '已配置' : '未配置' }}
          </span>
        </div>
      </div>

      <div class="card card-pad">
        <div class="section-title">
          <div>
            <h2>LLM 配置</h2>
            <p>填写 Key 与 Base 后从服务端拉取可用模型列表</p>
          </div>
        </div>
        <div class="form-grid">
          <div class="field full">
            <label>API Key</label>
            <input v-model="llm.api_key" class="input" type="password" placeholder="sk-..." @change="onLlmCredentialChange" />
          </div>
          <div class="field full">
            <label>API Base</label>
            <input
              v-model="llm.api_base"
              class="input mono"
              placeholder="https://api.openai.com/v1"
              @change="onLlmCredentialChange"
            />
          </div>
          <div class="field full">
            <label>Model</label>
            <div class="model-picker">
              <select v-model="llm.model" class="select" :disabled="!modelOptions.length">
                <option v-if="!modelOptions.length" value="" disabled>请先获取模型列表</option>
                <option v-for="id in modelOptions" :key="id" :value="id">{{ id }}</option>
              </select>
              <button class="btn" type="button" :disabled="modelsLoading || !llm.api_key" @click="fetchModels">
                {{ modelsLoading ? '获取中…' : '获取模型列表' }}
              </button>
            </div>
            <p v-if="modelsHint" class="field-hint">{{ modelsHint }}</p>
            <p v-if="modelsError" class="field-hint error">{{ modelsError }}</p>
          </div>
        </div>
        <div class="toolbar" style="margin-top: 14px">
          <button class="btn primary" :disabled="!llm.model" @click="saveLlm">保存</button>
          <span class="pill" :class="llm.configured ? 'success' : 'warning'">
            {{ llm.configured ? '已配置' : '未配置' }}
          </span>
        </div>
      </div>

      <div id="settings-ssh" class="card card-pad" :class="{ 'settings-section-focus': sshSectionFocus }">
        <div class="section-title">
          <div>
            <h2>远程 SSH（cqris）</h2>
            <p>远程合入 / 编译验证的堡垒机与目标机账号，保存到数据库（OTP 每次仍需手动输入）</p>
          </div>
        </div>
        <div class="form-grid">
          <div class="field">
            <label>堡垒机</label>
            <input :value="ssh.bastion_host" class="input mono" disabled />
          </div>
          <div class="field">
            <label>端口</label>
            <input :value="ssh.bastion_port" class="input mono" disabled />
          </div>
          <div class="field">
            <label>cqris 用户名</label>
            <input v-model="ssh.bastion_user" class="input" placeholder="工号/域账号" autocomplete="username" />
          </div>
          <div class="field">
            <label>cqris 密码</label>
            <input v-model="ssh.bastion_password" class="input" type="password" autocomplete="off" />
          </div>
          <div class="field">
            <label>目标 IP</label>
            <input v-model="ssh.target_ip" class="input mono" placeholder="10.205.0.158" />
          </div>
          <div class="field">
            <label>目标用户名</label>
            <input v-model="ssh.target_user" class="input" autocomplete="username" />
          </div>
          <div class="field full">
            <label>目标密码</label>
            <input v-model="ssh.target_password" class="input" type="password" autocomplete="off" />
          </div>
        </div>
        <div class="toolbar ssh-toolbar" style="margin-top: 14px">
          <button class="btn primary" @click="saveSsh">保存</button>
          <button class="btn danger" :disabled="!ssh.credentials_configured" @click="clearSsh">清除配置</button>
          <span class="pill" :class="ssh.credentials_configured ? 'success' : 'warning'">
            {{ ssh.credentials_configured ? '已配置' : '未配置' }}
          </span>
        </div>
      </div>

      <div class="card card-pad">
        <div class="section-title">
          <div>
            <h2>帮助文档</h2>
            <p>工具能力说明与操作流程</p>
          </div>
        </div>
        <div class="list">
          <a class="list-item split" href="/overview" target="_blank" rel="noopener">
            <span>
              <strong>GKI Patch Tool 说明</strong>
              <span class="muted" style="display:block">功能概览、架构与使用指引</span>
            </span>
            <span class="pill info">docs</span>
          </a>
        </div>
      </div>
    </div>

    <div v-if="message" class="message" style="margin-top: 18px">{{ message }}</div>
    <div v-if="error" class="message error" style="margin-top: 18px">{{ error }}</div>
  </section>
</template>

<script setup lang="ts">
import { nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { isEmbeddedMode } from '../composables/useEmbeddedNav'

const isEmbedded = isEmbeddedMode()
const route = useRoute()
const sshSectionFocus = ref(false)

const repo = reactive<any>({ repo_dir: '', configured: false })
const llm = reactive<any>({ api_key: '', api_base: 'https://api.openai.com/v1', model: '', configured: false })
const ssh = reactive<any>({
  bastion_host: 'cqris.transsion.com',
  bastion_port: 22,
  target_ip: '10.205.0.158',
  bastion_user: '',
  bastion_password: '',
  target_user: '',
  target_password: '',
  credentials_configured: false,
})
const modelOptions = ref<string[]>([])
const modelsLoading = ref(false)
const modelsError = ref('')
const modelsHint = ref('')
const message = ref('')
const error = ref('')

function ensureCurrentModelInOptions() {
  if (llm.model && !modelOptions.value.includes(llm.model)) {
    modelOptions.value = [llm.model, ...modelOptions.value].sort((a, b) => a.localeCompare(b))
  }
}

async function fetchModels() {
  modelsError.value = ''
  modelsHint.value = ''
  if (!llm.api_key?.trim()) {
    modelsError.value = '请先填写 API Key'
    return
  }
  modelsLoading.value = true
  try {
    const data = await api.post<any>('/api/llm/models', {
      api_key: llm.api_key,
      api_base: llm.api_base,
    })
    modelOptions.value = data.models || []
    modelsHint.value = `已从 ${data.api_base || llm.api_base} 获取 ${data.count ?? modelOptions.value.length} 个模型`
    ensureCurrentModelInOptions()
    if (!llm.model && modelOptions.value.length) {
      llm.model = modelOptions.value[0]
    }
  } catch (err: any) {
    modelOptions.value = []
    modelsError.value = err.message || String(err)
  } finally {
    modelsLoading.value = false
  }
}

function onLlmCredentialChange() {
  modelsHint.value = ''
  modelsError.value = ''
}

async function loadAll() {
  error.value = ''
  try {
    const [repoData, llmData, sshData] = await Promise.all([
      api.get<any>('/api/repo/config'),
      api.get<any>('/api/llm/config'),
      api.get<any>('/api/upgrade/ssh-config'),
    ])
    Object.assign(repo, repoData)
    repo.repo_dir = repoData.repo_dir || repoData.effective_dir || ''
    Object.assign(llm, llmData)
    Object.assign(ssh, sshData)
    if (llm.api_key) {
      await fetchModels()
    } else if (llm.model) {
      modelOptions.value = [llm.model]
    }
  } catch (err: any) {
    error.value = err.message || String(err)
  }
}

async function saveRepo() {
  await save('/api/repo/config', { repo_dir: repo.repo_dir })
}

async function saveLlm() {
  if (!llm.model) {
    error.value = '请先获取并选择模型'
    return
  }
  await save('/api/llm/config', {
    api_key: llm.api_key,
    api_base: llm.api_base,
    model: llm.model,
  })
}

async function saveSsh() {
  if (!ssh.bastion_user?.trim() || !ssh.bastion_password) {
    error.value = '请填写 cqris 用户名和密码'
    return
  }
  if (!ssh.target_ip?.trim() || !ssh.target_user?.trim() || !ssh.target_password) {
    error.value = '请填写目标 IP、用户名和密码'
    return
  }
  await save('/api/upgrade/ssh-credentials', {
    bastion_user: ssh.bastion_user.trim(),
    bastion_password: ssh.bastion_password,
    target_ip: ssh.target_ip.trim(),
    target_user: ssh.target_user.trim(),
    target_password: ssh.target_password,
  })
}

async function clearSsh() {
  if (!ssh.credentials_configured) return
  if (!window.confirm('确定清除已保存的远程 SSH 账号？清除后创建远程任务需重新配置。')) return
  error.value = ''
  message.value = ''
  try {
    await api.delete('/api/upgrade/ssh-credentials')
    message.value = 'SSH 配置已清除'
    await loadAll()
  } catch (err: any) {
    error.value = err.message || String(err)
  }
}

async function save(url: string, body: any) {
  error.value = ''
  message.value = ''
  try {
    await api.put(url, body)
    message.value = '配置已保存'
    await loadAll()
  } catch (err: any) {
    error.value = err.message || String(err)
  }
}

onMounted(async () => {
  await loadAll()
  if (String(route.query.section || '') === 'ssh') {
    sshSectionFocus.value = true
    await nextTick()
    document.getElementById('settings-ssh')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    window.setTimeout(() => {
      sshSectionFocus.value = false
    }, 2400)
  }
})
</script>

<style scoped>
.model-picker {
  display: flex;
  gap: 8px;
  align-items: stretch;
}
.model-picker .select {
  flex: 1;
  min-width: 0;
}
.field-hint {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--muted);
}
.field-hint.error {
  color: var(--danger);
}
.ssh-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.settings-section-focus {
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.35);
}
</style>
