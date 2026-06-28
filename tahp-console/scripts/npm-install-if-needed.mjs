#!/usr/bin/env node
/**
 * package-lock.json 未变且 node_modules 存在时跳过 npm install。
 */
import { createHash } from 'crypto'
import { spawnSync } from 'child_process'
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'fs'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = resolve(__dirname, '..')
const lockPath = join(root, 'package-lock.json')
const stampDir = join(root, '.tahp')
const stampPath = join(stampDir, 'npm-install.stamp')

function lockFingerprint() {
  return createHash('sha256').update(readFileSync(lockPath)).digest('hex')
}

if (!existsSync(lockPath)) {
  console.log('[EasyAdapter] 未找到 package-lock.json，执行 npm install…')
} else if (!existsSync(join(root, 'node_modules'))) {
  console.log('[EasyAdapter] 首次运行，正在安装 npm 依赖…')
} else if (existsSync(stampPath) && readFileSync(stampPath, 'utf-8').trim() === lockFingerprint()) {
  console.log('[EasyAdapter] npm 依赖已同步（package-lock 未变），跳过 install')
  process.exit(0)
} else {
  console.log('[EasyAdapter] 同步 npm 依赖（package-lock 有变更）…')
}

const isWin = process.platform === 'win32'
const result = spawnSync(isWin ? 'npm.cmd' : 'npm', ['install'], {
  cwd: root,
  stdio: 'inherit',
  shell: isWin,
})

if (result.status !== 0) {
  process.exit(result.status ?? 1)
}

if (existsSync(lockPath)) {
  mkdirSync(stampDir, { recursive: true })
  writeFileSync(stampPath, `${lockFingerprint()}\n`, 'utf-8')
}
