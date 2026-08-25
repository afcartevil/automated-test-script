// @vitest-environment jsdom
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

vi.mock('naive-ui', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('naive-ui')
  return {
    ...actual,
    NModal: {
      props: ['show', 'closable'],
      emits: ['update:show'],
      template: `
        <div v-if="show" class="n-modal-stub">
          <button
            v-if="closable"
            class="modal-close-x"
            type="button"
            @click="$emit('update:show', false)"
          >x</button>
          <slot name="header" />
          <slot name="header-extra" />
          <slot />
        </div>
      `,
    },
  }
})

import BugAnalysisInteractionModal from '@/components/tahp/BugAnalysisInteractionModal.vue'

function timedOutApproval() {
  return {
    approval_id: 'ap-1',
    command: 'rm -rf /tmp/demo',
    description: '删除临时目录',
    choices: ['once', 'deny'],
    allow_permanent: true,
    timeout_ms: 60_000,
    deadline_at: Date.now() - 1000,
  }
}

describe('BugAnalysisInteractionModal', () => {
  it('shows close X and dismisses a timed-out approval without sending a choice', async () => {
    const wrapper = mount(BugAnalysisInteractionModal, {
      props: {
        approval: timedOutApproval(),
        userInput: null,
      },
    })

    expect(wrapper.get('.modal-close-x').text()).toBe('x')
    expect(wrapper.text()).toContain('已超时')
    expect(wrapper.text()).toContain('关闭')

    await wrapper.get('.modal-close-x').trigger('click')
    expect(wrapper.emitted('dismiss')).toHaveLength(1)
    expect(wrapper.emitted('approval')).toBeUndefined()
  })

  it('footer 关闭 also dismisses after timeout', async () => {
    const wrapper = mount(BugAnalysisInteractionModal, {
      props: {
        approval: timedOutApproval(),
        userInput: null,
      },
    })

    const closeBtn = wrapper.findAll('button').find(b => b.text() === '关闭')
    expect(closeBtn).toBeTruthy()
    await closeBtn!.trigger('click')
    expect(wrapper.emitted('dismiss')).toHaveLength(1)
  })
})
