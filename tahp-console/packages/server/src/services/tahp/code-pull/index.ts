/**
 * 代码拉取模块导出。
 * 后期适配流水线可：
 *   import { codePullCapability } from '../code-pull'
 *   registerStage(createCapabilityStage({ key: 'code_pull', capability: codePullCapability, ... }))
 */
export { codePullCapability, pickMappedRootFromDiscover } from './capability'
export {
  startCodePull,
  cancelCodePull,
  getCodePullRunDetail,
  listCodePullRunSummaries,
  probeCodePull,
  recoverCodePullRuns,
} from './service'
export {
  validateRepoInitCommand,
  codePullLinuxPath,
  codePullWinPath,
  codePullRelPath,
  buildRepoInitCommand,
  buildRepoSyncTmuxStart,
  detectRepoSyncFailureInLog,
  formatRepoSyncFailure,
  parseFailedReposFromLog,
} from './repo-sync-tmux'
export type { FailedRepoItem } from './repo-sync-tmux'
export { normalizeMappedRoot, joinWinCodePath } from './result-parse'
export type {
  CodePullInput,
  CodePullResult,
  CodePullRunRecord,
  CodePullRunSummary,
} from './types'
