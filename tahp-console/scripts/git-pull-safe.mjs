#!/usr/bin/env node
/**
 * 启动前静默尝试 git fetch + pull --ff-only。
 * - 本地有未提交修改时仍尝试拉取；仅修改不同文件时可成功合入远程更新。
 * - 拉取失败或存在冲突风险时清理半成品状态，退出 0，由调用方继续用当前代码启动。
 * 供 run_adapter.bat 在 npm install 之前调用。
 */
import { spawnSync } from 'child_process'
import { dirname } from 'path'
import { fileURLToPath } from 'url'
import { getTahpProjectRoot } from './lib/tahp-paths.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const logPrefix = '[EasyAdapter]'

const GIT_ENV = {
  ...process.env,
  GIT_TERMINAL_PROMPT: '0',
  GCM_INTERACTIVE: 'Never',
  SSH_ASKPASS: '',
  DISPLAY: process.env.DISPLAY || '',
}

function runGit(args, cwd) {
  return spawnSync('git', args, {
    cwd,
    encoding: 'utf-8',
    env: GIT_ENV,
    stdio: ['ignore', 'pipe', 'pipe'],
    timeout: 120_000,
    windowsHide: true,
  })
}

function firstLine(text) {
  return String(text || '').split(/\r?\n/).map(s => s.trim()).find(Boolean) || ''
}

function abortInProgressMergeOrRebase(cwd) {
  runGit(['merge', '--abort'], cwd)
  runGit(['rebase', '--abort'], cwd)
}

function resolveRepoRoot() {
  const guessed = getTahpProjectRoot()
  const probe = runGit(['rev-parse', '--show-toplevel'], guessed)
  if (probe.status === 0) {
    return firstLine(probe.stdout)
  }
  return null
}

function main() {
  const repoRoot = resolveRepoRoot()
  if (!repoRoot) {
    console.log(`${logPrefix} 非 Git 仓库，跳过代码更新`)
    process.exit(0)
  }

  const branchRes = runGit(['rev-parse', '--abbrev-ref', 'HEAD'], repoRoot)
  const branch = firstLine(branchRes.stdout)
  if (!branch || branch === 'HEAD') {
    console.log(`${logPrefix} 当前为 detached HEAD，跳过代码更新`)
    process.exit(0)
  }

  const upstreamRes = runGit(['rev-parse', '--abbrev-ref', '@{u}'], repoRoot)
  const upstream = firstLine(upstreamRes.stdout)
  const pullRef = upstream || `origin/${branch}`

  const localBefore = firstLine(runGit(['rev-parse', '--short', 'HEAD'], repoRoot).stdout)

  const fetchRes = runGit(['fetch', '--quiet', 'origin'], repoRoot)
  if (fetchRes.status !== 0) {
    const err = firstLine(fetchRes.stderr) || firstLine(fetchRes.stdout) || 'fetch 失败'
    console.log(`${logPrefix} 代码更新跳过（无法连接远程）: ${err}`)
    process.exit(0)
  }

  const pullArgs = upstream
    ? ['pull', '--ff-only', '--quiet']
    : ['pull', '--ff-only', '--quiet', 'origin', branch]

  const pullRes = runGit(pullArgs, repoRoot)
  if (pullRes.status !== 0) {
    abortInProgressMergeOrRebase(repoRoot)
    const err = firstLine(pullRes.stderr) || firstLine(pullRes.stdout) || 'pull 失败'
    const hint = /overwritten by merge|would be overwritten|Cannot fast-forward|Not possible to fast-forward/i.test(err)
      ? '（保留本地未提交修改，继续使用当前代码）'
      : ''
    console.log(`${logPrefix} 代码更新跳过: ${err}${hint}`)
    process.exit(0)
  }

  const localAfter = firstLine(runGit(['rev-parse', '--short', 'HEAD'], repoRoot).stdout)
  if (localAfter && localBefore && localAfter !== localBefore) {
    console.log(`${logPrefix} 代码已更新: ${localBefore} -> ${localAfter} (${pullRef})`)
  } else {
    console.log(`${logPrefix} 代码已是最新 (${localAfter || localBefore})`)
  }
  process.exit(0)
}

main()
