#!/usr/bin/env node
/**
 * Skill 脚本 Python 依赖 — 安装到 Hermes Agent venv（Agent 执行 skill CLI 时使用）。
 * 在 npm run setup / 启动前可选检查中调用。
 */
import { spawnSync } from 'child_process'
import { existsSync } from 'fs'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'
import { applyHermesAgentEnvFromDisk } from './ensure-hermes-agent.mjs'
import {
  getBundledHermesAgentDir,
  getConsoleRoot,
  getSystemPython,
  getTahpProjectRoot,
  getVenvPython,
  resolvePythonCommand,
} from './lib/tahp-paths.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))

/** skill / 随仓依赖 → 相对 TAHP 项目根的 requirements.txt */
const SKILL_REQUIREMENTS = [
  {
    id: 'checklist-scmp-sync',
    req: 'tahp-console/packages/server/src/services/tahp/checklist-scmp-sync/requirements.txt',
    imports: ['httpx', 'cryptography'],
  },
  {
    id: 'tones-scmp',
    req: 'skills/.claude/skills/tones-scmp/scripts/requirements.txt',
    imports: ['httpx', 'cryptography'],
  },
]

function log(msg) {
  console.log(msg)
}

function warn(msg) {
  console.warn(msg)
}

function resolveSkillPython() {
  const agent = applyHermesAgentEnvFromDisk()
  if (agent.ok && agent.paths?.python) return agent.paths.python
  if (process.env.HERMES_AGENT_BRIDGE_PYTHON?.trim()) {
    return process.env.HERMES_AGENT_BRIDGE_PYTHON.trim()
  }
  const consoleRoot = getConsoleRoot(__dirname)
  const agentDir = getBundledHermesAgentDir(getTahpProjectRoot(consoleRoot))
  if (agentDir) {
    const venvPy = getVenvPython(agentDir)
    if (existsSync(venvPy)) return venvPy
  }
  return getSystemPython()
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
    { stdio: 'inherit', env: process.env },
  )
  return result.status === 0
}

function skillNeedsInstall(python, skill) {
  return skill.imports.some((mod) => !verifyImport(python, mod))
}

export function ensureSkillPythonDeps(options = {}) {
  const { quiet = false } = options

  if (process.env.TAHP_SKIP_SKILL_DEPS === '1') {
    if (!quiet) warn('  ⚠ Skill Python 依赖已跳过（TAHP_SKIP_SKILL_DEPS=1）')
    return { ok: true, skipped: true }
  }

  const consoleRoot = getConsoleRoot(__dirname)
  const projectRoot = getTahpProjectRoot(consoleRoot)
  const python = resolveSkillPython()

  const pending = SKILL_REQUIREMENTS.filter((skill) => {
    const reqFile = join(projectRoot, skill.req)
    return existsSync(reqFile) && skillNeedsInstall(python, skill)
  })

  if (pending.length === 0) {
    if (!quiet) log(`  ✓ Skill Python 依赖已就绪 (${python})`)
    return { ok: true, ready: true, python }
  }

  if (!quiet) {
    log('Skill Python 依赖\n')
    log(`  → 解释器: ${python}`)
    log(`  → 待安装: ${pending.map((s) => s.id).join(', ')}`)
  }

  for (const skill of pending) {
    const reqFile = join(projectRoot, skill.req)
    const ok = pipInstall(python, reqFile, `${skill.id}/requirements.txt`)
    if (!ok) {
      return {
        ok: false,
        error: `${skill.id} 依赖安装失败，请检查网络后重试: npm run setup:skills`,
        python,
      }
    }
    const stillMissing = skill.imports.filter((mod) => !verifyImport(python, mod))
    if (stillMissing.length > 0) {
      return {
        ok: false,
        error: `${skill.id} 安装后仍缺少: ${stillMissing.join(', ')}（解释器: ${python}）`,
        python,
      }
    }
  }

  if (!quiet) log(`  ✓ Skill Python 依赖已安装 (${python})`)
  return { ok: true, python, installed: pending.map((s) => s.id) }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = ensureSkillPythonDeps({ quiet: false })
  process.exit(result.ok ? 0 : 1)
}
