import { existsSync, mkdirSync } from 'fs'
import { join } from 'path'
import { safeFileStore } from '../../safe-file-store'
import { tahpPaths } from '../paths'
import {
  ADAPT_LAYOUT_SCHEMA_VERSION,
  type AdaptDomainLayoutRecord,
  type AdaptLayoutManifest,
} from './types'

const LAYOUT_DIR = () => join(tahpPaths.projectRoot, '.adapt-config', 'domain-layouts')
const MANIFEST_PATH = () => join(LAYOUT_DIR(), 'manifest.json')

function emptyManifest(cloudSyncEnabled: boolean): AdaptLayoutManifest {
  return {
    schema_version: ADAPT_LAYOUT_SCHEMA_VERSION,
    layouts: {},
    sync: {
      cloud_sync_enabled: cloudSyncEnabled,
    },
  }
}

export function getAdaptLayoutManifestPath(): string {
  return MANIFEST_PATH()
}

export async function readLocalLayoutManifest(): Promise<AdaptLayoutManifest> {
  try {
    const raw = await safeFileStore.readText(MANIFEST_PATH())
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

export async function writeLocalLayoutManifest(manifest: AdaptLayoutManifest): Promise<void> {
  const dir = LAYOUT_DIR()
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true })
  await safeFileStore.writeText(
    MANIFEST_PATH(),
    JSON.stringify(manifest, null, 2),
    { backup: true },
  )
}

export async function upsertLocalDomainLayout(
  record: AdaptDomainLayoutRecord,
  cloudSyncEnabled: boolean,
): Promise<AdaptLayoutManifest> {
  const manifest = await readLocalLayoutManifest()
  manifest.layouts[record.domain_id] = record
  manifest.sync.last_local_save = new Date().toISOString()
  manifest.sync.cloud_sync_enabled = cloudSyncEnabled
  await writeLocalLayoutManifest(manifest)
  return manifest
}

export async function deleteLocalDomainLayout(domainId: string): Promise<AdaptLayoutManifest> {
  const manifest = await readLocalLayoutManifest()
  delete manifest.layouts[domainId]
  manifest.sync.last_local_save = new Date().toISOString()
  await writeLocalLayoutManifest(manifest)
  return manifest
}
