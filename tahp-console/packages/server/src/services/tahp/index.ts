/**
 * TAHP 服务层入口 — 启动 MCP bridge 与 task stream.
 */
import { tahpPaths, hasTahpProject } from './paths'
import { getMcpBridge } from './mcp-bridge'
import { getTaskStream } from './task-stream'
import { logger } from '../logger'

export { tahpPaths, hasTahpProject } from './paths'
export { getMcpBridge } from './mcp-bridge'
export { getTaskStream } from './task-stream'
export type { TaskEvent } from './task-stream'

/** 在 bootstrap 中调用 — 启动 MCP bridge (失败不致命) */
export async function initTahpBridge(): Promise<void> {
  if (!hasTahpProject()) {
    logger.warn({ path: tahpPaths.mcpServer }, '[tahp] tahp-mcp-server 未找到，TAHP 功能将不可用')
    return
  }
  try {
    const bridge = getMcpBridge()
    getTaskStream() // 绑定监听
    await bridge.start()
    logger.info({ root: tahpPaths.projectRoot }, '[tahp] MCP bridge ready')
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[tahp] MCP bridge 启动失败，将在请求时重试')
  }
}
