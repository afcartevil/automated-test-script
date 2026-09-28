<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import EaPageHead from '@/components/layout/EaPageHead.vue'
import EaCard from '@/components/layout/EaCard.vue'

const SOP_URL = 'https://transsioner.feishu.cn/wiki/BdVUwpCL4ifRZckiQlzcPQoUndg'

const router = useRouter()
const activeKey = ref('pursuit')

function go(name: string) {
  router.push({ name })
}

function openUrl(url: string) {
  window.open(url, '_blank', 'noopener,noreferrer')
}

function openItem(item: ManualItem) {
  if (item.route) go(item.route)
  else if (item.url) openUrl(item.url)
}

function scrollToItem(key: string) {
  pinNav(key)
  document.getElementById(`manual-item-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function scrollToGroup(id: string) {
  pinNav(id)
  document.getElementById(`manual-group-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function toneStyle(tone: string) {
  return { '--item-tone': tone } as Record<string, string>
}

interface ManualItem {
  key: string
  title: string
  desc: string
  steps: string[]
  notes?: string[]
  tone: string
  route?: string
  url?: string
}

interface ManualGroup {
  id: string
  title: string
  subtitle: string
  color: string
  items: ManualItem[]
}

const groups: ManualGroup[] = [
  {
    id: 'core',
    title: '三大核心',
    subtitle: '适配调试/适配流水线、Modem 升级、GKI 升级',
    color: 'var(--accent)',
    items: [
      {
        key: 'adapt-debug',
        title: 'AI 适配调试',
        tone: 'var(--violet-ic)',
        desc: '把<span class="hl">源版本</span>的功能、特性、运营商定制改到<span class="hl">目标版本</span>。按域（通信 / 驱动 / 内核等）填前置条件，<span class="hl">启动 Agent</span> 改代码并出适配报告；入库须<span class="hl">人工审核</span>后走 Gerrit。',
        steps: [
          '进入「AI 适配调试」，选择工作区与业务域（通信 / 驱动 / 内核等）。',
          '可用「<span class="hl">从中心载入前置</span>」按项目号自动填表。',
          '完成必填项后<span class="hl">启动</span>；填完表单后会进入运行监控，可看 Agent 过程与文件改动。',
          '完成后在本页「历史表单」点「<span class="hl">查看完整报告</span>」核对修改清单；需要入库时走<span class="hl">审核</span>与 <span class="hl">Gerrit 提交</span>。',
        ],
        notes: [
          '偏单次、按 JIRA / 需求交互调试。要把适配和编译、烧录、自检串起来，用下面的「适配流水线」。',
          'Agent 不可用时任务失败，不会改成后台直接调模型。',
        ],
        route: 'tahp.adapt-debug',
      },
      {
        key: 'pipeline',
        title: '适配流水线',
        tone: 'var(--accent)',
        desc: '适配调试的自动流转路径：把<span class="hl">选项目 → 前置信息 → AI 适配 → 编译 → 烧录 → 适配自检 → 提交 Gerrit → 人工审核入库</span>串成工作流。某阶段没就绪或失败会变成<span class="hl">人工处理</span>（选恢复点、能力未接入、选仓等）；按界面推荐的恢复点续跑，<span class="hl-warn">不要整条重跑</span>。',
        steps: [
          '进入「适配流水线」，在「<span class="hl">新建运行</span>」选项目与前置版本（需 <span class="hl">EasyAdapter 中心</span>已配置、<span class="hl">Agent Bridge</span> 就绪）。也可在运行列表点「<span class="hl">复制</span>」带出已有配置再核对启动。',
          '<span class="hl">启动</span>后在「运行看板」按阶段观察进度。',
          '页头「<span class="hl">⚠ N 项待人工处理</span>」可点进对应运行；失败阶段在面板选恢复点，「刷新」可重载恢复点。',
          '整条不要了点红色「<span class="hl-warn">终止</span>」确认后结束；已终止 / 已失败不再计入待人工。',
          '「流程编排」Tab 可查看 / 调整阶段定义。',
        ],
        notes: [
          '流水线只负责编排；编译、刷机、自检复用现有功能。',
        ],
        route: 'tahp.pipeline',
      },
      {
        key: 'modem',
        title: 'Modem 升级',
        tone: 'var(--amber-ic)',
        desc: 'AP 基线升级后，Modem 仓 patch <span class="hl">自动合入并提交</span>，<span class="hl">人工审核</span>通过后入库。<span class="hl">不会自动开合入</span>：TONES / MergeTool 经中心推送通知后，须在工作台采用、核对再启动。',
        steps: [
          'TONES 完成 AP 基线升级后，通知出现在工作台「<span class="hl">外部通知</span>」；也可手动粘贴通知文本。',
          '点「<span class="hl">采用</span>」填入，核对合入仓 / 项目推荐后<span class="hl">启动</span>分阶段执行。',
          '阶段面板跟踪合入、冲突与日志；有冲突按提示处理再继续。',
          '核对并启动后点「<span class="hl">确认完成</span>」，通知才从待办消失。',
          '<span class="hl">人工审核</span>通过后<span class="hl-ok">入库</span>。运行历史可回看；环境 / 仓库 / 推送策略在「配置中心」。',
        ],
        notes: [
          '子页：工作台 / 运行历史 / 配置中心。',
          '合入由本机 Console 调用集成版 Modem Patch Tool，不必另装一份工具。',
        ],
        route: 'tahp.modem-baseline.workbench',
      },
      {
        key: 'gki',
        title: 'GKI 升级',
        tone: 'var(--emerald-ic)',
        desc: 'GKI patch <span class="hl">质量分析</span>、稳定性验证并选取最优 Tag，再自动合入提交；<span class="hl">人工审核</span>通过后入库。任务同样来自 <span class="hl">TONES</span>，在 Console 内嵌的 GKI Patch Tool 中处理。',
        steps: [
          '进入「GKI 升级」，先等本机服务就绪（首次会拉起），从<span class="hl">工作台</span>看外部通知与任务列表。',
          '填 From / To Tag 后可「前往分析」或直接「前往合入」；也可在左侧打开「<span class="hl">patch分析</span>」看质量结论、选最优 Tag。',
          '「故障诊断」处理合入 / 验证中的 crash。确认后走「<span class="hl">patch入库</span>」合入与编译验证。',
          '历史在「数据库」；LLM / SSH 由 EasyAdapter 一键配置注入，「设置」里看其余环境项。',
        ],
        notes: [
          '左侧：工作台 / patch分析 / patch入库 / 故障诊断 / 数据库 / 设置，会打开对应页，不必退回顶栏。',
          '与 Modem 升级一样：通知不会自动开合入，须审核后入库。',
        ],
        route: 'tahp.gki-patch.dashboard',
      },
    ],
  },
  {
    id: 'public',
    title: '公共能力',
    subtitle: '跨业务复用：智能诊断、质量验测、代码拉取、校准数据',
    color: 'var(--info)',
    items: [
      {
        key: 'bug-analysis',
        title: '智能诊断',
        tone: 'var(--info)',
        desc: '面向 JIRA / 日志的 Bug 分析。三种启动方式：<span class="hl">单条 JIRA</span>、<span class="hl">JQL 批量</span>、<span class="hl">本地日志</span>；最近任务（内存实时流）与历史任务（磁盘报告）分栏，支持跨列表关键词<span class="hl">搜索</span>。',
        steps: [
          '进入「智能诊断」，选择模式（单条 / 批量 / 本地）。',
          '单条 / 批量需 <span class="hl">JIRA 已配置</span>；本地模式填日志路径与问题描述。',
          '<span class="hl">启动</span>后在「最近任务」看实时进度与对话流。',
          '历史报告在「历史任务」；点<span class="hl">搜索</span>图标可同时过滤最近与历史。',
          '可提炼为知识条目或回写 JIRA 备注。',
        ],
        notes: [
          '最近任务重启后清空；历史任务落盘，可删除。',
          '本地模式跳过 JIRA 拉取与日志下载，完成后不支持备注到 JIRA。',
        ],
        route: 'tahp.bug-analysis',
      },
      {
        key: 'self-check',
        title: '质量验测',
        tone: 'var(--success)',
        desc: '设备侧 AI 自检。四个 Tab：<span class="hl">总览 / 测试执行 / 评审补全 / 测试报告</span>。多设备并行调度，含刷机与 str4 / week / monkey / smoke / GMS / 功耗等用例。执行中可能弹出<span class="hl">人工确认</span>，报告需<span class="hl">人工复核</span>。',
        steps: [
          '进入「质量验测」，先看「总览」确认设备、验测任务与近期任务。',
          '「测试执行」勾选设备与用例后<span class="hl">启动</span>，支持刷机与并行；遇到人工确认按弹窗处理。',
          '「评审补全」处理 Gerrit 相关补测。',
          '「测试报告」审阅并复核结果。',
        ],
        notes: [
          '新增测试大类前须先确认用例对外能力（启动 / 停止 / 状态 / 时长 / 刷机）。',
          '可被适配流水线作为「自检」阶段调用。',
        ],
        route: 'tahp.self-check',
      },
      {
        key: 'code-pull',
        title: '代码拉取',
        tone: 'var(--sky-ic)',
        desc: '在堡垒机上对 system / vendor 分别执行 <span class="hl">repo init</span> 与 <span class="hl">repo sync -c -j64</span>。自动拉起齐治 Bridge / remote-runner，全程免确认；两仓都成功才算完成。',
        steps: [
          '进入「代码拉取」，确认本机命令行工具与堡垒机通道可用（页顶告警<span class="hl-warn">需先处理</span>）。',
          '分别粘贴 System、Vendor 的 repo init 命令。',
          '点击<span class="hl">开始</span>后观察日志；目录约定 /work/code/$USER/code-pull/&lt;runId&gt;/system|vendor。',
          '需要中止时点<span class="hl-warn">取消</span>；历史 run 可从列表重新打开。',
        ],
        notes: [
          '先 system 后 vendor；Windows 下对应映射盘里的同名目录。',
          '本能力只拉代码，不编译、不刷机。',
        ],
        route: 'tahp.code-pull',
      },
      {
        key: 'rf-calib',
        title: '校准数据',
        tone: 'var(--amber-ic)',
        desc: '本机通过 Modem Meta 的 <span class="hl">MetaCLI</span> 备份 / 恢复射频校准数据，等价 GUI「Update Parameter / Read Write Cal Data」，<span class="hl">不必再开 GUI</span>。点开始后 MetaCLI 等待连接，<span class="hl">关机插 USB</span> 即进校准模式。',
        steps: [
          '首次：本机已装 Modem Meta（目录内可见 <span class="hl">META.exe</span>、<code>bin</code>、<code>configs</code>）。到「<span class="hl">配置 → 一键配置 → Modem 工具</span>」填 META.exe <span class="hl">所在目录</span> 并保存，不要填到某个 .exe。',
          '进入「校准数据」，顶部应显示「<span class="hl">Modem Meta 已配置</span>」；未配置时点「前往一键配置」。页内可展开「校准数据操作 SOP」。',
          '备份：模式选「<span class="hl">备份</span>」；进 META 选「Modem Meta 连接方式（推荐）」；COM 保持 <code>Auto Connection</code>；输出文件可留空。点「开始备份」→ 手机关机 → 插 USB。任务「已完成」且日志末尾「备份完成」即成功；默认落盘 <code>reports/rf-calib-meta/&lt;任务ID&gt;/calibration_data.ini</code>。',
          '恢复：模式选「<span class="hl">恢复</span>」，点「选择文件」指定校准 <code>.ini</code>。参数丢失时用其它<span class="hl">同配置机</span>备份，或制造资料盘 <code>\\\\sh-nas\\Dcc\\03.项目文件\\01.项目文件\\01.PCBA项目\\制造资料\\射频校准文件</code>。同样关机插 USB；成功看「已完成」与日志「恢复完成」「Write calibration file done」。',
          '以<span class="hl">任务状态 + 末尾「备份/恢复完成」</span>为准，不要只看 MetaCLI 中间的 Error。IMEI 默认不备份 / 不还原，相关 Failed 会标「已默认跳过」。',
        ],
        notes: [
          '仅 Windows。勿同时按 Vol+ 与 Vol-（会进 Recovery，不是校准 META）。',
          '其它进 META 方式：「已在 META」可选手动/自动 COM；「adb reboot meta」仅部分工程版，非首选。',
          '输出不要填 .tahp-config 下路径，MetaCLI 对带点号的隐藏目录常写失败。',
        ],
        route: 'tahp.rf-calib-meta',
      },
    ],
  },
  {
    id: 'ops',
    title: '运营监控',
    subtitle: '运行数据、评测回归与平台资产观测',
    color: 'var(--warn)',
    items: [
      {
        key: 'evals',
        title: '质量评测',
        tone: 'var(--violet-ic)',
        desc: '回答「改了 Skill / 路由 / 模型之后质量变好还是变坏」。三套评测域：<span class="hl">AI 适配、智能诊断、检索路由</span>；支持评测集管理、批量跑分、导入导出与检索 CI 门禁。',
        steps: [
          '进入「质量评测」，右上角切换评测域（默认 AI 适配）。',
          '「管理评测集」维护用例；可从历史报告生成用例。',
          '「<span class="hl">开始评测</span>」批量跑分，在评测记录中对比两次 run。',
          '检索路由可走 CI 门禁（npm run eval:retrieval:ci）。',
        ],
        notes: [
          '诊断由大模型打分；适配看客观结果；检索走离线比对。',
          '不覆盖整条流水线重跑（适配 → 编译 → 自检）。',
        ],
        route: 'tahp.evals',
      },
      {
        key: 'skills',
        title: 'Skills',
        tone: 'var(--indigo-fg)',
        desc: 'Hermes 业务 Skill 库。三个 Tab：<span class="hl">库浏览 / 自改进 / 同步中心</span>；按功能类型（AI 故障分析 / AI 自动化适配 / AI 自检工具）与模块过滤，查看详情、导入与同步。',
        steps: [
          '进入「Skills」，在「<span class="hl">库浏览</span>」按功能类型 / 模块检索目标 Skill。',
          '点 Skill 查看详情与执行规则。',
          '「<span class="hl">自改进</span>」查看 Agent 新建或改过、尚未固化到工程目录的 Skill。',
          '「<span class="hl">同步中心</span>」从中心拉取 / 同步 Skill 到本机。',
          '改 Skill 后建议用「质量评测」做回归。',
        ],
        notes: [
          '日常用本页管理业务 Skill。',
        ],
        route: 'hermes.skills',
      },
      {
        key: 'chat',
        title: '对话搜索',
        tone: 'var(--rose-ic)',
        desc: 'Hermes 全屏对话。从顶栏「运营监控 → 对话搜索」进入时<span class="hl">每次新建空白对话</span>，不接着上一场。历史会话从左侧列表打开，或用 Ctrl+K 检索。',
        steps: [
          '从「运营监控 → <span class="hl">对话搜索</span>」进入，当前页是一场新对话，可直接提问。',
          '要复盘某次适配 / 诊断，在<span class="hl">左侧会话列表</span>点历史记录；或 Ctrl+K 按关键词搜索后打开。',
          '新对话请写清任务与项目，便于事后在报告 / 评测里追溯。',
        ],
        notes: [
          '业务主路径仍走三大核心工作台，不要用纯对话替代适配 / Modem / GKI 流程。',
        ],
        route: 'hermes.chat',
      },
    ],
  },
]

const sopTone = 'var(--success)'

let observer: IntersectionObserver | null = null
let navPinUntil = 0

function pinNav(key: string) {
  activeKey.value = key
  navPinUntil = Date.now() + 800
}

onMounted(() => {
  observer = new IntersectionObserver(
    (entries) => {
      if (Date.now() < navPinUntil) return
      const visible = entries
        .filter(entry => entry.isIntersecting)
        .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top)
      const top = visible[0]?.target as HTMLElement | undefined
      const key = top?.dataset.manualKey
      if (key) activeKey.value = key
    },
    { root: null, rootMargin: '0px 0px -70% 0px', threshold: [0, 0.25, 0.5, 1] },
  )
  document.querySelectorAll<HTMLElement>('[data-manual-key]').forEach(el => observer?.observe(el))
})

onUnmounted(() => {
  observer?.disconnect()
  observer = null
})
</script>

<template>
  <div class="page page-wide manual-page">
    <div class="manual-layout">
      <aside class="manual-sidebar">
        <nav class="manual-nav" aria-label="手册目录">
          <button
            type="button"
            class="nav-group-title"
            :class="{ active: activeKey === 'pursuit' }"
            :style="toneStyle('var(--violet-ic)')"
            @click="scrollToGroup('pursuit')"
          >
            三大追求
          </button>
          <template v-for="group in groups" :key="group.id">
            <button
              type="button"
              class="nav-group-title"
              :class="{ active: activeKey === group.id }"
              :style="toneStyle(group.color)"
              @click="scrollToGroup(group.id)"
            >
              {{ group.title }}
            </button>
            <button
              v-for="item in group.items"
              :key="item.key"
              type="button"
              class="nav-item"
              :class="{ active: activeKey === item.key }"
              :style="toneStyle(item.tone)"
              @click="scrollToItem(item.key)"
            >
              {{ item.title }}
            </button>
          </template>
          <button
            type="button"
            class="nav-group-title"
            :class="{ active: activeKey === 'config' }"
            :style="toneStyle(sopTone)"
            @click="scrollToGroup('config')"
          >
            配置
          </button>
          <button
            type="button"
            class="nav-item"
            :class="{ active: activeKey === 'sop' }"
            :style="toneStyle(sopTone)"
            @click="scrollToItem('sop')"
          >
            EasyAdapter 配置 SOP
          </button>
        </nav>
      </aside>

      <div class="manual-content">
        <EaPageHead title="EasyAdapter 使用手册" />

        <section
          id="manual-group-pursuit"
          class="manual-intro"
          aria-label="产品理念"
          data-manual-key="pursuit"
        >
          <p class="intro-slogan">可靠+好用+易用，是EasyAdapter追求的目标</p>
          <ul class="intro-traits">
            <li><strong class="trait trait-reliable">可靠——</strong>信任EasyAdapter所做的，它是可并肩而行的伙伴</li>
            <li><strong class="trait trait-handy">好用——</strong>用了就不想换，有适配任务时第一个想到它</li>
            <li><strong class="trait trait-easy">易用——</strong>门槛低，上手快，新人不用学就会，或学一点就会</li>
          </ul>
        </section>

        <EaCard
          v-for="group in groups"
          :id="`manual-group-${group.id}`"
          :key="group.id"
          class="manual-group"
        >
          <header class="group-head" :data-manual-key="group.id">
            <h2 :style="toneStyle(group.color)">{{ group.title }}</h2>
            <p>{{ group.subtitle }}</p>
          </header>

          <article
            v-for="item in group.items"
            :id="`manual-item-${item.key}`"
            :key="item.key"
            class="manual-item"
            :data-manual-key="item.key"
            :style="toneStyle(item.tone)"
          >
            <div class="item-main">
              <h3>{{ item.title }}</h3>
              <p class="item-desc" v-html="item.desc" />

              <ol class="item-steps">
                <li v-for="(step, i) in item.steps" :key="i" v-html="step" />
              </ol>

              <ul v-if="item.notes?.length" class="item-notes">
                <li v-for="(note, i) in item.notes" :key="i">{{ note }}</li>
              </ul>
            </div>
            <button
              type="button"
              class="ea-btn-primary ea-btn-sm item-open"
              @click="openItem(item)"
            >
              打开
            </button>
          </article>
        </EaCard>

        <EaCard id="manual-group-config" class="manual-group">
          <header class="group-head" data-manual-key="config">
            <h2 :style="toneStyle(sopTone)">配置 SOP</h2>
            <p>环境、路径与账号配置步骤在飞书文档中维护，与本手册互补</p>
          </header>
          <article
            id="manual-item-sop"
            class="manual-item"
            data-manual-key="sop"
            :style="toneStyle(sopTone)"
          >
            <div class="item-main">
              <h3>EasyAdapter 配置 SOP</h3>
              <p class="item-desc">首次使用请按以下顺序完成配置（具体参考<span class="hl">飞书 SOP</span>）：</p>
              <ol class="item-steps">
                <li>先在「<span class="hl">配置 → 模型管理</span>」配好模型 Provider 与 API Key；</li>
                <li>再到「<span class="hl">配置 → 一键配置</span>」填齐全部配置项，点击「<span class="hl">保存并启动skill配置检查</span>」；</li>
                <li>Agent 会在同一标签页内依次核对各 Skill；检查完成后可返回修改配置并再次启动检查。</li>
              </ol>
              <p class="item-desc">三步都完成后，再回到本手册中的业务入口操作。</p>
            </div>
            <button
              type="button"
              class="ea-btn-primary ea-btn-sm item-open"
              @click="openUrl(SOP_URL)"
            >
              打开飞书 SOP
            </button>
          </article>
        </EaCard>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.manual-page {
  padding-bottom: 48vh;
  max-width: 1320px;
}

.manual-layout {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr);
  gap: 24px;
  align-items: start;
}

