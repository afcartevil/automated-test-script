#!/usr/bin/env node
/**
 * 确保仓库内 hermes-agent-main 已安装 venv 并写入 Agent 环境变量。
 * 在 npm run dev / tahp-console start / setup 时调用。
 */
import { spawnSync } from 'child_process'
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'fs'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'
import {
  getAgentPathsFile,
  getAgentStateDir,
  getBundledHermesAgentDir,
  getConsoleRoot,
  getSystemPython,
  getTahpProjectRoot,
  getVenvHermesBin,
  getVenvPython,
  resolvePythonCommand,
} from './lib/tahp-paths.mjs'
import {
  detectHermesHome,
  runFirstLaunchHermesInit,
  runInteractiveHermesSetupWizard,
} from './lib/hermes-setup-wizard.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))

const MARKER_VERSION = 1

function log(msg) {
  console.log(msg)
}

function warn(msg) {
  console.warn(msg)
}

function fail(msg) {
  console.error(msg)
}

function loadDotEnv(consoleRoot) {
  const envPath = join(consoleRoot, '.env')
  if (!existsSync(envPath)) return
  const lines = readFileSync(envPath, 'utf-8').split(/\r?\n/)
  for (const line of lines) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const eq = trimmed.indexOf('=')
    if (eq <= 0) continue
    const key = trimmed.slice(0, eq).trim()
    let val = trimmed.slice(eq + 1).trim()
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
      val = val.slice(1, -1)
    }
    if (process.env[key] === undefined) process.env[key] = val
  }
}

function run(cmd, args, opts = {}) {
  const result = spawnSync(cmd, args, {
    encoding: 'utf-8',
    stdio: opts.inherit ? 'inherit' : 'pipe',
    windowsHide: true,
    ...opts,
  })
  return result
}

function runPython(pythonSpec, args, opts = {}) {
  const { command, prefixArgs } = resolvePythonCommand(pythonSpec)
  return run(command, [...prefixArgs, ...args], opts)
}

