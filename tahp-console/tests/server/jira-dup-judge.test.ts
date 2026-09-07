import { describe, expect, it } from 'vitest'
import {
  buildJiraDupJudgePrompt,
  jiraDupJudgeSessionId,
  resolveJiraBrowseUrl,
} from '../../packages/server/src/services/tahp/jira-dup-judge'

describe('jira-dup-judge prompt', () => {
  it('uses the fixed 置重 template with the browse URL', () => {
    expect(buildJiraDupJudgePrompt('http://jira.transsion.com/browse/X6885O6AEE-37668')).toBe(
      '把 http://jira.transsion.com/browse/X6885O6AEE-37668 按 jira-dup-judge 置重。',
    )
  })

  it('keeps an existing browse URL and strips query/hash', () => {
    expect(resolveJiraBrowseUrl(
      'http://jira.transsion.com/browse/X6885O6AEE-37668?focusedCommentId=1#comment',
      'X6885O6AEE-37668',
    )).toBe('http://jira.transsion.com/browse/X6885O6AEE-37668')
  })

  it('builds browse URL from key when the task URL is empty', () => {
    const prev = process.env.TAHP_JIRA_BASE_URL
    process.env.TAHP_JIRA_BASE_URL = 'http://jira.transsion.com'
    expect(resolveJiraBrowseUrl('', 'FOO-12')).toBe('http://jira.transsion.com/browse/FOO-12')
    if (prev === undefined) delete process.env.TAHP_JIRA_BASE_URL
    else process.env.TAHP_JIRA_BASE_URL = prev
  })

  it('uses a dedicated agent session so continue-analysis is not overwritten', () => {
    expect(jiraDupJudgeSessionId('task-bug-1')).toBe('tahp-bug-dup-task-bug-1')
  })
})
