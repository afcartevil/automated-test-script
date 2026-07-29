import { execFile } from 'node:child_process'
import { createHash } from 'node:crypto'
import { promisify } from 'node:util'

const execFileAsync = promisify(execFile)

export interface GitFileEntry {
  path: string
  /** XY status from `git status --porcelain` e.g. 'M ', ' M', 'A ', '??' */
  status: string
}

export interface GitSnapshot {
  repo: string
  files: GitFileEntry[]
  takenAt: string
}

/**
 * Take a snapshot of uncommitted changes in one or more git repos.
 * Gracefully returns empty snapshot if git is unavailable.
 */
export async function takeSnapshot(roots: string[]): Promise<GitSnapshot[]> {
  const results: GitSnapshot[] = []
  for (const root of roots) {
    try {
      const { stdout } = await execFileAsync('git', ['status', '--porcelain'], {
        cwd: root,
        timeout: 15_000,
        windowsHide: true,
      })
      const files: GitFileEntry[] = stdout
        .split('\n')
        .filter(l => l.length >= 4)
        .map(l => ({
          status: l.substring(0, 2),
          path: l.substring(3),
        }))
        .sort((a, b) => a.path.localeCompare(b.path))

      results.push({ repo: root, files, takenAt: new Date().toISOString() })
    } catch {
      results.push({ repo: root, files: [], takenAt: new Date().toISOString() })
    }
  }
  return results
}

/**
 * Return file paths that differ between two snapshot sets.
 * Comparison is by repo + path + status.
 */
export function diffSnapshots(before: GitSnapshot[], after: GitSnapshot[]): string[] {
  const beforeMap = new Map<string, string>()
  for (const snap of before) {
    for (const f of snap.files) {
      beforeMap.set(`${snap.repo}\0${f.path}`, f.status)
    }
  }

  const changed: string[] = []
  const seen = new Set<string>()

  for (const snap of after) {
    for (const f of snap.files) {
      const key = `${snap.repo}\0${f.path}`
      seen.add(key)
      const prev = beforeMap.get(key)
      if (prev !== f.status) {
        changed.push(f.path)
      }
    }
  }

  for (const [key] of beforeMap) {
    if (!seen.has(key)) {
      const path = key.split('\0')[1]
      changed.push(path)
    }
  }

  return [...new Set(changed)].sort()
}

/**
 * Stable hash of snapshot content. Files are sorted before hashing
 * so traversal order doesn't affect the result.
 */
export function fingerprint(snapshots: GitSnapshot[]): string {
  const hash = createHash('sha256')
  const sorted = [...snapshots].sort((a, b) => a.repo.localeCompare(b.repo))
  for (const snap of sorted) {
    hash.update(snap.repo)
    hash.update('\n')
    const files = [...snap.files].sort((a, b) => a.path.localeCompare(b.path))
    for (const f of files) {
      hash.update(`${f.status} ${f.path}\n`)
    }
  }
  return hash.digest('hex')
}