function pythonMeetsMinimum(python) {
  const r = runPython(python, ['-c', 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'])
  return r.status === 0
}

function isVenvPythonUsable(pythonPath) {
  if (!pythonPath || !existsSync(pythonPath)) return false
  const r = run(pythonPath, ['--version'])
  return r.status === 0
}

/** 从其他机器拷贝的 .venv 常指向不存在的 base Python（如 C:\\Python313\\python.exe） */
function venvNeedsRecreate(agentDir, venvPython) {
  const venvDir = join(agentDir, '.venv')
  if (!existsSync(venvDir)) return true
  if (!existsSync(venvPython)) return true
  if (!isVenvPythonUsable(venvPython)) {
    warn('  ⚠ 检测到损坏的 .venv（常见于跨电脑拷贝），将用本机 Python 重建')
    return true
  }
  const cfgPath = join(venvDir, 'pyvenv.cfg')
  if (existsSync(cfgPath)) {
    try {
      const cfg = readFileSync(cfgPath, 'utf-8')
      const exeMatch = cfg.match(/^executable\s*=\s*(.+)$/m)
      const exePath = exeMatch?.[1]?.trim()
      if (exePath && !existsSync(exePath)) {
        warn(`  ⚠ .venv 指向已不存在的 Python: ${exePath}`)
        warn('    将重建虚拟环境（请勿跨电脑拷贝 hermes-agent-main/.venv）')
        return true
      }
      const homeMatch = cfg.match(/^home\s*=\s*(.+)$/m)
      const baseHome = homeMatch?.[1]?.trim()
      if (baseHome && !existsSync(baseHome)) {
        warn('    将重建虚拟环境（请勿跨电脑拷贝 hermes-agent-main/.venv）')
        return true
      }
    } catch { /* ignore */ }
  }
  return false
}

function removeVenvDir(venvDir) {
  if (!existsSync(venvDir)) return true
  try {
    rmSync(venvDir, { recursive: true, force: true, maxRetries: 3, retryDelay: 200 })
    return !existsSync(venvDir)
  } catch (err) {
    warn(`  ⚠ 删除 ${venvDir} 失败: ${err?.message || err}`)
    if (process.platform === 'win32') {
      const r = run('cmd.exe', ['/c', 'rmdir', '/s', '/q', venvDir])
      return r.status === 0 && !existsSync(venvDir)
    }
    return false
  }
}

function finishOptionalFailure(opts, msg, extra = {}) {
  if (opts.optional) {
    warn('')
    warn('  ⚠ Agent 环境未就绪，Web UI 仍将启动（Bridge / Bug 分析 / 适配 Agent 暂不可用）')
    warn('    与 API Key 无关；修复 Agent venv 请执行: npm run setup:agent -- --force')
    warn(`    详情: ${msg}`)
    warn('')
    return { ok: false, optional: true, error: msg, ...extra }
  }
  return { ok: false, error: msg, ...extra }
}

function verifyAgentImport(python, agentDir) {
  const r = run(
    python,
    ['-c', 'from run_agent import AIAgent; print("ok")'],
    {
      cwd: agentDir,
      env: {
        ...process.env,
        PYTHONPATH: agentDir,
      },
    },
  )
  return r.status === 0 && (r.stdout || '').includes('ok')
}

function readAgentPaths(consoleRoot) {
  const file = getAgentPathsFile(consoleRoot)
  if (!existsSync(file)) return null
  try {
    return JSON.parse(readFileSync(file, 'utf-8'))
  } catch {
    return null
  }
}

function writeAgentPaths(consoleRoot, data) {
  const stateDir = getAgentStateDir(consoleRoot)
  mkdirSync(stateDir, { recursive: true })
  writeFileSync(getAgentPathsFile(consoleRoot), `${JSON.stringify(data, null, 2)}\n`, 'utf-8')
}

function mergeConsoleEnv(consoleRoot, entries) {
  const envPath = join(consoleRoot, '.env')
  const header = '# --- TAHP bundled hermes-agent (auto-generated) ---'
  const footer = '# --- end TAHP bundled hermes-agent ---'
  let content = existsSync(envPath) ? readFileSync(envPath, 'utf-8') : ''
  const start = content.indexOf(header)
  const end = content.indexOf(footer)
  const block = [
    header,
    ...Object.entries(entries).map(([k, v]) => `${k}=${v}`),
    footer,
    '',
  ].join('\n')
  if (start >= 0 && end > start) {
    content = `${content.slice(0, start)}${block}${content.slice(end + footer.length).replace(/^\n+/, '')}`
  } else {
    content = `${content.trimEnd()}\n\n${block}`
  }
  writeFileSync(envPath, content, 'utf-8')
}

function applyToProcessEnv(paths) {
  process.env.HERMES_AGENT_ROOT = paths.agentRoot
  process.env.HERMES_AGENT_BRIDGE_PYTHON = paths.python
  if (paths.hermesBin && existsSync(paths.hermesBin)) {
    process.env.HERMES_BIN = paths.hermesBin
  }
}

function ensureHermesUserConfig(agentDir) {
  const hermesHome = detectHermesHome()
  mkdirSync(hermesHome, { recursive: true })
  const configPath = join(hermesHome, 'config.yaml')
  if (!existsSync(configPath)) {
    const example = join(agentDir, 'cli-config.yaml.example')
    if (existsSync(example)) {
      copyFileSync(example, configPath)
      log(`  ✓ 已创建 Hermes 配置: ${configPath}`)
      log('    （首次启动将提示在「模型管理」配置 API Key；见下方说明）')
    } else {
      warn(`  ⚠ 未找到 config 模板，请稍后运行 hermes setup 或于控制台配置模型`)
    }
  } else {
    log(`  ✓ Hermes 配置已存在: ${configPath}`)
  }

  const agentEnv = join(agentDir, '.env')
  const agentEnvExample = join(agentDir, '.env.example')
  if (!existsSync(agentEnv) && existsSync(agentEnvExample)) {
    copyFileSync(agentEnvExample, agentEnv)
    log(`  ✓ 已创建 ${agentEnv}（可按需填入 API Key）`)
  }
}

function installDependencies(python, agentDir, { full = false } = {}) {
  log('  → 升级 pip...')
  run(python, ['-m', 'pip', 'install', '--upgrade', 'pip', 'setuptools', 'wheel'], { inherit: true, cwd: agentDir })

  const uv = process.env.UV || (process.platform === 'win32' ? 'uv.exe' : 'uv')
  const hasUv = run(uv, ['--version']).status === 0
  const hasLock = existsSync(join(agentDir, 'uv.lock'))

  if (full && hasUv && hasLock) {
    log('  → 使用 uv sync 安装完整依赖（可能需数分钟）...')
    const sync = run(
      uv,
      ['sync', '--extra', 'all', '--locked'],
      {
        inherit: true,
        cwd: agentDir,
        env: {
          ...process.env,
          UV_PROJECT_ENVIRONMENT: join(agentDir, '.venv'),
          UV_NO_CONFIG: '1',
        },
      },
    )
    if (sync.status === 0) return true
    warn('  ⚠ uv sync 失败，回退到 pip install -e .')
  }

  log('  → pip install -e . （核心 Agent 依赖）...')
  const pip = run(python, ['-m', 'pip', 'install', '-e', '.'], { inherit: true, cwd: agentDir })
  return pip.status === 0
}

function createVenv(systemPython, agentDir) {
  const venvDir = join(agentDir, '.venv')
  if (existsSync(venvDir)) {
    log('  → 删除旧 .venv 后重建...')
    if (!removeVenvDir(venvDir)) {
      fail('  ✗ 无法删除旧 .venv，请手动删除 hermes-agent-main\\.venv 后重试')
      return false
    }
  }
  log(`  → 创建虚拟环境: ${venvDir}`)
  const r = runPython(systemPython, ['-m', 'venv', venvDir], { inherit: true, cwd: agentDir })
  if (r.status !== 0) return false
  const py = getVenvPython(agentDir)
  if (!isVenvPythonUsable(py)) {
    fail('  ✗ venv 创建后仍不可用，请检查 TAHP_PYTHON 指向 Python 3.11–3.13')
    return false
  }
  return true
}

/**
 * @param {{ force?: boolean, full?: boolean, quiet?: boolean }} opts
 * @returns {{ ok: boolean, skipped?: boolean, paths?: object, error?: string }}
 */
export function ensureHermesAgent(opts = {}) {
  if (process.env.TAHP_SKIP_AGENT_SETUP === '1') {
    applyHermesAgentEnvFromDisk()
    return { ok: true, skipped: true }
  }

  const consoleRoot = getConsoleRoot()
  const tahpRoot = getTahpProjectRoot(consoleRoot)
  loadDotEnv(consoleRoot)

  if (!opts.quiet) {
    log('')
    log('TAHP Hermes Agent 环境检查')
    log('─'.repeat(40))
  }

  const agentDir = getBundledHermesAgentDir(tahpRoot)
  if (!agentDir) {
    const msg = `未在 TAHP 根目录找到 hermes-agent-main（需要 run_agent.py）。\n  期望路径: ${join(tahpRoot, 'hermes-agent-main')}`
    fail(`  ✗ ${msg}`)
    return finishOptionalFailure(opts, msg)
  }

  if (!opts.quiet) log(`  ✓ Agent 源码: ${agentDir}`)

  const cached = readAgentPaths(consoleRoot)
  const venvPython = getVenvPython(agentDir)
  const hermesBin = getVenvHermesBin(agentDir)

  if (
    !opts.force
    && cached?.version === MARKER_VERSION
    && cached.agentRoot === agentDir
    && isVenvPythonUsable(cached.python)
    && verifyAgentImport(cached.python, agentDir)
  ) {
    if (!opts.quiet) log('  ✓ Agent 环境已就绪（跳过安装）')
    applyToProcessEnv(cached)
    const init = opts.forceWizard
      ? runInteractiveHermesSetupWizard({
        consoleRoot,
        agentDir,
        hermesBin: cached.hermesBin || hermesBin,
        quiet: opts.quiet,
        force: true,
      })
      : runFirstLaunchHermesInit({
        consoleRoot,
        agentDir,
        hermesBin: cached.hermesBin || hermesBin,
        quiet: opts.quiet,
      })
    if (opts.forceWizard && !init.ok) {
      return { ok: false, error: 'Hermes setup 向导失败', paths: cached }
    }
    if (!opts.quiet) log('─'.repeat(40))
    return { ok: true, skipped: true, paths: cached, init }
  }

  const systemPython = getSystemPython()
  if (!opts.quiet) log(`  → 系统 Python: ${systemPython}`)
  const pyVer = runPython(systemPython, ['--version'])
  if (pyVer.status !== 0) {
    const msg = `未找到 Python。请安装 Python 3.11+ 并设置 TAHP_PYTHON。`
    fail(`  ✗ ${msg}`)
    return finishOptionalFailure(opts, msg)
  }
  if (!opts.quiet) log(`  ✓ ${(pyVer.stdout || pyVer.stderr || '').trim()}`)
  if (!pythonMeetsMinimum(systemPython)) {
    const msg = '需要 Python 3.11 或更高版本（hermes-agent 要求）。'
    fail(`  ✗ ${msg}`)
    return finishOptionalFailure(opts, msg)
  }

  const py314Check = runPython(systemPython, ['-c', 'import sys; raise SystemExit(0 if sys.version_info < (3, 14) else 1)'])
  if (py314Check.status !== 0) {
    warn('  ⚠ 当前为 Python 3.14+，hermes-agent 官方测试以 3.11–3.13 为主；若安装失败请安装 3.12 并设 TAHP_PYTHON')
  }

  if (venvNeedsRecreate(agentDir, venvPython) || opts.force) {
    if (!createVenv(systemPython, agentDir)) {
      const msg = '创建 .venv 失败'
      fail(`  ✗ ${msg}`)
      return finishOptionalFailure(opts, msg)
    }
  }

  const activeVenvPython = getVenvPython(agentDir)
  if (!installDependencies(activeVenvPython, agentDir, { full: opts.full })) {
    const msg = 'pip 安装 hermes-agent 失败'
    fail(`  ✗ ${msg}`)
    return finishOptionalFailure(opts, msg)
  }

  if (!verifyAgentImport(activeVenvPython, agentDir)) {
    const msg = '安装后仍无法 import run_agent.AIAgent'
    fail(`  ✗ ${msg}`)
    return finishOptionalFailure(opts, msg)
  }

  if (!opts.quiet) log('  ✓ run_agent.AIAgent 导入成功')

  ensureHermesUserConfig(agentDir)

  const paths = {
    version: MARKER_VERSION,
    agentRoot: agentDir,
    python: activeVenvPython,
    hermesBin: existsSync(hermesBin) ? hermesBin : undefined,
    readyAt: new Date().toISOString(),
  }
  writeAgentPaths(consoleRoot, paths)
  mergeConsoleEnv(consoleRoot, {
    HERMES_AGENT_ROOT: agentDir,
    HERMES_AGENT_BRIDGE_PYTHON: activeVenvPython,
    ...(paths.hermesBin ? { HERMES_BIN: paths.hermesBin } : {}),
  })
  applyToProcessEnv(paths)

  if (!opts.quiet) {
    log('  ✓ 已写入 .tahp/agent-paths.json 与 tahp-console/.env')
  }

  const init = opts.forceWizard
    ? runInteractiveHermesSetupWizard({
      consoleRoot,
      agentDir,
      hermesBin: paths.hermesBin || hermesBin,
      quiet: opts.quiet,
      force: true,
    })
    : runFirstLaunchHermesInit({
      consoleRoot,
      agentDir,
      hermesBin: paths.hermesBin || hermesBin,
      quiet: opts.quiet,
    })
  if (opts.forceWizard && !init.ok) {
    return { ok: false, error: 'Hermes setup 向导失败', paths }
  }

  if (!opts.quiet) {
    log('')
    warn('  可选完整依赖: npm run setup:agent -- --full')
    warn('  交互式向导: npm run setup:agent -- --wizard')
    log('─'.repeat(40))
  }

  return { ok: true, paths, init }
}

/** 将已缓存路径注入当前进程（不触发安装） */
export function applyHermesAgentEnvFromDisk() {
  const consoleRoot = getConsoleRoot()
  loadDotEnv(consoleRoot)
  if (process.env.HERMES_AGENT_ROOT?.trim()) return { ok: true, source: 'env' }
  const cached = readAgentPaths(consoleRoot)
  if (cached?.agentRoot && cached?.python) {
    applyToProcessEnv(cached)
    return { ok: true, source: 'cache', paths: cached }
  }
  const agentDir = getBundledHermesAgentDir(getTahpProjectRoot(consoleRoot))
  if (agentDir && existsSync(getVenvPython(agentDir))) {
    const paths = {
      agentRoot: agentDir,
      python: getVenvPython(agentDir),
      hermesBin: getVenvHermesBin(agentDir),
    }
    applyToProcessEnv(paths)
    return { ok: true, source: 'bundled-venv', paths }
  }
  return { ok: false }
}

const isMain = process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))

if (isMain) {
  const force = process.argv.includes('--force')
  const full = process.argv.includes('--full')
  const forceWizard = process.argv.includes('--wizard')
  const wizardOnly = process.argv.includes('--wizard-only')
  const optional = process.argv.includes('--optional')
  if (wizardOnly) {
    const consoleRoot = getConsoleRoot()
    loadDotEnv(consoleRoot)
    const agentDir = getBundledHermesAgentDir(getTahpProjectRoot(consoleRoot))
    const hermesBin = process.env.HERMES_BIN || (agentDir ? getVenvHermesBin(agentDir) : 'hermes')
    const wizard = runInteractiveHermesSetupWizard({
      consoleRoot,
      agentDir,
      hermesBin,
      force: true,
    })
    process.exit(wizard.ok ? 0 : 1)
  }
  const result = ensureHermesAgent({ force, full, forceWizard, optional })
  process.exit(result.ok || result.optional ? 0 : 1)
}
