import { mkdirSync, rmSync, writeFileSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import { afterEach, describe, expect, it } from 'vitest'
import {
  buildUpgradeSteps,
  applyHighestDailyTcardOverride,
  assertContinuousUpgradeEligible,
  classifyReleaseZipName,
  matchModelFolder,
  mergeHighestDailyVersion,
  modelFamilyVariants,
  packageSetFromPaths,
  parseMrReleaseFolder,
  parseUserReleaseFolder,
  pickLatestForAndroid,
  pickTcardZipForPreviousAndroid,
  type ParsedReleaseVersion,
} from '../../packages/server/src/services/tahp/device-release-upgrade'

const tempRoots: string[] = []

function tempVersion(folderName: string): string {
  const root = join(tmpdir(), `tahp-release-${Date.now()}-${tempRoots.length}`)
  const versionPath = join(root, folderName)
  mkdirSync(join(versionPath, 'Open'), { recursive: true })
  tempRoots.push(root)
  return versionPath
}

afterEach(() => {
  tempRoots.splice(0).forEach((root) => rmSync(root, { recursive: true, force: true }))
})

describe('release upgrade resolver helpers', () => {
  it('parses USER and MR versions into Android majors', () => {
    expect(parseUserReleaseFolder('X6850-15.1.2.180SP05(OP001PF001AZ)_MR9_N19')).toMatchObject({
      androidVersion: 15,
      versionName: '15.1.2.180SP05',
      isOpMarket: true,
    })
    expect(parseMrReleaseFolder('X6850-H895DE-U-EU-240927V3580_MR5')).toMatchObject({
      androidVersion: 14,
      versionName: '240927V3580',
      channel: 'MR',
    })
  })

  it('classifies full and incremental packages', () => {
    expect(classifyReleaseZipName('X6850-15.1.2.180SP05(OP001PF001AZ).zip')).toBe('full')
    expect(classifyReleaseZipName('Tcard_X6850-16.3.0.145SP06_a15.zip')).toBe('tcard')
    expect(classifyReleaseZipName('X-15.1.2.1-16.3.0.2.zip')).toBe('tcard')
    expect(classifyReleaseZipName('X6850_user_EFUSE.zip')).toBe('skip')
  })

  it('selects latest OP release and matching previous-Android T-card package', () => {
    const versions = [
      parseUserReleaseFolder('X6850-15.1.2.170SP01(RU001PF001AZ)_MR8_N1')!,
      parseUserReleaseFolder('X6850-15.1.2.180SP05(OP001PF001AZ)_MR9_N19')!,
      parseUserReleaseFolder('X6850-15.1.2.175SP03(OP001PF001AZ)_MR8_N8')!,
    ]
    expect(pickLatestForAndroid(versions, 15)?.versionName).toBe('15.1.2.180SP05')
    expect(pickTcardZipForPreviousAndroid([
      'D:\\Tcard_X6850-16.3.0.1_a14.zip',
      'D:\\Tcard_X6850-16.3.0.1_a15.zip',
    ], 15)).toContain('_a15')
  })

  it('rejects continuous upgrade when RELEASE has only one Android major', () => {
    const releases = [
      parseUserReleaseFolder('X6850-16.3.0.145SP06(OP005PF001AZ)_FR_N52')!,
      parseUserReleaseFolder('X6850-16.3.0.155SP08(OP005PF001AZ)_FR_N53')!,
    ]
    expect(() => assertContinuousUpgradeEligible(releases))
      .toThrow('仅识别到一个 Android 大版本（Android 16），不能使用连续版本升级')
    expect(() => assertContinuousUpgradeEligible([
      ...releases,
      parseUserReleaseFolder('X6850-15.1.2.180SP05(OP001PF001AZ)_MR9_N19')!,
    ])).not.toThrow()
  })

  it('keeps the plan when daily adds a second Android major without a T-card package', () => {
    const release = parseUserReleaseFolder('X6879-16.3.0.155SP08(OP005PF001AZ)_FR_N53')!
    const steps = buildUpgradeSteps(
      [release],
      () => ({
        model: 'X6879-H785',
        version: release,
        packages: packageSetFromPaths(['\\\\cq\\X6879-16.3.0.155SP08.zip']),
      }),
      () => '\\\\cq\\X6879-H785\\USER\\Open',
    )
    const merged = mergeHighestDailyVersion(steps, {
      androidVersion: 17,
      systemVersion: 'tOS17.0',
      versionName: '2026.09.21.01.00.00_1',
      devProjectPath: '\\\\sh\\X6879-H785\\DEV\\Android_17',
      openPath: '\\\\cq\\X6879-H785\\DEV\\Android_17\\Open',
      tcardResolveWarning: 'TEST 下未找到 Android 17 的 T卡升级包',
    })

    expect(merged).toEqual({ added: true, overrideApplied: false })
    expect(steps.map((step) => step.androidVersion)).toEqual([16, 17])
    expect(steps[1]).toMatchObject({
      channel: 'DAILY',
      available: false,
      selected: false,
      unavailableReason: 'TEST 下未找到 Android 17 的 T卡升级包',
    })
    expect(() => assertContinuousUpgradeEligible(steps)).not.toThrow()
  })

  it('marks missing Chongqing package for transfer and keeps Shanghai source path', () => {
    const a15Path = tempVersion('X6850-15.1.2.180SP05(OP001PF001AZ)_MR9_N19')
    const a16Path = tempVersion('X6850-16.3.0.145SP06(OP005PF001AZ)_FR_N52')
    const a15Zip = join(a15Path, 'Open', 'X6850-15.1.2.180SP05.zip')
    const a16Zip = join(a16Path, 'Open', 'Tcard_X6850-16.3.0.145SP06_a15.zip')
    writeFileSync(a15Zip, 'flash')
    writeFileSync(a16Zip, 'tcard')

    const a15 = parseUserReleaseFolder(
      'X6850-15.1.2.180SP05(OP001PF001AZ)_MR9_N19',
      a15Path,
    )!
    const a16 = parseUserReleaseFolder(
      'X6850-16.3.0.145SP06(OP005PF001AZ)_FR_N52',
      a16Path,
    )!
    const ciPackages = packageSetFromPaths(['\\\\cq\\Open\\X6850-15.1.2.180SP05.zip'])
    const steps = buildUpgradeSteps(
      [a15, a16] as ParsedReleaseVersion[],
      (release) => release.androidVersion === 15
        ? { model: 'X6850-H895', version: release, packages: ciPackages }
        : null,
      (model, release) => `\\\\cq\\${model || 'X6850-H895'}\\${release.relativePath}\\Open`,
    )

    expect(steps[0]).toMatchObject({ available: true, needsTransfer: false, selected: true })
    expect(steps[1]).toMatchObject({
      available: false,
      needsTransfer: true,
      selected: false,
      sourcePath: a16Zip,
    })
    expect(steps[1]?.cqTargetPath).toContain('X6850-H895')
  })

  it('provides B/non-B model family fallback', () => {
    expect(modelFamilyVariants('X6850B-H895')).toEqual(['X6850B-H895', 'X6850-H895'])
  })

  it('prefers standard hardware-suffixed model folder over generic project folder', () => {
    expect(matchModelFolder(
      ['X6879', 'X6879-H785', 'X6876-H786'],
      ['X6879'],
    )).toBe('X6879-H785')
    expect(matchModelFolder(
      ['X6879', 'X6879-H785'],
      ['X6879-H785', 'X6879'],
    )).toBe('X6879-H785')
  })

  it('overrides only matching RELEASE highest Android with latest daily T-card path', () => {
    const steps = [
      {
        androidVersion: 15,
        androidLabel: 'Android 15',
        releaseVersionName: '15.1.2.180',
        releaseFolder: 'a15',
        channel: 'USER' as const,
        packagePath: '\\\\cq\\a15.zip',
        fullZip: '\\\\cq\\a15.zip',
        tcardZips: [],
        cqTargetPath: '\\\\cq\\a15',
        needsTransfer: false,
        available: true,
        selected: true,
      },
      {
        androidVersion: 16,
        androidLabel: 'Android 16',
        releaseVersionName: '16.3.0.145',
        releaseFolder: 'a16',
        channel: 'USER' as const,
        packagePath: '\\\\cq\\old-a16.zip',
        tcardZips: ['\\\\cq\\old-a16.zip'],
        cqTargetPath: '\\\\cq\\a16',
        needsTransfer: false,
        available: true,
        selected: true,
      },
    ]
    const latestDaily = '\\\\cq\\daily\\Tcard_X6850-16.3.0.200_a15.zip'
    expect(applyHighestDailyTcardOverride(steps, {
      androidVersion: 16,
      tcardPackagePath: latestDaily,
    })).toBe(true)
    expect(steps[1]?.packagePath).toBe(latestDaily)
    expect(steps[1]?.tcardZips[0]).toBe(latestDaily)

    expect(applyHighestDailyTcardOverride(steps, {
      androidVersion: 17,
      tcardPackagePath: '\\\\cq\\daily\\a17.zip',
    })).toBe(false)
  })
})
