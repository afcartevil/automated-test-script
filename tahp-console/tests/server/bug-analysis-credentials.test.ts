import { describe, expect, it } from 'vitest'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import {
  buildSilentCredentialResumeMessage,
  filterLoginsightSkillRoots,
  isLlmCredentialUserInput,
  pickConfiguredLlmApiKey,
  redactUserInputValues,
  writeLoginsightCliCredentials,
} from '../../packages/server/src/services/tahp/bug-analysis-credentials'
import type { ParsedUserInputRequest } from '../../packages/server/src/services/tahp/bug-analysis-interaction'

function llmRequest(): ParsedUserInputRequest {
  return {
    requestId: 'llm-1',
    title: 'LogInsight LLM API Key',
    message: '请填写 sw-aimodel API Key',
    timeoutSec: 300,
    persistKey: 'loginsight_llm_api_key',
    fields: [
      { name: 'llm_api_key', label: 'LLM API Key', type: 'password', required: true },
    ],
    rawBlock: '',
    startIndex: 0,
  }
}

describe('bug-analysis-credentials', () => {
  it('pickConfiguredLlmApiKey prefers TAHP_API_KEY then active custom provider', () => {
    expect(pickConfiguredLlmApiKey({
      env: { TAHP_API_KEY: 'tahp-key' },
      activeProvider: 'custom:sw-aimodel',
      customProviders: [{ name: 'sw-aimodel', api_key: 'custom-key' }],
    })?.apiKey).toBe('tahp-key')

    expect(pickConfiguredLlmApiKey({
      env: {},
      activeProvider: 'custom:sw-aimodel',
      customProviders: [{ name: 'sw-aimodel', api_key: 'custom-key' }],
    })).toEqual({ apiKey: 'custom-key', source: 'active_custom' })

    expect(pickConfiguredLlmApiKey({
      env: { ANTHROPIC_API_KEY: 'env-key' },
      activeProvider: 'anthropic',
      customProviders: [],
    })).toEqual({ apiKey: 'env-key', source: 'active_env' })
  })

  it('filterLoginsightSkillRoots keeps dirs with SKILL.md / CLI and dedupes', () => {
    const root = mkdtempSync(join(tmpdir(), 'li-roots-'))
    try {
      const a = join(root, 'project', 'loginsight-remote-cli')
      const b = join(root, 'hermes', 'loginsight-remote-cli')
      mkdirSync(a, { recursive: true })
      mkdirSync(join(b, 'scripts'), { recursive: true })
      writeFileSync(join(a, 'SKILL.md'), '# a\n')
      writeFileSync(join(b, 'scripts', 'loginsight_cli.py'), '# cli\n')
      const empty = join(root, 'empty')
      mkdirSync(empty, { recursive: true })

      const found = filterLoginsightSkillRoots([a, a, b, empty])
      expect(found).toHaveLength(2)
      expect(found.map(p => p.toLowerCase())).toContain(a.toLowerCase())
      expect(found.map(p => p.toLowerCase())).toContain(b.toLowerCase())
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })

  it('writeLoginsightCliCredentials writes llm_api_key to json and .env without wiping operator', () => {
    const root = mkdtempSync(join(tmpdir(), 'li-seed-'))
    try {
      writeFileSync(join(root, '.loginsight_cli.json'), JSON.stringify({
        operator_user: 'u1',
        operator_password: 'p1',
      }))
      writeLoginsightCliCredentials(root, { llmApiKey: 'sk-test-key' })
      const json = JSON.parse(readFileSync(join(root, '.loginsight_cli.json'), 'utf-8')) as Record<string, string>
      expect(json.llm_api_key).toBe('sk-test-key')
      expect(json.operator_user).toBe('u1')
      expect(json.operator_password).toBe('p1')
      const env = readFileSync(join(root, '.env'), 'utf-8')
      expect(env).toContain('LLM_API_KEY=sk-test-key')
      expect(env).toContain('OPERATOR_USER=u1')
    } finally {
      rmSync(root, { recursive: true, force: true })
    }
  })

  it('classifies LLM credential prompts and redacts secrets from persisted values', () => {
    const req = llmRequest()
    expect(isLlmCredentialUserInput(req)).toBe(true)
    expect(isLlmCredentialUserInput({
      ...req,
      title: '日志保存目录',
      message: '请填写本机日志路径',
      persistKey: 'jira_log_output_dir',
      fields: [{ name: 'log_dir', label: '日志目录', type: 'text' }],
    })).toBe(false)

    const redacted = redactUserInputValues(req, { llm_api_key: 'sk-secret' })
    expect(redacted.llm_api_key).toBe('***')
    const resume = buildSilentCredentialResumeMessage(req, true)
    expect(resume).not.toContain('sk-secret')
    expect(resume).toContain('Hermes 运行时副本')
  })
})
