import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, describe, expect, it } from 'vitest'
import { findUdFirmwareFile } from '../../packages/server/src/services/tahp/ota-pretest'

const dirs: string[] = []

function makeDir(): string {
  const dir = mkdtempSync(join(tmpdir(), 'ud-fw-'))
  dirs.push(dir)
  return dir
}

afterEach(() => {
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true })
})

describe('findUdFirmwareFile', () => {
  it('优先 download_agent/flash.xml', () => {
    const dir = makeDir()
    mkdirSync(join(dir, 'download_agent'), { recursive: true })
    writeFileSync(join(dir, 'flash.xml'), '<xml/>')
    writeFileSync(join(dir, 'download_agent', 'flash.xml'), '<xml/>')
    writeFileSync(join(dir, 'MT6833_Android_scatter.txt'), 'scatter')
    expect(findUdFirmwareFile(dir)).toBe(join(dir, 'download_agent', 'flash.xml'))
  })

  it('没有 flash.xml 时使用根目录 *_Android_scatter.txt', () => {
    const dir = makeDir()
    mkdirSync(join(dir, 'Open'), { recursive: true })
    mkdirSync(join(dir, 'nested'), { recursive: true })
    writeFileSync(join(dir, 'efuse_MT6833.xml'), '<xml/>')
    writeFileSync(join(dir, 'MT6833_Android_scatter.xml'), '<xml/>')
    writeFileSync(join(dir, 'MT6833_Android_scatter.txt'), 'scatter')
    writeFileSync(join(dir, 'Open', 'Open_scatter.txt'), 'open')
    writeFileSync(join(dir, 'nested', 'MT6789_Android_scatter.txt'), 'nested')
    expect(findUdFirmwareFile(dir)).toBe(join(dir, 'MT6833_Android_scatter.txt'))
  })

  it('两者都没有时返回 null', () => {
    const dir = makeDir()
    writeFileSync(join(dir, 'Open_scatter.txt'), 'open')
    expect(findUdFirmwareFile(dir)).toBeNull()
  })
})
