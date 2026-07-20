/**
 * AI 生成用例持久化目录（跨重启 / 跨 rebuild 不丢失）。
 *
 * 权威落盘：{projectRoot}/.tahp-config/ai-generated-cases/
 * 运行时镜像：tahpPaths.selfCheckDir 下 case_config + python/cases（供 run_case.py 加载）
 */
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  unlinkSync,
  writeFileSync,
} from 'node:fs'
import { join } from 'node:path'
import { tahpPaths } from './paths'

const AI_GENERATED_TEST_TYPE = 'ai_generated'
const AI_GENERATED_MODULE = 'generated'
const AI_GENERATED_MODULE_LABEL = 'AI生成用例'

export interface AiGeneratedCaseConfigFile {
  testType: string
  module: string
  moduleLabel: string
  conditions: { dutSimCount: number; auxRequired: number; auxSimCount: number }
  defaultCaseMode: string
  cases: Array<{
    caseIndex: number
    caseName: string
    mode: string
    canReuse: boolean
    execMode?: 'manual' | 'nl_ui'
  }>
}

export function getAiGeneratedDurableRoot(): string {
  return join(tahpPaths.projectRoot, '.tahp-config', 'ai-generated-cases')
}

export function getAiGeneratedDurableConfigFile(): string {
  return join(getAiGeneratedDurableRoot(), 'ai_generated_generated.json')
}

export function getAiGeneratedDurableCaseDir(): string {
  return join(getAiGeneratedDurableRoot(), 'generated')
}

export function getAiGeneratedDurablePlanDir(): string {
  return join(getAiGeneratedDurableCaseDir(), 'plans')
}

export function getAiGeneratedDurableCaseInfoFile(): string {
  return join(getAiGeneratedDurableCaseDir(), 'case_info.json')
}

export function getAiGeneratedRuntimeConfigFile(): string {
  return join(tahpPaths.selfCheckDir, 'case_config', 'ai_generated_generated.json')
}

export function getAiGeneratedRuntimeCaseDir(): string {
  return join(
    tahpPaths.selfCheckDir,
    'python',
    'cases',
    AI_GENERATED_TEST_TYPE,
    AI_GENERATED_MODULE,
  )
}

export function getAiGeneratedRuntimePlanDir(): string {
  return join(getAiGeneratedRuntimeCaseDir(), 'plans')
}

export function getAiGeneratedRuntimeCaseInfoFile(): string {
  return join(getAiGeneratedRuntimeCaseDir(), 'case_info.json')
}

export function defaultAiGeneratedConfig(): AiGeneratedCaseConfigFile {
  return {
    testType: AI_GENERATED_TEST_TYPE,
    module: AI_GENERATED_MODULE,
    moduleLabel: AI_GENERATED_MODULE_LABEL,
    conditions: { dutSimCount: 0, auxRequired: 0, auxSimCount: 0 },
    defaultCaseMode: 'solo',
    cases: [],
  }
}

export function ensureAiGeneratedDurableDirs(): void {
  const root = getAiGeneratedDurableRoot()
  const caseDir = getAiGeneratedDurableCaseDir()
  const planDir = getAiGeneratedDurablePlanDir()
  if (!existsSync(root)) mkdirSync(root, { recursive: true })
  if (!existsSync(caseDir)) mkdirSync(caseDir, { recursive: true })
  if (!existsSync(planDir)) mkdirSync(planDir, { recursive: true })
}

function ensureAiGeneratedRuntimeDirs(): void {
  const configDir = join(tahpPaths.selfCheckDir, 'case_config')
  const caseDir = getAiGeneratedRuntimeCaseDir()
  const planDir = getAiGeneratedRuntimePlanDir()
  if (!existsSync(configDir)) mkdirSync(configDir, { recursive: true })
  if (!existsSync(caseDir)) mkdirSync(caseDir, { recursive: true })
  if (!existsSync(planDir)) mkdirSync(planDir, { recursive: true })
}

function readConfigFile(path: string): AiGeneratedCaseConfigFile | null {
  if (!existsSync(path)) return null
  try {
    const parsed = JSON.parse(readFileSync(path, 'utf-8'))
    return { ...defaultAiGeneratedConfig(), ...parsed }
  } catch {
    return null
  }
}

/** 若权威目录为空而旧运行时目录仍有数据，则一次性迁入权威目录 */
export function migrateLegacyAiGeneratedCasesIfNeeded(): void {
  ensureAiGeneratedDurableDirs()
  const durableConfig = getAiGeneratedDurableConfigFile()
  if (existsSync(durableConfig)) {
    const cfg = readConfigFile(durableConfig)
    if (cfg && cfg.cases.length > 0) return
  }

  const legacyConfigPath = getAiGeneratedRuntimeConfigFile()
  const legacyCaseDir = getAiGeneratedRuntimeCaseDir()
  const legacy = readConfigFile(legacyConfigPath)
  if (!legacy || !legacy.cases.length) return

  writeFileSync(durableConfig, `${JSON.stringify(legacy, null, 2)}\n`, 'utf-8')

  const legacyInfo = join(legacyCaseDir, 'case_info.json')
  if (existsSync(legacyInfo)) {
    copyFileSync(legacyInfo, getAiGeneratedDurableCaseInfoFile())
  }

  for (const name of readdirSync(legacyCaseDir)) {
    if (!/^case\d+\.py$/i.test(name)) continue
    copyFileSync(join(legacyCaseDir, name), join(getAiGeneratedDurableCaseDir(), name))
  }

  const legacyPlans = join(legacyCaseDir, 'plans')
  if (existsSync(legacyPlans)) {
    for (const name of readdirSync(legacyPlans)) {
      if (!/^case\d+\.json$/i.test(name)) continue
      copyFileSync(join(legacyPlans, name), join(getAiGeneratedDurablePlanDir(), name))
    }
  }
}

