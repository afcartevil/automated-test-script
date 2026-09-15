#!/usr/bin/env node
/**
 * 功耗自动化 (tpower_auto) Python 依赖 — 仅在启动功耗测试时检查/安装，不参与 Console 启动。
 * 使用与 BFF 自检相同的 TAHP_PYTHON / py -3 解析逻辑。
 */
import { spawnSync } from 'child_process'
import { existsSync } from 'fs'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'
import { resolvePythonCommand, getSystemPython } from './lib/tahp-paths.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const consoleRoot = resolve(__dirname, '..')

const POWER_REQ_MIN = join(
  consoleRoot,
  'packages/server/src/services/tahp/self-check/python/tools/tpower_auto/requirements-self-check-power-minimal.txt',
)

const POWER_REQ = join(
  consoleRoot,
  'packages/server/src/services/tahp/self-check/python/tools/tpower_auto/requirements-self-check-power.txt',
)

const WIN_REQ = join(
  consoleRoot,
  'packages/server/src/services/tahp/self-check/python/tools/tpower_auto/requirements-win.txt',
)

const SDD_REQ = join(
  consoleRoot,
  'packages/server/src/services/tahp/self-check/python/tools/sdd_test/requirements.txt',
)

/** 冒烟 USD (sdd_test) 启动链路上的关键 import（pip 包名 → import 名） */
const SDD_RUNTIME_IMPORTS = [
  'pytest',
  'PIL',
  'yaml',
  'xmltodict',
  'dateutil',
  'cryptography',
  'pytest_rerunfailures',
  'requests',
]

/** task_proc 启动链路上的关键 import（pip 包名 → import 名） */
const POWER_RUNTIME_IMPORTS = [
  'appdirs',
  'yaml',
  'pandas',
  'openpyxl',
  'openai',
  'uiautomator2',
  'cv2',
  'onnxruntime',
  'ruamel.yaml',
  'psutil',
  'requests',
  'deprecated',
  'func_timeout',
  'PIL',
  'numpy',
  'scipy',
  'mss',
  'thrift',
  'serial',
  'Crypto',
]

function log(msg) {
  console.log(msg)
}

function warn(msg) {
  console.warn(msg)
}

function pipInstall(python, reqFile, label) {
  if (!existsSync(reqFile)) {
    warn(`  ⚠ 未找到依赖清单: ${reqFile}`)
    return false
  }
  const { command, prefixArgs } = resolvePythonCommand(python)
  log(`  → pip install -r ${label} ...`)
  const result = spawnSync(
    command,
    [...prefixArgs, '-m', 'pip', 'install', '-r', reqFile],
    { stdio: 'inherit', cwd: consoleRoot, env: process.env },
  )
  return result.status === 0
}

function verifyImport(python, moduleName) {
  const { command, prefixArgs } = resolvePythonCommand(python)
  const result = spawnSync(
    command,
    [...prefixArgs, '-c', `import ${moduleName}`],
    { encoding: 'utf-8', windowsHide: true },
  )
  return result.status === 0
}

function listMissingPowerImports(python) {
  return POWER_RUNTIME_IMPORTS.filter((mod) => !verifyImport(python, mod))
}

export function ensureSelfCheckPythonDeps(options = {}) {
  const { quiet = false, forTest = false } = options
  const python = getSystemPython()

  if (process.env.TAHP_SKIP_POWER_DEPS === '1') {
    if (!quiet) warn('  ⚠ 已跳过（TAHP_SKIP_POWER_DEPS=1）')
    return { ok: true, skipped: true }
  }

  let missing = listMissingPowerImports(python)
  if (missing.length === 0) {
    if (!quiet) log(`  ✓ 功耗自动化依赖已就绪 (${python})`)
    return { ok: true, ready: true }
  }

  if (!quiet) {
    log('功耗自动化 Python 依赖\n')
    log(`  → 缺少: ${missing.join(', ')}`)
    log(`  → 正在安装 (${python})...`)
  }

  const okMinimal = pipInstall(python, POWER_REQ_MIN, 'requirements-self-check-power-minimal.txt')
  if (!okMinimal) {
    return { ok: false, error: '最小依赖安装失败，请检查网络或重试功耗测试' }
  }

  missing = listMissingPowerImports(python)
  if (missing.length === 0 && process.env.TAHP_POWER_DEPS_MINIMAL_ONLY === '1') {
    if (!quiet) log(`  ✓ 已安装最小依赖（TAHP_POWER_DEPS_MINIMAL_ONLY=1）`)
    return { ok: true }
  }

  const okPower = pipInstall(python, POWER_REQ, 'requirements-self-check-power.txt')
  let okWin = true
  if (process.platform === 'win32' && existsSync(WIN_REQ)) {
    okWin = pipInstall(python, WIN_REQ, 'requirements-win.txt')
  }

  if (!okPower || !okWin) {
    return {
      ok: false,
      error: '完整依赖 pip install 失败，请检查网络后重试功耗测试，或执行: npm run setup:power',
    }
  }

  missing = listMissingPowerImports(python)
  if (missing.length > 0) {
    return {
      ok: false,
      error: `安装后仍缺少: ${missing.join(', ')}（解释器: ${python}）`,
    }
  }

  if (!quiet) log(`  ✓ 功耗自动化 Python 依赖已安装 (${python})`)
  return { ok: true }
}

/** 功耗测试模块启动前调用（非 EasyAdapter / Console 启动路径） */
export function ensureSelfCheckPythonDepsForPowerTest(options = {}) {
  return ensureSelfCheckPythonDeps({ ...options, forTest: true, quiet: options.quiet ?? false })
}

function listMissingSddImports(python) {
  return SDD_RUNTIME_IMPORTS.filter((mod) => !verifyImport(python, mod))
}

/** 冒烟 USD (sdd_test) 启动前检查/安装依赖（pytest 等框架包从未自动安装过，缺失会导致 si_run 秒崩、无 SDD_report.json） */
export function ensureSddPythonDeps(options = {}) {
  const { quiet = false } = options
  const python = getSystemPython()

  if (process.env.TAHP_SKIP_SDD_DEPS === '1') {
    if (!quiet) warn('  ⚠ 已跳过（TAHP_SKIP_SDD_DEPS=1）')
    return { ok: true, skipped: true }
  }

  let missing = listMissingSddImports(python)
  if (missing.length === 0) {
    if (!quiet) log(`  ✓ 冒烟 USD 依赖已就绪 (${python})`)
    return { ok: true, ready: true }
  }

  if (!quiet) {
    log('冒烟 USD (sdd_test) Python 依赖\n')
    log(`  → 缺少: ${missing.join(', ')}`)
    log(`  → 正在安装 (${python})...`)
  }

  if (!pipInstall(python, SDD_REQ, 'sdd_test/requirements.txt')) {
    return { ok: false, error: '冒烟 USD 依赖 pip install 失败，请检查网络后重试冒烟测试' }
  }

  missing = listMissingSddImports(python)
  if (missing.length > 0) {
    return { ok: false, error: `安装后仍缺少: ${missing.join(', ')}（解释器: ${python}）` }
  }

  if (!quiet) log(`  ✓ 冒烟 USD Python 依赖已安装 (${python})`)
  return { ok: true }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const forTest = process.argv.includes('--for-test')
  const forSdd = process.argv.includes('--for-sdd')
  const result = forSdd
    ? ensureSddPythonDeps({ quiet: false })
    : ensureSelfCheckPythonDeps({ quiet: false, forTest })
  process.exit(result.ok ? 0 : 1)
}
