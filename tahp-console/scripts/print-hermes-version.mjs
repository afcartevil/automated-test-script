#!/usr/bin/env node
/**
 * 启动脚本横幅：Hermes 版本 + EasyAdapter 后台说明。
 * 中文走 Node stdout，避免 cmd chcp 65001 下 echo 把下一行吃成 `ho`。
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

process.stdout.write(`
========================================
  EasyAdapter Console 后台模式
`)
process.stdout.write(formatHermesVersionBanner({
  version,
  targetVersion: TARGET_HERMES_VERSION,
  targetTag: TARGET_HERMES_TAG,
  agentDir,
}, { color: shouldColorHermesBanner() }))
process.stdout.write(`========================================
  启动顺序: 构建检查 -> 停止旧进程 -> 后台守护 8650 -> 系统托盘 -> 打开浏览器
  服务在后台运行，关闭本窗口不会影响使用
  日常使用: 任务栏托盘图标 EA 右键菜单
    打开控制台 / 重启 / 更新并重启 / 停止 / 查看日志
  配置 API Key: 系统 - 模型管理
========================================

`)
