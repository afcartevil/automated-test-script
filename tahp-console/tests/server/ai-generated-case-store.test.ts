import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import {
  bootstrapAiGeneratedCaseStore,
  getAiGeneratedDurableConfigFile,
  getAiGeneratedDurableRoot,
  getAiGeneratedRuntimeCaseDir,
  getAiGeneratedRuntimeConfigFile,
  loadDurableAiGeneratedConfig,
  saveDurableAiGeneratedConfig,
  writeDurableCasePython,
} from '../../packages/server/src/services/tahp/ai-generated-case-store'
import { tahpPaths } from '../../packages/server/src/services/tahp/paths'
import {
  deleteAiGeneratedCases,
  loadAiGeneratedCaseConfig,
} from '../../packages/server/src/services/tahp/gerrit-ai-generated-cases'
import { getAllCaseCatalogs, getCaseCatalogDetail, initDeviceSelfCheck } from '../../packages/server/src/services/tahp/device-self-check'

describe('ai-generated durable case store', () => {
  const createdKeys: string[] = []

  afterEach(() => {
    if (createdKeys.length) {
      deleteAiGeneratedCases([...createdKeys])
      createdKeys.length = 0
    }
  })

  it('persists cases under .tahp-config and reloads after bootstrap', () => {
    const durableRoot = getAiGeneratedDurableRoot()
    expect(durableRoot.replace(/\\/g, '/')).toContain('.tahp-config/ai-generated-cases')

    const config = loadDurableAiGeneratedConfig()
    const caseIndex = (config.cases.reduce((max, c) => Math.max(max, c.caseIndex), 0) || 0) + 1
    config.cases.push({
      caseIndex,
      caseName: '持久化自检用例',
      mode: 'solo',
      canReuse: false,
      execMode: 'nl_ui',
    })
    writeDurableCasePython(caseIndex, 'def run(**context):\n    return {"status": "pass", "message": "ok"}\n')
    saveDurableAiGeneratedConfig(config)
    createdKeys.push(`ai_generated/generated/${caseIndex}`)

    expect(existsSync(getAiGeneratedDurableConfigFile())).toBe(true)
    expect(existsSync(join(getAiGeneratedDurableRoot(), 'generated', `case${caseIndex}.py`))).toBe(true)

    // 模拟重启：再次 bootstrap，应从权威目录恢复并镜像到 runtime
    const reloaded = bootstrapAiGeneratedCaseStore()
    expect(reloaded.cases.some(c => c.caseIndex === caseIndex && c.caseName === '持久化自检用例')).toBe(true)
    expect(existsSync(getAiGeneratedRuntimeConfigFile())).toBe(true)
    expect(existsSync(join(getAiGeneratedRuntimeCaseDir(), `case${caseIndex}.py`))).toBe(true)

    initDeviceSelfCheck()
    const aiGroup = getAllCaseCatalogs().find(g => g.testType === 'ai_generated')
    expect(aiGroup?.modules[0]?.cases.some(c => c.caseIndex === caseIndex)).toBe(true)
    const detail = getCaseCatalogDetail('ai_generated')
    expect(detail.some(item => item.caseIndex === caseIndex)).toBe(true)
    expect(loadAiGeneratedCaseConfig()?.cases.some(c => c.caseIndex === caseIndex)).toBe(true)
  })

  it('migrates legacy runtime cases into durable store', () => {
    const runtimeConfig = getAiGeneratedRuntimeConfigFile()
    const runtimeCaseDir = getAiGeneratedRuntimeCaseDir()
    mkdirSync(join(tahpPaths.selfCheckDir, 'case_config'), { recursive: true })
    mkdirSync(runtimeCaseDir, { recursive: true })

    // 清空权威目录以触发迁移
    const durableRoot = getAiGeneratedDurableRoot()
    if (existsSync(durableRoot)) rmSync(durableRoot, { recursive: true, force: true })

    const legacy = {
      testType: 'ai_generated',
      module: 'generated',
      moduleLabel: 'AI生成用例',
      conditions: { dutSimCount: 0, auxRequired: 0, auxSimCount: 0 },
      defaultCaseMode: 'solo',
      cases: [{ caseIndex: 99, caseName: '遗留用例', mode: 'solo', canReuse: false, execMode: 'nl_ui' }],
    }
    writeFileSync(runtimeConfig, `${JSON.stringify(legacy, null, 2)}\n`, 'utf-8')
    writeFileSync(join(runtimeCaseDir, 'case99.py'), 'def run(**context):\n    return {"status": "pass"}\n', 'utf-8')
    createdKeys.push('ai_generated/generated/99')

    const migrated = bootstrapAiGeneratedCaseStore()
    expect(migrated.cases.some(c => c.caseIndex === 99)).toBe(true)
    expect(existsSync(getAiGeneratedDurableConfigFile())).toBe(true)
    const durableRaw = readFileSync(getAiGeneratedDurableConfigFile(), 'utf-8')
    expect(durableRaw).toContain('遗留用例')
  })
})
