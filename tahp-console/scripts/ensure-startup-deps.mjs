#!/usr/bin/env node
/**
 * npm run dev / prestart 启动前：仅 Hermes Agent（功耗 Python 依赖在启动功耗测试时安装）。
 */
import { resolve } from 'path'
import { fileURLToPath } from 'url'
import { applyHermesAgentEnvFromDisk, ensureHermesAgent } from './ensure-hermes-agent.mjs'
import { ensureSkillPythonDeps } from './ensure-skill-python-deps.mjs'
import { ensureGkiPatchDeps } from './ensure-gki-patch-deps.mjs'

export function ensureStartupDeps(options = {}) {
  const { skipAgent = false, agentQuiet = true } = options
  const result = { agent: { ok: true }, skillDeps: { ok: true }, gkiPatchDeps: { ok: true } }

  if (!skipAgent) {
    let agent = applyHermesAgentEnvFromDisk()
    if (!agent.ok) {
      agent = ensureHermesAgent({
        quiet: agentQuiet,
        skipImportVerify: true,
        optional: true,
      })
    }
    result.agent = agent
  }

  result.skillDeps = ensureSkillPythonDeps({ quiet: agentQuiet })
  result.gkiPatchDeps = ensureGkiPatchDeps({ quiet: agentQuiet })

  return result
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (process.env.TAHP_SKIP_PREDEV_AGENT === '1') {
    applyHermesAgentEnvFromDisk()
    process.exit(0)
  }

  const { agent } = ensureStartupDeps({ agentQuiet: process.env.TAHP_STARTUP_QUIET !== '0' })

  if (!agent.ok && !agent.optional) {
    process.exit(1)
  }

  process.exit(0)
}
