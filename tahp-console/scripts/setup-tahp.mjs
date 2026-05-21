#!/usr/bin/env node
/**
 * TAHP Console setup — 校验运行环境.
 *   1. Node.js >= 20
 *   2. Python 3 可用 (用于 tahp-mcp-server)
 *   3. TAHP 项目根目录可定位
 *   4. tahp-mcp-server 依赖已安装 (尝试导入 mcp)
 */
import { execSync, spawnSync } from 'child_process'
import { existsSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const consoleDir = resolve(__dirname, '..')
const defaultProjectRoot = resolve(consoleDir, '..')

const projectRoot = process.env.TAHP_PROJECT_ROOT
  ? resolve(process.env.TAHP_PROJECT_ROOT)
  : defaultProjectRoot

const python = process.env.TAHP_PYTHON || (process.platform === 'win32' ? 'python' : 'python3')

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
const py = spawnSync(python, ['--version'], { encoding: 'utf-8' })
if (py.status === 0) {
  const ver = (py.stdout || py.stderr || '').trim()
  pass(`${ver} (${python})`)
} else {
  fail(`未找到 ${python}。请安装 Python 3.10+ 或设 TAHP_PYTHON 环境变量`)
}

// 3. TAHP 项目根
const mcpServerPath = resolve(projectRoot, 'tahp-mcp-server', 'server.py')
if (existsSync(mcpServerPath)) pass(`TAHP 项目根: ${projectRoot}`)
else fail(`未找到 ${mcpServerPath}。请确认 TAHP_PROJECT_ROOT (默认是 console 上级目录)`)

// 4. tahp-mcp-server 依赖
if (existsSync(mcpServerPath)) {
  const req = spawnSync(python, ['-c', 'import mcp,yaml; print("ok")'], { encoding: 'utf-8' })
  if (req.status === 0 && req.stdout.includes('ok')) {
    pass('Python 依赖 mcp / pyyaml 已就绪')
  } else {
    const reqFile = resolve(projectRoot, 'requirements.txt')
    if (existsSync(reqFile)) {
      warn(`Python 依赖未就绪，请执行: ${python} -m pip install -r ${reqFile}`)
    } else {
      warn(`Python 依赖未就绪 (mcp / pyyaml)，请按需 pip install`)
    }
  }
}

// 5. node_modules
if (existsSync(resolve(consoleDir, 'node_modules'))) pass('node_modules 已安装')
else warn('node_modules 不存在，请执行: npm install')

console.log('')
if (ok) {
  console.log('✓ 环境检查通过')
  process.exit(0)
} else {
  console.log('✗ 存在问题，请根据上面的提示修复')
  process.exit(1)
}
