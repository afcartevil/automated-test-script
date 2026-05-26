/**
 * TAHP AI 适配调试 REST 路由
 * 处理：启动适配任务、查询状态、保存/获取配置
 */
import Router from '@koa/router'
import type { Context } from 'koa'
import { getMcpBridge } from '../../services/tahp/mcp-bridge'
import { logger } from '../../services/logger'
import { safeFileStore } from '../../services/safe-file-store'
import { tahpPaths } from '../../services/tahp/paths'
import { join } from 'path'

export const tahpAdaptRoutes = new Router()

// 配置存储文件路径
const CONFIG_PATH = join(tahpPaths.projectRoot, '.adapt-config', 'config.json')

interface AdaptConfig {
  domain: string
  projectCode: string
  soc: string
  kernelVersion: string
  preVendor?: string
  postVendor?: string
  formData: Record<string, any>
}

interface ToolCallResult {
  content?: Array<{ type: string; text?: string }>
  isError?: boolean
}

function unwrapToolResult(raw: unknown): unknown {
  const r = raw as ToolCallResult
  if (!r || !Array.isArray(r.content)) return raw
  const first = r.content[0]
  if (!first || first.type !== 'text') return r
  try {
    return JSON.parse(first.text || '')
  } catch {
    return { text: first.text }
  }
}

// POST /api/tahp/adapt/launch — 启动适配任务
tahpAdaptRoutes.post('/api/tahp/adapt/launch', async (ctx) => {
  try {
    const body = (ctx.request.body || {}) as AdaptConfig
    const { domain, projectCode, soc, kernelVersion, formData } = body

    if (!domain || !projectCode || !soc) {
      ctx.status = 400
      ctx.body = { success: false, error: '缺少必填: domain / projectCode / soc' }
      return
    }

    // 构建 AI 适配任务描述
    const taskDesc = `
AI 适配调试 - ${domain}
项目: ${projectCode}
SoC: ${soc}
Kernel: ${kernelVersion}
前置条件: ${JSON.stringify(formData, null, 2)}
    `.trim()

    // 调用 MCP 启动任务 (tahp_execute)
    try {
      const raw = await getMcpBridge().callTool('tahp_execute', {
        document_path: `adapt-${domain}-${Date.now()}`,
        module: 'adaptation',
        domain,
        constraints_extra: {
          projectCode,
          soc,
          kernelVersion,
          formData,
        },
      })

      const data = unwrapToolResult(raw)
      ctx.body = { success: true, data }
    } catch (mcpErr) {
      logger.warn({ err: (mcpErr as Error).message }, '[tahp-adapt] MCP call failed')
      ctx.status = 500
      ctx.body = { success: false, error: (mcpErr as Error).message }
    }
  } catch (err) {
    logger.error({ err }, '[tahp-adapt-launch] unexpected error')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/adapt/status/:taskId — 查询任务状态
tahpAdaptRoutes.get('/api/tahp/adapt/status/:taskId', async (ctx) => {
  try {
    const { taskId } = ctx.params
    const raw = await getMcpBridge().callTool('tahp_status', { task_id: taskId })
    const data = unwrapToolResult(raw)
    ctx.body = { success: true, data }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[tahp-adapt-status] tool call failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// POST /api/tahp/adapt/config/save — 保存配置
tahpAdaptRoutes.post('/api/tahp/adapt/config/save', async (ctx) => {
  try {
    const config = (ctx.request.body || {}) as AdaptConfig
    await safeFileStore.writeText(CONFIG_PATH, JSON.stringify(config, null, 2))
    ctx.body = { success: true, data: { success: true } }
  } catch (err) {
    logger.warn({ err: (err as Error).message }, '[tahp-adapt-save-config] write failed')
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// GET /api/tahp/adapt/config/get — 获取已保存的配置
tahpAdaptRoutes.get('/api/tahp/adapt/config/get', async (ctx) => {
  try {
    const content = await safeFileStore.readText(CONFIG_PATH)
    const config = JSON.parse(content) as AdaptConfig
    ctx.body = { success: true, data: config }
  } catch (err: any) {
    if (err?.code === 'ENOENT') {
      // 尚未保存过配置，返回 null
      ctx.body = { success: true, data: null }
    } else {
      logger.warn({ err: (err as Error).message }, '[tahp-adapt-get-config] read failed')
      ctx.body = { success: true, data: null }
    }
  }
})
