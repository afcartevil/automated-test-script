/**
 * 约束文件系统 — 读写 TAHP constraints/ 与 playbooks/ YAML.
 *   - 严格限制在 tahpPaths.constraintsDir / playbooksDir 之内 (防 path traversal)
 *   - 写入前调用 scripts/validate_constraints.py 做 dry-run
 */
import { readFile, writeFile, readdir, stat } from 'fs/promises'
import { existsSync } from 'fs'
import { join, relative, resolve, sep } from 'path'
import { tahpPaths } from './paths'
import { runPythonScript } from './scripts-runner'
import { logger } from '../logger'

export interface ModuleInfo {
  name: string
  displayName?: string
  domain?: string
  owner?: string
  domains: { domain: string; file: string }[]
  hasModuleYaml: boolean
}

function ensureInside(base: string, candidate: string): string {
  const abs = resolve(candidate)
  const rel = relative(resolve(base), abs)
  if (rel.startsWith('..') || rel.includes(`..${sep}`)) {
    throw new Error(`路径越界: ${candidate}`)
  }
  return abs
}

const DOMAIN_FILES = [
  'bug-analysis.yaml',
  'code-adaptation.yaml',
  'version-adaptation.yaml',
  'carrier-porting.yaml',
]

const DOMAIN_KEY_BY_FILE: Record<string, string> = {
  'bug-analysis.yaml': 'bug_analysis',
  'code-adaptation.yaml': 'code_adaptation',
  'version-adaptation.yaml': 'version_adaptation',
  'carrier-porting.yaml': 'carrier_porting',
}

export async function listModules(): Promise<ModuleInfo[]> {
  const dir = tahpPaths.constraintsDir
  if (!existsSync(dir)) return []
  const entries = await readdir(dir, { withFileTypes: true })
  const result: ModuleInfo[] = []
  for (const e of entries) {
    if (!e.isDirectory()) continue
    if (e.name === 'shared') continue
    const moduleDir = join(dir, e.name)
    const moduleYaml = join(moduleDir, 'module.yaml')
    const hasModuleYaml = existsSync(moduleYaml)
    const domains: { domain: string; file: string }[] = []
    for (const f of DOMAIN_FILES) {
      if (existsSync(join(moduleDir, f))) {
        domains.push({ domain: DOMAIN_KEY_BY_FILE[f], file: f })
      }
    }
    result.push({ name: e.name, domains, hasModuleYaml })
  }
  return result
}

export async function readConstraintFile(moduleName: string, fileName: string): Promise<string> {
  const moduleDir = join(tahpPaths.constraintsDir, moduleName)
  const target = ensureInside(moduleDir, join(moduleDir, fileName))
  if (!existsSync(target)) throw new Error(`约束文件不存在: ${moduleName}/${fileName}`)
  return readFile(target, 'utf-8')
}

export interface ValidateResult {
  ok: boolean
  stdout: string
  stderr: string
  exitCode: number
}

export async function validateConstraintContent(moduleName: string, fileName: string, content: string): Promise<ValidateResult> {
  // 落临时文件 + 调用 validate_constraints.py
  const moduleDir = join(tahpPaths.constraintsDir, moduleName)
  const tmpFile = join(moduleDir, `.${fileName}.tahp-console.tmp`)
  await writeFile(tmpFile, content, 'utf-8')
  try {
    const result = await runPythonScript('validate_constraints.py', [tmpFile, '--strict'], { capture: true })
    return {
      ok: result.exitCode === 0,
      stdout: result.stdout,
      stderr: result.stderr,
      exitCode: result.exitCode,
    }
  } finally {
    try { (await import('fs/promises')).unlink(tmpFile) } catch {}
  }
}

export async function writeConstraintFile(moduleName: string, fileName: string, content: string): Promise<void> {
  const moduleDir = join(tahpPaths.constraintsDir, moduleName)
  const target = ensureInside(moduleDir, join(moduleDir, fileName))
  await writeFile(target, content, 'utf-8')
  logger.info({ moduleName, fileName, size: content.length }, '[tahp] constraint saved')
}

export async function listPlaybooks(): Promise<{ name: string; file: string; size: number }[]> {
  const dir = tahpPaths.playbooksDir
  if (!existsSync(dir)) return []
  const entries = await readdir(dir, { withFileTypes: true })
  const items: { name: string; file: string; size: number }[] = []
  for (const e of entries) {
    if (!e.isFile() || !e.name.endsWith('.yaml')) continue
    const fullPath = join(dir, e.name)
    const s = await stat(fullPath)
    items.push({ name: e.name.replace(/\.yaml$/, ''), file: e.name, size: s.size })
  }
  return items.sort((a, b) => a.name.localeCompare(b.name))
}

export async function readPlaybook(file: string): Promise<string> {
  const target = ensureInside(tahpPaths.playbooksDir, join(tahpPaths.playbooksDir, file))
  if (!existsSync(target)) throw new Error(`Playbook 不存在: ${file}`)
  return readFile(target, 'utf-8')
}
