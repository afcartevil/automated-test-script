import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, describe, expect, it } from 'vitest'
import {
  classifyFlashArtifacts,
  inferPartitionFromImgName,
} from '../../packages/server/src/services/tahp/adapt-pipeline/flash-artifact-classify'
import { resolveHarnessSkillPath } from '../../packages/server/src/services/tahp/adapt-pipeline/harness-skill-registry'

describe('flash-artifact-classify', () => {
  let dir = ''

  afterEach(() => {
    if (dir) rmSync(dir, { recursive: true, force: true })
    dir = ''
  })

  it('infers partition from img name', () => {
    expect(inferPartitionFromImgName('boot.img')).toBe('boot')
    expect(inferPartitionFromImgName('super.img')).toBe('super')
    expect(inferPartitionFromImgName('my_boot_v2.img')).toBeUndefined()
  })

  it('classifies zip as full_rom', () => {
    dir = mkdtempSync(join(tmpdir(), 'flash-cls-'))
    const zip = join(dir, 'flashfiles.zip')
    writeFileSync(zip, 'x')
    expect(classifyFlashArtifacts({ pkgPath: zip }).kind).toBe('full_rom')
  })

  it('classifies scatter directory as full_rom', () => {
    dir = mkdtempSync(join(tmpdir(), 'flash-cls-'))
    writeFileSync(join(dir, 'MT6789_Android_scatter.xml'), '<xml/>')
    expect(classifyFlashArtifacts({ artifactsDir: dir }).kind).toBe('full_rom')
  })

  it('classifies single img', () => {
    dir = mkdtempSync(join(tmpdir(), 'flash-cls-'))
    const img = join(dir, 'boot.img')
    writeFileSync(img, 'img')
    const c = classifyFlashArtifacts({ pkgPath: img })
    expect(c.kind).toBe('single_img')
    expect(c.partition).toBe('boot')
    expect(c.imgPath).toBe(img)
  })

  it('returns none for empty native-like output', () => {
    dir = mkdtempSync(join(tmpdir(), 'flash-cls-'))
    writeFileSync(join(dir, 'TeleService.apk'), 'apk')
    expect(classifyFlashArtifacts({ artifactsDir: dir }).kind).toBe('none')
  })
})

describe('harness-flash-single-img skill path', () => {
  it('resolves project skill', () => {
    const p = resolveHarnessSkillPath('harness-flash-single-img')
    expect(p).toBeTruthy()
    expect(p!.replace(/\\/g, '/')).toContain('harness-flash-single-img/SKILL.md')
  })
})
