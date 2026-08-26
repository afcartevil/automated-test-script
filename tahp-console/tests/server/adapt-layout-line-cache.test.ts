import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

function fakeProjectRoot(): string {
  const root = mkdtempSync(join(tmpdir(), 'line-cache-'))
  mkdirSync(join(root, 'skills', '.claude', 'skills', 'jira-ops'), { recursive: true })
  writeFileSync(join(root, 'skills', '.claude', 'skills', 'jira-ops', 'SKILL.md'), '# jira-ops\n', 'utf-8')
  return root
}

describe('adapt-layout line-cache V13', () => {
  let tempRoot = ''
  const prevEnv = process.env.TAHP_PROJECT_ROOT

  beforeEach(() => {
    tempRoot = fakeProjectRoot()
    process.env.TAHP_PROJECT_ROOT = tempRoot
  })

  afterEach(() => {
    if (prevEnv === undefined) delete process.env.TAHP_PROJECT_ROOT
    else process.env.TAHP_PROJECT_ROOT = prevEnv
    if (tempRoot && existsSync(tempRoot)) rmSync(tempRoot, { recursive: true, force: true })
  })

  it('keeps previous cache when pull throws', async () => {
    const { pullOrReadLineLayouts, writeLineLayoutCache, readLineLayoutCache } = await import(
      '../../packages/server/src/services/tahp/adapt-layout/line-cache'
    )
    await writeLineLayoutCache({
      updated_at: '2026-08-26T00:00:00.000Z',
      from_center: true,
      lines: [{
        line_id: 'a16-to-a17',
        from_os: '16',
        to_os: '17',
        domains: [{
          workspace_id: 'adapt-debug',
          domain_id: 'tp',
          revision: 2,
          fields: [{ key: 'x_keep', label: '保留', type: 'text', required: false }],
          related_skills: [],
        }],
      }],
    })

    const result = await pullOrReadLineLayouts(async () => {
      throw new Error('network down')
    })
    expect(result.pulled).toBe(false)
    expect(result.error).toMatch(/network down/)
    expect(result.cache?.lines[0].line_id).toBe('a16-to-a17')
    expect(result.cache?.lines[0].domains[0].fields[0].key).toBe('x_keep')
    const disk = await readLineLayoutCache()
    expect(disk?.lines[0].domains[0].fields[0].key).toBe('x_keep')
  })

  it('does not wipe cache when center returns malformed payload', async () => {
    const { pullOrReadLineLayouts, writeLineLayoutCache } = await import(
      '../../packages/server/src/services/tahp/adapt-layout/line-cache'
    )
    await writeLineLayoutCache({
      updated_at: '2026-08-26T00:00:00.000Z',
      from_center: true,
      lines: [{ line_id: 'a16-to-a17', from_os: '16', to_os: '17', domains: [] }],
    })
    const result = await pullOrReadLineLayouts(async () => ({ ok: true }))
    expect(result.pulled).toBe(false)
    expect(result.cache?.lines[0].line_id).toBe('a16-to-a17')
  })

  it('writes pulled lines on success', async () => {
    const { pullOrReadLineLayouts, readLineLayoutCache } = await import(
      '../../packages/server/src/services/tahp/adapt-layout/line-cache'
    )
    const result = await pullOrReadLineLayouts(async () => ({
      lines: [{
        line_id: 'a17-to-a18',
        from_os: '17',
        to_os: '18',
        domains: [{
          workspace_id: 'adapt-debug',
          domain_id: 'tp',
          revision: 1,
          fields: [{ key: 'debug_project', label: '调试项目名', type: 'text', required: true }],
          related_skills: ['tp-adapt-bringup'],
        }],
      }],
    }))
    expect(result.pulled).toBe(true)
    expect(result.cache?.lines[0].line_id).toBe('a17-to-a18')
    const disk = await readLineLayoutCache()
    expect(disk?.from_center).toBe(true)
    expect(disk?.lines[0].domains[0].fields[0].key).toBe('debug_project')
  })
})