.manual-sidebar {
  position: sticky;
  top: 16px;
  max-height: calc(100vh - 32px);
  overflow: auto;
  padding: 8px 4px 16px 0;
}

.nav-group-title {
  display: block;
  width: 100%;
  text-align: left;
  border: none;
  background: none;
  padding: 4px 10px;
  font-family: inherit;
  font-size: 16px;
  font-weight: 800;
  color: var(--item-tone, var(--accent));
  margin: 20px 0 8px;
  letter-spacing: 0.02em;
  cursor: pointer;
  border-radius: 8px;

  &:first-child {
    margin-top: 0;
  }

  &:hover {
    background: color-mix(in srgb, var(--item-tone, var(--accent)) 10%, transparent);
  }

  &.active {
    background: color-mix(in srgb, var(--item-tone, var(--accent)) 14%, transparent);
  }
}

.nav-item {
  display: block;
  width: 100%;
  text-align: left;
  border: none;
  background: none;
  padding: 6px 10px;
  border-radius: 8px;
  cursor: pointer;
  color: var(--item-tone, var(--text));
  font-family: inherit;
  font-size: 13px;
  font-weight: 600;
  border-left: 2px solid color-mix(in srgb, var(--item-tone, var(--accent)) 45%, transparent);
  transition: color 0.18s, background 0.18s, border-color 0.18s;

  &:hover {
    background: color-mix(in srgb, var(--item-tone, var(--accent)) 10%, transparent);
  }

  &.active {
    color: var(--item-tone, var(--accent));
    background: color-mix(in srgb, var(--item-tone, var(--accent)) 14%, transparent);
    border-left-color: var(--item-tone, var(--accent));
  }
}

