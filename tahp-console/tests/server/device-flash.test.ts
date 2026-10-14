import { describe, it, expect } from 'vitest'
import { mkdirSync, writeFileSync, readFileSync, existsSync, rmSync, readdirSync, utimesSync } from 'fs'
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
  parseAndroidVersionFromDevProjectName,
  findLatestTcardPackageInOpenPath,
  findLatestTcardPackageInTestRoot,
  findDailyTrunkBranchName,
  matchProjectFolder,
  resolveUserRootPkgPath,
  clearFlashPackageCache,
  MARKET_VERSIONS,
  type DailySystemVersionOption,
} from '../../packages/server/src/services/tahp/device-flash'
import { applyStoredOtaAccount, assertOtaBatteryLevel, findLatestUdZip, isOemUnlocked, needsUdFlash, parseBatteryLevel, parseUsbdebugFlag, readOtaAccountStore, readProjectSwdConfig, swdProjectConfigPath, writeOtaAccountStore } from '../../packages/server/src/services/tahp/ota-pretest'

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

  it('parses Android version from sw_ver_sh DEV project folders', () => {
    expect(parseAndroidVersionFromDevProjectName('X6850_Android_16_user')).toBe(16)
    expect(parseAndroidVersionFromDevProjectName('project-Android17-release')).toBe(17)
    expect(parseAndroidVersionFromDevProjectName('legacy_project')).toBeNull()
  })

  it('recognizes Android trunk when no release branch exists', () => {
    expect(findDailyTrunkBranchName(['tOS_mtk_A17_trunk'], 17)).toBe('tOS_mtk_A17_trunk')
    expect(findDailyTrunkBranchName(['tOS_mtk_A16_trunk'], 17)).toBeNull()
  })

  it('keeps the generic project name for sw_ver_sh and Chongqing CI daily paths', () => {
    expect(matchProjectFolder(
      ['X6879', 'X6879-H785', 'X6876-H786'],
      ['X6879'],
    )).toBe('X6879')
    expect(matchProjectFolder(
      ['X6876', 'X6876-H786'],
      ['X6876-H786', 'X6876'],
    )).toBe('X6876-H786')
  })

  it('finds T-card package in latest daily Open directory', () => {
    const base = join(tmpdir(), `tahp-daily-tcard-${Date.now()}`)
    mkdirSync(base, { recursive: true })
    try {
      writeFileSync(join(base, 'X6850-16.3.0.145.zip'), 'full')
      const tcard = join(base, 'Tcard_X6850-16.3.0.145_a15.zip')
      writeFileSync(tcard, 'tcard')
      expect(findLatestTcardPackageInOpenPath(base)).toBe(tcard)
    } finally {
      rmSync(base, { recursive: true, force: true })
    }
  })

  it('prefers Tcard *_a15.zip when upgrading from Android 15, ignoring incremental packages', () => {
    const base = join(tmpdir(), `tahp-daily-tcard-a15-${Date.now()}`)
    mkdirSync(base, { recursive: true })
    try {
      const incremental = join(base, 'X6885-16.3.0.140SP17-OP007PF001AZ-16.3.0.145SP08-OP004PF001AZ_20260826235808.zip')
      const a15 = join(base, 'Tcard_X6885-16.3.0.145SP08-OP004PF001AZ_a15.zip')
      const plain = join(base, 'Tcard_X6885-16.3.0.145SP08-OP004PF001AZ.zip')
      writeFileSync(incremental, 'delta')
      writeFileSync(a15, 'a15')
      writeFileSync(plain, 'tcard')
      expect(findLatestTcardPackageInOpenPath(base, 15)).toBe(a15)
    } finally {
      rmSync(base, { recursive: true, force: true })
    }
  })

  it('does not use unsuffixed Tcard_ zip when upgrading from Android 15', () => {
    const base = join(tmpdir(), `tahp-daily-tcard-no-a15-${Date.now()}`)
    mkdirSync(base, { recursive: true })
    try {
      writeFileSync(join(base, 'Tcard_X6885-16.3.0.145SP08-OP004PF001AZ.zip'), 'tcard')
      expect(() => findLatestTcardPackageInOpenPath(base, 15)).toThrow(/未找到 T卡升级包/)
    } finally {
      rmSync(base, { recursive: true, force: true })
    }
  })

  it('falls back to newest TEST version that contains a usable T-card package', () => {
    const base = join(tmpdir(), `tahp-test-tcard-${Date.now()}`)
    const noTcardOpen = join(base, 'tOS16.3.0.156[2026.09.21.01.00.00_1_user]', 'Open')
    const olderOpen = join(base, 'tOS16.3.0.155SP08[2026.09.16.22.08.09_2_user]', 'Open')
    const latestOpen = join(base, 'tOS16.3.0.155SP08[2026.09.20.18.56.27_3_user]', 'Open')
    mkdirSync(noTcardOpen, { recursive: true })
    mkdirSync(olderOpen, { recursive: true })
    mkdirSync(latestOpen, { recursive: true })
    try {
      writeFileSync(join(noTcardOpen, 'CM5-16.3.0.156.zip'), 'full')
      writeFileSync(join(olderOpen, 'Tcard_CM5-16.3.0.155SP08-OP004PF001AZ.zip'), 'tcard')
      const expected = join(latestOpen, 'Tcard_CM5-16.3.0.155SP08-OP005PF001AZ_a15.zip')
      writeFileSync(expected, 'tcard')
      writeFileSync(join(latestOpen, 'Tcard_CM5-16.3.0.155SP08-OP005PF001AZ_user_root_a15.zip'), 'root')

      expect(findLatestTcardPackageInTestRoot(base, 16)).toEqual({
        openPath: latestOpen,
        tcardPackagePath: expected,
      })
    } finally {
      rmSync(base, { recursive: true, force: true })
    }
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

  it('flashes UD only when adb root cannot succeed', () => {
    expect(needsUdFlash('adbd cannot run as root in production builds')).toBe(true)
    expect(needsUdFlash('adbd is already running as root')).toBe(false)
    expect(needsUdFlash('restarting adbd as root')).toBe(false)
    expect(needsUdFlash('设备已root')).toBe(false)
    expect(() => needsUdFlash('')).toThrow(/无法根据 adb root/)
  })

  it('rejects continuous OTA when battery is below 30 percent', () => {
    expect(parseBatteryLevel('  level: 30')).toBe(30)
    expect(parseBatteryLevel('  level: 29\n')).toBe(29)
    expect(parseBatteryLevel('scale: 100')).toBeNull()
    expect(() => assertOtaBatteryLevel(29)).toThrow(/低于 30%/)
    expect(() => assertOtaBatteryLevel(30)).not.toThrow()
  })

  it('treats usbdebug flag 1 as written and bootloader 0 as unlocked', () => {
    expect(parseUsbdebugFlag('   1')).toBe(1)
    expect(parseUsbdebugFlag('0')).toBe(0)
    expect(parseUsbdebugFlag('')).toBeNull()
    expect(isOemUnlocked('0')).toBe(true)
    expect(isOemUnlocked('1')).toBe(false)
    expect(isOemUnlocked('', 'orange')).toBe(true)
    expect(isOemUnlocked('', 'green')).toBe(false)
  })

  it('finds the newest UD package only under DerivativeVersions', () => {
    const base = join(tmpdir(), `tahp-ud-package-${Date.now()}`)
    const older = join(base, 'TEST', 'old_user', 'DerivativeVersions', 'STS_VERSIONS', 'old_ud', 'Open')
    const newer = join(base, 'TEST', 'new_user', 'DerivativeVersions', 'STS_VERSIONS', 'new_ud', 'Open')
    mkdirSync(older, { recursive: true })
    mkdirSync(newer, { recursive: true })
    try {
      const oldZip = join(older, 'project_old_ud.zip')
      const newZip = join(newer, 'project_new_ud.zip')
      writeFileSync(oldZip, 'old')
      writeFileSync(newZip, 'new')
      const now = new Date()
      const later = new Date(now.getTime() + 10_000)
      utimesSync(oldZip, now, now)
      utimesSync(newZip, later, later)
      writeFileSync(join(base, 'ignored_ud.zip'), 'outside derivative')
      expect(findLatestUdZip(base)).toBe(newZip)
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

describe('ota account store', () => {
  it('keeps username, password and SWD path in the project swd config', () => {
    const base = join(tmpdir(), `tahp-ota-account-${Date.now()}`)
    const prev = process.env.TAHP_CONSOLE_HOME
    const iniPath = swdProjectConfigPath()
    const oemConfigPath = join(iniPath, '..', 'oem-unlock-windows', 'config.json')
    const iniBackup = existsSync(iniPath) ? readFileSync(iniPath) : null
    const oemBackup = existsSync(oemConfigPath) ? readFileSync(oemConfigPath) : null
    process.env.TAHP_CONSOLE_HOME = base
    try {
      writeOtaAccountStore({
        username: '18660000',
        password: 'oa-secret',
        swdToolDir: 'E:\\Softwaredownload',
      })
      const restored = applyStoredOtaAccount({
        username: '',
        password: '',
        swdScriptPath: 'swd_flash.py',
        swdToolDir: '',
        oemToolDir: 'oem-unlock-windows',
      })
      expect(readProjectSwdConfig()).toMatchObject({
        username: '18660000',
        password: 'oa-secret',
        swdToolDir: 'E:\\Softwaredownload',
      })
      expect(readOtaAccountStore()).toMatchObject({
        username: '18660000',
        password: 'oa-secret',
        swdToolDir: 'E:\\Softwaredownload',
      })
      expect(restored.username).toBe('18660000')
      expect(restored.password).toBe('oa-secret')
      expect(restored.swdToolDir).toBe('E:\\Softwaredownload')
      expect(restored.swdScriptPath).toBe('swd_flash.py')
    } finally {
      if (iniBackup) writeFileSync(iniPath, iniBackup)
      else rmSync(iniPath, { force: true })
      if (oemBackup) writeFileSync(oemConfigPath, oemBackup)
      else rmSync(oemConfigPath, { force: true })
      if (prev === undefined) delete process.env.TAHP_CONSOLE_HOME
      else process.env.TAHP_CONSOLE_HOME = prev
      rmSync(base, { recursive: true, force: true })
    }
  })
})
