import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'fs'
import { join } from 'path'
import {
  applyChecklistScmpEvent,
  parseChecklistScmpLine,
  resolveChecklistScmpCliRoot,
  resolveChecklistScmpRequirements,
  validateFeishuUrl,
} from '../../packages/server/src/services/tahp/checklist-scmp-sync'
import type { ChecklistScmpRun } from '../../packages/server/src/services/tahp/checklist-scmp-sync'

function emptyRun(): ChecklistScmpRun {
  return {
    run_id: 'css-test',
    url: 'https://transsioner.feishu.cn/wiki/abc',
    status: 'running',
    progress: 0,
    phase: 'start',
    message: '',
    log_tail: [],
    created_at: '2026-09-21T00:00:00+08:00',
    updated_at: '2026-09-21T00:00:00+08:00',
  }
}

describe('checklist-scmp-sync events', () => {
  it('rejects empty or non-feishu urls', () => {
    expect(validateFeishuUrl('')).toMatch(/请填写/)
    expect(validateFeishuUrl('not-a-url')).toMatch(/http/)
    expect(validateFeishuUrl('https://example.com/doc')).toMatch(/飞书/)
    expect(validateFeishuUrl('https://transsioner.feishu.cn/wiki/xxxx')).toBeNull()
  })

  it('parses jsonl even when prefixed by stderr noise', () => {
    const event = parseChecklistScmpLine('noise {"event":"row","message":"Audio 第4行"}')
    expect(event?.event).toBe('row')
    expect(event?.message).toContain('Audio')
  })

  it('maps plan/sheet/done events to progress and summary', () => {
    let run = applyChecklistScmpEvent(emptyRun(), {
      event: 'workbook',
      title: 'X6879-tOS17 全功能特性checklist_V2.5',
      message: '已读取文档',
    })
    expect(run.title).toContain('X6879')
    expect(run.progress).toBeGreaterThanOrEqual(8)

    run = applyChecklistScmpEvent(run, {
      event: 'parsed',
      project: 'X6879',
      tos_version: '17.0.0',
      message: '解析标题',
    })
    expect(run.project).toBe('X6879')
    expect(run.tos_version).toBe('17.0.0')

    run = applyChecklistScmpEvent(run, { event: 'plan', sheet_count: 10, message: '将处理 10 张表' })
    expect(run.sheet_total).toBe(10)
    expect(run.progress).toBeGreaterThanOrEqual(20)

    run = applyChecklistScmpEvent(run, {
      event: 'sheet_done',
      sheet_name: 'Audio',
      index: 5,
      total: 10,
      message: 'Audio 完成',
    })
    expect(run.current_sheet).toBe('Audio')
    expect(run.progress).toBe(60)

    run = applyChecklistScmpEvent(run, {
      event: 'done',
      ok: true,
      summary: {
        sheet_count: 10,
        feature_count: 20,
        supported: 8,
        unsupported: 6,
        partial: 2,
        missing: 4,
        failed_sheets: [],
      },
      message: '全部处理完成',
    })
    expect(run.status).toBe('completed')
    expect(run.progress).toBe(100)
    expect(run.summary?.supported).toBe(8)
  })

  it('marks fatal error as failed', () => {
    const run = applyChecklistScmpEvent(emptyRun(), {
      event: 'error',
      message: '无法从标题解析项目编码',
      error: { message: '无法从标题解析项目编码' },
    })
    expect(run.status).toBe('failed')
    expect(run.error).toContain('项目编码')
  })

  it('compacts missing httpx traceback into an actionable message', () => {
    const run = applyChecklistScmpEvent(emptyRun(), {
      event: 'error',
      message: "ModuleNotFoundError: No module named 'httpx'",
      error: { message: "Traceback ... No module named 'httpx'" },
    })
    expect(run.status).toBe('failed')
    expect(run.error).toContain('httpx')
    expect(run.error).toContain('setup:skills')
    expect(run.error).not.toContain('Traceback')
  })
})

describe('checklist-scmp-sync cli vendor', () => {
  it('resolves vendored run.py', () => {
    const root = resolveChecklistScmpCliRoot()
    expect(root).toBeTruthy()
    expect(existsSync(join(root!, 'run.py'))).toBe(true)
  })

  it('ships tones-scmp requirements in git so other hosts can pip without the Skill tree', () => {
    const req = resolveChecklistScmpRequirements()
    expect(req).toBeTruthy()
    expect(req!.replace(/\\/g, '/')).toMatch(/checklist-scmp-sync\/requirements\.txt$/)
    const text = readFileSync(req!, 'utf-8')
    expect(text).toContain('httpx')
    expect(text).toContain('cryptography')
  })
})
