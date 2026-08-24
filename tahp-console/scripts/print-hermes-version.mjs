#!/usr/bin/env node
/**
 * 启动脚本横幅：醒目输出当前 Hermes Agent 版本。
 * 供 run_adapter.bat 在 setup:agent 之后、进入后台启动前调用。
 */
import { dirname } from 'path'
import { fileURLToPath } from 'url'
import { getBundledHermesAgentDir, getConsoleRoot, getTahpProjectRoot } from './lib/tahp-paths.mjs'
import {
  TARGET_HERMES_TAG,
  TARGET_HERMES_VERSION,
  formatHermesVersionBanner,
  readPyprojectVersion,
  shouldColorHermesBanner,
} from './lib/hermes-agent-fingerprint.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const consoleRoot = getConsoleRoot(__dirname)
const agentDir = getBundledHermesAgentDir(getTahpProjectRoot(consoleRoot)) || ''
const version = agentDir ? readPyprojectVersion(agentDir) : ''

process.stdout.write(formatHermesVersionBanner({
  version,
  targetVersion: TARGET_HERMES_VERSION,
  targetTag: TARGET_HERMES_TAG,
  agentDir,
}, { color: shouldColorHermesBanner() }))
