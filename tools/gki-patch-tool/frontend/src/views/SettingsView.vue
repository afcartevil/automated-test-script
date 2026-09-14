<template>
  <section>
    <div class="topbar">
      <div>
        <p class="eyebrow">Settings</p>
        <h1 class="page-title">系统设置</h1>
        <p v-if="!isEmbedded" class="page-desc">管理本地仓库路径、LLM API、飞书应用与远程 SSH 账号。保存后写入本机，换一套代码仍会保留。</p>
        <p v-else class="page-desc">管理本地仓库路径与飞书应用（LLM / SSH 使用 EasyAdapter 一键配置）。保存后写入本机，换一套代码仍会保留。</p>
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
        <p v-if="repo.machine_settings_path" class="field-hint">
          本机持久化：{{ repo.machine_settings_path }}
        </p>
      </div>

      <div v-if="!isEmbedded" class="card card-pad">
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

      <div class="card card-pad">
        <div class="section-title">
          <div>
            <h2>飞书应用</h2>
            <p>配置后导出验收表格无需本机安装 lark-cli；可指定共享目录，并把所有者转给指定用户</p>
          </div>
        </div>
        <div class="form-grid">
          <div class="field">
            <label>App ID</label>
            <input v-model="feishu.app_id" class="input mono" placeholder="cli_xxx" autocomplete="off" />
          </div>
          <div class="field">
            <label>App Secret</label>
            <input v-model="feishu.app_secret" class="input" type="password" placeholder="应用密钥" autocomplete="off" />
          </div>
          <div class="field full">
            <label>存放目录 Token（可选）</label>
            <input v-model="feishu.folder_token" class="input mono" placeholder="可直接粘贴文件夹链接，如 https://xxx.feishu.cn/drive/folder/CvYFfs..." />
          </div>
          <div class="field full">
            <label>默认所有者（可选）</label>
            <input v-model="feishu.owner" class="input" placeholder="如 ke.li11@transsion.com，表格会转到该用户名下" />
          </div>
          <div class="field">
            <label>默认文档密级</label>
            <select v-model="feishu.secure_label" class="input">
              <option value="S4">S4-绝密</option>
              <option value="S3">S3-机密</option>
              <option value="S2">S2-内部公开</option>
              <option value="S1">S1-外部公开</option>
            </select>
          </div>
          <div class="field full">
            <label>开放平台地址</label>
            <input v-model="feishu.open_base" class="input mono" placeholder="https://open.feishu.cn" />
          </div>
          <div class="field full">
            <label>任务通知接收人（可多人，无群时用这个）</label>
            <textarea
              v-model="feishu.notify_users"
              class="input textarea"
              rows="3"
              placeholder="每人一行或用逗号分隔，如：&#10;ke.li11@transsion.com&#10;someone@transsion.com"
            />
          </div>
          <div class="field full">
            <label>任务通知 Webhook（可选，有群再填）</label>
            <input
              v-model="feishu.webhook_url"
              class="input mono"
              placeholder="群自定义机器人 Webhook，如 https://open.feishu.cn/open-apis/bot/v2/hook/…"
              autocomplete="off"
            />
          </div>
          <div class="field full">
            <label>Webhook 签名密钥（可选）</label>
            <input
              v-model="feishu.webhook_secret"
              class="input"
              type="password"
              placeholder="机器人开启「签名校验」时填写"
              autocomplete="off"
            />
          </div>
          <div class="field full">
            <label>GKI 异常告警多维表格 URL</label>
            <input
              v-model="feishu.alert_bitable_url"
              class="input mono"
              placeholder="飞书 wiki/base 链接，含 table=tbl…"
            />
          </div>
          <div class="field">
            <label>打开时同步异常告警</label>
            <select v-model="feishu.alert_sync_enabled" class="input">
              <option :value="true">开启</option>
              <option :value="false">关闭</option>
            </select>
          </div>
          <div class="field">
            <label>进程内同步间隔（秒）</label>
            <input
              v-model.number="feishu.alert_sync_interval_sec"
              class="input mono"
              type="number"
              min="60"
              step="60"
              placeholder="1800"
            />
          </div>
        </div>
        <p class="field-hint">
          在飞书开放平台创建企业自建应用，开通云空间/电子表格权限，以及「转移云文档所有权」。填了默认所有者后，新建表格会转到该用户名下；应用仍保留协作者以便后续刷新。
          存放目录可直接粘贴云空间文件夹链接，例如
          https://xxx.feishu.cn/drive/folder/CvYFfsIzMl6Yo2dRq3ocfqGDnfh
          （会自动识别最后一段 token，不一定是 fldcn 开头）。应用需要对该文件夹有编辑权限。不填则建在应用云空间。
          默认密级会在创建验收表格、上传模块代码 HTML 后自动设置（文件夹本身不支持密级）；需应用或 lark-cli 具备 docs:secure_label 权限。
          任务通知：没有群时，在「任务通知接收人」填多人企业邮箱（或 ou_ open_id），分析 / 故障诊断 / 入库任务完成或失败会用应用逐个发私信。应用需开通 im:message，并在开放平台把这些用户纳入可用范围。不填接收人时会回退发给「默认所有者」。有群才需要填 Webhook。
          异常告警：Console 进入 GKI 工作台时会按上方多维表格补拉「异常告警=1」的行；已同步成任务的行不会重复提醒。应用需对表格有读权限（base:record:read / wiki）。
        </p>
        <div class="toolbar" style="margin-top: 14px">
          <button class="btn primary" @click="saveFeishu">保存</button>
          <button class="btn" type="button" :disabled="feishuTesting || !feishu.app_id || !feishu.app_secret" @click="testFeishu">
            {{ feishuTesting ? '测试中…' : '测试连接' }}
          </button>
          <button
            class="btn"
            type="button"
            :disabled="feishuWebhookTesting || !canTestNotify"
            @click="testFeishuWebhook"
          >
            {{ feishuWebhookTesting ? '发送中…' : '测试通知' }}
          </button>
          <span class="pill" :class="feishu.configured ? 'success' : 'warning'">
            {{ feishu.configured ? '应用已配置' : '应用未配置' }}
          </span>
          <span class="pill" :class="feishu.webhook_configured ? 'success' : 'warning'">
            {{ feishu.webhook_configured ? '通知已配置' : '通知未配置' }}
          </span>
        </div>
      </div>

      <div
        v-if="!isEmbedded"
        id="settings-ssh"
        class="card card-pad"
        :class="{ 'settings-section-focus': sshSectionFocus }"
      >
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
            <h2>合入 / 编译经验</h2>
            <p>失败重试时勾选「写入后续 prompt」会追加到这里，之后同类任务自动带上</p>
          </div>
        </div>
        <div class="field">
          <label>冲突合入经验</label>
          <textarea v-model="retryHints.conflict" class="input" rows="5" spellcheck="false" placeholder="例如：同名函数实现不同时，只把 .rej 的 +/- 合进 vendor 现有函数" />
        </div>
        <div class="field" style="margin-top: 12px">
          <label>编译修复经验</label>
          <textarea v-model="retryHints.build_fix" class="input" rows="5" spellcheck="false" placeholder="例如：vendor 与内核宏同名时，优先 rename vendor 符号，不要改 include/linux" />
        </div>
        <div class="toolbar" style="margin-top: 14px">
          <button class="btn primary" type="button" @click="saveRetryHints">保存经验</button>
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
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'
import { isEmbeddedMode } from '../composables/useEmbeddedNav'

