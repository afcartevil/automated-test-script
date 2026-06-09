/**
 * 释放被占用的 TCP 监听端口（开发模式启动前调用）
 */
import { execSync } from 'child_process'

function uniquePids(pids) {
  return [...new Set(pids.filter(pid => Number.isFinite(pid) && pid > 0))]
}

/** 查询正在监听指定端口的进程 PID 列表 */
export function getListeningPids(port) {
  if (!port || Number.isNaN(port)) return []

  try {
    if (process.platform === 'win32') {
      const out = execSync('netstat -aon -p tcp', { encoding: 'utf-8' })
      return uniquePids(
        out
          .split('\n')
          .map(l => l.trim())
          .filter(l => l.includes('LISTENING'))
          .map(l => l.split(/\s+/))
          .filter(parts => parseInt((parts[1] || '').split(':').pop(), 10) === port)
          .map(parts => parseInt(parts[parts.length - 1], 10)),
      )
    }
  } catch {
    return []
  }

  try {
    const out = execSync(`lsof -tiTCP:${port} -sTCP:LISTEN`, {
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim()
    return uniquePids(out.split(/\r?\n/).map(p => parseInt(p, 10)))
  } catch {
    return []
  }
}

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

  try {
    if (process.platform === 'win32') {
      execSync(`taskkill /F /PID ${pids.join(' /PID ')}`, { encoding: 'utf-8', stdio: 'ignore' })
    } else {
      execSync(`kill -9 ${pids.join(' ')}`, { encoding: 'utf-8', stdio: 'ignore' })
    }
  } catch {
    // 进程可能已退出
  }

  // 给 OS 一点时间回收端口
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 400)
  return true
}
