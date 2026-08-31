import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'fs'
import { dirname, join } from 'path'
import { tmpdir } from 'os'
import { afterEach, describe, expect, it } from 'vitest'
import {
  PATH_PARAM_FIELDS,
  flattenPathParams,
  parsePathParams,
  winJoin,
} from '../../packages/server/src/services/tahp/adapt-pipeline/path-params'
import {
  createRun,
  getRun,
  resetStoreForTest,
} from '../../packages/server/src/services/tahp/adapt-pipeline/store'

const PROJECT = 'lk7k_h582'
const SOC = 'mt6858'
const KERNEL = '6.12'
const VEXT = 'k6858v1_64'

function writeFile(filePath: string, content: string) {
  mkdirSync(dirname(filePath), { recursive: true })
  writeFileSync(filePath, content)
}

function populateVendorTree(root: string, side: 'old' | 'new', extraProjects: string[] = []) {
  const names = [PROJECT, ...extraProjects]
  for (const name of names) {
    const proj = join(root, 'vendor', 'transsion', 'projects', name)
    mkdirSync(proj, { recursive: true })
  }

  const proj = join(root, 'vendor', 'transsion', 'projects', PROJECT)
  writeFile(join(proj, 'BoardConfig-vext.mk'), `TARGET_BOARD_PLATFORM := MT6858\n`)
  writeFile(join(proj, 'ProjectConfig.mk'), `LINUX_KERNEL_VERSION := kernel-${KERNEL} # comment\n`)
  writeFile(join(proj, `vnd_${PROJECT}.mk`), `VEXT_TARGET_PROJECT := ${VEXT}\n`)
  writeFile(join(proj, 'ko_order_table.csv'), 'id,name\n')

  writeFile(
    join(root, 'vendor', 'mediatek', 'proprietary', 'tools', 'dct', 'dws', SOC, `${PROJECT}.dws`),
    'dws\n',
  )
  writeFile(
    join(
      root,
      'vendor', 'mediatek', 'proprietary', 'bootable', 'bootloader', 'preloader',
      'custom', PROJECT, 'dct', 'dct', 'codegen.dws',
    ),
    'dws\n',
  )
  writeFile(
    join(
      root,
      'vendor', 'mediatek', 'proprietary', 'bootable', 'bootloader', 'lk2', 'project', `${PROJECT}.mk`,
    ),
    'mk\n',
  )
  writeFile(join(root, 'device', 'mediateksample', VEXT, 'ko_order_table.csv'), 'csv\n')

  mkdirSync(
    join(root, 'kernel', `kernel_device_modules-${KERNEL}`, 'arch', 'arm64', 'boot', 'dts', 'mediatek'),
    { recursive: true },
  )
  writeFile(
    join(root, 'kernel', `kernel_device_modules-${KERNEL}`, 'arch', 'arm64', 'boot', 'dts', 'mediatek', `${SOC}.dts`),
    '/dts-v1/;\n',
  )
  if (side === 'new') {
    mkdirSync(
      join(root, 'kernel', `kernel_device_modules-${KERNEL}`, 'arch', 'arm64', 'boot', 'dts', 'transsion'),
      { recursive: true },
    )
  }
}

function fieldMap(result: ReturnType<typeof parsePathParams>) {
  return new Map(result.fields.map(f => [f.key, f]))
}

