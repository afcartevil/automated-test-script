import { tahpGet, tahpPost } from './client'

export interface GkiPatchStatus {
  toolRoot: string
  dataDir: string
  port: number
  appUrl: string
  appBaseUrl: string
  dbPath: string
  seedDbPath: string
  running: boolean
  frontendBuilt: boolean
  settingsPath: string
  integrated?: boolean
  autoStart?: boolean
}

export function fetchGkiPatchStatus() {
  return tahpGet<GkiPatchStatus>('/api/tahp/gki-patch/status')
}

export function startGkiPatchServer() {
  return tahpPost<GkiPatchStatus>('/api/tahp/gki-patch/start')
}