const isEmbedded = isEmbeddedMode()
const route = useRoute()
const sshSectionFocus = ref(false)

const repo = reactive<any>({ repo_dir: '', configured: false })
const llm = reactive<any>({
  api_key: '',
  api_base: 'https://api.openai.com/v1',
  model: '',
  configured: false,
  managed_by_ea: false,
  readonly: false,
})
const feishu = reactive<any>({
  app_id: '',
  app_secret: '',
  folder_token: '',
  owner: '',
  open_base: 'https://open.feishu.cn',
  secure_label: 'S2',
  webhook_url: '',
  webhook_secret: '',
  notify_users: '',
  alert_sync_enabled: true,
  alert_bitable_url: '',
  alert_sync_interval_sec: 1800,
  configured: false,
  webhook_configured: false,
})
const feishuTesting = ref(false)
const feishuWebhookTesting = ref(false)
const canTestNotify = computed(() => {
  if (feishu.webhook_url?.trim()) return true
  return Boolean(feishu.app_id?.trim() && feishu.app_secret?.trim() && (feishu.notify_users?.trim() || feishu.owner?.trim()))
})
const retryHints = reactive({ conflict: '', build_fix: '' })
const ssh = reactive<any>({
  bastion_host: 'cqris.transsion.com',
  bastion_port: 22,
  target_ip: '10.205.0.158',
  bastion_user: '',
  bastion_password: '',
  target_user: '',
  target_password: '',
  credentials_configured: false,
  managed_by_ea: false,
  readonly: false,
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
    const [repoData, llmData, feishuData, sshData, hintData] = await Promise.all([
      api.get<any>('/api/repo/config'),
      api.get<any>('/api/llm/config'),
      api.get<any>('/api/feishu/config'),
      api.get<any>('/api/upgrade/ssh-config'),
      api.get<any>('/api/settings/retry-hints').catch(() => ({ hints: {} })),
    ])
    Object.assign(repo, repoData)
    repo.repo_dir = repoData.repo_dir || repoData.effective_dir || ''
    Object.assign(llm, llmData)
    Object.assign(feishu, feishuData)
    if (!feishu.open_base) feishu.open_base = 'https://open.feishu.cn'
    if (!feishu.secure_label) feishu.secure_label = 'S2'
    if (feishu.alert_sync_enabled === undefined) feishu.alert_sync_enabled = true
    if (!feishu.alert_bitable_url) {
      feishu.alert_bitable_url = 'https://transsioner.feishu.cn/wiki/JJglwZtIuiBXqbkARAPcSQesntc?table=tblV2q5qJffkFuPE&view=vewLOPzQfs'
    }
    if (!feishu.alert_sync_interval_sec) feishu.alert_sync_interval_sec = 1800
    Object.assign(ssh, sshData)
    retryHints.conflict = hintData?.hints?.conflict || ''
    retryHints.build_fix = hintData?.hints?.build_fix || ''
    // 集成模式不展示 LLM 配置，跳过拉取模型列表
    if (!isEmbedded) {
      if (llm.api_key) {
        await fetchModels()
      } else if (llm.model) {
        modelOptions.value = [llm.model]
      }
    }
  } catch (err: any) {
    error.value = err.message || String(err)
  }
}

