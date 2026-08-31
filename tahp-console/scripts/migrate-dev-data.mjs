#!/usr/bin/env node
/**
 * 将 dev 模式本地数据迁移到守护进程目录（~/.tahp-console），仅补缺不覆盖。
 * 供 run_adapter.bat 在 stop 之后、start 之前调用。
 */
import { copyFileSync, existsSync, mkdirSync, readdirSync, statSync, writeFileSync } from 'fs'
import { homedir } from 'os'
import { basename, dirname, join, resolve } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const consoleRoot = resolve(__dirname, '..')
const logPrefix = '[EasyAdapter]'

const DB_FILES = [
  'hermes-web-ui.db',
  'hermes-web-ui.db-wal',
  'hermes-web-ui.db-shm',
  'hermes-web-ui.json',
]

const ROOT_FILES = [
  'config.json',
  '.credentials',
  '.token',
  '.login-lock.json',
]

const MERGE_DIRS = ['upload', 'media']

/** 运行时业务数据（外部通知等），迁到 {consoleHome}/data/… */
const RUNTIME_DATA_DIRS = ['gki-patch', 'modem-patch', 'modem-baseline']

function getTargetHome() {
  if (process.env.TAHP_CONSOLE_HOME?.trim()) {
    return resolve(process.env.TAHP_CONSOLE_HOME.trim())
  }
  return join(homedir(), '.tahp-console')
}

function getSourceDirs() {
  const sources = []
  const distDataDir = join(consoleRoot, 'dist', 'data')
  if (existsSync(distDataDir)) {
    sources.push({ label: 'dist 数据目录', dir: distDataDir })
  }
  const devDataDir = join(consoleRoot, 'packages', 'server', 'data')
  if (existsSync(devDataDir)) {
    sources.push({ label: 'dev 数据目录', dir: devDataDir })
  }
  const legacyHome = join(homedir(), '.hermes-web-ui')
  if (existsSync(legacyHome)) {
    sources.push({ label: 'legacy 数据目录', dir: legacyHome })
  }
  return sources
}

function isNonEmptyFile(path) {
  if (!existsSync(path)) return false
  try {
    return statSync(path).size > 0
  } catch {
    return false
  }
}

function copyFileIfMissing(src, dest) {
  if (!isNonEmptyFile(src) || existsSync(dest)) return false
  mkdirSync(dirname(dest), { recursive: true })
  copyFileSync(src, dest)
  return true
}

function mergeDirIfMissing(srcDir, destDir) {
  if (!existsSync(srcDir)) return 0
  mkdirSync(destDir, { recursive: true })
  let copied = 0
  for (const name of readdirSync(srcDir)) {
    const src = join(srcDir, name)
    const dest = join(destDir, name)
    if (existsSync(dest)) continue
    const st = statSync(src)
    if (st.isDirectory()) {
      copied += mergeDirIfMissing(src, dest)
      continue
    }
    if (!st.isFile() || st.size <= 0) continue
    mkdirSync(dirname(dest), { recursive: true })
    copyFileSync(src, dest)
    copied++
  }
  return copied
}

function markMigrated(targetHome, details) {
  const stampPath = join(targetHome, '.dev-data-migrated')
  const lines = [
    `migrated_at=${new Date().toISOString()}`,
    ...details,
  ]
  writeFileSync(stampPath, `${lines.join('\n')}\n`, 'utf-8')
}

function main() {
  const targetHome = getTargetHome()
  const sources = getSourceDirs()
  if (sources.length === 0) {
    process.exit(0)
  }

  mkdirSync(targetHome, { recursive: true })
  const targetDataDir = join(targetHome, 'data')
  mkdirSync(targetDataDir, { recursive: true })
  const copied = []
  let copiedCount = 0

  for (const source of sources) {
    for (const name of DB_FILES) {
      const dest = join(targetHome, name)
      if (copyFileIfMissing(join(source.dir, name), dest)) {
        copied.push(`${source.label}: ${name}`)
        copiedCount++
      }
    }
    for (const name of ROOT_FILES) {
      const dest = join(targetHome, name)
      if (copyFileIfMissing(join(source.dir, name), dest)) {
        copied.push(`${source.label}: ${name}`)
        copiedCount++
      }
    }
    for (const name of MERGE_DIRS) {
      const added = mergeDirIfMissing(join(source.dir, name), join(targetHome, name))
      if (added > 0) {
        copied.push(`${source.label}: ${name}/ (+${added})`)
        copiedCount += added
      }
    }
    for (const name of RUNTIME_DATA_DIRS) {
      const added = mergeDirIfMissing(join(source.dir, name), join(targetDataDir, name))
      if (added > 0) {
        copied.push(`${source.label}: ${name}/ → data/ (+${added})`)
        copiedCount += added
      }
    }
  }

  if (copiedCount === 0) {
    console.log(`${logPrefix} 本地数据已就绪，无需迁移`)
    process.exit(0)
  }

  console.log(`${logPrefix} 已迁移 ${copiedCount} 项本地数据到 ${targetHome}`)
  for (const item of copied) {
    console.log(`${logPrefix}   - ${item}`)
  }
  markMigrated(targetHome, copied)
}

main()
