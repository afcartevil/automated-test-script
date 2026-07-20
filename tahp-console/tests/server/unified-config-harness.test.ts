import { describe, expect, it } from 'vitest'
import { buildUnifiedConfigDirective } from '../../packages/server/src/services/tahp/unified-config'

describe('unified config harness directive', () => {
  it('mentions harness env sync in agent directive', () => {
    const directive = buildUnifiedConfigDirective()
    expect(directive).toContain('harness')
    expect(directive).toContain('tran_harness/env.yaml')
    expect(directive).toContain('HARNESS_QIZHI_TARGET_HOST')
    expect(directive).toContain('config show --effective')
  })
})
