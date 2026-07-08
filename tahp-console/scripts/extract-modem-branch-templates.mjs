import fs from 'fs'
import path from 'path'
import os from 'os'
import crypto from 'crypto'
import { spawnSync } from 'child_process'

function nowIso() {
  return new Date().toISOString()
}

function ownerFromEnv() {
  try {
    return os.userInfo().username?.trim() || process.env.USERNAME?.trim() || 'unknown'
  } catch {
    return process.env.USERNAME?.trim() || 'unknown'
  }
}

function ownerKey(owner) {
  return String(owner || 'unknown').replace(/[^\w.-]+/g, '_')
}

function parseArgs(argv) {
  const args = {}
  for (let i = 0; i < argv.length; i += 1) {
    const key = argv[i]
    if (!key || !key.startsWith('--')) continue
    const name = key.slice(2)
    const next = argv[i + 1]
    if (!next || next.startsWith('--')) {
      args[name] = true
      continue
    }
    args[name] = next
    i += 1
  }
  return args
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true })
}

function readJson(filePath, fallback) {
  try {
    if (!fs.existsSync(filePath)) return fallback
    return JSON.parse(fs.readFileSync(filePath, 'utf-8'))
  } catch {
    return fallback
  }
}

function writeJson(filePath, value) {
  ensureDir(path.dirname(filePath))
  fs.writeFileSync(filePath, JSON.stringify(value, null, 2), 'utf-8')
}

function git(repoPath, args) {
  const result = spawnSync('git', ['-C', repoPath, ...args], {
    encoding: 'utf-8',
    windowsHide: true,
  })
  return {
    ok: result.status === 0,
    status: result.status ?? -1,
    stdout: String(result.stdout || '').trim(),
    stderr: String(result.stderr || '').trim(),
  }
}

function parseTosVersionToken(branch) {
  const match = String(branch || '').match(/^tOS\s*([0-9]+(?:\.[0-9]+){1,3})/i)
  if (!match) return null
  const full = `tOS${match[1]}`
  const parts = match[1].split('.').map(part => Number(part) || 0)
  const major = parts[0] ?? 0
  const minor = parts[1] ?? 0
  const patch = parts[2] ?? 0
  const key = `tOS${major}.${minor}`
  return { full, key, major, minor, patch }
}

function compareTosToken(left, right) {
  if (!left && !right) return 0
  if (!left) return -1
  if (!right) return 1
  if (left.major !== right.major) return left.major - right.major
  if (left.minor !== right.minor) return left.minor - right.minor
  return left.patch - right.patch
}

function isAtLeastBaseline(token, baseline) {
  return compareTosToken(token, baseline) >= 0
}

function uniqueByKey(items, toKey) {
  const map = new Map()
  for (const item of items) {
    const key = toKey(item)
    if (!key) continue
    if (!map.has(key)) map.set(key, item)
  }
  return Array.from(map.values())
}

function pickOne(values) {
  if (!values.length) return { value: undefined, ambiguous: false }
  if (values.length === 1) return { value: values[0], ambiguous: false }
  return { value: undefined, ambiguous: true }
}

