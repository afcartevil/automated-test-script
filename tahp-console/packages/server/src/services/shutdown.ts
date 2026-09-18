import { logger } from './logger'
import { closeDb } from '../db'
import { isGkiPatchAutoStartEnabled, stopGkiPatchServer } from './tahp/gki-patch'
import { stopBaselineNotifyClient } from './tahp/sync'
import { stopSelfCheckBackgroundProcesses } from './tahp/device-self-check'
import { stopVerifyAutoRun } from './tahp/verify-auto-run'
import { markBffExit, stopBffHeartbeat } from './crash-log'

export function bindShutdown(server: any, groupChatServer?: any, chatRunServer?: any, agentBridgeManager?: any): void {
  let isShuttingDown = false

  const shutdown = async (signal: string) => {
    if (isShuttingDown) return
    isShuttingDown = true
    stopBffHeartbeat()
    markBffExit('graceful', { signal })

    // Force exit after 3s no matter what
    setTimeout(() => process.exit(0), 3000)

    logger.info('Shutting down (%s)...', signal)
    console.log(`[shutdown] Received signal: ${signal}`)

    try {
      stopBaselineNotifyClient()
      logger.info('Baseline notify client stopped')

      // 停止验测任务自动执行调度器（不中断已在跑的测试，进程本身由下面的清理负责）
      try {
        stopVerifyAutoRun()
      } catch (err) {
        logger.warn(err, 'Failed to stop verify-auto-run scheduler (non-fatal)')
      }

      // 停止自检后台进程（monkey watchdog / power），避免 BFF 退出后孤儿进程残留
      try {
        await stopSelfCheckBackgroundProcesses()
        logger.info('Self-check background processes stopped')
      } catch (err) {
        logger.warn(err, 'Failed to stop self-check background processes (non-fatal)')
      }

      if (isGkiPatchAutoStartEnabled()) {
        stopGkiPatchServer()
        logger.info('GKI patch server stopped')
      }

      if (agentBridgeManager) {
        try {
          await agentBridgeManager.stop()
          logger.info('Agent bridge stopped')
        } catch (err) {
          logger.warn(err, 'Failed to stop agent bridge (non-fatal)')
        }
      }

      // Close ChatRunSocket first to abort all active runs and close EventSource connections
      if (chatRunServer) {
        chatRunServer.close()
        logger.info('ChatRunSocket closed')
      }

      // Disconnect Socket.IO before HTTP server to prevent hanging
      if (groupChatServer) {
        groupChatServer.agentClients.disconnectAll()
        groupChatServer.getIO().close()
        logger.info('Socket.IO closed')
      }

      const servers = Array.isArray(server) ? server : [server].filter(Boolean)
      if (servers.length) {
        await Promise.all(servers.map((httpServer) => (
          new Promise<void>((resolve) => {
            httpServer.close(() => {
              logger.info('HTTP server closed')
              resolve()
            })
          })
        )))
      }
    } catch (err) {
      logger.error(err, 'Shutdown error')
    }

    closeDb()
    process.exit(0)
  }

  process.once('SIGUSR2', shutdown)
  process.on('SIGINT', shutdown)
  process.on('SIGTERM', shutdown)
}
