import type { PipelineRun, TestPlan } from './adapt-pipeline/types'
import { recommendTestCasesWithMeta } from './gerrit-case-recommendation'
import { getCaseCatalogDetail } from './device-self-check'

/**
 * Build must-test items from pipeline run context.
 * Sources: domain labels, changed_files path keywords, audit summary.
 *
 * Known limitation: recommendation engine candidate pool only covers
 * week_driver / week_tdd / str4_driver_component.
 * monkey / smoke / gms / power / pipeline_adapt cases cannot be recommended —
 * use TestPlan.mode='smoke'（冒烟全量）/ 'pipeline_adapt'（按勾选域映射模块）或 mode='fixed'。
 */
export function buildMustTestItems(run: PipelineRun): string[] {
  const items: string[] = []

  for (const d of run.domains) {
    if (!d.enabled || d.status !== 'done') continue
    if (d.domain_label) items.push(d.domain_label)

    // Extract keywords from changed file paths
    if (d.changed_files) {
      for (const f of d.changed_files) {
        const base = f.replace(/^.*[\\/]/, '').replace(/\.\w+$/, '')
        if (base.length >= 3 && !items.includes(base)) {
          items.push(base)
        }
      }
    }
  }

  return [...new Set(items)]
}

type CatalogCaseRef = { caseKey: string; caseName: string; score: number }

/** adapt-debug / feature-adapt 域 id → pipeline_adapt catalog module */
const DOMAIN_ID_TO_PIPELINE_MODULE: Record<string, string> = {
  tp: 'tp',
  vib: 'vibrator',
  vibrator: 'vibrator',
  audio: 'audio',
  lcm: 'lcm',
  fp: 'fingerprint',
  fingerprint: 'fingerprint',
}

export function mapDomainToPipelineAdaptModule(domainId: string): string | undefined {
  const id = domainId.trim().toLowerCase()
  return DOMAIN_ID_TO_PIPELINE_MODULE[id]
}

/** 与 device-self-check getModulesForTestType('pipeline_adapt') 对齐 */
const PIPELINE_ADAPT_MODULE_ORDER = ['tp', 'vibrator', 'audio', 'lcm', 'fingerprint'] as const

/** 勾选（enabled）的调试项对应的 pipeline_adapt 模块，保持 catalog 顺序。 */
export function resolvePipelineAdaptModules(run: PipelineRun): string[] {
  const mapped = new Set<string>()
  for (const d of run.domains) {
    if (!d.enabled) continue
    const module = mapDomainToPipelineAdaptModule(d.domain_id)
    if (module) mapped.add(module)
  }
  return PIPELINE_ADAPT_MODULE_ORDER.filter(m => mapped.has(m))
}

/** Collect all catalog case keys under a testType (e.g. smoke/usd/1, pipeline_adapt/tp/1). */
export function listCatalogCaseKeys(testType: string): CatalogCaseRef[] {
  return getCaseCatalogDetail(testType).map(item => ({
    caseKey: item.key,
    caseName: item.caseName,
    score: 1,
  }))
}

/** Collect all catalog case keys under testType `smoke` (e.g. smoke/usd/1). */
export function listSmokeCaseKeys(): CatalogCaseRef[] {
  return listCatalogCaseKeys('smoke')
}

/**
 * pipeline_adapt catalog keys.
 * `modules` omitted → 全量；传入数组（含空）→ 只保留这些模块。
 */
export function listPipelineAdaptCaseKeys(modules?: readonly string[]): CatalogCaseRef[] {
  const all = listCatalogCaseKeys('pipeline_adapt')
  if (modules === undefined) return all
  const allow = new Set(modules)
  return all.filter(c => allow.has(c.caseKey.split('/')[1] ?? ''))
}

function catalogPlanResult(testType: 'smoke' | 'pipeline_adapt', cases: CatalogCaseRef[]): CasePlanResult {
  const selectedCases = cases.map(c => c.caseKey)
  return {
    plan: {
      mode: testType,
      test_type: testType,
      selected_cases: selectedCases,
    },
    cases,
    source: selectedCases.length ? testType : `${testType}_empty`,
    aiGeneratedCases: [],
  }
}

export interface CasePlanResult {
  plan: TestPlan
  cases: Array<{ caseKey: string; caseName: string; score: number }>
  source: string
  aiGeneratedCases: Array<{ caseKey: string; prompt: string }>
}

/**
 * Plan test cases for a pipeline run.
 * If mustTestItems is empty, degrades to 'fixed' mode (never silently runs empty).
 */
export async function planCases(run: PipelineRun): Promise<CasePlanResult> {
  // Smoke: execute every smoke catalog case.
  if (run.test_plan?.mode === 'smoke') {
    return catalogPlanResult('smoke', listSmokeCaseKeys())
  }

  // pipeline_adapt: only modules mapped from enabled (勾选) debug domains.
  if (run.test_plan?.mode === 'pipeline_adapt') {
    const modules = resolvePipelineAdaptModules(run)
    return catalogPlanResult('pipeline_adapt', listPipelineAdaptCaseKeys(modules))
  }

  // If run already has a fixed plan with selected cases, use it directly
  if (run.test_plan?.mode === 'fixed' && run.test_plan.selected_cases?.length) {
    return {
      plan: run.test_plan,
      cases: run.test_plan.selected_cases.map(k => ({ caseKey: k, caseName: k, score: 1 })),
      source: 'fixed',
      aiGeneratedCases: [],
    }
  }

  const mustTestItems = run.test_plan?.must_test_items ?? buildMustTestItems(run)

  // Empty must-test items → degrade to fixed mode, don't silently run empty
  if (!mustTestItems.length) {
    return {
      plan: { mode: 'fixed', must_test_items: [] },
      cases: [],
      source: 'empty',
      aiGeneratedCases: [],
    }
  }

  try {
    const result = await recommendTestCasesWithMeta(mustTestItems)
    const selectedCases = result.cases.map(c => c.caseKey)

    if (!selectedCases.length) {
      return {
        plan: { mode: 'fixed', must_test_items: mustTestItems },
        cases: [],
        source: 'recommend_empty',
        aiGeneratedCases: [],
      }
    }

    return {
      plan: {
        mode: 'recommend',
        must_test_items: mustTestItems,
        selected_cases: selectedCases,
      },
      cases: result.cases.map(c => ({
        caseKey: c.caseKey,
        caseName: c.caseName,
        score: c.score,
      })),
      source: result.source,
      aiGeneratedCases: result.aiGeneratedCases.map(c => ({
        caseKey: c.caseKey,
        prompt: String((c as unknown as Record<string, unknown>).prompt ?? ''),
      })),
    }
  } catch (err) {
    return {
      plan: { mode: 'fixed', must_test_items: mustTestItems },
      cases: [],
      source: 'recommend_error',
      aiGeneratedCases: [],
    }
  }
}
