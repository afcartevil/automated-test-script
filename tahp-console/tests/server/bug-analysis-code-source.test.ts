import { describe, expect, it } from 'vitest'
import { mkdtempSync, rmSync } from 'fs'
import { join } from 'path'
import { tmpdir } from 'os'
import {
  DEFAULT_OPENGROK_BRANCH,
  OPENGROK_BRANCHES,
  buildCodeSourceDirective,
  buildCodeSourceUserBlock,
  codeSourcePreferredSkillIds,
  parseCodeSource,
  restoreCodeSourceFromReport,
  snapshotCodeSourceForReport,
} from '../../packages/server/src/services/tahp/code-source'

describe('code-source 判型', () => {
  it('空输入不产生代码源', () => {
    expect(parseCodeSource(undefined)).toBeUndefined()
    expect(parseCodeSource('')).toBeUndefined()
    expect(parseCodeSource('   ')).toBeUndefined()
  })

  it('Windows 盘符 / 映射盘路径判为本地路径', () => {
    const ref = parseCodeSource('D:\\code\\tOS_mtk_A16\\frameworks')
    expect(ref?.kind).toBe('local_path')
    expect(ref?.path).toBe('D:\\code\\tOS_mtk_A16\\frameworks')
    expect(ref?.exists).toBe(false)
  })

  it('本地路径存在时 exists=true 且去掉尾部分隔符', () => {
    const dir = mkdtempSync(join(tmpdir(), 'tahp-code-src-'))
    try {
      const ref = parseCodeSource(`${dir}\\`)
      expect(ref?.kind).toBe('local_path')
      expect(ref?.path).toBe(dir)
      expect(ref?.exists).toBe(true)
    } finally {
      rmSync(dir, { recursive: true, force: true })
    }
  })

  it('UNC 与 POSIX 绝对路径判为本地路径', () => {
    expect(parseCodeSource('/home/user/aosp')?.kind).toBe('local_path')
  })

  it('UNC 路径不做存在性探测（避免请求线程阻塞在不可达网络）', () => {
    const started = Date.now()
    const ref = parseCodeSource('\\\\10.255.255.1\\share\\code')
    expect(ref?.kind).toBe('local_path')
    expect(ref?.exists).toBeUndefined()
    expect(Date.now() - started).toBeLessThan(500)
  })

  it('已知分支名判为 OpenGrok 分支并标记 branchKnown', () => {
    const ref = parseCodeSource(DEFAULT_OPENGROK_BRANCH)
    expect(ref?.kind).toBe('opengrok_branch')
    expect(ref?.branch).toBe(DEFAULT_OPENGROK_BRANCH)
    expect(ref?.branchKnown).toBe(true)
  })

  it('分支清单包含截图中的三平台分支', () => {
    expect(OPENGROK_BRANCHES).toContain('tOS_mtk_A17_trunk')
    expect(OPENGROK_BRANCHES).toContain('tOS_qcom_A14_nonhlos_trunk')
    expect(OPENGROK_BRANCHES).toContain('tOS_unisoc_A16_sys_trunk')
    expect(OPENGROK_BRANCHES).toContain('transsion_mtk.s0.mp1_trunk')
  })

  it('未收录但形似分支的输入仍判为分支，branchKnown=false', () => {
    const ref = parseCodeSource('tOS_mtk_A18_trunk')
    expect(ref?.kind).toBe('opengrok_branch')
    expect(ref?.branchKnown).toBe(false)
  })

  it('A17 之类模糊关键字判为分支查询', () => {
    expect(parseCodeSource('A17')?.kind).toBe('opengrok_branch')
  })

  it('xref 链接解析出分支、文件与行号', () => {
    const ref = parseCodeSource(
      'http://opengrok.transsion.com/xref/tOS_mtk_A16_trunk/frameworks/base/core/java/Foo.java#128',
    )
    expect(ref?.kind).toBe('opengrok_url')
    expect(ref?.branch).toBe('tOS_mtk_A16_trunk')
    expect(ref?.filePath).toBe('/frameworks/base/core/java/Foo.java')
    expect(ref?.startLine).toBe(128)
    expect(ref?.branchKnown).toBe(true)
  })

  it('search 链接从 project 参数取分支', () => {
    const ref = parseCodeSource('http://opengrok.transsion.com/search?project=tOS_qcom_A17_trunk&full=wifi')
    expect(ref?.kind).toBe('opengrok_url')
    expect(ref?.branch).toBe('tOS_qcom_A17_trunk')
  })

  it('非 OpenGrok 链接与自由文本判为 unknown', () => {
    expect(parseCodeSource('http://jira.transsion.com/browse/X-1')?.kind).toBe('unknown')
    expect(parseCodeSource('telephony 模块')?.kind).toBe('unknown')
  })

  it('多行输入只取第一行，超长输入被截断', () => {
    expect(parseCodeSource(`${DEFAULT_OPENGROK_BRANCH}\n第二行说明`)?.branch).toBe(DEFAULT_OPENGROK_BRANCH)
    expect(parseCodeSource('D:\\'.padEnd(900, 'x'))?.raw.length).toBe(512)
  })
})

