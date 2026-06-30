#!/usr/bin/env node
/**
 * 探测本机 Git Bash 并写入 tahp-console/.env（HERMES_GIT_BASH_PATH）。
 * 由 run_adapter.bat 与 ensure-hermes-agent 调用。
 */
import { ensureGitBashEnv } from './lib/discover-git-bash.mjs'
import { getConsoleRoot } from './lib/tahp-paths.mjs'

const consoleRoot = getConsoleRoot()
const strict = process.env.TAHP_REQUIRE_AGENT === '1'

if (process.platform !== 'win32') {
  process.exit(0)
}

console.log('')
console.log('TAHP Git Bash 检测')
console.log('─'.repeat(40))

const result = ensureGitBashEnv({ consoleRoot, quiet: false, persist: true })

if (!result.ok) {
  console.error(`  ✗ ${result.error}`)
  console.log('─'.repeat(40))
  process.exit(strict ? 1 : 0)
}

if (result.source === 'env') {
  console.log(`  ✓ 已配置 HERMES_GIT_BASH_PATH=${result.path}`)
}
console.log('─'.repeat(40))
console.log('')
process.exit(0)
