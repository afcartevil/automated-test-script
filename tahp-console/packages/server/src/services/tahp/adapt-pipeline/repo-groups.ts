/**
 * 根据变更文件的绝对路径识别 git 仓，并按仓分组（审核选仓 / 拆 CR）
 */
import { execFileSync } from 'child_process'
import { dirname, normalize } from 'path'
import { isAbsFilePath } from './workspace-changed-files'

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

function lastSegment(p: string): string {
  const parts = p.replace(/\\/g, '/').split('/').filter(Boolean)
  return parts[parts.length - 1] || p
}

/** 从文件绝对路径向上找 git 仓根；找不到则退回文件所在目录 */
export function resolveRepoForFile(file: string): string {
  const abs = normalize(file)
  let dir = dirname(abs)
  for (let i = 0; i < 48; i++) {
    const root = tryGitRoot(dir)
    if (root) return normalize(root)
    const parent = dirname(dir)
    if (parent === dir) break
    dir = parent
  }
  return dirname(normalize(abs))
}

export function groupChangedFilesByRepo(
  domains: Array<{ domain_id: string; changed_files?: string[]; enabled?: boolean; status?: string }>,
): RepoChangeGroup[] {
  const map = new Map<string, RepoChangeGroup>()

  for (const d of domains) {
    if (d.enabled === false) continue
    for (const f of d.changed_files ?? []) {
      if (!f?.trim() || !isAbsFilePath(f.trim())) continue
      const repo = resolveRepoForFile(f)
      let g = map.get(repo)
      if (!g) {
        g = { repo, repo_label: lastSegment(repo), files: [], domain_ids: [] }
        map.set(repo, g)
      }
      if (!g.files.includes(f)) g.files.push(f)
      if (!g.domain_ids.includes(d.domain_id)) g.domain_ids.push(d.domain_id)
    }
  }

  return [...map.values()].sort((a, b) => a.repo_label.localeCompare(b.repo_label))
}

export function filterFilesBySelectedRepos(
  files: string[],
  selectedRepos: string[],
): string[] {
  if (!selectedRepos.length) return files
  const selected = new Set(selectedRepos.map(r => normalize(r).toLowerCase()))
  return files.filter(f => {
    if (!f?.trim()) return false
    const repo = resolveRepoForFile(f)
    return selected.has(normalize(repo).toLowerCase())
  })
}

/** 勾选入库仓库后，只保留选中仓（路径大小写不敏感） */
export function filterRepoGroupsBySelection(
  groups: RepoChangeGroup[],
  selectedRepos: string[] | undefined,
): RepoChangeGroup[] {
  if (!selectedRepos?.length) return groups
  const selected = new Set(selectedRepos.map(r => normalize(r).toLowerCase()))
  return groups.filter(g => selected.has(normalize(g.repo).toLowerCase()))
}
