import Router from '@koa/router'
import {
  listDevices,
  refreshDevices,
  setDeviceRole,
  startTest,
  startCustomTest,
  continueTest,
  resumeTest,
  endTest,
  skipCurrentCase,
  updateCaseResult,
  retestCase,
  retestReportCase,
  openDeviceCaseFailureLogs,
  getDevice,
  getTestSession,
  getModuleConditions,
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  deleteAiGeneratedCases,
  createAiNlUiCase,
  updateAiNlUiCase,
  getSettings,
  updateSettings,
  resolveOtaPretestUdPackage,
  runOtaPretestOperation,
  addSseClient,
  removeSseClient,
  submitManualDecision,
  getPendingManualDecision,
  DeviceInfo,
  DeviceRole,
  StartTestFlashPayload,
  StartTestTcardPayload,
} from '../../services/tahp/device-self-check'
import {
  listSelfCheckReports,
  getSelfCheckReportDetail,
  openSelfCheckReportXlsx,
  openSelfCheckCaseFailureLogs,
  submitSelfCheckReportReview,
  updateReportCaseResult,
  type SelfCheckReviewStatus,
} from '../../services/tahp/self-check-reports'
import { getSelfCheckPipelineStatus } from '../../services/tahp/pipeline-status'
import { probeTPowerStatus, loadTPowerConfig, saveTPowerConfig } from '../../services/tahp/tpower-status'

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
      const { testType, flash, tcard, prioritizeTddManual, modules } = ctx.request.body as {
        testType: 'str4' | 'week' | 'monkey' | 'monkey_check' | 'smoke' | 'ota_upgrade' | 'gms' | 'power' | 'power_feature' | 'thermal' | 'kernel_feature' | 'pipeline_adapt' | 'ai_generated' | 'bitflip'
        flash?: StartTestFlashPayload
        tcard?: StartTestTcardPayload
        prioritizeTddManual?: boolean
        modules?: string[]
        otaPretest?: {
          udFlash?: boolean
          oemUnlock?: boolean
          udPackagePath?: string
        }
      }
      const { otaPretest } = ctx.request.body as {
        otaPretest?: { udFlash?: boolean; oemUnlock?: boolean; udPackagePath?: string }
      }
      const result = await startTest(deviceId, testType, flash, {
        prioritizeTddManual: Boolean(prioritizeTddManual),
        tcard,
        modules: Array.isArray(modules) ? modules.filter(m => typeof m === 'string' && m.trim()) : undefined,
        otaPretest: otaPretest ? {
          udFlash: Boolean(otaPretest.udFlash),
          oemUnlock: Boolean(otaPretest.oemUnlock),
          udPackagePath: String(otaPretest.udPackagePath || '').trim() || undefined,
        } : undefined,
      })
      ctx.body = {
        success: true,
        data: result,
      }
    } catch (err: any) {
      const message = err?.message || 'Failed to start test'
      ctx.status = message.includes('不支持 GMS') ? 400 : 500
      ctx.body = { success: false, error: message }
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

// 从错误状态恢复测试（从当前/报错模块继续）
tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/devices/:deviceId/test/resume',
  async (ctx) => {
    try {
      const deviceId = ctx.params.deviceId
      const result = await resumeTest(deviceId)
      if (!result) {
        ctx.status = 400
        ctx.body = { success: false, error: '设备非错误状态或会话已失效' }
        return
      }
      ctx.body = { success: true, data: result }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to resume test' }
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

// 获取所有用例大类
tahpDeviceSelfCheckRoutes.get(
  '/api/tahp/device-self-check/case-catalogs',
  async (ctx) => {
    try {
      const catalogs = getAllCaseCatalogs()
      ctx.body = { success: true, data: catalogs }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to get case catalogs' }
    }
  }
)

// 获取用例大类详情（含手动测试步骤）
tahpDeviceSelfCheckRoutes.get(
  '/api/tahp/device-self-check/case-catalogs/:testType/detail',
  async (ctx) => {
    try {
      const detail = getCaseCatalogDetail(ctx.params.testType)
      ctx.body = { success: true, data: detail }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to get case catalog detail' }
    }
  }
)

// 删除 AI 生成用例（仅允许 ai_generated/generated/*）
tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/ai-cases/delete',
  async (ctx) => {
    try {
      const { caseKeys } = ctx.request.body as { caseKeys?: string[] }
      const result = deleteAiGeneratedCases(Array.isArray(caseKeys) ? caseKeys : [])
      ctx.body = { success: true, data: result }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to delete AI cases' }
    }
  }
)

// 手动新增 NL UI 自动化 AI 用例
tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/ai-cases/create',
  async (ctx) => {
    try {
      const { caseName, nlDescription, expectedResult } = ctx.request.body as {
        caseName?: string
        nlDescription?: string
        expectedResult?: string
      }
      const created = await createAiNlUiCase({
        caseName: String(caseName || ''),
        nlDescription: String(nlDescription || ''),
        expectedResult: expectedResult ? String(expectedResult) : undefined,
      })
      ctx.body = { success: true, data: created }
    } catch (err: any) {
      const message = err?.message || 'Failed to create AI case'
      const notExecutable = /不可|无法|拒绝|缺少|无效|过短/i.test(message)
      ctx.status = notExecutable ? 400 : 500
      ctx.body = { success: false, error: message }
    }
  }
)

// 修改并覆盖已有 NL UI 自动化 AI 用例（同 caseIndex）
tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/ai-cases/update',
  async (ctx) => {
    try {
      const { caseKey, caseName, nlDescription, expectedResult } = ctx.request.body as {
        caseKey?: string
        caseName?: string
        nlDescription?: string
        expectedResult?: string
      }
      const updated = await updateAiNlUiCase({
        caseKey: String(caseKey || ''),
        caseName: String(caseName || ''),
        nlDescription: String(nlDescription || ''),
        expectedResult: expectedResult ? String(expectedResult) : undefined,
      })
      ctx.body = { success: true, data: updated }
    } catch (err: any) {
      const message = err?.message || 'Failed to update AI case'
      const notExecutable = /不可|无法|拒绝|缺少|无效|过短|不存在/i.test(message)
      ctx.status = notExecutable ? 400 : 500
      ctx.body = { success: false, error: message }
    }
  }
)

