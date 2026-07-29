import { existsSync } from 'node:fs'
import { resolve, basename } from 'node:path'

/**
 * Resolve build artifacts directory to a Windows-accessible flash package path.
 *
 * Linux build output path → mapped Windows drive path → verify existence → pkgPath.
 * Returns null when resolution fails (caller should fall back to human pick).
 */
export function resolveFlashPkgPath(
  artifactsDir: string | undefined,
  mappedRoot: string | undefined,
): string | null {
  if (!artifactsDir || !mappedRoot) return null

  // artifactsDir may be a Linux path from the build server.
  // mappedRoot is the Windows-mapped drive root (e.g. Z:\some\project).
  // Try direct use first (already Windows), then attempt Linux→Windows mapping.
  const candidates: string[] = []

  if (existsSync(artifactsDir)) {
    candidates.push(artifactsDir)
  }

  // Common pattern: Linux /home/user/project/out/... → Z:\out\...
  // Extract relative portion after common prefixes
  const linuxPrefixes = ['/home/', '/mnt/', '/data/']
  for (const prefix of linuxPrefixes) {
    const idx = artifactsDir.indexOf(prefix)
    if (idx >= 0) {
      // Find project boundary (3rd slash after prefix start)
      const afterPrefix = artifactsDir.substring(idx + prefix.length)
      const slashIdx = afterPrefix.indexOf('/')
      if (slashIdx >= 0) {
        const relative = afterPrefix.substring(slashIdx + 1).replace(/\//g, '\\')
        const mapped = resolve(mappedRoot, relative)
        if (existsSync(mapped)) {
          candidates.push(mapped)
        }
      }
    }
  }

  // Look for .zip or directory containing flash-ready files
  for (const dir of candidates) {
    const zipCandidate = findFlashPackage(dir)
    if (zipCandidate) return zipCandidate
    if (existsSync(dir)) return dir
  }

  return null
}

function findFlashPackage(dir: string): string | null {
  if (!existsSync(dir)) return null

  // If dir itself is a zip
  if (dir.endsWith('.zip') && existsSync(dir)) return dir

  // Check common package names in the directory
  const names = ['flashfiles.zip', 'package.zip', 'images.zip']
  for (const name of names) {
    const p = resolve(dir, name)
    if (existsSync(p)) return p
  }

  return null
}

/**
 * Validate a user-provided package path is usable for flashing.
 */
export function validateFlashPkgPath(pkgPath: string): { valid: boolean; reason?: string } {
  if (!pkgPath) return { valid: false, reason: '路径为空' }
  if (!existsSync(pkgPath)) return { valid: false, reason: `路径不存在: ${pkgPath}` }
  return { valid: true }
}
