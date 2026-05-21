/**
 * Pipeline 路由 — 读 playbooks/*.yaml.
 */
import Router from '@koa/router'
import { listPlaybooks, readPlaybook } from '../../services/tahp/constraints-fs'

export const tahpPipelineRoutes = new Router()

tahpPipelineRoutes.get('/api/tahp/pipelines', async (ctx) => {
  try {
    const list = await listPlaybooks()
    ctx.body = { success: true, data: list }
  } catch (err) {
    ctx.status = 500
    ctx.body = { success: false, error: (err as Error).message }
  }
})

tahpPipelineRoutes.get('/api/tahp/pipelines/:file', async (ctx) => {
  const file = ctx.params.file
  if (!/^[a-zA-Z0-9_-]+(\.yaml)?$/.test(file)) {
    ctx.status = 400
    ctx.body = { success: false, error: '非法的 pipeline 名' }
    return
  }
  const fileName = file.endsWith('.yaml') ? file : `${file}.yaml`
  try {
    const content = await readPlaybook(fileName)
    ctx.body = { success: true, data: { name: file, file: fileName, content } }
  } catch (err) {
    ctx.status = 404
    ctx.body = { success: false, error: (err as Error).message }
  }
})
