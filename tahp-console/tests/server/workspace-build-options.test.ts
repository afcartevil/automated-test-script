import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { existsSync, mkdirSync, writeFileSync, rmSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

const execFileMock = vi.fn()

vi.mock('node:child_process', async () => {
  const actual = await vi.importActual<typeof import('node:child_process')>('node:child_process')
  return {
    ...actual,
    execFile: (...args: unknown[]) => execFileMock(...args),
  }
})

describe('workspace-build-options', () => {
  let base = ''

  beforeEach(() => {
    execFileMock.mockReset()
    base = join(tmpdir(), `tahp-wbo-${Date.now()}-${Math.random().toString(16).slice(2)}`)
    mkdirSync(base, { recursive: true })
  })

  afterEach(() => {
    if (base && existsSync(base)) rmSync(base, { recursive: true, force: true })
  })

  it('returns fallback when mapped_root/workspace empty', async () => {
    const {
      resolveWorkspaceBuildOptions,
      listHarnessMarketPresets,
    } = await import('../../packages/server/src/services/tahp/adapt-pipeline/workspace-build-options')

    const res = await resolveWorkspaceBuildOptions('', '')
    expect(res.source).toBe('fallback')
    expect(res.components).toEqual([])
    expect(res.markets).toEqual(listHarnessMarketPresets())
    expect(res.warning).toMatch(/mapped_root/)
  })

  it('parses pack.json + merges tr* from comp_dict when harness fails', async () => {
    execFileMock.mockImplementation((_file: unknown, _args: unknown, optsOrCb: unknown, maybeCb?: unknown) => {
      const cb = typeof optsOrCb === 'function' ? optsOrCb : maybeCb
      if (typeof cb === 'function') (cb as (e: Error, out: string, err: string) => void)(new Error('harness missing'), '', '')
      return {} as never
    })

    const ws = 'project/km9'
    const root = join(base, ws)
    mkdirSync(join(root, '.pipe'), { recursive: true })
    writeFileSync(join(root, 'pack.json'), JSON.stringify({
      project_name: 'KM9',
      platform: 'mtk',
      markets: ['OP', 'IN'],
      part_conf: [
        { component: 'sys' },
        { component: 'hal' },
        { component: 'krn' },
      ],
    }))
    writeFileSync(join(root, '.pipe', 'info.json'), JSON.stringify({
      comp_dict: { sys: 'a', hal: 'b', krn: 'c', trprd: 'd', trreg: 'e' },
    }))

    const { resolveWorkspaceBuildOptions } = await import(
      '../../packages/server/src/services/tahp/adapt-pipeline/workspace-build-options'
    )
    const res = await resolveWorkspaceBuildOptions(base, ws)
    expect(res.source).toBe('pack_json')
    expect(res.components).toEqual(expect.arrayContaining(['sys', 'hal', 'krn', 'trprd', 'trreg']))
    expect(res.markets).toEqual(['in', 'op'])
    expect(res.recommended_markets).toEqual(['in', 'op'])
    expect(res.project_name).toBe('KM9')
  })

  it('prefers harness status and lowercases markets', async () => {
    execFileMock.mockImplementation((_file: unknown, _args: unknown, optsOrCb: unknown, maybeCb?: unknown) => {
      const cb = typeof optsOrCb === 'function' ? optsOrCb : maybeCb
      const stdout = JSON.stringify({
        status: 'ok',
        data: {
          components: ['sys', 'hal', 'krn', 'vext', 'odm'],
          markets: ['OP', 'EU', 'TR', 'IN'],
          platform: 'mtk',
          project_name: 'KM9',
          comp_dict: { trprd: 'x', trreg: 'y', sys: 'z' },
          pack_json_exists: true,
        },
      })
      if (typeof cb === 'function') (cb as (e: null, out: string, err: string) => void)(null, stdout, '')
      return {} as never
    })

    const { resolveWorkspaceBuildOptions } = await import(
      '../../packages/server/src/services/tahp/adapt-pipeline/workspace-build-options'
    )
    // 使用不存在的本地根，避免 harness mock 失败时回落到本机真实 pack.json
    const res = await resolveWorkspaceBuildOptions(join(base, 'no-pack-root'), 'project/km9')
    expect(res.source).toBe('harness_status')
    expect(res.components).toEqual(expect.arrayContaining(['sys', 'hal', 'krn', 'vext', 'odm', 'trprd', 'trreg']))
    expect(res.markets).toEqual(['eu', 'in', 'op', 'tr'])
    expect(res.recommended_components.length).toBeGreaterThan(0)
  })

  it('listHarnessMarketPresets exposes harness-supported markets', async () => {
    const { listHarnessMarketPresets } = await import(
      '../../packages/server/src/services/tahp/adapt-pipeline/workspace-build-options'
    )
    const presets = listHarnessMarketPresets()
    expect(presets).toEqual(expect.arrayContaining(['op', 'eu', 'in', 'tr', 'vn', 'id']))
    expect(presets.every(m => m === m.toLowerCase())).toBe(true)
  })
})