.manual-intro {
  margin-bottom: 16px;
  padding: 20px 24px;
  border-radius: 12px;
  border: 1px solid color-mix(in srgb, var(--accent) 18%, var(--line));
  background: linear-gradient(135deg, var(--accent-soft), var(--violet-bg));
  scroll-margin-top: 16px;
}

.intro-slogan {
  margin: 0;
  text-align: center;
  font-size: 18px;
  font-weight: 800;
  letter-spacing: 0.02em;
  color: var(--accent);
}

.intro-traits {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: 16px 0 0;
  padding: 0;
  list-style: none;
  font-size: 13.5px;
  line-height: 1.65;
  color: var(--text);

  li {
    margin: 0;
    padding: 4px 0 4px 10px;
    border-left: 3px solid var(--accent);
  }
}

.trait {
  font-weight: 800;
}

.trait-reliable { color: var(--accent); }
.trait-handy { color: var(--violet-ic); }
.trait-easy { color: var(--success); }

.intro-traits li:nth-child(1) { border-left-color: var(--accent); }
.intro-traits li:nth-child(2) { border-left-color: var(--violet-ic); }
.intro-traits li:nth-child(3) { border-left-color: var(--success); }

.manual-group {
  margin-bottom: 16px;
  scroll-margin-top: 16px;
}

