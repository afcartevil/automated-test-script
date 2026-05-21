/**
 * 约束 YAML 文件 CRUD + 校验.
 */
import Router from '@koa/router'
import { readConstraintFile, writeConstraintFile, validateConstraintContent } from '../../services/tahp/constraints-fs'

export const tahpConstraintRoutes = new Router()

const FILE_PATTERN = /^[a-zA-Z0-9_.-]+\.yaml$/
const MODULE_PATTERN = /^[a-zA-Z0-9_-]+$/

function validateNames(module: string, file: string): string | null {
  if (!MODULE_PATTERN.test(module)) return '非法的模块名'
  if (!FILE_PATTERN.test(file)) return '非法的文件名 (只允许 *.yaml)'
  return null
}

// GET /api/tahp/constraints/:module/:file
tahpConstraintRoutes.get('/api/tahp/constraints/:module/:file', async (ctx) => {
  const { module, file } = ctx.params
  const err = validateNames(module, file)
  if (err) { ctx.status = 400; ctx.body = { success: false, error: err }; return }
  try {
    const content = await readConstraintFile(module, file)
    ctx.body = { success: true, data: { module, file, content } }
  } catch (e) {
    ctx.status = 404
    ctx.body = { success: false, error: (e as Error).message }
  }
})

// POST /api/tahp/constraints/validate — body { module, file, content }
tahpConstraintRoutes.post('/api/tahp/constraints/validate', async (ctx) => {
  const body = (ctx.request.body || {}) as Record<string, string>
  const { module, file, content } = body
  const e = validateNames(module || '', file || '')
  if (e) { ctx.status = 400; ctx.body = { success: false, error: e }; return }
  if (typeof content !== 'string') {
    ctx.status = 400
    ctx.body = { success: false, error: 'content 必须为字符串' }
    return
  }
  try {
    const result = await validateConstraintContent(module, file, content)
    ctx.body = { success: true, data: result }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

// PUT /api/tahp/constraints/:module/:file — body { content, skipValidate? }
tahpConstraintRoutes.put('/api/tahp/constraints/:module/:file', async (ctx) => {
  const { module, file } = ctx.params
  const err = validateNames(module, file)
  if (err) { ctx.status = 400; ctx.body = { success: false, error: err }; return }
  const body = (ctx.request.body || {}) as Record<string, unknown>
  const content = body.content
  if (typeof content !== 'string') {
    ctx.status = 400
    ctx.body = { success: false, error: 'content 必须为字符串' }
    return
  }
  try {
    if (!body.skipValidate) {
      const vr = await validateConstraintContent(module, file, content)
      if (!vr.ok) {
        ctx.status = 400
        ctx.body = { success: false, error: '校验失败', data: vr }
        return
      }
    }
    await writeConstraintFile(module, file, content)
    ctx.body = { success: true }
  } catch (e) {
    ctx.status = 500
    ctx.body = { success: false, error: (e as Error).message }
  }
})
