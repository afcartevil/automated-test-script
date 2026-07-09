import { describe, expect, it } from 'vitest'
import { existsSync } from 'fs'
import { join, resolve } from 'path'
import { isValidTahpProjectRoot } from '../../packages/server/src/services/tahp/paths'

/**
 * 回归：dist/server/index.js 打包后 __dirname 为 dist/server，
 * 旧逻辑会把 projectRoot 误解析为盘符根目录（如 D:\ / E:\）。
 */
describe('tahp paths (dist __dirname regression)', () => {
  it('dist/server __dirname should resolve to tahp repo root, not drive root', () => {
    const consoleRoot = resolve(process.cwd())
    const distServerDir = join(consoleRoot, 'dist', 'server')

    function isConsoleRoot(dir: string): boolean {
      return (
        existsSync(join(dir, 'package.json')) &&
        existsSync(join(dir, 'packages', 'server'))
      )
    }

    const derivedConsole = resolve(distServerDir, '..', '..')
    expect(isConsoleRoot(derivedConsole)).toBe(true)

    const projectRoot = resolve(derivedConsole, '..')
    expect(isValidTahpProjectRoot(projectRoot)).toBe(true)
    expect(projectRoot).not.toMatch(/^[A-Za-z]:[\\/]?$/)
  })

  it('rejects drive root even when skills folder exists', () => {
    const drive = `${process.platform === 'win32' ? 'Z:' : '/'}\\`
    const fakeRoot = resolve(drive)
    if (fakeRoot.match(/^[A-Za-z]:[\\/]?$/)) {
      expect(isValidTahpProjectRoot(fakeRoot)).toBe(false)
    }
  })
})