.group-head {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--line);

  h2 {
    margin: 0;
    font-size: 18px;
    font-weight: 800;
    color: var(--item-tone, var(--head));
  }

  p {
    margin: 6px 0 0;
    font-size: 13px;
    color: var(--muted);
  }
}

.manual-item {
  display: flex;
  align-items: flex-start;
  gap: 16px;
  padding: 16px 0;
  border-bottom: 1px solid var(--line);
  scroll-margin-top: 16px;

  &:last-child {
    padding-bottom: 0;
    border-bottom: none;
  }
}

.item-main {
  flex: 1;
  min-width: 0;

  h3 {
    margin: 0;
    font-size: 15.5px;
    font-weight: 700;
    color: var(--item-tone, var(--head));
  }
}

.item-desc {
  margin: 8px 0 0;
  font-size: 13.5px;
  line-height: 1.65;
  color: var(--text);
}

.item-steps {
  margin: 10px 0 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--text);

  li + li {
    margin-top: 4px;
  }
}

.item-notes {
  margin: 10px 0 0;
  padding-left: 16px;
  font-size: 12.5px;
  line-height: 1.65;
  color: var(--muted);
}

.item-open {
  flex-shrink: 0;
  margin-top: 2px;
}

.item-desc :deep(.hl),
.item-steps :deep(.hl) {
  color: var(--accent);
  font-weight: 700;
}

.item-desc :deep(.hl-warn),
.item-steps :deep(.hl-warn) {
  color: var(--warn);
  font-weight: 700;
}

.item-desc :deep(.hl-ok),
.item-steps :deep(.hl-ok) {
  color: var(--success);
  font-weight: 700;
}

@media (max-width: 900px) {
  .intro-traits {
    grid-template-columns: 1fr;
  }

  .manual-layout {
    grid-template-columns: 1fr;
  }

  .manual-sidebar {
    position: static;
    max-height: none;
    overflow: visible;
    padding: 0 0 8px;
  }

  .manual-nav {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }

  .nav-group-title {
    width: 100%;
    margin: 8px 0 0;
  }

  .nav-item {
    width: auto;
    border-left: none;
    border-radius: 999px;
    padding: 6px 12px;
    background: var(--surface);
    border: 1px solid color-mix(in srgb, var(--item-tone, var(--line)) 42%, var(--line));

    &.active {
      border-color: var(--item-tone, var(--accent));
    }
  }
}
</style>
