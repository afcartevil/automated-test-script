/**
 * 添加 Provider 前：临时写入配置并通过 Agent Bridge 发起一次最短对话探活。
 * 结束后恢复 config.yaml，不影响用户后续 git 提交。
 */
import { randomBytes } from 'crypto'
import { readFileSync, writeFileSync } from 'fs'
import { getActiveConfigPath, getActiveProfileName } from './hermes-profile'
import { updateConfigYaml } from '../config-helpers'
import {
  AgentBridgeClient,
  getAgentBridgeManager,
} from './agent-bridge'
import { filterBridgeToolCallMarkupDelta } from './run-chat/bridge-delta'
import { logger } from '../logger'

const VERIFY_TIMEOUT_MS = 90_000
const TEMP_PREFIX = '__tahp_verify_'

export interface ProviderBridgeVerifyInput {
  base_url: string
  api_key: string
  model: string
}

export interface ProviderBridgeVerifyResult {
  ok: true
  reply: string
}

async function applyTempProviderConfig(input: ProviderBridgeVerifyInput, tempName: string): Promise<void> {
  await updateConfigYaml((config) => {
    if (!Array.isArray(config.custom_providers)) config.custom_providers = []
    config.custom_providers = (config.custom_providers as Array<{ name?: string }>)
      .filter(entry => !String(entry?.name || '').startsWith(TEMP_PREFIX))
    ;(config.custom_providers as unknown[]).push({
      name: tempName,
      base_url: input.base_url.trim(),
      api_key: input.api_key.trim(),
      model: input.model.trim(),
    })
    const prev = config.model && typeof config.model === 'object' && !Array.isArray(config.model)
      ? config.model
      : {}
    config.model = {
      ...prev,
      default: input.model.trim(),
      provider: `custom:${tempName}`,
      base_url: input.base_url.trim(),
      api_key: input.api_key.trim(),
    }
    return config
  })
}

async function invalidateBridgeProfile(profile: string): Promise<void> {
  try {
    const manager = getAgentBridgeManager()
    if (!manager?.running) return
    await new AgentBridgeClient({ connectRetryMs: 0, timeoutMs: 5000 }).destroyProfile(profile)
  } catch (err) {
    logger.warn({ err: (err as Error).message, profile }, '[provider-verify] bridge invalidate failed')
  }
}

export async function verifyProviderViaBridge(
  input: ProviderBridgeVerifyInput,
): Promise<ProviderBridgeVerifyResult> {
  const baseUrl = input.base_url?.trim()
  const apiKey = input.api_key?.trim()
  const model = input.model?.trim()
  if (!baseUrl) throw new Error('缺少 Base URL')
  if (!apiKey) throw new Error('缺少 API Key')
  if (!model) throw new Error('缺少模型名称')

  const manager = getAgentBridgeManager()
  if (!manager?.running) {
    throw new Error('Agent Bridge 未运行，请等待 Console 启动完成后再验证模型')
  }

  const profile = getActiveProfileName()
  const configPath = getActiveConfigPath()
  const backup = readFileSync(configPath, 'utf-8')
  const tempName = `${TEMP_PREFIX}${Date.now()}`
  const sessionId = `provider-verify-${randomBytes(6).toString('hex')}`
  const client = new AgentBridgeClient({ timeoutMs: VERIFY_TIMEOUT_MS })

  try {
    await applyTempProviderConfig({ base_url: baseUrl, api_key: apiKey, model }, tempName)
    await invalidateBridgeProfile(profile)

    const started = await client.chat(
      sessionId,
      '请只回复：OK',
      undefined,
      '你是 TAHP Provider 连通性测试助手。仅做探活：直接回复 OK 两个字母，不要调用工具，不要附加解释。',
      profile,
      { model, timeout: 60 },
    )

    const markupState: { bridgePendingToolCallMarkup?: string } = {}
    let fullResponse = ''
    let lastError = ''

    for await (const chunk of client.streamOutput(started.run_id, { intervalMs: 100 })) {
      if (chunk.delta) {
        fullResponse += filterBridgeToolCallMarkupDelta(markupState, chunk.delta)
      }
      if (chunk.error) lastError = String(chunk.error)
      if (chunk.done) {
        if (chunk.status === 'error') {
          throw new Error(chunk.error || lastError || 'Agent Bridge 验证失败')
        }
        if (chunk.status === 'interrupted') {
          throw new Error('Agent Bridge 验证被中断')
        }
        break
      }
    }

    const reply = fullResponse.trim()
    if (!reply) {
      throw new Error('模型未返回有效回复，请检查 Base URL、API Key 与模型名称')
    }

    logger.info({ model, baseUrl, replyLen: reply.length }, '[provider-verify] bridge chat ok')
    return { ok: true, reply: reply.slice(0, 200) }
  } finally {
    try {
      writeFileSync(configPath, backup, 'utf-8')
    } catch (err) {
      logger.error({ err: (err as Error).message }, '[provider-verify] failed to restore config.yaml')
    }
    await invalidateBridgeProfile(profile)
    try {
      await client.destroy(sessionId, profile)
    } catch { /* ignore */ }
  }
}
