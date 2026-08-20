import { existsSync } from 'node:fs'

/**
 * Validate a user-provided package path is usable for flashing.
 */
export function validateFlashPkgPath(pkgPath: string): { valid: boolean; reason?: string } {
  if (!pkgPath) return { valid: false, reason: '路径为空' }
  if (!existsSync(pkgPath)) return { valid: false, reason: `路径不存在: ${pkgPath}` }
  return { valid: true }
}
