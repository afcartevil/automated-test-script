import fs from 'fs'
import path from 'path'
import crypto from 'crypto'
import os from 'os'
import { spawn, spawnSync } from 'child_process'
import type { ServerResponse } from 'http'
import * as XLSX from 'xlsx'
import { config as serverConfig } from '../../config'

export type ModemBaselineStatus = 'running' | 'success' | 'failed' | 'conflict'
export type ModemBaselineMode = 'stop_after_merge'
export type ModemBaselinePhase = 'precheck' | 'merge' | 'conflict' | 'resume' | 'build' | 'archive'

export type ModemBaselineConfig = {
  NODE_BRANCH: string
  target_BRANCH: string
  AP_lable: string
  DESCRIPTION?: string
  JIRAID: string
  work_dir: string
  mapped_prefix?: string
  remote_prefix?: string
  /** projects/ 下子目录名；继续执行成功后自动 ./tools/bld_modem.sh <name> */
  build_project?: string
}

export type ModemBaselineRunMeta = {
  runId: string
  status: ModemBaselineStatus
  mode: ModemBaselineMode
  phase?: ModemBaselinePhase
  createdAt: string
  startedAt?: string
  finishedAt?: string
  config: ModemBaselineConfig
  remoteWorkDir?: string
  logPath?: string
  reportPath?: string
  conflictFiles?: string[]
  error?: string
}

export type UserWorkspaceProfile = {
  owner: string
  mappedPrefix: string
  remotePrefix: string
  roots: string[]
  updatedAt: string
}

export type RepoProfile = {
  repoId: string
  owner: string
  label: string
  localPath: string
  mappedPrefix: string
  remotePrefix: string
  projectName?: string
  platform?: string
  vendor?: string
  defaultNodeBranch?: string
  defaultTargets?: string[]
  recentBranches?: string[]
  lastUsedAt?: string
  branchTemplateStatus?: 'idle' | 'running' | 'success' | 'failed'
  branchTemplateError?: string
  branchTemplateUpdatedAt?: string
  branches?: {
    trunk?: { nodeBranch: string; trunkBranch: string }
    mp?: Array<{ tos: string; mpNodeBranch: string; mpBranch: string }>
  }
}

export type ScannedRepoCandidate = {
  localPath: string
  repoName: string
  isGitRepo: boolean
}

export type PrecheckItem = {
  key: string
  level: 'ok' | 'warn' | 'error'
  title: string
  detail: string
}

export type PrecheckResult = {
  canStart: boolean
  items: PrecheckItem[]
}

export type ModemPatchOperationType = 'baseline_upgrade' | 'patch' | 'unknown'

export type BranchRule = {
  ruleId: string
  enabled: boolean
  label: string
  operationType?: ModemPatchOperationType
  platform?: string
  vendor?: string
  nodePattern: string
  trunkPattern: string
  mpPattern?: string
  defaultTarget?: 'trunk' | 'mp'
  updatedAt: string
}

export type BranchTemplate = {
  templateId: string
  owner: string
  tos: string
  platform: string
  nodeBranch: string
  trunkBranch: string
  mpBranch: string
  mpNodeBranch: string
  sourceFile?: string
  sourceSheet?: string
  updatedAt: string
}

export type NoticeParseResult = {
  rawText: string
  operationType: ModemPatchOperationType
  platform?: string
  tosVersion?: string
  targetMode?: 'trunk' | 'mp'
  version?: string
  confidence: number
  candidates: { platforms: string[] }
  warnings: string[]
}

export type RecommendationResult = {
  nodeBranch?: string
  targetBranch?: string
  apLabel?: string
  ruleId?: string
  branchSource?: 'template' | 'rule'
  targetMode?: 'trunk' | 'mp'
  warnings: string[]
}

type HarnessResult = {
  status: string
  exit_code: number
  command: string
  output?: string
  error?: string
}

type BridgeProbeResult = {
  ready: boolean
  summary: string
  cached?: boolean
}

type LocalExecResult = {
  exitCode: number | null
  stdout: string
  stderr: string
  timedOut: boolean
}

type RunRuntime = {
  runId: string
  clients: Set<ServerResponse>
  logLineOpen: boolean
}

const runtimes = new Map<string, RunRuntime>()
const BRIDGE_PROBE_CACHE_TTL_MS = 90_000
let lastBridgeProbeSuccessAt = 0
let lastBridgeProbeSummary = ''

function nowIso() {
  return new Date().toISOString()
}

function getCachedBridgeProbe(): BridgeProbeResult | null {
  if (!lastBridgeProbeSuccessAt) return null
  if (Date.now() - lastBridgeProbeSuccessAt > BRIDGE_PROBE_CACHE_TTL_MS) return null
  return {
    ready: true,
    summary: lastBridgeProbeSummary || 'cached_bridge_probe=1',
    cached: true,
  }
}

function rememberBridgeProbeSuccess(summary: string) {
  lastBridgeProbeSuccessAt = Date.now()
  lastBridgeProbeSummary = summary
}

