// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import SelfCheckChecklist from '@/components/tahp/self-check/SelfCheckChecklist.vue'
import {
  STANDARD_TEST_TYPE_ORDER,
  TEST_TYPE_CATEGORIES,
  getTestTypeCategory,
  getTestTypeLabel,
} from '@/components/tahp/self-check/self-check-utils'
import type { CaseCatalogGroup } from '@/api/tahp/device-self-check'

function makeGroups(): CaseCatalogGroup[] {
  return STANDARD_TEST_TYPE_ORDER.map(testType => ({
    testType,
    label: getTestTypeLabel(testType),
    modules: [],
  }))
}

function mountChecklist(props: { groups?: CaseCatalogGroup[]; activeTestType?: string | null } = {}) {
  return mount(SelfCheckChecklist, {
    props: {
      compact: true,
      groups: makeGroups(),
      ...props,
    },
  })
}

describe('测试大类两级收纳常量', () => {
  it('两个分类的并集与 STANDARD_TEST_TYPE_ORDER 完备一致、无重复', () => {
    const grouped = TEST_TYPE_CATEGORIES.flatMap(c => c.testTypes)
    expect(new Set(grouped).size).toBe(grouped.length)
    expect([...grouped].sort()).toEqual([...STANDARD_TEST_TYPE_ORDER].sort())
  })

  it('getTestTypeCategory 归属正确', () => {
    for (const testType of ['str4', 'week', 'smoke', 'ota_upgrade', 'gms', 'pipeline_adapt', 'ai_generated']) {
      expect(getTestTypeCategory(testType)?.key).toBe('general')
    }
    for (const testType of ['monkey', 'monkey_check', 'power', 'power_feature', 'thermal', 'kernel_feature', 'bitflip']) {
      expect(getTestTypeCategory(testType)?.key).toBe('domain')
    }
    expect(getTestTypeCategory('custom')).toBeNull()
    expect(getTestTypeCategory('')).toBeNull()
  })
})

describe('SelfCheckChecklist 两级卡片', () => {
  it('初始仅展示「通用测试 / 领域测试」两张大类卡', () => {
    const wrapper = mountChecklist()
    const cards = wrapper.findAll('.checklist-card')
    expect(cards.length).toBe(2)
    expect(cards[0].text()).toContain('通用测试')
    expect(cards[1].text()).toContain('领域测试')
    expect(cards[0].text()).toContain('7 个测试项')
    // 测试项卡未渲染（覆盖/自动化/前置 meta 仅测试项卡有）
    expect(wrapper.find('.checklist-meta').exists()).toBe(false)
    wrapper.unmount()
  })

  it('点击大类卡原位展开测试项，点击测试项 emit openCatalog', async () => {
    const wrapper = mountChecklist()
    await wrapper.findAll('.checklist-card')[0].trigger('click')

    const cards = wrapper.findAll('.checklist-card')
    expect(cards.length).toBe(7)
    expect(cards[0].text()).toContain('转测摸底测试')
    expect(cards.map(c => c.find('h4').text())).toEqual([
      '转测摸底测试', '周版本测试', '冒烟测试', '连续OTA升级', 'GMS测试', '流水线适配自动化测试', 'AI用例',
    ])

    await cards[0].trigger('click')
    expect(wrapper.emitted('openCatalog')).toEqual([['str4']])
    wrapper.unmount()
  })

  it('「返回分类」回到大类卡视图，分类切换可直达另一类', async () => {
    const wrapper = mountChecklist()
    await wrapper.findAll('.checklist-card')[0].trigger('click')
    expect(wrapper.findAll('.checklist-card').length).toBe(7)

    await wrapper.find('.checklist-back').trigger('click')
    expect(wrapper.findAll('.checklist-card').length).toBe(2)

    const switchButtons = () => wrapper.findAll('.category-switch-btn')
    await wrapper.findAll('.checklist-card')[1].trigger('click')
    expect(wrapper.findAll('.checklist-card')[0].text()).toContain('monkey测试')
    expect(switchButtons()[1].classes()).toContain('active')

    await switchButtons()[0].trigger('click')
    expect(wrapper.findAll('.checklist-card')[0].text()).toContain('转测摸底测试')
    expect(switchButtons()[0].classes()).toContain('active')
    wrapper.unmount()
  })

  it('activeTestType 传入时自动落在对应分类并高亮当前项', () => {
    const wrapper = mountChecklist({ activeTestType: 'monkey' })
    const cards = wrapper.findAll('.checklist-card')
    expect(cards.length).toBe(7)
    expect(cards[0].text()).toContain('monkey测试')
    expect(cards[0].classes()).toContain('is-active')
    expect(wrapper.findAll('.category-switch-btn')[1].classes()).toContain('active')
    wrapper.unmount()
  })
})
