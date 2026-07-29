import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mkdtempSync, writeFileSync, rmSync, mkdirSync } from 'node:fs'
import { join } from 'node:path'
import { execFileSync } from 'node:child_process'
import { tmpdir } from 'node:os'
import { takeSnapshot, diffSnapshots, fingerprint } from '../../packages/server/src/services/tahp/git-snapshot'

let repoDir: string

function git(...args: string[]) {
  execFileSync('git', args, { cwd: repoDir, windowsHide: true })
}

beforeEach(() => {
  repoDir = mkdtempSync(join(tmpdir(), 'git-snap-'))
  git('init')
  git('config', 'user.email', 'test@test.com')
  git('config', 'user.name', 'Test')
  writeFileSync(join(repoDir, 'initial.txt'), 'hello')
  git('add', '.')
  git('commit', '-m', 'init')
})

afterEach(() => {
  rmSync(repoDir, { recursive: true, force: true })
})

describe('takeSnapshot', () => {
  it('returns empty files for clean repo', async () => {
    const snaps = await takeSnapshot([repoDir])
    expect(snaps).toHaveLength(1)
    expect(snaps[0].files).toHaveLength(0)
    expect(snaps[0].repo).toBe(repoDir)
  })

  it('detects new file', async () => {
    writeFileSync(join(repoDir, 'new.txt'), 'new')
    const snaps = await takeSnapshot([repoDir])
    expect(snaps[0].files.length).toBeGreaterThan(0)
    expect(snaps[0].files.some(f => f.path === 'new.txt')).toBe(true)
  })

  it('detects modified file', async () => {
    writeFileSync(join(repoDir, 'initial.txt'), 'modified')
    const snaps = await takeSnapshot([repoDir])
    expect(snaps[0].files.some(f => f.path === 'initial.txt')).toBe(true)
  })

  it('gracefully handles non-git directory', async () => {
    const nonGit = mkdtempSync(join(tmpdir(), 'non-git-'))
    try {
      const snaps = await takeSnapshot([nonGit])
      expect(snaps).toHaveLength(1)
      expect(snaps[0].files).toHaveLength(0)
    } finally {
      rmSync(nonGit, { recursive: true, force: true })
    }
  })
})

describe('diffSnapshots', () => {
  it('returns empty for identical snapshots', async () => {
    writeFileSync(join(repoDir, 'a.txt'), 'a')
    const snap = await takeSnapshot([repoDir])
    expect(diffSnapshots(snap, snap)).toEqual([])
  })

  it('detects new file added after first snapshot', async () => {
    const before = await takeSnapshot([repoDir])
    writeFileSync(join(repoDir, 'added.txt'), 'x')
    const after = await takeSnapshot([repoDir])
    const diff = diffSnapshots(before, after)
    expect(diff).toContain('added.txt')
  })

  it('detects file removed after first snapshot', async () => {
    writeFileSync(join(repoDir, 'temp.txt'), 'temp')
    const before = await takeSnapshot([repoDir])
    rmSync(join(repoDir, 'temp.txt'))
    const after = await takeSnapshot([repoDir])
    const diff = diffSnapshots(before, after)
    expect(diff).toContain('temp.txt')
  })
})

describe('fingerprint', () => {
  it('is stable for same content', async () => {
    writeFileSync(join(repoDir, 'f.txt'), 'content')
    const snap = await takeSnapshot([repoDir])
    expect(fingerprint(snap)).toBe(fingerprint(snap))
  })

  it('changes when file changes', async () => {
    writeFileSync(join(repoDir, 'f.txt'), 'v1')
    const snap1 = await takeSnapshot([repoDir])
    const fp1 = fingerprint(snap1)

    writeFileSync(join(repoDir, 'f.txt'), 'v2')
    git('add', 'f.txt')
    const snap2 = await takeSnapshot([repoDir])
    const fp2 = fingerprint(snap2)

    expect(fp1).not.toBe(fp2)
  })

  it('is independent of snapshot order', async () => {
    writeFileSync(join(repoDir, 'a.txt'), 'a')
    writeFileSync(join(repoDir, 'b.txt'), 'b')
    const snap = await takeSnapshot([repoDir])
    const reversed = [...snap].map(s => ({ ...s, files: [...s.files].reverse() }))
    expect(fingerprint(snap)).toBe(fingerprint(reversed))
  })
})