async function saveRepo() {
  await save('/api/repo/config', { repo_dir: repo.repo_dir })
}

async function saveRetryHints() {
  error.value = ''
  message.value = ''
  try {
    await api.put('/api/settings/retry-hints', { domain: 'conflict', text: retryHints.conflict })
    await api.put('/api/settings/retry-hints', { domain: 'build_fix', text: retryHints.build_fix })
    message.value = '合入/编译经验已保存'
    await loadAll()
  } catch (err: any) {
    error.value = err.message || String(err)
  }
}

async function saveLlm() {
  if (llm.managed_by_ea || llm.readonly) {
    error.value = '当前由 EasyAdapter 托管 LLM 配置，请在 EasyAdapter「模型」中修改'
    return
  }
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

async function saveFeishu() {
  const hasApp = !!(feishu.app_id?.trim() && feishu.app_secret?.trim())
  const hasWebhook = !!feishu.webhook_url?.trim()
  if (!hasApp && !hasWebhook) {
    error.value = '请至少填写飞书 App ID/Secret，或任务通知 Webhook'
    return
  }
  await save('/api/feishu/config', {
    app_id: feishu.app_id.trim(),
    app_secret: feishu.app_secret.trim(),
    folder_token: (feishu.folder_token || '').trim(),
    owner: (feishu.owner || '').trim(),
    open_base: (feishu.open_base || 'https://open.feishu.cn').trim(),
    secure_label: (feishu.secure_label || 'S2').trim(),
    webhook_url: (feishu.webhook_url || '').trim(),
    webhook_secret: (feishu.webhook_secret || '').trim(),
    notify_users: (feishu.notify_users || '').trim(),
    alert_sync_enabled: feishu.alert_sync_enabled !== false,
    alert_bitable_url: (feishu.alert_bitable_url || '').trim(),
    alert_sync_interval_sec: Number(feishu.alert_sync_interval_sec) || 1800,
  })
}

async function testFeishu() {
  error.value = ''
  message.value = ''
  if (!feishu.app_id?.trim() || !feishu.app_secret?.trim()) {
    error.value = '请先填写并保存飞书 App ID / Secret'
    return
  }
  feishuTesting.value = true
  try {
    await api.put('/api/feishu/config', {
      app_id: feishu.app_id.trim(),
      app_secret: feishu.app_secret.trim(),
      folder_token: (feishu.folder_token || '').trim(),
      owner: (feishu.owner || '').trim(),
      open_base: (feishu.open_base || 'https://open.feishu.cn').trim(),
      secure_label: (feishu.secure_label || 'S2').trim(),
      webhook_url: (feishu.webhook_url || '').trim(),
      webhook_secret: (feishu.webhook_secret || '').trim(),
      notify_users: (feishu.notify_users || '').trim(),
      alert_sync_enabled: feishu.alert_sync_enabled !== false,
      alert_bitable_url: (feishu.alert_bitable_url || '').trim(),
      alert_sync_interval_sec: Number(feishu.alert_sync_interval_sec) || 1800,
    })
    await api.post('/api/feishu/config/test', {})
    message.value = '飞书应用连接成功'
    await loadAll()
  } catch (err: any) {
    error.value = err.message || String(err)
  } finally {
    feishuTesting.value = false
  }
}

async function testFeishuWebhook() {
  error.value = ''
  message.value = ''
  if (!canTestNotify.value) {
    error.value = '请先填写通知接收人，或群机器人 Webhook'
    return
  }
  feishuWebhookTesting.value = true
  try {
    await api.put('/api/feishu/config', {
      app_id: feishu.app_id.trim(),
      app_secret: feishu.app_secret.trim(),
      folder_token: (feishu.folder_token || '').trim(),
      owner: (feishu.owner || '').trim(),
      open_base: (feishu.open_base || 'https://open.feishu.cn').trim(),
      secure_label: (feishu.secure_label || 'S2').trim(),
      webhook_url: feishu.webhook_url.trim(),
      webhook_secret: (feishu.webhook_secret || '').trim(),
      notify_users: (feishu.notify_users || '').trim(),
      alert_sync_enabled: feishu.alert_sync_enabled !== false,
      alert_bitable_url: (feishu.alert_bitable_url || '').trim(),
      alert_sync_interval_sec: Number(feishu.alert_sync_interval_sec) || 1800,
    })
    const result = await api.post<any>('/api/feishu/webhook/test', {})
    const sent = result?.response?.sent
    message.value = feishu.webhook_url?.trim()
      ? '测试通知已发送，请到飞书群查看'
      : `测试通知已发送${Array.isArray(sent) ? `（${sent.length} 人）` : ''}，请到飞书私信查看`
    await loadAll()
  } catch (err: any) {
    error.value = err.message || String(err)
  } finally {
    feishuWebhookTesting.value = false
  }
}

async function saveSsh() {
  if (isEmbedded || ssh.managed_by_ea || ssh.readonly) {
    error.value = '当前由 EasyAdapter 托管 SSH 配置，请在 EasyAdapter「一键配置」中修改'
    return
  }
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
  if (isEmbedded || ssh.managed_by_ea || ssh.readonly) {
    error.value = '当前由 EasyAdapter 托管 SSH 配置，无法在此清除'
    return
  }
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
  if (!isEmbedded && String(route.query.section || '') === 'ssh') {
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