function formatRunLogTimestamp(date = new Date()) {
  const pad = (value: number) => String(value).padStart(2, '0')
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
  ].join('-') + ` ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

function ensureRunLogTimestamps(text: string, lineOpen = false) {
  const timestamp = `[${formatRunLogTimestamp()}]`
  const hasTimestamp = /^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\](?:\s|$)/
  const parts = String(text ?? '').split(/(\r?\n)/)
  let nextLineOpen = lineOpen
  let normalized = ''

  for (const part of parts) {
    if (part === '\n' || part === '\r\n') {
      normalized += part
      nextLineOpen = false
      continue
    }
    if (!part) continue
    if (!nextLineOpen && !hasTimestamp.test(part)) {
      normalized += `${timestamp} ${part}`
    } else {
      normalized += part
    }
    nextLineOpen = true
  }

  return {
    text: normalized,
    lineOpen: nextLineOpen,
  }
}

function toolRootCandidates() {
  const envOverride = process.env.MODEM_BASELINE_TOOL_ROOT?.trim()
  const candidates = [
    envOverride ? path.resolve(envOverride) : '',
    path.resolve(process.cwd(), '..', 'tools', 'modem-patch-tool'),
    path.resolve(process.cwd(), 'tools', 'modem-patch-tool'),
  ].filter(Boolean)

  return Array.from(new Set(candidates))
}

function modemBaselineToolRoot() {
  for (const candidate of toolRootCandidates()) {
    if (fs.existsSync(candidate)) {
      return candidate
    }
  }

  return toolRootCandidates()[0] ?? path.resolve(process.cwd(), '..', 'tools', 'modem-patch-tool')
}

function ensureToolRoot() {
  const toolRoot = modemBaselineToolRoot()
  if (!fs.existsSync(toolRoot)) {
    throw new Error(`Modem patch tool root not found: ${toolRoot}; please check tools/modem-patch-tool or MODEM_BASELINE_TOOL_ROOT`)
  }
  return toolRoot
}

function defaultConfigPath() {
  return path.resolve(ensureToolRoot(), 'config', 'baseline_upgrade.json')
}

function runsRootDir() {
  return path.resolve(serverConfig.dataDir, 'modem-baseline', 'runs')
}

function modemPatchConfigRootDir() {
  return path.resolve(serverConfig.dataDir, 'modem-patch')
}

function workspacesRootDir() {
  return path.resolve(modemPatchConfigRootDir(), 'workspaces')
}

function reposRootDir() {
  return path.resolve(modemPatchConfigRootDir(), 'repos')
}

function rulesRootDir() {
  return path.resolve(modemPatchConfigRootDir(), 'rules')
}

function branchTemplatesRootDir() {
  return path.resolve(modemPatchConfigRootDir(), 'branch-templates')
}

function ensureDir(dir: string) {
  fs.mkdirSync(dir, { recursive: true })
}

function ensureDataDirs() {
  ensureDir(runsRootDir())
  ensureDir(workspacesRootDir())
  ensureDir(reposRootDir())
  ensureDir(rulesRootDir())
  ensureDir(branchTemplatesRootDir())
}

function currentOwner() {
  try {
    return os.userInfo().username?.trim() || process.env.USERNAME?.trim() || 'unknown'
  } catch {
    return process.env.USERNAME?.trim() || 'unknown'
  }
}

function ownerKey(owner = currentOwner()) {
  return owner.replace(/[^\w.-]+/g, '_')
}

function workspaceProfilePath(owner = currentOwner()) {
  return path.resolve(workspacesRootDir(), `${ownerKey(owner)}.json`)
}

function repoProfilesPath(owner = currentOwner()) {
  return path.resolve(reposRootDir(), `${ownerKey(owner)}.json`)
}

function rulesPath(owner = currentOwner()) {
  return path.resolve(rulesRootDir(), `${ownerKey(owner)}.json`)
}

function branchTemplatesPath(owner = currentOwner()) {
  return path.resolve(branchTemplatesRootDir(), `${ownerKey(owner)}.json`)
}

function runDir(runId: string) {
  return path.resolve(runsRootDir(), runId)
}

function ensureRunDirs(runId: string) {
  ensureDir(runDir(runId))
  ensureDir(path.resolve(runDir(runId), 'logs'))
  ensureDir(path.resolve(runDir(runId), 'artifacts'))
}

function runMetaPath(runId: string) {
  return path.resolve(runDir(runId), 'meta.json')
}

function runConfigPath(runId: string) {
  return path.resolve(runDir(runId), 'config.json')
}

function runLogPath(runId: string) {
  return path.resolve(runDir(runId), 'logs', 'runtime.log.txt')
}

function createRunId() {
  return `${Date.now()}-${crypto.randomBytes(4).toString('hex')}`
}

function writeRunMeta(meta: ModemBaselineRunMeta) {
  ensureRunDirs(meta.runId)
  fs.writeFileSync(runMetaPath(meta.runId), JSON.stringify(meta, null, 2), 'utf-8')
}

function readJsonFile<T>(filePath: string, fallback: T): T {
  try {
    if (!fs.existsSync(filePath)) return fallback
    return JSON.parse(fs.readFileSync(filePath, 'utf-8')) as T
  } catch {
    return fallback
  }
}

function writeJsonFile(filePath: string, value: unknown) {
  ensureDir(path.dirname(filePath))
  fs.writeFileSync(filePath, JSON.stringify(value, null, 2), 'utf-8')
}

export function getModemPatchWorkspaceProfile(owner = currentOwner()): UserWorkspaceProfile | null {
  ensureDataDirs()
  const filePath = workspaceProfilePath(owner)
  return readJsonFile<UserWorkspaceProfile | null>(filePath, null)
}

export function saveModemPatchWorkspaceProfile(
  input: { mappedPrefix?: string; remotePrefix?: string; roots?: string[] },
  owner = currentOwner(),
): UserWorkspaceProfile {
  ensureDataDirs()
  const mappedPrefix = String(input.mappedPrefix ?? '').trim()
  const remotePrefix = String(input.remotePrefix ?? '').trim()
  if (!mappedPrefix || !remotePrefix) {
    throw new Error('invalid_workspace_profile')
  }
  const roots = Array.from(new Set((input.roots ?? []).map(item => path.win32.normalize(String(item || '').trim())).filter(Boolean)))
  const profile: UserWorkspaceProfile = {
    owner,
    mappedPrefix,
    remotePrefix,
    roots,
    updatedAt: nowIso(),
  }
  writeJsonFile(workspaceProfilePath(owner), profile)
  return profile
}

export function listModemPatchRepos(owner = currentOwner()): RepoProfile[] {
  ensureDataDirs()
  return readJsonFile<RepoProfile[]>(repoProfilesPath(owner), [])
}

function writeRepoProfiles(items: RepoProfile[], owner = currentOwner()) {
  ensureDataDirs()
  writeJsonFile(repoProfilesPath(owner), items)
}

function resolveWorkspaceProfileForWrite(owner = currentOwner()) {
  const profile = getModemPatchWorkspaceProfile(owner)
  if (!profile) {
    throw new Error('workspace_profile_not_found')
  }
  return profile
}

export function createModemPatchRepo(
  input: {
    label?: string
    localPath?: string
    projectName?: string
    platform?: string
    vendor?: string
  },
  owner = currentOwner(),
): RepoProfile {
  const profile = resolveWorkspaceProfileForWrite(owner)
  const label = String(input.label ?? '').trim()
  const localPath = path.win32.normalize(String(input.localPath ?? '').trim())
  if (!label || !localPath) {
    throw new Error('invalid_repo_profile')
  }
  if (!fs.existsSync(localPath)) {
    throw new Error('repo_path_not_found')
  }
  const items = listModemPatchRepos(owner)
  const nextItem: RepoProfile = {
    repoId: crypto.randomBytes(8).toString('hex'),
    owner,
    label,
    localPath,
    mappedPrefix: profile.mappedPrefix,
    remotePrefix: profile.remotePrefix,
    projectName: input.projectName ? String(input.projectName).trim() : undefined,
    platform: input.platform ? String(input.platform).trim() : undefined,
    vendor: input.vendor ? String(input.vendor).trim() : undefined,
    lastUsedAt: nowIso(),
    branchTemplateStatus: 'idle',
    branches: undefined,
  }
  items.unshift(nextItem)
  writeRepoProfiles(items, owner)
  return nextItem
}

function updateRepoBranchTemplateState(
  repoId: string,
  patch: { status?: RepoProfile['branchTemplateStatus']; error?: string; updatedAt?: string },
  owner = currentOwner(),
) {
  const items = listModemPatchRepos(owner)
  const index = items.findIndex(item => item.repoId === repoId)
  if (index < 0) throw new Error('repo_not_found')
  const current = items[index]
  const nextItem: RepoProfile = {
    ...current,
    branchTemplateStatus: patch.status ?? current.branchTemplateStatus,
    branchTemplateError: patch.error !== undefined ? patch.error : current.branchTemplateError,
    branchTemplateUpdatedAt: patch.updatedAt ?? current.branchTemplateUpdatedAt,
  }
  items.splice(index, 1, nextItem)
  writeRepoProfiles(items, owner)
  return nextItem
}

export function updateModemPatchRepo(
  repoId: string,
  input: {
    label?: string
    localPath?: string
    platform?: string
    branches?: RepoProfile['branches']
  },
  owner = currentOwner(),
): RepoProfile {
  const items = listModemPatchRepos(owner)
  const index = items.findIndex(item => item.repoId === repoId)
  if (index < 0) {
    throw new Error('repo_not_found')
  }

  const current = items[index]
  const workspace = getModemPatchWorkspaceProfile(owner)
  const label = input.label !== undefined ? String(input.label).trim() : current.label
  const localPath = input.localPath !== undefined
    ? path.win32.normalize(String(input.localPath).trim())
    : current.localPath
  const platform = input.platform !== undefined
    ? String(input.platform).trim()
    : (current.platform ?? '')
  const branches = input.branches !== undefined ? input.branches : current.branches

  if (!label || !localPath || !platform) {
    throw new Error('invalid_repo_profile')
  }
  if (!fs.existsSync(localPath)) {
    throw new Error('repo_path_not_found')
  }

  const nextItem: RepoProfile = {
    ...current,
    label,
    localPath,
    platform,
    mappedPrefix: workspace?.mappedPrefix ?? current.mappedPrefix,
    remotePrefix: workspace?.remotePrefix ?? current.remotePrefix,
    lastUsedAt: nowIso(),
    branches,
  }
  items.splice(index, 1, nextItem)
  writeRepoProfiles(items, owner)
  if (input.branches !== undefined) {
    syncBranchTemplatesFromRepoBranches(platform, branches, owner)
  }
  return nextItem
}

export function deleteModemPatchRepo(repoId: string, owner = currentOwner()) {
  const items = listModemPatchRepos(owner)
  const nextItems = items.filter(item => item.repoId !== repoId)
  if (nextItems.length === items.length) {
    throw new Error('repo_not_found')
  }
  writeRepoProfiles(nextItems, owner)
  return { success: true as const }
}

function defaultBranchRules(): BranchRule[] {
  const now = nowIso()
  return [
    {
      ruleId: 'default-baseline-upgrade',
      enabled: true,
      label: 'Baseline upgrade (generic)',
      operationType: 'baseline_upgrade',
      nodePattern: '{NODE_BRANCH}',
      trunkPattern: '{target_BRANCH}',
      mpPattern: '{target_BRANCH}',
      defaultTarget: 'trunk',
      updatedAt: now,
    },
  ]
}

export function listModemPatchRules(owner = currentOwner()): BranchRule[] {
  ensureDataDirs()
  const rules = readJsonFile<BranchRule[]>(rulesPath(owner), [])
  if (!rules.length) return defaultBranchRules()
  return rules
}

export function listModemPatchBranchTemplates(owner = currentOwner()): BranchTemplate[] {
  ensureDataDirs()
  return readJsonFile<BranchTemplate[]>(branchTemplatesPath(owner), [])
}

function writeModemPatchRules(items: BranchRule[], owner = currentOwner()) {
  ensureDataDirs()
  writeJsonFile(rulesPath(owner), items)
}

function writeModemPatchBranchTemplates(items: BranchTemplate[], owner = currentOwner()) {
  ensureDataDirs()
  writeJsonFile(branchTemplatesPath(owner), items)
}

function mergeBranchTemplates(items: BranchTemplate[], owner = currentOwner()) {
  const existing = listModemPatchBranchTemplates(owner)
  const merged = new Map<string, BranchTemplate>()
  for (const item of existing) {
    const key = `${normalizeBranchTemplatePlatform(item.platform)}\u0000${item.tos}`
    merged.set(key, item)
  }
  for (const item of items) {
    const key = `${normalizeBranchTemplatePlatform(item.platform)}\u0000${item.tos}`
    merged.set(key, item)
  }
  const nextItems = Array.from(merged.values())
  writeModemPatchBranchTemplates(nextItems, owner)
  return nextItems
}

function syncRepoBranchesFromTemplates(items: BranchTemplate[], owner = currentOwner()) {
  const repos = listModemPatchRepos(owner)
  let changed = false
  const byPlatform = new Map<string, BranchTemplate[]>()
  for (const item of items) {
    const key = normalizeBranchTemplatePlatform(item.platform)
    if (!key) continue
    const list = byPlatform.get(key) || []
    list.push(item)
    byPlatform.set(key, list)
  }

  const nextRepos = repos.map((repo) => {
    const key = normalizeBranchTemplatePlatform(repo.platform || repo.label)
    if (!key) return repo
    const matched = byPlatform.get(key) || []
    if (!matched.length) return repo

    const currentMp = Array.isArray(repo.branches?.mp) ? [...repo.branches.mp] : []
    const mpMap = new Map(currentMp.map(item => [item.tos, item]))
    for (const item of matched) {
      mpMap.set(item.tos, {
        tos: item.tos,
        mpNodeBranch: item.mpNodeBranch || 'master',
        mpBranch: item.mpBranch,
      })
    }
    const mp = Array.from(mpMap.values()).sort((left, right) => left.tos.localeCompare(right.tos))
    const latest = matched[matched.length - 1]
    const nextRepo: RepoProfile = {
      ...repo,
      branches: {
        trunk: {
          nodeBranch: latest.nodeBranch || 'master',
          trunkBranch: latest.trunkBranch,
        },
        mp,
      },
    }
    changed = true
    return nextRepo
  })

  if (changed) writeRepoProfiles(nextRepos, owner)
  return nextRepos
}

export function createModemPatchRule(
  input: Partial<BranchRule> & { label?: string; nodePattern?: string; trunkPattern?: string },
  owner = currentOwner(),
): BranchRule {
  const label = String(input.label ?? '').trim()
  const nodePattern = String(input.nodePattern ?? '').trim()
  const trunkPattern = String(input.trunkPattern ?? '').trim()
  if (!label || !nodePattern || !trunkPattern) {
    throw new Error('invalid_rule')
  }
  const now = nowIso()
  const rule: BranchRule = {
    ruleId: crypto.randomBytes(8).toString('hex'),
    enabled: input.enabled !== false,
    label,
    operationType: input.operationType ?? 'baseline_upgrade',
    platform: input.platform ? String(input.platform).trim() : undefined,
    vendor: input.vendor ? String(input.vendor).trim() : undefined,
    nodePattern,
    trunkPattern,
    mpPattern: input.mpPattern ? String(input.mpPattern).trim() : undefined,
    defaultTarget: input.defaultTarget ?? 'trunk',
    updatedAt: now,
  }
  const items = listModemPatchRules(owner).filter(item => item.ruleId !== 'default-baseline-upgrade')
  items.unshift(rule)
  writeModemPatchRules(items, owner)
  return rule
}

export function updateModemPatchRule(
  ruleId: string,
  input: Partial<BranchRule>,
  owner = currentOwner(),
): BranchRule {
  const items = listModemPatchRules(owner).filter(item => item.ruleId !== 'default-baseline-upgrade')
  const index = items.findIndex(item => item.ruleId === ruleId)
  if (index < 0) {
    throw new Error('rule_not_found')
  }
  const current = items[index]
  const next: BranchRule = {
    ...current,
    enabled: input.enabled !== undefined ? Boolean(input.enabled) : current.enabled,
    label: input.label !== undefined ? String(input.label).trim() : current.label,
    operationType: input.operationType ?? current.operationType,
    platform: input.platform !== undefined ? (input.platform ? String(input.platform).trim() : undefined) : current.platform,
    vendor: input.vendor !== undefined ? (input.vendor ? String(input.vendor).trim() : undefined) : current.vendor,
    nodePattern: input.nodePattern !== undefined ? String(input.nodePattern).trim() : current.nodePattern,
    trunkPattern: input.trunkPattern !== undefined ? String(input.trunkPattern).trim() : current.trunkPattern,
    mpPattern: input.mpPattern !== undefined ? (input.mpPattern ? String(input.mpPattern).trim() : undefined) : current.mpPattern,
    defaultTarget: input.defaultTarget ?? current.defaultTarget,
    updatedAt: nowIso(),
  }
  if (!next.label || !next.nodePattern || !next.trunkPattern) {
    throw new Error('invalid_rule')
  }
  items.splice(index, 1, next)
  writeModemPatchRules(items, owner)
  return next
}

export function deleteModemPatchRule(ruleId: string, owner = currentOwner()) {
  const items = listModemPatchRules(owner).filter(item => item.ruleId !== 'default-baseline-upgrade')
  const nextItems = items.filter(item => item.ruleId !== ruleId)
  if (nextItems.length === items.length) {
    throw new Error('rule_not_found')
  }
  writeModemPatchRules(nextItems, owner)
  return { success: true as const }
}

function normalizeTosVersion(text?: string) {
  const raw = String(text ?? '').trim()
  if (!raw) return ''
  const match = raw.match(/tos\s*([0-9]+(?:\.[0-9]+){1,3})/i)
  if (match) return `tOS${match[1]}`
  return raw
}

const MP_TOS_VERSIONS = new Set(['tOS15.1.2', 'tOS15.1.3', 'tOS16.3'])

const BUILTIN_TOS15_TEMPLATES: Array<Pick<BranchTemplate, 'tos' | 'platform' | 'nodeBranch' | 'trunkBranch' | 'mpBranch' | 'mpNodeBranch'>> = [
  { tos: 'tOS15.1.2', platform: 'GEN95-S', nodeBranch: 'master', trunkBranch: 'PRODUCT_S_s0bsp_GEN95_common', mpBranch: 's0.mp1_v17.23_gen95_mp', mpNodeBranch: 's0.mp1_v17.23_gen95' },
  { tos: 'tOS15.1.2', platform: 'GEN98-S', nodeBranch: 'master', trunkBranch: 'PRODUCT_S_s0mp1rc_NR16_common', mpBranch: 's0.mp1_v17.23_nr16_mp', mpNodeBranch: 's0.mp1_v17.23_nr16' },
  { tos: 'tOS15.1.2', platform: 'GEN99-T', nodeBranch: 'master', trunkBranch: 'PRODUCT_T_t0mp1rc_NR17_common', mpBranch: 't0.mp1_v14.94_nr17_mp', mpNodeBranch: 't0.mp1_v14.94_nr17' },
  { tos: 'tOS15.1.2', platform: 'GEN99-U', nodeBranch: 'master', trunkBranch: 'PRODUCT_U_u0mp1rc_NR17_common', mpBranch: 'u0.mp1_v10.69_nr17_mp', mpNodeBranch: 'u0.mp1_v10.69_nr17' },
  { tos: 'tOS15.1.2', platform: 'GEN93-V', nodeBranch: 'master', trunkBranch: 'PRODUCT_V_v0mp1rc_LR12A_common', mpBranch: 'v0.mp1_v13.29_gen93_mp', mpNodeBranch: 'v0.mp1_v13.29_gen93' },
  { tos: 'tOS15.1.2', platform: 'GEN97-V', nodeBranch: 'master', trunkBranch: 'PRODUCT_V_v0mp1rc_NR15_common', mpBranch: 'v0.mp1_v13.29_gen97_mp', mpNodeBranch: 'v0.mp1_v13.29_gen97' },
  { tos: 'tOS15.1.3', platform: 'GEN98-S(MP1MP2)', nodeBranch: 'master', trunkBranch: 'PRODUCT_S_s0mp1rc_NR16', mpBranch: 's0.mp1_v17.23_nr16_mp', mpNodeBranch: 's0.mp1_v17.23_nr16' },
  { tos: 'tOS15.1.3', platform: 'GEN98-S(MP3)', nodeBranch: 'master', trunkBranch: 'PRODUCT_S_s0mp1rc_NR16_common', mpBranch: 's0.mp1_v17.23_nr16_mp', mpNodeBranch: 's0.mp1_v17.23_nr16' },
  { tos: 'tOS15.1.3', platform: 'GEN97-V', nodeBranch: 'master', trunkBranch: 'PRODUCT_V_v0mp1rc_NR15_common', mpBranch: 'v0.mp1_v13.134_gen97_mp', mpNodeBranch: 'v0.mp1_v13.134_gen97' },
]

function isMpTosVersion(tosVersion?: string) {
  return MP_TOS_VERSIONS.has(normalizeTosVersion(tosVersion))
}

function normalizeBranchTemplateHeader(header: unknown) {
  return String(header ?? '').trim().toLowerCase().replace(/[\s_-]+/g, '')
}

function findBranchTemplateColumn(headerIndex: Map<string, number>, names: string[]) {
  for (const name of names) {
    const column = headerIndex.get(normalizeBranchTemplateHeader(name))
    if (column !== undefined) return column
  }
  return undefined
}

function buildBranchTemplateHeaderIndex(headers: unknown[]) {
  const index = new Map<string, number>()
  headers.forEach((header, col) => {
    const key = normalizeBranchTemplateHeader(header)
    if (key) index.set(key, col)
  })
  return index
}

function deriveMpNodeBranch(mpBranch: string) {
  const trimmed = String(mpBranch ?? '').trim()
  if (!trimmed) return ''
  if (/_mp$/i.test(trimmed)) {
    return trimmed.replace(/_mp$/i, '')
  }
  return trimmed
}

function normalizeBranchTemplatePlatform(text?: string) {
  return normalizePlatformToken(String(text ?? '').replace(/\s*\([^)]*\)\s*$/, ''))
}

function findBranchTemplateMatches(
  templates: BranchTemplate[],
  tosVersion?: string,
  platform?: string,
) {
  const normalizedTos = normalizeTosVersion(tosVersion)
  const normalizedPlatform = normalizeBranchTemplatePlatform(platform)
  return templates.filter((item) => {
    if (normalizedTos && item.tos !== normalizedTos) return false
    if (!normalizedPlatform) return true
    return normalizeBranchTemplatePlatform(item.platform) === normalizedPlatform
  })
}

function parseModemPatchBranchTemplatesFromExcel(
  filePath: string,
  owner = currentOwner(),
): { sourcePath: string; items: BranchTemplate[] } {
  const resolved = path.resolve(String(filePath ?? '').trim())
  if (!resolved) {
    throw new Error('invalid_branch_template_file')
  }
  if (!fs.existsSync(resolved)) {
    throw new Error('branch_template_file_not_found')
  }

  let workbook: XLSX.WorkBook
  try {
    workbook = XLSX.readFile(resolved, { cellDates: false })
  } catch (error) {
    const message = String((error as Error)?.message ?? error)
    if (message.includes('EBUSY') || message.includes('locked')) {
      throw new Error('branch_template_file_busy')
    }
    throw error
  }

  const items: BranchTemplate[] = []
  const updatedAt = nowIso()

  for (const sheetName of workbook.SheetNames) {
    const sheet = workbook.Sheets[sheetName]
    if (!sheet) continue
    const rows = XLSX.utils.sheet_to_json(sheet, {
      header: 1,
      defval: '',
      raw: false,
    }) as unknown[][]
    if (!rows.length) continue

    const headerIndex = buildBranchTemplateHeaderIndex(rows[0])
    const tosCol = findBranchTemplateColumn(headerIndex, ['tos', 'tos版本', '版本'])
    const platformCol = findBranchTemplateColumn(headerIndex, ['platform', '平台'])
    const trunkCol = findBranchTemplateColumn(headerIndex, ['trunk_branch', 'trunkbranch', '主干分支', 'modem共仓主干'])
    const mpCol = findBranchTemplateColumn(headerIndex, ['mp_branch', 'mpbranch', '量产分支', 'modem共仓量产'])
    const mpNodeCol = findBranchTemplateColumn(headerIndex, ['mp_node_branch', 'mpnodebranch', 'mp节点分支', '量产节点分支'])
    const nodeCol = findBranchTemplateColumn(headerIndex, ['node_branch', 'nodebranch', 'trunk_node_branch', '主干节点分支', '节点分支'])

    if (platformCol === undefined || trunkCol === undefined || mpCol === undefined) {
      throw new Error(`branch_template_missing_columns:${sheetName}`)
    }

    let currentTos = normalizeTosVersion(String(tosCol !== undefined ? rows[1]?.[tosCol] ?? '' : '')) || normalizeTosVersion(sheetName)
    for (let rowIndex = 1; rowIndex < rows.length; rowIndex += 1) {
      const row = rows[rowIndex]
      if (!Array.isArray(row)) continue

      if (tosCol !== undefined) {
        const rowTos = normalizeTosVersion(String(row[tosCol] ?? ''))
        if (rowTos) currentTos = rowTos
      }

      const platform = String(row[platformCol] ?? '').trim()
      const trunkBranch = String(row[trunkCol] ?? '').trim()
      const mpBranch = String(row[mpCol] ?? '').trim()
      if (!platform && !trunkBranch && !mpBranch) continue
      if (!platform || !trunkBranch || !mpBranch) {
        throw new Error(`branch_template_invalid_row:${sheetName}:${rowIndex + 1}`)
      }

      const nodeBranch = nodeCol !== undefined ? String(row[nodeCol] ?? '').trim() || 'master' : 'master'
      const mpNodeBranch = mpNodeCol !== undefined
        ? String(row[mpNodeCol] ?? '').trim() || deriveMpNodeBranch(mpBranch)
        : deriveMpNodeBranch(mpBranch)

      items.push({
        templateId: crypto.randomBytes(8).toString('hex'),
        owner,
        tos: currentTos || normalizeTosVersion(sheetName),
        platform,
        nodeBranch,
        trunkBranch,
        mpBranch,
        mpNodeBranch,
        sourceFile: resolved,
        sourceSheet: sheetName,
        updatedAt,
      })
    }
  }

  if (!items.length) {
    throw new Error('branch_template_empty')
  }

  return {
    sourcePath: resolved,
    items,
  }
}

export function importModemPatchBranchTemplatesFromExcel(
  filePath: string,
  owner = currentOwner(),
): { sourcePath: string; items: BranchTemplate[] } {
  const result = parseModemPatchBranchTemplatesFromExcel(filePath, owner)
  mergeBranchTemplates(result.items, owner)
  syncRepoBranchesFromTemplates(result.items, owner)
  return result
}

function normalizeOperationType(text: string): ModemPatchOperationType {
  const lower = text.toLowerCase()
  if (lower.includes('baseline') || text.includes('基线')) return 'baseline_upgrade'
  if (lower.includes('patch')) return 'patch'
  return 'unknown'
}

function normalizePlatformToken(text?: string) {
  const raw = String(text ?? '').trim().toUpperCase().replace(/[_\s]+/g, '')
  if (!raw) return ''
  const unified = raw.replace(/-([STUVW])$/, '$1')
  const matched = unified.match(/^(GEN\d+(?:-R\d+)?)([STUVW])?$/)
  if (!matched) return unified
  return `${matched[1]}${matched[2] ?? ''}`
}

function basePlatformToken(text?: string) {
  const normalized = normalizePlatformToken(text)
  const matched = normalized.match(/^(GEN\d+(?:-R\d+)?)([STUVW])?$/)
  return matched?.[1] ?? normalized
}

export function parseModemPatchNotice(text: string): NoticeParseResult {
  const rawText = String(text ?? '').trim()
  const warnings: string[] = []
  const platforms = Array.from(new Set(
    (rawText.match(/GEN\d+(?:-R\d+)?(?:-?[STUVW])?/gi) || [])
      .map(item => normalizePlatformToken(item))
      .filter(Boolean),
  ))
  const versionMatch = rawText.match(/\bV\d+(?:\.\d+){0,4}\b/i)
  const tosMatch = rawText.match(/\btOS\s*\d+(?:\.\d+){1,3}(?:\s*MP)?\b/i)
  const specialMpMatch = rawText.match(/\b(15\.1\.2|15\.1\.3|16\.3)(?:\s*MP)?\b/i)
  const explicitMp = /\bMP\b/i.test(rawText)
  const platform = platforms[0]
  const version = versionMatch ? versionMatch[0].toUpperCase() : undefined
  const tosVersion = tosMatch
    ? normalizeTosVersion(tosMatch[0])
    : specialMpMatch
      ? normalizeTosVersion(`tOS${specialMpMatch[1]}`)
      : undefined
  const targetMode = explicitMp || isMpTosVersion(tosVersion) ? 'mp' : 'trunk'
  const operationType = normalizeOperationType(rawText)

  let confidence = 0.2
  if (platform) confidence += 0.4
  if (version) confidence += 0.2
  if (tosVersion) confidence += 0.1
  if (operationType !== 'unknown') confidence += 0.2
  confidence = Math.min(1, confidence)

  if (!platforms.length) warnings.push('no_platform_detected')
  if (!version) warnings.push('no_version_detected')

  return {
    rawText,
    operationType,
    platform,
    tosVersion,
    targetMode,
    version,
    confidence,
    candidates: { platforms },
    warnings,
  }
}

function applyTemplate(template: string, vars: Record<string, string>) {
  let out = template
  for (const [key, value] of Object.entries(vars)) {
    out = out.replaceAll(`{${key}}`, value)
  }
  return out
}

export function recommendModemPatchConfig(input: {
  noticeText?: string
  repoId?: string
  config?: Partial<ModemBaselineConfig>
}, owner = currentOwner()): RecommendationResult {
  const warnings: string[] = []
  const parsed = input.noticeText ? parseModemPatchNotice(input.noticeText) : null
  const repos = listModemPatchRepos(owner)
  const repo = input.repoId ? repos.find(item => item.repoId === input.repoId) : null
  const platform = normalizePlatformToken(parsed?.platform || repo?.platform || '')
  const basePlatform = basePlatformToken(platform)
  const vendor = (repo?.vendor || '').trim()
  const operationType = parsed?.operationType || 'baseline_upgrade'
  const targetMode = parsed?.targetMode || 'trunk'
  const rules = listModemPatchRules(owner).filter(item => item.enabled)
  const templates = listModemPatchBranchTemplates(owner)
  const templateMatches = findBranchTemplateMatches(templates, parsed?.tosVersion, parsed?.platform || repo?.platform)
  const uniqueTemplateMatches = templateMatches.length > 1
    ? Array.from(new Map(
      templateMatches.map(item => [
        `${String(item.nodeBranch || '').trim()}\u0000${String(item.trunkBranch || '').trim()}\u0000${String(item.mpNodeBranch || '').trim()}\u0000${String(item.mpBranch || '').trim()}`,
        item,
      ]),
    ).values())
    : templateMatches
  const canUseSharedTrunkTemplate = targetMode === 'trunk' && !parsed?.tosVersion
  let selectedTemplate = uniqueTemplateMatches.length === 1 ? uniqueTemplateMatches[0] : null
  let selectedTemplateNodeBranch: string | undefined
  let selectedTemplateTargetBranch: string | undefined
  let templateAmbiguous = uniqueTemplateMatches.length > 1

  if (!selectedTemplate && canUseSharedTrunkTemplate && uniqueTemplateMatches.length > 1) {
    const trunkCombos = Array.from(new Map(
      uniqueTemplateMatches.map(item => [
        `${item.nodeBranch}\u0000${item.trunkBranch}`,
        { nodeBranch: item.nodeBranch, trunkBranch: item.trunkBranch },
      ]),
    ).values())
    if (trunkCombos.length === 1) {
      selectedTemplateNodeBranch = trunkCombos[0].nodeBranch
      selectedTemplateTargetBranch = trunkCombos[0].trunkBranch
      templateAmbiguous = false
    }
  }

  const matched = rules
    .map((rule) => {
      const rulePlatform = normalizePlatformToken(rule.platform || '')
      const ruleBasePlatform = basePlatformToken(rulePlatform)
      let platformScore = 0
      if (rulePlatform) {
        if (!platform) return null
        if (rulePlatform === platform) platformScore = 3
        else if (ruleBasePlatform === basePlatform) platformScore = 2
        else return null
      }

      const vendorScore = rule.vendor ? 1 : 0
      return {
        rule,
        platformScore,
        vendorScore,
      }
    })
    .filter((entry): entry is { rule: BranchRule; platformScore: number; vendorScore: number } => Boolean(entry))
    .filter(({ rule }) => {
    if (rule.operationType && rule.operationType !== operationType) return false
    if (rule.vendor && vendor && rule.vendor.toLowerCase() !== vendor.toLowerCase()) return false
    if (rule.vendor && !vendor) return false
    return true
    })
    .sort((left, right) => {
      if (right.platformScore !== left.platformScore) return right.platformScore - left.platformScore
      if (right.vendorScore !== left.vendorScore) return right.vendorScore - left.vendorScore
      return 0
    })[0]?.rule || null

  if (templateAmbiguous) warnings.push('branch_template_ambiguous')
  else if (!uniqueTemplateMatches.length && parsed?.platform) warnings.push('branch_template_not_found')
  if (!selectedTemplate && !selectedTemplateNodeBranch && !matched) warnings.push('no_rule_matched')
  const vars: Record<string, string> = {
    platform: platform || basePlatform,
    version: parsed?.version || '',
    vendor,
    NODE_BRANCH: String(input.config?.NODE_BRANCH ?? '').trim(),
    target_BRANCH: String(input.config?.target_BRANCH ?? '').trim(),
  }

  const apLabel = parsed?.version || (String(input.config?.AP_lable ?? '').trim() || undefined)
  const defaultTarget = targetMode === 'mp' ? 'mp' : (matched?.defaultTarget || 'trunk')
  let branchSource: RecommendationResult['branchSource']
  const nodeBranch = selectedTemplate
    ? (defaultTarget === 'mp' ? selectedTemplate.mpNodeBranch : selectedTemplate.nodeBranch)
    : selectedTemplateNodeBranch
      ? selectedTemplateNodeBranch
    : matched?.nodePattern
      ? applyTemplate(matched.nodePattern, vars)
      : undefined
  const targetBranch = selectedTemplate
    ? (defaultTarget === 'mp' ? selectedTemplate.mpBranch : selectedTemplate.trunkBranch)
    : selectedTemplateTargetBranch
      ? selectedTemplateTargetBranch
    : matched
      ? applyTemplate(defaultTarget === 'mp' ? (matched.mpPattern || matched.trunkPattern) : matched.trunkPattern, vars)
      : undefined

  if (selectedTemplate || selectedTemplateNodeBranch) branchSource = 'template'
  else if (matched) branchSource = 'rule'

  if (nodeBranch && nodeBranch.includes('{')) warnings.push('unresolved_placeholders_in_node')
  if (targetBranch && targetBranch.includes('{')) warnings.push('unresolved_placeholders_in_target')

  return {
    nodeBranch: nodeBranch || undefined,
    targetBranch: targetBranch || undefined,
    apLabel,
    ruleId: matched?.ruleId,
    branchSource,
    targetMode: defaultTarget,
    warnings,
  }
}

function isGitRepoPath(targetPath: string) {
  if (!fs.existsSync(targetPath)) return false
  try {
    const dotGit = path.resolve(targetPath, '.git')
    if (fs.existsSync(dotGit)) return true
    const result = spawnSync('git', ['-C', targetPath, 'rev-parse', '--show-toplevel'], {
      windowsHide: true,
      timeout: 5000,
      encoding: 'utf-8',
    })
    return result.status === 0
  } catch {
    return false
  }
}

type TosToken = { full: string; key: string; major: number; minor: number; patch: number }

function parseTosToken(branch: string): TosToken | null {
  const match = String(branch || '').match(/^tOS\s*([0-9]+(?:\.[0-9]+){1,3})/i)
  if (!match) return null
  const parts = match[1].split('.').map(part => Number(part) || 0)
  const major = parts[0] ?? 0
  const minor = parts[1] ?? 0
  const patch = parts[2] ?? 0
  return {
    full: `tOS${match[1]}`,
    key: `tOS${major}.${minor}`,
    major,
    minor,
    patch,
  }
}

function compareTosToken(left: { major: number; minor: number; patch: number }, right: { major: number; minor: number; patch: number }) {
  if (left.major !== right.major) return left.major - right.major
  if (left.minor !== right.minor) return left.minor - right.minor
  return left.patch - right.patch
}

function tosKeyToToken(tos: string) {
  const match = String(tos || '').match(/^tOS\s*([0-9]+)\.([0-9]+)/i)
  if (!match) return null
  return { major: Number(match[1]) || 0, minor: Number(match[2]) || 0, patch: 0 }
}

function pickOne(values: string[]) {
  if (!values.length) return { value: '', ambiguous: false }
  if (values.length === 1) return { value: values[0], ambiguous: false }
  return { value: '', ambiguous: true }
}

function listRemoteBranches(repoPath: string, remote: string) {
  const result = spawnSync('git', ['-C', repoPath, 'ls-remote', '--heads', remote], {
    windowsHide: true,
    timeout: 15000,
    encoding: 'utf-8',
  })
  if (result.status !== 0) {
    const stderr = String(result.stderr || '').trim()
    throw new Error(stderr || `git_ls_remote_failed:${result.status ?? -1}`)
  }
  const stdout = String(result.stdout || '')
  return stdout
    .split(/\r?\n/g)
    .map(line => line.trim())
    .filter(Boolean)
    .map(line => line.split(/\s+/g)[1] || '')
    .map(ref => ref.replace(/^refs\/heads\//, ''))
    .filter(Boolean)
}

function pickTrunkBranch(branches: string[]) {
  const candidates = branches.filter(name => name.endsWith('_common'))
  return pickOne(Array.from(new Set(candidates)).sort())
}

function pickBuiltinTrunkBranch(
  templates: Array<Pick<BranchTemplate, 'nodeBranch' | 'trunkBranch'>>,
) {
  const candidates = Array.from(new Map(
    templates
      .map(item => ({
        nodeBranch: String(item.nodeBranch || 'master').trim() || 'master',
        trunkBranch: String(item.trunkBranch || '').trim(),
      }))
      .filter(item => item.trunkBranch)
      .map(item => [`${item.nodeBranch}::${item.trunkBranch}`, item]),
  ).values()).sort((left, right) => (
    left.trunkBranch.localeCompare(right.trunkBranch) || left.nodeBranch.localeCompare(right.nodeBranch)
  ))

  if (candidates.length === 1) return { value: candidates[0], ambiguous: false }
  if (candidates.length > 1) return { value: null, ambiguous: true }
  return { value: null, ambiguous: false }
}

function pickMpBranches(branches: string[], baseline: TosToken) {
  const candidates = branches
    .filter(name => /^tOS[0-9]+\.[0-9]+/i.test(name))
    .filter(name => !/_node$/i.test(name))
    .map(name => ({ name, token: parseTosToken(name) }))
    .filter(item => item.token && compareTosToken(item.token, baseline) >= 0) as Array<{ name: string; token: TosToken }>

  const byKey = new Map<string, Array<{ name: string; token: TosToken }>>()
  for (const item of candidates) {
    const list = byKey.get(item.token.key) || []
    list.push(item)
    byKey.set(item.token.key, list)
  }

  const picks: Array<{ name: string; token: TosToken }> = []
  for (const [key, items] of byKey.entries()) {
    const sorted = items.sort((left, right) => {
      const leftRelease = /release/i.test(left.name) ? 1 : 0
      const rightRelease = /release/i.test(right.name) ? 1 : 0
      if (leftRelease !== rightRelease) return rightRelease - leftRelease
      const diff = compareTosToken(left.token, right.token)
      if (diff !== 0) return -diff
      return left.name.localeCompare(right.name)
    })
    const picked = sorted[0]
    if (picked) picks.push(picked)
  }

  return picks.sort((a, b) => compareTosToken(a.token, b.token))
}

function pickMpNodeBranch(branches: string[], token: TosToken) {
  const candidates = branches.filter(name => /_node$/i.test(name))
  const strict = candidates.filter(name => name.includes(token.full))
  const relaxed = candidates.filter(name => name.startsWith(token.key) || name.includes(token.key))
  const best = strict.length ? strict : relaxed
  const picked = pickOne(Array.from(new Set(best)).sort())
  if (picked.value) return { value: picked.value, ambiguous: picked.ambiguous }
  return { value: 'master', ambiguous: false }
}

function collectTos15TemplatesForRepo(
  repo: RepoProfile,
  remoteBranches: string[],
  owner = currentOwner(),
) {
  const normalizedPlatform = normalizeBranchTemplatePlatform(repo.platform || repo.label)
  const branchSet = new Set(remoteBranches)
  return BUILTIN_TOS15_TEMPLATES
    .filter(item => normalizeBranchTemplatePlatform(item.platform) === normalizedPlatform)
    .filter(item => branchSet.has(item.mpBranch))
    .map(item => ({
      ...item,
      templateId: crypto.randomBytes(8).toString('hex'),
      owner,
      sourceFile: '',
      sourceSheet: 'builtin-tos15',
      updatedAt: nowIso(),
    }))
}

function mergeBranchTemplatesForPlatform(
  platform: string,
  baselineKey: string,
  nextItems: BranchTemplate[],
  owner = currentOwner(),
) {
  const existing = listModemPatchBranchTemplates(owner)
  const baselineToken = tosKeyToToken(baselineKey) || { major: 16, minor: 3, patch: 0 }
  const normalizedPlatform = normalizeBranchTemplatePlatform(platform)
  const preserved = existing.filter(item => {
    if (normalizeBranchTemplatePlatform(item.platform) !== normalizedPlatform) return true
    const token = tosKeyToToken(item.tos)
    if (!token) return true
    return compareTosToken(token, baselineToken) < 0
  })
  const merged = preserved.concat(nextItems)
  writeModemPatchBranchTemplates(merged, owner)
  return merged
}

function syncBranchTemplatesFromRepoBranches(
  repoPlatform: string,
  branches: RepoProfile['branches'] | undefined,
  owner = currentOwner(),
  baselineKey = 'tOS16.3',
) {
  if (!branches?.trunk?.trunkBranch) return
  const trunkNode = String(branches.trunk.nodeBranch || 'master').trim() || 'master'
  const trunkBranch = String(branches.trunk.trunkBranch || '').trim()
  if (!trunkBranch) return
  const mp = Array.isArray(branches.mp) ? branches.mp : []
  const updatedAt = nowIso()
  const nextTemplates: BranchTemplate[] = mp
    .map(item => ({
      templateId: crypto.randomBytes(8).toString('hex'),
      owner,
      tos: String(item.tos || '').trim(),
      platform: repoPlatform,
      nodeBranch: trunkNode,
      trunkBranch,
      mpBranch: String(item.mpBranch || '').trim(),
      mpNodeBranch: String(item.mpNodeBranch || '').trim() || 'master',
      sourceFile: '',
      sourceSheet: 'manual',
      updatedAt,
    }))
    .filter(item => item.tos && item.mpBranch)

  if (!nextTemplates.length) return
  mergeBranchTemplatesForPlatform(repoPlatform, baselineKey, nextTemplates, owner)
}

export function autoExtractBranchTemplatesForRepo(
  repoId: string,
  owner = currentOwner(),
  options?: { remote?: string; baseline?: string },
) {
  const remote = String(options?.remote || 'origin')
  const baseline = String(options?.baseline || 'tOS16.3')
  const baselineToken = parseTosToken(baseline) || { full: baseline, key: baseline, major: 16, minor: 3, patch: 0 }

  const repo = listModemPatchRepos(owner).find(item => item.repoId === repoId)
  if (!repo) throw new Error('repo_not_found')
  const platform = String(repo.platform || repo.label || '').trim()
  const localPath = String(repo.localPath || '').trim()
  if (!platform || !localPath) throw new Error('invalid_repo_profile')
  if (!isGitRepoPath(localPath)) throw new Error('not_git_repo')

  updateRepoBranchTemplateState(repoId, { status: 'running', error: '', updatedAt: nowIso() }, owner)

  let errorMessage = ''
  try {
    const branches = listRemoteBranches(localPath, remote)
    const tos15Templates = collectTos15TemplatesForRepo(repo, branches, owner)
    const trunkPicked = pickTrunkBranch(branches)
    const builtinTrunkPicked = trunkPicked.value ? { value: null, ambiguous: false } : pickBuiltinTrunkBranch(tos15Templates)
    const trunkBranch = trunkPicked.value || builtinTrunkPicked.value?.trunkBranch || ''
    const trunkNodeBranch = builtinTrunkPicked.value?.nodeBranch || tos15Templates[0]?.nodeBranch || 'master'
    const extractedTrunk = trunkBranch
      ? {
          nodeBranch: trunkNodeBranch,
          trunkBranch,
        }
      : null
    const mpBranches = pickMpBranches(branches, baselineToken)
    const updatedAt = nowIso()
    const mpEntries: Array<{ tos: string; mpNodeBranch: string; mpBranch: string }> = []
    const extractedMp = mpBranches.map(item => {
      const mpNode = pickMpNodeBranch(branches, item.token)
      mpEntries.push({
        tos: item.token.key,
        mpNodeBranch: mpNode.value,
        mpBranch: item.name,
      })
      return {
        tos: item.token.key,
        mpNodeBranch: mpNode.value,
        mpBranch: item.name,
      }
    })
    const templateTrunk = extractedTrunk || repo.branches?.trunk || null
    const nextTemplates: BranchTemplate[] = templateTrunk
      ? extractedMp.map(item => {
        return {
          templateId: crypto.randomBytes(8).toString('hex'),
          owner,
          tos: item.tos,
          platform,
          nodeBranch: templateTrunk.nodeBranch || 'master',
          trunkBranch: templateTrunk.trunkBranch,
          mpBranch: item.mpBranch,
          mpNodeBranch: item.mpNodeBranch,
          sourceFile: localPath,
          sourceSheet: `auto:${remote}`,
          updatedAt,
        }
      })
      : []

    for (const item of tos15Templates) {
      mpEntries.push({
        tos: item.tos,
        mpNodeBranch: item.mpNodeBranch || 'master',
        mpBranch: item.mpBranch,
      })
    }

    const extractedAny = Boolean(extractedTrunk) || mpEntries.length > 0
    const extractionErrors: string[] = []
    if (!extractedTrunk) {
      extractionErrors.push(
        trunkPicked.ambiguous || builtinTrunkPicked.ambiguous
          ? 'trunk_branch_ambiguous'
          : 'trunk_branch_not_found',
      )
    }
    if (!mpBranches.length && !tos15Templates.length) {
      extractionErrors.push('mp_branch_not_found')
    }
    if (!extractedAny) {
      throw new Error(extractionErrors[0] || 'branch_extract_failed')
    }

    if (nextTemplates.length || tos15Templates.length) {
      mergeBranchTemplatesForPlatform(platform, 'tOS15.1.2', nextTemplates.concat(tos15Templates), owner)
    }

    const currentBranches = repo.branches
    const nextRepoBranches: RepoProfile['branches'] = {
      trunk: extractedTrunk || currentBranches?.trunk,
      mp: mpEntries.length
        ? Array.from(new Map(
          [
            ...((Array.isArray(currentBranches?.mp) ? currentBranches?.mp : []).map(item => [item.tos, item] as const)),
            ...(mpEntries.map(item => [item.tos, item] as const)),
          ],
        ).values()).sort((left, right) => left.tos.localeCompare(right.tos))
        : currentBranches?.mp,
    }

    updateModemPatchRepo(repoId, {
      branches: nextRepoBranches,
    }, owner)

    const partialError = extractionErrors.join('; ')
    updateRepoBranchTemplateState(repoId, {
      status: 'success',
      error: partialError,
      updatedAt: nowIso(),
    }, owner)
    return {
      success: true as const,
      templates: nextTemplates.concat(tos15Templates),
      warnings: extractionErrors,
    }
  } catch (error) {
    errorMessage = String((error as Error)?.message ?? error)
    updateRepoBranchTemplateState(repoId, { status: 'failed', error: errorMessage.slice(0, 500), updatedAt: nowIso() }, owner)
    return { success: false as const, error: errorMessage }
  }
}

export function scheduleAutoExtractBranchTemplatesForRepo(repoId: string, owner = currentOwner()) {
  updateRepoBranchTemplateState(repoId, { status: 'running', error: '', updatedAt: nowIso() }, owner)
  setTimeout(() => {
    try {
      autoExtractBranchTemplatesForRepo(repoId, owner)
    } catch (error) {
      updateRepoBranchTemplateState(repoId, {
        status: 'failed',
        error: String((error as Error)?.message ?? error).slice(0, 500),
        updatedAt: nowIso(),
      }, owner)
    }
  }, 0)
}

export function scanModemPatchRepos(root: string, owner = currentOwner()): { root: string; items: ScannedRepoCandidate[]; warnings: string[] } {
  const profile = resolveWorkspaceProfileForWrite(owner)
  const normalizedRoot = path.win32.normalize(String(root ?? '').trim())
  if (!normalizedRoot) {
    throw new Error('invalid_scan_root')
  }
  const warnings: string[] = []
  if (!fs.existsSync(normalizedRoot)) {
    throw new Error('scan_root_not_found')
  }
  const rootAllowed = profile.roots.some(item => path.win32.normalize(item) === normalizedRoot)
  if (!rootAllowed) {
    warnings.push('scan_root_not_in_workspace_roots')
  }

  const items: ScannedRepoCandidate[] = []
  const queue: Array<{ dir: string; depth: number }> = [{ dir: normalizedRoot, depth: 0 }]
  const seen = new Set<string>()
  const maxDepth = 6
  const maxCandidates = 200

  while (queue.length && items.length < maxCandidates) {
    const current = queue.shift()
    if (!current) break
    const dir = path.win32.normalize(current.dir)
    if (seen.has(dir)) continue
    seen.add(dir)

    let entries: fs.Dirent[] = []
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true })
    } catch (error) {
      warnings.push(`scan_failed:${dir}:${String((error as Error)?.message ?? error)}`)
      continue
    }

    const hasGit = entries.some(entry => entry.name === '.git')
    if (hasGit) {
      items.push({
        localPath: dir,
        repoName: path.basename(dir),
        isGitRepo: true,
      })
      continue
    }

    if (current.depth >= maxDepth) continue
    for (const entry of entries) {
      if (!entry.isDirectory()) continue
      if (entry.name === '.git' || entry.name === 'node_modules' || entry.name === '.repo') continue
      queue.push({ dir: path.resolve(dir, entry.name), depth: current.depth + 1 })
    }
  }

  return { root: normalizedRoot, items, warnings }
}

export function scanModemPatchReposMulti(
  roots: unknown,
  owner = currentOwner(),
): { roots: string[]; items: ScannedRepoCandidate[]; warnings: string[] } {
  const list = Array.isArray(roots)
    ? roots.map(item => String(item ?? '').trim()).filter(Boolean)
    : String(roots ?? '').trim()
      ? [String(roots ?? '').trim()]
      : []
  const normalizedRoots = Array.from(new Set(list.map(item => path.win32.normalize(item))))
  if (!normalizedRoots.length) {
    throw new Error('invalid_scan_root')
  }

  const rootList: string[] = []
  const warnings: string[] = []
  const map = new Map<string, ScannedRepoCandidate>()

  for (const root of normalizedRoots) {
    try {
      const result = scanModemPatchRepos(root, owner)
      rootList.push(result.root)
      for (const warning of result.warnings) warnings.push(`${result.root}:${warning}`)
      for (const item of result.items) {
        map.set(path.win32.normalize(item.localPath).toUpperCase(), item)
      }
    } catch (error) {
      warnings.push(`scan_root_failed:${root}:${String((error as Error)?.message ?? error)}`)
    }
  }

  return { roots: rootList, items: Array.from(map.values()), warnings }
}

export function readModemBaselineRun(runId: string): ModemBaselineRunMeta | null {
  const metaPath = runMetaPath(runId)
  if (!fs.existsSync(metaPath)) return null
  try {
    return JSON.parse(fs.readFileSync(metaPath, 'utf-8')) as ModemBaselineRunMeta
  } catch {
    return null
  }
}

export function listModemBaselineRuns(): ModemBaselineRunMeta[] {
  ensureDataDirs()
  const items: ModemBaselineRunMeta[] = []
  const entries = fs.readdirSync(runsRootDir(), { withFileTypes: true })
  for (const entry of entries) {
    if (!entry.isDirectory()) continue
    const meta = readModemBaselineRun(entry.name)
    if (meta) items.push(meta)
  }
  return items.sort((a, b) => (a.createdAt < b.createdAt ? 1 : -1))
}

export function readModemBaselineLog(runId: string) {
  const meta = readModemBaselineRun(runId)
  if (!meta?.logPath || !fs.existsSync(meta.logPath)) return ''
  return fs.readFileSync(meta.logPath, 'utf-8')
}

function sendEvent(res: ServerResponse, event: string, data: unknown) {
  res.write(`event: ${event}\n`)
  res.write(`data: ${JSON.stringify(data)}\n\n`)
}

function runtimeFor(runId: string) {
  let runtime = runtimes.get(runId)
  if (!runtime) {
    runtime = { runId, clients: new Set(), logLineOpen: false }
    runtimes.set(runId, runtime)
  }
  return runtime
}

function broadcast(runId: string, event: string, data: unknown) {
  const runtime = runtimes.get(runId)
  if (!runtime) return
  for (const client of runtime.clients) {
    try {
      sendEvent(client, event, data)
    } catch {
      runtime.clients.delete(client)
    }
  }
}

function inferPhaseFromStatus(status: ModemBaselineStatus, phase?: ModemBaselinePhase): ModemBaselinePhase {
  if (status === 'conflict') return 'conflict'
  if (status === 'success') return 'archive'
  if (status === 'running') {
    if (phase === 'build') return 'build'
    if (phase === 'resume') return 'resume'
    if (phase === 'precheck') return 'precheck'
    return 'merge'
  }
  if (phase === 'build') return 'build'
  return phase === 'resume' ? 'resume' : phase === 'archive' ? 'archive' : phase === 'conflict' ? 'conflict' : 'merge'
}

const BUILD_PROJECT_NAME_RE = /^[A-Za-z0-9][A-Za-z0-9._+-]*$/

function sanitizeBuildProjectName(value: unknown): string | undefined {
  const name = String(value ?? '').trim()
  if (!name || !BUILD_PROJECT_NAME_RE.test(name)) return undefined
  return name
}

function shellSingleQuote(value: string) {
  return `'${value.replace(/'/g, `'\\''`)}'`
}

