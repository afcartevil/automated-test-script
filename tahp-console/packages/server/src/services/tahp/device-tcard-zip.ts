/**
 * T卡 / 连续 OTA 包名规则：只认 Tcard_ 前缀。
 * A15→A16 及以后只选 Tcard_*_a{上一档}.zip。
 * A14→A15 不认 _a14 尾缀，选 Tcard_项目-15.x...zip。
 */
const SKIP_ZIP_RE = /(_user|_userdebug|_eng|efuse|target_files|ota_tools|^OTA_TOOLS\.zip$|trpre_apk)/i
const ANDROID_SUFFIX_RE = /_a\d+\.zip$/i
const TCARD_TARGET_ANDROID_RE = /^Tcard_[^-]+-(\d+)\./i

export function zipFileName(path: string): string {
  return path.replace(/^.*[\\/]/, '')
}

export function isOfficialTcardZipName(name: string): boolean {
  const fileName = zipFileName(name)
  return /^Tcard_/i.test(fileName) && /\.zip$/i.test(fileName) && !SKIP_ZIP_RE.test(fileName)
}

function tcardTargetAndroid(fileName: string): number | undefined {
  const match = TCARD_TARGET_ANDROID_RE.exec(fileName)
  if (!match) return undefined
  const major = Number(match[1])
  return Number.isFinite(major) ? major : undefined
}

export function rankTcardZip(name: string, previousAndroid?: number): number {
  const fileName = zipFileName(name)
  if (!isOfficialTcardZipName(fileName)) return -1
  if (previousAndroid === 14) {
    if (ANDROID_SUFFIX_RE.test(fileName)) return -1
    return tcardTargetAndroid(fileName) === previousAndroid + 1 ? 4 : -1
  }
  if (previousAndroid != null) {
    return new RegExp(`_a${previousAndroid}\\.zip$`, 'i').test(fileName) ? 4 : -1
  }
  if (!ANDROID_SUFFIX_RE.test(fileName)) return 2
  return 1
}

export function sortTcardZipPaths(paths: string[], previousAndroid?: number): string[] {
  return paths
    .filter((path) => rankTcardZip(path, previousAndroid) >= 0)
    .slice()
    .sort((a, b) => {
      const delta = rankTcardZip(b, previousAndroid) - rankTcardZip(a, previousAndroid)
      return delta || b.localeCompare(a)
    })
}

export function pickPreferredTcardZipPath(
  paths: string[],
  previousAndroid?: number,
): string | undefined {
  return sortTcardZipPaths(paths, previousAndroid)[0]
}

export function missingTcardZipHint(previousAndroid: number): string {
  if (previousAndroid === 14) return '未找到T卡包（需 Tcard_*-15.*.zip）'
  return `未找到T卡包（需 Tcard_*_a${previousAndroid}.zip）`
}
