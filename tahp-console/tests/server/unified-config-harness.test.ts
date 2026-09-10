import { describe, expect, it } from 'vitest'
import {
  UNIFIED_CONFIG_FIELDS,
  buildUnifiedConfigDirective,
  fillUnifiedConfigDefaults,
} from '../../packages/server/src/services/tahp/unified-config'

describe('unified config harness directive', () => {
  it('mentions harness env sync in agent directive', () => {
    const directive = buildUnifiedConfigDirective()
    expect(directive).toContain('harness')
    expect(directive).toMatch(/tran_asf\/env\.yaml|tran_harness\/env\.yaml/)
    expect(directive).toContain('HARNESS_QIZHI_TARGET_HOST')
    expect(directive).toContain('HARNESS_QIZHI_OTP_SECRET')
    expect(directive).toContain('docs/agent-npx-cli-sop.md')
    expect(directive).toContain('harness-requirement.json')
    expect(directive).toContain('启动skill配置检查')
  })
})

describe('modem tool field defaults', () => {
  const byKey = Object.fromEntries(UNIFIED_CONFIG_FIELDS.map(f => [f.key, f]))

  it('pre-fills team-common Modem 工具 paths when the user has not set custom values', () => {
    expect(byKey.seven_zip_exe.default).toBe('E:\\software\\7-Zip\\7z.exe')
    expect(byKey.chrome_binary.default).toBe('C:\\Program Files\\Google\\Chrome\\Application')
    expect(byKey.wireshark_path.default).toBe('E:\\software\\Wireshark')
    expect(byKey.elt_home.default).toBe('E:\\software\\ELT')
    expect(byKey.nlt_home.default).toBe('E:\\software\\ELT')
    expect(byKey.quts_python_path.default).toBe('E:\\software\\ELT')
    expect(byKey.modem_meta_root.default).toBe('E:\\software\\ELT')
  })

  it('does not hardcode workspace_root; clone path is resolved at save/read time', () => {
    expect(byKey.workspace_root.default).toBeUndefined()
  })

  it('keeps custom values and fills empty modem fields so save validation can pass', () => {
    const filled = fillUnifiedConfigDefaults({
      domain_account: 'alice',
      seven_zip_exe: '',
      chrome_binary: '  ',
      wireshark_path: 'D:\\custom\\Wireshark',
    })
    expect(filled.domain_account).toBe('alice')
    expect(filled.seven_zip_exe).toBe('E:\\software\\7-Zip\\7z.exe')
    expect(filled.chrome_binary).toBe('C:\\Program Files\\Google\\Chrome\\Application')
    expect(filled.wireshark_path).toBe('D:\\custom\\Wireshark')
    expect(filled.elt_home).toBe('E:\\software\\ELT')
    expect(filled.modem_meta_root).toBe('E:\\software\\ELT')
  })
})
