/**
 * 首次启动：非阻塞提醒 + 静默写入默认 terminal 配置。
 * 完整交互向导仅通过 --wizard / --wizard-only 显式触发。
 */
import { spawnSync } from 'child_process'
import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'fs'
import { homedir } from 'os'
import { join } from 'path'
import { getAgentStateDir } from './tahp-paths.mjs'

/** 与 hermes_cli/doctor.py _PROVIDER_ENV_HINTS 对齐 */
const PROVIDER_ENV_HINTS = [
  'OPENROUTER_API_KEY',
  'OPENAI_API_KEY',
  'ANTHROPIC_API_KEY',
  'ANTHROPIC_TOKEN',
  'OPENAI_BASE_URL',
  'NOUS_API_KEY',
  'GLM_API_KEY',
  'ZAI_API_KEY',
  'Z_AI_API_KEY',
  'KIMI_API_KEY',
  'KIMI_CN_API_KEY',
  'GMI_API_KEY',
  'MINIMAX_API_KEY',
  'MINIMAX_CN_API_KEY',
  'KILOCODE_API_KEY',
  'DEEPSEEK_API_KEY',
  'DASHSCOPE_API_KEY',
  'HF_TOKEN',
  'OPENCODE_ZEN_API_KEY',
  'OPENCODE_GO_API_KEY',
  'XIAOMI_API_KEY',
  'TOKENHUB_API_KEY',
  'TAHP_API_KEY',
  'TAHP_LLM_UPSTREAM',
]

export function detectHermesHome() {
  if (process.env.HERMES_HOME?.trim()) return process.env.HERMES_HOME.trim()
  if (process.platform === 'win32') {
    const local = process.env.LOCALAPPDATA || process.env.APPDATA
    if (local) return join(local, 'hermes')
  }
  return join(homedir(), '.hermes')
}

function readActiveProfile(hermesHome) {
  const activeFile = join(hermesHome, 'active_profile')
  if (!existsSync(activeFile)) return 'default'
  try {
    const name = readFileSync(activeFile, 'utf-8').trim()
    return name || 'default'
  } catch {
    return 'default'
  }
}

function resolveProfileConfigPaths(hermesHome) {
  const profile = readActiveProfile(hermesHome)
  if (!profile || profile === 'default') {
    return [join(hermesHome, 'config.yaml')]
  }
  return [
    join(hermesHome, 'profiles', profile, 'config.yaml'),
    join(hermesHome, 'config.yaml'),
  ]
}

