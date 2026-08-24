import { mkdir, mkdtemp, readFile, rm, writeFile } from 'fs/promises'
import { existsSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'
import { afterEach, describe, expect, it } from 'vitest'
import {
  backfillSkillImproveSnapshots,
  readSkillSnapshot,
  snapshotImprovedSkills,
  SKILL_SNAPSHOT_MAX_BYTES,
} from '../../packages/server/src/services/tahp/bug-analysis-skill-snapshot'

const tempDirs: string[] = []

async function tempDir(prefix: string): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), prefix))
  tempDirs.push(dir)
  return dir
}

afterEach(async () => {
  await Promise.all(tempDirs.splice(0).map(dir => rm(dir, { recursive: true, force: true })))
})

describe('snapshotImprovedSkills', () => {
  it('copies the skill directory and writes a runtime manifest', async () => {
    const src = await tempDir('snap-src-')
    const reports = await tempDir('snap-reports-')
    const skillDir = join(src, 'demo-skill')
    await mkdir(skillDir, { recursive: true })
    await writeFile(join(skillDir, 'SKILL.md'), '# Demo\n', 'utf-8')
    await mkdir(join(skillDir, 'references'), { recursive: true })
    await writeFile(join(skillDir, 'references', 'note.md'), 'note\n', 'utf-8')

    const records = await snapshotImprovedSkills({
      reportsDir: reports,
      taskId: 'task-bug-1',
      records: [{ name: 'demo-skill', actions: ['create'] }],
      resolveSkillDir: (name) => name === 'demo-skill' ? skillDir : null,
      source: 'runtime',
    })

    expect(records[0].snapshot_dir).toBe('bug-analysis/skills/task-bug-1/demo-skill')
    expect(records[0].snapshot_source).toBe('runtime')
    const dest = join(reports, 'bug-analysis', 'skills', 'task-bug-1', 'demo-skill')
    expect(await readFile(join(dest, 'SKILL.md'), 'utf-8')).toBe('# Demo\n')
    const manifest = JSON.parse(await readFile(join(dest, 'manifest.json'), 'utf-8'))
    expect(manifest.truncated).toBe(false)
    expect(manifest.snapshot_source).toBe('runtime')
    expect(manifest.files.some((f: { path: string }) => f.path === 'references/note.md')).toBe(true)

    const read = readSkillSnapshot(reports, 'task-bug-1', 'demo-skill')
    expect(read?.skill_md).toBe('# Demo\n')
    expect(read?.snapshot_source).toBe('runtime')
  })

  it('truncates oversized skills to SKILL.md only', async () => {
    const src = await tempDir('snap-big-')
    const reports = await tempDir('snap-big-reports-')
    const skillDir = join(src, 'huge-skill')
    await mkdir(skillDir, { recursive: true })
    await writeFile(join(skillDir, 'SKILL.md'), '# huge\n', 'utf-8')
    await writeFile(join(skillDir, 'blob.bin'), 'x'.repeat(64), 'utf-8')

    const records = await snapshotImprovedSkills({
      reportsDir: reports,
      taskId: 'task-bug-2',
      records: [{ name: 'huge-skill', actions: ['write_file'] }],
      resolveSkillDir: () => skillDir,
      maxBytes: 8,
      maxFiles: 200,
    })
    expect(records[0].snapshot_dir).toBeTruthy()
    const dest = join(reports, 'bug-analysis', 'skills', 'task-bug-2', 'huge-skill')
    expect(existsSync(join(dest, 'SKILL.md'))).toBe(true)
    expect(existsSync(join(dest, 'blob.bin'))).toBe(false)
    const manifest = JSON.parse(await readFile(join(dest, 'manifest.json'), 'utf-8'))
    expect(manifest.truncated).toBe(true)
    expect(SKILL_SNAPSHOT_MAX_BYTES).toBeGreaterThan(1024)
  })

  it('backfills historical reports from a task→skill map', async () => {
    const src = await tempDir('snap-bf-src-')
    const reports = await tempDir('snap-bf-reports-')
    const skillDir = join(src, 'old-skill')
    await mkdir(skillDir, { recursive: true })
    await writeFile(join(skillDir, 'SKILL.md'), '# old\n', 'utf-8')
    const reportDir = join(reports, 'bug-analysis')
    await mkdir(reportDir, { recursive: true })
    await writeFile(join(reportDir, 'task-bug-9.json'), JSON.stringify({
      task_id: 'task-bug-9',
      skills_improved: [{ name: 'old-skill', actions: ['create'] }],
    }, null, 2), 'utf-8')

    const result = await backfillSkillImproveSnapshots({
      reportsDir: reports,
      ledgerByTask: new Map([['task-bug-9', ['old-skill']]]),
      resolveSkillDir: () => skillDir,
    })
    expect(result.reports_updated).toBe(1)
    expect(result.skills_copied).toBe(1)
    const json = JSON.parse(await readFile(join(reportDir, 'task-bug-9.json'), 'utf-8'))
    expect(json.skills_improved[0].snapshot_source).toBe('backfill')
    const read = readSkillSnapshot(reports, 'task-bug-9', 'old-skill')
    expect(read?.snapshot_source).toBe('backfill')
    expect(read?.skill_md).toBe('# old\n')
  })
})
