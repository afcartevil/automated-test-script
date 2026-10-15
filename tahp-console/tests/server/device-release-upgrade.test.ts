import { mkdirSync, rmSync, writeFileSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import { afterEach, describe, expect, it } from 'vitest'
import {
  buildUpgradeSteps,
  findCiRelease,
  applyHighestDailyTcardOverride,
  assertContinuousUpgradeEligible,
  classifyReleaseZipName,
  listVersionFolders,
  matchModelFolder,
  mergeHighestDailyVersion,
  modelFamilyVariants,
  packageSetFromPaths,
  parseMrReleaseFolder,
  parseUserReleaseFolder,
  pickFullFlashZip,
  pickLatestForAndroid,
  pickTcardZipForPreviousAndroid,
  resolveReleasePackageRoot,
  type ParsedReleaseVersion,
} from '../../packages/server/src/services/tahp/device-release-upgrade'
import { missingTcardZipHint } from '../../packages/server/src/services/tahp/device-tcard-zip'

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
    expect(parseUserReleaseFolder('X6876-16.3.0.150SP06(OPPJ005PF001PJ)_MR3_N34')).toMatchObject({
      isOpMarket: false,
    })
    expect(parseMrReleaseFolder('X6850-H895FHJKL-U-OP-250717V3825_MR1')).toMatchObject({
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
    expect(classifyReleaseZipName('X6850-15.1.0.159(OP001PF001AZ).zip')).toBe('full')
    expect(classifyReleaseZipName('X6850-H895FHJKL-U-OP-250717V3825.zip')).toBe('full')
    expect(classifyReleaseZipName('Tcard_X6850-16.3.0.145SP06_a15.zip')).toBe('tcard')
    expect(classifyReleaseZipName('Tcard_X6885-16.3.0.145SP08-OP004PF001AZ.zip')).toBe('tcard')
    expect(classifyReleaseZipName('X-15.1.2.1-16.3.0.2.zip')).toBe('skip')
    expect(classifyReleaseZipName('X6850-H895FHJKL-U-OP-241125V3671-250218V3766_20250219114005.zip')).toBe('skip')
    expect(classifyReleaseZipName('X6885-16.3.0.140SP17-OP007PF001AZ-16.3.0.145SP08-OP004PF001AZ_20260826235808.zip')).toBe('skip')
    expect(classifyReleaseZipName('X6850_user_EFUSE.zip')).toBe('skip')
    expect(classifyReleaseZipName('full_x6850_h895_f1-target_files.zip')).toBe('skip')
    expect(classifyReleaseZipName('trpre_apk_management_system_files.zip')).toBe('skip')
    expect(classifyReleaseZipName('OTA_TOOLS.zip')).toBe('skip')
    expect(classifyReleaseZipName('X6850-15.1.2.180SP05(OP001PF001AZ)_user_root.zip')).toBe('skip')
  })

  it('picks device_update full zip by USER/MR official names, not Tcard or tools', () => {
    const user = parseUserReleaseFolder('X6850-15.1.2.180SP05(OP001PF001AZ)_MR9_N19')!
    const mr = parseMrReleaseFolder('X6850-H895FHJKL-U-OP-250717V3825_MR8')!
    expect(pickFullFlashZip([
      'D:\\Open\\full_x6850_h895_f1-target_files.zip',
      'D:\\Open\\trpre_apk_management_system_files.zip',
      'D:\\Open\\Tcard_X6850-15.1.2.180SP05-OP001PF001AZ.zip',
      'D:\\Open\\X6850-15.1.2.180SP05(OP001PF001AZ)_user_root.zip',
      'D:\\Open\\X6850-15.1.2.180SP05(OP001PF001AZ).zip',
    ], user)).toBe('D:\\Open\\X6850-15.1.2.180SP05(OP001PF001AZ).zip')
    expect(pickFullFlashZip([
      'D:\\Open\\OTA_TOOLS.zip',
      'D:\\Open\\X6850-H895FHJKL-U-OP-241125V3671-250218V3766_20250219114005.zip',
      'D:\\Open\\X6850-H895FHJKL-U-OP-250717V3825.zip',
    ], mr)).toBe('D:\\Open\\X6850-H895FHJKL-U-OP-250717V3825.zip')
  })

  it('selects latest OP release and matching previous-Android T-card package', () => {
    const versions = [
      parseUserReleaseFolder('X6850-15.1.2.170SP01(RU001PF001AZ)_MR8_N1')!,
      parseUserReleaseFolder('X6850-15.1.2.180SP05(OP001PF001AZ)_MR9_N19')!,
      parseUserReleaseFolder('X6850-15.1.2.175SP03(OP001PF001AZ)_MR8_N8')!,
    ]
    expect(pickLatestForAndroid(versions, 15)?.versionName).toBe('15.1.2.180SP05')
    expect(pickLatestForAndroid([
      parseUserReleaseFolder('X6876-16.3.0.150SP06(OPPJ005PF001PJ)_MR3_N34')!,
      parseUserReleaseFolder('X6876-16.3.0.150SP06(OP005PF001AZ)_MR3_N32')!,
      parseUserReleaseFolder('X6876-16.3.0.150SP06(IN005PF001AZ)_MR3_N35')!,
    ], 16)?.folderName).toBe('X6876-16.3.0.150SP06(OP005PF001AZ)_MR3_N32')
    expect(pickTcardZipForPreviousAndroid([
      'D:\\Tcard_X6850-16.3.0.1_a14.zip',
      'D:\\Tcard_X6850-16.3.0.1_a15.zip',
    ], 15)).toContain('_a15')
    expect(pickTcardZipForPreviousAndroid([
      '\\\\cq\\Open\\X6885-16.3.0.140SP17-OP007PF001AZ-16.3.0.145SP08-OP004PF001AZ_20260826235808.zip',
      '\\\\cq\\Open\\Tcard_X6885-16.3.0.145SP08-OP004PF001AZ_a15.zip',
      '\\\\cq\\Open\\Tcard_X6885-16.3.0.145SP08-OP004PF001AZ.zip',
    ], 15)).toBe('\\\\cq\\Open\\Tcard_X6885-16.3.0.145SP08-OP004PF001AZ_a15.zip')
    expect(pickTcardZipForPreviousAndroid([
      '\\\\cq\\Open\\Tcard_X6885-16.3.0.145SP08-OP004PF001AZ.zip',
    ], 15)).toBeUndefined()
    expect(pickTcardZipForPreviousAndroid([
      'D:\\Open\\Tcard_X6850-15.1.2.180SP05-OP001PF001AZ_a14.zip',
      'D:\\Open\\Tcard_X6850-15.1.2.180SP05-OP001PF001AZ.zip',
      'D:\\Open\\Tcard_X6850-16.3.0.145SP06-OP001PF001AZ.zip',
    ], 14)).toBe('D:\\Open\\Tcard_X6850-15.1.2.180SP05-OP001PF001AZ.zip')
    expect(pickTcardZipForPreviousAndroid([
      'D:\\Open\\Tcard_X6850-15.1.2.180SP05-OP001PF001AZ_a14.zip',
    ], 14)).toBeUndefined()
    expect(missingTcardZipHint(14)).toBe('未找到T卡包（需 Tcard_*-15.*.zip）')
    expect(packageSetFromPaths([
      '\\\\cq\\Open\\X6885-16.3.0.140SP17-OP007PF001AZ-16.3.0.145SP08-OP004PF001AZ_20260826235808.zip',
      '\\\\cq\\Open\\Tcard_X6885-16.3.0.145SP08-OP004PF001AZ_a15.zip',
      '\\\\cq\\Open\\Tcard_X6885-16.3.0.145SP08-OP004PF001AZ.zip',
      '\\\\cq\\Open\\X6885-16.3.0.145SP08(OP004PF001AZ).zip',
    ]).tcardZips).toEqual([
      '\\\\cq\\Open\\Tcard_X6885-16.3.0.145SP08-OP004PF001AZ.zip',
      '\\\\cq\\Open\\Tcard_X6885-16.3.0.145SP08-OP004PF001AZ_a15.zip',
    ])
  })

  it('fills Shanghai A15 T-card path when Chongqing only has device_update zip', () => {
    const a15Path = tempVersion('X6885-15.1.0.159(OP004PF001AZ)_MR1')
    const a16Path = tempVersion('X6885-16.3.0.145SP08(OP004PF001AZ)_MR2_N48')
    const shanghaiTcard = join(a16Path, 'Open', 'Tcard_X6885-16.3.0.145SP08-OP004PF001AZ_a15.zip')
    writeFileSync(join(a15Path, 'Open', 'X6885-15.1.0.159(OP004PF001AZ).zip'), 'flash')
    writeFileSync(shanghaiTcard, 'tcard')

    const a15 = parseUserReleaseFolder('X6885-15.1.0.159(OP004PF001AZ)_MR1', a15Path)!
    const a16 = parseUserReleaseFolder('X6885-16.3.0.145SP08(OP004PF001AZ)_MR2_N48', a16Path)!
    const a15Full = '\\\\cq\\Open\\X6885-15.1.0.159(OP004PF001AZ).zip'
    const a16Full = '\\\\cq\\Open\\X6885-16.3.0.145SP08(OP004PF001AZ).zip'
    const steps = buildUpgradeSteps(
      [a15, a16],
      (release) => release.androidVersion === 15
        ? { model: 'X6885-H8923', version: release, packages: packageSetFromPaths([a15Full]) }
        : {
            model: 'X6885-H8923',
            version: release,
            packages: packageSetFromPaths([
              a16Full,
              '\\\\cq\\Open\\Tcard_X6885-16.3.0.145SP08-OP004PF001AZ.zip',
            ]),
          },
      () => '\\\\cq\\X6885-H8923\\USER\\Open',
    )

    expect(steps[0]?.packagePath).toBe(a15Full)
    expect(steps[1]).toMatchObject({
      androidVersion: 16,
      packagePath: shanghaiTcard,
      sourcePath: shanghaiTcard,
      fullZip: a16Full,
      tcardZips: [shanghaiTcard],
      available: false,
      selected: false,
      needsTransfer: true,
    })
    expect(steps[1]?.packagePath).not.toBe(a16Full)
    expect(steps[1]?.unavailableReason).toBeUndefined()
  })

  it('scans all same-Android folders for T-card instead of only the latest OP Open', () => {
    const a15Path = tempVersion('X6873-15.1.2.165SP07(OP001PF001AZ)_MR11_N34')
    const a16LatestPath = tempVersion('X6873-16.3.0.150SP09(OP006PF001AZ)_MR4_N53')
    const a16OlderPath = tempVersion('X6873-16.2.0.145SP03(OP002PF001AZ)_MR2_N45')
    const shanghaiTcard = join(a16OlderPath, 'Open', 'Tcard_X6873-16.2.0.145SP03-OP002PF001AZ_a15.zip')
    writeFileSync(join(a15Path, 'Open', 'X6873-15.1.2.165SP07(OP001PF001AZ).zip'), 'flash')
    writeFileSync(join(a16LatestPath, 'Open', 'X6873-16.3.0.150SP09(OP006PF001AZ).zip'), 'full')
    writeFileSync(shanghaiTcard, 'tcard')

    const a15 = parseUserReleaseFolder('X6873-15.1.2.165SP07(OP001PF001AZ)_MR11_N34', a15Path)!
    const a16Latest = parseUserReleaseFolder('X6873-16.3.0.150SP09(OP006PF001AZ)_MR4_N53', a16LatestPath)!
    const a16Older = parseUserReleaseFolder('X6873-16.2.0.145SP03(OP002PF001AZ)_MR2_N45', a16OlderPath)!
    const a15Full = '\\\\cq\\Open\\X6873-15.1.2.165SP07(OP001PF001AZ).zip'
    const a16Full = '\\\\cq\\Open\\X6873-16.3.0.150SP09(OP006PF001AZ).zip'
    const steps = buildUpgradeSteps(
      [a15, a16Latest, a16Older],
      (release) => release.androidVersion === 15
        ? { model: 'X6873-H972', version: release, packages: packageSetFromPaths([a15Full]) }
        : { model: 'X6873-H972', version: a16Latest, packages: packageSetFromPaths([a16Full]) },
      (_model, release) => `\\\\cq\\X6873-H972\\${release.relativePath}\\Open`,
    )

    expect(steps[1]).toMatchObject({
      androidVersion: 16,
      packagePath: shanghaiTcard,
      sourcePath: shanghaiTcard,
      releaseFolder: a16Older.folderName,
      releaseVersionName: '16.2.0.145SP03',
      fullZip: a16Full,
      available: false,
      selected: false,
      needsTransfer: true,
    })
    expect(steps[1]?.packagePath).not.toBe(a16Full)
    expect(steps[1]?.cqTargetPath).toContain(a16Older.folderName)
  })

  it('prefers OP-market T-card over other markets when scanning all folders', () => {
    const a15Path = tempVersion('X6873-15.1.2.165SP07(OP001PF001AZ)_MR11_N34')
    const inPath = tempVersion('X6873-16.3.0.150SP09(IN006PF001AZ)_MR3_N56')
    const opPath = tempVersion('X6873-16.2.0.145SP03(OP002PF001AZ)_MR2_N45')
    const inTcard = join(inPath, 'Open', 'Tcard_X6873-16.3.0.150SP09-IN006PF001AZ_a15.zip')
    const opTcard = join(opPath, 'Open', 'Tcard_X6873-16.2.0.145SP03-OP002PF001AZ_a15.zip')
    writeFileSync(join(a15Path, 'Open', 'X6873-15.1.2.165SP07(OP001PF001AZ).zip'), 'flash')
    writeFileSync(inTcard, 'in')
    writeFileSync(opTcard, 'op')

    const a15 = parseUserReleaseFolder('X6873-15.1.2.165SP07(OP001PF001AZ)_MR11_N34', a15Path)!
    const a16In = parseUserReleaseFolder('X6873-16.3.0.150SP09(IN006PF001AZ)_MR3_N56', inPath)!
    const a16Op = parseUserReleaseFolder('X6873-16.2.0.145SP03(OP002PF001AZ)_MR2_N45', opPath)!
    const steps = buildUpgradeSteps(
      [a15, a16In, a16Op],
      (release) => release.androidVersion === 15
        ? { model: 'X6873-H972', version: release, packages: packageSetFromPaths(['\\\\cq\\a15.zip']) }
        : null,
      () => '\\\\cq\\Open',
    )

    expect(steps[1]?.packagePath).toBe(opTcard)
    expect(steps[1]?.releaseFolder).toBe(a16Op.folderName)
  })

  it('does not fill device_update zip when neither Chongqing nor Shanghai has the A15 T-card', () => {
    const a15 = parseUserReleaseFolder('X6885-15.1.0.159(OP004PF001AZ)_MR1')!
    const a16 = parseUserReleaseFolder('X6885-16.3.0.145SP08(OP004PF001AZ)_MR2_N48')!
    const a15Full = '\\\\cq\\Open\\X6885-15.1.0.159(OP004PF001AZ).zip'
    const a16Full = '\\\\cq\\Open\\X6885-16.3.0.145SP08(OP004PF001AZ).zip'
    const steps = buildUpgradeSteps(
      [a15, a16],
      (release) => release.androidVersion === 15
        ? { model: 'X6885-H8923', version: release, packages: packageSetFromPaths([a15Full]) }
        : {
            model: 'X6885-H8923',
            version: release,
            packages: packageSetFromPaths([
              a16Full,
              '\\\\cq\\Open\\Tcard_X6885-16.3.0.145SP08-OP004PF001AZ.zip',
            ]),
          },
      () => '\\\\cq\\X6885-H8923\\USER\\Open',
    )

    expect(steps[1]).toMatchObject({
      androidVersion: 16,
      packagePath: '',
      fullZip: a16Full,
      tcardZips: [],
      available: false,
      selected: false,
      needsTransfer: false,
      unavailableReason: missingTcardZipHint(15),
    })
    expect(steps[1]?.packagePath).not.toBe(a16Full)
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
        packages: packageSetFromPaths(['\\\\cq\\X6879-16.3.0.155SP08(OP005PF001AZ).zip']),
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
    const a15Zip = join(a15Path, 'Open', 'X6850-15.1.2.180SP05(OP001PF001AZ).zip')
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
    const ciPackages = packageSetFromPaths(['\\\\cq\\Open\\X6850-15.1.2.180SP05(OP001PF001AZ).zip'])
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

  it('resolves USER Open directly and MR nested platform Open for Chongqing path', () => {
    const modelRoot = join(tmpdir(), `tahp-release-${Date.now()}-${tempRoots.length}`)
    tempRoots.push(modelRoot)
    const extra = 'tran_mtk_u0.mp1.rc_v3.8_os13.6-os14.0_mp.rel_231212'
    const mrFolder = 'X6850-H895FHJKL-U-OP-250218V3766_MR11'
    const userFolder = 'X6850-15.1.2.180SP05(OP001PF001AZ)_MR9_N19'
    const userPath = join(modelRoot, 'USER', userFolder)
    const mrPath = join(modelRoot, 'x6850_h895_f1', 'MR', mrFolder)
    mkdirSync(join(userPath, 'Open'), { recursive: true })
    mkdirSync(join(mrPath, extra, 'Open'), { recursive: true })
    writeFileSync(join(userPath, 'Open', 'X6850-15.1.2.180SP05(OP001PF001AZ).zip'), 'user')
    writeFileSync(join(mrPath, extra, 'Open', 'X6850-H895FHJKL-U-OP-250218V3766.zip'), 'mr')

    expect(resolveReleasePackageRoot(userPath)).toBe(userPath)
    expect(resolveReleasePackageRoot(mrPath)).toBe(join(mrPath, extra))

    const versions = listVersionFolders(modelRoot)
    const a14 = versions.find((item) => item.androidVersion === 14)
    const a15 = versions.find((item) => item.androidVersion === 15)
    expect(a14?.relativePath).toBe(join('x6850_h895_f1', 'MR', mrFolder, extra))
    expect(a15?.relativePath).toBe(join('USER', userFolder))

    const steps = buildUpgradeSteps(
      versions,
      () => null,
      (model, release) => join('\\\\10.205.4.40\\cq', model || 'X6850-H895', release.relativePath, 'Open'),
    )
    const a14Step = steps.find((step) => step.androidVersion === 14)
    expect(a14Step?.cqTargetPath).toContain(extra)
    expect(a14Step?.cqTargetPath.replace(/\//g, '\\')).toBe(
      `\\\\10.205.4.40\\cq\\X6850-H895\\x6850_h895_f1\\MR\\${mrFolder}\\${extra}\\Open`,
    )
  })

  it('prefers nested Open with zips when version root Open is missing', () => {
    const root = join(tmpdir(), `tahp-release-${Date.now()}-${tempRoots.length}`)
    const versionPath = join(root, 'MR11')
    tempRoots.push(root)
    const extra = 'tran_mtk_t0.mp1.rc_v9.9_os13.0-os14.0_mp.rel_999999'
    mkdirSync(join(versionPath, extra, 'Open'), { recursive: true })
    mkdirSync(join(versionPath, 'other_platform', 'Open'), { recursive: true })
    writeFileSync(join(versionPath, extra, 'Open', 'full.zip'), 'ok')
    expect(resolveReleasePackageRoot(versionPath)).toBe(join(versionPath, extra))
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

  it('keeps CI packages and falls back to CI\\IDH with the same relative path', () => {
    const root = join(tmpdir(), `tahp-ci-idh-${Date.now()}-${tempRoots.length}`)
    tempRoots.push(root)
    const folder = 'LI9-15.1.2.170SP05(OP001PF001AZ)'
    const ciOpen = join(root, 'CI', 'RELEASE_VERSIONS', 'TECNO', 'LI9-H335', 'USER', folder, 'Open')
    const idhOpen = join(root, 'CI', 'IDH', 'RELEASE_VERSIONS', 'TECNO', 'LI9-H335', 'USER', folder, 'Open')
    mkdirSync(ciOpen, { recursive: true })
    mkdirSync(idhOpen, { recursive: true })
    const ciZip = join(ciOpen, 'LI9-15.1.2.170SP05(OP001PF001AZ).zip')
    const idhZip = join(idhOpen, 'LI9-15.1.2.170SP05(OP001PF001AZ).zip')
    writeFileSync(ciZip, 'ci')
    writeFileSync(idhZip, 'idh')

    const release = parseUserReleaseFolder(folder)!
    const ciBrand = join(root, 'CI', 'RELEASE_VERSIONS', 'TECNO')
    const idhBrand = join(root, 'CI', 'IDH', 'RELEASE_VERSIONS', 'TECNO')
    expect(findCiRelease([ciBrand, idhBrand], ['LI9-H335'], release)).toMatchObject({
      brandRoot: ciBrand,
      packages: { fullZip: ciZip },
    })

    rmSync(join(root, 'CI', 'RELEASE_VERSIONS', 'TECNO', 'LI9-H335'), { recursive: true, force: true })
    expect(findCiRelease([ciBrand, idhBrand], ['LI9-H335'], release)).toMatchObject({
      brandRoot: idhBrand,
      packages: { fullZip: idhZip },
    })
  })
})
