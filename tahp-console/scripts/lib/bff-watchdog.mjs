#!/usr/bin/env node
/**
 * 盯着 BFF PID。进程消失且没有 graceful/stop-requested 标记时写入 logs/crash.log。
 * native crash / taskkill / OOM 走不到 JS uncaughtException，只能靠这个。
 */
import { isProcessRunning } from './tray-actions.mjs'
import { recordUnexpectedExit } from './crash-log.mjs'

const pid = parseInt(process.argv[2] || '', 10)
if (!Number.isFinite(pid) || pid <= 0) {
  process.exit(0)
}

const intervalMs = Math.max(500, parseInt(process.env.TAHP_BFF_WATCHDOG_MS || '2000', 10) || 2000)

function tick() {
  if (isProcessRunning(pid)) {
    setTimeout(tick, intervalMs)
    return
  }
  try {
    recordUnexpectedExit(pid, { type: 'watchdog-exit', detectedBy: 'bff-watchdog' })
  } catch (err) {
    console.error('[bff-watchdog] failed to write crash log:', err)
  }
  process.exit(0)
}

setTimeout(tick, intervalMs)
