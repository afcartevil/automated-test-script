#!/usr/bin/env node
/**
 * GKI Patch Tool 依赖 — 在 EasyAdapter 启动前检查/安装 Python venv 与前端构建产物。
 * 供 npm run setup:gki-patch / ensure-startup-deps / run_adapter.bat 调用。
 */
import { spawnSync } from 'child_process'
import { existsSync, readFileSync, rmSync } from 'fs'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'
import {
  getConsoleRoot,
  getGkiPatchToolRoot,
  getSystemPython,
  getTahpProjectRoot,
  getVenvPython,
  pythonCommandSupportsHermes,
  resolvePythonCommand,
} from './lib/tahp-paths.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))

const RUNTIME_IMPORTS = [
  { module: 'fastapi', label: 'fastapi' },
  { module: 'uvicorn', label: 'uvicorn' },
  { module: 'yaml', label: 'PyYAML' },
  { module: 'httpx', label: 'httpx' },
  { module: 'paramiko', label: 'paramiko' },
  { module: 'openpyxl', label: 'openpyxl' },
]

function log(msg) {
  console.log(msg)
}

function warn(msg) {
  console.warn(msg)
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

function listMissingImports(python) {
  return RUNTIME_IMPORTS.filter((item) => !verifyImport(python, item.module))
}

function removeVenvDir(venvDir) {
  if (!existsSync(venvDir)) return true
  try {
    rmSync(venvDir, { recursive: true, force: true, maxRetries: 3, retryDelay: 200 })
    return !existsSync(venvDir)
  } catch (err) {
    warn(`  ⚠ 删除 ${venvDir} 失败: ${err?.message || err}`)
    if (process.platform === 'win32') {
      const r = spawnSync('cmd.exe', ['/c', 'rmdir', '/s', '/q', venvDir], { windowsHide: true })
      return r.status === 0 && !existsSync(venvDir)
    }
    return false
  }
}

function venvNeedsRecreate(toolRoot, venvPython) {
  const venvDir = join(toolRoot, '.venv')
  if (!existsSync(venvDir) || !existsSync(venvPython)) return true
  if (!pythonCommandSupportsHermes(venvPython)) {
    warn('  ⚠ GKI Patch .venv 解释器不可用或版本不在 3.11-3.13，将重建')
    return true
  }
  const cfgPath = join(venvDir, 'pyvenv.cfg')
  if (!existsSync(cfgPath)) return false
  try {
    const cfg = readFileSync(cfgPath, 'utf-8')
    const exePath = cfg.match(/^executable\s*=\s*(.+)$/m)?.[1]?.trim()
    const baseHome = cfg.match(/^home\s*=\s*(.+)$/m)?.[1]?.trim()
    if ((exePath && !existsSync(exePath)) || (baseHome && !existsSync(baseHome))) {
      warn(`  ⚠ GKI Patch .venv 指向已不存在的 Python: ${exePath || baseHome}`)
      return true
    }
    const ver = cfg.match(/^version\s*=\s*(.+)$/m)?.[1]?.trim() || ''
    if (/^3\.1[4-9]\b|^3\.[2-9]\d\b/.test(ver)) {
      warn(`  ⚠ GKI Patch .venv 基于 Python ${ver}，需要 3.11-3.13，将重建`)
      return true
    }
  } catch { /* ignore */ }
  return false
}

function ensureVenv(toolRoot, systemPython, quiet) {
  const venvDir = join(toolRoot, '.venv')
  const venvPython = getVenvPython(toolRoot)
  if (venvNeedsRecreate(toolRoot, venvPython)) {
    if (existsSync(venvDir)) {
      if (!quiet) log('  → 删除损坏或版本不匹配的 GKI Patch .venv ...')
      if (!removeVenvDir(venvDir)) {
        warn('  ⚠ 无法删除 GKI Patch .venv，请手动删除 tools\\gki-patch-tool\\.venv 后重试')
        return null
      }
    }
  } else if (existsSync(venvPython)) {
    return venvPython
  }

  if (!quiet) log(`  → 创建 GKI Patch 虚拟环境: ${venvDir}`)
  const { command, prefixArgs } = resolvePythonCommand(systemPython)
  const result = spawnSync(
    command,
    [...prefixArgs, '-m', 'venv', venvDir],
    { stdio: quiet ? 'pipe' : 'inherit', cwd: toolRoot, env: process.env },
  )
  if (result.status !== 0 || !existsSync(venvPython)) {
    return null
  }
  return venvPython
}

function pipInstall(python, reqFile, quiet) {
  if (!existsSync(reqFile)) {
    warn(`  ⚠ 未找到依赖清单: ${reqFile}`)
    return false
  }
  const { command, prefixArgs } = resolvePythonCommand(python)
  spawnSync(
    command,
    [...prefixArgs, '-m', 'pip', 'install', '--upgrade', 'pip<26', 'setuptools', 'wheel'],
    { stdio: quiet ? 'pipe' : 'inherit', cwd: dirname(reqFile), env: process.env },
  )
  if (!quiet) log(`  → pip install -r requirements.txt ...`)
  const result = spawnSync(
    command,
    [...prefixArgs, '-m', 'pip', 'install', '-r', reqFile],
    { stdio: quiet ? 'pipe' : 'inherit', cwd: dirname(reqFile), env: process.env },
  )
  return result.status === 0
}

function ensurePythonDeps(toolRoot, options = {}) {
  const { quiet = false } = options
  const systemPython = getSystemPython()
  if (!pythonCommandSupportsHermes(systemPython)) {
    return {
      ok: false,
      error: 'GKI Patch 需要 Python 3.11-3.13 正式版（不要使用 3.14）。请设置 TAHP_PYTHON 后重试: npm run setup:gki-patch',
    }
  }
  const python = ensureVenv(toolRoot, systemPython, quiet)
  if (!python) {
    return { ok: false, error: 'GKI Patch Python 虚拟环境创建失败' }
  }

  let missing = listMissingImports(python)
  if (missing.length === 0) {
    return { ok: true, ready: true, python }
  }

  if (!quiet) {
    log('GKI Patch Tool Python 依赖')
    log(`  → 解释器: ${python}`)
    log(`  → 缺少: ${missing.map((item) => item.label).join(', ')}`)
  }

  const reqFile = join(toolRoot, 'requirements.txt')
  const installed = pipInstall(python, reqFile, quiet)
  if (!installed) {
    return {
      ok: false,
      error: 'GKI Patch Python 依赖安装失败，请检查网络后重试: npm run setup:gki-patch',
      python,
    }
  }

  missing = listMissingImports(python)
  if (missing.length > 0) {
    return {
      ok: false,
      error: `GKI Patch 安装后仍缺少: ${missing.map((item) => item.label).join(', ')}（解释器: ${python}）`,
      python,
    }
  }

  return { ok: true, python, installed: true }
}

function frontendDistExists(toolRoot) {
  return existsSync(join(toolRoot, 'frontend', 'dist', 'index.html'))
}

function runNpm(cwd, args, quiet) {
  const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm'
  return spawnSync(npmCmd, args, {
    stdio: quiet ? 'pipe' : 'inherit',
    cwd,
    env: process.env,
    shell: process.platform === 'win32',
  })
}

function ensureFrontendBuilt(toolRoot, options = {}) {
  const { quiet = false, force = false } = options
  const frontendDir = join(toolRoot, 'frontend')

  if (!existsSync(join(frontendDir, 'package.json'))) {
    return { ok: false, error: `未找到 GKI Patch 前端目录: ${frontendDir}` }
  }

  if (!force && frontendDistExists(toolRoot)) {
    return { ok: true, ready: true }
  }

  if (!quiet) log('GKI Patch Tool 前端构建')

  if (!existsSync(join(frontendDir, 'node_modules'))) {
    if (!quiet) log('  → npm install (frontend) ...')
    const installResult = runNpm(frontendDir, ['install'], quiet)
    if (installResult.status !== 0) {
      return { ok: false, error: 'GKI Patch 前端 npm install 失败' }
    }
  }

  if (!quiet) log('  → npm run build (frontend) ...')
  const buildResult = runNpm(frontendDir, ['run', 'build'], quiet)
  if (buildResult.status !== 0) {
    return { ok: false, error: 'GKI Patch 前端 npm run build 失败' }
  }

  if (!frontendDistExists(toolRoot)) {
    return { ok: false, error: 'GKI Patch 前端构建产物缺失: frontend/dist/index.html' }
  }

  return { ok: true, built: true }
}

export function ensureGkiPatchDeps(options = {}) {
  const { quiet = false, skipFrontend = false, forceFrontend = false } = options

  if (process.env.TAHP_SKIP_GKI_PATCH_DEPS === '1') {
    if (!quiet) warn('  ⚠ GKI Patch 依赖已跳过（TAHP_SKIP_GKI_PATCH_DEPS=1）')
    return { ok: true, skipped: true }
  }

  const consoleRoot = getConsoleRoot(__dirname)
  const projectRoot = getTahpProjectRoot(consoleRoot)
  const toolRoot = getGkiPatchToolRoot(projectRoot)

  if (!existsSync(join(toolRoot, 'web_app', 'app.py'))) {
    return {
      ok: false,
      error: `未找到 GKI Patch Tool: ${toolRoot}`,
    }
  }

  const pythonResult = ensurePythonDeps(toolRoot, { quiet })
  if (!pythonResult.ok) return pythonResult

  if (skipFrontend) {
    if (!quiet) {
      if (frontendDistExists(toolRoot)) {
        log(`  ✓ GKI Patch Python 依赖已就绪 (${pythonResult.python})`)
      } else {
        warn('  ⚠ GKI Patch 前端尚未构建，进入页面时将提示手动构建')
      }
    }
    return { ok: true, python: pythonResult.python, frontendBuilt: frontendDistExists(toolRoot) }
  }

  const frontendResult = ensureFrontendBuilt(toolRoot, { quiet, force: forceFrontend })
  if (!frontendResult.ok) {
    return {
      ...frontendResult,
      python: pythonResult.python,
    }
  }

  if (!quiet) {
    log(`  ✓ GKI Patch Tool 依赖已就绪 (${pythonResult.python})`)
  }

  return {
    ok: true,
    python: pythonResult.python,
    frontendBuilt: true,
    toolRoot,
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const forceFrontend = process.argv.includes('--force-frontend')
  const result = ensureGkiPatchDeps({ quiet: false, forceFrontend })
  if (!result.ok) {
    console.error(`  ✗ ${result.error}`)
    process.exit(1)
  }
  process.exit(0)
}
