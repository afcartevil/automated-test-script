import { describe, expect, it } from 'vitest'
import {
  getAllCaseCatalogs,
  getCaseCatalogDetail,
  initDeviceSelfCheck,
  resolveStartModules,
} from '../../packages/server/src/services/tahp/device-self-check'

const A17_NAMES = [
  'log配置',
  '三键uart和console功能配置',
  '检查Kernel panic前串口打印',
  '长按power key软重启',
  '检查user版本默认uart是否关闭',
  '下载模式DA返回清除异常状态',
  '双键触发hang',
  'db文件检查',
  'root版本开机完成停止串口log',
  '关闭RT_RUNTIME_SHARE',
  'SODI移除检查',
  '不开机log_store[TDFS]检查',
  '关闭mrdump_key功能',
  'mt6789平台晶振patch检查',
  'OCP埋点',
  '器件稳定性埋点',
  'fec2.0方案',
  '黑屏定屏类故障检测',
  '解析expdb/tranpdb',
  '重启检查',
  'cpu中sram bitflip导致的黑屏问题',
  'kernel-5.10 s2idle hwt patch检查',
  'MTK平台检查pl/lk的boot_reason枚举定义顺序保持一致',
]

const QCOM_EXTRA_NAMES = [
  'minidump && fulldump转存',
  'kasan适配',
  '启动日志保存',
  'crash界面优化',
]

const STABILITY_NAMES = [...A17_NAMES, ...QCOM_EXTRA_NAMES]

const MEMORY_NAMES = [
  '融合/压缩版本识别',
  '内存压缩状态',
  '内存融合2.2/2.3',
  'kswapd绑核',
  'shrink_slab',
  'look around',
  'kswapd回收日志',
  'top10 page fault',
  'Quantus Framework',
  '内存分配',
]

const SCHED_NAMES = [
  '感知调度',
  '性能统计 perf log',
  'CPU调度健康标准',
  'cgroup分组策略',
]

