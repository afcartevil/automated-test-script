import { existsSync, mkdirSync } from 'fs'
import { join } from 'path'
import { safeFileStore } from '../../safe-file-store'
import { tahpPaths } from '../paths'
import {
  ADAPT_LAYOUT_SCHEMA_VERSION,
  DEFAULT_ADAPT_WORKSPACE,
  isAdaptWorkspaceId,
  type AdaptDomainLayoutRecord,
  type AdaptLayoutManifest,
} from './types'

const LAYOUT_ROOT = () => join(tahpPaths.projectRoot, '.adapt-config', 'domain-layouts')
const LEGACY_MANIFEST_PATH = () => join(LAYOUT_ROOT(), 'manifest.json')

function layoutDir(workspaceId: string): string {
  return join(LAYOUT_ROOT(), workspaceId)
}

function manifestPath(workspaceId: string): string {
  return join(layoutDir(workspaceId), 'manifest.json')
}

function normalizeWorkspaceId(workspaceId?: string): string {
  const id = String(workspaceId || DEFAULT_ADAPT_WORKSPACE).trim()
  if (!isAdaptWorkspaceId(id)) {
    throw new Error(`无效的工作区 ID: ${id}`)
  }
  return id
}

function emptyManifest(cloudSyncEnabled: boolean): AdaptLayoutManifest {
  return {
    schema_version: ADAPT_LAYOUT_SCHEMA_VERSION,
    layouts: {},
    sync: {
      cloud_sync_enabled: cloudSyncEnabled,
    },
  }
}

export function getAdaptLayoutManifestPath(workspaceId?: string): string {
  return manifestPath(normalizeWorkspaceId(workspaceId))
}

async function migrateLegacyManifestIfNeeded(workspaceId: string): Promise<void> {
  if (workspaceId !== DEFAULT_ADAPT_WORKSPACE) return
  const target = manifestPath(workspaceId)
  if (existsSync(target)) return
  const legacy = LEGACY_MANIFEST_PATH()
  if (!existsSync(legacy)) return
  const raw = await safeFileStore.readText(legacy)
  const dir = layoutDir(workspaceId)
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  await safeFileStore.writeText(target, raw, { backup: true })
}

export async function readLocalLayoutManifest(workspaceId?: string): Promise<AdaptLayoutManifest> {
  const ws = normalizeWorkspaceId(workspaceId)
  await migrateLegacyManifestIfNeeded(ws)
  const path = manifestPath(ws)
  try {
    const raw = await safeFileStore.readText(path)
    const parsed = JSON.parse(raw) as AdaptLayoutManifest
    if (!parsed.layouts || typeof parsed.layouts !== 'object') {
      return emptyManifest(false)
    }
    return {
      schema_version: parsed.schema_version ?? ADAPT_LAYOUT_SCHEMA_VERSION,
      layouts: parsed.layouts,
      sync: {
        cloud_sync_enabled: !!parsed.sync?.cloud_sync_enabled,
        last_local_save: parsed.sync?.last_local_save,
        last_cloud_pull: parsed.sync?.last_cloud_pull,
        last_cloud_push: parsed.sync?.last_cloud_push,
        cloud_revision: parsed.sync?.cloud_revision,
      },
    }
  } catch (err: unknown) {
    const code = (err as NodeJS.ErrnoException)?.code
    if (code === 'ENOENT') return emptyManifest(false)
    throw err
  }
}

export async function writeLocalLayoutManifest(
  manifest: AdaptLayoutManifest,
  workspaceId?: string,
): Promise<void> {
  const ws = normalizeWorkspaceId(workspaceId)
  const dir = layoutDir(ws)
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  await safeFileStore.writeText(
    manifestPath(ws),
    JSON.stringify(manifest, null, 2),
    { backup: true },
  )
}

export async function upsertLocalDomainLayout(
  record: AdaptDomainLayoutRecord,
  cloudSyncEnabled: boolean,
  workspaceId?: string,
): Promise<AdaptLayoutManifest> {
  const manifest = await readLocalLayoutManifest(workspaceId)
  manifest.layouts[record.domain_id] = record
  manifest.sync.last_local_save = new Date().toISOString()
  manifest.sync.cloud_sync_enabled = cloudSyncEnabled
  await writeLocalLayoutManifest(manifest, workspaceId)
  return manifest
}

export async function deleteLocalDomainLayout(
  domainId: string,
  workspaceId?: string,
): Promise<AdaptLayoutManifest> {
  const manifest = await readLocalLayoutManifest(workspaceId)
  delete manifest.layouts[domainId]
  manifest.sync.last_local_save = new Date().toISOString()
  await writeLocalLayoutManifest(manifest, workspaceId)
  return manifest
}
