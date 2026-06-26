/**
 * 从中心拉取已发布内容写入本地副本，并重建检索索引 / 热生效公共配置。
 * 执行侧（适配/自检/检索）读本地副本，逻辑不变。
 */
import { join } from 'path'
import { tahpPaths } from '../paths'
import { safeFileStore } from '../../safe-file-store'
import { logger } from '../../logger'
import { upsertIndexRecord } from '../kb-search'
import { reloadBusinessDomains } from '../business-domain-registry'
import { centralClient } from './central-client'
import type { PullPayload } from './manifest'

let lastPulledAt = ''

function entryPath(id: string): string {
  return join(tahpPaths.knowledgeDir, '.kb-data', 'entries', `${id}.json`)
}

function configTargetPath(key: string, relPath: string): string {
  if (key === 'business-domains') return join(tahpPaths.knowledgeDir, 'business-domains.yaml')
  if (key === 'kb-config') return join(tahpPaths.knowledgeDir, 'config.yaml')
  // 兜底：按中心给的相对路径落到 projectRoot
  return join(tahpPaths.projectRoot, relPath)
}

export interface PullResult {
  entries: number
  skills: number
  configs: number
  generated_at: string
}

export async function applyPull(payload: PullPayload): Promise<PullResult> {
  let entryCount = 0
  for (const entry of payload.entries) {
    const id = String((entry as Record<string, unknown>).id || '')
    if (!id) continue
    await safeFileStore.writeText(entryPath(id), JSON.stringify(entry, null, 2))
    try {
      upsertIndexRecord(entry as any)
    } catch (e) {
      logger.warn({ id, err: (e as Error).message }, '[sync] reindex entry failed')
    }
    entryCount++
  }

  let skillCount = 0
  for (const skill of payload.skills) {
    if (!skill.id || typeof skill.content !== 'string') continue
    const target = join(tahpPaths.skillsDir, skill.id, 'SKILL.md')
    await safeFileStore.writeText(target, skill.content)
    skillCount++
  }

  let configCount = 0
  let configChanged = false
  for (const cfg of payload.configs) {
    if (typeof cfg.content !== 'string') continue
    await safeFileStore.writeText(configTargetPath(cfg.key, cfg.rel_path), cfg.content, { backup: true })
    configCount++
    if (cfg.key === 'business-domains') configChanged = true
  }
  if (configChanged) {
    try {
      reloadBusinessDomains()
      logger.info('[sync] business domains reloaded after pull')
    } catch (e) {
      logger.warn({ err: (e as Error).message }, '[sync] reload business domains failed')
    }
  }

  return { entries: entryCount, skills: skillCount, configs: configCount, generated_at: payload.generated_at }
}

/** 执行一次增量 pull（首启传空 since 拉全量） */
export async function runPull(incremental = true): Promise<PullResult | null> {
  const since = incremental ? lastPulledAt : ''
  const payload = await centralClient.pull(since || undefined)
  const result = await applyPull(payload)
  lastPulledAt = payload.generated_at
  logger.info(result, '[sync] pull applied')
  return result
}