function evaluateModemBuildResult(result: HarnessResult): boolean {
  const combined = `${String(result.output ?? '')}\n${String(result.error ?? '')}`
  const successMarker = /make\s+modem\s+completed\s+su+cessfully/i.test(combined)
    || /####\s*make\s+modem\s+completed\s+su+cessfully\s*####/i.test(combined)
  const failureMarker = /make\s+modem\s+failed/i.test(combined)
    || /modem\s+build\s+failed/i.test(combined)

  if (successMarker && !failureMarker) return true
  if (failureMarker) return false
  return result.status === 'ok' && (result.exit_code === 0 || result.exit_code == null)
}

function filterBuildProjectNames(names: string[]) {
  return Array.from(new Set(
    names
      .map(name => String(name ?? '').trim())
      .filter(name => name && !name.startsWith('.') && BUILD_PROJECT_NAME_RE.test(name)),
  )).sort((a, b) => a.localeCompare(b))
}

function listBuildProjectsLocal(projectsDir: string): string[] {
  if (!fs.existsSync(projectsDir)) return []
  let stat: fs.Stats
  try {
    stat = fs.statSync(projectsDir)
  } catch {
    return []
  }
  if (!stat.isDirectory()) return []

  // 映射盘/SMB 上 Dirent.isDirectory() 常不可靠，逐项 stat
  const names: string[] = []
  for (const name of fs.readdirSync(projectsDir)) {
    if (!name || name.startsWith('.')) continue
    try {
      if (fs.statSync(path.win32.resolve(projectsDir, name)).isDirectory()) {
        names.push(name)
      }
    } catch {
      // ignore unreadable entries
    }
  }
  return filterBuildProjectNames(names)
}

