import { describe, it, expect } from 'vitest'
import { extractP0TestSuggestions } from '../../packages/server/src/services/tahp/gerrit-review-report'

const SINGLE_CHANGE_REPORT = `
## 5. 测试建议

### P0 - 必须测试
1. **充电路径** - 插拔充电器 / 验证点: 电流正常
2. **休眠唤醒** - 灭屏后唤醒 / 验证点: 无卡死

### P1 - 强烈建议
1. **温度** - 高温场景
`

const TOPIC_REPORT = `
## 合并测试建议

### P0 - 必须测试
1. **USB枚举** - 连接 PC / 验证点: adb devices 可见
- **快充协议** - 使用 PD 充电器 / 验证点: 功率达标

### P1 - 强烈建议
1. 低电量场景
`

describe('extractP0TestSuggestions', () => {
  it('extracts numbered P0 items from single change report', () => {
    const { items, rawSection } = extractP0TestSuggestions(SINGLE_CHANGE_REPORT)
    expect(items).toHaveLength(2)
    expect(items[0]).toContain('充电路径')
    expect(items[1]).toContain('休眠唤醒')
    expect(rawSection).toContain('充电路径')
  })

  it('extracts P0 items under merged topic section', () => {
    const { items } = extractP0TestSuggestions(TOPIC_REPORT)
    expect(items).toHaveLength(2)
    expect(items[0]).toContain('USB枚举')
    expect(items[1]).toContain('快充协议')
  })

  it('returns empty for missing P0 section', () => {
    const { items, rawSection } = extractP0TestSuggestions('## 1. 基本信息\n无测试建议')
    expect(items).toEqual([])
    expect(rawSection).toBe('')
  })

  it('stops at P1 heading', () => {
    const { items } = extractP0TestSuggestions(SINGLE_CHANGE_REPORT)
    expect(items.every(i => !i.includes('温度'))).toBe(true)
  })

  it('extracts P0 from HTML badge heading in terminal summary', () => {
    const report = `
**测试建议**:

### <span class="badge badge-p0">P0</span> 必须测试
1. **SAR 校准基础功能** — USB 正常插入和拔出时，确认是否成功触发校准。
2. **反复快速插拔稳定性** — 快速反复插拔 USB 线。

### <span class="badge badge-p1">P1</span> 强烈建议
1. **休眠与唤醒场景测试** — 连接 USB 后使机器进入深度休眠。
`
    const { items } = extractP0TestSuggestions(report)
    expect(items).toHaveLength(2)
    expect(items[0]).toContain('SAR 校准基础功能')
    expect(items[1]).toContain('反复快速插拔')
  })

  it('extracts from **P0 必须测试** without dash', () => {
    const report = `
### 4. 测试建议

**P0 必须测试**
1. **SAR 校准触发** — 插入和拔出 USB
2. **开机时带电** — 关机插入 USB 后开机

**P1 强烈建议**
1. 频繁插拔压力测试
`
    const { items } = extractP0TestSuggestions(report)
    expect(items).toHaveLength(2)
    expect(items[0]).toContain('SAR 校准触发')
  })

  it('extracts from bold-wrapped ### P0 heading', () => {
    const report = `
### 4. 测试建议
**### P0 - 必须测试**
*   插拔 USB 充电器，验证 SAR 传感器校准
*   重复快速插拔 USB 测试

**### P1 - 强烈建议**
*   休眠/唤醒测试
`
    const { items } = extractP0TestSuggestions(report)
    expect(items).toHaveLength(2)
    expect(items[0]).toContain('插拔 USB')
  })

  it('stops extraction before P1 and P2 sections', () => {
    const report = `
### 4. 测试建议
### P0 - 必须测试
1. **USB 插拔** — 验证充电与枚举
2. **SAR 校准** — 插拔触发校准

**P1 强烈建议**
1. 休眠唤醒测试
2. 高频插拔压力测试

**P2 建议测试**
1. 开机带 USB 启动
`
    const { items } = extractP0TestSuggestions(report)
    expect(items).toHaveLength(2)
    expect(items.every(i => !i.includes('休眠') && !i.includes('开机'))).toBe(true)
  })

  it('extracts items from standalone 必须测试 heading', () => {
    const report = `
## 5. 测试建议

### 必须测试
1. **USB枚举** - 连接 PC
2. **充电路径** - 插拔充电器

### 强烈建议
1. 低电量场景
`
    const { items } = extractP0TestSuggestions(report)
    expect(items).toHaveLength(2)
    expect(items[0]).toContain('USB枚举')
    expect(items[1]).toContain('充电路径')
  })

  it('extracts P0 from bold marker under 测试建议 section', () => {
    const report = `
### 4. 测试建议
**P0 - 必须测试**
*   插拔 USB 线，验证 kernel log 中是否正常触发校准。
*   多次高频插拔 USB，检查是否出现内核卡顿或崩溃。

**P1 - 强烈建议**
*   带 USB 线开机和不带 USB 线开机。
`
    const { items } = extractP0TestSuggestions(report)
    expect(items).toHaveLength(2)
    expect(items[0]).toContain('插拔 USB 线')
    expect(items[1]).toContain('多次高频插拔')
  })

  it('extracts from #### ### P0 - 必须测试 (double-hash heading)', () => {
    const report = `
### 4. 测试建议
#### ### P0 - 必须测试
1.  **SAR 校准触发功能验证** — 正常插入和拔出 USB Type-C 数据线
2.  **SAR 传感器读数验证** — 插拔 USB 后检查 SAR 传感器读数
3.  **反复快速插拔稳定性** — 快速反复插拔 USB 线

#### ### P1 - 强烈建议
1.  休眠与唤醒场景测试
`
    const { items } = extractP0TestSuggestions(report)
    expect(items).toHaveLength(3)
    expect(items[0]).toContain('SAR 校准触发')
    expect(items.every(i => !i.includes('休眠'))).toBe(true)
  })

  it('extracts from historical report task-gerrit-1782373263967 (1543793)', async () => {
    const { readFileSync, existsSync } = await import('node:fs')
    const { join } = await import('node:path')
    const reportPath = join(process.cwd(), '..', 'reports', 'gerrit-review', 'task-gerrit-1782373263967-c33b44.json')
    if (!existsSync(reportPath)) return
    const report = JSON.parse(readFileSync(reportPath, 'utf8'))
    const { items } = extractP0TestSuggestions(report.llm_response || '')
    expect(items.length).toBeGreaterThanOrEqual(3)
    expect(items.some(i => /USB|SAR|插拔/i.test(i))).toBe(true)
  })
})

describe('extractModules', () => {
  it('extracts modules from terminal summary line', async () => {
    const { extractModules } = await import('../../packages/server/src/services/tahp/gerrit-review-report')
    const result = extractModules('**模块**: LCM/TP/USB\n**P0**: test')
    expect(result.modules).toEqual(['LCM', 'TP', 'USB'])
    expect(result.display).toBe('LCM/TP/USB')
  })

  it('extracts modules from markdown table', async () => {
    const { extractModules } = await import('../../packages/server/src/services/tahp/gerrit-review-report')
    const result = extractModules('| 模块 | 通信 |\n| --- | --- |')
    expect(result.modules).toEqual(['通信'])
    expect(result.display).toBe('通信')
  })

  it('returns 未识别 when no module info', async () => {
    const { extractModules } = await import('../../packages/server/src/services/tahp/gerrit-review-report')
    const result = extractModules('## 测试建议\n无模块')
    expect(result.modules).toEqual([])
    expect(result.display).toBe('未识别')
  })
})
