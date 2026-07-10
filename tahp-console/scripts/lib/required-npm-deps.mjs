/**
 * 校验 package.json 声明的 dependencies 是否已落到 node_modules。
 * 用于 npm-install-if-needed：lock 未变但缺包时仍触发 npm install。
 */
import { existsSync, readFileSync } from 'fs'
import { dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))

export function getConsoleRoot(fromDir = __dirname) {
  return resolve(fromDir, '..', '..')
}

/**
 * @param {string} consoleRoot tahp-console 根目录
 * @returns {string[]} package.json dependencies 的 key 列表
 */
export function listDeclaredDependencies(consoleRoot = getConsoleRoot()) {
  const pkgPath = join(consoleRoot, 'package.json')
  if (!existsSync(pkgPath)) return []
  try {
    const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8'))
    return Object.keys(pkg.dependencies || {})
  } catch {
    return []
  }
}

/**
 * @param {string} consoleRoot
 * @returns {string[]} 在 package.json 中声明但 node_modules 中缺失的包名
 */
export function findMissingDependencies(consoleRoot = getConsoleRoot()) {
  const missing = []
  for (const name of listDeclaredDependencies(consoleRoot)) {
    const installed = join(consoleRoot, 'node_modules', name, 'package.json')
    if (!existsSync(installed)) missing.push(name)
  }
  return missing
}

/** Windows 托盘等启动路径强依赖的包（缺失时优先提示） */
export const TRAY_RUNTIME_PACKAGES = ['systray2']

/**
 * @param {string} consoleRoot
 * @returns {string[]} 托盘相关缺失包
 */
export function findMissingTrayPackages(consoleRoot = getConsoleRoot()) {
  return TRAY_RUNTIME_PACKAGES.filter((name) => {
    const installed = join(consoleRoot, 'node_modules', name, 'package.json')
    return !existsSync(installed)
  })
}
