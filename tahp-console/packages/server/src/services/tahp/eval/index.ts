/**
 * 评估层 —— 对外入口（bug-analysis / adapt / retrieval）。
 */
export * from './types'
export {
  computeAgreement,
  isJudgeTrustworthy,
  MIN_AGREEMENT_RATE,
  MIN_LABELED_SAMPLES,
} from './calibration'
export { compareEvalRuns } from './compare'
export { computeSkillsHash } from './fingerprint'
export {
  aggregateScore,
  buildJudgePrompt,
  judgeReport,
  parseJudgeVerdict,
  resolveJudgeModel,
  JUDGE_PROMPT_VERSION,
  PASS_THRESHOLD,
  WARN_THRESHOLD,
} from './judge'
export {
  createEvalCaseFromReport,
  listEvalCaseCandidates,
  DEFAULT_RUBRIC,
} from './case-builder'
export {
  abortEvalRun,
  startEvalRun,
  updateEvalCase,
} from './runner'
export {
  ADAPT_OBJECTIVE_VERSION,
  DEFAULT_ADAPT_AGENT_RUBRIC,
  DEFAULT_ADAPT_PIPELINE_RUBRIC,
  mergeObjectiveAndLlm,
  scoreAdaptCase,
  scoreObjectiveRubrics,
  signalsFromAdaptReport,
  signalsFromPipelineRun,
} from './adapt-objective'
export {
  createAdaptCaseFromAgentReport,
  createAdaptCaseFromCandidate,
  createAdaptCaseFromPipelineRun,
  listAdaptEvalCandidates,
} from './adapt-case-builder'
export {
  abortAdaptEvalRun,
  startAdaptEvalRun,
  updateAdaptEvalCase,
} from './adapt-runner'
export {
  DEFAULT_RETRIEVAL_RUBRIC,
  INTENTS_WITHOUT_SKILL_RANKING,
  RETRIEVAL_OBJECTIVE_VERSION,
  collectRetrievalSignals,
  scoreRetrievalCase,
  scoreRetrievalRubrics,
} from './retrieval-objective'
export {
  RETRIEVAL_SEED_SPECS,
  createRetrievalCase,
  createRetrievalCaseFromSeed,
  importMissingRetrievalSeeds,
  listRetrievalEvalCandidates,
} from './retrieval-case-builder'
export {
  abortRetrievalEvalRun,
  startRetrievalEvalRun,
  updateRetrievalEvalCase,
} from './retrieval-runner'
export {
  EVAL_BUNDLE_FORMAT,
  EVAL_BUNDLE_VERSION,
  exportEvalBundle,
  importEvalBundle,
  redactEvalCase,
  validateEvalBundle,
} from './bundle'
export type { EvalBundle, ExportEvalBundleOptions, ImportEvalBundleOptions } from './bundle'
export {
  RETRIEVAL_CI_SAFE_SEED_IDS,
  isRetrievalCiSafeSeed,
  runRetrievalCiGate,
  seedSpecToEvalCase,
} from './retrieval-ci-gate'
export type { RetrievalCiGateResult } from './retrieval-ci-gate'
export {
  deleteEvalCase,
  evalCasesDir,
  evalResultsDir,
  isSafeEvalId,
  listEvalCaseResults,
  listEvalCases,
  listEvalRuns,
  readEvalCase,
  readEvalCaseResult,
  readEvalRun,
  saveEvalCase,
  setHumanLabel,
} from './store'
