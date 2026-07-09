#!/usr/bin/env node
/**
 * 从 run_adapter.bat 以无窗口方式拉起托盘（单实例）。
 */
import { spawn } from 'child_process'
import { existsSync } from 'fs'
import { dirname, resolve } from 'path'
import { fileURLToPath } from 'url'
import {
  isTrayEnabled,
  readTrayPid,
  isProcessRunning,
} from './tray-actions.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const consoleRoot = resolve(__dirname, '..', '..')
const trayEntry = resolve(consoleRoot, 'bin', 'easyadapter-tray.mjs')
const logPrefix = '[EasyAdapter]'

function main() {
  if (process.platform !== 'win32') {
    process.exit(0)
  }
  if (!isTrayEnabled()) {
    console.log(`${logPrefix} 托盘已禁用 (TAHP_TRAY=0)`)
    process.exit(0)
  }
  if (!existsSync(trayEntry)) {
    console.error(`${logPrefix} 未找到托盘入口: ${trayEntry}`)
    process.exit(1)
  }

  const existing = readTrayPid()
  if (existing && isProcessRunning(existing)) {
    console.log(`${logPrefix} 托盘已在运行 (PID: ${existing})`)
    process.exit(0)
  }

  const child = spawn(process.execPath, [trayEntry], {
    cwd: consoleRoot,
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
    env: process.env,
  })
  child.unref()
  console.log(`${logPrefix} 托盘已启动 (PID: ${child.pid})`)
}

main()
