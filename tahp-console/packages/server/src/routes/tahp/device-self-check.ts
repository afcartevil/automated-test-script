import Router from '@koa/router'
import {
  listDevices,
  refreshDevices,
  setDeviceRole,
  startTest,
  continueTest,
  endTest,
  updateCaseResult,
  getDevice,
  getTestSession,
  getModuleConditions,
  addSseClient,
  removeSseClient,
  submitManualDecision,
  getPendingManualDecision,
  DeviceInfo,
  DeviceRole,
} from '../../services/tahp/device-self-check'

export const tahpDeviceSelfCheckRoutes = new Router()

// 获取设备列表
tahpDeviceSelfCheckRoutes.get(
  '/api/tahp/device-self-check/devices',
  async (ctx) => {
    try {
      const devices = await listDevices()
      ctx.body = { success: true, data: devices }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to list devices' }
    }
  }
)

// 刷新设备
tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/devices/refresh',
  async (ctx) => {
    try {
      const devices = await refreshDevices()
      ctx.body = { success: true, data: devices }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to refresh devices' }
    }
  }
)

// 获取单个设备
tahpDeviceSelfCheckRoutes.get(
  '/api/tahp/device-self-check/devices/:deviceId',
  async (ctx) => {
    try {
      const deviceId = ctx.params.deviceId
      const device = getDevice(deviceId)
      const session = getTestSession(deviceId)
      ctx.body = {
        success: true,
        data: {
          device,
          session,
        },
      }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to get device' }
    }
  }
)

// 设置设备角色
tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/devices/:deviceId/role',
  async (ctx) => {
    try {
      const deviceId = ctx.params.deviceId
      const { role } = ctx.request.body as { role: DeviceRole }
      const device = await setDeviceRole(deviceId, role)
      ctx.body = { success: true, data: device }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to set role' }
    }
  }
)

// 开始测试
tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/devices/:deviceId/test/start',
  async (ctx) => {
    try {
      const deviceId = ctx.params.deviceId
      const { testType } = ctx.request.body as { testType: 'str4' | 'week' }
      const result = await startTest(deviceId, testType)
      ctx.body = {
        success: true,
        data: result,
      }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to start test' }
    }
  }
)

// 继续测试
tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/devices/:deviceId/test/continue',
  async (ctx) => {
    try {
      const deviceId = ctx.params.deviceId
      const result = await continueTest(deviceId)
      ctx.body = {
        success: true,
        data: result,
      }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to continue test' }
    }
  }
)

// 获取模块配置
tahpDeviceSelfCheckRoutes.get(
  '/api/tahp/device-self-check/module-conditions',
  async (ctx) => {
    try {
      const conditions = getModuleConditions()
      ctx.body = { success: true, data: conditions }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to get module conditions' }
    }
  }
)

// 结束测试
tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/devices/:deviceId/test/end',
  async (ctx) => {
    try {
      const deviceId = ctx.params.deviceId
      const result = endTest(deviceId)
      ctx.body = { success: true, data: result }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to end test' }
    }
  }
)

// 修改用例结果
tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/devices/:deviceId/case-result',
  async (ctx) => {
    try {
      const deviceId = ctx.params.deviceId
      const { testType, module, caseIndex, status, message } = ctx.request.body as {
        testType: string
        module: string
        caseIndex: number
        status: string
        message: string
      }
      const result = updateCaseResult(deviceId, testType, module, caseIndex, status, message)
      ctx.body = { success: true, data: result }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to update case result' }
    }
  }
)

// 提交人工决策
tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/manual-decision',
  async (ctx) => {
    try {
      const { decisionId, decision } = ctx.request.body as {
        decisionId: string
        decision: string
      }
      const ok = submitManualDecision(decisionId, decision)
      ctx.body = { success: ok, error: ok ? undefined : '决策已过期或不存在' }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to submit decision' }
    }
  }
)

// 获取待处理人工决策
tahpDeviceSelfCheckRoutes.get(
  '/api/tahp/device-self-check/devices/:deviceId/pending-manual-decision',
  async (ctx) => {
    try {
      const deviceId = ctx.params.deviceId
      const decision = getPendingManualDecision(deviceId)
      ctx.body = { success: true, data: decision }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to get pending decision' }
    }
  }
)

// SSE 事件流
tahpDeviceSelfCheckRoutes.get(
  '/api/tahp/device-self-check/events',
  async (ctx) => {
    ctx.set({
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'X-Accel-Buffering': 'no',
    })
    ctx.status = 200
    ctx.respond = false

    const res = ctx.res as any
    res.write('event: connected\ndata: {}\n\n')

    addSseClient(res)

    // 保持连接
    const keepAlive = setInterval(() => {
      try {
        res.write(': keepalive\n\n')
      } catch {
        clearInterval(keepAlive)
        removeSseClient(res)
      }
    }, 15000)

    // Koa 不需要关闭，close 事件在 addSseClient 中已注册
  }
)
