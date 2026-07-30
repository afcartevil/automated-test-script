import { describe, expect, it } from 'vitest'
import { buildUnifiedConfigDirective } from '../../packages/server/src/services/tahp/unified-config'

describe('unified config harness directive', () => {
  it('mentions harness env sync in agent directive', () => {
    const directive = buildUnifiedConfigDirective()
    expect(directive).toContain('harness')
    expect(directive).toContain('tran_harness/env.yaml')
    expect(directive).toContain('HARNESS_QIZHI_TARGET_HOST')
    expect(directive).toContain('HARNESS_QIZHI_OTP_SECRET')
    expect(directive).toContain('docs/agent-npx-cli-sop.md')
    expect(directive).toContain('harness-requirement.json')
    expect(directive).toContain('启动skill配置检查')
  })
})
