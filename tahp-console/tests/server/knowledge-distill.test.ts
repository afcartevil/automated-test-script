/**
 * 知识沉淀（Phase 2）核心逻辑测试：
 *  - depositDistilledEntry 把诊断报告写成 pending_review 知识条目并落盘
 *  - recordDistillRequest 按 task_id 去重（同任务多次沉淀只保留最新一条）
 */
import { describe, expect, it, beforeAll, afterAll } from 'vitest'
import { mkdtempSync, rmSync, readdirSync, readFileSync, existsSync } from 'fs'
import { tmpdir } from 'os'
import { join } from 'path'

let tmpRoot: string
let tmpHome: string
let depositDistilledEntry: typeof import('../../packages/server/src/routes/tahp/knowledge')['depositDistilledEntry']
let recordDistillRequest: typeof import('../../packages/server/src/services/tahp/bug-analysis-logger')['recordDistillRequest']
let listDistillRequests: typeof import('../../packages/server/src/services/tahp/bug-analysis-logger')['listDistillRequests']

beforeAll(async () => {
  tmpRoot = mkdtempSync(join(tmpdir(), 'tahp-kb-root-'))
  tmpHome = mkdtempSync(join(tmpdir(), 'tahp-kb-home-'))
  process.env.TAHP_PROJECT_ROOT = tmpRoot
  process.env.HERMES_WEB_UI_HOME = tmpHome

  const kbMod = await import('../../packages/server/src/routes/tahp/knowledge')
  depositDistilledEntry = kbMod.depositDistilledEntry
  const logMod = await import('../../packages/server/src/services/tahp/bug-analysis-logger')
  recordDistillRequest = logMod.recordDistillRequest
  listDistillRequests = logMod.listDistillRequests
})

afterAll(() => {
  for (const d of [tmpRoot, tmpHome]) {
    try { rmSync(d, { recursive: true, force: true }) } catch { /* ignore */ }
  }
})

describe('depositDistilledEntry', () => {
  it('writes a pending_review entry from a diagnosis report and persists it', async () => {
    const { entry, action } = await depositDistilledEntry({
      content: '# 某模块崩溃\n根因：空指针解引用。修复建议：在调用前加判空保护。',
      module: 'telephony',
      func_type: 'bug_analysis',
      source_task_id: 'task-123',
      jira_key: 'ABC-1',
    })

    expect(action).toBe('created')

    expect(entry.id).toMatch(/^kb-/)
    expect(entry.status).toBe('pending_review')
    expect(entry.module).toBe('telephony')
    expect(entry.func_type).toBe('bug_analysis')
    expect(entry.source_task_id).toBe('task-123')
    expect(entry.source_file).toBe('JIRA ABC-1')
    expect(entry.keywords.length).toBeGreaterThan(0)
    expect(entry.business_domain).toBeTruthy()
    expect(entry.business_domain_label).toBeTruthy()

    const entriesDir = join(tmpRoot, 'knowledge-base', '.kb-data', 'entries')
    expect(existsSync(join(entriesDir, `${entry.id}.json`))).toBe(true)
    const saved = JSON.parse(readFileSync(join(entriesDir, `${entry.id}.json`), 'utf-8'))
    expect(saved.id).toBe(entry.id)
    expect(saved.status).toBe('pending_review')
  })

  it('defaults module to shared and func_type to bug_analysis', async () => {
    const { entry, action } = await depositDistilledEntry({
      content: '这是一段足够长的内容用于生成默认条目，验证缺省值逻辑是否正确。',
    })
    expect(action).toBe('created')
    expect(entry.module).toBe('shared')
    expect(entry.func_type).toBe('bug_analysis')
    expect(entry.category).toBe('错误模式')
  })

  it('updates existing entry instead of creating duplicate for same jira_key', async () => {
    const first = await depositDistilledEntry({
      content: '# 报告 v1\n根因：A。这是一段足够长的正文用于查重测试，确保内容长度满足阈值要求。',
      jira_key: 'DEDUP-99',
      source_task_id: 'task-dedup-1',
    })
    expect(first.action).toBe('created')

    const second = await depositDistilledEntry({
      content: '# 报告 v2\n根因：B。这是一段足够长的正文用于查重测试，确保内容长度满足阈值要求。',
      jira_key: 'DEDUP-99',
      source_task_id: 'task-dedup-2',
    })
    expect(second.action).toBe('updated')
    expect(second.entry.id).toBe(first.entry.id)

    const entriesDir = join(tmpRoot, 'knowledge-base', '.kb-data', 'entries')
    const files = readdirSync(entriesDir).filter(f => f.endsWith('.json'))
    const dedupFiles = files.filter(f => {
      const data = JSON.parse(readFileSync(join(entriesDir, f), 'utf-8'))
      return data.jira_key === 'DEDUP-99'
    })
    expect(dedupFiles).toHaveLength(1)
  })

  it('returns unchanged when content is identical', async () => {
    const content = '# 相同报告\n根因：C。这是一段足够长的正文用于查重测试，确保内容长度满足阈值要求。'
    const first = await depositDistilledEntry({ content, jira_key: 'DEDUP-100' })
    const second = await depositDistilledEntry({ content, jira_key: 'DEDUP-100' })
    expect(second.action).toBe('unchanged')
    expect(second.entry.id).toBe(first.entry.id)
  })
})

describe('recordDistillRequest dedup', () => {
  it('keeps only the latest record per task_id', async () => {
    await recordDistillRequest({
      task_id: 'dup-task', requested_at: new Date().toISOString(),
      source: 'bug-analysis', result: 'recorded',
    })
    await recordDistillRequest({
      task_id: 'dup-task', requested_at: new Date().toISOString(),
      source: 'bug-analysis', entry_id: 'kb-final', result: 'deposited',
    })

    const all = await listDistillRequests()
    const forTask = all.filter(r => r.task_id === 'dup-task')
    expect(forTask).toHaveLength(1)
    expect(forTask[0].entry_id).toBe('kb-final')
    expect(forTask[0].result).toBe('deposited')
  })
})