// 启动自定义测试
tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/devices/:deviceId/test/custom-start',
  async (ctx) => {
    try {
      const deviceId = ctx.params.deviceId
      const { selectedCases, customAuxDeviceIds, prioritizeTddManual, caseIds } = ctx.request.body as {
        selectedCases: string[]
        customAuxDeviceIds: string[]
        prioritizeTddManual?: boolean
        caseIds?: Record<string, string[]>
      }
      const result = await startCustomTest(
        deviceId,
        selectedCases || [],
        customAuxDeviceIds || [],
        { prioritizeTddManual: Boolean(prioritizeTddManual), caseIds },
      )
      if (!result) {
        ctx.status = 400
        ctx.body = { success: false, error: '设备不可用或不在空闲状态' }
        return
      }
      ctx.body = { success: true, data: result }
    } catch (err: any) {
      const message = err?.message || 'Failed to start custom test'
      ctx.status = message.includes('不支持 GMS') ? 400 : 500
      ctx.body = { success: false, error: message }
    }
  }
)

// 结束测试
tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/devices/:deviceId/test/end',
  async (ctx) => {
    try {
      const deviceId = ctx.params.deviceId
      const result = await endTest(deviceId)
      ctx.body = { success: true, data: result }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to end test' }
    }
  }
)