/** 将权威目录镜像到 selfCheckDir，供 Python run_case 加载 */
export function mirrorAiGeneratedCasesToRuntime(): void {
  ensureAiGeneratedDurableDirs()
  ensureAiGeneratedRuntimeDirs()

  const durableConfig = getAiGeneratedDurableConfigFile()
  const runtimeConfig = getAiGeneratedRuntimeConfigFile()
  const durableCaseDir = getAiGeneratedDurableCaseDir()
  const runtimeCaseDir = getAiGeneratedRuntimeCaseDir()
  const durablePlanDir = getAiGeneratedDurablePlanDir()
  const runtimePlanDir = getAiGeneratedRuntimePlanDir()

  // 清空运行时镜像中的旧 case/plan，避免残留
  if (existsSync(runtimeCaseDir)) {
    for (const name of readdirSync(runtimeCaseDir)) {
      if (/^case\d+\.py$/i.test(name) || name === 'case_info.json') {
        unlinkSync(join(runtimeCaseDir, name))
      }
    }
  }
  if (existsSync(runtimePlanDir)) {
    for (const name of readdirSync(runtimePlanDir)) {
      if (/^case\d+\.json$/i.test(name)) unlinkSync(join(runtimePlanDir, name))
    }
  }

  if (!existsSync(durableConfig)) {
    if (existsSync(runtimeConfig)) unlinkSync(runtimeConfig)
    return
  }

  copyFileSync(durableConfig, runtimeConfig)

  const durableInfo = getAiGeneratedDurableCaseInfoFile()
  if (existsSync(durableInfo)) {
    copyFileSync(durableInfo, getAiGeneratedRuntimeCaseInfoFile())
  }

  for (const name of readdirSync(durableCaseDir)) {
    if (!/^case\d+\.py$/i.test(name)) continue
    copyFileSync(join(durableCaseDir, name), join(runtimeCaseDir, name))
  }

  if (existsSync(durablePlanDir)) {
    for (const name of readdirSync(durablePlanDir)) {
      if (!/^case\d+\.json$/i.test(name)) continue
      copyFileSync(join(durablePlanDir, name), join(runtimePlanDir, name))
    }
  }
}

export function loadDurableAiGeneratedConfig(): AiGeneratedCaseConfigFile {
  migrateLegacyAiGeneratedCasesIfNeeded()
  ensureAiGeneratedDurableDirs()
  return readConfigFile(getAiGeneratedDurableConfigFile()) ?? defaultAiGeneratedConfig()
}

export function saveDurableAiGeneratedConfig(config: AiGeneratedCaseConfigFile): void {
  ensureAiGeneratedDurableDirs()
  writeFileSync(getAiGeneratedDurableConfigFile(), `${JSON.stringify(config, null, 2)}\n`, 'utf-8')
  mirrorAiGeneratedCasesToRuntime()
}

export function loadDurableCaseInfo(): Array<Record<string, unknown>> {
  migrateLegacyAiGeneratedCasesIfNeeded()
  ensureAiGeneratedDurableDirs()
  const path = getAiGeneratedDurableCaseInfoFile()
  if (!existsSync(path)) return []
  try {
    const parsed = JSON.parse(readFileSync(path, 'utf-8'))
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function saveDurableCaseInfo(info: Array<Record<string, unknown>>): void {
  ensureAiGeneratedDurableDirs()
  writeFileSync(getAiGeneratedDurableCaseInfoFile(), `${JSON.stringify(info, null, 2)}\n`, 'utf-8')
  mirrorAiGeneratedCasesToRuntime()
}

export function writeDurableCasePython(caseIndex: number, source: string): void {
  ensureAiGeneratedDurableDirs()
  writeFileSync(join(getAiGeneratedDurableCaseDir(), `case${caseIndex}.py`), source.endsWith('\n') ? source : `${source}\n`, 'utf-8')
}

export function writeDurableCasePlan(caseIndex: number, plan: unknown): void {
  ensureAiGeneratedDurableDirs()
  writeFileSync(
    join(getAiGeneratedDurablePlanDir(), `case${caseIndex}.json`),
    `${JSON.stringify(plan, null, 2)}\n`,
    'utf-8',
  )
}

export function removeDurableCaseFiles(caseIndexes: Iterable<number>): void {
  ensureAiGeneratedDurableDirs()
  for (const index of caseIndexes) {
    const py = join(getAiGeneratedDurableCaseDir(), `case${index}.py`)
    const plan = join(getAiGeneratedDurablePlanDir(), `case${index}.json`)
    if (existsSync(py)) unlinkSync(py)
    if (existsSync(plan)) unlinkSync(plan)
  }
}

export function clearDurableAiGeneratedStoreIfEmpty(config: AiGeneratedCaseConfigFile): void {
  if (config.cases.length) return
  const configFile = getAiGeneratedDurableConfigFile()
  const infoFile = getAiGeneratedDurableCaseInfoFile()
  if (existsSync(configFile)) unlinkSync(configFile)
  if (existsSync(infoFile)) unlinkSync(infoFile)
  // 运行时镜像一并清理
  mirrorAiGeneratedCasesToRuntime()
}

/** 启动时：迁移 + 镜像，保证列表与执行路径一致 */
export function bootstrapAiGeneratedCaseStore(): AiGeneratedCaseConfigFile {
  const config = loadDurableAiGeneratedConfig()
  mirrorAiGeneratedCasesToRuntime()
  return config
}
