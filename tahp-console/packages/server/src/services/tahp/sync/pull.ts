/**
 * 从中心拉取已发布内容写入本地副本，并重建检索索引 / 热生效公共配置。
 * Phase 2：支持整包 files 内联或 package_url ZIP；pull 后热注入。
 */
import { join } from 'path'
import { tahpPaths } from '../paths'
import { safeFileStore } from '../../safe-file-store'
import { logger } from '../../logger'
import { upsertIndexRecord } from '../kb-search'
import { reloadBusinessDomains } from '../business-domain-registry'
import { HermesSkillInjector } from '../../hermes/skill-injector'
import { config } from '../../../config'
import { centralClient } from './central-client'
import type { PullPayload } from './manifest'
import { setLastPulledAt } from './status'
import {
  applyInlineFilesToLocal,
  applySkillZipToLocal,
  localRequirementsHash,
} from './skill-package'

let lastPulledAt = ''

function entryPath(id: string): string {
  return join(tahpPaths.knowledgeDir, '.kb-data', 'entries', `${id}.json`)
}

function configTargetPath(key: string, relPath: string): string {
  if (key === 'business-domains') return join(tahpPaths.knowledgeDir, 'business-domains.yaml')
  if (key === 'kb-config') return join(tahpPaths.knowledgeDir, 'config.yaml')
  return join(tahpPaths.projectRoot, relPath)
}

export interface PullResult {
  entries: number
  skills: number
  configs: number
  generated_at: string
  skill_ids: string[]
  reinjected: string[]
  reinject_error?: string
  requirements_changed: string[]
}

async function applyOneSkill(
  skill: PullPayload['skills'][number],
): Promise<{ id: string; reqBefore: string | null; reqAfter: string | null }> {
  const id = skill.id
  const reqBefore = localRequirementsHash(id)

  if (skill.files?.length) {
    applyInlineFilesToLocal(id, skill.files)
  } else if (skill.package_url) {
    const buf = await centralClient.downloadSkillPackage(id, skill.package_url)
    applySkillZipToLocal(id, buf)
  } else if (typeof skill.content === 'string') {
    // P1 兼容：仅 SKILL.md
    const target = join(tahpPaths.skillsDir, id, 'SKILL.md')
    await safeFileStore.writeText(target, skill.content)
  } else {
    throw new Error(`skill ${id} 无 files/package_url/content`)
  }

  const reqAfter = localRequirementsHash(id)
  return { id, reqBefore, reqAfter }
}

export async function applyPull(
  payload: PullPayload,
  options?: { reinjectSkillIds?: string[] | null },
): Promise<PullResult> {
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
  const skillIds: string[] = []
  const requirements_changed: string[] = []
  for (const skill of payload.skills) {
    if (!skill.id) continue
    try {
      const r = await applyOneSkill(skill)
      skillCount++
      skillIds.push(r.id)
      if (r.reqAfter && r.reqBefore !== r.reqAfter) {
        requirements_changed.push(r.id)
      }
    } catch (e) {
      logger.warn({ id: skill.id, err: (e as Error).message }, '[sync] apply skill package failed')
    }
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

  const result: PullResult = {
    entries: entryCount,
    skills: skillCount,
    configs: configCount,
    generated_at: payload.generated_at,
    skill_ids: skillIds,
    reinjected: [],
    requirements_changed,
  }

  const reinjectTarget =
    options?.reinjectSkillIds === null
      ? null
      : options?.reinjectSkillIds?.length
        ? options.reinjectSkillIds
        : skillIds.length
          ? skillIds
          : null

  if (reinjectTarget && reinjectTarget.length > 0) {
    try {
      const injection = await new HermesSkillInjector().injectMissingSkills(reinjectTarget)
      result.reinjected = [...injection.injected, ...injection.updated]
    } catch (e) {
      result.reinject_error = (e as Error).message
      logger.warn({ err: result.reinject_error }, '[sync] reinject after pull failed')
    }
  }

  return result
}

export async function runPull(
  incremental = true,
  options?: { reinjectSkillIds?: string[] | null },
): Promise<PullResult | null> {
  const since = incremental ? lastPulledAt : ''
  const payload = await centralClient.pull(since || undefined)
  const result = await applyPull(payload, options)
  lastPulledAt = payload.generated_at
  setLastPulledAt(payload.generated_at)
  logger.info(result, '[sync] pull applied')
  return result
}

/** 将本机 skill 打 ZIP 上传到中心 */
export async function publishSkillPackage(skillId: string): Promise<{ id: string; hash: string; file_count: number }> {
  if (!config.tahp.centralUrl || !config.tahp.centralToken) {
    throw new Error('中心未配置')
  }
  const { buildLocalSkillZipBuffer, listLocalSkillFiles, computePackageHash } = await import('./skill-package')
  const files = listLocalSkillFiles(skillId)
  if (!files.length) throw new Error(`本地无 Skill: ${skillId}`)
  const buf = buildLocalSkillZipBuffer(skillId)
  const meta = await centralClient.uploadSkillPackage(skillId, buf.toString('base64'))
  return {
    id: skillId,
    hash: meta.hash || computePackageHash(files),
    file_count: meta.files?.length || files.length,
  }
}
