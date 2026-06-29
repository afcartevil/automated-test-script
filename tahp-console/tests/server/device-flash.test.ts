import { describe, it, expect } from 'vitest'
import {
  normalizePath,
  isZipFile,
  isNetworkPath,
  buildFlashCommand,
  buildReleaseBranchFolder,
  normalizeSystemVersionLabel,
  pickLatestSystemVersion,
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
})
