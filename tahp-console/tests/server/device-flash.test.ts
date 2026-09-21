import { describe, it, expect } from 'vitest'
import { mkdirSync, writeFileSync, rmSync, readdirSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import {
  normalizePath,
  isZipFile,
  isNetworkPath,
  buildFlashCommand,
  buildReleaseBranchFolder,
  buildSkipOobeAdbArgs,
  normalizeSystemVersionLabel,
  pickLatestSystemVersion,
  resolveUserRootPkgPath,
  clearFlashPackageCache,
  MARKET_VERSIONS,
  type DailySystemVersionOption,
} from '../../packages/server/src/services/tahp/device-flash'

describe('device-flash helpers', () => {
  it('normalizes UNC paths', () => {
    expect(normalizePath('//10.150.98.24/share/rom.zip')).toBe(
      '\\\\10.150.98.24\\share\\rom.zip'
    )
  })

  it('detects zip and network paths', () => {
    expect(isZipFile('D:\\rom\\build.zip')).toBe(true)
    expect(isNetworkPath('\\\\server\\rom.zip')).toBe(true)
  })

  it('builds device_update command', () => {
    const cmd = buildFlashCommand(['ABC123'], 'D:\\pkg\\scatter.xml', {
      stageVersion: 'Open',
      customMarket: true,
      skipUnzip: true,
    })
    expect(cmd).toContain('ABC123')
    expect(cmd).toContain('-stage')
    expect(cmd).toContain('Open')
  })

  it('exports market version options', () => {
    expect(MARKET_VERSIONS.some((m) => m.value === 'India')).toBe(true)
  })

  it('maps system version to mtk release branch folder', () => {
    expect(buildReleaseBranchFolder('tOS16.2')).toBe('tOS16.2.0_mtk_sys_release')
    expect(buildReleaseBranchFolder('16.3')).toBe('tOS16.3.0_mtk_sys_release')
    expect(normalizeSystemVersionLabel('tOS16.3.0_mtk_sys_release')).toBe('tOS16.3')
  })

  it('picks the newest tOS system version', () => {
    const versions: DailySystemVersionOption[] = [
      { label: 'tOS16.2', value: 'tOS16.2', branchFolder: 'tOS16.2.0_mtk_sys_release' },
      { label: 'tOS17.0', value: 'tOS17.0', branchFolder: 'tOS17.0.0_mtk_sys_release' },
      { label: 'tOS16.3', value: 'tOS16.3', branchFolder: 'tOS16.3.0_mtk_sys_release' },
    ]
    expect(pickLatestSystemVersion(versions)).toBe('tOS17.0')
  })

  it('resolves user_root package from flash package directory', () => {
    const base = join(tmpdir(), `tahp-flash-root-${Date.now()}`)
    mkdirSync(base, { recursive: true })
    try {
      const mainZip = join(base, '2026.06.29.12.00.00_100_CM5_v1000.zip')
      const rootZip = join(base, '2026.06.29.12.00.00_100_CM5_v1000_user_root.zip')
      writeFileSync(mainZip, 'main')
      writeFileSync(rootZip, 'root')

      expect(resolveUserRootPkgPath(mainZip)).toBe(rootZip)
      expect(resolveUserRootPkgPath(base)).toBe(rootZip)
    } finally {
      rmSync(base, { recursive: true, force: true })
    }
  })

  it('builds SkipOOBE adb commands for a known serial', () => {
    expect(buildSkipOobeAdbArgs('ABC123')).toEqual([
      ['-s', 'ABC123', 'root'],
      ['-s', 'ABC123', 'wait-for-device'],
      ['-s', 'ABC123', 'shell', 'settings', 'put', 'secure', 'user_setup_complete', '1'],
      ['-s', 'ABC123', 'shell', 'settings', 'put', 'global', 'device_provisioned', '1'],
      ['-s', 'ABC123', 'shell', 'settings', 'put', 'system', 'show_inadvertent', '0'],
      ['-s', 'ABC123', 'shell', 'input', 'keyevent', '3'],
      ['-s', 'ABC123', 'shell', 'input', 'keyevent', '3'],
      ['-s', 'ABC123', 'shell', 'input', 'keyevent', '3'],
    ])
  })

  it('clears flash package cache directory contents', () => {
    const base = join(tmpdir(), `tahp-flash-clear-${Date.now()}`)
    mkdirSync(base, { recursive: true })
    const prev = process.env.TAHP_FLASH_PACKAGE_DIR
    process.env.TAHP_FLASH_PACKAGE_DIR = base
    try {
      writeFileSync(join(base, 'cached.zip'), 'zip-bytes')
      mkdirSync(join(base, '_downloads'), { recursive: true })
      writeFileSync(join(base, '_downloads', 'daily.zip'), 'daily')

      const result = clearFlashPackageCache()
      expect(result.flashPackageDir).toBe(base)
      expect(result.removedEntries).toBe(2)
      expect(result.freedBytes).toBeGreaterThan(0)
      expect(readdirSync(base)).toHaveLength(0)
    } finally {
      if (prev === undefined) delete process.env.TAHP_FLASH_PACKAGE_DIR
      else process.env.TAHP_FLASH_PACKAGE_DIR = prev
      rmSync(base, { recursive: true, force: true })
    }
  })
})
