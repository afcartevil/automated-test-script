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
})