async function listBuildProjectsRemote(remoteWorkDir: string): Promise<string[]> {
  const remote = String(remoteWorkDir ?? '').trim()
  if (!remote) return []
  const command = `cd ${shellSingleQuote(remote)} && echo __APM_BEGIN__ && for d in projects/*/; do [ -d "$d" ] || continue; basename "$d"; done; echo __APM_END__`
  const result = await harnessExec(command, { timeoutMs: 60_000 })
  if (result.status !== 'ok' || result.exit_code !== 0) {
    throw new Error(`remote_list_failed status=${result.status} exit_code=${result.exit_code}`)
  }
  const raw = String(result.output ?? '')
  const start = raw.indexOf('__APM_BEGIN__')
  const end = raw.indexOf('__APM_END__', start >= 0 ? start : 0)
  const body = start >= 0
    ? (end >= 0 ? raw.slice(start + '__APM_BEGIN__'.length, end) : raw.slice(start + '__APM_BEGIN__'.length))
    : raw
  const names = body
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(line => line && !line.startsWith('Updating files:'))
  return filterBuildProjectNames(names)
}

/** 根据代码路径列出 work_dir/projects 下的项目名（本地优先，失败/空则走远端） */
export async function listModemBuildProjects(input: {
  work_dir?: string
  mapped_prefix?: string
  remote_prefix?: string
}): Promise<{
  projectsDir: string
  remoteProjectsDir: string
  items: string[]
  source: 'local' | 'remote' | 'none'
  warning?: string
}> {
  const workDir = String(input.work_dir ?? '').trim()
  if (!workDir) throw new Error('work_dir_required')

  const config: ModemBaselineConfig = {
    NODE_BRANCH: '-',
    target_BRANCH: '-',
    AP_lable: '-',
    JIRAID: '-',
    work_dir: workDir,
    mapped_prefix: input.mapped_prefix,
    remote_prefix: input.remote_prefix,
  }
  const mapped = computeMappedWorkDir(config) ?? normalizeWinPath(workDir)
  const remote = computeRemoteWorkDir(config)
  const projectsDir = path.win32.resolve(mapped, 'projects')
  const remoteProjectsDir = `${remote.replace(/\/+$/, '')}/projects`

  try {
    const localItems = listBuildProjectsLocal(projectsDir)
    if (localItems.length) {
      return { projectsDir, remoteProjectsDir, items: localItems, source: 'local' }
    }
  } catch (error) {
    const warning = `local_list_failed: ${String((error as Error)?.message ?? error)}`
    try {
      const remoteItems = await listBuildProjectsRemote(remote)
      if (remoteItems.length) {
        return { projectsDir, remoteProjectsDir, items: remoteItems, source: 'remote', warning }
      }
      return {
        projectsDir,
        remoteProjectsDir,
        items: [],
        source: 'none',
        warning: `${warning}; remote_projects_empty: ${remoteProjectsDir}`,
      }
    } catch (remoteError) {
      return {
        projectsDir,
        remoteProjectsDir,
        items: [],
        source: 'none',
        warning: `${warning}; remote_list_failed: ${String((remoteError as Error)?.message ?? remoteError)}`,
      }
    }
  }

  try {
    const remoteItems = await listBuildProjectsRemote(remote)
    if (remoteItems.length) {
      return { projectsDir, remoteProjectsDir, items: remoteItems, source: 'remote' }
    }
    return {
      projectsDir,
      remoteProjectsDir,
      items: [],
      source: 'none',
      warning: `projects_not_found local=${projectsDir} remote=${remoteProjectsDir}`,
    }
  } catch (remoteError) {
    return {
      projectsDir,
      remoteProjectsDir,
      items: [],
      source: 'none',
      warning: `local_empty=${projectsDir}; remote_list_failed: ${String((remoteError as Error)?.message ?? remoteError)}`,
    }
  }
}