function configHasTerminalBackend(content) {
  return /terminal:\s*[\s\S]*?\n\s+backend:\s*["']?\w+/m.test(content)
    || /terminal:\s*\{[^}]*backend:/s.test(content)
}

/**
 * 等价于在「Quick setup」里选 Local，但不启动交互式 hermes setup terminal。
 */
export function ensureDefaultTerminalBackend(hermesHome = detectHermesHome()) {
  const paths = resolveProfileConfigPaths(hermesHome)
  for (const configPath of paths) {
    if (!existsSync(configPath)) continue
    let content
    try {
      content = readFileSync(configPath, 'utf-8')
    } catch {
      continue
    }
    if (configHasTerminalBackend(content)) {
      return { applied: false, reason: 'already-set', configPath }
    }
    const block = [
      '',
      '# TAHP first-run: default terminal backend (local, non-interactive)',
      'terminal:',
      '  backend: local',
      '  cwd: "."',
    ].join('\n')
    writeFileSync(configPath, `${content.trimEnd()}${block}\n`, 'utf-8')
    return { applied: true, configPath }
  }
  return { applied: false, reason: 'no-config-file' }
}

function envFileHasProviderConfig(envPath) {
  if (!existsSync(envPath)) return false
  let content
  try {
    content = readFileSync(envPath, 'utf-8')
  } catch {
    return false
  }
  return PROVIDER_ENV_HINTS.some((key) => {
    const re = new RegExp(`^${key}\\s*=\\s*\\S+`, 'm')
    return re.test(content)
  })
}

function configYamlHasProviderKey(hermesHome) {
  for (const configPath of resolveProfileConfigPaths(hermesHome)) {
    if (!existsSync(configPath)) continue
    try {
      const content = readFileSync(configPath, 'utf-8')
      if (/custom_providers:[\s\S]*?api_key:\s*\S+/m.test(content)) return true
    } catch { /* ignore */ }
  }
  return false
}

export function hasLlmConfigured(hermesHome = detectHermesHome(), agentDir) {
  if (envFileHasProviderConfig(join(hermesHome, '.env'))) return true
  const profile = readActiveProfile(hermesHome)
  if (envFileHasProviderConfig(join(hermesHome, 'profiles', profile, '.env'))) return true
  if (agentDir && envFileHasProviderConfig(join(agentDir, '.env'))) return true
  if (configYamlHasProviderKey(hermesHome)) return true
  if (process.env.TAHP_API_KEY?.trim() || process.env.TAHP_LLM_UPSTREAM?.trim()) return true
  if (process.env.ANTHROPIC_API_KEY?.trim() || process.env.OPENROUTER_API_KEY?.trim()) return true
  return false
}

export function getHermesSetupDoneFile(consoleRoot) {
  return join(getAgentStateDir(consoleRoot), 'hermes-setup.done')
}

export function isHermesSetupMarkedDone(consoleRoot) {
  return existsSync(getHermesSetupDoneFile(consoleRoot))
}

export function markHermesSetupDone(consoleRoot, meta = {}) {
  const dir = getAgentStateDir(consoleRoot)
  mkdirSync(dir, { recursive: true })
  writeFileSync(
    getHermesSetupDoneFile(consoleRoot),
    `${JSON.stringify({ completedAt: new Date().toISOString(), ...meta }, null, 2)}\n`,
    'utf-8',
  )
}

function getFirstLaunchReminderFile(consoleRoot) {
  return join(getAgentStateDir(consoleRoot), 'first-launch-reminder.done')
}

export function isInteractiveTerminal() {
  return Boolean(process.stdin.isTTY && process.stdout.isTTY)
}

function printFirstLaunchReminders({ hermesHome, hermesBin, hasLlm, terminalApplied, quiet }) {
  if (quiet) return
  const hermesBinHint = hermesBin && existsSync(hermesBin) ? hermesBin : 'hermes'

  console.log('')
  console.log('─'.repeat(60))
  console.log('  TAHP 首次启动提示（不阻塞，服务将继续启动）')
  console.log('─'.repeat(60))

  if (terminalApplied) {
    console.log('  ✓ 已写入默认终端后端: terminal.backend = local')
    console.log('    （等同 Quick setup 默认值；未运行交互式 hermes setup terminal）')
  } else {
    console.log('  · 终端后端: 已在 config.yaml 中配置，未改动')
  }

  console.log('')
  if (hasLlm) {
    console.log('  ✓ 已检测到 LLM / API 配置，可直接使用 Agent 与对话功能')
  } else {
    console.log('  ⚠ 尚未检测到 API Key，请先配置后再使用 Agent / 对话：')
    console.log('      推荐: 浏览器 → 系统 → 模型管理 → 添加提供商并保存')
    console.log(`      可选: ${hermesBinHint} setup`)
    console.log(`      可选: ${hermesBinHint} setup model   （仅配置模型与 Key）`)
  }

  console.log('')
  console.log('  可选高级配置（需在终端手动执行，会进入交互菜单）：')
  console.log(`    ${hermesBinHint} setup terminal   # Docker / SSH 等执行环境`)
  console.log(`    ${hermesBinHint} setup            # 完整 Hermes 向导`)
  console.log('')
  console.log(`  Hermes 配置目录: ${hermesHome}`)
  console.log('─'.repeat(60))
  console.log('')
}

/**
 * 首次启动非阻塞初始化：默认 terminal + 终端提醒。
 * @returns {{ ok: true, reminders?: boolean, terminal?: object }}
 */
export function runFirstLaunchHermesInit({
  consoleRoot,
  agentDir,
  hermesBin,
  quiet = false,
}) {
  if (process.env.TAHP_SKIP_HERMES_SETUP_WIZARD === '1') {
    return { ok: true, skipped: true, reason: 'TAHP_SKIP_HERMES_SETUP_WIZARD' }
  }

  const hermesHome = detectHermesHome()
  const hasLlm = hasLlmConfigured(hermesHome, agentDir)
  const firstReminderDone = existsSync(getFirstLaunchReminderFile(consoleRoot))

  let terminal = { applied: false }
  if (!firstReminderDone || !configYamlHasTerminalBackendAnywhere(hermesHome)) {
    terminal = ensureDefaultTerminalBackend(hermesHome)
  }

  const shouldRemind = !quiet && !firstReminderDone
  if (shouldRemind) {
    printFirstLaunchReminders({
      hermesHome,
      hermesBin,
      hasLlm,
      terminalApplied: terminal.applied,
      quiet,
    })
    mkdirSync(getAgentStateDir(consoleRoot), { recursive: true })
    writeFileSync(
      getFirstLaunchReminderFile(consoleRoot),
      `${JSON.stringify({ shownAt: new Date().toISOString() }, null, 2)}\n`,
      'utf-8',
    )
  } else if (!quiet && !hasLlm) {
    console.warn('')
    console.warn('  ⚠ 仍未检测到 LLM API Key — 请在 Web UI「模型管理」中配置后再使用 Agent')
    console.warn('')
  }

  if (hasLlm && !isHermesSetupMarkedDone(consoleRoot)) {
    markHermesSetupDone(consoleRoot, { source: 'detected-existing-config' })
  }

  return { ok: true, reminders: shouldRemind, terminal, hasLlm }
}

function configYamlHasTerminalBackendAnywhere(hermesHome) {
  for (const configPath of resolveProfileConfigPaths(hermesHome)) {
    if (!existsSync(configPath)) continue
    try {
      if (configHasTerminalBackend(readFileSync(configPath, 'utf-8'))) return true
    } catch { /* ignore */ }
  }
  return false
}

/**
 * 显式触发的交互式 hermes setup（会阻塞，仅 --wizard-only / --wizard）。
 */
export function runInteractiveHermesSetupWizard({
  consoleRoot,
  agentDir,
  hermesBin,
  quiet = false,
  force = false,
}) {
  const log = quiet ? () => {} : (m) => console.log(m)
  const warn = quiet ? () => {} : (m) => console.warn(m)

  if (!force && (isHermesSetupMarkedDone(consoleRoot) || hasLlmConfigured(detectHermesHome(), agentDir))) {
    if (!quiet) log('  Hermes 已配置，使用 --wizard 可强制重跑交互向导')
    return { ran: false, ok: true, skipped: true, reason: 'already-configured' }
  }

  if (!hermesBin || !existsSync(hermesBin)) {
    warn('  ⚠ 未找到 hermes，无法运行交互向导')
    return { ran: false, ok: false, reason: 'no-hermes-bin' }
  }

  if (!isInteractiveTerminal()) {
    warn('  ⚠ 非交互终端，无法运行 hermes setup')
    return { ran: false, ok: false, reason: 'non-interactive' }
  }

  log('')
  log('  启动交互式 hermes setup（完成后返回）...')
  log('')

  const hermesHome = detectHermesHome()
  const env = {
    ...process.env,
    HERMES_HOME: hermesHome,
    HERMES_AGENT_ROOT: agentDir,
    PYTHONUNBUFFERED: '1',
  }

  const result = spawnSync(hermesBin, ['setup'], {
    cwd: agentDir,
    env,
    stdio: 'inherit',
    windowsHide: false,
  })

  const exitCode = result.status ?? 1
  if (hasLlmConfigured(hermesHome, agentDir)) {
    markHermesSetupDone(consoleRoot, { source: 'hermes-setup-wizard', exitCode })
  }
  return { ran: true, ok: exitCode === 0 || hasLlmConfigured(hermesHome, agentDir), exitCode }
}

/**
 * @deprecated 名称保留；默认走非阻塞首次初始化。
 */
export function runHermesSetupOnFirstLaunch(opts) {
  if (opts.forceWizard) {
    return runInteractiveHermesSetupWizard(opts)
  }
  return runFirstLaunchHermesInit(opts)
}
