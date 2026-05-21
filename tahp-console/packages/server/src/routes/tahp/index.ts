/**
 * TAHP 路由聚合 — 一次性挂载所有 /api/tahp/* 路由.
 */
import type Koa from 'koa'
import { tahpTaskRoutes } from './tasks'
import { tahpModuleRoutes } from './modules'
import { tahpConstraintRoutes } from './constraints'
import { tahpKnowledgeRoutes } from './knowledge'
import { tahpGateRoutes } from './gate'
import { tahpToolsRoutes } from './tools'
import { tahpReportsRoutes } from './reports'
import { tahpPipelineRoutes } from './pipelines'

export function registerTahpRoutes(app: Koa) {
  app.use(tahpTaskRoutes.routes())
  app.use(tahpModuleRoutes.routes())
  app.use(tahpConstraintRoutes.routes())
  app.use(tahpKnowledgeRoutes.routes())
  app.use(tahpGateRoutes.routes())
  app.use(tahpToolsRoutes.routes())
  app.use(tahpReportsRoutes.routes())
  app.use(tahpPipelineRoutes.routes())
}
