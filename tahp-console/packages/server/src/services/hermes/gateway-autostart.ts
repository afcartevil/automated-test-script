/**
 * gateway-autostart stub — Gateway Manager removed from TAHP.
 * TAHP uses direct LLM upstream (env vars) instead of a local gateway process.
 */

export type GatewayRuntimeStatus = {
  running: boolean
  profile: string
  pid?: number
  port?: number
  error?: string
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function ensureProfileGatewaysRunning(): Promise<void> {
  // no-op: TAHP does not manage local Hermes gateway processes
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function getGatewayRuntimeStatusForProfile(profile: string): Promise<GatewayRuntimeStatus> {
  return { running: false, profile }
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function restartGatewayForProfile(profile: string): Promise<GatewayRuntimeStatus> {
  return { running: false, profile, error: 'Gateway management is disabled in TAHP. Use TAHP_LLM_UPSTREAM env var instead.' }
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function isGatewayRunningForProfile(_hermesBin: string, _profileDir: string): Promise<boolean> {
  return Promise.resolve(false)
}
