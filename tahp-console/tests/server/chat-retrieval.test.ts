import { describe, expect, it } from 'vitest'
import { formatRetrievalPrompt } from '../../packages/server/src/services/tahp/chat-retrieval/prompt-formatter'
import { resolveDomainKeywords } from '../../packages/server/src/services/tahp/chat-retrieval/catalog-query'
import { runRetrieval } from '../../packages/server/src/services/tahp/chat-retrieval/orchestrator'
import { runHistoricalCase } from '../../packages/server/src/services/tahp/chat-retrieval/strategies/historical-case'
import { runAnalysisSop } from '../../packages/server/src/services/tahp/chat-retrieval/strategies/analysis-sop'
import { routeIntent } from '../../packages/server/src/services/tahp/chat-retrieval/intent-router'
import { buildHistoricalCaseDirective, buildSkillExecutionDirective } from '../../packages/server/src/services/tahp/context-injector'
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

  it('explicit catalog mode with empty kb hints dify supplement and bans skill fill', () => {
    const bundle: RetrievalBundle = {
      intent: 'historical_case',
      strategy_label: '历史案例检索',
      kb_hits: [],
      skill_hits: [],
      lark_hits: [],
      directives: ['主答案必须来自智能诊断沉淀案例'],
      latency_ms: 5,
      catalog_mode: true,
      explicit_mode: true,
    }
    const out = formatRetrievalPrompt(bundle)
    expect(out).toContain('底软通信知识库补充参考')
    expect(out).toContain('禁止')
    expect(out).toContain('答复格式')
  })

  it('auto catalog mode allows doc/skill fusion wording', () => {
    const bundle: RetrievalBundle = {
      intent: 'historical_case',
      strategy_label: '历史案例检索',
      kb_hits: [],
      skill_hits: [],
      lark_hits: [],
      directives: [],
      latency_ms: 5,
      catalog_mode: true,
      explicit_mode: false,
    }
    const out = formatRetrievalPrompt(bundle)
    expect(out).toContain('底软通信')
    expect(out).not.toContain('**禁止**输出 Skill 清单')
  })
})

describe('resolveDomainKeywords call focus', () => {
  it('narrows to call keywords for 通话-focused query even with telephony hint', () => {
    const kws = resolveDomainKeywords('通信通话常见问题', 'telephony')
    expect(kws).toContain('通话')
    expect(kws).toContain('ims')
    expect(kws).not.toContain('modem')
    expect(kws).not.toContain('apn')
    expect(kws).not.toContain('sim')
  })

  it('keeps broad telephony bag when SIM/data terms present', () => {
    const kws = resolveDomainKeywords('SIM卡识别异常', 'telephony')
    expect(kws).toContain('sim')
  })
})

describe('directive selection contract', () => {
  it('historical directive bans skills; skill directive mentions foundation', () => {
    const hist = buildHistoricalCaseDirective()
    const skill = buildSkillExecutionDirective({ scenario: 'chat' })
    expect(hist).toContain('历史案例')
    expect(hist).toMatch(/禁止.*Skill|禁止列举/)
    expect(skill).toContain('com-comm-analysis-foundation')
  })
})

describe('fusion retrieval (auto mode)', () => {
  it('runAnalysisSop returns doc_chunk hits for 常见通话问题 query', async () => {
    const query = '常见通话问题，以及分析流程'
    const routed = routeIntent(query, {})
    expect(routed.intent).toBe('analysis_sop')
    const bundle = await runAnalysisSop(query, routed, { explicit: false })
    expect(bundle.kb_hits.length).toBeGreaterThan(0)
    expect(bundle.kb_hits.some(h => h.source_type === 'doc_chunk')).toBe(true)
    expect(bundle.explicit_mode).toBe(false)
  })

  it('runHistoricalCase auto mode returns doc hits for catalog query', async () => {
    const query = '通信通话常见问题有哪些'
    const routed = routeIntent(query, {})
    const bundle = await runHistoricalCase(query, routed, { explicit: false })
    expect(bundle.catalog_mode).toBe(true)
    expect(bundle.kb_hits.length).toBeGreaterThan(0)
    expect(bundle.explicit_mode).toBe(false)
  })

  it('runHistoricalCase explicit mode keeps bug_distill only', async () => {
    const query = '通信通话常见问题有哪些'
    const routed = routeIntent(query, {})
    const bundle = await runHistoricalCase(query, routed, { explicit: true })
    expect(bundle.explicit_mode).toBe(true)
    for (const hit of bundle.kb_hits) {
      expect(hit.source_type).toBe('bug_distill')
    }
  })

  it('runRetrieval auto sets explicit_mode false for catalog query', async () => {
    const { bundle } = await runRetrieval('通信通话常见问题有哪些', { retrieval_mode: 'auto' })
    expect(bundle.explicit_mode).toBe(false)
    expect(bundle.kb_hits.length).toBeGreaterThan(0)
  })

  it('runRetrieval historical mode sets explicit_mode true', async () => {
    const { bundle } = await runRetrieval('通信通话常见问题有哪些', { retrieval_mode: 'historical' })
    expect(bundle.explicit_mode).toBe(true)
  })
})
