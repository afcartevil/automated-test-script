import { copyFile, mkdir, readdir, rm, stat } from 'fs/promises'
import { existsSync } from 'fs'
import { join, resolve } from 'path'
import { getActiveProfileDir } from './hermes-profile'
import { logger } from '../logger'
import { tahpPaths, hasTahpProject } from '../tahp/paths'

export interface SkillInjectionResult {
  sourceDir: string
  targetDir: string
  injected: string[]
  updated: string[]
  skipped: string[]
}

export class HermesSkillInjector {
  constructor(
    private readonly sourceDir = HermesSkillInjector.resolveSourceDir(),
    private readonly targetDir = join(getActiveProfileDir(), 'skills'),
  ) {}

  static resolveSourceDir(env: NodeJS.ProcessEnv = process.env, baseDir = __dirname): string {
    const override = env.HERMES_WEB_UI_SKILLS_DIR?.trim()
    if (override) return resolve(override)

    if (hasTahpProject()) {
      const tahpSkills = join(tahpPaths.projectRoot, 'skills', '.claude', 'skills')
      if (existsSync(tahpSkills)) return tahpSkills
    }

    const candidates = [
      // Production bundle: dist/server/index.js with dist/skills copied by build.
      resolve(baseDir, '../skills'),
      // Development/test: packages/server/src/services/hermes -> packages/skills.
      resolve(baseDir, '../../../../skills'),
      // Running from repository root without bundling.
      resolve(process.cwd(), 'packages/skills'),
    ]

    return candidates.find(candidate => existsSync(candidate)) || candidates[0]
  }

  async injectMissingSkills(): Promise<SkillInjectionResult> {
    const result: SkillInjectionResult = {
      sourceDir: this.sourceDir,
      targetDir: this.targetDir,
      injected: [],
      updated: [],
      skipped: [],
    }

    if (!await this.isDirectory(this.sourceDir)) {
      logger.debug('[skill-injector] no bundled skills directory at %s', this.sourceDir)
      return result
    }

    await mkdir(this.targetDir, { recursive: true })
    const entries = await readdir(this.sourceDir, { withFileTypes: true })
    for (const entry of entries) {
      if (!entry.isDirectory() || entry.name.startsWith('.')) continue
      const sourceSkillDir = join(this.sourceDir, entry.name)
      const targetSkillDir = join(this.targetDir, entry.name)
      const existed = existsSync(targetSkillDir)
      if (existed && !(await this.dirNeedsSync(sourceSkillDir, targetSkillDir))) {
        result.skipped.push(entry.name)
        continue
      }
      if (existed) {
        await rm(targetSkillDir, { recursive: true, force: true })
      }
      await this.copyDir(sourceSkillDir, targetSkillDir)
      if (existed) result.updated.push(entry.name)
      else result.injected.push(entry.name)
    }

    if (result.injected.length > 0 || result.updated.length > 0) {
      logger.info({
        injected: result.injected.length,
        updated: result.updated.length,
        skipped: result.skipped.length,
      }, '[skill-injector] synced bundled skills')
    } else if (result.skipped.length > 0) {
      logger.debug('[skill-injector] all %d bundled skills up to date', result.skipped.length)
    }
    return result
  }

  private async isDirectory(path: string): Promise<boolean> {
    try {
      return (await stat(path)).isDirectory()
    } catch {
      return false
    }
  }

  /** 比较目录内所有文件的相对路径 + size + mtime，一致则跳过复制 */
  private async dirNeedsSync(sourceDir: string, targetDir: string): Promise<boolean> {
    const sourceSig = await this.dirSignature(sourceDir)
    const targetSig = await this.dirSignature(targetDir)
    return sourceSig !== targetSig
  }

  private async dirSignature(dir: string): Promise<string> {
    const parts: string[] = []
    await this.collectSignatureParts(dir, dir, parts)
    parts.sort()
    return parts.join('\n')
  }

  private async collectSignatureParts(root: string, current: string, parts: string[]): Promise<void> {
    const entries = await readdir(current, { withFileTypes: true })
    for (const entry of entries) {
      const fullPath = join(current, entry.name)
      if (entry.isDirectory()) {
        await this.collectSignatureParts(root, fullPath, parts)
      } else if (entry.isFile()) {
        const rel = fullPath.slice(root.length + 1).replace(/\\/g, '/')
        const info = await stat(fullPath)
        parts.push(`${rel}:${info.size}:${info.mtimeMs}`)
      }
    }
  }

  private async copyDir(sourceDir: string, targetDir: string): Promise<void> {
    await mkdir(targetDir, { recursive: true })
    const entries = await readdir(sourceDir, { withFileTypes: true })
    for (const entry of entries) {
      const sourcePath = join(sourceDir, entry.name)
      const targetPath = join(targetDir, entry.name)
      if (entry.isDirectory()) {
        await this.copyDir(sourcePath, targetPath)
      } else if (entry.isFile()) {
        await copyFile(sourcePath, targetPath)
      }
    }
  }
}
