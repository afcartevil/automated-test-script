// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRouter: () => ({ push: vi.fn() }),
  }
})

import ManualView from '@/views/tahp/ManualView.vue'

class IntersectionObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

vi.stubGlobal('IntersectionObserver', IntersectionObserverStub)

describe('ManualView product intro', () => {
  it('renders the product copy verbatim at the top of the handbook', () => {
    const wrapper = mount(ManualView)

    expect(wrapper.get('.intro-slogan').text()).toBe('可靠+好用+易用，是EasyAdapter追求的目标')
    expect(wrapper.findAll('.intro-traits li').map(item => item.text())).toEqual([
      '可靠——信任EasyAdapter所做的，它是可并肩而行的伙伴',
      '好用——用了就不想换，有适配任务时第一个想到它',
      '易用——门槛低，上手快，新人不用学就会，或学一点就会',
    ])
  })

  it('keeps handbook labels aligned with current product surfaces', () => {
    const wrapper = mount(ManualView)
    const text = wrapper.text()

    expect(text).toContain('库浏览 / 自改进 / 同步中心')
    expect(text).toContain('人工确认')
    expect(text).toContain('人工复核')
    expect(text).not.toContain('无需人工介入')
    expect(text).toContain('⚠ N 项待人工处理')
    expect(text).toContain('patch分析')
    expect(text).toContain('patch入库')
    expect(text).toContain('工作台 / patch分析 / patch入库 / 故障诊断 / 数据库 / 设置')
  })

  it('jumps to the product slogan when clicking 三大追求', async () => {
    HTMLElement.prototype.scrollIntoView = vi.fn()
    const wrapper = mount(ManualView, { attachTo: document.body })
    const titles = wrapper.findAll('.manual-nav .nav-group-title')
    expect(titles[0].text()).toBe('三大追求')
    expect(titles[1].text()).toBe('三大核心')

    await titles[0].trigger('click')
    expect(wrapper.get('#manual-group-pursuit .intro-slogan').text()).toBe(
      '可靠+好用+易用，是EasyAdapter追求的目标',
    )
    expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('highlights the group title itself when clicking 三大核心 / 配置', async () => {
    HTMLElement.prototype.scrollIntoView = vi.fn()
    const wrapper = mount(ManualView, { attachTo: document.body })
    const titles = wrapper.findAll('.manual-nav .nav-group-title')
    const core = titles.find(node => node.text() === '三大核心')
    const config = titles.find(node => node.text() === '配置')

    await core!.trigger('click')
    expect(core!.classes()).toContain('active')
    expect(wrapper.findAll('.nav-item.active')).toHaveLength(0)

    await config!.trigger('click')
    expect(config!.classes()).toContain('active')
    expect(wrapper.findAll('.nav-item').find(node => node.classes().includes('active'))?.text())
      .toBeUndefined()
    expect(wrapper.findAll('.nav-item').find(node => node.text() === 'Skills')?.classes())
      .not.toContain('active')
    wrapper.unmount()
  })
})