describe('device self-check kernel_feature catalog', () => {
  it('loads kernel_feature with stability + memory + sched modules', () => {
    initDeviceSelfCheck()

    const group = getAllCaseCatalogs().find(g => g.testType === 'kernel_feature')
    expect(group?.label).toBe('内核特性自检')
    expect(group?.modules).toHaveLength(3)
    expect(group?.modules.map(m => m.module)).toEqual(['stability', 'memory', 'sched'])
    expect(group?.modules[0]?.moduleLabel).toBe('稳定性')
    expect(group?.modules[1]?.moduleLabel).toBe('内存(SPD)')
    expect(group?.modules[2]?.moduleLabel).toBe('调度(SPD)')

    expect(group?.modules[0]?.cases).toHaveLength(27)
    expect(group?.modules[0]?.cases[0]?.caseName).toBe('log配置')
    expect(group?.modules[0]?.cases[17]?.caseName).toBe('黑屏定屏类故障检测')
    expect(group?.modules[0]?.cases[17]?.caseIndex).toBe(19)
    expect(group?.modules[0]?.cases[18]?.caseName).toBe('解析expdb/tranpdb')
    expect(group?.modules[0]?.cases[18]?.caseIndex).toBe(11)
    expect(group?.modules[0]?.cases[19]?.caseName).toBe('重启检查')
    expect(group?.modules[0]?.cases[1]?.automationMode).toBe('manual')
    expect(group?.modules[0]?.cases[3]?.automationMode).toBe('manual')
    expect(group?.modules[0]?.cases[4]?.automationMode).toBe('manual')
    expect(group?.modules[0]?.cases[6]?.automationMode).toBe('manual')
    expect(group?.modules[0]?.cases[14]?.automationMode).toBe('manual')
    expect(group?.modules[0]?.cases[19]?.automationMode).toBe('manual')
    expect(group?.modules[0]?.cases[1]?.platforms).toEqual(['mtk', 'qcom'])
    expect(group?.modules[0]?.cases[0]?.platforms).toEqual(['mtk'])
    expect(group?.modules[0]?.cases[23]?.caseName).toBe('minidump && fulldump转存')
    expect(group?.modules[0]?.cases[23]?.platforms).toEqual(['qcom'])
    expect(group?.modules[0]?.cases[23]?.automationMode).toBe('full')
    expect(group?.modules[0]?.cases[24]?.automationMode).toBe('manual')
    expect(group?.modules[0]?.cases[25]?.caseName).toBe('启动日志保存')
    expect(group?.modules[0]?.cases[26]?.automationMode).toBe('manual')

    expect(group?.modules[1]?.cases).toHaveLength(10)
    expect(group?.modules[1]?.cases.map(c => c.caseName)).toEqual(MEMORY_NAMES)
    expect(group?.modules[1]?.cases.every(c => c.automationMode === 'full')).toBe(true)
    expect(group?.modules[1]?.cases.map(c => c.caseIndex)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])

    expect(group?.modules[2]?.cases).toHaveLength(4)
    expect(group?.modules[2]?.cases.map(c => c.caseName)).toEqual(SCHED_NAMES)
    expect(group?.modules[2]?.cases.every(c => c.automationMode === 'full')).toBe(true)
    expect(group?.modules[2]?.cases.map(c => c.caseIndex)).toEqual([1, 2, 3, 4])

    const typeOrder = getAllCaseCatalogs().map(g => g.testType)
    expect(typeOrder.indexOf('thermal')).toBeLessThan(typeOrder.indexOf('kernel_feature'))

    const detail = getCaseCatalogDetail('kernel_feature')
    expect(detail).toHaveLength(41)
    expect(detail[0]).toMatchObject({
      testType: 'kernel_feature',
      module: 'stability',
      moduleLabel: '稳定性',
      caseName: 'log配置',
      key: 'kernel_feature/stability/1',
      automationMode: 'full',
      platforms: ['mtk'],
    })
    expect(detail.slice(0, 27).map(d => d.caseName)).toEqual(STABILITY_NAMES)
    expect(detail.slice(27, 37).map(d => d.caseName)).toEqual(MEMORY_NAMES)
    expect(detail.slice(37, 41).map(d => d.caseName)).toEqual(SCHED_NAMES)
    expect(detail[27]).toMatchObject({
      module: 'memory',
      moduleLabel: '内存(SPD)',
      caseName: '融合/压缩版本识别',
      key: 'kernel_feature/memory/1',
      automationMode: 'full',
    })
    expect(detail[37]).toMatchObject({
      module: 'sched',
      moduleLabel: '调度(SPD)',
      caseName: '感知调度',
      key: 'kernel_feature/sched/1',
      automationMode: 'full',
    })
    // 单版本原则：压缩 2.0/1.1 只走 memory/2「内存压缩状态」，无独立 memory/11
    expect(detail.find(d => d.key === 'kernel_feature/memory/11')).toBeUndefined()
    expect(detail.find(d => d.key === 'kernel_feature/memory/2')?.manualSteps).toMatch(/单版本|应检/)
    expect(detail[1]?.automationMode).toBe('manual')
    expect(detail[3]?.automationMode).toBe('manual')
    expect(detail[4]?.automationMode).toBe('manual')
    expect(detail[14]?.automationMode).toBe('manual')
    expect(detail[19]?.automationMode).toBe('manual')
    expect(detail.find(d => d.key === 'kernel_feature/stability/11')?.manualSteps).toMatch(/md_KCONSOLE/)
    expect(detail.find(d => d.key === 'kernel_feature/stability/13')?.expectedResult).toMatch(/xbl\.bin|kernel\.bin|last_kmsg/)
    expect(detail.find(d => d.key === 'kernel_feature/stability/24')?.manualSteps).toMatch(/90EE|QSaharaServer/)
    expect(detail.find(d => d.key === 'kernel_feature/stability/26')?.expectedResult).toMatch(/debuglogger\/stability/)
    expect(detail[0]?.preconditions?.length).toBeGreaterThan(0)
    expect(detail[0]?.manualSteps.length).toBeGreaterThan(0)
    expect(detail[0]?.expectedResult.length).toBeGreaterThan(0)
    expect(detail[27]?.preconditions?.length).toBeGreaterThan(0)
    expect(detail[37]?.manualSteps.length).toBeGreaterThan(0)
    // 用例详情应展示具体检查步骤，而非「自动执行 xxx 脚本」占位文案
    for (const item of detail.filter(d => d.module === 'memory' || d.module === 'sched')) {
      expect(item.manualSteps).not.toMatch(/自动执行/)
      expect(item.manualSteps.split('\n').length).toBeGreaterThan(1)
    }
    expect(detail.find(d => d.key === 'kernel_feature/sched/2')?.manualSteps).toContain("dmesg | grep '[K]'")
    expect(detail.find(d => d.key === 'kernel_feature/memory/4')?.manualSteps).toContain('kswapd0')
  })
})

describe('resolveStartModules (kernel_feature)', () => {
  it('defaults to all modules and filters by selection order', () => {
    expect(resolveStartModules('kernel_feature')).toEqual(['stability', 'memory', 'sched'])
    expect(resolveStartModules('kernel_feature', null)).toEqual(['stability', 'memory', 'sched'])
    expect(resolveStartModules('kernel_feature', [])).toEqual(['stability', 'memory', 'sched'])
    expect(resolveStartModules('kernel_feature', ['sched', 'memory'])).toEqual(['memory', 'sched'])
    expect(resolveStartModules('kernel_feature', ['memory'])).toEqual(['memory'])
    expect(resolveStartModules('kernel_feature', ['memory', 'unknown'])).toEqual(['memory'])
  })

  it('rejects empty valid selection', () => {
    expect(() => resolveStartModules('kernel_feature', ['unknown'])).toThrow(/至少选择一个/)
  })
})

describe('chip platform case filter', () => {
  it('classifies qcom/mtk/unisoc from getprop blob', async () => {
    const { __testingClassifyChipPlatform, __testingCaseAppliesToChipPlatform } = await import(
      '../../packages/server/src/services/tahp/device-self-check'
    )
    expect(__testingClassifyChipPlatform('qcom lahaina')).toBe('qcom')
    expect(__testingClassifyChipPlatform('mt6877 mediatek')).toBe('mtk')
    expect(__testingClassifyChipPlatform('ums9620 unisoc')).toBe('unisoc')
    expect(__testingCaseAppliesToChipPlatform(['mtk'], 'qcom')).toBe(false)
    expect(__testingCaseAppliesToChipPlatform(['mtk', 'qcom'], 'qcom')).toBe(true)
    expect(__testingCaseAppliesToChipPlatform(undefined, 'qcom')).toBe(true)
    expect(__testingCaseAppliesToChipPlatform(['mtk'], 'unknown')).toBe(true)
  })
})
