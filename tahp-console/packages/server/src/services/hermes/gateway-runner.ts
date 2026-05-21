import { spawn } from 'child_process'
import { getActiveProfileDir } from './hermes-profile'

export function startGatewayRunManaged(
  hermesBin: string,
  opts: { profileDir?: string } = {},
): { pid: number | null; reused: boolean } {
  const profileDir = opts.profileDir || getActiveProfileDir()
  const child = spawn(hermesBin, ['gateway', 'run', '--replace'], {
    detached: true,
    stdio: 'ignore',
    windowsHide: true,
    env: {
      ...process.env,
      HERMES_HOME: profileDir,
    },
  })
  // Silently swallow ENOENT — hermes CLI is not required for tahp-console operation
  child.on('error', () => {})
  child.unref()

  const pid = child.pid ?? null
  return { pid, reused: false }
}
