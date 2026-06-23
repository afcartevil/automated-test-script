import { beforeEach, describe, expect, it, vi } from 'vitest'

const sendGerritReviewChatMock = vi.fn()

vi.mock('../../packages/server/src/services/tahp/gerrit-review', () => ({
  sendGerritReviewChat: (...args: unknown[]) => sendGerritReviewChatMock(...args),
}))

describe('gerrit-review routes', () => {
  beforeEach(() => {
    vi.resetModules()
    sendGerritReviewChatMock.mockReset()
  })

  it('returns 400 when message is empty', async () => {
    sendGerritReviewChatMock.mockReturnValue({ ok: false, error: '消息不能为空' })

    const { tahpGerritReviewRoutes } = await import('../../packages/server/src/routes/tahp/gerrit-review')
    const layer = tahpGerritReviewRoutes.stack.find(
      (entry: { path: string }) => entry.path === '/api/tahp/gerrit-review/chat',
    )
    const ctx: {
      request: { body: Record<string, unknown> }
      status?: number
      body?: unknown
    } = { request: { body: { message: '  ' } } }

    await layer!.stack[0](ctx)

    expect(ctx.status).toBe(400)
    expect(ctx.body).toEqual({ success: false, error: '消息不能为空' })
  })

  it('returns 400 when gerrit is not configured', async () => {
    sendGerritReviewChatMock.mockReturnValue({
      ok: false,
      error: 'gerrit账号未设置，无法进行code review，请在设置中完善gerrit账号',
    })

    const { tahpGerritReviewRoutes } = await import('../../packages/server/src/routes/tahp/gerrit-review')
    const layer = tahpGerritReviewRoutes.stack.find(
      (entry: { path: string }) => entry.path === '/api/tahp/gerrit-review/chat',
    )
    const ctx: {
      request: { body: Record<string, unknown> }
      status?: number
      body?: unknown
    } = {
      request: {
        body: { message: 'https://gerrit.transsion.com/c/foo/+/1' },
      },
    }

    await layer!.stack[0](ctx)

    expect(ctx.status).toBe(400)
    expect(ctx.body).toEqual({
      success: false,
      error: 'gerrit账号未设置，无法进行code review，请在设置中完善gerrit账号',
    })
  })

  it('starts chat and returns session_id and task_id', async () => {
    sendGerritReviewChatMock.mockReturnValue({
      ok: true,
      sessionId: 'sess-gerrit-1',
      taskId: 'task-gerrit-1',
    })

    const { tahpGerritReviewRoutes } = await import('../../packages/server/src/routes/tahp/gerrit-review')
    const layer = tahpGerritReviewRoutes.stack.find(
      (entry: { path: string }) => entry.path === '/api/tahp/gerrit-review/chat',
    )
    const ctx: {
      request: { body: Record<string, unknown> }
      status?: number
      body?: unknown
    } = {
      request: {
        body: {
          message: 'https://gerrit.transsion.com/c/MTK_CODE/quark/kernel-5.15/+/1543793',
        },
      },
    }

    await layer!.stack[0](ctx)

    expect(sendGerritReviewChatMock).toHaveBeenCalledWith({
      sessionId: undefined,
      message: 'https://gerrit.transsion.com/c/MTK_CODE/quark/kernel-5.15/+/1543793',
    })
    expect(ctx.body).toEqual({
      success: true,
      data: {
        session_id: 'sess-gerrit-1',
        task_id: 'task-gerrit-1',
        status: 'running',
      },
    })
  })
})