async function runModemBuildAfterResume(
  runId: string,
  config: ModemBaselineConfig,
  appendLog: (line: string) => void,
): Promise<'success' | 'failed'> {
  const project = sanitizeBuildProjectName(config.build_project)
  if (!project) {
    appendLog('[build] skipped: build_project not selected\n')
    return 'success'
  }

  const remote = computeRemoteWorkDir(config)
  updateRunMeta(runId, { status: 'running', phase: 'build', finishedAt: undefined, error: undefined })
  appendLog(`[build] start project=${project} cmd=./tools/bld_modem.sh ${project}\n`)

  const command = `cd ${shellSingleQuote(remote)} && ./tools/bld_modem.sh ${shellSingleQuote(project)}`
  const BUILD_TIMEOUT_MS = 6 * 60 * 60 * 1000
  appendLog(`[build] harness timeout_sec=${Math.ceil(BUILD_TIMEOUT_MS / 1000)}\n`)
  try {
    const result = await harnessExec(command, { timeoutMs: BUILD_TIMEOUT_MS })
    const output = String(result.output ?? '').trim()
    const errorText = String(result.error ?? '').trim()
    if (output) appendLog(`[build] output:\n${output.endsWith('\n') ? output : `${output}\n`}`)
    if (errorText) appendLog(`[build] error:\n${errorText.endsWith('\n') ? errorText : `${errorText}\n`}`)
    appendLog(`[build] done status=${result.status} exit_code=${String(result.exit_code)}\n`)
    if (evaluateModemBuildResult(result)) {
      appendLog(`[build] success project=${project}\n`)
      return 'success'
    }
    // bridge 默认 300s 超时会出现此文案；远端编译可能仍在跑
    if (/timed out waiting for bridge response/i.test(`${output}\n${errorText}`)) {
      appendLog('[build] bridge timed out before modem build finished; treat as failed wait (increase harness --timeout)\n')
    }
    appendLog(`[build] failed project=${project}\n`)
    return 'failed'
  } catch (error) {
    appendLog(`[build] failed: ${String((error as Error)?.message ?? error)}\n`)
    return 'failed'
  }
}

function updateRunMeta(runId: string, patch: Partial<ModemBaselineRunMeta>) {
  const current = readModemBaselineRun(runId)
  if (!current) return null
  const nextMeta: ModemBaselineRunMeta = {
    ...current,
    ...patch,
  }
  nextMeta.phase = inferPhaseFromStatus(nextMeta.status, patch.phase ?? nextMeta.phase)
  writeRunMeta(nextMeta)
  broadcast(runId, 'status', {
    status: nextMeta.status,
    phase: nextMeta.phase,
    reportPath: nextMeta.reportPath,
    error: nextMeta.error,
  })
  return nextMeta
}

export function registerModemBaselineSseClient(runId: string, res: ServerResponse) {
  const meta = readModemBaselineRun(runId)
  if (!meta) {
    throw new Error('run_not_found')
  }

  const runtime = runtimeFor(runId)
  runtime.clients.add(res)

  sendEvent(res, 'status', { status: meta.status, phase: meta.phase, reportPath: meta.reportPath, error: meta.error })
  if (meta.logPath && fs.existsSync(meta.logPath)) {
    const text = fs.readFileSync(meta.logPath, 'utf-8')
    if (text) sendEvent(res, 'log', { line: text, full: true })
  }
  if (meta.conflictFiles?.length) {
    sendEvent(res, 'conflicts', { files: meta.conflictFiles })
  }
}

