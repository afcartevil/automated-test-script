#!/usr/bin/env node
/**
 * 源码指纹未变且 dist/server/index.js 存在时跳过 npm run build。
 * 供 run_adapter.bat 在守护进程启动前调用。
 */
import { createHash } from 'crypto'
import { spawnSync } from 'child_process'
import { existsSync, mkdirSync, readdirSync, readFileSync, statSync, writeFileSync } from 'fs'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = resolve(__dirname, '..')
const stampDir = join(root, '.tahp')
const stampPath = join(stampDir, 'build.stamp')
const distEntry = join(root, 'dist', 'server', 'index.js')
const logPrefix = '[EasyAdapter]'

const WATCH_EXTENSIONS = new Set(['.ts', '.tsx', '.vue', '.js', '.mjs', '.scss', '.sass', '.css', '.html', '.json', '.py'])
const WATCH_FILES = [
  'package.json',
  'package-lock.json',
  'vite.config.ts',
  'vite.config.website.ts',
  'scripts/build-server.mjs',
  'bin/easyadapter-tray.mjs',
  'scripts/lib/tray-actions.mjs',
  'scripts/lib/tray-launcher.mjs',
  'scripts/win/run-adapter-hidden.vbs',
  'packages/server/tsconfig.json',
  'tsconfig.json',
  'tsconfig.app.json',
  'tsconfig.node.json',
]
const WATCH_DIRS = [
  'packages/client',
  'packages/server/src',
]
const CASE_CONFIG_DIR = 'packages/server/src/services/tahp/self-check/case_config'

const SKIP_DIR_NAMES = new Set(['node_modules', '.git', 'dist', '.tahp'])

function walkDir(dir, files = []) {
  if (!existsSync(dir)) return files
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (SKIP_DIR_NAMES.has(entry.name)) continue
      walkDir(full, files)
      continue
    }
    if (!entry.isFile()) continue
    const dot = entry.name.lastIndexOf('.')
    const ext = dot >= 0 ? entry.name.slice(dot).toLowerCase() : ''
    if (WATCH_EXTENSIONS.has(ext)) files.push(full)
  }
  return files
}

function computeFingerprint() {
  const hash = createHash('sha256')
  for (const rel of WATCH_FILES) {
    const full = join(root, rel)
    if (!existsSync(full)) continue
    const st = statSync(full)
    hash.update(`${rel}:${st.mtimeMs}:${st.size}\n`)
  }
  for (const rel of WATCH_DIRS) {
    const files = walkDir(join(root, rel))
    files.sort()
    for (const full of files) {
      const relPath = full.slice(root.length + 1).replace(/\\/g, '/')
      const st = statSync(full)
      hash.update(`${relPath}:${st.mtimeMs}:${st.size}\n`)
    }
  }
  const caseConfigDir = join(root, CASE_CONFIG_DIR)
  if (existsSync(caseConfigDir)) {
    for (const name of readdirSync(caseConfigDir).sort()) {
      if (!name.toLowerCase().endsWith('.json')) continue
      const full = join(caseConfigDir, name)
      if (!statSync(full).isFile()) continue
      const st = statSync(full)
      hash.update(`${CASE_CONFIG_DIR}/${name}:${st.mtimeMs}:${st.size}\n`)
    }
  }
  return hash.digest('hex')
}

function runBuild() {
  const isWin = process.platform === 'win32'
  const nodeOptions = [
    process.env.NODE_OPTIONS?.trim(),
    '--max-old-space-size=8192',
  ].filter(Boolean).join(' ')
  const result = spawnSync(isWin ? 'npm.cmd' : 'npm', ['run', 'build'], {
    cwd: root,
    stdio: 'inherit',
    shell: isWin,
    env: { ...process.env, NODE_OPTIONS: nodeOptions },
  })
  if (result.status !== 0) process.exit(result.status ?? 1)
}

function main() {
  const fingerprint = computeFingerprint()

  if (!existsSync(distEntry)) {
    console.log(`${logPrefix} 未找到生产构建，正在执行 npm run build…`)
  } else if (existsSync(stampPath) && readFileSync(stampPath, 'utf-8').trim() === fingerprint) {
    console.log(`${logPrefix} 生产构建已最新，跳过 build`)
    process.exit(0)
  } else {
    console.log(`${logPrefix} 源码或依赖有变更，正在执行 npm run build…`)
  }

  runBuild()
  mkdirSync(stampDir, { recursive: true })
  writeFileSync(stampPath, `${fingerprint}\n`, 'utf-8')
}

main()
