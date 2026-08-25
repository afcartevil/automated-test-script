// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PipelineRunList from '@/components/tahp/pipeline/PipelineRunList.vue'
import type { RunSummary } from '@/api/tahp/adapt-pipeline'

function run(overrides: Partial<RunSummary> = {}): RunSummary {
  return {
    run_id: 'run-1',
    project_code: 'KM9',
    status: 'failed',
    iteration: 1,
    current_node: 'build',
    created_at: '2026-08-25T00:00:00.000Z',
    updated_at: '2026-08-25T00:00:00.000Z',
    ...overrides,
  }
}

describe('PipelineRunList clone action', () => {
  it('emits clone for any status without selecting the run', async () => {
    const wrapper = mount(PipelineRunList, {
      props: {
        items: [
          run({ run_id: 'a', status: 'running', project_code: 'KM9' }),
          run({ run_id: 'b', status: 'draft', project_code: 'LJ9' }),
        ],
        selectedId: null,
      },
    })

    const cloneButtons = wrapper.findAll('.btn-clone')
    expect(cloneButtons).toHaveLength(2)
    await cloneButtons[0].trigger('click')
    expect(wrapper.emitted('clone')).toEqual([['a']])
    expect(wrapper.emitted('select')).toBeUndefined()
  })
})