function listRemoteBranches(repoPath, remote) {
  const result = git(repoPath, ['ls-remote', '--heads', remote])
  if (!result.ok) return { branches: [], error: result.stderr || `git_failed:${result.status}` }
  const branches = result.stdout
    .split(/\r?\n/g)
    .map(line => line.trim())
    .filter(Boolean)
    .map(line => line.split(/\s+/g)[1] || '')
    .map(ref => ref.replace(/^refs\/heads\//, ''))
    .filter(Boolean)
  return { branches: Array.from(new Set(branches)).sort(), error: '' }
}

function pickTrunkBranch(branches) {
  const candidates = branches.filter(name => name.endsWith('_common'))
  const picked = pickOne(candidates)
  return { trunkBranch: picked.value, ambiguous: picked.ambiguous }
}

function pickMpBranches(branches, baselineToken) {
  const candidates = branches.filter(name => /^tOS[0-9]+\.[0-9]+/i.test(name) && !/_node$/i.test(name))
  const withTokens = candidates
    .map(name => ({ name, token: parseTosVersionToken(name) }))
    .filter(item => item.token && isAtLeastBaseline(item.token, baselineToken))
  const releaseFirst = withTokens.filter(item => /release/i.test(item.name))
  const selected = releaseFirst.length ? releaseFirst : withTokens
  return selected
    .sort((a, b) => compareTosToken(a.token, b.token))
    .map(item => ({ name: item.name, token: item.token }))
}

function pickMpNodeBranch(branches, mpBranchName, token) {
  const suffixCandidates = branches.filter(name => /_node$/i.test(name))
  const fullVersion = token?.full || ''
  const keyVersion = token?.key || ''
  const strict = fullVersion
    ? suffixCandidates.filter(name => name.includes(fullVersion))
    : []
  const relaxed = keyVersion
    ? suffixCandidates.filter(name => name.startsWith(keyVersion) || name.includes(keyVersion))
    : []
  const best = strict.length ? strict : relaxed
  const picked = pickOne(best.sort())
  if (picked.value) return { nodeBranch: picked.value, ambiguous: picked.ambiguous, source: 'matched' }
  return { nodeBranch: 'master', ambiguous: false, source: 'fallback_master' }
}

function tosKeyTokenToComparable(tosKey) {
  const match = String(tosKey || '').match(/^tOS\s*([0-9]+)\.([0-9]+)/i)
  if (!match) return null
  return { major: Number(match[1]) || 0, minor: Number(match[2]) || 0, patch: 0 }
}

function main() {
  const args = parseArgs(process.argv.slice(2))
  const owner = String(args.owner || ownerFromEnv())
  const remote = String(args.remote || 'origin')
  const baselineRaw = String(args.baseline || 'tOS16.3')
  const baselineToken = parseTosVersionToken(baselineRaw) || { full: baselineRaw, key: baselineRaw, major: 16, minor: 3, patch: 0 }

  const repoRoot = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..')
  const serverDataDir = path.resolve(repoRoot, 'packages', 'server', 'data')
  const modemPatchDir = path.resolve(serverDataDir, 'modem-patch')
  const repoProfilesFile = path.resolve(modemPatchDir, 'repos', `${ownerKey(owner)}.json`)
  const branchTemplatesFile = path.resolve(modemPatchDir, 'branch-templates', `${ownerKey(owner)}.json`)

  const repos = readJson(repoProfilesFile, [])
  if (!Array.isArray(repos) || !repos.length) {
    process.stdout.write(`repo_profiles_not_found: ${repoProfilesFile}\n`)
    process.exitCode = 1
    return
  }

  const existing = readJson(branchTemplatesFile, [])
  const preserved = Array.isArray(existing)
    ? existing.filter(item => {
      const tos = tosKeyTokenToComparable(item?.tos)
      return !tos || compareTosToken(tos, baselineToken) < 0
    })
    : []

  const generated = []
  const warnings = []
  const updatedAt = nowIso()

  for (const repo of repos) {
    const localPath = String(repo?.localPath || '').trim()
    const platform = String(repo?.platform || repo?.label || '').trim()
    if (!localPath || !platform) continue

    const gitCheck = git(localPath, ['rev-parse', '--is-inside-work-tree'])
    if (!gitCheck.ok) {
      warnings.push({ platform, localPath, code: 'not_git_repo', detail: gitCheck.stderr || `git_failed:${gitCheck.status}` })
      continue
    }

    const remoteBranchesResult = listRemoteBranches(localPath, remote)
    if (remoteBranchesResult.error) {
      warnings.push({ platform, localPath, code: 'list_remote_failed', detail: remoteBranchesResult.error })
      continue
    }
    const branches = remoteBranchesResult.branches

    const trunkPicked = pickTrunkBranch(branches)
    if (!trunkPicked.trunkBranch) {
      warnings.push({ platform, localPath, code: trunkPicked.ambiguous ? 'trunk_ambiguous' : 'trunk_not_found', detail: '' })
      continue
    }

    const mpBranches = pickMpBranches(branches, baselineToken)
    if (!mpBranches.length) {
      warnings.push({ platform, localPath, code: 'mp_not_found', detail: '' })
      continue
    }

    const nodeBranch = String(repo?.defaultNodeBranch || 'master').trim() || 'master'
    const perTos = uniqueByKey(mpBranches, item => item.token?.key || '')
    for (const mp of perTos) {
      const token = mp.token
      if (!token) continue
      const mpNodePicked = pickMpNodeBranch(branches, mp.name, token)
      if (mpNodePicked.ambiguous) {
        warnings.push({ platform, localPath, code: 'mp_node_ambiguous', detail: `${token.full}` })
      }
      generated.push({
        templateId: crypto.randomBytes(8).toString('hex'),
        owner,
        tos: token.key,
        platform,
        nodeBranch,
        trunkBranch: trunkPicked.trunkBranch,
        mpBranch: mp.name,
        mpNodeBranch: mpNodePicked.nodeBranch,
        sourceFile: localPath,
        sourceSheet: remote,
        updatedAt,
      })
    }
  }

  const merged = preserved.concat(generated)
  writeJson(branchTemplatesFile, merged)

  process.stdout.write(`owner=${owner}\n`)
  process.stdout.write(`repos=${repos.length}\n`)
  process.stdout.write(`preserved=${preserved.length}\n`)
  process.stdout.write(`generated=${generated.length}\n`)
  process.stdout.write(`output=${branchTemplatesFile}\n`)
  if (warnings.length) {
    process.stdout.write(`warnings=${warnings.length}\n`)
    for (const item of warnings.slice(0, 50)) {
      process.stdout.write(`${item.code}\t${item.platform}\t${item.localPath}\t${item.detail || ''}\n`)
    }
    if (warnings.length > 50) {
      process.stdout.write(`warnings_truncated=${warnings.length - 50}\n`)
    }
  }
}

main()