describe('code-source 提示词注入', () => {
  it('无代码源时不注入任何内容', () => {
    expect(buildCodeSourceDirective(undefined)).toBe('')
    expect(buildCodeSourceUserBlock(undefined)).toEqual([])
    expect(codeSourcePreferredSkillIds(undefined)).toEqual([])
  })

  it('本地路径指令要求只读取证并给出路径', () => {
    const directive = buildCodeSourceDirective(parseCodeSource('D:\\code\\aosp'))
    expect(directive).toContain('指定代码源')
    expect(directive).toContain('D:\\code\\aosp')
    expect(directive).toContain('只读')
    // 路径不存在时须提示 Agent 降级而不是编造
    expect(directive).toContain('code_source_unavailable')
    expect(directive).not.toContain('opengrok')
  })

  it('OpenGrok 分支指令包含 CLI 取证顺序与分支', () => {
    const directive = buildCodeSourceDirective(parseCodeSource(DEFAULT_OPENGROK_BRANCH))
    expect(directive).toContain('opengrok search')
    expect(directive).toContain('find-in-file')
    expect(directive).toContain('fetch')
    expect(directive).toContain(DEFAULT_OPENGROK_BRANCH)
  })

  it('未收录分支时提示先核对分支名并给出已知清单', () => {
    const directive = buildCodeSourceDirective(parseCodeSource('tOS_mtk_A18_trunk'))
    expect(directive).toContain('opengrok branches --query tOS_mtk_A18_trunk')
    expect(directive).toContain(DEFAULT_OPENGROK_BRANCH)
  })

  it('OpenGrok 类型才要求优先 Read 官方 opengrok Skill', () => {
    expect(codeSourcePreferredSkillIds(parseCodeSource('tOS_mtk_A16_trunk'))[0]).toMatch(/opengrok$/)
    expect(codeSourcePreferredSkillIds(parseCodeSource('D:\\code\\aosp'))).toEqual([])
  })

  it('user message 块回显判型结果', () => {
    const block = buildCodeSourceUserBlock(parseCodeSource('tOS_qcom_A16_trunk')).join('\n')
    expect(block).toContain('## 指定代码源')
    expect(block).toContain('tOS_qcom_A16_trunk')
  })
})

describe('code-source 落盘与恢复', () => {
  it('快照使用 snake_case 字段', () => {
    const snap = snapshotCodeSourceForReport(
      parseCodeSource('http://opengrok.transsion.com/xref/tOS_mtk_A16_trunk/a/B.java#7'),
    )
    expect(snap).toMatchObject({
      kind: 'opengrok_url',
      branch: 'tOS_mtk_A16_trunk',
      file_path: '/a/B.java',
      start_line: 7,
    })
    expect(snapshotCodeSourceForReport(undefined)).toBeUndefined()
  })

  it('从报告快照与旧版字符串都能恢复', () => {
    const snap = snapshotCodeSourceForReport(parseCodeSource(DEFAULT_OPENGROK_BRANCH))
    expect(restoreCodeSourceFromReport(snap)?.branch).toBe(DEFAULT_OPENGROK_BRANCH)
    expect(restoreCodeSourceFromReport(DEFAULT_OPENGROK_BRANCH)?.kind).toBe('opengrok_branch')
    expect(restoreCodeSourceFromReport(undefined)).toBeUndefined()
    expect(restoreCodeSourceFromReport({})).toBeUndefined()
  })
})
