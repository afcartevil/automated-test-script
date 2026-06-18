import { describe, expect, it } from 'vitest'
import {
  extractAdaptAgentFileChanges,
  extractAdaptAgentSkillRefs,
  extractFilesFromLlmResponse,
  extractPathsFromExecuteCode,
  normalizeAdaptAgentReport,
} from '../../packages/server/src/services/tahp/adapt-agent-report'

const SAMPLE = {
  task_id: 'task-adapt-agent-1781141545433-139087',
  domainId: 'comm-framework',
  domainLabel: '通信框架',
  module: 'telephony',
  relatedSkills: ['comm-framework-agent-test', 'com-comm-analysis-foundation'],
  startedAt: '2026-06-11T01:32:25.433Z',
  completedAt: '2026-06-11T01:34:21.579Z',
  duration_ms: 116143,
  fileChanges: [
    { path: 'D:\\Code\\tahp\\skills\\.claude\\skills\\comm-framework-agent-test\\SKILL.md', tool: 'read_file', action: 'modify' },
    { path: 'D:\\AAA_TEMP\\agent-test-output\\comm_framework_agent_test.txt', tool: 'write_file', action: 'modify' },
  ],
  toolsUsed: [
    { name: 'read_file', preview: '(path=D:\\Code\\tahp\\skills\\.claude\\skills\\comm-framework-agent-test\\SKILL.md)' },
    { name: 'skill_view', preview: '(name=transsion-coding-standards-review)' },
    { name: 'write_file', preview: '(path=D:\\AAA_TEMP\\agent-test-output\\comm_framework_agent_test.txt)' },
    { name: 'execute_code', preview: '(code=file_path = r"D:\\AAA_TEMP\\agent-test-output\\comm_framework_agent_test.txt")' },
  ],
  llm_response: 'done',
}

const CHECKLIST_AUDIT = `## Skill 遵从性自检

| 自检项 | 结果 | 说明 |
|--------|------|------|
| 是否 Read 主控 Skill 全文？ | ✅ | ok |

# 编码规范审核报告

## 概览

- **总体结论**：✅ 通过 — ok

## AOSP 流程风险评估

| 子系统 | 变更点 | 调用链影响 | 修改方式合规 | 风险等级 | 建议 |
| 无 | 无 | 无 | ✅ | 低 | ok |
`

describe('adapt-agent-report', () => {
  it('extractPathsFromExecuteCode parses path= assignments', () => {
    const code = 'append_content = ""\npath = r"F:\\\\framework\\\\agent-test-output\\\\comm_framework_agent_test.txt"\nwith open(path, "a") as f: f.write(append_content)'
    const paths = extractPathsFromExecuteCode(code)
    expect(paths).toHaveLength(1)
    expect(paths[0]).toContain('comm_framework_agent_test.txt')
  })

  it('extractAdaptAgentFileChanges includes execute_code path writes', () => {
    const files = extractAdaptAgentFileChanges({
      toolsUsed: [
        { name: 'execute_code', preview: '(code=path = r"F:\\\\AAA_TEMP\\\\out\\\\test.txt")' },
      ],
      llm_response: '',
    })
    expect(files).toHaveLength(1)
    expect(files[0].path).toContain('test.txt')
    expect(files[0].tool).toBe('execute_code')
  })

  it('extractFilesFromLlmResponse parses file modification table', () => {
    const text = `## 文件修改清单\n\n| 路径 | 修改说明 |\n|------|----------|\n| \`D:\\\\AAA_TEMP\\\\agent-test-output\\\\comm_framework_agent_test.txt\` | **新建** — 测试文件 |`
    const files = extractFilesFromLlmResponse(text)
    expect(files).toHaveLength(1)
    expect(files[0].path).toContain('comm_framework_agent_test.txt')
    expect(files[0].action).toBe('create')
  })

  it('extractAdaptAgentFileChanges excludes read_file and SKILL.md', () => {
    const files = extractAdaptAgentFileChanges(SAMPLE)
    expect(files).toHaveLength(1)
    expect(files[0].path).toContain('comm_framework_agent_test.txt')
    expect(files[0].tool).toBe('write_file')
  })

  it('extractAdaptAgentSkillRefs returns full skill paths', () => {
    const skills = extractAdaptAgentSkillRefs(SAMPLE)
    const ids = skills.map(s => s.skill_id)
    expect(ids).toContain('comm-framework-agent-test')
    expect(ids).toContain('com-comm-analysis-foundation')
    expect(ids).toContain('transsion-coding-standards-review')
    expect(skills.every(s => s.path.endsWith('SKILL.md'))).toBe(true)
    expect(ids).not.toContain('read_file')
    expect(ids).not.toContain('terminal')
  })

  it('normalizeAdaptAgentReport maps camelCase timestamps and files', () => {
    const n = normalizeAdaptAgentReport({
      ...SAMPLE,
      auditReport: `## Skill 遵从性自检\n**结论**: ✅ 完全遵从\n\n# 编码规范审核报告\n## 概览\n- **总体结论**：✅ 通过 — ok\n\n## AOSP 流程风险评估\n| 子系统 | 变更点 | 调用链影响 | 修改方式合规 | 风险等级 | 建议 |\n| N/A | 无 | 无 | ✅ | 无 | N/A |`,
    })
    expect(n.started_at).toBe('2026-06-11T01:32:25.433Z')
    expect(n.completed_at).toBe('2026-06-11T01:34:21.579Z')
    expect(n.domain).toBe('comm-framework')
    expect(n.domain_label).toBe('通信框架')
    expect(n.files_modified).toHaveLength(1)
    expect(n.skills_used.length).toBeGreaterThanOrEqual(3)
    expect(n.audit_summary).toHaveLength(3)
    expect(n.audit_summary![0].status).toBe('pass')
  })

  it('falls back to llm_response for files when tools empty', () => {
    const n = normalizeAdaptAgentReport({
      ...SAMPLE,
      fileChanges: [],
      toolsUsed: [{ name: 'execute_code', preview: '(code=truncated…)' }],
      llm_response: `## 文件修改清单\n| \`D:\\\\AAA_TEMP\\\\agent-test-output\\\\comm_framework_agent_test.txt\` | **新建** |`,
      auditReport: CHECKLIST_AUDIT,
    })
    expect(n.files_modified).toHaveLength(1)
    expect(n.files_modified[0]).toContain('comm_framework_agent_test.txt')
    expect(n.audit_summary![0].status).toBe('pass')
  })
})
