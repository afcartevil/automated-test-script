import { describe, it, expect } from 'vitest'
import {
  normalizePath,
  isZipFile,
  isNetworkPath,
  buildFlashCommand,
  MARKET_VERSIONS,
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
})
