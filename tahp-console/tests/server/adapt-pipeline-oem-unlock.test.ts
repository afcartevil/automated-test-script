import { readFileSync } from 'fs'
import { describe, expect, it } from 'vitest'
import {
  parseBuildKind,
  parseFlashLocked,
  resolveOemUnlockScriptPath,
  resolveOemWizardGate,
} from '../../packages/server/src/services/tahp/adapt-pipeline/oem-unlock-product'

describe('oem unlock product helpers', () => {
  it('parses ro.boot.flash.locked', () => {
    expect(parseFlashLocked('0')).toBe('unlocked')
    expect(parseFlashLocked('1')).toBe('locked')
    expect(parseFlashLocked('')).toBe('unknown')
    expect(parseFlashLocked(' 1\n')).toBe('locked')
  })

  it('parses ro.build.type', () => {
    expect(parseBuildKind('user')).toBe('user')
    expect(parseBuildKind('userdebug')).toBe('userdebug')
    expect(parseBuildKind('userroot')).toBe('userroot')
    expect(parseBuildKind('user_root')).toBe('userroot')
    expect(parseBuildKind('eng')).toBe('userdebug')
    expect(parseBuildKind('')).toBe('unknown')
  })

  it('gates wizard by lock + build type', () => {
    expect(resolveOemWizardGate('unlocked', 'user')).toBe('unlocked')
    expect(resolveOemWizardGate('locked', 'user')).toBe('block_user')
    expect(resolveOemWizardGate('locked', 'userdebug')).toBe('offer_auto_unlock')
    expect(resolveOemWizardGate('locked', 'userroot')).toBe('offer_auto_unlock')
    expect(resolveOemWizardGate('locked', 'unknown')).toBe('unknown')
  })

  it('ships oem-unlock-product.bat with serial-scoped adb/fastboot', () => {
    const bat = readFileSync(resolveOemUnlockScriptPath(), 'utf8')
    expect(bat).toContain('adb -s "%SERIAL%" root')
    expect(bat).toContain('service call oem_lock 4 i32 1')
    expect(bat).toContain('fastboot -s "%SERIAL%" flashing unlock')
    expect(bat).toContain('fastboot -s "%SERIAL%" erase userdata')
    expect(bat.toLowerCase()).not.toContain('pause')
  })
})
