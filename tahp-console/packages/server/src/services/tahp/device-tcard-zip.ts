/**
 * T卡 / 连续 OTA 包名规则：只认 Tcard_ 前缀；
 * 优先不带 _aNN 后缀的官方名，再退回 Tcard_*_a{previousAndroid}.zip。
 */
const SKIP_ZIP_RE = /(_user|_userdebug|_eng|efuse|target_files|ota_tools|^OTA_TOOLS\.zip$|trpre_apk)/i
const ANDROID_SUFFIX_RE = /_a\d+\.zip$/i

export function zipFileName(path: string): string {
  return path.replace(/^.*[\\/]/, '')
}

export function isOfficialTcardZipName(name: string): boolean {
  const fileName = zipFileName(name)
  return /^Tcard_/i.test(fileName) && /\.zip$/i.test(fileName) && !SKIP_ZIP_RE.test(fileName)
}

export function rankTcardZip(name: string, previousAndroid?: number): number {
  const fileName = zipFileName(name)
  if (!isOfficialTcardZipName(fileName)) return -1
  if (!ANDROID_SUFFIX_RE.test(fileName)) return 3
  if (previousAndroid != null && new RegExp(`_a${previousAndroid}\\.zip$`, 'i').test(fileName)) return 2
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
