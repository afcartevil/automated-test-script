/**
 * 单独跑 device_update 整包刷机（不经流水线 UI）
 *
 * Usage:
 *   npx tsx scripts/run-flash-once.mts
 */
process.env.TAHP_PROJECT_ROOT ||= 'D:\\code\\EA\\easyadapter'

const deviceId = process.env.FLASH_DEVICE_ID || '144512559G106720'
const pkgPath = process.env.FLASH_PKG_PATH || 'Z:\\ea-build\\output_version_lj9_h972'

const { runDeviceFlash, waitForAdbDevice } = await import(
  '../packages/server/src/services/tahp/device-flash.ts'
)

console.log('[flash-once] start', { deviceId, pkgPath })

const result = await runDeviceFlash([deviceId], { pkgPath }, (line) => {
  console.log('[log]', line)
})

console.log('[flash-once] result', {
  success: result.success,
  returnCode: result.returnCode,
})

if (result.success) {
  console.log('[flash-once] waiting device reboot…')
  try {
    await waitForAdbDevice(deviceId, 180_000)
    console.log('[flash-once] device ready')
  } catch (err) {
    console.warn('[flash-once] reboot wait:', (err as Error).message)
  }
}

process.exit(result.success ? 0 : 1)
