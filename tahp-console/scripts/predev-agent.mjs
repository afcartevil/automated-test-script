#!/usr/bin/env node
/**
 * npm run dev 的 predev 钩子：run_adapter.bat 已 setup:agent 时可跳过重复检查。
 */
import { applyHermesAgentEnvFromDisk, ensureHermesAgent } from './ensure-hermes-agent.mjs'

if (process.env.TAHP_SKIP_PREDEV_AGENT === '1') {
  applyHermesAgentEnvFromDisk()
  process.exit(0)
}

const result = ensureHermesAgent({ quiet: true, skipImportVerify: true })
process.exit(result.ok || result.optional ? 0 : 1)