export function unregisterModemBaselineSseClient(runId: string, res: ServerResponse) {
  runtimes.get(runId)?.clients.delete(res)
}

function summarizeForLog(text: unknown, limit = 160) {
  const normalized = String(text ?? '').replace(/\s+/g, ' ').trim()
  return normalized.length > limit ? `${normalized.slice(0, limit)}...` : normalized
}

async function sleep(ms: number) {
  await new Promise(resolve => setTimeout(resolve, ms))
}

async function harnessExec(command: string, opts?: { timeoutMs?: number }): Promise<HarnessResult> {
  const timeoutMs = opts?.timeoutMs ?? 5 * 60 * 1000
  // harness --timeout 单位为秒；比本地 timer 略短，让 bridge 先返回而非被本地 SIGKILL
  const timeoutSec = Math.max(1, Math.ceil(timeoutMs / 1000))
  const localTimeoutMs = timeoutMs + 30_000
  const isWindows = process.platform === 'win32'
  const appData = process.env.APPDATA
  const npmBinDir = appData ? path.resolve(appData, 'npm') : null
  const harnessPs1 = npmBinDir ? path.resolve(npmBinDir, 'harness.ps1') : null

  return await new Promise<HarnessResult>((resolve, reject) => {
    const args = [
      '--json',
      'remote-runner',
      'bridge-exec',
      '--i-understand-this-runs-raw-shell',
      '--timeout',
      String(timeoutSec),
      '--command',
      command,
    ]

    const env = isWindows && npmBinDir
      ? { ...process.env, PATH: `${process.env.PATH ?? ''};${npmBinDir}` }
      : process.env

    const processRef = isWindows && harnessPs1 && fs.existsSync(harnessPs1)
      ? spawn('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', harnessPs1, ...args], {
          stdio: ['ignore', 'pipe', 'pipe'],
          env,
          windowsHide: true,
        })
      : spawn('harness', args, {
          stdio: ['ignore', 'pipe', 'pipe'],
          env,
          windowsHide: true,
        })

    let stdout = ''
    let stderr = ''
    let settled = false

    const timer = setTimeout(() => {
      if (settled) return
      try {
        processRef.kill('SIGKILL')
      } catch {}
      reject(new Error(`harness timeout after ${timeoutSec}s`))
    }, localTimeoutMs)

    processRef.stdout.on('data', (chunk) => {
      stdout += chunk.toString()
      if (settled) return
      const text = stdout.trim()
      if (!text.startsWith('{')) return
      try {
        const parsed = JSON.parse(text) as HarnessResult
        settled = true
        clearTimeout(timer)
        try {
          processRef.kill('SIGKILL')
        } catch {}
        resolve(parsed)
      } catch {}
    })

    processRef.stderr.on('data', (chunk) => {
      stderr += chunk.toString()
    })

    processRef.on('error', (error) => {
      if (settled) return
      clearTimeout(timer)
      reject(error)
    })

    processRef.on('close', () => {
      if (settled) return
      clearTimeout(timer)
      try {
        resolve(JSON.parse(stdout) as HarnessResult)
      } catch {
        reject(new Error(`invalid harness json: ${stderr || stdout}`))
      }
    })
  })
}

async function localGitExec(cwd: string, args: string[], opts?: { timeoutMs?: number }): Promise<LocalExecResult> {
  const timeoutMs = opts?.timeoutMs ?? 1500
  return await new Promise<LocalExecResult>((resolve) => {
    const processRef = spawn('git', ['-C', cwd, ...args], {
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    })
    let stdout = ''
    let stderr = ''
    let settled = false
    let timedOut = false

    const timer = setTimeout(() => {
      if (settled) return
      timedOut = true
      settled = true
      try {
        processRef.kill('SIGKILL')
      } catch {}
      resolve({ exitCode: null, stdout, stderr, timedOut })
    }, timeoutMs)

    processRef.stdout.on('data', (chunk) => {
      stdout += chunk.toString()
    })

    processRef.stderr.on('data', (chunk) => {
      stderr += chunk.toString()
    })

    processRef.on('error', () => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve({ exitCode: 1, stdout, stderr, timedOut })
    })

    processRef.on('close', (exitCode) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve({ exitCode, stdout, stderr, timedOut })
    })
  })
}

type WinPrefix = { kind: 'drive' | 'path'; value: string }

