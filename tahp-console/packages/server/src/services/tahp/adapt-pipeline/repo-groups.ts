/**
 * 将变更文件按 git 仓分组（用于审核选仓入库）
 */
import { execFileSync } from 'child_process'
import { existsSync } from 'fs'
import { dirname, isAbsolute, join, normalize, relative, sep } from 'path'

export interface RepoChangeGroup {
  repo: string
  repo_label: string
  files: string[]
  domain_ids: string[]
}

function tryGitRoot(dir: string): string | null {
  try {
    const out = execFileSync(
      'git',
      ['-c', 'safe.directory=*', 'rev-parse', '--show-toplevel'],
      { cwd: dir, encoding: 'utf-8', timeout: 8000, windowsHide: true },
    )
    const root = out.trim()
    return root || null
  } catch {
    return null
  }
}

function resolveFileAbs(mappedRoot: string, file: string): string {
  if (isAbsolute(file)) return normalize(file)
  return normalize(join(mappedRoot, file))
}

/** 自文件路径向上找 git 根；找不到则退回 mapped_root 下首段目录 */
export function resolveRepoForFile(mappedRoot: string, file: string): string {
  const abs = resolveFileAbs(mappedRoot, file)
  let dir = existsSync(abs) ? dirname(abs) : dirname(abs)
  for (let i = 0; i < 24; i++) {
    const root = tryGitRoot(dir)
    if (root) return normalize(root)
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }

  const rel = relative(mappedRoot, abs).replace(/\\/g, '/')
  const top = rel.split('/')[0]
  if (top && top !== '..' && top !== '.') {
    return normalize(join(mappedRoot, top))
  }
  return normalize(mappedRoot)
}

export function groupChangedFilesByRepo(
  mappedRoot: string,
  domains: Array<{ domain_id: string; changed_files?: string[]; enabled?: boolean; status?: string }>,
): RepoChangeGroup[] {
  const map = new Map<string, RepoChangeGroup>()
  const root = mappedRoot.trim()
  if (!root) return []

  for (const d of domains) {
    if (d.enabled === false) continue
    if (d.status && d.status !== 'done' && d.status !== 'pending') {
      // still include done domains primarily
    }
    for (const f of d.changed_files ?? []) {
      if (!f?.trim()) continue
      const repo = resolveRepoForFile(root, f)
      let g = map.get(repo)
      if (!g) {
        const label = relative(root, repo).replace(/\\/g, '/') || repo.split(/[/\\]/).pop() || repo
        g = { repo, repo_label: label, files: [], domain_ids: [] }
        map.set(repo, g)
      }
      if (!g.files.includes(f)) g.files.push(f)
      if (!g.domain_ids.includes(d.domain_id)) g.domain_ids.push(d.domain_id)
    }
  }

  return [...map.values()].sort((a, b) => a.repo_label.localeCompare(b.repo_label))
}

export function filterFilesBySelectedRepos(
  mappedRoot: string,
  files: string[],
  selectedRepos: string[],
): string[] {
  if (!selectedRepos.length) return files
  const selected = new Set(selectedRepos.map(r => normalize(r).toLowerCase()))
  return files.filter(f => {
    const repo = resolveRepoForFile(mappedRoot, f)
    return selected.has(normalize(repo).toLowerCase())
  })
}
