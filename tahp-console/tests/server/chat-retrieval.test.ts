import { describe, expect, it } from 'vitest'
import { formatRetrievalPrompt } from '../../packages/server/src/services/tahp/chat-retrieval/prompt-formatter'
import type { RetrievalBundle } from '../../packages/server/src/services/tahp/chat-retrieval/types'

describe('chat-retrieval prompt formatter', () => {
  it('formats kb hits without full skill catalog', () => {
    const bundle: RetrievalBundle = {
      intent: 'historical_case',
      strategy_label: '历史案例检索',
      kb_hits: [{
        id: 'kb-f2dc1bc8',
        source_type: 'bug_distill',
        module: 'telephony',
        func_type: 'bug_analysis',
        title: 'JIRA TOS163-37004',
        snippet: 'VozWiFi Movistar 通话界面显示问题',
        relevance: 87,
        jira_key: 'TOS163-37004',
        status: 'archived',
        path: 'knowledge-base/.kb-data/entries/kb-f2dc1bc8.json',
      }],
      skill_hits: [],
      lark_hits: [],
      directives: ['禁止 grep 全库'],
      latency_ms: 12,
    }
    const out = formatRetrievalPrompt(bundle)
    expect(out).toContain('历史案例检索')
    expect(out).toContain('VozWiFi')
    expect(out).toContain('kb-f2dc1bc8')
    expect(out).not.toContain('已扫描到的 Skills（共')
  })
})