function normalizeWinPath(value: string) {
  return path.win32.normalize(String(value ?? '').trim()).replace(/\//g, '\\')
}

function parseWinPrefix(prefix: string): WinPrefix | null {
  const raw = String(prefix ?? '').trim().replace(/\//g, '\\')
  if (!raw) return null
  const driveRootMatch = raw.match(/^([A-Za-z]):\\?$/)
  if (driveRootMatch) {
    return { kind: 'drive', value: `${driveRootMatch[1].toUpperCase()}:` }
  }
  const normalized = path.win32.normalize(raw).replace(/[\\]+$/, '')
  if (!normalized) return null
  return { kind: 'path', value: normalized }
}

function winPathStartsWithPrefix(workDir: string, prefix: WinPrefix) {
  const normalizedWorkDir = normalizeWinPath(workDir).toUpperCase()
  const normalizedPrefix = String(prefix.value).toUpperCase()
  return normalizedWorkDir.startsWith(normalizedPrefix)
}

function computeRemoteWorkDir(config: ModemBaselineConfig) {
  const remotePrefix = config.remote_prefix ?? '/work/user/code'
  const normalizedWorkDir = normalizeWinPath(config.work_dir)
  const mappedPrefix = parseWinPrefix(config.mapped_prefix ?? 'Z:')
  if (!mappedPrefix) return normalizedWorkDir
  if (!winPathStartsWithPrefix(normalizedWorkDir, mappedPrefix)) return normalizedWorkDir
  let relative = normalizedWorkDir.slice(mappedPrefix.value.length).replace(/\\/g, '/')
  if (relative && !relative.startsWith('/')) relative = `/${relative}`
  return `${remotePrefix}${relative}`
}

function computeMappedWorkDir(config: ModemBaselineConfig) {
  const normalizedWorkDir = normalizeWinPath(config.work_dir)
  const mappedPrefix = parseWinPrefix(config.mapped_prefix ?? 'Z:')
  if (!mappedPrefix) return null
  if (winPathStartsWithPrefix(normalizedWorkDir, mappedPrefix)) return normalizedWorkDir
  return null
}

function parseMergeConflictLog(text: string) {
  const files = new Set<string>()
  for (const line of text.split('\n')) {
    const matched = line.match(/Merge conflict in\s+(.+?)\s*$/)
    if (matched?.[1]) files.add(matched[1].trim())
  }
  return Array.from(files).sort()
}

function hasConflictMarker(buf: Buffer) {
  if (buf.indexOf(Buffer.from('<<<<<<<')) >= 0) return true
  if (buf.indexOf(Buffer.from('<<<<<<<', 'utf16le')) >= 0) return true
  return false
}

async function listUnmergedFiles(config: ModemBaselineConfig) {
  const remoteWorkDir = computeRemoteWorkDir(config)
  const mapped = computeMappedWorkDir(config)

  if (mapped) {
    try {
      const indexLock = path.resolve(mapped, '.git', 'index.lock')
      if (fs.existsSync(indexLock)) {
        return ['.git/index.lock']
      }

      const parseGitLsFilesUnmerged = (text: string) => {
        const files = new Set<string>()
        for (const rawLine of text.split('\n')) {
          const line = rawLine.trim()
          if (!line) continue
          const tabIndex = line.lastIndexOf('\t')
          if (tabIndex < 0) continue
          const file = line.slice(tabIndex + 1).trim()
          if (file) files.add(file)
        }
        return Array.from(files).sort()
      }

      const unmergedByLsFiles = await localGitExec(mapped, ['ls-files', '-u'], { timeoutMs: 1500 })
      if (!unmergedByLsFiles.timedOut && unmergedByLsFiles.exitCode === 0) {
        const files = parseGitLsFilesUnmerged(unmergedByLsFiles.stdout)
        if (files.length) return files
      }

      const localMergeHead = path.resolve(mapped, '.git', 'MERGE_HEAD')
      if (!fs.existsSync(localMergeHead)) return []
    } catch {}
  }

  try {
    const stripAnsi = (value: string) => value.replace(/\x1b\[[0-9;]*[A-Za-z]|\x1b./g, '')
    const extractBetween = (text: string) => {
      const stripped = stripAnsi(text)
      const start = stripped.indexOf('__APM_BEGIN__')
      if (start < 0) return stripped
      const end = stripped.indexOf('__APM_END__', start)
      return end >= 0
        ? stripped.slice(start + '__APM_BEGIN__'.length, end)
        : stripped.slice(start + '__APM_BEGIN__'.length)
    }

    const unmergedByLsFiles = await harnessExec(
      `cd ${remoteWorkDir} && echo __APM_BEGIN__ && (git ls-files -u | cut -f2 | sort -u || true) && echo __APM_END__`,
    )
    if (unmergedByLsFiles.status === 'ok' && unmergedByLsFiles.exit_code === 0) {
      const files = extractBetween(unmergedByLsFiles.output ?? '')
        .split('\n')
        .map(line => line.trim())
        .filter(line => line && !line.startsWith('Updating files:'))
      if (files.length) return files
    }

    const unmergedByDiff = await harnessExec(
      `cd ${remoteWorkDir} && echo __APM_BEGIN__ && (GIT_PAGER=cat git diff --name-only --diff-filter=U || true) && echo __APM_END__`,
    )
    if (unmergedByDiff.status === 'ok' && unmergedByDiff.exit_code === 0) {
      const files = extractBetween(unmergedByDiff.output ?? '')
        .split('\n')
        .map(line => line.trim())
        .filter(line => line && !line.startsWith('Updating files:'))
      if (files.length) return files
    }

    const mergeState = await harnessExec(
      `cd ${remoteWorkDir} && test -f .git/MERGE_HEAD && echo __APM_MERGE_HEAD__ || echo __APM_NO__`,
    )
    if (mergeState.status === 'ok' && mergeState.exit_code === 0) {
      const output = stripAnsi(mergeState.output ?? '')
      if (!output.includes('__APM_MERGE_HEAD__')) return []
    }
  } catch {}

  if (!mapped) return []

  const conflictLog = path.resolve(mapped, 'log', 'merge_conflict.log')
  for (let i = 0; i < 6; i += 1) {
    try {
      if (fs.existsSync(conflictLog)) {
        const parsed = parseMergeConflictLog(fs.readFileSync(conflictLog, 'utf-8'))
        if (parsed.length) {
          return parsed.filter(relativePath => {
            const fullPath = path.resolve(mapped, relativePath.replace(/\//g, path.sep))
            try {
              if (!fs.existsSync(fullPath)) return true
              return hasConflictMarker(fs.readFileSync(fullPath))
            } catch {
              return true
            }
          })
        }
      }
    } catch {}
    await sleep(800)
  }

  return []
}

async function checkBridgeHealthy(appendLog: (line: string) => void, retries = 2, timeoutMs = 60_000) {
  const cached = getCachedBridgeProbe()
  if (cached?.ready) {
    appendLog(`[precheck] bridge check reused cached result ttl_ms=${BRIDGE_PROBE_CACHE_TTL_MS} summary="${cached.summary}"\n`)
    return true
  }

  let lastError: unknown = null
  for (let index = 0; index <= retries; index += 1) {
    try {
      if (index > 0) await sleep(1200)
      appendLog(`[precheck] bridge check attempt=${index + 1}/${retries + 1} timeout_ms=${timeoutMs}\n`)
      const probe = await harnessExec('echo bridge_check', { timeoutMs })
      const outputSummary = summarizeForLog(probe.output)
      const errorSummary = summarizeForLog(probe.error)
      appendLog(
        `[precheck] bridge check attempt=${index + 1}/${retries + 1} result status=${probe.status} exit_code=${probe.exit_code} output="${outputSummary}" error="${errorSummary}"\n`,
      )
      if (probe.status === 'ok' && probe.exit_code === 0 && probe.output?.includes('bridge_check')) {
        rememberBridgeProbeSuccess(`status=${probe.status} exit_code=${probe.exit_code} output="${outputSummary}" error="${errorSummary}"`)
        appendLog(`[precheck] bridge check attempt=${index + 1}/${retries + 1} passed\n`)
        return true
      }
      lastError = new Error(
        `unexpected_probe_result status=${probe.status} exit_code=${probe.exit_code} output="${outputSummary}" error="${errorSummary}"`,
      )
    } catch (error) {
      lastError = error
      appendLog(`[precheck] bridge check attempt=${index + 1}/${retries + 1} failed: ${String((error as Error)?.message ?? error)}\n`)
    }
  }

  appendLog(`[precheck] bridge check failed: ${String((lastError as Error)?.message ?? lastError)}\n`)
  return false
}

async function probeBridge(timeoutMs: number) {
  const cached = getCachedBridgeProbe()
  if (cached?.ready) return cached

  try {
    const probe = await harnessExec('echo bridge_check', { timeoutMs })
    const outputSummary = summarizeForLog(probe.output)
    const errorSummary = summarizeForLog(probe.error)
    const ready = probe.status === 'ok' && probe.exit_code === 0 && probe.output?.includes('bridge_check')
    const summary = `status=${probe.status} exit_code=${probe.exit_code} output="${outputSummary}" error="${errorSummary}"`
    if (ready) rememberBridgeProbeSuccess(summary)
    return {
      ready,
      summary,
    }
  } catch (error) {
    return {
      ready: false,
      summary: `error="${summarizeForLog((error as Error)?.message ?? error)}"`,
    }
  }
}

export async function precheckModemPatchConfig(input: {
  config?: Partial<ModemBaselineConfig>
  repoId?: string
}, owner = currentOwner()): Promise<PrecheckResult> {
  const workspace = getModemPatchWorkspaceProfile(owner)
  const repos = listModemPatchRepos(owner)
  const repo = input.repoId ? repos.find(item => item.repoId === input.repoId) : null
  const config = input.config ?? {}
  const workDir = String(config.work_dir ?? repo?.localPath ?? '').trim()
  const mappedPrefix = String(config.mapped_prefix ?? repo?.mappedPrefix ?? workspace?.mappedPrefix ?? '').trim()
  const remotePrefix = String(config.remote_prefix ?? repo?.remotePrefix ?? workspace?.remotePrefix ?? '').trim()
  const items: PrecheckItem[] = []

  if (!mappedPrefix || !remotePrefix) {
    items.push({
      key: 'workspace_mapping',
      level: 'error',
      title: 'Workspace mapping',
      detail: 'mapped_prefix / remote_prefix is missing',
    })
  } else if (!workDir) {
    items.push({
      key: 'workspace_mapping',
      level: 'error',
      title: 'Workspace mapping',
      detail: 'work_dir is missing',
    })
  } else {
    const normalizedWorkDir = normalizeWinPath(workDir)
    const parsedPrefix = parseWinPrefix(mappedPrefix)
    const mapped = parsedPrefix ? winPathStartsWithPrefix(normalizedWorkDir, parsedPrefix) : false
    const computedRemote = computeRemoteWorkDir({
      NODE_BRANCH: String(config.NODE_BRANCH ?? ''),
      target_BRANCH: String(config.target_BRANCH ?? ''),
      AP_lable: String(config.AP_lable ?? ''),
      JIRAID: String(config.JIRAID ?? ''),
      DESCRIPTION: config.DESCRIPTION ? String(config.DESCRIPTION) : undefined,
      work_dir: normalizedWorkDir,
      mapped_prefix: mappedPrefix,
      remote_prefix: remotePrefix,
    })
    items.push({
      key: 'workspace_mapping',
      level: mapped ? 'ok' : 'warn',
      title: 'Workspace mapping',
      detail: mapped
        ? `${mappedPrefix} -> ${remotePrefix}\nremote path = ${computedRemote}`
        : `work_dir does not start with ${mappedPrefix}\nremote path will be used as-is: ${computedRemote}`,
    })
  }

  if (!workDir) {
    items.push({
      key: 'local_path_exists',
      level: 'error',
      title: 'Local path',
      detail: 'Repository path is empty',
    })
    items.push({
      key: 'git_repo',
      level: 'error',
      title: 'Git repository',
      detail: 'Repository path is empty',
    })
  } else {
    const normalizedWorkDir = path.win32.normalize(workDir)
    if (!fs.existsSync(normalizedWorkDir)) {
      items.push({
        key: 'local_path_exists',
        level: 'error',
        title: 'Local path',
        detail: 'Repository path does not exist',
      })
      items.push({
        key: 'git_repo',
        level: 'error',
        title: 'Git repository',
        detail: 'Repository path does not exist',
      })
    } else {
      items.push({
        key: 'local_path_exists',
        level: 'ok',
        title: 'Local path',
        detail: 'Repository path exists',
      })
      items.push({
        key: 'git_repo',
        level: isGitRepoPath(normalizedWorkDir) ? 'ok' : 'error',
        title: 'Git repository',
        detail: isGitRepoPath(normalizedWorkDir)
          ? 'Valid git repository detected'
          : 'Path exists but is not a valid git repository',
      })
    }
  }

  const bridgeProbe = await probeBridge(60_000)
  items.push({
    key: 'bridge',
    level: bridgeProbe.ready ? 'ok' : 'error',
    title: 'Harness bridge',
    detail: bridgeProbe.ready
      ? `Bridge is ready\n${bridgeProbe.summary}`
      : `Bridge is not ready\n${bridgeProbe.summary}`,
  })

  return {
    canStart: !items.some(item => item.level === 'error'),
    items,
  }
}

function decodeText(buffer: Buffer) {
  const utf8 = buffer.toString('utf-8')
  if (utf8.includes('\u0000')) {
    const utf16 = buffer.toString('utf16le')
    return utf16.charCodeAt(0) === 0xfeff ? utf16.slice(1) : utf16
  }
  return utf8
}

async function postProcessRun(runId: string, config: ModemBaselineConfig, code: number | null, appendLog: (line: string) => void) {
  const current = readModemBaselineRun(runId)
  if (!current) return

  // #region debug-point modem-postprocess-enter
  appendLog(`[debug] postProcessRun enter runId=${runId} code=${String(code)}\n`)
  // #endregion

  const mapped = computeMappedWorkDir(config)
  const remote = computeRemoteWorkDir(config)
  const mergeLogPath = mapped ? path.resolve(mapped, 'log', 'merge_conflict.log') : null
  const localMergeHead = mapped ? path.resolve(mapped, '.git', 'MERGE_HEAD') : null
  const localIndexLock = mapped ? path.resolve(mapped, '.git', 'index.lock') : null
  const localStillInMerge = Boolean(localMergeHead && fs.existsSync(localMergeHead))
  appendLog(
    `[conflicts] mapped=${mapped ?? ''} log=${mergeLogPath ?? ''} log_exists=${mergeLogPath ? fs.existsSync(mergeLogPath) : false} merge_head_exists=${localMergeHead ? fs.existsSync(localMergeHead) : false}\n`,
  )
  if (localIndexLock && fs.existsSync(localIndexLock)) {
    try {
      const stat = fs.statSync(localIndexLock)
      appendLog(`[conflicts] git_index_lock_exists=1 path=${localIndexLock} size=${stat.size} mtime=${stat.mtime.toISOString()}\n`)
    } catch {
      appendLog(`[conflicts] git_index_lock_exists=1 path=${localIndexLock}\n`)
    }
  }

  if (mergeLogPath && fs.existsSync(mergeLogPath)) {
    let text: string | null = null
    let matches = 0
    let readError: unknown = null
    let prevSize = -1
    let stableReads = 0
    let tries = 0

    for (let index = 0; index < 10; index += 1) {
      tries = index + 1
      try {
        const stat = fs.statSync(mergeLogPath)
        const size = stat.size
        text = decodeText(fs.readFileSync(mergeLogPath))
        matches = Array.from(text.matchAll(/Merge conflict in\s+(.+?)\s*$/gm)).length
        const previous = prevSize
        if (matches > 0) break
        stableReads = size > 0 && size === prevSize ? stableReads + 1 : 0
        prevSize = size
        appendLog(`[conflicts] merge_conflict.log retry=${index + 1}/10 size=${size} prev_size=${previous} stable=${stableReads} matches=${matches} text_len=${text.length}\n`)
      } catch (error) {
        readError = error
        appendLog(`[conflicts] merge_conflict.log retry=${index + 1}/10 error=${String((error as Error)?.message ?? error)}\n`)
      }
      await sleep(1000)
    }

    if (text != null) {
      appendLog(`[conflicts] merge_conflict.log done tries=${tries} size=${prevSize} stable=${stableReads}\n`)
      appendLog(`[conflicts] merge_conflict.log matches=${matches}\n`)
    } else if (readError) {
      appendLog(`[conflicts] merge_conflict.log read failed: ${String((readError as Error)?.message ?? readError)}\n`)
    }
  }

  let remoteMergeHead = false
  if (mapped) {
    remoteMergeHead = localStillInMerge
    appendLog(`[conflicts] remote_merge_head=SKIP(mapped) local_merge_head=${Number(localStillInMerge)}\n`)
  } else {
    try {
      const mergeHeadProbe = await harnessExec(`cd ${remote} && test -f .git/MERGE_HEAD && echo __APM_MERGE_HEAD__ || echo __APM_NO__`, { timeoutMs: 8000 })
      const raw = (mergeHeadProbe.output ?? '').trim()
      const cleaned = raw.split('\n').map(line => line.trim()).filter(line => line && !line.startsWith('Updating files:')).join('\n').trim()
      const marker = cleaned.match(/__APM_(MERGE_HEAD|NO)__/)
      const remoteHead = marker?.[1] === 'MERGE_HEAD' ? 'MERGE_HEAD' : marker?.[1] === 'NO' ? 'NO' : cleaned || raw
      remoteMergeHead = remoteHead === 'MERGE_HEAD'
      appendLog(`[conflicts] remote_merge_head=${remoteHead}\n`)
    } catch (error) {
      appendLog(`[conflicts] remote_merge_head probe failed: ${String((error as Error)?.message ?? error)}\n`)
    }
  }

  if (mapped) {
    try {
      const size = mergeLogPath && fs.existsSync(mergeLogPath) ? fs.statSync(mergeLogPath).size : 'MISSING'
      appendLog(`[conflicts] remote_merge_conflict_size=SKIP(mapped) local_size=${String(size)}\n`)
    } catch (error) {
      appendLog(`[conflicts] remote_merge_conflict_size local probe failed: ${String((error as Error)?.message ?? error)}\n`)
    }
  } else {
    try {
      const mergeSizeProbe = await harnessExec(`cd ${remote} && test -f log/merge_conflict.log && stat -c%s log/merge_conflict.log || echo MISSING`, { timeoutMs: 8000 })
      const raw = (mergeSizeProbe.output ?? '').trim()
      const cleaned = raw.split('\n').map(line => line.trim()).filter(line => line && !line.startsWith('Updating files:'))
      appendLog(`[conflicts] remote_merge_conflict_size=${cleaned[cleaned.length - 1] ?? ''}\n`)
    } catch (error) {
      appendLog(`[conflicts] remote_merge_conflict_size probe failed: ${String((error as Error)?.message ?? error)}\n`)
    }
  }

  // #region debug-point modem-postprocess-before-list-unmerged
  appendLog(`[debug] postProcessRun before listUnmergedFiles mapped=${mapped ?? ''} remote=${remote}\n`)
  // #endregion
  const conflictFiles = localIndexLock && fs.existsSync(localIndexLock) ? ['.git/index.lock'] : await listUnmergedFiles(config)
  // #region debug-point modem-postprocess-after-list-unmerged
  appendLog(`[debug] postProcessRun after listUnmergedFiles count=${conflictFiles.length}\n`)
  // #endregion
  appendLog(`[conflicts] detected_files=${conflictFiles.length}\n`)
  const hasRealConflict = conflictFiles.length > 0 || remoteMergeHead || localStillInMerge
  let status: ModemBaselineStatus = hasRealConflict ? 'conflict' : code === 1 ? 'failed' : 'success'
  appendLog(`[conflicts] final_status=${status} exit_code=${String(code)} local_merge_head=${Number(localStillInMerge)} remote_merge_head=${Number(remoteMergeHead)}\n`)

  if (status === 'success' && current.phase === 'resume' && sanitizeBuildProjectName(config.build_project)) {
    const buildResult = await runModemBuildAfterResume(runId, config, appendLog)
    if (buildResult === 'failed') {
      const failedMeta: ModemBaselineRunMeta = {
        ...current,
        status: 'failed',
        phase: 'build',
        finishedAt: nowIso(),
        conflictFiles: undefined,
        error: 'build_failed',
      }
      appendLog('[run] phase=build status=failed summary=bld_modem_failed\n')
      writeRunMeta(failedMeta)
      broadcast(runId, 'status', { status: failedMeta.status, phase: failedMeta.phase, reportPath: failedMeta.reportPath, error: failedMeta.error })
      broadcast(runId, 'conflicts', { files: [] })
      return
    }
  }

  const nextMeta: ModemBaselineRunMeta = {
    ...current,
    status,
    phase: status === 'success' ? 'archive' : status === 'conflict' ? 'conflict' : current.phase,
    finishedAt: nowIso(),
    conflictFiles: conflictFiles.length ? conflictFiles : undefined,
    error: status === 'failed' ? current.error : undefined,
  }
  if (status === 'success') {
    const built = sanitizeBuildProjectName(config.build_project)
    appendLog(
      built && current.phase === 'resume'
        ? `[run] phase=archive status=success summary=resume_and_build_completed project=${built}\n`
        : '[run] phase=archive status=success summary=merge_commit_post_merge_completed\n',
    )
  } else if (status === 'conflict') {
    appendLog(`[run] phase=conflict status=conflict summary=manual_resolution_required files=${conflictFiles.length}\n`)
  } else {
    appendLog(`[run] phase=${nextMeta.phase} status=failed summary=post_process_failed exit_code=${String(code)}\n`)
  }
  // #region debug-point modem-postprocess-before-write-meta
  appendLog(`[debug] postProcessRun before writeRunMeta status=${nextMeta.status} phase=${nextMeta.phase}\n`)
  // #endregion
  writeRunMeta(nextMeta)
  broadcast(runId, 'status', { status: nextMeta.status, phase: nextMeta.phase, reportPath: nextMeta.reportPath, error: nextMeta.error })
  broadcast(runId, 'conflicts', { files: conflictFiles })
}

function updateReportPathFromLog(runId: string, line: string) {
  const matched = line.match(/Report(?: generated locally)?:\s*(.+)\s*$/)
  if (!matched?.[1]) return
  const current = readModemBaselineRun(runId)
  if (!current) return
  const nextMeta: ModemBaselineRunMeta = { ...current, reportPath: matched[1].trim() }
  writeRunMeta(nextMeta)
  broadcast(runId, 'status', { status: nextMeta.status, phase: nextMeta.phase, reportPath: nextMeta.reportPath, error: nextMeta.error })
}

function appendRunLog(runId: string, logPath: string, line: string) {
  const runtime = runtimeFor(runId)
  const normalized = ensureRunLogTimestamps(line, runtime.logLineOpen)
  runtime.logLineOpen = normalized.lineOpen
  fs.appendFileSync(logPath, normalized.text, 'utf-8')
  broadcast(runId, 'log', { line: normalized.text })
  updateReportPathFromLog(runId, normalized.text)
}

function markRunFailed(runId: string, error: string) {
  const current = readModemBaselineRun(runId)
  if (!current) return
  const nextMeta: ModemBaselineRunMeta = {
    ...current,
    status: 'failed',
    phase: inferPhaseFromStatus('failed', current.phase),
    finishedAt: nowIso(),
    error,
  }
  writeRunMeta(nextMeta)
  broadcast(runId, 'status', { status: nextMeta.status, phase: nextMeta.phase, reportPath: nextMeta.reportPath, error: nextMeta.error })
}

function validateConfig(input: unknown): ModemBaselineConfig | null {
  if (!input || typeof input !== 'object') return null
  const value = input as Partial<ModemBaselineConfig>
  if (!value.NODE_BRANCH || !value.target_BRANCH || !value.AP_lable || !value.JIRAID || !value.work_dir) {
    return null
  }
  return {
    NODE_BRANCH: String(value.NODE_BRANCH),
    target_BRANCH: String(value.target_BRANCH),
    AP_lable: String(value.AP_lable),
    DESCRIPTION: value.DESCRIPTION ? String(value.DESCRIPTION) : undefined,
    JIRAID: String(value.JIRAID),
    work_dir: String(value.work_dir),
    mapped_prefix: value.mapped_prefix ? String(value.mapped_prefix) : undefined,
    remote_prefix: value.remote_prefix ? String(value.remote_prefix) : undefined,
    build_project: sanitizeBuildProjectName(value.build_project),
  }
}

export function getModemBaselineDefaults() {
  const toolRoot = ensureToolRoot()
  const defaults = defaultConfigPath()
  if (!fs.existsSync(defaults)) {
    throw new Error(`默认配置不存在: ${defaults}`)
  }

  const raw = JSON.parse(fs.readFileSync(defaults, 'utf-8')) as Partial<ModemBaselineConfig>
  return {
    toolRoot,
    config: {
      NODE_BRANCH: String(raw.NODE_BRANCH ?? ''),
      target_BRANCH: String(raw.target_BRANCH ?? ''),
      AP_lable: String(raw.AP_lable ?? ''),
      DESCRIPTION: String(raw.DESCRIPTION ?? ''),
      JIRAID: String(raw.JIRAID ?? ''),
      work_dir: String(raw.work_dir ?? ''),
      mapped_prefix: String(raw.mapped_prefix ?? ''),
      remote_prefix: String(raw.remote_prefix ?? ''),
      build_project: sanitizeBuildProjectName(raw.build_project),
    } satisfies ModemBaselineConfig,
  }
}

async function startBackgroundRun(runId: string, config: ModemBaselineConfig, scriptName: string) {
  const toolRoot = ensureToolRoot()
  const logPath = runLogPath(runId)
  const scriptPath = path.resolve(toolRoot, scriptName)
  const pythonExe = process.env.PYTHON ?? 'python'
  const configPath = runConfigPath(runId)

  try {
    const bridgeReady = await checkBridgeHealthy(line => appendRunLog(runId, logPath, line))
    if (!bridgeReady) {
      markRunFailed(runId, 'bridge_not_ready')
      return
    }
    const current = readModemBaselineRun(runId)
    const nextPhase = current?.phase === 'resume' ? 'resume' : 'merge'
    updateRunMeta(runId, { status: 'running', phase: nextPhase })
  } catch {
    markRunFailed(runId, 'bridge_not_ready')
    return
  }

  // #region debug-point modem-python-spawn
  appendRunLog(runId, logPath, `[debug] startBackgroundRun spawn script=${scriptName} python=${pythonExe} scriptPath=${scriptPath} configPath=${configPath}\n`)
  // #endregion
  const processRef = spawn(pythonExe, ['-u', scriptPath, configPath], {
    cwd: toolRoot,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1', PYTHONIOENCODING: 'utf-8', SKIP_BRIDGE_CHECK: 'true' },
    windowsHide: true,
  })
  // #region debug-point modem-python-spawned
  appendRunLog(runId, logPath, `[debug] startBackgroundRun spawned pid=${String(processRef.pid ?? '')} script=${scriptName}\n`)
  // #endregion

  processRef.on('error', (error) => {
    appendRunLog(runId, logPath, `[spawn] failed: ${String((error as Error)?.message ?? error)}\n`)
    markRunFailed(runId, 'spawn_failed')
  })
  processRef.stdout.on('data', chunk => appendRunLog(runId, logPath, chunk.toString()))
  processRef.stderr.on('data', chunk => appendRunLog(runId, logPath, chunk.toString()))
  processRef.on('close', async (code) => {
    // #region debug-point modem-python-close
    appendRunLog(runId, logPath, `[debug] startBackgroundRun close pid=${String(processRef.pid ?? '')} code=${String(code)} script=${scriptName}\n`)
    // #endregion
    await postProcessRun(runId, config, code, line => appendRunLog(runId, logPath, line))
  })
}

export function createModemBaselineRun(input: unknown) {
  ensureToolRoot()
  ensureDataDirs()
  const validated = validateConfig(input)
  if (!validated) {
    throw new Error('invalid_config')
  }

  const runId = createRunId()
  ensureRunDirs(runId)
  const logPath = runLogPath(runId)
  const remoteWorkDir = computeRemoteWorkDir(validated)
  const meta: ModemBaselineRunMeta = {
    runId,
    status: 'running',
    mode: 'stop_after_merge',
    phase: 'precheck',
    createdAt: nowIso(),
    startedAt: nowIso(),
    config: validated,
    remoteWorkDir,
    logPath,
  }

  fs.writeFileSync(runConfigPath(runId), JSON.stringify(validated, null, 2), 'utf-8')
  fs.writeFileSync(logPath, '', 'utf-8')
  writeRunMeta(meta)
  void startBackgroundRun(runId, validated, 'debug_stop_after_merge.py')

  return { runId, status: meta.status }
}

export function continueModemBaselineRun(runId: string, input?: { build_project?: string }) {
  ensureToolRoot()
  const meta = readModemBaselineRun(runId)
  if (!meta) throw new Error('not_found')
  if (meta.status === 'running') throw new Error('running')
  if (meta.status !== 'conflict') throw new Error('not_in_conflict')
  if (!meta.logPath) throw new Error('missing_log_path')

  const buildProject = sanitizeBuildProjectName(input?.build_project ?? meta.config.build_project)
  const nextConfig: ModemBaselineConfig = {
    ...meta.config,
    build_project: buildProject,
  }
  fs.writeFileSync(runConfigPath(runId), JSON.stringify(nextConfig, null, 2), 'utf-8')

  const nextMeta: ModemBaselineRunMeta = {
    ...meta,
    status: 'running',
    phase: 'resume',
    finishedAt: undefined,
    conflictFiles: undefined,
    error: undefined,
    config: nextConfig,
  }
  writeRunMeta(nextMeta)
  broadcast(runId, 'status', { status: nextMeta.status, phase: nextMeta.phase, reportPath: nextMeta.reportPath, error: nextMeta.error })
  appendRunLog(
    runId,
    meta.logPath,
    buildProject
      ? `[continue] requested build_project=${buildProject}\n`
      : '[continue] requested (no build_project; auto build will be skipped)\n',
  )
  void startBackgroundRun(runId, nextConfig, 'debug_continue_after_merge.py')
  return { runId, status: nextMeta.status }
}

export async function refreshModemBaselineConflicts(runId: string, autoStageResolved = true) {
  const meta = readModemBaselineRun(runId)
  if (!meta) throw new Error('not_found')
  const appendLog = (line: string) => {
    if (!meta.logPath) return
    appendRunLog(runId, meta.logPath, line)
  }

  appendLog(`[refresh] requested autoStage=${Number(autoStageResolved)}\n`)
  let staged = 0
  let filesBefore: string[] = []
  let filesAfter: string[] = []

  try {
    filesBefore = await listUnmergedFiles(meta.config)
    appendLog(`[refresh] before=${filesBefore.length}\n`)
  } catch (error) {
    appendLog(`[refresh] list before failed: ${String((error as Error)?.message ?? error)}\n`)
  }

  if (autoStageResolved && filesBefore.length) {
    const remote = computeRemoteWorkDir(meta.config)
    const mapped = computeMappedWorkDir(meta.config)
    let batchHandled = false

    if (mapped) {
      try {
        const gitDir = path.win32.resolve(mapped, '.git')
        const scriptPath = path.win32.resolve(gitDir, 'apm_refresh_conflicts.sh')
        const script = `#!/bin/bash
set +e
staged=0
unmerged="$(GIT_PAGER=cat git diff --name-only --diff-filter=U 2>/dev/null || true)"
if [ -n "$unmerged" ]; then
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    if GIT_PAGER=cat git grep -n -E '^(<<<<<<<|=======|>>>>>>>)' -- "$f" >/dev/null 2>&1; then
      echo "__APM_MARKER__:$f"
    else
      if git add -- "$f" >/dev/null 2>&1; then
        staged=$((staged+1))
        echo "__APM_STAGED__:$f"
      else
        echo "__APM_ADD_FAIL__:$f"
      fi
    fi
  done <<< "$unmerged"
fi
echo "__APM_STAGED_COUNT__:$staged"
echo "__APM_REMAINING_BEGIN__"
GIT_PAGER=cat git diff --name-only --diff-filter=U 2>/dev/null || true
echo "__APM_REMAINING_END__"
`
        fs.writeFileSync(scriptPath, script.replace(/\r\n/g, '\n'), 'utf-8')
        const result = await harnessExec(`cd ${remote} && bash .git/apm_refresh_conflicts.sh`, { timeoutMs: 120000 })
        const raw = (result.output ?? '').trim()
        appendLog(`[refresh] batch status=${result.status} exit_code=${result.exit_code}\n`)
        const matched = raw.match(/__APM_STAGED_COUNT__:(\d+)/)
        staged = matched ? Number(matched[1]) : 0
        for (const line of raw.split('\n').map(item => item.trim()).filter(Boolean)) {
          if (line.startsWith('__APM_MARKER__:')) appendLog(`[refresh] marker remains: ${line.slice('__APM_MARKER__:'.length)}\n`)
          if (line.startsWith('__APM_ADD_FAIL__:')) appendLog(`[refresh] git add failed: ${line.slice('__APM_ADD_FAIL__:'.length)}\n`)
        }
        batchHandled = true
      } catch (error) {
        appendLog(`[refresh] batch failed: ${String((error as Error)?.message ?? error)}\n`)
      }
    }

    if (!batchHandled) {
      const quote = (value: string) => `'${String(value).replace(/'/g, `'\"'\"'`)}'`
      for (const file of filesBefore) {
        try {
          const probe = await harnessExec(
            `cd ${remote} && set +e; GIT_PAGER=cat git grep -n -E '^(<<<<<<<|=======|>>>>>>>)' -- ${quote(file)} >/dev/null 2>&1; rc=$?; echo __APM_RC:\${rc}__`,
            { timeoutMs: 45000 },
          )
          const match = (probe.output ?? '').trim().match(/__APM_RC:(\d+)__/)
          const rc = match ? Number(match[1]) : null
          if (rc === 1) {
            const add = await harnessExec(`cd ${remote} && git add -- ${quote(file)}`, { timeoutMs: 45000 })
            if (add.status === 'ok' && add.exit_code === 0) staged += 1
          }
        } catch (error) {
          appendLog(`[refresh] stage failed: ${file} err=${String((error as Error)?.message ?? error)}\n`)
        }
      }
    }
  }

  try {
    filesAfter = await listUnmergedFiles(meta.config)
    appendLog(`[refresh] staged=${staged} remaining=${filesAfter.length}\n`)
  } catch (error) {
    appendLog(`[refresh] list after failed: ${String((error as Error)?.message ?? error)}\n`)
    filesAfter = filesBefore
  }

  const nextMeta: ModemBaselineRunMeta = {
    ...meta,
    conflictFiles: filesAfter.length ? filesAfter : undefined,
    phase: 'conflict',
    // Refresh only reconciles the conflict list. It must not auto-advance
    // the run state, otherwise manual "continue" becomes impossible.
    status: meta.status === 'conflict' ? 'conflict' : meta.status,
  }
  writeRunMeta(nextMeta)
  broadcast(runId, 'conflicts', { files: filesAfter })
  broadcast(runId, 'status', { status: nextMeta.status, phase: nextMeta.phase, reportPath: nextMeta.reportPath, error: nextMeta.error })
  return { files: filesAfter, staged }
}

export function openModemBaselineConflictFile(runId: string, relativeFile: string) {
  const meta = readModemBaselineRun(runId)
  if (!meta) throw new Error('not_found')
  const file = String(relativeFile ?? '').trim()
  if (!file) throw new Error('bad_request')

  const mapped = computeMappedWorkDir(meta.config)
  if (!mapped) throw new Error('mapped_not_available')

  const fullPath = path.win32.resolve(mapped, file.replace(/\//g, '\\'))
  const relative = path.win32.relative(mapped, fullPath)
  if (!relative || relative.startsWith('..') || path.win32.isAbsolute(relative)) {
    throw new Error('path_outside_workdir')
  }
  if (!fs.existsSync(fullPath)) {
    throw new Error('file_not_found')
  }

  const powershellPath = process.platform === 'win32' ? 'powershell.exe' : 'powershell'
  const quoted = `'${fullPath.replace(/'/g, "''")}'`
  const result = spawnSync(
    powershellPath,
    ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', `Invoke-Item -LiteralPath ${quoted}`],
    { windowsHide: true, timeout: 5000, encoding: 'utf-8' },
  )

  if (result.error) {
    throw new Error(`spawn_failed:${String(result.error.message ?? result.error)}`)
  }
  if (typeof result.status === 'number' && result.status !== 0) {
    throw new Error(`open_failed:${(result.stderr || '').trim()}`)
  }

  return { success: true }
}
