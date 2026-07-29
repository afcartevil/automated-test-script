import type { PipelineRun, TestPlan } from './adapt-pipeline/types'
import { recommendTestCasesWithMeta } from './gerrit-case-recommendation'

/**
 * Build must-test items from pipeline run context.
 * Sources: domain labels, changed_files path keywords, audit summary.
 *
 * Known limitation: recommendation engine candidate pool only covers
 * week_driver / week_tdd / str4_driver_component.
 * monkey / smoke / gms / power cases cannot be recommended — use TestPlan.mode='fixed'.
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
