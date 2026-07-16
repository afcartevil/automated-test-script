#!/usr/bin/env node
/**
 * TAHP Console setup — 校验运行环境.
 *   1. Node.js >= 20
 *   2. Python 3 可用 (用于 hermes-agent-main)
 *   3. TAHP 项目根目录可定位 (skills / knowledge-base)
 *   4. 仓库内 hermes-agent-main 初始化（venv + Agent 环境变量）
 */
import { spawnSync } from 'child_process'
import { existsSync } from 'fs'
import { resolve, dirname, join } from 'path'
import { fileURLToPath } from 'url'
import { ensureHermesAgent } from './ensure-hermes-agent.mjs'
import { ensureSkillPythonDeps } from './ensure-skill-python-deps.mjs'
import { ensureGkiPatchDeps } from './ensure-gki-patch-deps.mjs'
import { getBundledHermesAgentDir, getSystemPython, getTahpProjectRoot, resolvePythonCommand } from './lib/tahp-paths.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const consoleDir = resolve(__dirname, '..')
const projectRoot = getTahpProjectRoot(consoleDir)

const python = getSystemPython()

const checks = []
let ok = true

function pass(msg) { console.log(`  ✓ ${msg}`); checks.push(['pass', msg]) }
function warn(msg) { console.log(`  ⚠ ${msg}`); checks.push(['warn', msg]) }
function fail(msg) { console.log(`  ✗ ${msg}`); checks.push(['fail', msg]); ok = false }

console.log('TAHP Console 环境检查\n')

// 1. Node
const nodeMajor = parseInt(process.versions.node.split('.')[0], 10)
if (nodeMajor >= 20) pass(`Node.js ${process.version}`)
else fail(`Node.js ${process.version} 过低，要求 >= 20`)

// 2. Python
const { command: pyCmd, prefixArgs: pyPrefix } = resolvePythonCommand(python)
const py = spawnSync(pyCmd, [...pyPrefix, '--version'], { encoding: 'utf-8' })
if (py.status === 0) {
  const ver = (py.stdout || py.stderr || '').trim()
  pass(`${ver} (${python})`)
} else {
  fail(`未找到 ${python}。请安装 Python 3.10+ 或设 TAHP_PYTHON 环境变量`)
}

// 3. TAHP 项目根
const hasSkills = existsSync(join(projectRoot, 'skills', '.claude', 'skills'))
const hasKb = existsSync(join(projectRoot, 'knowledge-base'))
if (hasSkills || hasKb) pass(`TAHP 项目根: ${projectRoot}`)
else fail(`未找到 TAHP 工程标记 (skills/ 或 knowledge-base/)。请确认 TAHP_PROJECT_ROOT`)

// 4. node_modules
if (existsSync(resolve(consoleDir, 'node_modules'))) pass('node_modules 已安装')
else warn('node_modules 不存在，请执行: npm install')

// 5. Bundled hermes-agent-main
console.log('')
const bundledDir = getBundledHermesAgentDir(projectRoot)
if (bundledDir) {
  console.log('Hermes Agent（仓库内置）\n')
  const agentResult = ensureHermesAgent({ quiet: false })
  if (agentResult.ok) pass('hermes-agent-main 已就绪')
  else {
    fail(agentResult.error || 'hermes-agent-main 初始化失败')
  }
} else {
  warn(`未找到 ${join(projectRoot, 'hermes-agent-main')}，Agent Bridge 功能将不可用`)
}

// 6. Skill 脚本依赖（tones-scmp 等）
console.log('')
console.log('Skill Python 依赖\n')
const skillDeps = ensureSkillPythonDeps({ quiet: false })
if (skillDeps.ok) {
  if (!skillDeps.skipped) pass('Skill Python 依赖已就绪')
} else {
  warn(skillDeps.error || 'Skill Python 依赖安装失败（特性适配 SCMP 查询可能不可用）')
}

// 7. GKI Patch Tool 依赖
console.log('')
console.log('GKI Patch Tool 依赖\n')
const gkiPatchDeps = ensureGkiPatchDeps({ quiet: false })
if (gkiPatchDeps.ok) {
  if (!gkiPatchDeps.skipped) pass('GKI Patch Tool 依赖已就绪')
} else {
  warn(gkiPatchDeps.error || 'GKI Patch Tool 依赖安装失败（GKI Patch 页面可能不可用）')
}

// 8. 功耗自动化依赖（启动功耗测试时自动安装，不参与 Console 启动）
pass('功耗自动化依赖在启动功耗测试时自动检查/安装')

console.log('')
if (ok) {
  console.log('✓ 环境检查通过')
  process.exit(0)
} else {
  console.log('✗ 存在问题，请根据上面的提示修复')
  process.exit(1)
}
