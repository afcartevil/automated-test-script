#!/usr/bin/env node
/**
 * package-lock.json 未变且 node_modules 存在时跳过 npm install。
 * 若 package.json 声明的 dependencies 有缺失（如 systray2 未写入 lock），仍会执行 install。
 */
import { createHash } from 'crypto'
import { spawnSync } from 'child_process'
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'fs'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'
import { findMissingDependencies } from './lib/required-npm-deps.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = resolve(__dirname, '..')
const lockPath = join(root, 'package-lock.json')
const stampDir = join(root, '.tahp')
const stampPath = join(stampDir, 'npm-install.stamp')
const logPrefix = '[EasyAdapter]'

function lockFingerprint() {
  return createHash('sha256').update(readFileSync(lockPath)).digest('hex')
}

function removeIncompletePackages(names) {
  for (const name of names) {
    const pkgDir = join(root, 'node_modules', name)
    if (!existsSync(join(pkgDir, 'package.json'))) continue
    console.log(`${logPrefix} 依赖 ${name} 安装不完整，删除后重新安装…`)
    rmSync(pkgDir, { recursive: true, force: true })
  }
}

function runNpmInstall() {
  const isWin = process.platform === 'win32'
  const result = spawnSync(isWin ? 'npm.cmd' : 'npm', ['install'], {
    cwd: root,
    stdio: 'inherit',
    shell: isWin,
  })
  if (result.status !== 0) process.exit(result.status ?? 1)

  if (existsSync(lockPath)) {
    mkdirSync(stampDir, { recursive: true })
    writeFileSync(stampPath, `${lockFingerprint()}\n`, 'utf-8')
  }
}

function main() {
  const missing = findMissingDependencies(root)

  if (!existsSync(lockPath)) {
    console.log(`${logPrefix} 未找到 package-lock.json，执行 npm install…`)
  } else if (!existsSync(join(root, 'node_modules'))) {
    console.log(`${logPrefix} 首次运行，正在安装 npm 依赖…`)
  } else if (missing.length > 0) {
    console.log(
      `${logPrefix} 检测到缺失依赖 (${missing.join(', ')})，执行 npm install…`,
    )
  } else if (existsSync(stampPath) && readFileSync(stampPath, 'utf-8').trim() === lockFingerprint()) {
    console.log(`${logPrefix} npm 依赖已同步（package-lock 未变），跳过 install`)
    process.exit(0)
  } else {
    console.log(`${logPrefix} 同步 npm 依赖（package-lock 有变更）…`)
  }

  removeIncompletePackages(missing)
  runNpmInstall()

  const stillMissing = findMissingDependencies(root)
  if (stillMissing.length > 0) {
    console.error(
      `${logPrefix} npm install 后仍缺少依赖: ${stillMissing.join(', ')}`,
    )
    console.error('  请检查网络与 npm 源，或在 tahp-console 目录手动执行: npm install')
    process.exit(1)
  }
}

main()
