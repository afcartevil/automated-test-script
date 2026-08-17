<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import EaPageHead from '@/components/layout/EaPageHead.vue'
import EaCard from '@/components/layout/EaCard.vue'

const SOP_URL = 'https://transsioner.feishu.cn/wiki/BdVUwpCL4ifRZckiQlzcPQoUndg'

const router = useRouter()
const activeKey = ref('pipeline')

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
  activeKey.value = key
  document.getElementById(`manual-item-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function scrollToGroup(id: string) {
  const first = id === 'config' ? 'sop' : groups.find(g => g.id === id)?.items[0]?.key
  if (first) activeKey.value = first
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
    subtitle: '面向 Android 大版本升级的底软适配主线能力：流水线编排和功能 / 特性 / 运营商适配调试、Modem / GKI 基线升级',
    color: 'var(--accent)',
    items: [
      {
        key: 'pipeline',
        title: '适配流水线',
        tone: 'var(--accent)',
        desc: '把<span class="hl">选项目 → 拉取前置版本代码 → AI 适配 → 编译 → 烧录 → 自检 → 审核 → 提交 Gerrit</span>串成可自动流转的工作流。各阶段可随时增删；某阶段没准备好时转为<span class="hl">人工处理</span>，不会卡住流程；某步失败后按上一步的产出还在不在，推荐从哪一步接着跑，<span class="hl-warn">避免整条重跑</span>。',
        steps: [
          '进入「适配流水线」，在「<span class="hl">新建运行</span>」选项目与前置版本（需 <span class="hl">EasyAdapter 中心</span>已配置、<span class="hl">Agent Bridge</span> 就绪）。',
          '<span class="hl">启动</span>后在「运行看板」按阶段观察进度。',
          '某阶段<span class="hl-warn">失败</span>按界面推荐的恢复点继续，<span class="hl-warn">不要整条重跑</span>。',
          '「待人工处理」由人工审核通过后<span class="hl">提交 Gerrit</span>。',
          '「流程编排」Tab 可查看 / 调整阶段定义。',
        ],
        notes: [
          '编译、刷机、自检等步骤都复用现有功能，流水线只负责把它们串起来。',
        ],
        route: 'tahp.pipeline',
      },
      {
        key: 'adapt-debug',
        title: 'AI 适配调试',
        tone: 'var(--violet-ic)',
        desc: '基于 <span class="hl">JIRA / 需求</span>的单次适配工作台。按域（通信 / 驱动 / 内核等）填写前置条件，<span class="hl">启动 Agent</span> 产出代码修改与适配报告，可衔接编译、自检与 Gerrit 提交。',
        steps: [
          '进入「AI 适配调试」，选择工作区与业务域（通信 / 驱动 / 内核等）。',
          '可用「<span class="hl">从中心载入前置</span>」按项目号自动填表。',
          '完成必填项后<span class="hl">启动</span>；填完表单后会自动进入运行监控，可看 Agent 过程与文件改动。',
          '完成后到「报告」核对修改清单；需要入库时走<span class="hl">审核</span>与 <span class="hl">Gerrit 提交</span>。',
        ],
        notes: [
          '与流水线的区别：这里偏单次交互调试；流水线把适配与后续验证串成自动流转。',
        ],
        route: 'tahp.adapt-debug',
      },
      {
        key: 'modem',
        title: 'Modem 升级',
        tone: 'var(--amber-ic)',
        desc: 'Modem 基线 Patch 自动合入并提交，<span class="hl">人工审核</span>通过后入库。<span class="hl">任务来自 TONES</span>——TONES 完成 AP 基线升级后经 webhook 把通知推送到 EasyAdapter，操作员在工作台<span class="hl">采用</span>通知并启动分阶段执行。',
        steps: [
          '<span class="hl">TONES</span> 完成 AP 基线升级后经 webhook 推送通知到 EasyAdapter；也可在工作台手动粘贴通知文本。',
          '工作台「<span class="hl">外部通知</span>」列表出现待处理通知，点「<span class="hl">采用</span>」填入。',
          '系统解析通知给出合入仓 / 项目推荐，核对后<span class="hl">启动</span>分阶段执行。',
          '阶段面板跟踪合入、冲突与日志；有冲突按提示处理再继续。',
          '<span class="hl">人工审核</span>通过后<span class="hl-ok">入库</span>；运行历史可回看，环境 / 仓库 / 推送策略在配置中心维护。',
        ],
        notes: [
          '子页：工作台 / 运行历史 / 配置中心。',
          '任务源为 TONES，也可手动粘贴通知。',
        ],
        route: 'tahp.modem-baseline.workbench',
      },
      {
        key: 'gki',
        title: 'GKI 升级',
        tone: 'var(--emerald-ic)',
        desc: 'GKI Patch 质量分析、稳定性验证并选取最优 Tag，自动合入并提交，<span class="hl">人工审核</span>通过后入库。<span class="hl">任务同样来自 TONES</span>，在内嵌的 GKI Patch Tool 工作台中处理。',
        steps: [
          'GKI 升级任务来自 <span class="hl">TONES</span>，在内嵌 GKI Patch Tool 工作台中处理。',
          '进入页面后等待本地服务就绪（首次会拉起），从工作台开始。',
          '「<span class="hl">patch 分析</span>」查看质量与稳定性结论，用于选取最优 Tag。',
          '「故障诊断」处理合入 / 验证中的 crash 与异常。',
          '确认后走「<span class="hl">patch 入库</span>」提交；历史记录在「数据库」，环境在「设置」。',
        ],
        notes: [
          '内嵌工作台，首次进入可能拉起本地服务。',
          '与 Modem 升级同源：任务来自 TONES + 自动合入 + 人工审核入库。',
        ],
        route: 'tahp.gki-patch.dashboard',
      },
    ],
  },
  {
    id: 'public',
    title: '公共能力',
    subtitle: '跨业务复用的诊断、验测与代码拉取能力',
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
        desc: '设备侧 AI 自检。五个 Tab：<span class="hl">总览 / 自动规划 / 测试执行 / 评审补全 / 测试报告</span>。多设备并行调度，含刷机与 str4 / week / custom 等用例；由后台直接调度设备与用例，无需人工介入。',
        steps: [
          '进入「质量验测」，先看「总览」确认设备与近期任务。',
          '「自动规划」按版本 / 改动生成测试计划。',
          '「测试执行」勾选设备与用例后<span class="hl">启动</span>，支持刷机与并行。',
          '「评审补全」处理 Gerrit 相关补测。',
          '「测试报告」审阅结果。',
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
    ],
  },
  {
    id: 'ops',
    title: '运营监控',
    subtitle: '运行数据、评测回归与平台资产观测',
    color: 'var(--warn)',
    items: [
      {
        key: 'reports',
        title: '报告',
        tone: 'var(--warn)',
        desc: '已完成任务的执行报告汇总：适配分析结果、文件修改记录与质量验测审核。支持列表浏览与单任务详情。',
        steps: [
          '进入「报告」查看全部已完成任务。',
          '点一条进入详情，核对 AI 结论与文件改动。',
          '可从详情返回列表，或跳转「AI 适配调试」<span class="hl">启动新任务</span>。',
        ],
        notes: [
          '报告在任务完成后自动生成；空列表表示尚未跑过适配任务。',
        ],
        route: 'tahp.reports',
      },
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
        desc: 'Hermes 业务 Skill 库。<span class="hl">浏览 / 同步</span>两 Tab；按功能类型（AI 故障分析 / AI 自动化适配 / AI 自检工具）与模块过滤，查看详情、导入与同步中心。',
        steps: [
          '进入「Skills」，在「浏览」Tab 按功能类型 / 模块检索目标 Skill。',
          '点 Skill 查看详情与执行规则。',
          '「同步」Tab 用于 Skill 同步中心。',
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
        desc: 'Hermes 对话与会话检索，全屏布局。用于复盘 Agent 过程、定位某次诊断 / 适配的上下文。',
        steps: [
          '进入「对话搜索」，左侧会话列表选择历史会话。',
          '用关键词<span class="hl">检索</span>，打开对应记录查看上下文。',
          '新对话请明确任务与项目信息，便于后续在报告 / 评测中追溯。',
        ],
        notes: [
          '该页占满内容区；业务主路径仍建议走对应工作台而非纯对话。',
        ],
        route: 'hermes.chat',
      },
    ],
  },
]

const sopTone = 'var(--success)'

let observer: IntersectionObserver | null = null

onMounted(() => {
  observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter(entry => entry.isIntersecting)
        .sort((a, b) => b.intersectionRatio - a.intersectionRatio)
      const top = visible[0]?.target as HTMLElement | undefined
      const key = top?.dataset.manualKey
      if (key) activeKey.value = key
    },
    { root: null, rootMargin: '-16% 0px -70% 0px', threshold: [0, 0.25, 0.5, 1] },
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
          <template v-for="group in groups" :key="group.id">
            <button
              type="button"
              class="nav-group-title"
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
        <EaPageHead
          title="EasyAdapter 使用手册"
          subtitle="按导航分区说明三大核心、公共能力与运营监控；每项可直接打开对应页面"
        />

        <EaCard
          v-for="group in groups"
          :id="`manual-group-${group.id}`"
          :key="group.id"
          class="manual-group"
        >
          <header class="group-head">
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
          <header class="group-head">
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
                <li>再到「<span class="hl">配置 → 一键配置表单</span>」按 SOP 填好项目、JIRA、凭据等；</li>
                <li>最后到「<span class="hl">配置 → 常用 Skill 配置</span>」点「<span class="hl">启动 skill 配置检查</span>」，由 Agent 依次核对各 Skill 配置。</li>
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
  padding-bottom: 48px;
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
  padding: 0;
  font-family: inherit;
  font-size: 16px;
  font-weight: 800;
  color: var(--item-tone, var(--accent));
  margin: 20px 8px 8px;
  letter-spacing: 0.02em;
  cursor: pointer;
  border-radius: 6px;

  &:first-child {
    margin-top: 0;
  }

  &:hover {
    filter: brightness(1.08);
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