// 跳过当前用例（会话继续下一例）
tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/devices/:deviceId/test/skip-case',
  async (ctx) => {
    try {
      const deviceId = ctx.params.deviceId
      const result = skipCurrentCase(deviceId)
      ctx.body = { success: true, data: result }
    } catch (err: any) {
      const message = err?.message || 'Failed to skip case'
      ctx.status = /不存在|没有可跳过/.test(message) ? 400 : 500
      ctx.body = { success: false, error: message }
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

// 复测单个用例
tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/devices/:deviceId/case/retest',
  async (ctx) => {
    try {
      const deviceId = ctx.params.deviceId
      const { testType, module, caseIndex, auxDeviceId } = ctx.request.body as {
        testType: string
        module: string
        caseIndex: number
        auxDeviceId?: string
      }
      const result = await retestCase(deviceId, testType, module, caseIndex, auxDeviceId)
      ctx.body = { success: true, data: result }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to retest case' }
    }
  }
)

// 打开失败用例日志目录
tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/devices/:deviceId/cases/:caseKey/open-logs',
  async (ctx) => {
    try {
      const caseKey = decodeURIComponent(ctx.params.caseKey)
      const dirPath = await openDeviceCaseFailureLogs(ctx.params.deviceId, caseKey)
      ctx.body = { success: true, data: { dirPath } }
    } catch (err: any) {
      const message = err?.message || 'Failed to open failure logs'
      ctx.status = message.includes('不存在') || message.includes('无测试会话') ? 404 : 400
      ctx.body = { success: false, error: message }
    }
  },
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
      ctx.body = { success: ok, data: { accepted: ok }, error: ok ? undefined : '决策已过期或不存在' }
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

// 获取设置
tahpDeviceSelfCheckRoutes.get(
  '/api/tahp/device-self-check/settings',
  async (ctx) => {
    try {
      const settings = getSettings()
      ctx.body = { success: true, data: settings }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to get settings' }
    }
  }
)

// 更新设置
tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/settings',
  async (ctx) => {
    try {
      const newSettings = ctx.request.body as any
      updateSettings(newSettings)
      ctx.body = { success: true }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to update settings' }
    }
  }
)

tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/ota-pretest/pick-path',
  async (ctx) => {
    try {
      const { target } = (ctx.request.body || {}) as { target?: 'script' | 'directory' }
      const { pickLocalPythonScript, pickLocalDirectory } = await import('../../services/tahp/device-flash')
      const result = target === 'script' ? await pickLocalPythonScript() : await pickLocalDirectory()
      ctx.body = { success: !result.error, data: result, error: result.error }
      if (result.error && !result.canceled) ctx.status = 500
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to pick path' }
    }
  }
)

tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/ota-pretest/resolve-ud',
  async (ctx) => {
    try {
      const { deviceId } = (ctx.request.body || {}) as { deviceId?: string }
      const result = await resolveOtaPretestUdPackage(String(deviceId || ''))
      ctx.body = { success: true, data: result }
    } catch (err: any) {
      ctx.status = 400
      ctx.body = { success: false, error: err?.message || 'Failed to resolve UD package' }
    }
  }
)

tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/ota-pretest/preview',
  async (ctx) => {
    try {
      const { deviceId } = (ctx.request.body || {}) as { deviceId?: string }
      const { previewOtaStart } = await import('../../services/tahp/ota-pretest')
      const result = await previewOtaStart(String(deviceId || ''))
      ctx.body = { success: true, data: result }
    } catch (err: any) {
      ctx.status = 400
      ctx.body = { success: false, error: err?.message || 'Failed to preview OTA start' }
    }
  }
)

tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/ota-pretest/run',
  async (ctx) => {
    try {
      const body = (ctx.request.body || {}) as {
        deviceId?: string
        udPackagePath?: string
        pretestOnly?: boolean
      }
      const result = await runOtaPretestOperation(
        String(body.deviceId || ''),
        body.udPackagePath,
        { pretestOnly: Boolean(body.pretestOnly) },
      )
      ctx.body = { success: true, data: result }
    } catch (err: any) {
      ctx.status = 400
      ctx.body = { success: false, error: err?.message || 'Failed to run OTA pretest operation' }
    }
  }
)

tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/flash/pick-path',
  async (ctx) => {
    try {
      const { pickLocalFlashPath } = await import('../../services/tahp/device-flash')
      const result = await pickLocalFlashPath()
      ctx.body = { success: !result.error, data: result, error: result.error }
      if (result.error && !result.canceled) ctx.status = 500
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to pick flash path' }
    }
  }
)

tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/tcard/pick-zip',
  async (ctx) => {
    try {
      const { pickLocalTcardZipPath } = await import('../../services/tahp/device-flash')
      const result = await pickLocalTcardZipPath()
      ctx.body = { success: !result.error, data: result, error: result.error }
      if (result.error && !result.canceled) ctx.status = 500
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to pick T-card zip' }
    }
  }
)

tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/gms/pick-tradefed-path',
  async (ctx) => {
    try {
      const { pickLocalTradefedPath } = await import('../../services/tahp/device-flash')
      const result = await pickLocalTradefedPath()
      ctx.body = { success: !result.error, data: result, error: result.error }
      if (result.error && !result.canceled) ctx.status = 500
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to pick tradefed path' }
    }
  }
)

tahpDeviceSelfCheckRoutes.get(
  '/api/tahp/device-self-check/flash/daily-options',
  async (ctx) => {
    try {
      const deviceId = String(ctx.query.deviceId || '').trim()
      if (!deviceId) {
        ctx.status = 400
        ctx.body = { success: false, error: '缺少 deviceId' }
        return
      }
      const { getDailyFlashOptions } = await import('../../services/tahp/device-flash')
      const result = await getDailyFlashOptions(deviceId)
      ctx.body = { success: true, data: result }
    } catch (err: any) {
      ctx.status = 400
      ctx.body = { success: false, error: err?.message || 'Failed to load daily flash options' }
    }
  }
)

tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/flash/latest-daily',
  async (ctx) => {
    try {
      const { resolveLatestDailyFlashPackage } = await import('../../services/tahp/device-flash')
      const body = (ctx.request.body || {}) as {
        deviceId?: string
        systemVersion?: string
      }
      const result = await resolveLatestDailyFlashPackage({
        deviceId: body.deviceId || '',
        systemVersion: body.systemVersion || '',
      })
      ctx.body = { success: true, data: result }
    } catch (err: any) {
      ctx.status = 400
      ctx.body = { success: false, error: err?.message || 'Failed to resolve latest daily flash package' }
    }
  }
)

tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/tcard/release-upgrade',
  async (ctx) => {
    try {
      const { resolveReleaseUpgradePlan } = await import('../../services/tahp/device-release-upgrade')
      const body = (ctx.request.body || {}) as { deviceId?: string }
      const result = await resolveReleaseUpgradePlan(body.deviceId || '')
      ctx.body = { success: true, data: result }
    } catch (err: any) {
      ctx.status = 400
      ctx.body = { success: false, error: err?.message || 'Failed to resolve release upgrade plan' }
    }
  }
)

tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/flash/clear-packages',
  async (ctx) => {
    try {
      const { clearFlashPackageCache } = await import('../../services/tahp/device-flash')
      const result = clearFlashPackageCache()
      ctx.body = { success: true, data: result }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to clear flash package cache' }
    }
  }
)

// SSE 事件流
tahpDeviceSelfCheckRoutes.get(
  '/api/tahp/device-self-check/pipeline',
  async (ctx) => {
    try {
      const data = await getSelfCheckPipelineStatus()
      ctx.body = { success: true, data }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to get pipeline status' }
    }
  }
)

tahpDeviceSelfCheckRoutes.get(
  '/api/tahp/device-self-check/reports',
  async (ctx) => {
    try {
      const sinceHours = ctx.query.sinceHours ? Number(ctx.query.sinceHours) : undefined
      const pendingOnly = ctx.query.pendingOnly === '1' || ctx.query.pendingOnly === 'true'
      const data = await listSelfCheckReports({
        sinceHours: Number.isFinite(sinceHours) ? sinceHours : undefined,
        pendingOnly,
      })
      ctx.body = { success: true, data }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to list reports' }
    }
  }
)

tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/reports/:reportId/open',
  async (ctx) => {
    try {
      const filePath = openSelfCheckReportXlsx(ctx.params.reportId)
      ctx.body = { success: true, data: { filePath } }
    } catch (err: any) {
      const message = err?.message || 'Failed to open report file'
      ctx.status = message.includes('不存在') ? 404 : 400
      ctx.body = { success: false, error: message }
    }
  },
)

tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/reports/:reportId/cases/:caseKey/open-logs',
  async (ctx) => {
    try {
      const caseKey = decodeURIComponent(ctx.params.caseKey)
      const dirPath = await openSelfCheckCaseFailureLogs(ctx.params.reportId, caseKey)
      ctx.body = { success: true, data: { dirPath } }
    } catch (err: any) {
      const message = err?.message || 'Failed to open failure logs'
      ctx.status = message.includes('不存在') ? 404 : 400
      ctx.body = { success: false, error: message }
    }
  },
)

tahpDeviceSelfCheckRoutes.get(
  '/api/tahp/device-self-check/reports/:reportId',
  async (ctx) => {
    try {
      const data = await getSelfCheckReportDetail(ctx.params.reportId)
      if (!data) {
        ctx.status = 404
        ctx.body = { success: false, error: '报告不存在' }
        return
      }
      ctx.body = { success: true, data }
    } catch (err: any) {
      ctx.status = 400
      ctx.body = { success: false, error: err?.message || 'Failed to get report detail' }
    }
  }
)

tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/reports/:reportId/review',
  async (ctx) => {
    try {
      const body = (ctx.request.body || {}) as { status?: SelfCheckReviewStatus; note?: string }
      const status = body.status
      if (status !== 'reviewed' && status !== 'retest' && status !== 'pending') {
        ctx.status = 400
        ctx.body = { success: false, error: '无效 review 状态' }
        return
      }
      const data = await submitSelfCheckReportReview(ctx.params.reportId, {
        status,
        note: body.note,
      })
      if (!data) {
        ctx.status = 404
        ctx.body = { success: false, error: '报告不存在' }
        return
      }
      ctx.body = { success: true, data }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to submit review' }
    }
  }
)

tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/reports/:reportId/case-result',
  async (ctx) => {
    try {
      const body = (ctx.request.body || {}) as {
        caseKey?: string
        status?: string
        message?: string
      }
      if (!body.caseKey || !body.status) {
        ctx.status = 400
        ctx.body = { success: false, error: '缺少 caseKey 或 status' }
        return
      }
      const data = await updateReportCaseResult(
        ctx.params.reportId,
        body.caseKey,
        body.status,
        body.message ?? '',
      )
      if (!data) {
        ctx.status = 404
        ctx.body = { success: false, error: '报告或用例不存在' }
        return
      }
      ctx.body = { success: true, data }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to update report case' }
    }
  }
)

tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/reports/:reportId/retest',
  async (ctx) => {
    try {
      const body = (ctx.request.body || {}) as { caseKey?: string; auxDeviceId?: string }
      if (!body.caseKey) {
        ctx.status = 400
        ctx.body = { success: false, error: '缺少 caseKey' }
        return
      }
      const result = await retestReportCase(
        ctx.params.reportId,
        body.caseKey,
        body.auxDeviceId,
      )
      if (!result) {
        ctx.status = 404
        ctx.body = { success: false, error: '报告或用例不存在' }
        return
      }
      const detail = await getSelfCheckReportDetail(ctx.params.reportId)
      ctx.body = { success: true, data: { result, detail } }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to retest report case' }
    }
  }
)

tahpDeviceSelfCheckRoutes.get(
  '/api/tahp/device-self-check/tpower/status',
  async (ctx) => {
    try {
      const data = await probeTPowerStatus()
      ctx.body = { success: true, data }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to probe T-Power' }
    }
  }
)

tahpDeviceSelfCheckRoutes.get(
  '/api/tahp/device-self-check/tpower/config',
  async (ctx) => {
    try {
      ctx.body = { success: true, data: loadTPowerConfig() }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to load T-Power config' }
    }
  }
)

tahpDeviceSelfCheckRoutes.post(
  '/api/tahp/device-self-check/tpower/config',
  async (ctx) => {
    try {
      const body = (ctx.request.body || {}) as { adbSerial?: string; label?: string }
      const data = saveTPowerConfig(body)
      ctx.body = { success: true, data }
    } catch (err: any) {
      ctx.status = 500
      ctx.body = { success: false, error: err?.message || 'Failed to save T-Power config' }
    }
  }
)

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
