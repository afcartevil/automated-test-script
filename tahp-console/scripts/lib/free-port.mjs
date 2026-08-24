/**
 * 释放被占用的 TCP 监听端口（开发模式启动前调用）
 */
import { getListeningPids, killListeningPids } from './port-scan.mjs'

export { getListeningPids }

/**
 * 终止占用端口的进程；返回是否执行了释放操作
 * @param {number} port
 * @param {{ quiet?: boolean }} [opts]
 */
export function freePort(port, opts = {}) {
  const pids = getListeningPids(port)
  if (!pids.length) return false

  if (!opts.quiet) {
    console.log(`[dev] 端口 ${port} 被占用 (PID: ${pids.join(', ')})，正在释放…`)
  }

  killListeningPids(port, pids, { quiet: true })

  // 给 OS 一点时间回收端口
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 400)
  return true
}