describe('adapt-pipeline path params', () => {
  const temps: string[] = []

  function tempDir(prefix: string): string {
    const dir = mkdtempSync(join(tmpdir(), prefix))
    temps.push(dir)
    return dir
  }

  afterEach(() => {
    resetStoreForTest()
    delete process.env.TAHP_ADAPT_PIPELINE_DIR
    for (const dir of temps.splice(0)) {
      if (existsSync(dir)) rmSync(dir, { recursive: true, force: true })
    }
  })

  it('winJoin keeps mapped-drive vendor suffix and mixed slashes', () => {
    expect(winJoin('Z:/project/CM8/vendor', 'vendor', 'transsion', 'projects'))
      .toBe('Z:\\project\\CM8\\vendor\\vendor\\transsion\\projects')
    expect(winJoin('Z:\\code-pull\\cpull-1\\vendor', 'vendor', 'transsion', 'projects', PROJECT))
      .toBe(`Z:\\code-pull\\cpull-1\\vendor\\vendor\\transsion\\projects\\${PROJECT}`)
  })

  it('matches PROJECT_FULL by project-code prefix and lists all dirs', () => {
    const neu = tempDir('pp-new-')
    const old = tempDir('pp-old-')
    populateVendorTree(neu, 'new', ['cm8_foo'])
    populateVendorTree(old, 'old')

    const result = parsePathParams({
      project_code: 'LK7K',
      OLD_VENDOR_ROOT: old,
      NEW_VENDOR_ROOT: neu.replace(/\\/g, '/'),
    })
    const fields = fieldMap(result)
    const full = fields.get('PROJECT_FULL')!
    expect(full.ok).toBe(true)
    expect(full.value).toBe(PROJECT)
    expect(full.options).toEqual(['cm8_foo', PROJECT].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' })))
    expect(fields.get('SOC_PLATFROM')?.value).toBe('mt6858')
    expect(fields.get('NEW_KERNEL_VERSION')?.value).toBe('6.12')
    expect(fields.get('OLD_KERNEL_VERSION')?.value).toBe('6.12')
    expect(fields.get('NEW_PROJECTS_ROOT')?.ok).toBe(true)
    expect(fields.get('NEW_KERNEL_DWS_PATH')?.ok).toBe(true)
    expect(fields.get('NEW_KERNEL_PROJECT_DTS_PATH')?.ok).toBe(true)
    expect(fields.get('NEW_KO_PACK_SOC_PATH')?.ok).toBe(true)
    expect(result.fields.every(f => f.key)).toBe(true)
    expect(result.fields.map(f => f.key)).toContain('NEW_KO_PACK_SOC_PATH')
  })

  it('marks PROJECT_FULL failed without default when no similar dir, but keeps options', () => {
    const neu = tempDir('pp-nomatch-')
    const old = tempDir('pp-nomatch-old-')
    populateVendorTree(neu, 'new', ['cm8_foo'])
    mkdirSync(join(old, 'vendor', 'transsion', 'projects'), { recursive: true })

    const result = parsePathParams({
      project_code: 'ZZZ',
      OLD_VENDOR_ROOT: old,
      NEW_VENDOR_ROOT: neu,
    })
    const full = fieldMap(result).get('PROJECT_FULL')!
    expect(full.ok).toBe(false)
    expect(full.value).toBe('')
    expect(full.options?.length).toBeGreaterThan(0)
    expect(fieldMap(result).get('NEW_PROJECTS_ROOT')?.error).toMatch(/PROJECT_FULL/)
  })

  it('leaves missing path empty and ok=false', () => {
    const neu = tempDir('pp-miss-new-')
    const old = tempDir('pp-miss-old-')
    populateVendorTree(neu, 'new')
    populateVendorTree(old, 'old')
    rmSync(join(old, 'vendor', 'mediatek', 'proprietary', 'tools', 'dct', 'dws', SOC, `${PROJECT}.dws`))

    const result = parsePathParams({
      project_code: 'LK7K',
      OLD_VENDOR_ROOT: old,
      NEW_VENDOR_ROOT: neu,
    })
    const dws = fieldMap(result).get('OLD_KERNEL_DWS_PATH')!
    expect(dws.ok).toBe(false)
    expect(dws.value).toBe('')
    expect(dws.error).toMatch(/不存在/)
  })

  it('registry add/remove changes output keys', () => {
    const keys = parsePathParams({
      project_code: 'X',
      OLD_VENDOR_ROOT: 'Z:\\missing-old',
      NEW_VENDOR_ROOT: 'Z:\\missing-new',
    }).fields.map(f => f.key)
    expect(keys).toContain('SOC_PLATFROM')
    expect(keys).toContain('PROJECT_FULL')

    const without = PATH_PARAM_FIELDS.filter(f => f.key !== 'SOC_PLATFROM')
    const next = parsePathParams({
      project_code: 'X',
      OLD_VENDOR_ROOT: 'Z:\\missing-old',
      NEW_VENDOR_ROOT: 'Z:\\missing-new',
    }, without).fields.map(f => f.key)
    expect(next).not.toContain('SOC_PLATFROM')
    expect(next).toContain('PROJECT_FULL')
  })

  it('persists path_params on createRun', () => {
    const pipelineDir = tempDir('pp-store-')
    process.env.TAHP_ADAPT_PIPELINE_DIR = pipelineDir
    const neu = tempDir('pp-store-new-')
    const old = tempDir('pp-store-old-')
    populateVendorTree(neu, 'new')
    populateVendorTree(old, 'old')

    const parsed = parsePathParams({
      project_code: 'LK7K',
      OLD_VENDOR_ROOT: old,
      NEW_VENDOR_ROOT: neu,
      NEW_SYSTEM_ROOT: 'Z:\\project\\CM8\\system',
      NEW_TRSYSTEM_ROOT: 'Z:\\project\\trsys',
    })
    const run = createRun({
      project_code: 'LK7K',
      build_context: { mapped_root: 'Z:\\', workspace: 'ws', variant: 'userdebug' },
      path_params: parsed,
    })
    const loaded = getRun(run.run_id)
    expect(loaded?.path_params?.inputs.NEW_SYSTEM_ROOT).toBe('Z:\\project\\CM8\\system')
    expect(loaded?.path_params?.inputs.NEW_TRSYSTEM_ROOT).toBe('Z:\\project\\trsys')
    expect(loaded?.path_params?.fields.find(f => f.key === 'PROJECT_FULL')?.value).toBe(PROJECT)
  })

  it('flattenPathParams prefers fields.value including failed-but-overridden', () => {
    const flat = flattenPathParams({
      inputs: {
        project_code: 'LK7K',
        OLD_VENDOR_ROOT: 'Z:\\old\\vendor',
        NEW_VENDOR_ROOT: 'Z:\\new\\vendor',
        NEW_SYSTEM_ROOT: 'Z:\\sys',
        NEW_TRSYSTEM_ROOT: 'Z:\\trsys',
      },
      fields: [
        { key: 'PROJECT_FULL', label: 'PROJECT_FULL', kind: 'select', ok: true, value: 'lk7k_h582', parsed_value: 'lk7k_h582' },
        { key: 'OLD_KERNEL_DWS_PATH', label: 'OLD_KERNEL_DWS_PATH', kind: 'text', ok: false, value: 'Z:\\manual\\a.dws', error: '文件不存在' },
      ],
      parsed_at: '2026-01-01T00:00:00.000Z',
    })
    expect(flat.formData.NEW_VENDOR_ROOT).toBe('Z:\\new\\vendor')
    expect(flat.formData.NEW_SYSTEM_ROOT).toBe('Z:\\sys')
    expect(flat.formData.NEW_TRSYSTEM_ROOT).toBe('Z:\\trsys')
    expect(flat.formData.PROJECT_FULL).toBe('lk7k_h582')
    expect(flat.formData.OLD_KERNEL_DWS_PATH).toBe('Z:\\manual\\a.dws')
  })
})
