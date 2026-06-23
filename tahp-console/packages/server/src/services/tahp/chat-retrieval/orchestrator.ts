import type { ChatIntent } from './intents'
import { routeIntent, parseSlashIntent, type RoutedIntent } from './intent-router'
import type { RetrievalBundle, RetrievalOptions } from './types'
import { runHistoricalCase } from './strategies/historical-case'
import { runConceptReference } from './strategies/concept-reference'
import { runAnalysisSop, runAdaptationGuide, runPolicyStandards } from './strategies/analysis-sop'
import {
  runIntegrationConfig,
  runApiSpec,
  runVersionScope,
  runTroubleshootingChecklist,
  runDirectLookup,
  runMixedExplore,
} from './strategies/other-strategies'

async function executeStrategy(
  intent: ChatIntent,
  query: string,
  routed: RoutedIntent,
  options: RetrievalOptions,
): Promise<RetrievalBundle> {
  switch (intent) {
    case 'historical_case': return runHistoricalCase(query, routed, options)
    case 'concept_reference': return runConceptReference(query, routed, options)
    case 'analysis_sop': return runAnalysisSop(query, routed, options)
    case 'adaptation_guide': return runAdaptationGuide(query, routed, options)
    case 'integration_config': return runIntegrationConfig(query, routed, options)
    case 'api_spec': return runApiSpec(query, routed, options)
    case 'version_scope': return runVersionScope(query, routed, options)
    case 'troubleshooting_checklist': return runTroubleshootingChecklist(query, routed, options)
    case 'direct_lookup': return runDirectLookup(query, routed, options)
    case 'policy_standards': return runPolicyStandards(query, routed, options)
    case 'mixed_explore':
    default:
      return runMixedExplore(query, routed, options)
  }
}

export async function runRetrieval(
  userInput: string,
  options: RetrievalOptions = {},
): Promise<{ bundle: RetrievalBundle; routed: RoutedIntent; query: string }> {
  const slash = parseSlashIntent(userInput)
  const query = slash.rest || userInput
  const routed = routeIntent(query, {
    retrieval_mode: options.retrieval_mode,
    slash_intent: slash.intent,
  })
  const bundle = await executeStrategy(routed.intent, query, routed, options)
  return { bundle, routed, query }
}
