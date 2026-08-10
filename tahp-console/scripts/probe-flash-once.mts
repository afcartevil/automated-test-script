/**
 * 仅探测烧录能力，不启动刷机。
 *   npx tsx scripts/probe-flash-once.mts
 */
import { existsSync } from 'fs'
import { execFileSync } from 'child_process'
import { probeHarnessFlash } from '../packages/server/src/services/tahp/adapt-pipeline/harness-flash-capability'
import { defaultFlashSkillId } from '../packages/server/src/services/tahp/adapt-pipeline/harness-skill-registry'
import { classifyFlashArtifacts } from '../packages/server/src/services/tahp/adapt-pipeline/flash-artifact-classify'
import { validateFlashPkgPath } from '../packages/server/src/services/tahp/flash-artifact-resolver'

const pkg = process.env.FLASH_PKG_PATH || 'Z:\\ea-build\\output_version_lj9_h972'
const skillId = defaultFlashSkillId()

async function main() {
  const classified = classifyFlashArtifacts({ pkgPath: pkg })
  const validation = validateFlashPkgPath(classified.pkgPath || pkg)

  let harness: { available: boolean; reason?: string }
  try {
    harness = await probeHarnessFlash(skillId)
  } catch (e) {
    harness = { available: false, reason: String(e) }
  }

  let deviceUpdate: { available: boolean; exe?: string; error?: string } = { available: false }
  try {
    const { resolveDeviceUpdateExe } = await import('../packages/server/src/services/tahp/device-flash')
    const exe = resolveDeviceUpdateExe()
    deviceUpdate = { available: existsSync(exe), exe }
  } catch (e) {
    deviceUpdate = { available: false, error: String(e) }
  }

  let adb: { ok: boolean; devices?: string[]; error?: string } = { ok: false }
  try {
    const out = execFileSync('adb', ['devices'], { encoding: 'utf-8', timeout: 10_000, windowsHide: true })
    const devices = out
      .split(/\r?\n/)
      .slice(1)
      .map(l => l.trim())
      .filter(l => l && !l.startsWith('*'))
      .map(l => l.split(/\s+/)[0])
      .filter(Boolean)
    adb = { ok: true, devices }
  } catch (e) {
    adb = { ok: false, error: String(e).slice(0, 300) }
  }

  const canStandalone =
    validation.valid
    && classified.kind === 'full_rom'
    && (harness.available || deviceUpdate.available)
    && Boolean(adb.devices?.length)

  console.log(JSON.stringify({
    pkg,
    skillId,
    classified,
    validation,
    harness,
    deviceUpdate,
    adb,
    has_run_flash_once_script: false,
    can_invoke_apis: true,
    would_need_device_id: true,
    can_run_standalone_now: canStandalone,
    blockers: [
      !validation.valid ? `pkg invalid: ${validation.reason}` : null,
      classified.kind !== 'full_rom' ? `not full_rom: ${classified.kind}` : null,
      !harness.available && !deviceUpdate.available ? 'no flash backend (harness & device_update)' : null,
      !adb.devices?.length ? 'no adb device' : null,
    ].filter(Boolean),
  }, null, 2))
}

main().catch(err => {
  console.error(err)
  process.exit(1)
})
